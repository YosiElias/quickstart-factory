---
name: aap-mock
description: Mock Ansible Automation Platform log generator deployed as a Helm subchart for testing log-analysis pipelines
summary: "Mock AAP log generator (Python, image quay.io/rh-ai-quickstart/alm-aap-mock, upstream RHEcosystemAppEng/aap-log-generator) deployed as an optional Helm subchart gated by aap-mock.enabled within the ansible-log-monitor umbrella chart to provide realistic test data for agentic log-analysis pipelines alongside Alloy, pgvector, and MinIO siblings. Enable for demos and testing when no real AAP instance is available; disable via the condition toggle when connecting to production AAP — the three-PVC persistence layout (data/logs/sampleLogs) falls back to emptyDir when disabled, and the parent chart overrides sampleLogs.enabled=false in favor of an API-polling log collector sidecar. Downstream components must wait via init containers polling /healthz and /api/v2/jobs/ (count > 0) on http://alm-aap-mock:8080 before starting; env vars PORT=8080, PYTHONUNBUFFERED=1, and app.env map (OTLP_ENDPOINT, REPLAY_RATE, LOOP_ENABLED) configure runtime; security context uses runAsNonRoot with all capabilities dropped for OpenShift restricted SCC and dual Route+Ingress exposure. App loads all log files before starting HTTP server (~60-90s for 500 files), requiring liveness initialDelaySeconds=120s and readiness=90s; subchart defaults memory to 2Gi but parent overrides to 4Gi since 500 files need ~3-4GB; service name alm-aap-mock is hardcoded in Alloy init containers and AAP_API_URL so fullnameOverride or release naming must match."
metadata:
  type: component
tags:
  tech_stack: [python, helm]
  ai_pattern: [data-pipeline]
  platform: [openshift, kubernetes]
source_examples:
  - quickstart: "ansible-log-analysis"
    repo: "https://github.com/rh-ai-quickstart/ansible-log-analysis"
    notes: "Mock AAP log generator subchart providing test data for the log-analysis agentic pipeline"
    approach: "A"
---

# AAP Mock (Log Generator)

## Overview

The aap-mock component is a mock Ansible Automation Platform that generates realistic AAP logs for testing and demonstration. It is deployed as an optional local Helm subchart within the `ansible-log-monitor` parent chart, gated by `aap-mock.enabled`. Other components in the stack (Alloy log collector, the agentic backend) depend on its API to source log data for the analysis pipeline.

## Tech Stack & Dependencies

- **Runtime:** Python (containerized)
- **Container image:** `quay.io/rh-ai-quickstart/alm-aap-mock:latest`
- **Key dependencies:** Persistent storage for data, logs, and sample log files
- **Helm subchart:** Local subchart at `deploy/helm/ansible-log-monitor/charts/aap-mock/` (v0.1.0)
- **Upstream source:** https://github.com/RHEcosystemAppEng/aap-log-generator

## Key Patterns

### Conditional Subchart with Global Toggle

The aap-mock chart is included as a local dependency in the parent chart, gated by a condition so it can be disabled when a real AAP instance is available:

```yaml
# Parent Chart.yaml
dependencies:
  # Local sub-charts (aap-mock is optional for testing/demos)
  - name: aap-mock
    version: 0.1.0
    condition: aap-mock.enabled
```

### Three-PVC Persistence Layout

The deployment uses three separate PVCs for data, application logs, and sample log files. Each is independently toggleable and the volumes fall back to `emptyDir` when persistence is disabled:

```yaml
# values.yaml
persistence:
  data:
    enabled: true
    size: 2Gi
  logs:
    enabled: true
    size: 1Gi
  sampleLogs:
    enabled: true
    size: 2Gi
```

In the deployment template, the fallback pattern looks like:

```yaml
# deployment.yaml
volumes:
  - name: data
    {{- if .Values.persistence.data.enabled }}
    persistentVolumeClaim:
      claimName: {{ include "aap-mock.fullname" . }}-data
    {{- else }}
    emptyDir: {}
    {{- end }}
```

### OpenShift-Aware Security Context

The chart sets a restricted security context suitable for OpenShift's restricted SCC, letting OpenShift assign user IDs automatically:

```yaml
# values.yaml
podSecurityContext:
  runAsNonRoot: true
  # OpenShift will assign user IDs automatically

securityContext:
  allowPrivilegeEscalation: false
  runAsNonRoot: true
  capabilities:
    drop:
    - ALL
  seccompProfile:
    type: RuntimeDefault
```

### Downstream Init Container Wait Pattern

Other components wait for aap-mock to be healthy and have data loaded before starting. The Alloy deployment uses an init container that polls both the health endpoint and the jobs API:

```yaml
# Parent values.yaml — Alloy init container
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
      until [ $(curl -f -s http://alm-aap-mock:8080/api/v2/jobs/ | grep -o '"count":[0-9]*' | cut -d':' -f2) -gt 0 ] 2>/dev/null; do
        echo "Waiting for sample logs to load..."
        sleep 5
      done
```

### Dual Exposure: Route + Ingress

The chart supports both OpenShift Routes (enabled by default) and Kubernetes Ingress (disabled by default), with multi-version Ingress API compatibility:

```yaml
# values.yaml
route:
  enabled: true    # OpenShift
ingress:
  enabled: false   # non-OpenShift
```

## Configuration

- **Environment variables:**
  - `PORT` — hardcoded to `8080` in the deployment template
  - `PYTHONUNBUFFERED` — set to `1` for immediate log output
  - Additional env vars injected via `app.env` map (e.g., `OTLP_ENDPOINT`, `REPLAY_RATE`, `LOOP_ENABLED`)
- **Helm values:**
  - `enabled` — global toggle to include/exclude the subchart
  - `persistence.data/logs/sampleLogs` — independent PVC controls
  - `probes.liveness.initialDelaySeconds` — set to 120s to allow file loading
  - `probes.readiness.initialDelaySeconds` — set to 90s for file loading
  - `resources.limits.memory` — parent chart overrides to 4Gi (comment: "500 files with events needs ~3-4GB")

## Known Gotchas

- **Slow startup due to file loading:** The app loads all log files before starting the HTTP server. The values.yaml comment states "App loads all log files BEFORE starting server (~60-90s for 500 files)," which is why `initialDelaySeconds` for liveness is 120s and readiness is 90s.
- **Memory sizing depends on log file count:** The subchart defaults to 2Gi memory limit, but the parent chart overrides to 4Gi with the comment "500 files with events needs ~3-4GB." The values.yaml also notes "Loading 500+ log files requires ~1.5GB memory" for the base case.
- **Sample logs PVC disabled in parent:** While the subchart defaults `sampleLogs.enabled: true`, the parent chart overrides it to `false` (`sampleLogs.enabled: false`), relying instead on a separate log collector sidecar that polls the aap-mock API at `http://alm-aap-mock:8080`.
- **Service name matters for cross-component wiring:** Downstream components reference the service as `alm-aap-mock` (from `fullnameOverride` or release-name convention), as seen in the Alloy init container and log collector env var `AAP_API_URL: "http://alm-aap-mock:8080"`.

## Testing Notes

- Verify the pod is healthy: check `/healthz` endpoint responds on port 8080
- Verify readiness: check `/readyz` endpoint (separate from liveness)
- Verify log data is loaded: `curl http://alm-aap-mock:8080/api/v2/jobs/` should return a count > 0
- Check PVC binding: `kubectl get pvc -l app.kubernetes.io/name=aap-mock`

## Related Patterns

- Parent chart: `ansible-log-monitor` umbrella chart orchestrating aap-mock, Alloy, pgvector, minio, and backend
- Log collection: Alloy sidecar (`alm-aap-log-collector`) polls aap-mock API and writes to shared PVC
