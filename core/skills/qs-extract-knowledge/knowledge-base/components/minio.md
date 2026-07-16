---
name: minio
description: "MinIO S3-compatible object storage as Helm subchart for RAG indexes, ML models, and document uploads"
summary: "MinIO provides S3-compatible object storage as a Helm subchart (minio 0.1.0 from ai-architecture-charts) deployed as a single-replica StatefulSet with 50Gi PVC, serving three roles: FAISS RAG index storage tracked by a LATEST.json status pointer (BUILDING/READY/FAILED), serialized sklearn clustering model persistence via joblib, and optional sample document uploads via a gated Kubernetes Job (sampleFileUpload.enabled). Use this subchart when quickstarts need persistent S3-compatible storage for ML artifacts on OpenShift; credentials are centralized in a single Kubernetes Secret with four keys (user, password, host, port) referenced by all consumers via secretKeyRef, with defaults overridden per environment (subchart: minio_rag_user, parent chart: minio_alm_user, compose: minioadmin). Dual ports expose API (9000) and WebUI console (9090 in Helm, 9001 in compose) with edge-TLS OpenShift Routes; Python services connect via a duplicated get_minio_client factory using three-tier config priority (function params > env vars > defaults) with secure=False hardcoded for intra-cluster HTTP. Common gotchas: FAISS read_index/write_index require file paths forcing temp-file downloads from MinIO, the upload Job init container depends on OpenShift's internal image registry (image-registry.openshift-image-registry.svc:5000), the two get_minio_client copies (backend and RAG) must be updated in sync, and health checks use /minio/health/live on port 9000."
metadata:
  type: component
tags:
  tech_stack: [minio, python, helm]
  ai_pattern: [rag, embeddings, data-pipeline]
  platform: [openshift, kubernetes]
  data_layer: [minio]
source_examples:
  - quickstart: "ansible-log-analysis"
    repo: "https://github.com/rh-ai-quickstart/ansible-log-analysis"
    notes: "MinIO StatefulSet subchart from ai-architecture-charts storing RAG FAISS indexes, clustering models, and sample documents"
    approach: "A"
---

# MinIO

## Overview

MinIO provides S3-compatible object storage deployed as a Helm subchart from ai-architecture-charts. In the ansible-log-analysis quickstart it serves three roles: storing FAISS RAG indexes with a LATEST.json status pointer, persisting serialized sklearn clustering models, and optionally uploading sample documents via a Kubernetes Job. It runs as a single-replica StatefulSet with a 50Gi PVC on OpenShift.

## Tech Stack & Dependencies

- **Runtime:** MinIO server (quay.io/minio/minio:latest)
- **Container image:** `quay.io/minio/minio:latest` (Helm), `minio/minio:latest` (compose)
- **Key dependencies:** Python `minio` client library, OpenShift Routes for external access
- **Helm subchart:** minio 0.1.0 from `https://rh-ai-quickstart.github.io/ai-architecture-charts`

## Key Patterns

### StatefulSet with PVC

MinIO is deployed as a StatefulSet (not a Deployment) to maintain stable storage identity via volumeClaimTemplates. The chart uses a 50Gi ReadWriteOnce PVC mounted at `/data`.

From `deploy/helm/ansible-log-monitor/charts/minio-0.1.0.tgz` (statefulset.yaml):

```yaml
kind: StatefulSet
spec:
  replicas: 1
  volumeClaimTemplates:
    - metadata:
        name: minio-data
      spec:
        accessModes: ["ReadWriteOnce"]
        resources:
          requests:
            storage: 50Gi
```

### Credential Secret Pattern

Credentials are stored in a Kubernetes Secret with four keys: `user`, `password`, `host`, `port`. All consuming services reference this single secret by name `minio`.

From `deploy/helm/ansible-log-monitor/charts/minio-0.1.0.tgz` (secret.yaml):

```yaml
kind: Secret
apiVersion: v1
metadata:
  name: minio
data:
  user: {{ .Values.secret.user | b64enc | quote }}
  password: {{ .Values.secret.password | b64enc | quote }}
  host: {{ .Values.secret.host | b64enc | quote }}
  port: {{ .Values.secret.port | b64enc | quote }}
```

Consumers (RAG, backend, clustering) inject these via `secretKeyRef`:

```yaml
# From deploy/helm/ansible-log-monitor/charts/rag/values.yaml
- name: MINIO_ENDPOINT
  valueFrom:
    secretKeyRef:
      name: minio
      key: host
- name: MINIO_ACCESS_KEY
  valueFrom:
    secretKeyRef:
      name: minio
      key: user
```

### Dual-Port Service with OpenShift Routes

The Service exposes two ports: API (9000) and WebUI console (9090). Two OpenShift Routes provide TLS-terminated external access to each.

From `deploy/helm/ansible-log-monitor/charts/minio-0.1.0.tgz` (service.yaml):

```yaml
ports:
  - port: 9090
    targetPort: 9090
    name: webui
  - port: 9000
    targetPort: 9000
    name: api
```

From route.yaml, both routes use edge TLS termination:

```yaml
kind: Route
apiVersion: route.openshift.io/v1
metadata:
  name: minio-api
spec:
  port:
    targetPort: api
  tls:
    termination: edge
    insecureEdgeTerminationPolicy: Redirect
```

### LATEST.json Status Pointer for RAG Index

The RAG pipeline uses a LATEST.json file in the `rag-index` bucket as a status pointer that tracks build state: BUILDING, READY, or FAILED. This allows the RAG service to check readiness before loading and to skip rebuilds.

From `services/rag/src/rag/embed_and_index.py` (save_to_minio method):

```python
# Step 1: Set BUILDING status
pointer = {
    "status": "BUILDING",
    "error_message": None,
    "build_id": build_id,
    "build_ts": build_ts,
}
minio_client.put_object(
    bucket_name, "LATEST.json",
    io.BytesIO(pointer_json.encode()),
    length=len(pointer_json),
)
```

From `services/rag/index_loader.py` (check_index_ready):

```python
response = self.minio_client.get_object(
    self.bucket_name, "LATEST.json"
)
pointer = json.loads(response.read().decode())
return pointer.get("status") == "READY"
```

### Python MinIO Client Factory

A shared factory function creates MinIO clients with a three-tier config priority: function parameters, environment variables, then defaults. Two copies exist -- one in the backend package (`src/alm/utils/minio.py`) and a standalone one for the RAG service (`services/rag/src/utils/minio.py`) to avoid cross-dependencies.

From `services/rag/src/utils/minio.py`:

```python
def get_minio_client(...) -> Minio:
    endpoint = minio_endpoint or os.getenv("MINIO_ENDPOINT", "localhost")
    port = minio_port or os.getenv("MINIO_PORT", "9000")
    access_key = minio_access_key or os.getenv("MINIO_ACCESS_KEY", "minioadmin")
    secret_key = minio_secret_key or os.getenv("MINIO_SECRET_KEY", "minioadmin")
    return Minio(
        endpoint=f"{endpoint}:{port}",
        access_key=access_key, secret_key=secret_key,
        secure=False,  # Use HTTP for internal services
    )
```

### Sample Document Upload Job

An optional Kubernetes Job downloads files from configurable URLs and uploads them to a MinIO bucket. It uses an init container to wait for MinIO health before running.

From `deploy/helm/ansible-log-monitor/charts/minio-0.1.0.tgz` (upload-sample-docs.yaml):

```yaml
initContainers:
  - name: wait-for-minio
    image: "image-registry.openshift-image-registry.svc:5000/openshift/tools:latest"
    command:
      - /bin/bash
      - -c
      - |
        url="http://{{ .Values.secret.host }}:{{ .Values.secret.port }}/minio/health/live"
        until curl -ksf "$url"; do sleep 10; done
```

The Job is gated by `sampleFileUpload.enabled: false` (disabled by default in values.yaml).

### Model Storage for Clustering

The clustering service loads serialized sklearn models from MinIO using `get_object` and in-memory deserialization with joblib.

From `services/clustering/model_loader.py`:

```python
def load_from_minio(bucket_name: str, file_name: str) -> BaseEstimator:
    minio_client = Minio(
        endpoint=f"{endpoint}:{port}",
        access_key=access_key, secret_key=secret_key,
        secure=False,
    )
    response = minio_client.get_object(bucket_name, file_name)
    with io.BytesIO() as buffer:
        buffer.write(response.data)
        buffer.seek(0)
        return joblib.load(buffer)
```

## Configuration

- **Environment variables:**
  - `MINIO_ENDPOINT` / `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY` / `MINIO_PORT` -- used by all Python services (from the `minio` Secret)
  - `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD` -- MinIO server admin credentials (set by the Secret in Helm, hardcoded in compose)
  - `RAG_BUCKET_NAME` -- bucket for RAG index (defaults to `rag-index`)
  - `MINIO_SERVER_URL` -- used in compose to set the external API URL
- **Helm values (parent chart override):**
  - `minio.secret.user` / `minio.secret.password` -- credentials (defaults: `minio_rag_user` / `minio_rag_password` in subchart, overridden to `minio_alm_user` / `minio_alm_password` in parent)
  - `minio.secret.host` / `minio.secret.port` -- service address (defaults: `minio` / `9000`)
  - `minio.sampleFileUpload.enabled` -- toggle the document upload Job
  - `minio.sampleFileUpload.bucket` / `minio.sampleFileUpload.urls` -- target bucket and source URLs
- **Config files:** No config files; configuration is entirely via environment variables and Helm values

## Known Gotchas

- **Duplicate MinIO utility code:** The codebase has two separate `get_minio_client` implementations -- `src/alm/utils/minio.py` for the backend and `services/rag/src/utils/minio.py` for the RAG service. The RAG copy has a comment: "No dependencies on backend (alm.*) code." This avoids circular imports but means changes must be applied in both places.
- **Console port mismatch between Helm and compose:** The Helm chart uses port 9090 for the console (`--console-address :9090`), while the compose file uses port 9001 (`--console-address ":9001"`). The Helm Service exposes 9090 as `webui`; compose maps `9001:9001`.
- **secure=False hardcoded:** All Python MinIO client instantiations set `secure=False` with comments like "Use HTTP for internal services" or "Use HTTP for internal OpenShift services". This means all MinIO traffic is unencrypted within the cluster.
- **FAISS requires file paths:** The index_loader downloads FAISS index files from MinIO to temp files because FAISS's `read_index`/`write_index` require file paths, not byte streams. The temp directory is cleaned up in a `finally` block (from `services/rag/index_loader.py`).
- **Upload job uses internal image registry:** The init container for the sample upload Job uses `image-registry.openshift-image-registry.svc:5000/openshift/tools:latest`, which is only available on OpenShift clusters with the internal registry enabled.
- **Default credentials in subchart:** The subchart defaults to `minio_rag_user` / `minio_rag_password`, but the parent chart overrides them to `minio_alm_user` / `minio_alm_password`. The compose file uses `minioadmin` / `minioadmin`. These should be overridden in production.

## Testing Notes

- Health check endpoint: `http://<minio-host>:9000/minio/health/live` (used by the upload Job init container and compose healthcheck)
- Verify the `minio` Secret exists and has all four keys (`user`, `password`, `host`, `port`) before deploying dependent services
- After the RAG init job completes, check `LATEST.json` in the `rag-index` bucket for `"status": "READY"`
- The compose file includes a healthcheck: `curl -f http://localhost:9000/minio/health/live` with 30s interval

## Related Patterns

- RAG service depends on MinIO for index storage (see RAG component)
- Clustering service loads models from MinIO (see clustering component)
- Backend service uses MinIO for model upload via `upload_model_to_minio`
