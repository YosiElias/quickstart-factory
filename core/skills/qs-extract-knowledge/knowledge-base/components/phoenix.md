---
name: phoenix
description: Arize Phoenix LLM observability platform deployed as a Helm subchart for tracing LangChain calls via OpenTelemetry
summary: "Arize Phoenix provides LLM observability for AI Quickstarts by tracing LangChain agent calls via OpenTelemetry, deployed as a local Helm subchart (discovered via charts/ directory convention, not listed in Chart.yaml dependencies) that persists traces in the shared PostgreSQL/pgvector database via PHOENIX_SQL_DATABASE_URL from the pgvector Kubernetes secret with PHOENIX_WORKING_DIR=/tmp/phoenix. Use when a quickstart needs LangChain call tracing and trace inspection -- the backend instruments LangChain at module load time via register_phoenix() calling phoenix.otel.register() and explicit LangChainInstrumentor().instrument() before create_app(), sending OTLP traces to COLLECTOR_ENDPOINT (e.g., http://alm-phoenix:6006/v1/traces); port 6006 serves both UI and HTTP collector, port 4317 for gRPC in local compose. Critical config: the init-job uses an oc rollout status init container to block until Phoenix is ready before the backend starts, the Helm chart exposes an OpenShift Route on port 6006 by default, and a test pod verifies connectivity via wget. Gotchas: compose uses postgresql+asyncpg:// for PHOENIX_SQL_DATABASE_URL while Helm sources the URI from the pgvector secret; auto_instrument=True is commented out in phoenix.otel.register() so instrumentation must be done explicitly via LangChainInstrumentor().instrument(); and register_phoenix() must be called at module level before create_app() to ensure all LangChain calls are traced from startup."
metadata:
  type: component
tags:
  tech_stack: [arize-phoenix, opentelemetry, langchain, python]
  ai_pattern: [evaluation, agents]
  platform: [openshift, kubernetes]
  data_layer: [pgvector]
source_examples:
  - quickstart: "ansible-log-analysis"
    repo: "https://github.com/rh-ai-quickstart/ansible-log-analysis"
    notes: "Phoenix deployed as Helm subchart for LangChain observability with PostgreSQL-backed trace storage"
    approach: "A"
---

# Phoenix (Arize Phoenix)

## Overview

Arize Phoenix is an LLM observability platform used in AI Quickstarts to trace and monitor LangChain agent calls. In the ansible-log-analysis quickstart it runs as a standalone Helm subchart, receives OpenTelemetry traces from the FastAPI backend, and persists them in the shared PostgreSQL (pgvector) database. It exposes a web UI on port 6006 for inspecting traces.

## Tech Stack & Dependencies
- **Runtime:** Pre-built container image `arizephoenix/phoenix:latest`
- **Container image:** `arizephoenix/phoenix`
- **Key dependencies:** PostgreSQL database for trace storage (via pgvector secret), backend services instrumented with `arize-phoenix-otel` and `openinference-instrumentation-langchain`
- **Helm subchart:** Local subchart at `deploy/helm/ansible-log-monitor/charts/phoenix/` (chart version 0.1.0)
- **Python client libraries:** `arize-phoenix-otel>=0.13.1`, `openinference-instrumentation-langchain>=0.1.33` (from `pyproject.toml` lines 41-42)

## Key Patterns

### OTEL Registration and LangChain Instrumentation

The backend registers Phoenix tracing at module load time via a utility function. This instruments all LangChain calls automatically before any FastAPI routes are initialized.

From `src/alm/utils/phoenix.py`:
```python
from openinference.instrumentation.langchain import LangChainInstrumentor
from phoenix.otel import register

def register_phoenix():
    phoenix_endpoint = os.getenv("COLLECTOR_ENDPOINT")
    tracer_provider = register(
        project_name="ansible-log-monitor",
        endpoint=phoenix_endpoint,
    )
    LangChainInstrumentor().instrument(tracer_provider=tracer_provider)
    return tracer_provider.get_tracer(__name__)
```

From `src/alm/main_fastapi.py` (lines 10, 18):
```python
from alm.utils.phoenix import register_phoenix
register_phoenix()  # Called at module level, before create_app()
```

### PostgreSQL-Backed Trace Storage

Phoenix is configured to persist traces in the same PostgreSQL instance used by the application, via the `PHOENIX_SQL_DATABASE_URL` environment variable sourced from the pgvector Kubernetes secret.

From `deploy/helm/ansible-log-monitor/charts/phoenix/values.yaml` (lines 137-144):
```yaml
env:
  - name: PHOENIX_SQL_DATABASE_URL
    valueFrom:
      secretKeyRef:
        name: pgvector
        key: uri
  - name: PHOENIX_WORKING_DIR
    value: "/tmp/phoenix"
```

### Init Container Wait Pattern

The backend init-job uses an init container to wait for the Phoenix deployment to be ready before proceeding, ensuring traces can be collected from the start of the pipeline.

From `deploy/helm/ansible-log-monitor/charts/backend/templates/init-job.yaml` (lines 46-57):
```yaml
- name: wait-for-phoenix
  image: quay.io/openshift/origin-cli:4.15
  command:
    - sh
    - -c
    - |
      echo "Waiting for Phoenix deployment to be ready..."
      until oc rollout status deployment/{{ .Release.Name }}-phoenix \
        -n {{ .Release.Namespace }} --timeout=10s; do
        echo "Still waiting..."
        sleep 3
      done
      echo "Phoenix service is ready!"
```

### OpenShift Route Exposure

The Helm subchart enables an OpenShift Route by default (ingress disabled), making the Phoenix UI accessible outside the cluster.

From `deploy/helm/ansible-log-monitor/charts/phoenix/values.yaml` (lines 78-84):
```yaml
route:
  enabled: true
  annotations: {}
  host: ""
  path: ""
  tls: {}
```

## Configuration
- **Environment variables:**
  - `PHOENIX_SQL_DATABASE_URL` -- PostgreSQL connection string for trace persistence (sourced from pgvector secret)
  - `PHOENIX_WORKING_DIR` -- Working directory for Phoenix temp files (set to `/tmp/phoenix`)
  - `COLLECTOR_ENDPOINT` -- Used by the **backend** to send OTLP traces to Phoenix (e.g., `http://alm-phoenix:6006/v1/traces`)
- **Service port:** 6006 (both UI and OTLP HTTP collector); 4317 for OTLP gRPC in local compose deployment
- **Helm values:** `route.enabled: true` (OpenShift Route), `service.type: ClusterIP`, `service.port: 6006`, `autoscaling.enabled: false`

## Known Gotchas
- The compose file uses `postgresql+asyncpg://` in `PHOENIX_SQL_DATABASE_URL` and includes a comment noting the reason: "we dont use DATABASE_URL becuase it point to localhost, and the backend server isnt in the same network as phoenix" (from `deploy/local/compose.yaml` line 74). The Helm deployment avoids this by pulling the URI from the pgvector secret.
- Phoenix must be ready before the backend init-job runs; the init-job uses an `oc rollout status` init container to enforce this ordering (from `backend/templates/init-job.yaml` lines 46-57).
- `register_phoenix()` is called at module load time (line 18 of `main_fastapi.py`), before `create_app()`, so all LangChain calls are instrumented from application startup.
- The `auto_instrument=True` parameter in `phoenix.otel.register()` is commented out in the source (`src/alm/utils/phoenix.py` line 13); instrumentation is done explicitly via `LangChainInstrumentor().instrument()` instead.
- Phoenix is not listed in the parent chart's `dependencies` section in `Chart.yaml` -- it is a local subchart discovered by Helm via the `charts/` directory convention rather than a remote dependency.

## Testing Notes
- The Helm chart includes a test pod (`templates/tests/test-connection.yaml`) that runs `wget` against the Phoenix service to verify connectivity.
- Local development: Phoenix UI is accessible at `http://localhost:6006` (from `deploy/local/README.md`).
- Makefile provides `make phoenix` and `make stop-phoenix` targets for standalone local operation (from `deploy/local/README.md` lines 34, 41).

## Related Patterns
- pgvector -- shared PostgreSQL database used for trace storage
- backend -- FastAPI service that sends OTLP traces to Phoenix via `COLLECTOR_ENDPOINT`
