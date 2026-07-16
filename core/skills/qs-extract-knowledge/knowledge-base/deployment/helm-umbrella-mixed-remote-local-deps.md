---
name: helm-umbrella-mixed-remote-local-deps
description: "Umbrella Helm chart mixing remote ai-architecture-charts deps with many local subcharts"
summary: "Structures an umbrella Helm chart combining three dependency types for complex multi-component quickstarts: remote ai-architecture-charts (pgvector, minio, mcp-servers fetched via `helm dependency build` as .tgz archives), 8 local subcharts (FastAPI backend with init-job/RBAC, Gradio UI, annotation-interface with RBAC, clustering, FAISS RAG, TEI, conditional aap-mock, Phoenix), and inlined community charts (Loki, Grafana, Alloy as .tgz files configured via values.yaml passthrough keys). Use when a quickstart needs both standardized infrastructure from ai-architecture-charts and many custom application services; optional components toggle via the `condition` field (e.g., `aap-mock.enabled`, `global.rag.enabled`). Installation layers three values files via Makefile: `global-values.yaml` for cross-chart service discovery (`global.servicesNames`, `global.rag.serviceUrl`), `values.yaml` for per-chart config, and a dynamically generated model values file for LLM credentials via `prompt_openai_credentials`. Hyphenated chart names like mcp-servers create double-nested values keys (`mcp-servers.mcp-servers.loki-server`); remote chart versions are pinned in Chart.yaml while community charts are version-pinned by their .tgz archive filenames in `charts/`."
metadata:
  type: deployment-pattern
tags:
  tech_stack: [helm, kubernetes]
  ai_pattern: [agents, rag]
  platform: [openshift, rhoai]
  data_layer: [pgvector, minio, faiss, loki]
source_examples:
  - quickstart: "ansible-log-analysis"
    repo: "https://github.com/rh-ai-quickstart/ansible-log-analysis"
    notes: "Umbrella chart with 3 remote ai-architecture-charts (pgvector, minio, mcp-servers) and 8 local subcharts plus 3 inlined community charts (Loki, Grafana, Alloy)"
    approach: "A"
---

# Helm Umbrella Chart with Mixed Remote and Local Dependencies

## Overview

An umbrella Helm chart pattern that combines remote dependencies from the shared `ai-architecture-charts` repository with numerous local subcharts for application-specific services. This pattern is suited for complex quickstarts with many components that need both standardized infrastructure (databases, storage) and custom application charts.

## Pattern Description

The umbrella chart at `deploy/helm/ansible-log-monitor/Chart.yaml` declares a mix of dependency types: remote charts pulled from the `ai-architecture-charts` Helm repository for standardized infrastructure, local subcharts in the `charts/` directory for application-specific services, and community charts (Loki, Grafana, Alloy) configured entirely via `values.yaml` passthrough. Conditional dependencies use the `condition` field to make components optional.

## Implementation

### Umbrella Chart.yaml with Mixed Dependencies

From `deploy/helm/ansible-log-monitor/Chart.yaml`:

```yaml
dependencies:
  # External dependencies from remote repositories
  - name: pgvector
    version: 0.1.0
    repository: https://rh-ai-quickstart.github.io/ai-architecture-charts
  - name: minio
    version: 0.1.0
    repository: https://rh-ai-quickstart.github.io/ai-architecture-charts
  - name: mcp-servers
    version: 0.5.7
    repository: https://rh-ai-quickstart.github.io/ai-architecture-charts
  
  # Local sub-charts (aap-mock is optional for testing/demos)
  - name: aap-mock
    version: 0.1.0
    condition: aap-mock.enabled
  - name: rag
    version: 0.1.0
    condition: global.rag.enabled
```

### Local Subcharts Directory Structure

The `deploy/helm/ansible-log-monitor/charts/` directory contains 8 local subcharts:

- `backend/` - FastAPI backend (includes init-job, configmap, secret, route, RBAC)
- `ui/` - Gradio UI
- `annotation-interface/` - Gradio annotation interface (includes RBAC for job reading)
- `clustering/` - scikit-learn clustering service
- `rag/` - FAISS + MinIO RAG service
- `text-embeddings-inference/` - TEI with pre-baked model
- `aap-mock/` - Mock AAP log generator (conditional)
- `phoenix/` - Arize Phoenix observability

Remote charts are also stored as `.tgz` archives in `charts/` after `helm dependency build`: `pgvector-0.1.0.tgz`, `minio-0.1.0.tgz`, `mcp-servers-0.5.7.tgz`.

### Community Charts via Values Passthrough

Loki, Grafana, and Alloy are not declared as Chart.yaml dependencies but are configured via top-level keys in `values.yaml` (e.g., `grafana:`, `loki:`, `alloy:`), relying on their Helm charts being present as `.tgz` files or subcharts in the `charts/` directory. Their full configuration is inlined in the umbrella `values.yaml`.

### Global Values for Cross-Chart Configuration

From `deploy/helm/ansible-log-monitor/global-values.yaml`:

```yaml
global:
  servicesNames:
    backend: "alm-backend"
    annotationInterface: "alm-annotation-interface"
    clustering: "alm-clustering"
    ui: "alm-ui"
    embedding: "alm-embedding"
    rag: "alm-rag"
  rag:
    enabled: true
    serviceUrl: "http://alm-rag:8002"
    embedding:
      apiUrl: "http://alm-embedding:8080"
```

### Helm Install with Multiple Values Files

From `deploy/helm/Makefile`:

```makefile
env_args = \
    -f ansible-log-monitor/global-values.yaml \
    -f ansible-log-monitor/values.yaml

install: namespace
    $(call prompt_openai_credentials)
    helm install $(ANSIBLE_LOG_MONITOR_CHART) ./ansible-log-monitor \
        -n $(NAMESPACE) $(env_args) -f $(MODEL_VALUES_FILE)
```

The install command layers three values files: `global-values.yaml` (cross-chart config), `values.yaml` (per-chart config), and a dynamically generated `MODEL_VALUES_FILE` (LLM credentials).

## Configuration

- **Key settings:** `aap-mock.enabled` and `global.rag.enabled` control optional components
- **Defaults:** aap-mock is enabled by default in values.yaml; rag is enabled in global-values.yaml
- **Dependencies:** Requires `helm dependency build` to fetch remote charts from `ai-architecture-charts`

## Gotchas

- The `mcp-servers` chart uses a nested key structure in values.yaml (`mcp-servers.mcp-servers.loki-server`) because the chart name contains a hyphen, as seen in `deploy/helm/ansible-log-monitor/values.yaml`.
- Remote chart versions (pgvector 0.1.0, minio 0.1.0, mcp-servers 0.5.7) are pinned in Chart.yaml; community charts (Loki, Grafana, Alloy) are version-pinned via their `.tgz` archives in the charts directory.

## Related Patterns

- `helm-init-job-chained-readiness-gates.md` - How the backend subchart enforces startup ordering
- `openshift-scc-helm-extraobjects.md` - SCC grants for Grafana and Loki via extraObjects
- `helm-inline-grafana-alerting-webhook.md` - Grafana alerting configured in umbrella values.yaml
