---
name: rh-qs-minio-conversion
description: |
  Convert an existing AI Quickstart from MinIO (ai-architecture-charts minio
  subchart or hand-rolled templates) to the shared aws-compatible-storage chart
  (S4-backed) from ai-architecture-charts. Removes MinIO wiring, adds the
  aws-compatible-storage Helm dependency, updates app endpoints/credentials, and
  rewrites MinIO mentions in docs. Use when migrating a quickstart off MinIO
  onto S4 / aws-compatible-storage.
---

# rh-qs-minio-conversion

**Category:** `maintenance/`

## Trigger

- User asks to convert MinIO to **S4** / **aws-compatible-storage** / Super Simple Storage Service
- Quickstart uses MinIO via the [ai-architecture-charts minio](https://github.com/rh-ai-quickstart/ai-architecture-charts/tree/main/minio) subchart, `configure-pipeline` with `deployMinio`, **or hand-rolled** MinIO Deployment/PVC/Service/Secret/Route/Job templates
- Target is the shared **[aws-compatible-storage](https://github.com/rh-ai-quickstart/ai-architecture-charts/tree/main/aws-compatible-storage)** chart in [ai-architecture-charts](https://github.com/rh-ai-quickstart/ai-architecture-charts) (S4 runtime image)
- Quickstart still depends on the former chart name `object-storage` and needs renaming to `aws-compatible-storage`

## Goal

Replace self-managed MinIO with **aws-compatible-storage** — the ai-architecture-charts packaging of [S4](https://github.com/rh-aiservices-bu/s4) (Ceph RGW + web UI) — while keeping the S3 API. Swap endpoints, credentials, Helm wiring, local compose, bootstrap/validate scripts, and docs.

Do **not** vendor `charts/s4` from `rh-aiservices-bu/s4` into the quickstart. Depend on **`aws-compatible-storage`** from ai-architecture-charts (same pattern as `minio`, `pgvector`, `llama-stack`).

## Where This Runs

Inside the quickstart repo — typically `.rhoai-qs/<slug>/` after scaffold, or a cloned `rh-ai-quickstart/<slug>` (or sibling) checkout. Resolve the slug before editing (Phase 0).

**Chart source of truth:**

| Item | Location |
|------|----------|
| Shared chart | [`ai-architecture-charts/aws-compatible-storage`](https://github.com/rh-ai-quickstart/ai-architecture-charts/tree/main/aws-compatible-storage) |
| Helm path | `aws-compatible-storage/helm/` |
| Published repo | `https://rh-ai-quickstart.github.io/ai-architecture-charts` (chart name `aws-compatible-storage`) |
| Local sibling | `file://../ai-architecture-charts/aws-compatible-storage/helm` |
| Upstream runtime | `quay.io/rh-aiservices-bu/s4` (pin tag; chart `appVersion`) |
| MinIO (leave available) | [`ai-architecture-charts/minio`](https://github.com/rh-ai-quickstart/ai-architecture-charts/tree/main/minio) — do not delete from the charts repo |

**Proven conversions (patterns to copy; some predate the shared chart, vendored upstream S4, or still say `object-storage` — rewire those to `aws-compatible-storage` when touching them):**

| Quickstart | Chart path | Notes |
|------------|------------|--------|
| Fraud-Detection-data-versioning-with-lakeFS | `deploy/helm/fraud-detection` | lakeFS + DSPA + notebook; short DNS `s4`; regular bucket Job |
| Billing-extraction-with-GroundX | `helm/billing-workloads` | GroundX + notebook; S3 path proxy readiness; buckets `eyelevel`, `billing-artifacts` |
| self-improving-retrieval-for-rag-and-ai-agents | `deploy/helm/zenml-stack` | **Hand-rolled MinIO** → S4; ZenML S3 artifact store; KServe init `mc`→boto3; **S3 API Route** for laptop CLI |

## What it does

1. Inventories every MinIO dependency (Helm subchart **or** custom templates, compose, app, env, bootstrap/validate scripts, CI, **PNG/Mermaid**) — also any leftover `object-storage` chart name
2. Removes MinIO (subchart and/or `templates/minio-*.yaml`, values, hooks)
3. Adds **`aws-compatible-storage`** from ai-architecture-charts (`Chart.yaml` + values + `helm dependency update`)
4. Rewires consumers to the S3 API (`:7480`) and `{fullname}-credentials`
5. Adds a **regular** bucket bootstrap Job in the **parent** chart (UBI Python + boto3 — no `minio/mc`, no Docker Hub)
6. Updates READMEs, env examples, scripts, diagrams (MinIO → aws-compatible-storage / S4)
7. Verifies with `helm lint` / `helm template` / chart unit tests; recommend **`rh-qs-debug-and-deploy`** (deploy + test + debug/fix for conversion gaps — e.g. Loki bundled MinIO edge cases)

## Prerequisites

| Requirement | Notes |
|-------------|--------|
| Existing MinIO usage | Subchart, `configure-pipeline.deployMinio`, **or** hand-rolled MinIO templates |
| S3-compatible clients | boto3 / minio-py / AWS SDK / ZenML S3 flavor — keep API; change endpoint + credentials |
| Cluster PVC support | aws-compatible-storage needs a PVC for RGW data (default `10Gi`) |
| Chart source | [ai-architecture-charts aws-compatible-storage](https://github.com/rh-ai-quickstart/ai-architecture-charts/tree/main/aws-compatible-storage) — **not** a copy of `rh-aiservices-bu/s4/charts/s4` into the quickstart |
| Pullable Job images | OpenShift CLI / UBI only (see [Job images](#3-job-images--do-not-use-docker-hub-or-miniomc)) |

## MinIO → aws-compatible-storage mapping

| Concern | MinIO | aws-compatible-storage (S4) |
|---------|-------|-----------------------------|
| Chart | `minio` subchart **or** custom `templates/minio-*.yaml` | `aws-compatible-storage` from ai-architecture-charts |
| Dependency | `condition: minio.enabled` | `condition: aws-compatible-storage.enabled` |
| Image | `quay.io/minio/minio` | `quay.io/rh-aiservices-bu/s4` (pin tag, e.g. `0.3.2`) |
| S3 API port | **9000** | **7480** |
| Web / console | **9090** | **5000** (UI Route by default) |
| In-cluster endpoint | `http://minio:9000` | `http://<fullname>:7480` — prefer `fullnameOverride: aws-compatible-storage` or short `s4` |
| Credentials Secret | Often `minio` → `user`/`password`, or custom `minio-root` → `MINIO_ROOT_*` | `{fullname}-credentials` → `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` |
| Default access / secret | chart- or values-specific | `s4admin` / `s4secret` |
| UI Route name | e.g. `minio-s3` or `minio-webui` | **`{fullname}`** (targetPort `web-ui`) |
| S3 API Route name | often same as MinIO S3 Route | **`{fullname}-api`** when `route.s3Api.enabled: true` — **not** `{fullname}-s3` |
| Readiness (wait Jobs) | `/minio/health/live` or `/ready` | `http://<fullname>:5000/api` and/or boto3 `list_buckets` on `:7480` |
| Bucket bootstrap | `sampleFileUpload` / `mc` Job (often hook) | Parent **regular Job** + boto3 on UBI Python (not in the subchart) |
| UI auth | MinIO console | `auth.enabled` + `auth.username` / `auth.password` (required when auth on) |

### Naming choice (pick one and stick to it)

| `fullnameOverride` | Service DNS | Credentials Secret | S3 API Route | When |
|-----------------|-------------|--------------------|--------------|------|
| `aws-compatible-storage` | `http://aws-compatible-storage:7480` | `aws-compatible-storage-credentials` | `aws-compatible-storage-api` | Default / new migrations |
| `s4` | `http://s4:7480` | `s4-credentials` | `s4-api` | Match Fraud Detection–style short DNS or existing `s4` docs |

Document the chosen name in README and validate scripts. Do not mix both in one release.

> **Former chart name:** Early migrations may still say `object-storage` in Chart.yaml / values / helpers / packaged `charts/object-storage-*.tgz`. Treat that as the same target — rename the dependency, values key, helpers, and package to **`aws-compatible-storage`**. Keep DSPA CR fields named `objectStorage` (OpenShift AI API); that is unrelated to the Helm chart name.

## Hard-won rules (read before implementing)

From Fraud Detection, Billing, self-improving-retrieval, and the ai-architecture-charts `aws-compatible-storage` chart work:

### 1. Depend on ai-architecture-charts — do not vendor upstream S4

```yaml
# Chart.yaml — correct
dependencies:
  - name: aws-compatible-storage
    version: 0.1.0
    repository: https://rh-ai-quickstart.github.io/ai-architecture-charts
    # local sibling while iterating:
    # repository: "file://../ai-architecture-charts/aws-compatible-storage/helm"
    condition: aws-compatible-storage.enabled
```

```yaml
# Chart.yaml — wrong (do not do this in quickstarts)
# - name: s4
#   repository: "file://charts/s4"   # vendored from rh-aiservices-bu/s4
# - name: object-storage            # former chart name — rename to aws-compatible-storage
```

The shared chart already adapts upstream S4 templates (helpers renamed to `aws-compatible-storage.*`, OpenShift-friendly defaults, unittest suite including a Fraud-like `fullnameOverride: s4` contract). Bumps go through **`rh-qs-bump-versions`** / ai-architecture-charts releases.

### 2. Helm `--wait` vs post-install hooks

Helm runs **`--wait` before post-install hooks**. If a consumer (e.g. DSPA) stays unready until a bucket exists, and that Job is a `post-install` hook, install hangs and hooks never run.

**Fix:** Bucket (and lakeFS repo) creation = **regular Job** in parent release resources, with S4 wait loops. Optional post-install hooks only for work that can run after Ready (e.g. pipeline upload).

### 3. DSPA / external operators need FQDN

Cross-namespace probes fail on bare service names (`lookup … no such host`).

```yaml
dataSciencePipelines:
  objectStorage:   # DSPA CR field name — keep as-is (not the Helm chart name)
    host: aws-compatible-storage.<namespace>.svc.cluster.local   # or s4.<ns>.svc… if fullnameOverride: s4
    port: "7480"
    scheme: http
```

Default in templates: `printf "%s.%s.svc.cluster.local" <fullname> .Release.Namespace`. Same-namespace apps keep `http://<fullname>:7480`.

### 4. Job images — do not use Docker Hub or minio/mc

| Avoid | Why |
|-------|-----|
| `quay.io/minio/mc:…` | Often unauthorized / not pullable |
| `curlimages/curl`, `busybox`, `python:*-slim`, `alpine/*` | Docker Hub rate limits → `ImagePullBackOff` |

```yaml
jobImages:
  cli: image-registry.openshift-image-registry.svc:5000/openshift/cli:latest
  python: registry.redhat.io/ubi9/python-311:latest
  shell: registry.redhat.io/ubi9/ubi-minimal:latest
```

Replace KServe / InferenceService init containers that shell out to `mc` with the same UBI Python + boto3 download pattern (see [KServe / init downloads](#9-kserve--init-containers-using-mc)).

### 5. UBI Python + pip

`registry.redhat.io/ubi9/python-311`: **`pip install --user` fails**. Use `pip install --no-cache-dir -q boto3` and `HOME=/tmp`.

### 6. Credentials wiring

Prefer `secretKeyRef` → `{fullname}-credentials` for `AWS_*`. Do not inline demo keys in Deployments when the Secret exists. ODH data-connection Secrets may mirror keys — keep in sync with `aws-compatible-storage.s3.*`.

Hand-rolled MinIO often used `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD` on a custom Secret (e.g. `minio-root`). Map those to `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` on the aws-compatible-storage credentials Secret everywhere (Helm Jobs, KServe, ZenML registration scripts).

### 7. Docs / diagrams

Inventory **PNG/SVG** as well as Markdown. Prefer Mermaid when regenerating PNGs is awkward. Say **aws-compatible-storage (S4)** on first mention; “S4” alone is fine afterward for the runtime.

### 8. GroundX + S4 path proxy — gate readiness on upstream S4

GroundX layout workers init object storage once in Celery `worker_init`. TCP-only wait on a path proxy can succeed while S4 is still down → `HEAD` **502** → `upload` is `None` → ingest looks `complete` but only `progress.errors` has the failure.

**Fix:** Proxy `/healthz` must probe **upstream S4** (`httpGet`, not `tcpSocket`). Restart layout/extract Deployments after a bad race. UI must treat `progress.errors` as failure even when status is `complete`.

### 9. KServe / init containers using `mc`

Init containers that `mc alias` + `mc cp` must move to UBI Python + boto3 `download_file` against `http://<fullname>:7480` and the credentials Secret. Do not keep `MINIO_CLIENT_IMAGE=quay.io/minio/mc`.

### 10. S3 API Route name is `{fullname}-api` (NOTES may say `-s3`)

With `route.s3Api.enabled: true`, the chart creates Route **`{fullname}-api`** (`templates/route-s3.yaml`). Upstream / NOTES may still say `{fullname}-s3` — **ignore NOTES**; scripts and docs must use **`{fullname}-api`**.

UI Route remains **`{fullname}`** (port `web-ui` / `:5000`). Health for UI: `https://<host>/api`. There is **no** `/minio/health/*` on S4.

### 11. Dual endpoints when a laptop CLI registers S3

If bootstrap registers an S3 artifact store from **outside** the cluster (e.g. ZenML CLI), preserve a public S3 Route:

```yaml
aws-compatible-storage:
  route:
    enabled: true          # UI
    s3Api:
      enabled: true        # external S3 — only when laptop/CLI needs it
```

| Consumer | Endpoint |
|----------|----------|
| Same-namespace pods (KServe init, bootstrap Job) | `http://<fullname>:7480` |
| Laptop ZenML / external clients | `https://<{fullname}-api Route host>` as `client_kwargs.endpoint_url` |

Keep `route.s3Api.enabled: false` when nothing outside the cluster needs S3.

### 12. Parent-chart helpers for DNS / secret

Parent templates cannot call the subchart’s `aws-compatible-storage.fullname` with the subchart’s root context. Add thin helpers on the **parent** (Fraud Detection / zenml-stack pattern), matching the chosen `fullnameOverride`:

```yaml
{{- define "aws-compatible-storage.fullname" -}}
{{- /* match values: aws-compatible-storage.fullnameOverride */ -}}
aws-compatible-storage
{{- end }}
{{- define "aws-compatible-storage.secretName" -}}
{{- printf "%s-credentials" (include "aws-compatible-storage.fullname" .) }}
{{- end }}
{{- define "aws-compatible-storage.apiPort" -}}
7480
{{- end }}
{{- define "aws-compatible-storage.uiPort" -}}
5000
{{- end }}
```

If using `fullnameOverride: s4`, parent helpers may keep the short name (`s4` / `s4-credentials`) for continuity — just be consistent. If the parent still defines `object-storage.*` helpers from an earlier migration, rename them to `aws-compatible-storage.*` (or keep short `s4.*` aliases only when `fullnameOverride: s4`).

Use these in the bootstrap Job instead of hardcoding only in one place.

### 13. Hand-rolled MinIO is a first-class path

Inventory may find **no** Chart.yaml `minio` dependency — only `templates/minio-*.yaml`. Still convert: delete those templates, add `aws-compatible-storage`, rewire scripts that `--set minio.*` / wait on `deployment/minio` / `job/minio-bootstrap` / `/minio/health/ready`.

### 14. Bucket bootstrap stays in the parent

The aws-compatible-storage chart does **not** create buckets. lakeFS blockstore wiring, OpenShift AI data-connection Secrets, and bucket Jobs belong in the **parent** chart — same separation as documented in [aws-compatible-storage/README.md](https://github.com/rh-ai-quickstart/ai-architecture-charts/blob/main/aws-compatible-storage/README.md).

### 15. After `helm dependency update`

Commit **Chart.lock** and the packaged chart under `charts/` (e.g. `aws-compatible-storage-0.1.0.tgz`) per the quickstart’s existing Helm vendoring practice. Prefer the published OCI/HTTP repo version once the chart is released; use `file://../ai-architecture-charts/aws-compatible-storage/helm` only while iterating on an unreleased charts branch. Remove any leftover `object-storage-*.tgz` / `charts/object-storage/`.

---

## Workflow

### Phase 0: Resolve quickstart

Resolve which quickstart this session is for before any edits. If the user provides a git URL, clone it under `.rhoai-qs/` (slug = repo name). Otherwise, list sibling slugs under `.rhoai-qs/` (every entry is a quickstart) and confirm when more than one exists. See [validation-skill-template.md](../../../docs/foundation/validation-skill-template.md).

### Phase 1: Inventory MinIO surface area

```
- [ ] 1. Chart.yaml — minio / configure-pipeline / object-storage dependencies (may be absent if hand-rolled)
- [ ] 2. values.yaml — minio.*, configure-pipeline.minio.*, pipelineStorage.deployMinio, object-storage.*, aws-compatible-storage.*
- [ ] 3. Parent templates — minio-*.yaml, bucket Jobs/hooks, Routes, Secrets, object-storage.* helpers
- [ ] 4. App code — MINIO_*, AWS_* → http://minio:9000, mc init containers, minio SDK
- [ ] 5. Bootstrap / validate / delete scripts — oc waits, helm --set minio.*, health URLs
- [ ] 6. compose.yml / Containerfiles — local MinIO or minio/mc
- [ ] 7. Makefile / CI — minio-console, health checks, sample-upload
- [ ] 8. Docs — README, AGENTS, design, Mermaid, **PNG/SVG**
- [ ] 9. DSPA / lakeFS / GroundX / ZenML — Ready-before-hook or external S3 Route needs
- [ ] 10. Choose fullnameOverride: aws-compatible-storage (default) vs s4 (short DNS)
```

Present a short inventory + **URL/path matrix** (in-cluster vs Route, Secret keys, Route names, chosen `fullnameOverride`). Confirm scope before edit.

### Phase 2: Spec the conversion (approve before edit)

Draft: Service DNS (`fullnameOverride`), bucket names, auth, PVC size, bootstrap Job (regular), DSPA FQDN, whether **`route.s3Api.enabled`**, ZenML/store renames (`openshift-minio` → `openshift-s4` / `openshift-aws-compatible-storage`). Get approval, then implement.

### Phase 3: Remove MinIO from Helm

```
- [ ] 1. Remove Chart.yaml minio / configure-pipeline MinIO-only deps (or set deployMinio: false if keeping configure-pipeline for other reasons)
- [ ] 2. Delete templates/minio-*.yaml and MinIO-only hooks/Jobs
- [ ] 3. Drop minio: value blocks
- [ ] 4. helm dependency update — no minio chart left under charts/ (unless deliberately retained unused — prefer remove)
```

Subchart reference (inverse / MinIO add): [rh-qs-deploy/references/helm-minio.md](../rh-qs-deploy/references/helm-minio.md).

### Phase 4: Add the aws-compatible-storage Helm chart

```yaml
# Chart.yaml
dependencies:
  - name: aws-compatible-storage
    version: 0.1.0
    repository: https://rh-ai-quickstart.github.io/ai-architecture-charts
    # While developing against a local charts checkout:
    # repository: "file://../ai-architecture-charts/aws-compatible-storage/helm"
    condition: aws-compatible-storage.enabled
```

```bash
# From the quickstart Helm chart directory
helm dependency update
```

**Minimal values** (predictable DNS + OpenShift routes):

```yaml
aws-compatible-storage:
  enabled: true
  fullnameOverride: aws-compatible-storage   # or "s4" for short DNS
  image:
    repository: quay.io/rh-aiservices-bu/s4
    tag: "0.3.2"
    pullPolicy: IfNotPresent
  s3:
    accessKeyId: s4admin
    secretAccessKey: s4secret   # override via secrets overlay; do not commit prod
  auth:
    enabled: true
    username: admin
    password: changeme          # required when auth.enabled; prefer secrets.yaml
  route:
    enabled: true
    s3Api:
      enabled: false            # true only if laptop/CLI needs public S3 (e.g. ZenML)
  storage:
    data:
      storageClass: gp3-csi     # when the cluster requires an explicit class
      size: 10Gi

# Parent-owned bucket list (not part of the subchart)
awsCompatibleStorageBuckets:
  create: true
  names:
    - zenml-artifacts           # use this quickstart’s real bucket names

jobImages:
  cli: image-registry.openshift-image-registry.svc:5000/openshift/cli:latest
  python: registry.redhat.io/ubi9/python-311:latest
  shell: registry.redhat.io/ubi9/ubi-minimal:latest
```

Add parent helpers ([§12](#12-parent-chart-helpers-for-dns--secret)). Secret name with `fullnameOverride: aws-compatible-storage`: **`aws-compatible-storage-credentials`**. With `fullnameOverride: s4`: **`s4-credentials`**.

### Phase 5: Rewire application and chart consumers

```
- [ ] 1. In-cluster: http://minio:9000 → http://<fullname>:7480
- [ ] 2. DSPA / cross-NS: <fullname>.<ns>.svc.cluster.local:7480
- [ ] 3. External S3 (if any): https://<{fullname}-api host> — Route name {fullname}-api
- [ ] 4. Credentials → {fullname}-credentials AWS_*; drop MINIO_ROOT_* unless aliased
- [ ] 5. Replace mc init / bootstrap with UBI Python + boto3
- [ ] 6. Path-style addressing if the client needs it; region us-east-1
- [ ] 7. Bucket bootstrap Job — Phase 5b
- [ ] 8. .env.example / stack_config — S4_* / AWS_COMPATIBLE_STORAGE_* vars; rename store ids if approved
- [ ] 9. lakeFS / health waits: /minio/health/* → http://<fullname>:5000/api
- [ ] 10. Validate scripts: deployment/<fullname>, pvc/<fullname>-data, bootstrap Job, routes <fullname> + <fullname>-api
```

### Phase 5b: Bucket bootstrap Job (required pattern)

Regular Job in the **parent** chart (not a hook when `--wait` / DSPA needs the bucket). Wait on UI `/api`, then boto3 with retry on `list_buckets`, create buckets idempotently, optional put/get smoke test.

Use parent helpers for host/ports/secret name. Images from `jobImages`. No `helm.sh/hook` annotations.

### Phase 6: Local compose (optional)

```bash
podman run -d --name s4 \
  -p 5000:5000 -p 7480:7480 \
  -v s4-data:/var/lib/ceph/radosgw \
  quay.io/rh-aiservices-bu/s4:0.3.2
```

Wire to `http://localhost:7480` (or compose service DNS) with demo keys only. Remove MinIO compose service unless dual-store is requested. Prefer **podman** in docs.

### Phase 7: Docs, Makefile, verify

```
- [ ] 1. README / AGENTS — MinIO → aws-compatible-storage (S4); link ai-architecture-charts aws-compatible-storage + upstream s4; UI :5000, S3 :7480, Routes {fullname} / {fullname}-api
- [ ] 2. Diagrams — Mermaid preferred
- [ ] 3. Makefile — drop minio-* targets; add logs-aws-compatible-storage / logs-s4 if useful (Makefile-wrapped)
- [ ] 4. rh-qs-debug-and-deploy / validate-stack — UI `/api`, Route admitted, bootstrap Job complete; debug conversion gaps if deploy fails
- [ ] 5. Design / pipeline notes under .rhoai-qs/<slug>/ if present
```

### Phase 8: Quality gates

```bash
helm dependency update deploy/helm/<slug>/
helm lint deploy/helm/<slug>
helm template <release> deploy/helm/<slug> -f deploy/helm/<slug>/values.yaml \
  | grep -EIin 'aws-compatible-storage|object-storage|s4|minio|7480|9000|minio/mc|docker.io' || true
helm unittest deploy/helm/<slug>   # when tests exist
make lint test helm-lint helm-template helm-test   # when targets exist
```

Optional: lint/unittest the shared chart itself when changing it:

```bash
helm lint ./aws-compatible-storage/helm
helm unittest ./aws-compatible-storage/helm
```

Rendered manifests must include aws-compatible-storage Deployment/Service/Routes and **no** MinIO Deployment/StatefulSet / `quay.io/minio`. Residual `object-storage` strings should be limited to DSPA CR fields or intentional historical notes. Recommend **`rh-qs-debug-and-deploy`** so cluster deploy, smoke tests, and conversion-gap fixes (e.g. Loki bundled MinIO) run in one pass.

## Rules

- **Agents never run `oc`/`kubectl`** for routine work — Helm/Makefile only (`rh-qs-secure`)
- **Never commit** production `auth.password`, S3 secret keys, or cluster Route hostnames
- **Do not** leave MinIO and aws-compatible-storage both enabled for the same workload unless dual-store is requested
- **Do not** vendor `rh-aiservices-bu/s4/charts/s4` into the quickstart — use ai-architecture-charts `aws-compatible-storage`
- **Do not** keep the former chart name `object-storage` as a Helm dependency once migrating (rename to `aws-compatible-storage`)
- Keep S3 API in-cluster (`route.s3Api.enabled: false`) unless external registration needs it
- When `auth.enabled: true`, always set `auth.username` and `auth.password`
- Pin aws-compatible-storage chart version + S4 image tag; later bumps via **`rh-qs-bump-versions`**
- Prefer **podman** over docker in docs
- Prefer **OpenShift** / `oc` wording in docs; agents still do not run cluster commands for routine work
- **Never** ship Jobs on `quay.io/minio/mc` or Docker Hub images
- Bucket Jobs that unblock `helm --wait` must be **regular Jobs**, not post-install hooks
- Scripts must use Route **`{fullname}-api`**, not `{fullname}-s3`

## Checklist

- [ ] MinIO removed (subchart and/or hand-rolled templates) — no render
- [ ] `aws-compatible-storage` dependency from ai-architecture-charts (`Chart.lock` + packaged chart); image tag + chart version pinned
- [ ] No leftover `object-storage` Helm dependency / packaged chart (DSPA `objectStorage` CR fields OK)
- [ ] `fullnameOverride` chosen (`aws-compatible-storage` or `s4`); parent helpers present
- [ ] Consumers use `{fullname}-credentials` + port **7480** (FQDN for DSPA if present)
- [ ] External S3 (if needed) uses Route **`{fullname}-api`** and `route.s3Api.enabled: true`
- [ ] Bucket bootstrap = parent regular Job + UBI Python/boto3 (+ smoke test when prior Job had one)
- [ ] KServe/init `mc` replaced with boto3
- [ ] Bootstrap/validate scripts wait on S4 UI `/api` (not `/minio/health/*`)
- [ ] README / diagrams / `.env.example` describe aws-compatible-storage / S4 (including PNGs)
- [ ] `helm lint` + `helm template` (+ unittest) clean; **`rh-qs-debug-and-deploy`** recommended

## Output

- Updated Helm chart (no MinIO; `aws-compatible-storage` subchart + parent bootstrap Job)
- Updated app / script / env wiring
- Updated README / architecture mentions
- Short summary: `fullnameOverride`, endpoints (in-cluster vs Route), Secret name, auth, bootstrap Job, any leftover `MINIO_*` aliases

## Related

- Shared chart: [ai-architecture-charts/aws-compatible-storage](https://github.com/rh-ai-quickstart/ai-architecture-charts/tree/main/aws-compatible-storage) — [README](https://github.com/rh-ai-quickstart/ai-architecture-charts/blob/main/aws-compatible-storage/README.md), [values.yaml](https://github.com/rh-ai-quickstart/ai-architecture-charts/blob/main/aws-compatible-storage/helm/values.yaml)
- Upstream runtime: [rh-aiservices-bu/s4](https://github.com/rh-aiservices-bu/s4) — [Deployment docs](https://github.com/rh-aiservices-bu/s4/tree/main/docs/deployment)
- Inverse (add MinIO): [rh-qs-deploy/references/helm-minio.md](../rh-qs-deploy/references/helm-minio.md)
- **`rh-qs-secure`** — no raw cluster commands
- **`rh-qs-debug-and-deploy`** — post-migration cluster deploy, test, and debug/fix (preferred over verify-deploy alone for conversion gaps)
- **`rh-qs-bump-versions`** — later dependency / image bumps
