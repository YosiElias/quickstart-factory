---
name: rh-qs-helm-add-llamastack
description: Add Llama Stack and related ai-architecture-charts subcharts (llm-service, pgvector) to an existing quickstart Helm chart. Use when wiring cluster LLM/RAG, enabling llamastack provider in the API, or deploying models via the shared charts repo.
---

# rh-qs-helm-add-llamastack

## Purpose

Add [Llama Stack](https://github.com/meta-llama/llama-stack) to a quickstart using subcharts from [ai-architecture-charts](https://github.com/rh-ai-quickstart/ai-architecture-charts). The umbrella app chart stays in the quickstart repo; inference, vector DB, and model serving come from the shared charts.

## When to use

- The quickstart already has (or is getting) a Helm chart under `chart/`
- The functional design calls for Llama Stack (agents, RAG, tools) on OpenShift / OpenShift AI
- You need to enable a specific Hugging Face model, a remote OpenAI-compatible endpoint, or bundled pgvector

Do **not** use for greenfield scaffolding of the whole app (see `rh-qs-scaffold` / `rh-qs-implement`). Do **not** commit real tokens or API keys in `values.yaml`.

## Reference implementations

Study these before editing (patterns vary by use case):

| Repo | Pattern |
|------|---------|
| [ai-supply-chain-agent](https://github.com/rh-ai-quickstart/ai-supply-chain-agent) | `llama-stack` + `llm-service` + top-level `pgvector`; local 1B model; `LLAMA_STACK_URL` on API |
| [spending-transaction-monitor](https://github.com/rh-ai-quickstart/spending-transaction-monitor) | `llama-stack` with `llama-stack.pgvector`; **remote** model via `global.models.remote-llm`; `llm-service.enabled: false` |
| [RAG](https://github.com/rh-ai-quickstart/RAG) | Full stack: `llama-stack`, `llm-service`, `pgvector`, pipelines, MCP |

Upstream chart defaults and all model keys: [llm-service/helm/values.yaml](https://github.com/rh-ai-quickstart/ai-architecture-charts/blob/main/llm-service/helm/values.yaml) and [llama-stack/helm/values.yaml](https://github.com/rh-ai-quickstart/ai-architecture-charts/blob/main/llama-stack/helm/values.yaml).

## Workflow

### 1. Add subchart dependencies

In the app chart `Chart.yaml`, add dependencies from the published repo. Pin versions to match a known-good quickstart or the latest [ai-architecture-charts releases](https://github.com/rh-ai-quickstart/ai-architecture-charts/releases).

```yaml
dependencies:
  - name: llama-stack
    version: 0.7.3   # pin to a tested version; bump deliberately
    repository: https://rh-ai-quickstart.github.io/ai-architecture-charts
    condition: llama-stack.enabled
  - name: llm-service
    version: 0.5.9
    repository: https://rh-ai-quickstart.github.io/ai-architecture-charts
    condition: llm-service.enabled
  - name: pgvector
    version: 0.5.5
    repository: https://rh-ai-quickstart.github.io/ai-architecture-charts
    condition: pgvector.enabled
```

Include only what the design needs:

| Subchart | Add when |
|----------|----------|
| `llama-stack` | Always for this skill |
| `llm-service` | Models are **deployed on-cluster** (vLLM / HF download), not a remote-only URL |
| `pgvector` (top-level) | App or ingestion uses a **standalone** pgvector service (separate from Llama Stack’s bundled DB) |
| `llama-stack.pgvector` | Vector store should be **owned by Llama Stack** (typical RAG-with-LS path) |

Then refresh vendored charts:

```bash
cd chart
helm dependency update
```

### 2. Minimal Llama Stack enablement

In `values.yaml`, enable Llama Stack and its bundled pgvector unless the project already runs pgvector elsewhere:

```yaml
llama-stack:
  enabled: true
  pgvector:
    enabled: true
```

If the quickstart **already** deploys a top-level `pgvector` subchart (or an external Postgres with pgvector), set `llama-stack.pgvector.enabled: false` and point Llama Stack storage at that instance via parent overrides documented in [llama-stack/helm/values.yaml](https://github.com/rh-ai-quickstart/ai-architecture-charts/blob/main/llama-stack/helm/values.yaml) (`storage`, `vectorIOKvstore`, etc.).

Avoid running **two** pgvector instances for the same data unless intentional.

### 3. Model configuration (choose one path)

Models are configured under **`global.models`**. The chart merges these into both `llm-service` and `llama-stack` where applicable.

#### Path A — Remote LLM (`--remote`)

Use when inference lives outside the cluster (OpenShift AI endpoint, hosted vLLM, etc.). Disable on-cluster `llm-service`.

```yaml
global:
  models:
    remote-llm:
      id: custom-model-id
      url: https://custom-server-url/v1
      apiToken: ""          # set via secret/CI, not committed
      enabled: true

llm-service:
  enabled: false

llama-stack:
  enabled: true
  pgvector:
    enabled: true   # if RAG; omit or false if not needed
```

Set `id`, `url`, and `apiToken` from user input. Never commit real tokens.

#### Path B — Cluster-deployed model (`--model <key>`)

Use when `llm-service` pulls and serves a model on GPU/CPU nodes. Enable `llm-service` and set exactly one (or the models the user asked for) to `enabled: true`.

1. Copy the model catalog block from [llm-service/helm/values.yaml](https://github.com/rh-ai-quickstart/ai-architecture-charts/blob/main/llm-service/helm/values.yaml) into `global.models`.
2. Enable the entry matching `--model` (e.g. `llama-3-2-1b-instruct`).
3. Adjust **tolerations**: keep the `nvidia.com/gpu` block on GPU nodes; **comment out** tolerations on CPU-only clusters.

Example (1B instruct on cluster):

```yaml
global:
  models:
    llama-3-2-1b-instruct:
      id: meta-llama/Llama-3.2-1B-Instruct
      enabled: true
      tolerations:
        - key: "nvidia.com/gpu"
          operator: Exists
          effect: NoSchedule

llm-service:
  enabled: true
  secret:
    hf_token: ""      # required for gated HF models; use --api-key when provided
    enabled: true

llama-stack:
  enabled: true
  pgvector:
    enabled: true
```

**Pre-configured model keys** (enable the one you need; others stay `enabled: false`):

| Key | Model id |
|-----|----------|
| `llama-3-2-1b-instruct` | `meta-llama/Llama-3.2-1B-Instruct` |
| `llama-3-1-8b-instruct` | `meta-llama/Llama-3.1-8B-Instruct` |
| `llama-3-2-1b-instruct-quantized` | `RedHatAI/Llama-3.2-1B-Instruct-quantized.w8a8` |
| `llama-3-2-3b-instruct` | `meta-llama/Llama-3.2-3B-Instruct` |
| `llama-3-3-70b-instruct` | `meta-llama/Llama-3.3-70B-Instruct` |
| `llama-3-3-70b-instruct-quantization-fp8` | `meta-llama/Llama-3.3-70B-Instruct` |
| `llama-guard-3-1b` | `meta-llama/Llama-Guard-3-1B` |
| `llama-guard-3-8b` | `meta-llama/Llama-Guard-3-8B` |
| `qwen-2-5-vl-3b-instruct` | `Qwen/Qwen2.5-VL-3B-Instruct` |

For the full catalog with tolerations and advanced options (RHOAI custom models, safety shields), copy from the upstream `values.yaml` link above rather than duplicating the entire block in the quickstart.

#### Hugging Face token (`--api-key`)

When the user passes `--api-key`, set:

```yaml
llm-service:
  secret:
    hf_token: "<from user or secret store>"
    enabled: true
```

Document the variable in `.env.example` as `HF_TOKEN` (local) and instruct cluster deployers to use a Secret or `-f` values overlay. Leave `hf_token: ""` in committed defaults.

### 4. Wire the application

Point API/UI workloads at the in-cluster Llama Stack service (default Service name `llamastack`, port `8321`):

```yaml
# Example — adjust keys to match templates (.env.example, secrets, deployment env)
secrets:
  LLM_PROVIDER: "llamastack"
  LLAMASTACK_BASE_URL: "http://llamastack:8321"
```

Or per-deployment env (supply-chain pattern):

```yaml
backend:
  env:
    LLAMA_STACK_URL: "http://llamastack.<release-namespace>.svc.cluster.local:8321"
    LLAMA_STACK_MODEL: "meta-llama/Llama-3.2-1B-Instruct"
```

Use the **cluster DNS name** when the client runs in another namespace. For local `compose.yml`, use `http://localhost:8321` only if port-forward or compose maps 8321.

Align `MODEL` / `LLAMA_STACK_MODEL` with the enabled `global.models` entry or remote `id`.

### 5. Optional Llama Stack extras

Add only if the design requires them:

| Feature | values path | Notes |
|---------|-------------|--------|
| Web search (Tavily) | `llama-stack.secrets.TAVILY_SEARCH_API_KEY` | See RAG quickstart |
| PDF ingestion | `llama-stack.fileProcessors` | RAG pattern |
| MCP tools | `mcp-servers` subchart + `global.mcp-servers` | RAG pattern |
| Ingestion pipelines | `ingestion-pipeline`, `configure-pipeline` | RAG pattern |

### 6. Verify

```bash
helm template <release> chart -f chart/values.yaml | grep -E 'llamastack|llm-service|pgvector'
helm lint chart
```

After install on OpenShift, run **`make verify-deploy NAMESPACE=<ns>`** (defined in the quickstart Makefile during `rh-qs-deploy`). Do not use raw `oc`/`kubectl` in agent workflows.

Human or CI verification example (inside `verify-deploy` target):

```bash
# Example checks to embed in Makefile verify-deploy — not for agents to run ad hoc
curl -sf "http://llamastack.${NAMESPACE}.svc:8321/v1/health"
```

Confirm API pods reach `http://llamastack:8321` and that the enabled model appears in Llama Stack logs or `/v1/models` when applicable.

## CLI flags (agent interpretation)

| User says | Action |
|-----------|--------|
| `--remote` | Path A: `global.models.remote-llm` enabled; `llm-service.enabled: false` |
| `--model <key>` | Path B: enable matching entry under `global.models`; `llm-service.enabled: true` |
| `--api-key <token>` | Set `llm-service.secret.hf_token` (never commit); document in `.env.example` |

## Checklist

- [ ] `Chart.yaml` lists `llama-stack` (and `llm-service` / `pgvector` if needed) with `condition`
- [ ] `helm dependency update` run; `charts/*.tgz` updated if repo vendors deps
- [ ] `llama-stack.enabled: true`; pgvector strategy explicit (bundled vs standalone)
- [ ] Model path chosen: remote **or** cluster-deployed, not both enabled by mistake
- [ ] Application env vars point at `llamastack:8321` with correct model id
- [ ] No secrets in committed `values.yaml`
- [ ] `helm template` / `helm lint` clean; health check passes after deploy

## Governance

- Pin chart versions; bump only with a quick note in PR/issue
- Secrets via OpenShift Secret, CI vars, or local `-f` overlay — not git
- Match podman/OpenShift conventions from the parent quickstart (`Makefile` deploy targets)
