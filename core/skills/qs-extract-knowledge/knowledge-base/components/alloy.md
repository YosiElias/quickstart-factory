---
name: alloy
description: "Grafana Alloy log collection proxy for ingesting Ansible logs from filesystem into Loki"
summary: "Grafana Alloy serves as the log ingestion proxy in the ansible-log-analysis quickstart, deployed as a single-replica Deployment (overriding default DaemonSet via `controller.type: deployment`) to read Ansible logs from a shared `ansible-logs-pvc` (ReadWriteOnce, 5Gi via extraObjects), process them through a 16-stage pipeline with multiline aggregation (`max_lines=2000`), regex-based status override chain (included < ok/changed < failed/fatal < ignoring), `label_keep` filtering, and push structured entries to Loki at `http://loki:3100/loki/api/v1/push`. Use Deployment mode instead of DaemonSet when collecting from known file paths on a PVC rather than node-level pod logs; a sidecar `alm-aap-log-collector` polls the AAP Mock API to produce logs on the shared PVC, with an init container enforcing the startup dependency chain (AAP Mock healthy -> Alloy starts -> Backend init-job runs `oc rollout status deployment/alloy`). Pipeline config uses River/HCL-like syntax embedded inline in values.yaml under `alloy.alloy.configMap.content`, with file discovery glob `/var/log/ansible_logs/*/*.txt` and produces labels (`status`, `job`, `filename`, `cluster_name`) that Grafana alert rules directly query via `stage.label_keep`. Helm chart `alloy-1.4.0.tgz` is vendored in `charts/` but not declared in Chart.yaml so `helm dependency update` ignores it, the Containerfile must be built from project root (`../../`) because it copies `data/logs/` from repo root, and the baked-in logs are a documented workaround — the primary log path is the AAP log collector sidecar writing to the shared PVC at runtime."
metadata:
  type: component
tags:
  tech_stack: [grafana-alloy, loki]
  ai_pattern: [data-pipeline]
  platform: [openshift, kubernetes]
  data_layer: []
source_examples:
  - quickstart: "ansible-log-analysis"
    repo: "https://github.com/rh-ai-quickstart/ansible-log-analysis"
    notes: "Alloy deployed as a Deployment (not DaemonSet) with sidecar log collector and multi-stage processing pipeline for Ansible logs"
    approach: "A"
---

# Alloy

## Overview

Grafana Alloy is a log collection agent used as the ingestion proxy in the ansible-log-analysis quickstart. It reads Ansible log files from a shared PVC, applies a multi-stage processing pipeline (multiline aggregation, regex extraction, label promotion), and forwards structured log entries to Loki. In this architecture it replaces the older Promtail agent and runs as a single-replica Deployment rather than the default DaemonSet, since it collects from static file paths rather than node-level pod logs.

## Tech Stack & Dependencies

- **Runtime:** Grafana Alloy (upstream `docker.io/grafana/alloy:latest`)
- **Container image:** `quay.io/rh-ai-quickstart/alm-alloy:latest` (custom image that bakes in sample log files from `data/logs/`)
- **Key dependencies:** Loki (write endpoint at `http://loki:3100/loki/api/v1/push`), shared PVC `ansible-logs-pvc` for log files, AAP Mock service for init readiness
- **Helm subchart:** `alloy-1.4.0.tgz` — vendored .tgz in `deploy/helm/ansible-log-monitor/charts/` (not listed in Chart.yaml dependencies, manually placed)

## Key Patterns

### Deployment Mode Override

The Alloy Helm chart defaults to DaemonSet, but this quickstart overrides it to a single-replica Deployment since it collects from a known file path on a PVC rather than from every node:

```yaml
# From deploy/helm/ansible-log-monitor/values.yaml (lines 451-453)
alloy:
  controller:
    type: deployment  # Changed from the default DaemonSet to Deployment
    replicas: 1
```

### Init Container for Dependency Ordering

An init container blocks Alloy startup until the AAP Mock service is healthy and has loaded sample logs, preventing Alloy from starting with an empty log directory:

```yaml
# From values.yaml (lines 456-475)
initContainers:
  - name: wait-for-aap-mock
    image: registry.access.redhat.com/ubi9/ubi-minimal:latest
    command:
      - sh
      - -c
      - |
        until curl -f -s http://alm-aap-mock:8080/healthz > /dev/null 2>&1; do
          echo "Waiting for AAP Mock service..."
          sleep 5
        done
        # Wait for logs count > 0
        until [ $(curl -f -s http://alm-aap-mock:8080/api/v2/jobs/ \
          | grep -o '"count":[0-9]*' | cut -d':' -f2) -gt 0 ] 2>/dev/null; do
          sleep 5
        done
```

### Sidecar Log Collector Pattern

A sidecar container (`alm-aap-log-collector`) runs alongside Alloy in the same pod, polling the AAP Mock API and writing job logs to the shared PVC that Alloy reads from:

```yaml
# From values.yaml (lines 485-510)
extraContainers:
  - name: alm-aap-log-collector
    image: quay.io/rh-ai-quickstart/alm-aap-log-collector:latest
    env:
      - name: AAP_API_URL
        value: "http://alm-aap-mock:8080"
      - name: OUTPUT_DIR
        value: "/var/log/ansible_logs"
      - name: POLL_INTERVAL
        value: "300"  # 5 minutes
```

### Multi-Stage Ansible Log Processing Pipeline

The Alloy config (embedded as a ConfigMap in values.yaml) defines a 16-stage pipeline that parses Ansible log format into structured labels and metadata:

```
// From values.yaml alloy.alloy.configMap.content

// File discovery with glob pattern
local.file_match "ansible_logs" {
  path_targets = [{
    __address__ = "localhost",
    __path__    = "/var/log/ansible_logs/*/*.txt",
  }]
}

// Multiline aggregation for Ansible log blocks
stage.multiline {
  firstline     = "^(PLAY\\s+\\[|TASK\\s+\\[|RUNNING HANDLER\\s+\\[|...)"
  max_wait_time = "3s"
  max_lines     = 2000
}
```

Key pipeline stages:
1. **Multiline aggregation** (stage 1): Combines multi-line entries using PLAY/TASK/RECAP markers as line boundaries, with `max_lines = 2000`
2. **Cluster name extraction** (stages 2-3): Regex extracts `cluster_name` from the file path `/var/log/ansible_logs/<cluster_name>/`
3. **Status extraction with priority** (stages 8a-8d): Four sequential regex stages ensure `failed`/`fatal` status overrides `ok`/`changed`, and `ignoring` overrides everything
4. **Log type classification** (stages 10-13): Match selectors set `log_type` to `task`, `recap`, `play`, or `other`
5. **Label cleanup** (stage 16): `stage.label_keep` retains only `filename`, `cluster_name`, and `status`

### Status Override Chain

The pipeline uses sequential regex stages to implement priority-based status extraction, where later stages override earlier ones:

```
// 8a: Extract 'included' (lowest priority)
stage.regex {
  expression = "(?P<status>included):\\s+\\S+\\s+for\\s+(?P<host>\\S+)"
}
// 8b: Standard statuses override 'included'
stage.regex {
  expression = "(?P<status>ok|changed|failed|fatal|skipping):\\s+\\[(?P<host>[^\\]]+)\\]"
}
// 8c: failed/fatal always wins
stage.regex {
  expression = "(?P<status>failed|fatal):\\s+\\[(?P<host>[^\\]]+)\\]"
}
// 8d: '...ignoring' overrides everything
stage.regex {
  expression = "\\.\\.\\.(?P<status>ignoring)\\s*$"
}
```

### Custom Containerfile with Baked-In Logs

The Containerfile uses a multi-stage build to bake sample Ansible log files into the Alloy image:

```dockerfile
# From services/alloy/Containerfile
FROM registry.access.redhat.com/ubi9/ubi-minimal AS builder
WORKDIR /staging
COPY data/logs/ ./logs/

FROM docker.io/grafana/alloy:latest
USER root
RUN mkdir -p /var/log/ansible_logs
COPY --from=builder /staging/logs/ /var/log/ansible_logs/
USER alloy
```

Note the comment: must be built from the project root (`podman build -f services/alloy/Containerfile -t quay.io/rh-ai-quickstart/alm-alloy:latest ../../`).

## Configuration

- **Environment variables:** None directly on the Alloy container; the sidecar `alm-aap-log-collector` uses `AAP_API_URL`, `OUTPUT_DIR`, `POLL_INTERVAL`, `CLUSTER_NAME`, `LOG_LEVEL`
- **Config files:** Alloy pipeline config is embedded inline in `values.yaml` under `alloy.alloy.configMap.content` using Alloy's River/HCL-like syntax
- **Helm values:** Key overrides under the `alloy:` section in `deploy/helm/ansible-log-monitor/values.yaml`:
  - `fullnameOverride: alloy`
  - `controller.type: deployment` (overrides default DaemonSet)
  - `controller.replicas: 1`
  - `controller.volumes.extra` — mounts the `ansible-logs-pvc` PVC
  - `alloy.mounts.extra` — mounts PVC at `/var/log/ansible_logs`
  - `rbac.create: true`
- **PVC:** Created via `extraObjects` in values.yaml — `ansible-logs-pvc` with `ReadWriteOnce` and `5Gi` storage

## Known Gotchas

- **Helm chart is vendored, not declared as a dependency:** The `alloy-1.4.0.tgz` is placed directly in `deploy/helm/ansible-log-monitor/charts/` but is not listed in `Chart.yaml` dependencies. This means `helm dependency update` will not manage it.
- **Build context requirement:** The Containerfile must be built from the project root (two levels up) because it `COPY data/logs/` which lives at the repo root, not under `services/alloy/`. The Containerfile comment documents this: `podman build -f services/alloy/Containerfile -t quay.io/rh-ai-quickstart/alm-alloy:latest ../../`.
- **The baked-in logs in the custom image appear to be a workaround:** A comment in the Helm Makefile (line 203) states: "As a workaround the logs already included in alloy as part of its image, so this loading not called." The primary path now uses the AAP log collector sidecar to write logs to the shared PVC at runtime.
- **Init job also waits for Alloy:** The backend init-job (`deploy/helm/ansible-log-monitor/charts/backend/templates/init-job.yaml`) has a `wait-for-alloy` init container that runs `oc rollout status deployment/alloy` before starting the backend pipeline, creating a dependency chain: AAP Mock -> Alloy -> Backend init.
- **Labels from Alloy affect Grafana alerting:** The Grafana alert rules (in the same values.yaml) query Loki using labels set by Alloy's pipeline (`status`, `job`, `filename`). The alert comment at line 92 explicitly notes: "Available labels from Alloy: job, status, filename".

## Testing Notes

- Verify Alloy pod starts after AAP Mock is healthy (init container dependency)
- Check that the `ansible-logs-pvc` PVC is bound and the sidecar is writing log files to `/var/log/ansible_logs/`
- Query Loki to confirm logs are arriving with expected labels: `{status="failed"}`, `{cluster_name="default-cluster"}`
- Confirm the backend init-job completes (it depends on Alloy being ready via `oc rollout status deployment/alloy`)

## Related Patterns

- Loki — the log storage backend that Alloy pushes to
- Grafana — consumes Alloy-produced labels for alerting rules
- AAP Log Collector sidecar — produces the log files that Alloy reads
