# dev scripts

Scripts for local development only. **Never run against production data.**

| Script | Purpose |
|---|---|
| `seed_demo.py` | Inserts demo articles with pre-computed `relevance_score` values so the Feed screen is usable before Epic 5 (AI enrichment) has run. Requires a running API + DB. |

## Usage

```bash
# From repo root, with the API running locally:
cd api
python scripts/dev/seed_demo.py
```
