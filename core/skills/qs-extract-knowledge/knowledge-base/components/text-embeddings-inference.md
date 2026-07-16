---
name: text-embeddings-inference
description: HuggingFace TEI embedding server with pre-downloaded model, custom Helm subchart, and OpenAI-compatible API
summary: "HuggingFace TEI provides a CPU-based embedding server with OpenAI-compatible API for RAG pipelines, running nomic-ai/nomic-embed-text-v1.5 pre-downloaded into the container image (base ghcr.io/huggingface/text-embeddings-inference:cpu-1.8) to eliminate startup download delays. Deploy as a custom local Helm subchart (not ai-architecture-charts) with fullnameOverride for stable DNS referenced in global-values.yaml (global.servicesNames.embedding); model is baked in via Dockerfile that temporarily installs Python/huggingface_hub to download to HF_HOME=/data then removes Python, replacing an earlier PVC-based approach. Critical config: PORT=8080 (non-root), explicit command [\"text-embeddings-router\"], MAX_CLIENT_BATCH_SIZE=32, MAX_BATCH_TOKENS=8192, memory 4Gi request / 8Gi limit, liveness initialDelaySeconds=300 with failureThreshold=5 and readiness initialDelaySeconds=180 with failureThreshold=6. Pods OOMKill at 4Gi during model warmup so 8Gi limit is mandatory; CPU model loading takes 3-5 minutes requiring extended probe delays, compose start_period=180s, and Makefile wait-for-embedding 300s timeout; dependent services must poll /health via init container before starting."
metadata:
  type: component
tags:
  tech_stack: [python, huggingface]
  ai_pattern: [embeddings, rag, vector-search]
  platform: [openshift, kubernetes, tei]
  data_layer: []
source_examples:
  - quickstart: "ansible-log-analysis"
    repo: "https://github.com/rh-ai-quickstart/ansible-log-analysis"
    notes: "TEI CPU deployment with nomic-embed-text-v1.5 baked into image, custom Helm subchart"
    approach: "A"
---

# Text Embeddings Inference (TEI)

## Overview

HuggingFace Text Embeddings Inference (TEI) provides a high-performance embedding service with an OpenAI-compatible API. In this quickstart it serves as the dedicated embedding backend for RAG pipelines, running the `nomic-ai/nomic-embed-text-v1.5` model on CPU. The model is pre-downloaded into the container image at build time to eliminate startup download delays.

## Tech Stack & Dependencies

- **Runtime:** HuggingFace TEI `cpu-1.8` (Rust-based inference server)
- **Container image:** `quay.io/rh-ai-quickstart/alm-rag:tei-rag-v1` (custom image with pre-downloaded model)
- **Base image:** `ghcr.io/huggingface/text-embeddings-inference:cpu-1.8`
- **Model:** `nomic-ai/nomic-embed-text-v1.5`
- **Key dependencies:** None at runtime; Python + `huggingface_hub` used only at build time for model download
- **Helm subchart:** Local subchart at `deploy/helm/ansible-log-monitor/charts/text-embeddings-inference/` (not from ai-architecture-charts)

## Key Patterns

### Pre-downloaded Model in Container Image

The Dockerfile installs Python temporarily to download the model at build time, then removes Python to reduce image size. The model is stored in `/data` which TEI reads via `HF_HOME`.

```dockerfile
# From services/text-embeddings-inference/Dockerfile
FROM ghcr.io/huggingface/text-embeddings-inference:cpu-1.8

USER root
RUN apt-get update && apt-get install -y python3 python3-pip && \
    pip3 install --no-cache-dir --break-system-packages huggingface_hub && \
    rm -rf /var/lib/apt/lists/*

ENV HF_HOME=/data

RUN python3 -c "from huggingface_hub import snapshot_download; \
    snapshot_download('nomic-ai/nomic-embed-text-v1.5', \
                      cache_dir='/data')"

RUN apt-get remove -y python3 python3-pip && \
    apt-get autoremove -y
USER 1000
```

### Custom Helm Subchart (Not ai-architecture-charts)

TEI is deployed as a local Helm subchart rather than using a shared chart from ai-architecture-charts. The subchart lives at `deploy/helm/ansible-log-monitor/charts/text-embeddings-inference/` and is not listed in the parent `Chart.yaml` dependencies -- Helm picks it up automatically from the `charts/` directory.

### Explicit Command Override

The deployment template uses an explicit `command` field rather than relying on the image entrypoint:

```yaml
# From values.yaml
command: ["text-embeddings-router"]
```

### Service Naming via fullnameOverride

The service name is overridden to a project-specific name so other components can reference it by a stable DNS name:

```yaml
# From values.yaml
fullnameOverride: "alm-embedding"
```

This name is referenced in `global-values.yaml` and by downstream services:

```yaml
# From global-values.yaml
global:
  servicesNames:
    embedding: "alm-embedding"
  rag:
    embedding:
      apiUrl: "http://alm-embedding:8080"
```

### Init Container Wait Pattern

The RAG init job uses a `wait-for-embedding` init container that polls the TEI health endpoint before proceeding with index building:

```yaml
# From charts/rag/templates/rag-init-job.yaml
initContainers:
  - name: wait-for-embedding
    image: curlimages/curl:latest
    command:
      - sh
      - -c
      - |
        echo "Waiting for embedding service to be ready..."
        EMBEDDING_URL="${EMBEDDINGS_LLM_URL}/health"
        until curl -f -s "$EMBEDDING_URL" > /dev/null; do
          echo "Still waiting for embedding service at $EMBEDDING_URL..."
          sleep 5
        done
```

## Configuration

- **Environment variables:**
  - `MODEL_ID=nomic-ai/nomic-embed-text-v1.5` -- model identifier (pre-downloaded in image)
  - `HF_HOME=/data` -- HuggingFace cache directory where model is stored
  - `PORT=8080` -- service port (set to 8080 instead of 80 to avoid root permission requirement)
  - `MAX_CLIENT_BATCH_SIZE=32` -- increased from default 16 for larger batch throughput (per values.yaml comment: "memory allows with 8Gi limit")
  - `MAX_BATCH_TOKENS=8192` -- maximum tokens per batch
- **Config files:** No additional config files; all configuration via environment variables
- **Helm values:** Key overrides in `values.yaml`:
  - `image.repository` / `image.tag` -- custom pre-built image reference
  - `service.port: 8080` -- port changed from 80 per comment: "to avoid root permission requirement"
  - `fullnameOverride: "alm-embedding"` -- stable service DNS name
  - `resources.limits.memory: 8Gi` / `resources.requests.memory: 4Gi`
  - `livenessProbe.initialDelaySeconds: 300` / `readinessProbe.initialDelaySeconds: 180`

## Known Gotchas

- **OOMKilled at 4Gi during model warmup:** The values.yaml comment states memory limit was increased to 8Gi because the pod was OOMKilled at 4Gi during model loading/warmup. The request is set to 4Gi to ensure scheduling, but the limit must be 8Gi. (Source: `values.yaml` line 53 comment: "Increased for model loading/warmup (OOMKilled at 4Gi during warmup)")
- **CPU model loading takes 3-5 minutes:** Liveness probe `initialDelaySeconds` is set to 300 and readiness to 180 because model loading on CPU is slow. The compose.yaml also sets `start_period: 180s`. The Makefile `wait-for-embedding` target has a 300-second timeout. (Source: `values.yaml` line 62 comment, `compose.yaml` line 240)
- **Port 8080 instead of 80:** The service port is 8080 rather than the default 80 to avoid requiring root permissions. (Source: `values.yaml` line 48 comment: "Changed from 80 to avoid root permission requirement")
- **PVC removed in favor of baked-in model:** Earlier iterations used a PVC for the HuggingFace cache, but commit `d1541f3` removed the PVC template and simplified the deployment to rely entirely on the pre-downloaded model in the image. (Source: commit `d1541f3` which deleted `templates/pvc.yaml`)
- **Failure threshold tuning:** Liveness `failureThreshold` is 5 and readiness `failureThreshold` is 6 to tolerate the extended startup time without premature restarts. (Source: `values.yaml` lines 66-67, 76-77)

## Testing Notes

- Health endpoint: `curl http://alm-embedding:8080/health`
- Generate embeddings via OpenAI-compatible API (from chart README):
  ```bash
  curl -X POST http://alm-embedding:8080/embeddings \
    -H "Content-Type: application/json" \
    -d '{"model": "nomic-ai/nomic-embed-text-v1.5",
         "input": ["search_document: document text", "search_query: query text"]}'
  ```
- Makefile target `wait-for-embedding` polls the health endpoint with a 300-second timeout (Source: `deploy/local/Makefile` lines 69-85)
- Makefile target `test-embedding` available for local testing (Source: `deploy/local/Makefile` line 1)

## Related Patterns

- RAG init job depends on TEI readiness (see `charts/rag/templates/rag-init-job.yaml`)
- Backend references TEI via `EMBEDDINGS_LLM_URL` env var (defaults to `http://alm-embedding:8080`)
- Local compose deployment at `deploy/local/compose.yaml` mirrors the Helm configuration
