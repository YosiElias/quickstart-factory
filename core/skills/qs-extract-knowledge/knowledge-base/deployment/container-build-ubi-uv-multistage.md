---
name: container-build-ubi-uv-multistage
description: "UBI8 base images with uv package manager and multi-stage builds for OpenShift compatibility"
summary: "Provides container build patterns for Python services on OpenShift using UBI8 python-312 base images with the uv package manager (binaries copied from ghcr.io/astral-sh/uv:0.9.7), covering multi-stage, single-stage, and pip-based approaches with OpenShift random UID compatibility. Use multi-stage builds (builder+runtime) for backends needing optimal image size and layer caching via two-step uv sync (--no-install-project then --no-editable --frozen --no-dev); single-stage for simple services with minimal dependencies; pip with requirements.txt when uv is not adopted for a service. Critical settings: UV_HTTP_TIMEOUT=600 extends timeout for large ML packages like PyTorch, TORCH_CUDA_ARCH_LIST=\"\" skips CUDA compilation, runtime stage sets VIRTUAL_ENV=/app/.venv with PATH override and HF_HOME=/hf_cache for model downloads, and build context varies per service (root for backends, context: ../.. for compose-driven RAG, self-contained for UI). All images must set group 0 permissions (chgrp -R 0, chmod -R g=u) for OpenShift random UID, writable cache directories (/hf_cache, .deepeval) require explicit mkdir with chmod 777, Containerfile naming (Podman convention) requires the file parameter in docker/build-push-action for GitHub Actions CI, and the two-step dependency install enables Docker layer caching of dependencies separate from source code."
metadata:
  type: deployment-pattern
tags:
  tech_stack: [python, uv, podman]
  platform: [openshift]
source_examples:
  - quickstart: "ansible-log-analysis"
    repo: "https://github.com/rh-ai-quickstart/ansible-log-analysis"
    notes: "7 Containerfiles using UBI8 python-312 with uv 0.9.7; backend uses multi-stage build with frozen lockfile; all use group 0 permissions for OpenShift random UID"
    approach: "A"
---

# Container Build with UBI8 and uv Package Manager

## Overview

A container build pattern using Red Hat Universal Base Images (UBI8) with the `uv` package manager for Python dependency management. Services use `Containerfile` (not `Dockerfile`) and install uv by copying binaries from the official uv image. The backend uses a multi-stage build for smaller runtime images, while simpler services use single-stage builds.

## Pattern Description

The ansible-log-analysis quickstart has 7 Containerfiles all based on `registry.access.redhat.com/ubi8/python-312`. The `uv` package manager is installed by copying binaries from `ghcr.io/astral-sh/uv:0.9.7` rather than pip-installing it. The backend service uses a multi-stage build pattern (builder + runtime) to separate dependency installation from the final image. All images set group 0 permissions (`chgrp -R 0` or `chmod -R g=u`) for OpenShift compatibility where containers run with random UIDs in the root group.

## Implementation

### Multi-Stage Backend Containerfile

From `Containerfile` (project root):

```dockerfile
# Builder Stage
FROM registry.access.redhat.com/ubi8/python-312 AS builder
USER root
COPY --from=ghcr.io/astral-sh/uv:0.9.7 /uv /uvx /bin/

WORKDIR /app
COPY pyproject.toml uv.lock ./

# Install dependencies only (not the project)
RUN UV_HTTP_TIMEOUT=600 \
    TORCH_CUDA_ARCH_LIST="" \
    uv sync --frozen --no-install-project --no-dev

COPY README.md ./
COPY src/ ./src/
RUN UV_HTTP_TIMEOUT=600 \
    TORCH_CUDA_ARCH_LIST="" \
    uv sync --frozen --no-dev --no-editable

# Runtime Stage
FROM registry.access.redhat.com/ubi8/python-312
USER root
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src

ENV VIRTUAL_ENV=/app/.venv \
    PATH="/app/.venv/bin:$PATH" \
    HF_HOME=/hf_cache

# OpenShift random UID compatibility (group 0)
RUN mkdir -p /app/data/logs/failed /hf_cache && \
    chgrp -R 0 /app /hf_cache && \
    chmod -R g=u /app /hf_cache

EXPOSE 8000
ENTRYPOINT ["uvicorn", "alm.main_fastapi:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Single-Stage Service Containerfile

From `services/ui/Containerfile`:

```dockerfile
FROM registry.access.redhat.com/ubi8/python-312
USER root
COPY --from=ghcr.io/astral-sh/uv:0.9.7 /uv /uvx /bin/

WORKDIR /app
COPY pyproject.toml ./
RUN uv sync --no-dev

ENV VIRTUAL_ENV=/app/.venv
ENV PATH="/app/.venv/bin:$PATH"

COPY app.py .
EXPOSE 7860
ENTRYPOINT ["python","app.py"]
```

### Pip-Based Service (No uv)

From `services/aap-log-collector/Containerfile`:

```dockerfile
FROM registry.access.redhat.com/ubi8/python-312
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app/ ./app/

USER root
RUN chmod -R g=u /app
USER 1001

ENV PYTHONUNBUFFERED=1
CMD ["python", "-m", "app.main"]
```

The aap-log-collector uses `pip` with `requirements.txt` instead of `uv`, showing that not all services in the monorepo follow the same dependency management pattern.

### Build Context Variations

Some services build from the project root while others build from their service directory:

- Backend (`Containerfile` at root): `context: .` - needs access to `src/`, `data/`, `pyproject.toml`
- RAG (`services/rag/Containerfile`): `context: ../..` (from compose) - copies from `services/rag/` paths within root context
- UI (`services/ui/Containerfile`): `context: services/ui` - self-contained

From `services/rag/Containerfile`:

```dockerfile
COPY services/rag/pyproject.toml ./
RUN uv sync --no-dev
COPY services/rag/index_loader.py services/rag/main.py .
```

## Configuration

- **Key settings:** `UV_HTTP_TIMEOUT=600` extends download timeout for large ML dependencies; `TORCH_CUDA_ARCH_LIST=""` prevents CUDA-specific compilation
- **Defaults:** uv version pinned to `0.9.7`; Python 3.12 via UBI8; `--frozen` flag ensures lockfile is not modified during build
- **Dependencies:** All images use `registry.access.redhat.com/ubi8/python-312` base; uv binary copied from `ghcr.io/astral-sh/uv:0.9.7`

## Gotchas

- The backend build uses `--no-install-project` first then `--no-editable` in a second step. This two-step approach allows Docker to cache the dependency layer separately from the source code layer, as noted by the comment "Copy dependency files first (optimal layer caching)".
- The annotation-interface Containerfile creates a `.deepeval` directory with mode 777 and sets `HOME=/app` to fix a `PermissionError` when deepeval tries to create its cache directory: `RUN mkdir -p /app/.deepeval && chmod -R 777 /app/.deepeval`.
- The clustering service creates `/hf_cache` with mode 777 for HuggingFace model downloads: `RUN mkdir -p /hf_cache && chmod -R 777 /hf_cache`.
- All Containerfiles use `Containerfile` naming (Podman convention) rather than `Dockerfile`, but the GitHub Actions CI uses `docker/build-push-action` which references them via the `file` parameter.

## Related Patterns

- `container-build-tei-model-prebake.md` - The TEI service uses a different base image and build strategy
- `github-actions-path-filtered-matrix-quay.md` - CI/CD that builds and pushes these container images
