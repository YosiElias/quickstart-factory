---
name: container-build-tei-model-prebake
description: "TEI Dockerfile that pre-downloads HuggingFace model during build and cleans up Python"
summary: "Pre-bakes a HuggingFace embedding model (nomic-ai/nomic-embed-text-v1.5) into a TEI container during Docker build to eliminate runtime model download latency, critical for air-gapped or bandwidth-constrained OpenShift deployments. Use when deploying TEI with a known model that must be available immediately at startup without network access — the Dockerfile temporarily installs Python and huggingface_hub into the Debian-based TEI CPU base image (ghcr.io/huggingface/text-embeddings-inference:cpu-1.8), runs snapshot_download to cache all model files (weights, configs, tokenizer) at /data, then removes Python and switches from USER root to USER 1000 for runtime security. Critical config: set HF_HOME=/data for TEI model discovery, MODEL_ID=nomic-ai/nomic-embed-text-v1.5 for model selection, MAX_CLIENT_BATCH_SIZE=32 and MAX_BATCH_TOKENS=8192 for inference batching; pre-built image published to quay.io/rh-ai-quickstart/alm-rag:tei-rag-v1 with Helm chart appVersion 1.8. Gotchas: --break-system-packages flag required for pip install on PEP 668 Debian images, healthcheck needs start_period: 180s because TEI still takes minutes to load the pre-baked model into memory, snapshot_download fetches all files not just weights, and this is the only non-UBI Dockerfile in the quickstart."
metadata:
  type: deployment-pattern
tags:
  tech_stack: [python, huggingface]
  ai_pattern: [embeddings]
  platform: [openshift]
source_examples:
  - quickstart: "ansible-log-analysis"
    repo: "https://github.com/rh-ai-quickstart/ansible-log-analysis"
    notes: "Builds on TEI CPU image, installs Python temporarily to download nomic-embed-text-v1.5 via huggingface_hub, then removes Python to reduce image size"
    approach: "A"
---

# TEI Container Build with Pre-Baked Model

## Overview

A container build pattern for Text Embeddings Inference (TEI) that pre-downloads a HuggingFace model during the Docker build phase. This eliminates model download time at container startup, making deployments faster and more predictable, especially in air-gapped or bandwidth-constrained environments.

## Pattern Description

The official TEI Docker image does not include Python, but the `huggingface_hub` library (which requires Python) is needed to download models. This pattern temporarily installs Python and `huggingface_hub` during the build to download the model, then removes Python to keep the final image lean. The model is stored at `/data` where TEI automatically discovers it via the `HF_HOME` environment variable.

## Implementation

### TEI Dockerfile with Model Pre-Download

From `services/text-embeddings-inference/Dockerfile`:

```dockerfile
# Custom TEI image with pre-downloaded nomic-embed-text-v1.5 model
FROM ghcr.io/huggingface/text-embeddings-inference:cpu-1.8

# Install Python and huggingface_hub to download model
USER root
RUN apt-get update && apt-get install -y python3 python3-pip && \
    pip3 install --no-cache-dir --break-system-packages huggingface_hub && \
    rm -rf /var/lib/apt/lists/*

# Set HuggingFace cache directory (TEI uses this)
ENV HF_HOME=/data

# Pre-download the model during build
RUN python3 -c "from huggingface_hub import snapshot_download; \
    snapshot_download('nomic-ai/nomic-embed-text-v1.5', \
                      cache_dir='/data')"

# Clean up Python (optional - reduces image size)
RUN apt-get remove -y python3 python3-pip && \
    apt-get autoremove -y && \
    rm -rf /var/lib/apt/lists/*

# Switch back to non-root user (TEI runs as UID 1000)
USER 1000
```

### Runtime Configuration in Compose

From `deploy/local/compose.yaml` (alm-embedding service):

```yaml
alm-embedding:
  image: quay.io/rh-ai-quickstart/alm-rag:tei-rag-v1
  environment:
    - MODEL_ID=nomic-ai/nomic-embed-text-v1.5
    - HF_HOME=/data
    - PORT=8080
    - MAX_CLIENT_BATCH_SIZE=32
    - MAX_BATCH_TOKENS=8192
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
    start_period: 180s  # Model loading can take 3+ minutes
```

### Helm Chart Configuration

From `deploy/helm/ansible-log-monitor/charts/text-embeddings-inference/Chart.yaml`:

```yaml
name: text-embeddings-inference
description: TEI service with pre-downloaded nomic-embed-text-v1.5 model
appVersion: "1.8"
```

## Configuration

- **Key settings:** `HF_HOME=/data` is where TEI looks for cached models; `MODEL_ID=nomic-ai/nomic-embed-text-v1.5` tells TEI which model to load; `MAX_CLIENT_BATCH_SIZE=32` and `MAX_BATCH_TOKENS=8192` control inference batching
- **Defaults:** TEI CPU variant (`cpu-1.8`); runs as UID 1000 at runtime
- **Dependencies:** Requires network access during build to download from HuggingFace Hub; the pre-built image is published to `quay.io/rh-ai-quickstart/alm-rag:tei-rag-v1`

## Gotchas

- The `--break-system-packages` flag is required when installing pip packages in newer Debian-based images (like TEI's base) that enforce PEP 668 externally managed Python environments.
- The model download uses `snapshot_download` which downloads all model files including configs and tokenizer data, not just model weights. This ensures TEI has everything it needs at `/data`.
- The compose healthcheck uses `start_period: 180s` (3 minutes) because even with a pre-baked model, TEI needs time to load the model into memory and initialize the inference engine.
- This is the only service in the quickstart that uses a `Dockerfile` rather than a `Containerfile`, and its base image is not UBI-based (`ghcr.io/huggingface/text-embeddings-inference:cpu-1.8` is Debian-based).

## Related Patterns

- `container-build-ubi-uv-multistage.md` - The UBI-based build pattern used by all other services
