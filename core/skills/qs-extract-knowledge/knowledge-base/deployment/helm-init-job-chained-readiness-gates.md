---
name: helm-init-job-chained-readiness-gates
description: "Backend init Job with cascading init containers enforcing multi-service startup ordering"
summary: "Enforces strict multi-service startup ordering in Kubernetes/OpenShift by chaining 5 init containers in a Job (postgres via pg_isready, Phoenix/Alloy via oc rollout status, Loki via HTTP /ready, plus timed log-accumulation delay) that gates execution of backend_init_pipeline.py for building clustering models and RAG indexes. Use this two-tier gate pattern when the backend requires a completed data-ingestion pipeline before serving — the Job's init containers enforce service ordering, then the backend Deployment's own init container runs oc wait --for=condition=complete job/<name>-init to block until the Job finishes. Init containers using oc rollout status and oc wait require the quay.io/openshift/origin-cli:4.15 image plus a Role with get/watch/list on apps/deployments and batch/jobs bound to the backend ServiceAccount; postgresql.waitForReady: true toggles postgres readiness checking. Alloy creates a transitive dependency on AAP Mock through its own wait-for-aap-mock init container (not visible in the Job template); the init pipeline needs separate initResources (8Gi memory, 4Gi ephemeral-storage) for HuggingFace model downloads; backoffLimit: 3 controls Job retry attempts before failure."
metadata:
  type: deployment-pattern
tags:
  tech_stack: [helm, kubernetes, fastapi]
  ai_pattern: [agents]
  platform: [openshift]
source_examples:
  - quickstart: "ansible-log-analysis"
    repo: "https://github.com/rh-ai-quickstart/ansible-log-analysis"
    notes: "Init Job with 5 init containers (postgres, phoenix, loki, alloy, log-accumulation) gating backend deployment"
    approach: "A"
---

# Helm Init Job with Chained Readiness Gates

## Overview

A pattern where a Kubernetes Job with multiple init containers enforces strict startup ordering across services before running an initialization pipeline. The backend Deployment then waits for this init Job to complete before starting. This is used when the application requires data to be ingested and processed before the main service can serve requests.

## Pattern Description

The ansible-log-analysis quickstart has a complex startup dependency chain: PostgreSQL must be ready, then Phoenix (tracing), then Loki (log storage), then Alloy (which implies AAP Mock is ready and has loaded logs), then a delay for log accumulation. Only after all these are satisfied does the init Job run `backend_init_pipeline.py` (which builds clustering models and RAG indexes). The backend Deployment has its own init container that waits for this init Job to complete before starting the FastAPI server.

## Implementation

### Init Job Template

From `deploy/helm/ansible-log-monitor/charts/backend/templates/init-job.yaml`:

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: {{ include "backend.fullname" . }}-init
spec:
  template:
    spec:
      restartPolicy: Never
      initContainers:
        - name: wait-for-postgres
          image: postgres:15-alpine
          command:
            - sh
            - -c
            - |
              until pg_isready -d "$DATABASE_URL"; do
                echo "Waiting for PostgreSQL to be ready..."
                sleep 5
              done
        - name: wait-for-phoenix
          image: quay.io/openshift/origin-cli:4.15
          command:
            - sh
            - -c
            - |
              until oc rollout status deployment/{{ .Release.Name }}-phoenix \
                -n {{ .Release.Namespace }} --timeout=10s; do
                sleep 3
              done
        - name: wait-for-loki
          image: registry.access.redhat.com/ubi9/ubi-minimal:latest
          command:
            - sh
            - -c
            - |
              until curl -f -s http://loki:3100/ready > /dev/null 2>&1; do
                sleep 5
              done
        - name: wait-for-alloy
          image: quay.io/openshift/origin-cli:4.15
          command:
            - sh
            - -c
            - |
              until oc rollout status deployment/alloy --timeout=10s; do
                sleep 5
              done
        - name: wait-for-log-accumulation
          image: registry.access.redhat.com/ubi9/ubi-minimal:latest
          command:
            - sh
            - -c
            - |
              echo "Waiting 10 seconds for logs to accumulate..."
              sleep 10
      containers:
        - name: init-pipeline
          image: "{{ .Values.image.repository }}:{{ .Values.image.tag }}"
          command:
            - sh
            - -c
            - |
              python backend_init_pipeline.py
  backoffLimit: 3
```

### Backend Deployment Waiting on Init Job

From `deploy/helm/ansible-log-monitor/charts/backend/templates/deployment.yaml`:

```yaml
initContainers:
  - name: wait-for-postgres
    image: postgres:15-alpine
    command:
      - sh
      - -c
      - |
        until pg_isready -d "$DATABASE_URL"; do
          echo "Waiting for PostgreSQL to be ready..."
          sleep 2
        done
  - name: wait-for-init-job
    image: quay.io/openshift/origin-cli:4.15
    command:
      - sh
      - -c
      - |
        echo "Waiting for init job to complete..."
        until oc wait --for=condition=complete \
          job/{{ include "backend.fullname" . }}-init \
          -n {{ .Release.Namespace }} --timeout=10s; do
          echo "Still waiting..."
          sleep 3
        done
```

### RBAC for Init Container oc Commands

From `deploy/helm/ansible-log-monitor/charts/backend/templates/role.yaml`:

```yaml
rules:
  - apiGroups: ["apps"]
    resources: ["deployments"]
    verbs: ["get", "watch", "list"]
  - apiGroups: ["batch"]
    resources: ["jobs"]
    verbs: ["get", "watch", "list"]
```

The backend ServiceAccount is granted read-only access to deployments and jobs so that init containers using `oc rollout status` and `oc wait` can check readiness without elevated permissions.

## Configuration

- **Key settings:** `postgresql.waitForReady: true` in backend values.yaml controls whether the postgres init container is included
- **Defaults:** `backoffLimit: 3` on the init Job allows up to 3 retries before marking as failed
- **Dependencies:** The init Job uses `oc` CLI commands, requiring `quay.io/openshift/origin-cli:4.15` image and appropriate RBAC

## Gotchas

- The init Job uses `oc rollout status` to check deployment readiness, which requires RBAC permissions on deployments (get/watch/list). The backend subchart creates a Role and RoleBinding for this, as seen in `templates/role.yaml` and `templates/rolebinding.yaml`.
- The `wait-for-alloy` init container implicitly waits for AAP Mock because Alloy's own init container (`wait-for-aap-mock`) gates on AAP Mock's healthz endpoint, creating a transitive dependency chain.
- Separate init resource limits are defined in `backend/values.yaml` via `initResources` (8Gi memory) because the init pipeline downloads HuggingFace models and requires ephemeral-storage (4Gi).

## Related Patterns

- `helm-umbrella-mixed-remote-local-deps.md` - The umbrella chart that wires these subcharts together
- `helm-alloy-sidecar-pvc-log-collection.md` - Alloy's own init container that creates a dependency on AAP Mock
