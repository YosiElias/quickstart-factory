---
name: helm-loki-singlebin-high-ingestion
description: "Loki SingleBinary mode tuned for large log entries and high-volume Ansible log ingestion"
summary: "Deploys Grafana Loki in SingleBinary mode (3 replicas, auth_enabled: false, single-tenant) on OpenShift for ingesting large Ansible log entries (415-757 KB observed, max_line_size: 2MB) with high burst rates (ingestion_rate_mb: 100, ingestion_burst_size_mb: 200, max_global_streams_per_user: 100000) and 100MB gRPC send/recv limits. Use when bulk-loading historical multi-line log files requiring high ingestion throughput and large per-entry sizes — storage uses Loki-internal MinIO for TSDB/S3 schema v13 chunk storage with snappy encoding, structured metadata enabled, gateway resolver at OpenShift cluster DNS 172.30.0.10, and Loki Canary Deployment for health monitoring. Critical config: all microservice-mode replica counts (backend, read, write, ingester, querier, queryFrontend) must be explicitly zeroed in values.yaml when using SingleBinary mode; set rbac.sccEnabled: false and manage SCC grants via extraObjects instead. Gotcha: Loki's internal MinIO (minio.enabled: true under loki section) is separate from any application-level MinIO chart — deploying both without distinction causes storage confusion; filter Canary synthetic logs in queries with {pod!~\"loki-canary.*\"}."
metadata:
  type: deployment-pattern
tags:
  tech_stack: [helm, grafana-loki, kubernetes]
  ai_pattern: [data-pipeline]
  platform: [openshift]
  data_layer: [loki]
source_examples:
  - quickstart: "ansible-log-analysis"
    repo: "https://github.com/rh-ai-quickstart/ansible-log-analysis"
    notes: "Loki SingleBinary with 3 replicas, 2MB max_line_size for large Ansible logs, 100MB gRPC limits, anyuid SCC, and Loki-internal MinIO for chunk storage"
    approach: "A"
---

# Loki SingleBinary with High-Ingestion Tuning

## Overview

A Loki deployment pattern using SingleBinary mode with specific tuning for ingesting large log entries (multi-line Ansible task outputs reaching 415-757 KB per entry). This pattern configures Loki's ingestion rate limits, gRPC message sizes, and storage to handle high-volume bulk loading of historical log files.

## Pattern Description

The ansible-log-analysis quickstart configures the Grafana Loki Helm chart in SingleBinary deployment mode with 3 replicas. The configuration is heavily tuned for Ansible log characteristics: multi-line log entries that can be hundreds of kilobytes, high burst ingestion when loading historical files, and many concurrent label streams from different log files and clusters.

## Implementation

### Loki SingleBinary Configuration

From `deploy/helm/ansible-log-monitor/values.yaml` (loki section):

```yaml
loki:
  fullnameOverride: loki
  loki:
    limits_config:
      # Essential for large log entries (current: 415-757 KB, set to 2MB)
      max_line_size: 2MB
      # High ingestion rates for bulk loading historical files
      ingestion_rate_mb: 100
      ingestion_burst_size_mb: 200
      # Support for many log files with complex labels
      max_global_streams_per_user: 100000
      allow_structured_metadata: true
      volume_enabled: true
    server:
      http_listen_port: 3100
      grpc_server_max_recv_msg_size: 104857600  # 100MB
      grpc_server_max_send_msg_size: 104857600  # 100MB
    frontend_worker:
      grpc_client_config:
        max_recv_msg_size: 104857600  # 100MB
        max_send_msg_size: 104857600  # 100MB
    ingester:
      chunk_encoding: snappy
    querier:
      max_concurrent: 4
    auth_enabled: false

  deploymentMode: SingleBinary
  singleBinary:
    replicas: 3
    persistence:
      retentionPolicy:
        whenDeleted: Delete
        whenScaled: Delete
```

### Zeroed Microservice Replicas

From `deploy/helm/ansible-log-monitor/values.yaml`:

```yaml
  # Zero out replica counts of other deployment modes
  backend:
    replicas: 0
  read:
    replicas: 0
  write:
    replicas: 0
  ingester:
    replicas: 0
  querier:
    replicas: 0
  queryFrontend:
    replicas: 0
  # ... all other microservice components set to 0
```

### Loki Storage with Internal MinIO

```yaml
  loki:
    schemaConfig:
      configs:
        - from: "2024-04-01"
          store: tsdb
          object_store: s3
          schema: v13
          index:
            prefix: loki_index_
            period: 24h
    storage:
      bucketNames:
        chunks: loki-chunks
        ruler: loki-ruler
        admin: loki-admin

  minio:
    enabled: true  # Loki's internal MinIO for chunk storage
```

### Gateway DNS Resolver

```yaml
  gateway:
    nginxConfig:
      resolver: "172.30.0.10"
```

The gateway nginx resolver is set to `172.30.0.10`, which is the OpenShift cluster DNS service IP.

### Loki Canary for Health Monitoring

```yaml
  lokiCanary:
    kind: Deployment
```

Loki Canary is deployed as a Deployment (writes synthetic logs for health checks). The values.yaml includes a comment noting these synthetic logs should be filtered with `{pod!~"loki-canary.*"}` in queries.

## Configuration

- **Key settings:** `max_line_size: 2MB` is critical for Ansible logs that can reach 757 KB; `ingestion_rate_mb: 100` and `ingestion_burst_size_mb: 200` handle bulk historical file loading
- **Defaults:** 3 SingleBinary replicas; `auth_enabled: false` (single-tenant); `chunk_encoding: snappy` for compression
- **Dependencies:** Uses its own internal MinIO (separate from the application's MinIO for RAG); requires OpenShift cluster DNS at `172.30.0.10`

## Gotchas

- Loki uses its own internal MinIO instance (`minio.enabled: true` under the loki section) for chunk storage, which is separate from the application-level MinIO chart used for RAG index storage. The comment in `values.yaml` at line 399 confirms this: `minio: enabled: true`.
- The `max_line_size` value of `2MB` was specifically chosen based on observed Ansible log entry sizes of 415-757 KB, as noted in the inline comment: "Essential for large log entries (current: 415-757 KB, set to 2MB for headroom)".
- All microservice-mode replica counts must be explicitly zeroed when using SingleBinary mode, or the Loki Helm chart will deploy both SingleBinary and microservice components.
- The `rbac.sccEnabled: false` disables the Loki chart's built-in SCC handling; SCC grants are instead managed via `extraObjects` in the loki section of values.yaml.

## Related Patterns

- `openshift-scc-helm-extraobjects.md` - SCC grants for Loki service accounts
- `helm-alloy-sidecar-pvc-log-collection.md` - Alloy pushes processed logs to this Loki instance
- `helm-inline-grafana-alerting-webhook.md` - Grafana queries this Loki instance for alert rules
