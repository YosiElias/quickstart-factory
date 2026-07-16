---
name: compose-hybrid-loki-observability-stack
description: "Local dev compose with full Loki+Grafana+Promtail observability stack and native app processes"
summary: "Provides a local development environment using Docker/Podman Compose to run a full Loki+Grafana+Promtail observability stack alongside 11 infrastructure services (PostgreSQL, MinIO, Phoenix, TEI, RAG, AAP Mock, embedding, log collector) on a shared `alm` network while developer-facing services (backend, UI, annotation) run natively via `uv run` for hot-reload. Use when the quickstart includes a Loki-based log ingestion pipeline needing local testing — Promtail replaces the cluster-side Alloy for local log collection via a shared `ansible_logs` Docker volume (mounted `:ro` on Promtail), and Grafana provisions its Loki datasource inline via an entrypoint script with `GF_AUTH_ANONYMOUS_ENABLED=true`. The Makefile orchestrates startup order with health-check-gated `depends_on` (AAP Mock `start_period: 120s` for 500-file loading, embedding `start_period: 180s` for model loading), backend mounts a locally-generated `clustering_model.joblib` artifact, and default credentials are PostgreSQL `user/password/logsdb` and MinIO `minioadmin/minioadmin`. The `:z` SELinux volume suffix causes `lsetxattr: operation not supported` errors on macOS Docker Desktop (remove it); Promtail runs as `user: \"root\"` with `privileged: true` for Docker socket access; embedding and Loki MCP server conflict on port 8080 requiring Loki MCP remapping to 8081."
metadata:
  type: deployment-pattern
tags:
  tech_stack: [docker-compose, grafana-loki, grafana, promtail, python, uv]
  ai_pattern: [agents, data-pipeline]
  platform: [openshift]
  data_layer: [loki, postgresql, minio]
source_examples:
  - quickstart: "ansible-log-analysis"
    repo: "https://github.com/rh-ai-quickstart/ansible-log-analysis"
    notes: "Compose runs 11 services for local dev including Loki, Grafana, Promtail, AAP Mock, MinIO, RAG, embedding; backend/UI/annotation run natively via uv for hot-reload"
    approach: "A"
---

# Compose-Based Local Dev with Full Loki Observability Stack

## Overview

A local development pattern using Docker/Podman Compose to run a full observability stack (Loki, Grafana, Promtail) alongside application infrastructure (PostgreSQL, MinIO, Phoenix, TEI, RAG), while running application services (backend, UI, annotation interface) natively via `uv run` for hot-reload during development.

## Pattern Description

The ansible-log-analysis quickstart uses a compose file at `deploy/local/compose.yaml` with 11 containerized services and a shared Docker network (`alm`). Infrastructure services run in containers with health checks and dependency ordering, while the three developer-facing services (backend, UI, annotation) run as native processes started by the Makefile using `uv run`. Log collection uses Promtail locally (instead of Alloy on cluster) with shared Docker volumes for log file transfer between the AAP Mock, log collector, and Promtail.

## Implementation

### Network and Volume Architecture

From `deploy/local/compose.yaml`:

```yaml
networks:
  alm:

volumes:
  postgres_data:
  aap_mock_data:
  aap_mock_logs:
  loki_data:
  minio_data:
  ansible_logs:   # Shared between aap-log-collector and promtail
```

The `ansible_logs` volume is the key integration point: the `aap-log-collector` writes log files to it, and Promtail reads from it (mounted read-only).

### Log Collection Pipeline (Compose vs Cluster)

From `deploy/local/compose.yaml`:

```yaml
  aap-log-collector:
    image: quay.io/rh-ai-quickstart/alm-aap-log-collector:latest
    volumes:
      - ansible_logs:/var/log/ansible_logs:z
    depends_on:
      aap-mock:
        condition: service_healthy

  promtail:
    image: grafana/promtail:latest
    user: "root"
    privileged: true   # Required for Docker socket access on macOS
    volumes:
      - ./config/promtail/promtail-local-config.yaml:/etc/promtail/config.yaml:z
      - ansible_logs:/var/log/ansible_logs:ro,z
    depends_on:
      loki:
        condition: service_started
```

Locally, Promtail replaces Alloy for log ingestion. The `:z` suffix on volume mounts is for SELinux compatibility (RHEL/Fedora), with a comment noting macOS users should remove it.

### Grafana with Inline Datasource Provisioning

From `deploy/local/compose.yaml`:

```yaml
  grafana:
    environment:
      - GF_AUTH_ANONYMOUS_ENABLED=true
      - GF_AUTH_ANONYMOUS_ORG_ROLE=Admin
      - GF_FEATURE_TOGGLES_ENABLE=alertingSimplifiedRouting,...
    entrypoint:
      - sh
      - -euc
      - |
        mkdir -p /etc/grafana/provisioning/datasources
        cat <<EOF > /etc/grafana/provisioning/datasources/ds.yaml
        apiVersion: 1
        datasources:
        - name: Loki
          type: loki
          access: proxy
          url: http://loki:3100
          isDefault: true
        EOF
        /run.sh
    image: grafana/grafana:latest
    ports:
      - "3000:3000"
```

Grafana uses anonymous admin access locally (no login required) and provisions the Loki datasource via an entrypoint script that writes the provisioning YAML before starting Grafana.

### Health Check and Dependency Chain

From `deploy/local/compose.yaml`:

```yaml
  aap-mock:
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/healthz"]
      start_period: 120s  # Give time to load 500 files
    deploy:
      resources:
        limits:
          memory: 4G

  alm-embedding:
    healthcheck:
      start_period: 180s  # Model loading can take 3+ minutes

  backend:
    depends_on:
      postgres:
        condition: service_healthy
      alm-embedding:
        condition: service_healthy
      alm-rag:
        condition: service_started
```

### Native Application Services via Makefile

From `deploy/local/Makefile`:

```makefile
backend:
	@cd ../.. && uv run uvicorn alm.main_fastapi:app --reload &

ui:
	@cd ../../services/ui && uv run gradio app.py &

annotation:
	@cd ../../services/annotation_interface && uv run gradio app.py &
```

Application services run as background native processes with hot-reload. The Makefile `start` target orchestrates the startup order: postgres, phoenix, loki-stack, then rag-stack and aap-mock-stack in parallel, then backend, ui, and annotation.

## Configuration

- **Key settings:** AAP Mock's `start_period: 120s` allows time to load 500 log files; embedding service's `start_period: 180s` allows for model loading; Loki uses a local config at `config/loki/local-config.yaml`
- **Defaults:** PostgreSQL uses `user/password/logsdb` credentials; MinIO uses `minioadmin/minioadmin`; Grafana has anonymous admin access enabled
- **Dependencies:** Requires `docker-compose` or `podman-compose`; application services require `uv` for Python dependency management

## Gotchas

- The `:z` SELinux suffix on volume mounts is noted in comments as causing `"lsetxattr: operation not supported"` errors on macOS Docker Desktop. Users on macOS need to remove the `:z` suffix.
- The `promtail` service runs as `user: "root"` with `privileged: true` for Docker socket access on macOS. This would not be acceptable in production but is needed for local development log collection.
- The compose file maps the embedding service to host port 8080, while the Loki MCP server maps to 8081 (with a comment: "Changed host port to 8081 to avoid conflict with alm-embedding"). On cluster, they use different service names so the port conflict doesn't exist.
- The `backend` service in compose mounts `../../clustering_model.joblib` as a volume, which is a locally-generated model artifact from the training pipeline (`make local/train`).

## Related Patterns

- `makefile-delegating-local-cluster-router.md` - The Makefile that orchestrates this compose-based local development
- `helm-alloy-sidecar-pvc-log-collection.md` - The cluster equivalent using Alloy instead of Promtail
