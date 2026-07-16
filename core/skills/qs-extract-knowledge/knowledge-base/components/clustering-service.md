---
name: clustering-service
description: "FastAPI microservice serving a scikit-learn clustering model loaded from MinIO, with health probes and Helm subchart"
summary: "FastAPI/uvicorn microservice that serves a scikit-learn clustering model for embedding-vector classification, loading the joblib-serialized model from MinIO (via io.BytesIO) with automatic local-file fallback when MINIO_BUCKET_NAME is unset — used in ansible-log-analysis to cluster Ansible failure log embeddings via POST /cluster accepting {\"embeddings\": [[float]]} and returning {\"labels\": [int]}. Use this component pattern when you need a standalone model-serving sidecar with MinIO-backed artifact storage and Helm subchart wiring; the init container uses oc wait on the backend-init job (coordinated via global.servicesNames) to ensure MinIO bucket readiness before the clustering container starts, with RBAC Role granting batch/jobs get/list/watch for job polling. Deploys on port 8001 (image quay.io/rh-ai-quickstart/alm-clustering) with MinIO credentials injected from a Kubernetes \"minio\" secret (keys: host, port, user, password), liveness initialDelaySeconds: 30 to allow model load time, readiness initialDelaySeconds: 5, and rbac.create: true for init container job watching. MinIO client hardcodes secure=False (must change for TLS-enabled MinIO), model loads at module-level global so MinIO unreachability at startup crashes the container before health checks begin, an unused load_from_model_registry function shells out to oc whoami with fragile string slicing (host_output[1:-5]), and the init container image quay.io/openshift/origin-cli:latest couples deployment to OpenShift."
metadata:
  type: component
tags:
  tech_stack: [fastapi, python, scikit-learn, uvicorn, minio]
  ai_pattern: [model-serving, embeddings]
  platform: [openshift, kubernetes]
  data_layer: [minio]
source_examples:
  - quickstart: "ansible-log-analysis"
    repo: "https://github.com/rh-ai-quickstart/ansible-log-analysis"
    notes: "Clustering service that loads a joblib model from MinIO and exposes a /cluster prediction endpoint"
    approach: "A"
---

# Clustering Service

## Overview

A lightweight FastAPI microservice that serves a pre-trained scikit-learn clustering model for inference. It accepts embedding vectors via a POST endpoint and returns cluster labels. In the ansible-log-analysis quickstart, it clusters log embeddings to group similar Ansible failure patterns. The service loads the model from MinIO object storage at startup, with a local-file fallback when MinIO is not configured.

## Tech Stack & Dependencies

- **Runtime:** Python >= 3.12
- **Container image:** `quay.io/rh-ai-quickstart/alm-clustering`
- **Key dependencies:** fastapi >= 0.116.1, scikit-learn >= 1.7.1, minio >= 7.2.17, model_registry == 0.2.21, uvicorn >= 0.37.0
- **Helm subchart:** `deploy/helm/ansible-log-monitor/charts/clustering` (application chart, v0.1.0)

## Key Patterns

### Model Loading Strategy with MinIO Fallback

The service checks for a `MINIO_BUCKET_NAME` env var at startup. If set, it loads the serialized model from MinIO; otherwise, it falls back to a local `clustering_model.joblib` file. This is defined in `services/clustering/main.py`:

```python
if os.getenv("MINIO_BUCKET_NAME"):
    model: BaseEstimator = load_from_minio(
        os.getenv("MINIO_BUCKET_NAME"), "clustering_model.joblib"
    )
else:
    model = joblib.load("clustering_model.joblib")
```

The MinIO loader in `services/clustering/model_loader.py` reads the entire model into memory via `io.BytesIO`:

```python
minio_client = Minio(
    endpoint=f"{endpoint}:{port}",
    access_key=access_key,
    secret_key=secret_key,
    secure=False,
)
response = minio_client.get_object(bucket_name, file_name)
with io.BytesIO() as buffer:
    buffer.write(response.data)
    buffer.seek(0)
    return joblib.load(buffer)
```

### Init Container Dependency on Backend Job

The Helm deployment template uses an init container that waits for the backend init job to complete before starting the clustering container. This ensures the MinIO bucket and model artifact are ready. From `charts/clustering/templates/deployment.yaml`:

```yaml
initContainers:
  - name: wait-for-{{ .Values.global.servicesNames.backend }}-init
    image: quay.io/openshift/origin-cli:latest
    command:
      - sh
      - -c
      - |
        oc wait --for=condition=complete --timeout=600s \
          job/{{ .Values.global.servicesNames.backend }}-init \
          -n {{ .Release.Namespace }}
```

### RBAC for Job Watching

The service account gets a Role/RoleBinding granting read access to batch jobs so the init container's `oc wait` command can poll job status. From `charts/clustering/templates/role.yaml`:

```yaml
rules:
  - apiGroups: ["batch"]
    resources: ["jobs"]
    verbs: ["get", "list", "watch"]
```

### Prediction Endpoint

The `/cluster` POST endpoint accepts a 2D array of embedding vectors and returns cluster labels. From `services/clustering/main.py`:

```python
class InputData(BaseModel):
    embeddings: list[list[float]]

@app.post("/cluster")
def predict(data: InputData):
    input_array = np.array(data.embeddings)
    prediction = model.predict(input_array)
    return {"labels": prediction.tolist()}
```

## Configuration

- **Environment variables (from Helm values):**
  - `MINIO_ENDPOINT` — MinIO host (from `minio` secret, key `host`)
  - `MINIO_PORT` — MinIO port (from `minio` secret, key `port`)
  - `MINIO_ACCESS_KEY` — MinIO access key (from `minio` secret, key `user`)
  - `MINIO_SECRET_KEY` — MinIO secret key (from `minio` secret, key `password`)
  - `MINIO_BUCKET_NAME` — Bucket containing the model file (hardcoded to `clustering-model` in values.yaml)
- **Config files:** None beyond the Helm values
- **Helm values (key overrides in `charts/clustering/values.yaml`):**
  - `image.repository`: `quay.io/rh-ai-quickstart/alm-clustering`
  - `service.port` / `service.targetPort`: `8001`
  - `livenessProbe.initialDelaySeconds`: `30` (allows time for model load)
  - `readinessProbe.initialDelaySeconds`: `5`
  - `rbac.create`: `true` (needed for init container job watching)
- **Global values (from `global-values.yaml`):**
  - `global.servicesNames.clustering`: `alm-clustering`
  - `global.servicesNames.backend`: `alm-backend` (referenced by init container)

## Known Gotchas

- **MinIO `secure=False` hardcoded:** The MinIO client in `model_loader.py` sets `secure=False`, meaning it connects over plain HTTP. The source comment says `# Set to True if using HTTPS`. In a production RHOAI deployment with TLS-enabled MinIO, this must be changed.
- **Model loaded at import time:** The model is loaded as a module-level global in `main.py`, not lazily. If MinIO is slow or unreachable at startup, the container will crash before health checks begin. The liveness probe's `initialDelaySeconds: 30` in the Helm values partially mitigates this.
- **Model Registry function uses `oc` subprocess calls:** The `load_from_model_registry` function in `model_loader.py` shells out to `oc whoami` and `oc whoami -t` to fetch credentials, and parses the model registry host with fragile string slicing (`host_output[1:-5]`). This function is present but not wired into `main.py` — the TODO comment at line 10 says `# TODO change it for cluster deployment to be model registry.`
- **Init container requires OpenShift CLI:** The init container image `quay.io/openshift/origin-cli:latest` uses `oc wait`, coupling the deployment to OpenShift clusters.

## Testing Notes

- Verify the `/health` endpoint returns `{"status": "healthy"}` on port 8001
- Confirm the model file `clustering_model.joblib` exists in the MinIO bucket `clustering-model` before deploying
- Test the `/cluster` endpoint with sample embeddings: `curl -X POST http://<svc>:8001/cluster -H 'Content-Type: application/json' -d '{"embeddings": [[0.1, 0.2, 0.3]]}'`
- Check init container logs to verify the backend-init job dependency resolved

## Related Patterns

- MinIO object storage for model artifact storage
- Init container job-dependency pattern (shared with annotation-interface service)
- Helm subchart wiring via global values for service name coordination
