---
name: promtail
description: "Promtail log collector with multiline Ansible log parsing, regex pipeline stages, and Loki shipping"
summary: "Promtail serves as the log ingestion layer in the ansible-log-analysis quickstart, running as a privileged Docker Compose service (no Helm) that reads from a shared ansible_logs volume written by aap-log-collector and ships structured entries to Loki at http://loki:3100/loki/api/v1/push. Use when collecting multiline Ansible output needing structured label extraction before Loki indexing — the pipeline applies a multiline firstline regex (PLAY/TASK/RUNNING HANDLER/PLAY RECAP, max_lines: 2000), then a regex chain extracting cluster_name from path /var/log/ansible_logs/<cluster_name>/<job_name>.txt, classifying log_type via match selectors (task > recap > play > other), and extracting status with priority overrides (included < ok/changed/skipping < failed/fatal < ignoring), with labelallow restricting output to filename, cluster_name, and status for cardinality control. Config is file-based at deploy/local/config/promtail/promtail-local-config.yaml; server listens on HTTP 9080 (gRPC disabled), positions tracked at /tmp/positions.yaml; Docker socket scrape job exists but is commented out as work-in-progress. SELinux :z volume mounts cause \"operation not supported\" on macOS (remove :z), requires root/privileged mode for Docker socket access, and Grafana alert rules plus contact point templates directly reference promtail labels (job=\"ansible_logs\", status=\"failed\", log_type) — pipeline label changes break downstream alerting and webhook forwarding."
metadata:
  type: component
tags:
  tech_stack: [promtail, loki, grafana]
  ai_pattern: [data-pipeline]
  platform: []
  data_layer: []
source_examples:
  - quickstart: "ansible-log-analysis"
    repo: "https://github.com/rh-ai-quickstart/ansible-log-analysis"
    notes: "Promtail with complex multiline aggregation and regex pipeline for Ansible log parsing"
    approach: "A"
---

# Promtail

## Overview

Promtail is a log collection agent that ships logs to Loki. In this quickstart it acts as the ingestion layer for Ansible automation logs, parsing multiline output into structured labels (log type, status, cluster name) before pushing to Loki. It runs as a privileged Docker Compose service reading from a shared volume written by a separate log collector.

## Tech Stack & Dependencies

- **Runtime:** `grafana/promtail:latest` container image
- **Container image:** `grafana/promtail:latest`
- **Key dependencies:** Loki (push target at `http://loki:3100/loki/api/v1/push`), shared `ansible_logs` Docker volume populated by `aap-log-collector`
- **Helm subchart:** None (docker-compose only in local deployment)

## Key Patterns

### Multiline Ansible Log Aggregation

Ansible output spans multiple lines per task/play. The pipeline uses a `multiline` stage with a `firstline` regex that matches Ansible structural markers (PLAY, TASK, RUNNING HANDLER, PLAY RECAP) to group related lines into single log entries.

```yaml
# From deploy/local/config/promtail/promtail-local-config.yaml
pipeline_stages:
  - multiline:
      firstline: '^(PLAY\s+\[|TASK\s+\[|RUNNING HANDLER\s+\[|PLAY\s+RECAP\s+\*+|NO MORE HOSTS LEFT\s+\*+|Vault password)'
      max_lines: 2000
```

### Regex Pipeline for Structured Label Extraction

The pipeline uses a multi-stage regex chain to extract `cluster_name` from file paths, classify log entries by type (task, recap, play, other), and extract task status with priority-based overrides (included < ok/changed/skipping < failed/fatal < ignoring).

```yaml
# From deploy/local/config/promtail/promtail-local-config.yaml
# Status extraction with override logic (later regexes win)
- regex:
    expression: '(?P<status>included):\s+\S+\s+for\s+(?P<host>\S+)'
- regex:
    expression: '(?P<status>ok|changed|skipping):\s+\[(?P<host>[^\]]+)\]'
- regex:
    expression: '(?P<status>failed|fatal):\s+\[(?P<host>[^\]]+)\]'
- regex:
    expression: '\.\.\.(?P<status>ignoring)\s*$'
```

### Log Type Classification via Match Selectors

After extracting marker labels via regex, `match` stages with Loki selectors assign a `log_type` label. The order ensures only the first match wins (task > recap > play > other fallback).

```yaml
# From deploy/local/config/promtail/promtail-local-config.yaml
- match:
    selector: '{task_name_marker!=""}'
    stages:
      - static_labels:
          log_type: 'task'
- match:
    selector: '{recap_marker!="",log_type=""}'
    stages:
      - static_labels:
          log_type: 'recap'
```

### Label Allowlist for Cardinality Control

The pipeline ends with a `labelallow` stage that restricts which labels are sent to Loki, keeping only `filename`, `cluster_name`, and `status`. Temporary marker labels used for classification are dropped.

```yaml
# From deploy/local/config/promtail/promtail-local-config.yaml
- labelallow:
    - filename
    - cluster_name
    - status
```

### Shared Volume for Log Ingestion

Promtail reads from a named Docker volume (`ansible_logs`) mounted read-only. The `aap-log-collector` service writes logs to this volume with the path convention `/var/log/ansible_logs/<cluster_name>/<job_name>.txt`, which the `regex` stage parses for the `cluster_name` label.

```yaml
# From deploy/local/compose.yaml (promtail service)
volumes:
  - ./config/promtail/promtail-local-config.yaml:/etc/promtail/config.yaml:z
  - ansible_logs:/var/log/ansible_logs:ro,z
```

## Configuration

- **Environment variables:** None directly on promtail; config is file-based
- **Config files:**
  - `deploy/local/config/promtail/promtail-local-config.yaml` -- full scrape config with pipeline stages
- **Helm values:** Not applicable (local docker-compose deployment only)
- **Server ports:** HTTP listen on `9080`, gRPC disabled (`grpc_listen_port: 0`)
- **Positions file:** `/tmp/positions.yaml` -- tracks read offsets for log files

## Known Gotchas

- **SELinux volume mounts:** The compose file uses `:z` suffix on volume mounts for SELinux compatibility (RHEL/Fedora/CentOS). A comment in `deploy/local/compose.yaml` (line 82) warns macOS users to remove `:z` if they get "lsetxattr: operation not supported" errors.
- **Privileged mode required:** The compose service runs as `user: "root"` with `privileged: true`. A comment in `deploy/local/compose.yaml` (line 78) notes this is required for Docker socket access on macOS Docker Desktop.
- **Docker socket collection commented out:** The `aap-mock` Docker socket scrape job in the promtail config is entirely commented out with a TODO note: "Uncomment this when we have a way to collect logs from aap-mock container (work in progress)".
- **Downstream label coupling:** Grafana alert rules in `deploy/local/config/grafana/alerting/rules.yaml` directly reference promtail labels (`job="ansible_logs"`, `status="failed"`). The contact point template in `contactpoints.yaml` also forwards `filename`, `status`, and `log_type` labels to the backend alert webhook. Changes to the promtail pipeline label names will break downstream alerting.

## Testing Notes

- Promtail status is checked via the Makefile: `deploy/local/Makefile` (line 259) uses `docker compose ps | grep promtail | grep Up` to report running state.
- Verify logs are reaching Loki by querying `{job="ansible_logs"}` in Grafana or via the Loki API.
- The `loki-stack` Makefile target starts promtail together with loki, loki-mcp-server, and grafana as a group.

## Related Patterns

- Loki: receives logs pushed by promtail
- Grafana alerting: queries Loki using labels defined in the promtail pipeline
- aap-log-collector: writes the log files that promtail ingests
