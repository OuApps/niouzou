# Railway template — variable setup (maintainer guide)

How to configure the **published "Deploy on Railway" template** so a one-click
deploy asks for **at most one** variable (`OPENROUTER_API_KEY`, and even that can
be optional). Everything else is auto-generated or wired between services.

> This is an **internal/operator** guide, not the marketplace page. The page
> shown to deployers is [`RAILWAY_TEMPLATE.md`](RAILWAY_TEMPLATE.md). The
> per-variable config below lives only in the **Railway template composer**
> (dashboard) — it cannot be set from the CLI. The CLI can read/write the live
> project's variables and publish the template's text, nothing more.

## How Railway decides what to prompt

On the deploy screen, a variable is **only prompted when it has no value**. Give
it any of these and it disappears from the form:

- **`${{ secret(N) }}`** — Railway generates a random N-char secret per deploy.
- **A reference** — `${{ <Service>.VAR }}` (e.g. `${{ Postgres.DATABASE_URL }}`),
  resolved automatically from another service.
- **A default value** — a plain string baked into the template.

`PORT` and every `RAILWAY_*` variable are **injected by the platform** — never
put them in the template. If the form asks for a port, delete that variable in
the composer.

## The recipe (per service)

Open the template in the composer → for each service, set every variable as
below. After this, the only thing left without a value is `OPENROUTER_API_KEY`.

### api
| Variable | Set to |
|---|---|
| `JWT_SECRET` | `${{ secret(32) }}` |
| `DATABASE_URL` | `${{ Postgres.DATABASE_URL }}` |
| `MINIFLUX_URL` | `http://${{ miniflux.RAILWAY_PRIVATE_DOMAIN }}:8080` |
| `REFRESH_WORKER_URL` | `http://${{ refresh-worker.RAILWAY_PRIVATE_DOMAIN }}:8000` |
| `OPENROUTER_MODEL` | `google/gemma-4-26b-a4b-it:free` |
| `OPENROUTER_API_KEY` | **leave empty / optional** — the only real input |

### refresh-worker
| Variable | Set to |
|---|---|
| `JWT_SECRET` | `${{ api.JWT_SECRET }}` (or remove — the worker doesn't use it) |
| `DATABASE_URL` | `${{ Postgres.DATABASE_URL }}` |
| `MINIFLUX_URL` | `http://${{ miniflux.RAILWAY_PRIVATE_DOMAIN }}:8080` |
| `OPENROUTER_MODEL` | `google/gemma-4-26b-a4b-it:free` |
| `OPENROUTER_API_KEY` | empty / optional (same as api) |
| `CRON_FETCH_INTERVAL` | `30` |
| `CRON_NIGHTLY_REFRESH_HOUR` | `3` |
| `EMBEDDING_NUM_THREADS` / `OMP_NUM_THREADS` | `3` |
| `RAILWAY_CONFIG_FILE` | `refresh-worker.railway.toml` (fixed) |

### miniflux
| Variable | Set to |
|---|---|
| `DATABASE_URL` | `postgres://${{ Postgres.PGUSER }}:${{ Postgres.PGPASSWORD }}@${{ Postgres.RAILWAY_PRIVATE_DOMAIN }}:${{ Postgres.PGPORT }}/miniflux?sslmode=disable` |
| `ADMIN_USERNAME` | `admin` |
| `ADMIN_PASSWORD` | `${{ secret(16) }}` |
| `CREATE_ADMIN` | `1` |
| `RUN_MIGRATIONS` | `1` |

### pwa
| Variable | Set to |
|---|---|
| `VITE_API_URL` | `https://${{ api.RAILWAY_PUBLIC_DOMAIN }}/api/v1` |

### Postgres
Railway's Postgres image manages its own credentials — nothing to configure.

## Steps

1. Open the template: **Railway → your workspace → Templates → niouzou → Edit**.
2. For each service above, set every variable to the value in the table.
3. **Delete** any `PORT` or `RAILWAY_*` variable that appears.
4. Decide on `OPENROUTER_API_KEY`: mark it optional (zero prompts, the feed runs
   without AI until a key is added) or required (one prompt).
5. **Publish/Update** the template.

## Before publishing — security check

Confirm no real production secret value got baked in:

- `JWT_SECRET` must be `${{ secret(...) }}`, **not** your prod value.
- `OPENROUTER_API_KEY` must be **empty**, never your real `sk-or-...` key —
  otherwise everyone who deploys uses (and bills) your account.

## Note

The reference/secret config above is composer-only. Regenerating the template
from the project preserves references but **not** `secret()` generation, so the
secrets still have to be set here by hand.
