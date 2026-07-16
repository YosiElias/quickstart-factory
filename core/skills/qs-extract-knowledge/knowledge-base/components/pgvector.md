---
name: pgvector
description: "PostgreSQL with pgvector extension deployed as StatefulSet via Helm subchart for persistent vector and relational storage"
summary: "pgvector deploys PostgreSQL 17 (docker.io/pgvector/pgvector:pg17) as a StatefulSet via the ai-architecture-charts Helm subchart with PVC-backed storage, providing shared relational and vector storage consumed by multiple services — backend (async asyncpg via SQLAlchemy), Phoenix tracing (PHOENIX_SQL_DATABASE_URL), and annotation interface (sync psycopg2) — through a single Kubernetes Secret containing pre-built uri and jdbc-uri connection strings. Use when quickstart services need a shared PostgreSQL database with vector search capabilities; the subchart handles StatefulSet creation, PVC volumeClaimTemplates (ReadWriteOnce, 5Gi default), ConfigMap init scripts that create the database and enable the vector extension, and optional extraDatabases with per-database vectordb toggle. Consumers read DATABASE_URL from the pgvector Secret's uri key and apply URI scheme transforms (.replace(\"postgresql\", \"postgresql+asyncpg\") for async, .replace(\"postgresql\", \"postgresql+psycopg2\") for sync); backend and init-job Deployments include wait-for-postgres init containers using pg_isready to block until pgvector is reachable. Secret URIs embed namespace-qualified hostnames (e.g., pgvector.my-namespace), subchart defaults (user: postgres, password: rag_password, dbname: rag_blueprint) apply unless overridden in parent chart values, extraDatabases is commented out by default, annotation interface must handle psycopg2.errors.UndefinedTable for tables not yet created by the init pipeline, and local compose uses postgres:15 without automatic vector extension creation."
metadata:
  type: component
tags:
  tech_stack: [postgresql, pgvector, sqlalchemy, asyncpg, psycopg2, sqlmodel]
  ai_pattern: [vector-search, embeddings]
  platform: [openshift, kubernetes]
  data_layer: [pgvector]
source_examples:
  - quickstart: "ansible-log-analysis"
    repo: "https://github.com/rh-ai-quickstart/ansible-log-analysis"
    notes: "pgvector as shared relational + vector database for backend, Phoenix tracing, and annotation interface"
    approach: "A"
---

# pgvector

## Overview

pgvector is PostgreSQL with the `vector` extension, deployed as a Kubernetes StatefulSet via a reusable Helm subchart from `ai-architecture-charts`. In quickstart architectures, it serves as a shared database consumed by multiple services (backend, tracing, annotation UI) using a single Kubernetes Secret for connection strings. The subchart handles PVC-backed storage, init scripts for database and extension creation, and generates both `uri` and `jdbc-uri` connection strings in the Secret.

## Tech Stack & Dependencies
- **Runtime:** PostgreSQL 17 (via `docker.io/pgvector/pgvector:pg17`)
- **Container image:** `docker.io/pgvector/pgvector:pg17`
- **Key dependencies:** Kubernetes PVC for persistent storage; consumers use `asyncpg`, `psycopg2-binary`, `sqlalchemy`, `sqlmodel`
- **Helm subchart:** `pgvector` v0.1.0 from `https://rh-ai-quickstart.github.io/ai-architecture-charts`

## Key Patterns

### StatefulSet with PVC-Backed Storage

The subchart deploys pgvector as a StatefulSet (not a Deployment) to ensure stable network identity and persistent storage via `volumeClaimTemplates`. Data is mounted at `/var/lib/postgresql`.

```yaml
# From pgvector subchart values.yaml
volumeClaimTemplates:
  - metadata:
      name: pg-data
    spec:
      accessModes: ["ReadWriteOnce"]
      resources:
        requests:
          storage: 5Gi

volumeMounts:
  - mountPath: /docker-entrypoint-initdb.d
    name: initdb-volume
  - mountPath: /var/lib/postgresql
    name: pg-data
```

### Init Script for Database and Extension Creation

A ConfigMap-mounted init script runs at container startup to create the database and enable the `vector` extension. The `extraDatabases` value allows creating additional databases with optional vector support.

```yaml
# From pgvector subchart templates/configmap.yaml
data:
  init-db.sh: |
    #!/bin/bash
    set -e
    psql -U postgres -c "CREATE DATABASE ${POSTGRES_DBNAME};"
    psql -U postgres -d ${POSTGRES_DBNAME} -c "CREATE EXTENSION VECTOR;"
    {{- range .Values.extraDatabases }}
    psql -U postgres -c "CREATE DATABASE {{ .name }};"
    {{- if .vectordb }}
    psql -U postgres -d {{ .name }} -c "CREATE EXTENSION VECTOR;"
    {{- end }}
    {{- end }}
```

### Shared Secret with Pre-Built Connection URIs

The Secret template generates both standard PostgreSQL and JDBC connection URIs, so consumers can reference `pgvector` secret keys (`uri`, `jdbc-uri`) directly without constructing URLs themselves.

```yaml
# From pgvector subchart templates/secret.yaml
data:
  user: {{ .Values.secret.user | b64enc | quote }}
  password: {{ .Values.secret.password | b64enc | quote }}
  host: {{ .Values.secret.host | b64enc | quote }}
  port: {{ .Values.secret.port | b64enc | quote }}
  dbname: {{ .Values.secret.dbname | b64enc | quote }}
  jdbc-uri: {{ printf "jdbc:postgresql://%s.%s:%s/%s?password=%s&user=%s" ... | b64enc | quote }}
  uri: {{ printf "postgresql://%s:%s@%s.%s:%s/%s" ... | b64enc | quote }}
```

### Multi-Service Consumption via Secret References

Multiple services reference the same `pgvector` Secret by key name. The backend uses the `uri` key for `DATABASE_URL`, Phoenix uses it for `PHOENIX_SQL_DATABASE_URL`, and the annotation interface also reads `DATABASE_URL` from the same secret.

```yaml
# From backend/values.yaml - backend env
- name: DATABASE_URL
  valueFrom:
    secretKeyRef:
      name: pgvector
      key: uri

# From phoenix/values.yaml - Phoenix tracing env
- name: PHOENIX_SQL_DATABASE_URL
  valueFrom:
    secretKeyRef:
      name: pgvector
      key: uri
```

### Readiness Probe with Multi-Database Check

The StatefulSet readiness probe iterates over the primary database and all `extraDatabases` to confirm each is reachable before marking the pod as ready.

```yaml
# From pgvector subchart templates/statefulset.yaml
readinessProbe:
  exec:
    command:
      - /bin/sh
      - -c
      - |
        for db in "$POSTGRES_DBNAME" {{- range .Values.extraDatabases }} "{{ .name }}"{{- end }}; do
          pg_isready -U "$POSTGRES_USER" -d "$db" -h 127.0.0.1 -p "$POSTGRES_PORT" || exit 1
        done
```

### Async SQLAlchemy Connection Pattern

The backend connects to pgvector using `sqlalchemy.ext.asyncio` with `asyncpg`, applying string replacements to normalize the connection URI scheme.

```python
# From src/alm/database.py
engine = create_async_engine(
    os.getenv("DATABASE_URL")
    .replace("+asyncpg", "")
    .replace("postgresql", "postgresql+asyncpg")
)
```

### Sync SQLAlchemy Connection (Annotation Interface)

The annotation interface uses synchronous `psycopg2` instead, applying a different URI transform to get the `psycopg2` driver string.

```python
# From services/annotation_interface/app.py
self.engine = create_engine(
    os.getenv("DATABASE_URL")
    .replace("+asyncpg", "")
    .replace("postgresql", "postgresql+psycopg2")
)
```

## Configuration
- **Environment variables:** `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_PORT`, `POSTGRES_DBNAME` (all sourced from `pgvector` Secret); consumers read `DATABASE_URL` or `PHOENIX_SQL_DATABASE_URL` from the `uri` key
- **Config files:** Init script at `/docker-entrypoint-initdb.d/init-db.sh` (ConfigMap-mounted)
- **Helm values:** `secret.user`, `secret.password`, `secret.dbname`, `secret.host`, `secret.port` for credentials; `extraDatabases` list for additional databases; `volumeClaimTemplates[0].spec.resources.requests.storage` for PVC size

## Known Gotchas
- The URI in the Secret embeds the namespace (`%s.%s` with `host` and `Release.Namespace`), so the generated `uri` and `jdbc-uri` include the namespace-qualified hostname (e.g., `pgvector.my-namespace`). This is visible in `templates/secret.yaml`.
- The backend init-job template (`backend/templates/init-job.yaml`) includes a `wait-for-postgres` init container using `pg_isready -d "$DATABASE_URL"` to block until pgvector is reachable, and the main backend Deployment also has this same init container pattern -- both need the `pgvector` secret to exist before they can start.
- The `extraDatabases` feature in `values.yaml` supports creating additional databases with optional vector extension (`vectordb: true/false`), but it is commented out by default.
- In the parent chart `values.yaml`, the pgvector secret overrides are commented out, meaning the subchart defaults (`user: postgres`, `password: rag_password`, `dbname: rag_blueprint`) are used unless explicitly overridden.
- The annotation interface handles `psycopg2.errors.UndefinedTable` explicitly (in `services/annotation_interface/app.py` line 134) to gracefully handle the case where the backend init pipeline has not yet created the `grafanaalert` table.

## Testing Notes
- Verify the StatefulSet pod is running: check that `pg_isready` returns success for the configured database
- Confirm the `vector` extension is installed: connect to the database and run `SELECT * FROM pg_extension WHERE extname = 'vector';`
- For local development, `deploy/local/compose.yaml` uses plain `postgres:15` image with `POSTGRES_DB=logsdb` and no vector extension auto-creation (differs from Helm deployment)

## Related Patterns
- Helm subchart wiring (how `ai-architecture-charts` subcharts are integrated as dependencies)
- Backend init-job pattern (wait-for-postgres init container before running pipeline)
