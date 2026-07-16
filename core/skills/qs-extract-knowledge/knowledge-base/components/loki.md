---
name: loki
description: "Grafana Loki log aggregation system for AI-driven log analysis in quickstarts"
summary: "Grafana Loki (3.6.2 local, Helm chart 6.45.2) provides centralized log aggregation for AI-driven Ansible log analysis, deployed in SingleBinary mode (3 replicas) on OpenShift via vendored Helm chart, with Promtail (local) or Alloy (OpenShift) shipping multiline-aggregated logs grouped by PLAY/TASK/RECAP boundaries and priority-chained status labels (included < ok/changed/skipping < failed/fatal < ignoring) with structured metadata extraction (real_timestamp, log_type). Two query paths serve different needs: LokiQueryAgent queries via MCP server (LOKI_MCP_SERVER_URL) using LOGQL_FILE_NAME_QUERY_TEMPLATE for LangGraph agent root-cause analysis, while LokiDataLoader hits /loki/api/v1/query_range directly (LOKI_URL) for bulk ingestion with retry logic; Grafana alert rules on count_over_time({status=\"fatal\"}[5m]) trigger AI inference webhooks. Critical config: max_line_size: 2MB, gRPC limits 100MB on both server and frontend_worker sides, ingestion_rate_mb: 100, allow_structured_metadata: true handle 415-757 KB Ansible entries; local dev uses filesystem storage (4g memory) while OpenShift uses S3 via bundled MinIO with extraObjects Role/RoleBinding granting anyuid SCC. Gotchas: gRPC size limits must match on both server and frontend_worker.grpc_client_config sides or internal Loki communication fails with large entries, Loki Canary synthetic logs require {pod!~\"loki-canary.*\"} filter, gateway nginx resolver: \"172.30.0.10\" must match cluster DNS, and auth_enabled: false means no multi-tenancy enforcement."
metadata:
  type: component
tags:
  tech_stack: [loki, grafana, promtail, alloy, logql]
  ai_pattern: [agents, data-pipeline]
  platform: [openshift, kubernetes]
  data_layer: []
source_examples:
  - quickstart: "ansible-log-analysis"
    repo: "https://github.com/rh-ai-quickstart/ansible-log-analysis"
    notes: "Loki as log store for AI-driven Ansible log analysis with LangGraph agent querying via MCP server"
    approach: "A"
---

# Loki

## Overview

Grafana Loki serves as the centralized log aggregation backend in quickstarts that perform AI-driven log analysis. In the ansible-log-analysis quickstart, Loki receives structured Ansible logs via Promtail (local dev) or Alloy (OpenShift), stores them with labels and structured metadata, and exposes them to both Grafana dashboards and a LangGraph-based Loki agent that queries logs via an MCP server for root cause analysis.

## Tech Stack & Dependencies

- **Runtime:** Grafana Loki 3.6.2 (local dev), Loki Helm chart 6.45.2 / appVersion 3.5.7 (OpenShift)
- **Container image:** `grafana/loki:3.6.2` (local), official Grafana Loki Helm chart (OpenShift)
- **Key dependencies:** Promtail or Alloy (log shipper), Grafana (visualization/alerting), MCP server for agent queries
- **Helm subchart:** Vendored `loki-6.45.2.tgz` from Grafana Helm charts (not from ai-architecture-charts)

## Key Patterns

### SingleBinary Deployment Mode on OpenShift

The Helm values configure Loki in `SingleBinary` mode with 3 replicas, zeroing out all other deployment mode replica counts. This avoids the complexity of microservices mode while providing basic redundancy.

```yaml
# From deploy/helm/ansible-log-monitor/values.yaml
loki:
  deploymentMode: SingleBinary
  singleBinary:
    replicas: 3
    persistence:
      retentionPolicy:
        whenDeleted: Delete
        whenScaled: Delete
  # Zero out all other modes
  backend:
    replicas: 0
  read:
    replicas: 0
  write:
    replicas: 0
```

### Large Log Entry Tuning

Ansible log entries can reach 415-757 KB. The Loki config sets `max_line_size: 2MB` and increases gRPC message limits to 100MB to handle these without truncation. These limits appear in both the local config and the Helm values.

```yaml
# From deploy/local/config/loki/local-config.yaml
server:
  grpc_server_max_recv_msg_size: 104857600  # 100MB
  grpc_server_max_send_msg_size: 104857600  # 100MB
limits_config:
  # Critical for large log entries (current logs: 415-757 KB, set to 2MB for headroom)
  max_line_size: 2MB
  ingestion_rate_mb: 100
  ingestion_burst_size_mb: 200
  max_global_streams_per_user: 100000
  allow_structured_metadata: true
```

### Multiline Log Aggregation Pipeline

Promtail (local) and Alloy (OpenShift) both implement a multiline aggregation pipeline that groups Ansible log entries by PLAY/TASK/RECAP boundaries, then extracts labels (status, cluster_name, log_type) and structured metadata (real_timestamp).

```yaml
# From deploy/local/config/promtail/promtail-local-config.yaml
pipeline_stages:
  - multiline:
      firstline: '^(PLAY\s+\[|TASK\s+\[|RUNNING HANDLER\s+\[|PLAY\s+RECAP\s+\*+|NO MORE HOSTS LEFT\s+\*+|Vault password)'
      max_lines: 2000
  - regex:
      source: filename
      expression: '/var/log/ansible_logs/(?P<cluster_name>[^/]+)/'
  # ... status extraction with priority override logic (ok < changed < failed/fatal < ignoring)
  - structured_metadata:
      log_type:
      real_timestamp:
```

### Status Label Extraction with Priority Override

The pipeline applies multiple regex stages in sequence so that higher-priority statuses override lower-priority ones. The chain is: `included` -> `ok|changed|skipping` -> `failed|fatal` -> `ignoring`. This ensures that if a log line contains both `ok: [host1]` and `fatal: [host2]`, the status label will be `fatal`.

```yaml
# From deploy/local/config/promtail/promtail-local-config.yaml
# 4a: Extract 'included' (lowest priority)
- regex:
    expression: '(?P<status>included):\s+\S+\s+for\s+(?P<host>\S+)'
# 4b: Extract ok/changed/skipping (overrides included)
- regex:
    expression: '(?P<status>ok|changed|skipping):\s+\[(?P<host>[^\]]+)\]'
# 4c: Override if failed/fatal appears
- regex:
    expression: '(?P<status>failed|fatal):\s+\[(?P<host>[^\]]+)\]'
# 4d: Override if "...ignoring" at end of line
- regex:
    expression: '\.\.\.(?P<status>ignoring)\s*$'
```

### LangGraph Agent Querying Loki via MCP Server

The backend uses a LangGraph-based `LokiQueryAgent` that queries Loki through a dedicated MCP server (`alm-loki-mcp-server`). The agent builds LogQL queries using constants like `LOGQL_FILE_NAME_QUERY_TEMPLATE` and connects to Loki indirectly via the `LOKI_MCP_SERVER_URL` environment variable.

```python
# From src/alm/agents/loki_agent/agent.py
class LokiQueryAgent:
    def __init__(self, file_name: str, log_message: str, log_timestamp: str):
        from alm.tools import LOKI_STATIC_TOOLS, create_log_lines_above_tool
        self.tools = [
            *LOKI_STATIC_TOOLS,
            create_log_lines_above_tool(file_name, log_message, log_timestamp),
        ]
```

### Direct Loki API Access for Bulk Ingestion

The `LokiDataLoader` class queries Loki's HTTP API directly (via `LOKI_URL`) for bulk log retrieval, using the `/loki/api/v1/query_range` endpoint with retry logic and stabilization checks.

```python
# From src/alm/ingestion/loki_database.py
class LokiDataLoader(DataLoader):
    def __init__(self, query='{status=~"fatal|failed"}',
                 delta=timedelta(hours=1), limit=2000, max_retries=12*3):
        ...
    async def _load(self):
        endpoint = f"{os.getenv('LOKI_URL')}/loki/api/v1/query_range"
```

### Grafana Alerting Integration

Grafana alert rules query Loki for `{status="fatal"}` and `{status="failed"}` logs and route alerts to the backend's inference endpoint via webhook, triggering AI-driven analysis.

```yaml
# From deploy/helm/ansible-log-monitor/values.yaml
rules:
  - uid: fatal-logs-alert
    title: Fatal Ansible Logs
    data:
      - refId: A
        datasourceUid: loki
        model:
          expr: 'count_over_time({status="fatal"}[5m])'
```

## Configuration

- **Environment variables:**
  - `LOKI_URL` - Direct Loki HTTP API endpoint (e.g., `http://loki:3100`), used by `LokiDataLoader` for bulk ingestion
  - `LOKI_MCP_SERVER_URL` - MCP server SSE endpoint (e.g., `http://mcp-loki-server:8080/stream`), used by `LokiQueryAgent` for agent queries
- **Config files:**
  - `deploy/local/config/loki/local-config.yaml` - Loki server config for local dev (filesystem storage, inmemory ring)
  - `deploy/local/config/promtail/promtail-local-config.yaml` - Promtail pipeline for local dev
- **Helm values:** `loki` section in `deploy/helm/ansible-log-monitor/values.yaml` configures deployment mode, limits, schema, storage (S3 via MinIO), and the nginx gateway resolver (`172.30.0.10` for OpenShift DNS)

## Known Gotchas

- **gRPC message size limits must match on both sides:** The Helm values set both `server.grpc_server_max_recv_msg_size` and `frontend_worker.grpc_client_config.max_recv_msg_size` to 100MB. Missing the client-side setting causes internal Loki component communication failures with large log entries (visible in the `frontend_worker` section of `values.yaml`).
- **anyuid SCC required on OpenShift:** Loki, loki-canary, and its bundled MinIO all need the `anyuid` SecurityContextConstraint. The Helm values create a Role and RoleBinding via `extraObjects` for this.
- **Loki Canary generates synthetic logs:** The Loki Helm chart includes a canary component that writes synthetic log entries. These must be filtered out of real queries using `{pod!~"loki-canary.*"}` (noted in the values.yaml comment).
- **Local dev uses filesystem storage; OpenShift uses S3 (MinIO):** The local config stores chunks on filesystem (`/loki/chunks`), while the Helm deployment uses S3-compatible storage via Loki's bundled MinIO with buckets `loki-chunks`, `loki-ruler`, `loki-admin`.
- **OpenShift DNS resolver for gateway:** The Loki gateway nginx config sets `resolver: "172.30.0.10"` which is the default OpenShift/Kubernetes cluster DNS IP. This must match the cluster's DNS service address.
- **Auth disabled:** Both local and Helm configs set `auth_enabled: false`, meaning multi-tenancy is not enforced.

## Testing Notes

- Local dev health check: `curl http://localhost:3100/ready` (used in the Makefile `health` target)
- Verify log ingestion by checking Grafana at `http://localhost:3000` with query `{status=~"fatal|failed"}`
- The Makefile provides `make loki-stack` to start Loki + MCP server + Grafana + Promtail together, and `make stop-loki-stack` to tear them down
- Memory: local dev sets `4g` limit / `2g` reservation for the Loki container in compose.yaml

## Related Patterns

- Alloy log collection pipeline (OpenShift equivalent of Promtail, configured inline in Helm values)
- Grafana alerting rules that trigger AI inference via webhook to backend
- MCP server pattern for exposing Loki queries to LangGraph agents
