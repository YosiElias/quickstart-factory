---
name: fastapi-backend
description: "FastAPI backend with LangGraph agent pipelines, async PostgreSQL, and LLM-powered log analysis on RHOAI"
summary: "Implements a FastAPI backend intelligence layer for Ansible log monitoring on RHOAI that receives Grafana alerts and processes them through a nested LangGraph StateGraph pipeline (outer graph clusters logs via scikit-learn/sentence-transformers, inner graph summarizes/classifies/routes to direct solution or Loki/RAG context-gathering with streaming LLM fallback returning partial results on interruption), persisting results to async PostgreSQL via SQLModel+asyncpg and ML artifacts to MinIO. Use this pattern when building a multi-step LLM agent backend on RHOAI that needs dual LLM endpoints (separate OPENAI_API_TOKEN/ENDPOINT vs OPENAI_API_TOKEN_WITH_TOOL_CALLING/ENDPOINT_WITH_TOOL_CALLING env vars to work around model-serving endpoints lacking tool-call support), dynamic route auto-discovery from src/alm/routes/, singleton RAG handler with configurable top_k/top_n/similarity_threshold, and Phoenix/OTEL tracing. Critical infrastructure: Kubernetes init job (backoffLimit: 3) chaining wait-for-postgres/phoenix/loki/alloy init containers that must complete before the Deployment starts (Deployment uses `oc wait --for=condition=complete` in a wait-for-init-job init container requiring origin-cli image and RBAC), multi-stage UBI8 Python 3.12 container with CPU-only PyTorch via custom PyPI index and `uv sync --frozen`, OpenShift group-0 file permissions (`chgrp -R 0; chmod -R g=u`), health probes at /health, and Helm subchart at deploy/helm/ansible-log-monitor/charts/backend. Common gotchas: DATABASE_URL in the pgvector Secret (key: uri) must use standard `postgresql://` because the code does string replacement to force `+asyncpg` dialect, `OPENAI_TEMPERATURE` must always be set or the backend crashes at module import with TypeError, init job waits 600s for RAG service (set `RAG_ENABLED=false` to skip), and the Deployment requires 2 CPU/8Gi memory plus 2-4Gi ephemeral storage for sentence-transformer model downloads at startup."
metadata:
  type: component
tags:
  tech_stack: [fastapi, python, langchain, langgraph, uvicorn, sqlmodel, asyncpg, postgresql, httpx, minio, scikit-learn, sentence-transformers]
  ai_pattern: [agents, rag, embeddings, prompt-chaining]
  platform: [rhoai, openshift]
  data_layer: [pgvector, minio, faiss]
source_examples:
  - quickstart: "ansible-log-analysis"
    repo: "https://github.com/rh-ai-quickstart/ansible-log-analysis"
    notes: "FastAPI backend with LangGraph multi-step agent graph for Ansible log analysis, clustering, and RAG-augmented remediation"
    approach: "A"
---

# FastAPI Backend

## Overview

FastAPI backend serving as the core intelligence layer for an Ansible log monitoring quickstart on RHOAI. Receives log alerts (e.g. from Grafana), runs them through a LangGraph agent pipeline that summarizes, classifies, optionally fetches additional context from Loki and a RAG knowledge base, and produces step-by-step remediation. Persists results to PostgreSQL via async SQLModel and stores ML artifacts in MinIO.

## Tech Stack & Dependencies

- **Runtime:** Python >= 3.12, FastAPI >= 0.116.1, Uvicorn
- **Container image:** `quay.io/rh-ai-quickstart/alm-backend` (multi-stage build from `registry.access.redhat.com/ubi8/python-312`)
- **Key dependencies:** LangChain + LangGraph (agent orchestration), langchain-openai (OpenAI-compatible LLM calls via RHOAI endpoints), SQLModel + asyncpg (async PostgreSQL), httpx (RAG service client), Minio SDK (object storage), scikit-learn + sentence-transformers (clustering), arize-phoenix-otel (observability)
- **Helm subchart:** `deploy/helm/ansible-log-monitor/charts/backend` (custom application chart, v0.1.0)

## Key Patterns

### Dynamic Router Discovery

Route modules are auto-discovered at startup. Any Python module under `src/alm/routes/` that exposes a module-level `router: APIRouter` variable is automatically registered.

```python
# src/alm/main_fastapi.py
def _include_route_modules(app: FastAPI) -> None:
    routes_dir = current_dir.parent / "routes"
    routes_package = f"{package_name}.routes"
    for module_info in pkgutil.iter_modules([str(routes_dir)]):
        module_name = f"{routes_package}.{module_info.name}"
        module = importlib.import_module(module_name)
        router = getattr(module, "router", None)
        if isinstance(router, APIRouter):
            app.include_router(router)
```

### LangGraph Multi-Step Agent Pipeline

The core inference flow is a LangGraph `StateGraph` with two nested levels. The outer graph clusters the log, then delegates to an inner graph that summarizes, classifies, routes to either direct solution or context-gathering, and finally generates a step-by-step solution.

```python
# src/alm/agents/graph.py
def inference_graph():
    builder = StateGraph(GrafanaAlertState)
    builder.add_edge(START, "cluster_logs_node")
    builder.add_node("cluster_logs_node", cluster_logs_node)
    builder.add_node(no_clustering_graph_node)
    return builder.compile()
```

The inner graph uses `Command` objects to route between nodes, with a conditional branch deciding whether additional context from Loki/RAG is needed before generating the solution.

### Dual LLM Endpoint Pattern

The backend supports two separate LLM endpoint configurations: a default endpoint for structured output calls (`OPENAI_API_TOKEN` / `OPENAI_API_ENDPOINT`) and a separate tool-calling-capable endpoint (`OPENAI_API_TOKEN_WITH_TOOL_CALLING` / `OPENAI_API_ENDPOINT_WITH_TOOL_CALLING`). This works around model-serving endpoints on RHOAI that may not support tool calling.

```python
# src/alm/llm.py
def get_llm_support_tool_calling():
    API_KEY_WITH_TOOL_CALLING = os.getenv("OPENAI_API_TOKEN_WITH_TOOL_CALLING")
    BASE_URL_WITH_TOOL_CALLING = os.getenv("OPENAI_API_ENDPOINT_WITH_TOOL_CALLING")
    MODEL_WITH_TOOL_CALLING = os.getenv("OPENAI_MODEL_WITH_TOOL_CALLING")
    if API_KEY_WITH_TOOL_CALLING and BASE_URL_WITH_TOOL_CALLING and MODEL_WITH_TOOL_CALLING:
        return ChatOpenAI(api_key=API_KEY_WITH_TOOL_CALLING, base_url=BASE_URL_WITH_TOOL_CALLING, ...)
    else:
        return get_llm()
```

### Singleton RAG Handler with Lazy Initialization

The RAG integration uses a singleton `RAGHandler` that lazily connects to a separate RAG microservice via httpx. It queries `POST /rag/query` with configurable top_k, top_n, and similarity_threshold parameters.

```python
# src/alm/utils/rag_handler.py
class RAGHandler:
    _instance: Optional["RAGHandler"] = None
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def _initialize_rag_service(self):
        self._client = httpx.AsyncClient(base_url=self._rag_service_url, timeout=30.0)
```

### Streaming LLM with Fallback

The solution-generation step uses async streaming with a fallback that returns partial results if the stream is interrupted mid-response, rather than failing entirely.

```python
# src/alm/llm.py
async def stream_with_fallback(llm, messages):
    collected_output = []
    try:
        async for chunk in llm.astream(messages):
            if chunk.content:
                collected_output.append(chunk.content)
    except Exception as e:
        if len(collected_output) == 0:
            raise e
    return "".join(collected_output)
```

### Init Job with Service Dependency Chain

The backend uses a Kubernetes Job (`init-job.yaml`) that runs `backend_init_pipeline.py` before the main Deployment starts. The init job has a chain of init containers that wait for PostgreSQL, Phoenix (tracing), Loki, and Alloy (log collector) to be ready before executing the training pipeline. The Deployment itself has a `wait-for-init-job` init container that blocks until this Job completes.

```yaml
# deploy/helm/ansible-log-monitor/charts/backend/templates/init-job.yaml
initContainers:
  - name: wait-for-postgres
    image: postgres:15-alpine
    command: ["sh", "-c", "until pg_isready -d \"$DATABASE_URL\"; do sleep 5; done"]
  - name: wait-for-phoenix
    image: quay.io/openshift/origin-cli:4.15
    command: ["sh", "-c", "until oc rollout status deployment/...; do sleep 3; done"]
  - name: wait-for-loki
    ...
  - name: wait-for-alloy
    ...
```

### Multi-Stage Container Build with CPU-Only PyTorch

The Containerfile uses a two-stage build with UBI8 Python 3.12. PyTorch is installed as CPU-only via a custom PyPI index to avoid pulling CUDA dependencies, which keeps the image small. The `uv` package manager is used with `--frozen` lock file.

```dockerfile
# Containerfile
FROM registry.access.redhat.com/ubi8/python-312 AS builder
COPY --from=ghcr.io/astral-sh/uv:0.9.7 /uv /uvx /bin/
RUN UV_HTTP_TIMEOUT=600 TORCH_CUDA_ARCH_LIST="" uv sync --frozen --no-install-project --no-dev
```

The pyproject.toml configures the CPU-only PyTorch index:

```toml
# pyproject.toml
[[tool.uv.index]]
name = "pytorch-cpu"
url = "https://download.pytorch.org/whl/cpu"
explicit = true
[tool.uv.sources]
torch = [{ index = "pytorch-cpu" }]
```

### OpenShift-Compatible File Permissions

The runtime stage sets group-0 permissions for OpenShift's random UID assignment:

```dockerfile
# Containerfile
RUN mkdir -p /app/data/logs/failed /hf_cache && \
    chgrp -R 0 /app /hf_cache && \
    chmod -R g=u /app /hf_cache
```

## Configuration

- **Environment variables:**
  - `OPENAI_API_TOKEN` / `OPENAI_API_ENDPOINT` / `OPENAI_MODEL` / `OPENAI_TEMPERATURE` -- primary LLM (via RHOAI model serving)
  - `OPENAI_API_TOKEN_WITH_TOOL_CALLING` / `OPENAI_API_ENDPOINT_WITH_TOOL_CALLING` / `OPENAI_MODEL_WITH_TOOL_CALLING` -- optional separate LLM supporting tool calling
  - `DATABASE_URL` -- PostgreSQL connection string (injected from `pgvector` Secret)
  - `MINIO_ENDPOINT` / `MINIO_PORT` / `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY` -- MinIO object storage (injected from `minio` Secret)
  - `RAG_SERVICE_URL` / `RAG_ENABLED` / `RAG_TOP_K` / `RAG_TOP_N` / `RAG_SIMILARITY_THRESHOLD` -- RAG microservice integration
  - `COLLECTOR_ENDPOINT` -- Phoenix/OTEL tracing endpoint
  - `LOKI_URL` / `LOKI_MCP_SERVER_URL` -- Loki log backend and MCP server
  - `CLUSTERING_HOST` / `CLUSTERING_PORT` / `CLUSTERING_ALGORITHM` / `SENTENCE_TRANSFORMER_MODEL_NAME` -- clustering service and model config
  - `LOG_LEVEL` / `LOG_FORMAT` -- logging configuration (supports `pretty` and `json` formats)
- **Config files:** `.env` file loaded via `python-dotenv` at startup; Helm ConfigMap for cluster deployment
- **Helm values:** Image at `quay.io/rh-ai-quickstart/alm-backend:latest`, ClusterIP service on port 8000, health probes at `/health`, resource limits of 2 CPU / 8Gi memory (needed for sentence-transformer model loading), init job with `backoffLimit: 3`

## Known Gotchas

- The database engine creation in `src/alm/database.py` does a string replacement on the DATABASE_URL to force the `postgresql+asyncpg` dialect: `.replace("+asyncpg", "").replace("postgresql", "postgresql+asyncpg")`. This means the `pgvector` Secret must provide a `uri` key with a standard `postgresql://` connection string, not one already containing `+asyncpg`.
- The `OPENAI_TEMPERATURE` env var is cast with `float()` at module import time in `src/alm/llm.py` without a default, so it must always be set or the backend will crash on startup with a `TypeError`.
- The init job runs `backend_init_pipeline.py` which waits up to 600 seconds (10 minutes) for the RAG service to be ready. If the RAG service is not deployed, set `RAG_ENABLED=false` to skip this wait.
- Ephemeral storage requests of 2-4Gi are configured in Helm values because the init pipeline downloads HuggingFace models (sentence-transformers) during startup.
- The Deployment has a `wait-for-init-job` init container using `oc wait --for=condition=complete`, which requires the `origin-cli` image and appropriate RBAC to query Job status in the namespace.

## Testing Notes

- Health endpoint at `GET /health` returns `{"status": "ok"}` -- used by both liveness and readiness probes
- Root endpoint at `GET /` returns `{"service": "alm", "status": "ok"}`
- The init job must complete before the Deployment starts; check Job status with `oc get jobs -l app.kubernetes.io/component=init`
- Phoenix tracing is always registered at startup; verify traces arrive at the `COLLECTOR_ENDPOINT`

## Related Patterns

- RAG service integration (separate microservice at `alm-rag:8002`)
- Clustering service (separate microservice at `alm-clustering:8001`)
- Loki MCP server for log tool calling
- PostgreSQL with pgvector for alert persistence
- MinIO for ML artifact storage (clustering models)
