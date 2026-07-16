---
name: aap-log-collector
description: "Polling-based log collector sidecar that fetches AAP job logs via API and writes them to a shared volume"
summary: "Polls the AAP API (`/api/v2/jobs/`) for completed (successful/failed) Ansible job logs and writes them as individual files to a shared PVC volume for Grafana Alloy sidecar ingestion in the ansible-log-analysis quickstart. Use as an `extraContainers` sidecar on the Alloy pod (not a standalone Helm subchart) when you need to bridge AAP job output into a log pipeline; sole runtime dependency is `requests` on Python 3.12 UBI8 (`quay.io/rh-ai-quickstart/alm-aap-log-collector`). All configuration via env-var `Config.from_env()` dataclass -- `AAP_API_URL`, `OUTPUT_DIR`, `CLUSTER_NAME` (partitions logs by subdirectory), `POLL_INTERVAL` (default 300s), `PAGE_SIZE` (validated 1-200) -- with atomic temp-file-then-rename writes and in-memory set deduplication of processed job IDs. In-memory deduplication resets on pod restart causing re-fetch of all completed jobs (safe due to atomic writes); SELinux `:z` volume suffix must be removed on macOS to avoid `lsetxattr` errors; healthcheck uses `pgrep` since the collector has no HTTP server; compose requires `aap-mock` `service_healthy` before collector starts."
metadata:
  type: component
tags:
  tech_stack: [python, requests]
  ai_pattern: [data-pipeline]
  platform: [openshift]
  data_layer: []
source_examples:
  - quickstart: "ansible-log-analysis"
    repo: "https://github.com/rh-ai-quickstart/ansible-log-analysis"
    notes: "Sidecar container polling AAP Mock API, writing job logs to shared PVC for Alloy ingestion"
    approach: "A"
---

# AAP Log Collector

## Overview

A lightweight Python polling service that fetches completed Ansible Automation Platform (AAP) job logs through the AAP API and writes them as individual files to a shared volume. In the ansible-log-analysis quickstart it runs as a sidecar container alongside Grafana Alloy, sharing a PVC so Alloy can ingest the logs for downstream analysis. It tracks processed job IDs in memory to avoid re-fetching.

## Tech Stack & Dependencies

- **Runtime:** Python 3.12 on UBI8 (`registry.access.redhat.com/ubi8/python-312`)
- **Container image:** `quay.io/rh-ai-quickstart/alm-aap-log-collector:latest`
- **Key dependencies:** `requests>=2.31.0` (sole runtime dependency)
- **Helm subchart:** None -- deployed as an `extraContainers` sidecar on the Alloy pod via the parent Helm chart values

## Key Patterns

### Polling Loop with In-Memory Deduplication

The collector runs an infinite loop that polls the AAP API at a configurable interval, filtering for jobs in final states (`successful` or `failed`), and tracks already-processed job IDs in a Python set to avoid duplicate writes.

```python
# From services/aap-log-collector/app/main.py
FINAL_STATES = {"successful", "failed"}
processed_job_ids: Set[int] = set()

# In process_jobs():
jobs_to_process = [
    job
    for job in all_jobs
    if job["id"] not in processed_job_ids and job.get("status") in FINAL_STATES
]
```

### Atomic File Writes

Log files are written atomically using a temp-file-then-rename pattern to prevent partial writes if the process is interrupted mid-write.

```python
# From services/aap-log-collector/app/main.py
temp_path = path.with_suffix(".tmp")
try:
    temp_path.write_text(content, encoding="utf-8")
    temp_path.replace(path)
except Exception as e:
    if temp_path.exists():
        temp_path.unlink()
    raise
```

### Paginated API Fetching

The collector handles AAP API pagination by following the `next` field in responses, fetching all jobs across multiple pages before filtering.

```python
# From services/aap-log-collector/app/main.py
while True:
    response = requests.get(
        f"{api_url}/api/v2/jobs/",
        params={"page": page, "page_size": page_size},
        timeout=30,
    )
    data = response.json()
    results = data.get("results", [])
    all_jobs.extend(results)
    if not data.get("next"):
        break
    page += 1
```

### Sidecar Deployment via extraContainers

In the Helm deployment, the collector is not a standalone chart but an `extraContainers` entry on the Alloy pod, sharing the `ansible-logs` volume so Alloy can tail the files the collector writes.

```yaml
# From deploy/helm/ansible-log-monitor/values.yaml
extraContainers:
  - name: alm-aap-log-collector
    image: quay.io/rh-ai-quickstart/alm-aap-log-collector:latest
    env:
      - name: AAP_API_URL
        value: "http://alm-aap-mock:8080"
      - name: OUTPUT_DIR
        value: "/var/log/ansible_logs"
      - name: POLL_INTERVAL
        value: "300"
    volumeMounts:
      - name: ansible-logs
        mountPath: /var/log/ansible_logs
    resources:
      limits:
        cpu: 200m
        memory: 256Mi
      requests:
        cpu: 50m
        memory: 128Mi
```

### OpenShift-Compatible Container Setup

The Containerfile uses UBI8 base image and sets group-zero permissions before dropping to user 1001, which is the standard pattern for OpenShift's restricted SCC.

```dockerfile
# From services/aap-log-collector/Containerfile
FROM registry.access.redhat.com/ubi8/python-312
USER root
RUN chmod -R g=u /app
USER 1001
ENV PYTHONUNBUFFERED=1
CMD ["python", "-m", "app.main"]
```

## Configuration

- **Environment variables:**
  - `AAP_API_URL` -- Base URL of the AAP API to poll (default: `http://alm-aap-mock:8080`)
  - `OUTPUT_DIR` -- Directory to write log files (default: `/var/log/ansible_logs`)
  - `CLUSTER_NAME` -- Subdirectory name under output dir, used to partition logs by cluster (default: `default-cluster`)
  - `POLL_INTERVAL` -- Seconds between poll cycles (default: `300`, i.e. 5 minutes)
  - `PAGE_SIZE` -- Number of jobs per API page, validated 1-200 (default: `100`)
  - `LOG_LEVEL` -- Python logging level: DEBUG, INFO, WARNING, ERROR, CRITICAL (default: `INFO`)

- **Config files:** None -- all configuration is via environment variables through a dataclass (`Config.from_env()`)

- **Helm values:** No dedicated subchart; configured inline within the parent chart's `extraContainers` section in `deploy/helm/ansible-log-monitor/values.yaml`

## Known Gotchas

- **In-memory deduplication resets on restart:** The `processed_job_ids` set is purely in-memory (no persistent state). If the collector pod restarts, it will re-fetch and re-write all completed jobs. The atomic write pattern means this is safe but generates duplicate I/O. (Visible in `main.py` lines 15-16: `processed_job_ids: Set[int] = set()`)
- **SELinux volume label on RHEL:** The compose file uses the `:z` suffix on the shared volume mount for SELinux relabeling, with a comment noting macOS users should remove it to avoid `lsetxattr: operation not supported` errors. (From `deploy/local/compose.yaml` comment on the volume mount)
- **Healthcheck uses pgrep:** The compose healthcheck verifies the process is running via `pgrep -f 'python -m app.main'`, not an HTTP endpoint, since the collector has no HTTP server. (From `deploy/local/compose.yaml` healthcheck definition)

## Testing Notes

- Run locally via `make run` in `services/aap-log-collector/` which builds the image and mounts a `test-logs/` directory; requires the AAP Mock service to be accessible
- In compose, the collector depends on `aap-mock` with `condition: service_healthy`, so the mock must pass its healthcheck before the collector starts
- Verify operation by checking that `job-{id}.txt` files appear under the `OUTPUT_DIR/CLUSTER_NAME/` path after the first poll cycle

## Related Patterns

- Shared-volume sidecar pattern (collector writes, Alloy reads from same PVC)
- AAP API v2 pagination (`/api/v2/jobs/` with `page` and `page_size` params)
