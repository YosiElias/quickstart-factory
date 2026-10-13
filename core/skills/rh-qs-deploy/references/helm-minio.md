---
name: rh-qs-helm-add-minio
description: Add MinIO S3-compatible object storage to an existing quickstart Helm chart via ai-architecture-charts. Use for document pipelines, artifacts, lakeFS backends, or RAG sample data.
---

# rh-qs-helm-add-minio

## Purpose

Add [MinIO](https://min.io/) object storage to a quickstart using the shared [minio](https://github.com/rh-ai-quickstart/ai-architecture-charts/tree/main/minio) chart from [ai-architecture-charts](https://github.com/rh-ai-quickstart/ai-architecture-charts). The umbrella app chart stays in the quickstart repo; MinIO runs as a subchart (directly or via `configure-pipeline`).

## When to use

- The quickstart already has (or is getting) a Helm chart under `chart/`
- The design needs S3-compatible storage (documents, pipeline artifacts, model binaries, sample datasets)
- OpenShift Data Science Pipelines or ingestion notebooks need an object store backend

Do **not** use for greenfield app scaffolding (see `rh-qs-scaffold` / `rh-qs-implement`). Do **not** commit real passwords or cluster-specific route URLs in `values.yaml`.

## Reference implementations

| Repo | Pattern |
|------|---------|
| [Fraud Detection + lakeFS](https://github.com/rh-ai-quickstart/Fraud-Detection-data-versioning-with-lakeFS) | **Direct** `minio` subchart; parent chart adds bucket-creation hooks and lakeFS wiring |
| [Spending Transaction Monitor](https://github.com/rh-ai-quickstart/spending-transaction-monitor) | **Direct** `minio` subchart; |

Upstream defaults and parameters: [minio/helm/values.yaml](https://github.com/rh-ai-quickstart/ai-architecture-charts/blob/main/minio/helm/values.yaml) and [minio/README.md](https://github.com/rh-ai-quickstart/ai-architecture-charts/blob/main/minio/README.md).

## Choose a deployment path

| Path | Add to `Chart.yaml` | When |
|------|---------------------|------|
| **A — Standalone MinIO** | `minio` | Object storage only, or you own bucket/bootstrap logic in the parent chart (Fraud Detection style) |
| **B — Via configure-pipeline** | `configure-pipeline` | Kubeflow/ODS pipelines + notebook setup; MinIO deployed when `pipelineStorage.deployMinio: true` (RAG style) |

Use **one** path per quickstart unless you have a deliberate reason to run two MinIO instances (avoid by default).

## Workflow

### 1. Add subchart dependency

Pin versions to a known-good quickstart or [ai-architecture-charts releases](https://github.com/rh-ai-quickstart/ai-architecture-charts/releases).

#### Path A — Standalone MinIO

```yaml
dependencies:
  - name: minio
    version: 0.5.4   # pin deliberately; fraud-detection uses 0.5.2
    repository: https://rh-ai-quickstart.github.io/ai-architecture-charts
    condition: minio.enabled
```

#### Path B — configure-pipeline (includes MinIO)

```yaml
dependencies:
  - name: configure-pipeline
    version: 0.5.7
    repository: https://rh-ai-quickstart.github.io/ai-architecture-charts
    condition: configure-pipeline.enabled
```

MinIO is a dependency of `configure-pipeline`, gated by `pipelineStorage.deployMinio` in that chart’s values.

Refresh vendored charts:

```bash
cd chart
helm dependency update
```

### 2. Minimal enablement

#### Path A — Standalone

```yaml
minio:
  enabled: true
  secret:
    user: minio_user          # override per env; do not commit prod secrets
    password: minio_password
    host: minio               # Service DNS name (default fullnameOverride)
    port: "9000"
```

The subchart creates:

- StatefulSet `minio` with PVC (`volumeClaimTemplates`, default 50Gi upstream)
- Service: API port **9000**, console **9090**
- Secret `minio` with keys `user`, `password`, `host`, `port`
- OpenShift Routes `minio-api` and `minio-webui` (edge TLS) — always rendered by the subchart

Optional sizing override (Fraud Detection uses 10Gi):

```yaml
minio:
  volumeClaimTemplates:
    - metadata:
        name: minio-data
      spec:
        accessModes: ["ReadWriteOnce"]
        resources:
          requests:
            storage: 10Gi
```

#### Path B — configure-pipeline

```yaml
configure-pipeline:
  enabled: true
  pipelineStorage:
    deployMinio: true
  minio:
    secret:
      user: minio_rag_user
      password: minio_rag_password
      host: minio
      port: "9000"
```

Do **not** also add a top-level `minio` dependency unless you intend a second store.

### 3. Sample documents (`--sample-upload` or RAG demos)

Enable the subchart’s upload Job (creates bucket if missing, fetches URLs):

```yaml
minio:
  sampleFileUpload:
    enabled: true
    bucket: documents
    urls:
      - https://raw.githubusercontent.com/rh-ai-quickstart/RAG/refs/heads/main/notebooks/zippity-zoo/Zippity_Zoo_Grand_Invention.pdf
```

For RAG, the same block lives under `configure-pipeline`:

```yaml
configure-pipeline:
  minio:
    secret:
      user: minio_rag_user
      password: minio_rag_password
      host: minio
      port: "9000"
    sampleFileUpload:
      enabled: true
      bucket: documents
      urls: []   # list sample PDF URLs
```

### 4. Multiple buckets (parent chart)

The **minio subchart does not** define `minio.buckets` in upstream values. Fraud Detection adds a **parent** Helm hook (`templates/hooks/post-install-buckets.yaml`) that reads:

```yaml
minio:
  buckets:
    create: true
    names:
      - pipeline-artifacts
      - my-storage
```

If the quickstart needs several buckets at install time, copy that hook pattern from Fraud Detection or create buckets via `mc` / boto3 in a one-shot Job. Do not assume `buckets:` keys work without parent templates.

### 5. Wire workloads (S3 env vars)

In-cluster clients should use the API endpoint and Secret keys from the subchart:

| Variable | Typical value |
|----------|----------------|
| Endpoint | `http://minio:9000` |
| Access key | `minio` Secret → `user` |
| Secret key | `minio` Secret → `password` |
| Bucket | App-specific (e.g. `documents`, `pipeline-artifacts`) |

Example for app `secrets` or deployment `env`:

```yaml
secrets:
  AWS_ACCESS_KEY_ID: "minio_user"
  AWS_SECRET_ACCESS_KEY: "changeme"
  AWS_S3_ENDPOINT: "http://minio:9000"
  AWS_DEFAULT_REGION: "us-east-1"
  AWS_S3_BUCKET: "documents"
```

Fraud Detection notebooks use **parent-level** keys under `minio.secret` (`secret_key`, `secret_access_key`, `endpoint`, `defaultBucket`) in templates — those names are **not** consumed by the minio subchart Secret template. Keep parent template field names aligned with your chart’s `values.yaml`.

LakeFS and DSPA components in Fraud Detection point at `http://minio:9000` for block storage; lakeFS exposes its own S3 API on a separate Service — see that repo if both are required.

### 6. OpenShift / resources (optional)

Fraud Detection overrides image, resources, and ServiceAccount for bucket jobs:

```yaml
minio:
  image:
    repository: quay.io/minio/minio
    tag: latest
    pullPolicy: IfNotPresent
  resources:
    requests:
      cpu: 200m
      memory: 1Gi
    limits:
      cpu: "2"
      memory: 2Gi
  serviceAccount:
    create: false
    name: demo-setup   # parent SA used by bucket Job
```

`minio.openshift` in Fraud Detection values is documentation for operators; Routes ship from the subchart regardless.

### 7. Verify

```bash
helm template <release> chart -f chart/values.yaml | grep -E 'minio|minio-api'
helm lint chart
```

After install on OpenShift, run **`make verify-deploy NAMESPACE=<ns>`**. Embed MinIO health checks inside that Makefile target — agents do not run `oc`/`kubectl` directly.

Example checks for `verify-deploy` (human/CI only):

```bash
curl -sf "http://minio.${NAMESPACE}.svc:9000/minio/health/live"
```

Optional console access: document a `make minio-console` port-forward target if needed — do not document raw `oc port-forward` in README without a Makefile wrapper.

Confirm consuming pods use `http://minio:9000` (or fully qualified `minio.<namespace>.svc.cluster.local:9000` cross-namespace).

## CLI flags (agent interpretation)

| User says | Action |
|-----------|--------|
| `--bucket <name>` | Set `sampleFileUpload.bucket` or add to parent `minio.buckets.names` |
| `--sample-upload` | `sampleFileUpload.enabled: true` + `urls` list |
| `--storage <size>` | Override `volumeClaimTemplates[0].spec.resources.requests.storage` |
| `--user` / `--password` | Set `minio.secret.user` / `password` (via overlay, not git) |

## Subchart vs parent values

Only these keys are rendered by the **minio subchart** Secret/StatefulSet:

- `secret.user`, `secret.password`, `secret.host`, `secret.port`
- `sampleFileUpload.*`, `volumeClaimTemplates`, `resources`, `image`, `service.*`

Extra keys in Fraud Detection (`secret_key`, `endpoint`, `buckets`, `openshift`) are for **parent templates** — safe to use only if matching templates exist.

## Checklist

- [ ] Path chosen: standalone `minio` **or** `configure-pipeline`, not both accidentally
- [ ] `Chart.yaml` dependency + `condition` matches `*.enabled` in values
- [ ] `helm dependency update` run
- [ ] `minio.enabled: true` (Path A) or `configure-pipeline.enabled` + `pipelineStorage.deployMinio: true` (Path B)
- [ ] Credentials documented in `.env.example`; production uses Secret overlay
- [ ] App/pipeline env vars use `http://minio:9000` and correct bucket name
- [ ] Bucket creation strategy defined (sample upload Job, parent hook, or manual)
- [ ] `helm template` / `helm lint` clean; `/minio/health/live` succeeds after deploy

## Governance

- Pin chart versions; bump with a short PR note
- Never commit real passwords, HF tokens, or cluster-specific Route hostnames
- Prefer `quay.io/minio/minio` image per quickstart convention
- For lakeFS + versioning, use Fraud Detection as the composite reference — MinIO alone does not provide Git-like data versioning

## Related skills

- [Helm: Llama Stack guide](./helm-llamastack.md) — when RAG also needs Llama Stack and ingestion pipelines
