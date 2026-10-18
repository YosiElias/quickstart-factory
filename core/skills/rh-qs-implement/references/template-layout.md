# Template monorepo layout

Canonical structure from the validated `ai-quickstart-template` monorepo (see commit `2e6d181` or later template releases with `packages/`).

## Directory tree

```
<quickstart-slug>/
├── packages/
│   ├── api/                 # FastAPI (uv, pyproject.toml, Containerfile)
│   │   ├── src/
│   │   │   ├── main.py
│   │   │   ├── core/config.py
│   │   │   ├── routes/
│   │   │   └── schemas/
│   │   └── tests/
│   ├── ui/                  # React + Vite (pnpm, Containerfile)
│   │   └── src/
│   │       ├── routes/      # TanStack Router (file-based)
│   │       ├── components/
│   │       ├── services/    # API client
│   │       └── hooks/
│   ├── db/                  # SQLAlchemy + Alembic
│   │   ├── src/db/
│   │   └── alembic/versions/
│   ├── ingestion/           # Optional: RAG ingest jobs/scripts
│   └── configs/             # Shared eslint, prettier, ruff
├── chart/                   # App chart (api, ui, db, routes, migration job)
├── compose.yml              # Local Postgres (podman-compose)
├── Makefile                 # setup, dev, test, deploy, db-*
├── turbo.json
├── package.json             # Root pnpm + turbo scripts
├── .env.example
└── docs/images/             # Architecture diagrams for README
```

## Package dependencies

```
ui  ──HTTP──►  api  ──import──►  db
ingestion (optional) ──writes──► db / pgvector
```

## Rename checklist

Replace every occurrence of `ai-quickstart-template` with `<slug>`:

| Location | Examples |
|----------|----------|
| Helm | `Chart.yaml` name, `values.yaml` image repos, template labels |
| Compose | service name, volume name, `POSTGRES_DB` |
| Python/Node | package names in `pyproject.toml` / `package.json` if scoped |
| Makefile | `db-start` service names, image build tags |
| Env | `DATABASE_URL`, database name in `.env.example` |

## Common commands

```bash
make setup          # pnpm install + Python deps (uv)
make db-start       # podman-compose up database
make db-upgrade     # alembic upgrade head
make dev            # UI + API dev servers
make test
make lint
make containers-build
make deploy         # Helm to OpenShift (requires logged-in oc/helm)
```

Default local URLs:

- UI: http://localhost:3000
- API: http://localhost:8000 (Swagger: `/docs`)
- Postgres: localhost:5432

## API package conventions

- Routes in `packages/api/src/routes/`; register routers in `main.py`
- Settings via Pydantic `Settings` in `core/config.py`
- Tests: `pytest` with `conftest.py` fixtures; mock DB where appropriate
- Lint/format: Ruff (config may live in `packages/configs/ruff/`)

## UI package conventions

- File-based routes under `src/routes/`
- API calls in `src/services/`; TanStack Query in `src/hooks/`
- Components: atoms → molecules → organisms
- `VITE_API_BASE_URL` for API base URL
- Vitest + Testing Library for unit tests

## DB package conventions

- Models in `packages/db/src/db/models.py`
- New model → Alembic revision → `make db-upgrade`
- API uses `from db import get_session, ...` (editable install via uv workspace)

## Helm app chart

Typical templates:

- `api-deployment.yaml`, `api-service.yaml`
- `ui-deployment.yaml`, `ui-service.yaml`
- `database-deployment.yaml`, `database-pvc.yaml`, `database-service.yaml`
- `migration-job.yaml`
- `routes.yaml` (OpenShift Route)
- `secret.yaml`, `serviceaccount.yaml`

Wire secrets in `values.yaml`; never hardcode production passwords in templates.

## ai-architecture-charts

Use when the quickstart needs cluster-managed AI infrastructure:

- LLM / inference service
- Llama Stack or pipeline server
- MinIO (object storage for documents)
- pgvector (vector store)

Add as Helm dependencies or document separate install steps in README (authored later via `rh-qs-document`). Pin chart versions in `Chart.yaml`.

## Optional ingestion package

For RAG quickstarts:

```
packages/ingestion/
├── pyproject.toml
├── src/
│   ├── load.py          # read documents from data/ or S3
│   ├── chunk.py
│   └── embed.py         # call embedding endpoint; upsert vectors
└── Containerfile        # Job image for OpenShift Job / CronJob
```

Keep sample documents small and license-clear; reference them in README only after `rh-qs-document`.
