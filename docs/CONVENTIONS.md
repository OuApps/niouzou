# Conventions — Niouzou

## Language

- **Code**: English (variables, functions, classes, comments, commit messages)
- **User-facing strings**: English (MVP)
- **Documentation**: English

---

## Repository Structure

```
niouzou/
├── CLAUDE.md                  ← agent bootstrap (read first)
├── LICENSE
├── README.md
├── .env.example
├── docker-compose.yml         ← self-hosting stack
├── docker-compose.test.yml    ← throwaway Postgres for pytest
├── railway.toml
├── infra/
│   └── postgres-init/         ← creates the miniflux DB on first boot
├── docs/
│   ├── PRD.md
│   ├── ARCHITECTURE.md
│   ├── DATA_MODEL.md
│   ├── API_SPEC.md
│   ├── DESIGN_SYSTEM.md
│   ├── EPICS.md
│   └── CONVENTIONS.md
├── api/
│   ├── Dockerfile
│   ├── pyproject.toml
│   └── niouzou/
│       ├── main.py
│       ├── db.py
│       ├── config.py
│       ├── routers/
│       │   ├── auth.py
│       │   ├── feed.py
│       │   ├── articles.py
│       │   ├── feedback.py
│       │   ├── sources.py
│       │   └── keywords.py
│       ├── services/
│       │   ├── auth_service.py
│       │   ├── feed_service.py
│       │   ├── feedback_service.py
│       │   ├── sources_service.py
│       │   └── keywords_service.py
│       ├── models/            ← SQLAlchemy ORM models
│       ├── schemas/           ← Pydantic request/response schemas
│       ├── scoring/
│       │   ├── base.py        ← BaseScorer
│       │   ├── tfidf.py       ← TFIDFScorer (pipeline unit tests only since E16-S8)
│       │   ├── ai_keyword.py  ← AIKeywordScorer
│       │   ├── pipeline.py    ← ScoringPipeline
│       │   └── smart_match.py ← Smart Match k-NN (E16, DB-backed)
│       ├── crons/
│       │   ├── fetch.py
│       │   ├── enrich.py
│       │   └── nightly_refresh.py  ← weights + dual-score rescore (ex refresh_weights, E16-S9)
│       └── migrations/        ← Alembic
└── pwa/
    ├── Dockerfile
    ├── index.html
    ├── vite.config.ts
    ├── package.json
    └── src/
        ├── main.tsx
        ├── App.tsx
        ├── api/               ← API client (axios instance + typed functions)
        ├── components/        ← reusable UI components
        │   ├── BlobBackground.tsx
        │   ├── ArticleCard.tsx
        │   ├── BottomNav.tsx
        │   └── ...
        ├── screens/           ← one file per route
        │   ├── Feed.tsx
        │   ├── ArticleDetail.tsx
        │   ├── Saved.tsx
        │   ├── Keywords.tsx
        │   ├── Profile.tsx
        │   ├── Sources.tsx
        │   ├── Login.tsx
        │   └── Register.tsx
        ├── hooks/             ← custom React hooks
        ├── store/             ← global state (Zustand or Context)
        └── types/             ← TypeScript types mirroring API schemas
```

---

## Backend (Python / FastAPI)

### General rules
- Python 3.13
- Dependency management: `uv` (fast, modern) with `pyproject.toml`
- All settings via `config.py` using `pydantic-settings` — never read `os.environ` directly outside config
- Never put business logic in routers — routers call services, services call DB
- Never call the DB directly from a router

### Naming
```python
# Files: snake_case
feed_service.py

# Classes: PascalCase
class FeedService: ...
class TFIDFScorer: ...

# Functions and variables: snake_case
def get_feed_articles(user_id: UUID) -> list[ArticleSchema]: ...
article_relevance_score = 0.87

# Constants: UPPER_SNAKE_CASE
SCORE_THRESHOLD = 0.0
```

### Database
- ORM: SQLAlchemy 2.0 (async)
- Migrations: Alembic — never modify tables manually
- One session per request via FastAPI dependency injection
- Use `select()` syntax, not legacy `Query`

### API patterns
```python
# Router: thin, delegates to service
@router.get("/feed", response_model=FeedResponse)
async def get_feed(
    cursor: str | None = None,
    user: User = Depends(get_current_user),
    service: FeedService = Depends()
):
    return await service.get_feed(user_id=user.id, cursor=cursor)

# Service: all business logic lives here
class FeedService:
    async def get_feed(self, user_id: UUID, cursor: str | None) -> FeedResponse:
        ...
```

### Error handling
- Use FastAPI `HTTPException` with explicit status codes
- Never return 200 with an error payload
- Validation errors handled automatically by Pydantic

### Scoring
- Always subclass `BaseScorer` for new *pure* scorers (no I/O)
- `ScoringPipeline` is the only entry point for the keyword scorers — never
  call them directly from services. Since E16-S8 the pipeline is only used
  for the pure relevance maths (Σ salience × weight → sigmoid); keyword
  *extraction* comes from the combined enrichment LLM call (`TFIDFScorer`
  survives for pipeline unit tests but is never wired into `cron_enrich`)
- Scorer output is an unbounded float; normalisation to 0.0–1.0 happens in `ScoringPipeline`
- **Exception (E16):** `scoring/smart_match.py` needs the DB (the user's
  feedback neighbours) so it lives outside `BaseScorer`. It is only ever
  invoked through `ScoringService.score_article_for_user`, which computes
  and upserts BOTH `keyword_score` and `smart_score` on every pass (E16-S8,
  whatever `scoring_mode`) — never call `smart_score` from a router or
  another service
- **Embeddings:** the model is loaded only via `services/embedding_service.py`
  (lazy singleton). Tests NEVER load the real model — inject a fake encoder
  (see `tests/fake_embeddings.py` and the conftest tripwire)

### Content extraction & boilerplate (E10-S6)
- `EnrichmentService.extract_content` falls back to the RSS body whenever
  `newspaper4k` fails **or** returns recognised paywall/CGU boilerplate (a
  site's RGPD footer or cookie-wall). Without this, a non-empty junk footer
  would be stored as `content`, summarised by the LLM (hallucinated summary),
  and dodge the `is_premium` length check.
- The detector (`_is_boilerplate`) is **best-effort and extensible**, two
  tiers: (1) exact normalized-text match against full known templates
  (near-zero false positives); (2) marker groups — a group trips only when
  **all** its substrings co-occur (case-insensitive). Markers must be
  **source-specific** (emails like `dpo@ebra.fr`, CMS-only phrasings), never
  generic privacy vocabulary (`RGPD`, `cookies`, `CNIL`) that a legitimate
  article *about* that topic would contain.
- Built-in lists live in `enrichment_service.py`; operators extend them
  without a code change via `ENRICHMENT_BOILERPLATE_EXACT` (templates) and
  `ENRICHMENT_BOILERPLATE_MARKERS` (groups) — `|||` separates templates/groups,
  `&&` separates substrings within a group. **Add a new pattern here whenever
  another paywall source surfaces.**
- One-shot recovery of already-stored boilerplate rows:
  `python -m niouzou.tools.backfill_boilerplate_content` (`--all` for the
  whole corpus) — pulls the original RSS body back from Miniflux and re-runs
  the normal enrichment.

---

## Frontend (React / TypeScript)

### General rules
- TypeScript strict mode enabled
- No `any` types — if the shape is unknown, use `unknown` and narrow it
- All API response types defined in `src/types/` and kept in sync with `docs/API_SPEC.md`
- Component files: one component per file, named export preferred

### Naming
```ts
// Files: PascalCase for components, camelCase for hooks/utils
ArticleCard.tsx
useSwipeGesture.ts
formatTimeAgo.ts

// Components: PascalCase
const ArticleCard = ({ article }: ArticleCardProps) => { ... }

// Hooks: camelCase, prefixed with `use`
const useFeed = () => { ... }

// Types/interfaces: PascalCase
interface ArticleSchema { ... }
type FeedbackAction = 'like' | 'dislike' | 'skip' | 'save'
```

### Design system
- Always refer to `docs/DESIGN_SYSTEM.md` before writing any styles
- No hardcoded colors outside of CSS variables defined in DESIGN_SYSTEM.md
- Tailwind utility classes for layout and spacing
- Inline styles only for dynamic values (e.g. animation transforms, computed widths)
- `BlobBackground` must be rendered on every screen — never omit it

### State management
- Local component state: `useState` / `useReducer`
- Server state (API data, loading, errors): React Query (`@tanstack/react-query`)
- Global client state (auth token, user): Zustand — token persisted in localStorage
- No Redux

### API calls
- All API calls go through `src/api/` — never call `fetch` or `axios` directly from a component
- Use React Query for all data fetching
- Optimistic updates for feedback actions (swipe must feel instant)
- Auth token read from Zustand store (which hydrates from localStorage on init)

---

## Git

### Commit messages
```
feat: add swipe gesture to feed cards
fix: prevent duplicate articles on cursor pagination
chore: update dependencies
docs: add API_SPEC endpoints for keywords
refactor: extract scoring pipeline into separate module
```

### Branch naming
```
feat/e1-s2-feed-screen
fix/cursor-pagination-duplicates
chore/docker-compose-setup
```

Format: `type/epic-story-short-description`

---

## Environment Variables

- All env vars documented in `docs/ARCHITECTURE.md`
- Template always kept up to date in `.env.example`
- Never commit `.env` — it is gitignored
- Optional vars must have sensible defaults in `config.py`
- Frontend vars prefixed with `VITE_`

---

## Testing

- Backend: `pytest` + `pytest-asyncio`
- Frontend: `vitest` + `@testing-library/react`
- Focus tests on services and scoring logic — not on routers or UI details
- Each scorer must have unit tests covering: neutral user (no history), positive keywords, negative keywords, mixed

## Continuous integration

- GitHub Actions: `.github/workflows/ci.yml` runs on every push to `main` and
  every PR targeting it.
- Two jobs:
  - `test-api` — boots a PostgreSQL 17 service container, applies Alembic
    migrations, then runs the pytest suite via `uv`.
  - `test-pwa` — installs PWA deps with `npm ci`, then `npm run build`
    (TypeScript project references + Vite production build).
- A failing job blocks the merge. Secrets (none required today) are stored as
  GitHub Actions secrets, never inlined in the workflow file.

---

## What agents must do before writing any code

1. Read `CLAUDE.md`
2. Read the relevant Epic and Story in `docs/EPICS.md`
3. Read `docs/ARCHITECTURE.md` for structural decisions
4. Read `docs/DATA_MODEL.md` before touching anything DB-related
5. Read `docs/API_SPEC.md` before implementing any endpoint or API call
6. Read `docs/DESIGN_SYSTEM.md` before writing any frontend code