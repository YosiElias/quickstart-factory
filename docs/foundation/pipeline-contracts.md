# Pipeline Contract Formats

This document defines the YAML schema for each inter-skill handoff file. These contracts specify exactly what each file contains, which skill produces it, and which skill consumes it — enabling skills to be developed and validated independently.

Every handoff file follows the common header defined in [spec-as-contract.md](spec-as-contract.md) and lives in the quickstart's `.rhoai-qs/<slug>/pipeline/` directory as defined in [pipeline-convention.md](pipeline-convention.md).

## Common Header

All handoff files (specs and manifests) share this header:

```yaml
spec_version: 1
quickstart_name: "<human-readable name>"
slug: "<lowercase-hyphenated-identifier>"
skill: "<producing-skill>"
created_at: "<ISO 8601 timestamp>"
```

Manifests also include a `dependencies` section that records which upstream files they were built from, along with a `content_hash` for staleness detection (see [spec-as-contract.md](spec-as-contract.md#staleness-detection)).

## Handoff Files Overview

The pipeline passes structured artifacts through these files, in order:

| # | File | Producer | Consumer | Category | Location |
|---|------|----------|----------|----------|----------|
| 1 | `architecture-spec.yaml` | rh-qs-architect | rh-qs-scaffold | Spec | `.rhoai-qs/<slug>/designs/` |
| 2 | `scaffold-manifest.yaml` | rh-qs-scaffold | rh-qs-implement | Manifest | `.rhoai-qs/<slug>/pipeline/` |
| 3 | `implementation-manifest.yaml` | rh-qs-implement | rh-qs-deploy | Manifest | `.rhoai-qs/<slug>/pipeline/` |
| 4 | `deploy-manifest.yaml` | rh-qs-deploy | rh-qs-security | Manifest | `.rhoai-qs/<slug>/pipeline/` |
| 5 | `security-report.yaml` | rh-qs-security | rh-qs-debug-and-deploy | Report | `.rhoai-qs/<slug>/pipeline/` |
| 6 | `deploy-state.yaml` | rh-qs-debug-and-deploy | rh-qs-document | State | `.rhoai-qs/<slug>/pipeline/` |
| 7 | `doc-manifest.yaml` | rh-qs-document | rh-qs-ship | Manifest | `.rhoai-qs/<slug>/pipeline/` |

Additionally, the PRD (`.rhoai-qs/<slug>/prds/prd.md`) produced by rh-qs-discovery is a Markdown file, not YAML, and its format is defined by the PRD template — not this document.

---

## 1. architecture-spec.yaml

**Producer:** rh-qs-architect
**Consumer:** rh-qs-scaffold
**Category:** Spec
**Location:** `.rhoai-qs/<slug>/designs/architecture-spec.yaml`

Documents the architecture decisions, component bill of materials, technology stack, and testing strategy for a quickstart.

### Key fields

```yaml
spec_version: 1
quickstart_name: "Spending Transaction Monitor"
slug: spending-transaction-monitor
skill: rh-qs-architect
created_at: "2026-07-01T12:00:00Z"

technology_stack:
  frontend: "React 19 with TypeScript, Vite build, TanStack Router/Query for routing and state"
  backend: "FastAPI with Python 3.12+, UV package manager, Pydantic v2, SQLAlchemy 2 async ORM"
  database: "PostgreSQL"
  vector_db: "pgvector via ai-architecture-charts/pgvector"
  model_serving: "vLLM via ai-architecture-charts/llm-service"
  local_runtime: "podman-compose"
  monorepo: "Turborepo with pnpm and uv"
  deploy_platform: "Red Hat OpenShift AI"

components:
  llm-service:
    type: inference
    role: "LLM inference for conversational queries"
    technology: "vLLM"
    delivery: chart

    chart:
      name: ai-architecture-charts/llm-service
      version: "0.3.0"

    constraints:
      - "Must fit in 2x A100 GPUs"

    kb_sources:
      - path: core/knowledge-base/components/vllm-serving-patterns.md
        match_reason: "vLLM deployment patterns for multi-GPU serving"

    dependencies:
      - component: api-server
        reason: "API calls LLM for inference"

integration_patterns:
  protocols:
    - pair: "Backend → Model serving"
      protocol: "REST via KServe v2 inference protocol"
    - pair: "Ingestion → Vector DB"
      protocol: "Message queue (NATS) for async document processing"
  data_flows:
    - name: "User query flow"
      path: "Frontend → Backend API → Vector DB (similarity search) → LLM (context injection) → Response"
    - name: "Document ingestion"
      path: "Upload → Backend → Embedding service → Vector DB storage"
  security_boundaries:
    - point: "Frontend → Backend"
      mechanism: "OAuth2 with RHOAI authentication"
    - point: "Backend → Model serving"
      mechanism: "Service account token, network policy to model namespace"
    - point: "Secrets"
      mechanism: "OpenShift secrets for DB credentials and model API keys"

architecture_diagram_path: .rhoai-qs/spending-transaction-monitor/designs/architecture-diagram.mmd

testing_strategy:
  profile: standard
  unit_tests:
    python:
      scope: "Routes, schemas, services"
      runs_on: "Every PR (pr-checks / ci.yaml)"
    typescript:
      scope: "Components, hooks"
      runs_on: "Every PR"
  integration_tests:
    scope: "API + DB + in-cluster services"
    runs_on: "PR E2E workflow (rh-qs-test-suite)"
  e2e_tests:
    scope: "Agent quality, RAG responses"
    runs_on: "pull_request_target or nightly"
  helm_validation:
    scope: "Exported manifests valid"
    runs_on: "Every PR"

dependencies:
  - spec: .rhoai-qs/spending-transaction-monitor/prds/prd.md
    fields_used: [problem_statement, target_persona, technology_constraints]
    content_hash: "sha256:..."
  - spec: .rhoai-qs/spending-transaction-monitor/pipeline/prd-features.yaml
    fields_used: [input_features, deployment_questions, decision_points]
    content_hash: "sha256:..."
  - spec: .rhoai-qs/spending-transaction-monitor/pipeline/kb-scores.yaml
    fields_used: [results]
    content_hash: "sha256:..."
```

### Required fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `technology_stack` | map | yes | Technology layers with free-text descriptions (1-2 lines each) |
| `components` | map | yes | Component bill of materials keyed by component name |
| `components.<name>.type` | enum | yes | Component type: `inference`, `database`, `backend`, `ui`, `worker`, `gateway` |
| `components.<name>.role` | string | yes | What this component does |
| `components.<name>.technology` | string | yes | Stack/runtime (e.g., 'FastAPI', 'vLLM') |
| `components.<name>.delivery` | enum | yes | `chart`, `rhoai`, `application`, or `chart+rhoai` |
| `components.<name>.chart` | map | if delivery=chart | Chart name and version |
| `components.<name>.rhoai_features` | list | if delivery=rhoai | RHOAI features with purpose |
| `components.<name>.constraints` | list | no | PRD/requirement constraints (GPU, storage, etc.) |
| `components.<name>.kb_sources` | list of objects | no | KB files with path and match_reason |
| `components.<name>.dependencies` | list | no | Component dependencies with reason |
| `integration_patterns` | map | yes | Communication protocols, data flows, and security boundaries (from integration-analyzer subagent, Step 8) |
| `integration_patterns.protocols` | list | yes | Non-obvious communication patterns between component pairs |
| `integration_patterns.protocols[].pair` | string | yes | Component pair or integration point (e.g., "Backend → Model serving") |
| `integration_patterns.protocols[].protocol` | string | yes | Protocol name, version, and brief justification if non-standard |
| `integration_patterns.data_flows` | list | yes | Major user and system flows through components |
| `integration_patterns.data_flows[].name` | string | yes | Human-readable flow name |
| `integration_patterns.data_flows[].path` | string | yes | Component chain with arrows and context |
| `integration_patterns.security_boundaries` | list | yes | Security considerations at component boundaries |
| `integration_patterns.security_boundaries[].point` | string | yes | Boundary or security checkpoint name |
| `integration_patterns.security_boundaries[].mechanism` | string | yes | Security approach (auth, secrets, policy, isolation, etc.) |
| `architecture_diagram_path` | string | yes | Path to Mermaid diagram file (e.g., `.rhoai-qs/<slug>/designs/architecture-diagram.mmd`) |
| `testing_strategy` | map | yes | Testing levels and scope (no tool commands) |
| `dependencies` | list | yes | Upstream specs with content_hash |

---

## 2. scaffold-manifest.yaml

**Producer:** rh-qs-scaffold
**Consumer:** rh-qs-implement
**Category:** Manifest (records what was created)

Lists every file and directory the scaffold skill created, so the implement skill knows the exact repo structure it's working with.

### Schema

```yaml
spec_version: 1
quickstart_name: "Spending Transaction Monitor"
slug: spending-transaction-monitor
skill: rh-qs-scaffold
created_at: "2026-07-01T13:00:00Z"

repo:
  name: spending-transaction-monitor
  root: "."

packages:
  - name: api
    path: packages/api
    language: python
    framework: fastapi
    entry_point: src/main.py
    test_command: "make test-api"
  - name: ui
    path: packages/ui
    language: typescript
    framework: react
    entry_point: src/App.tsx
    test_command: "make test-ui"

ci_jobs:
  - name: lint
    path: .github/workflows/lint.yml
    trigger: pull_request
  - name: test
    path: .github/workflows/test.yml
    trigger: pull_request

created_files:
  - path: packages/api/src/main.py
    type: skeleton
  - path: packages/api/pyproject.toml
    type: config
  - path: packages/ui/src/App.tsx
    type: skeleton
  - path: packages/ui/package.json
    type: config
  - path: Makefile
    type: config
  - path: .github/workflows/lint.yml
    type: ci
  - path: .github/workflows/test.yml
    type: ci

linting:
  python: ruff
  typescript: eslint
  config_files:
    - path: ruff.toml
    - path: .eslintrc.json

dependencies:
  - spec: architecture-spec.yaml
    fields_used: [components, technology_stack]
    content_hash: "sha256:..."
```

### Required fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `repo.name` | string | yes | Repository name |
| `repo.root` | string | yes | Root path within the quickstart's own repo (typically `"."`) — this is separate from where the repo is nested on disk relative to `quickstart-factory`, see [pipeline-convention.md](pipeline-convention.md#nested-quickstart-repos) |
| `packages` | list | yes | Packages created, each with name, path, language, framework |
| `packages[].name` | string | yes | Package identifier |
| `packages[].path` | string | yes | Relative path from repo root |
| `packages[].language` | string | yes | `python`, `typescript`, etc. |
| `packages[].framework` | string | yes | `fastapi`, `react`, etc. |
| `packages[].entry_point` | string | yes | Main file relative to package path |
| `packages[].test_command` | string | yes | Command to run tests for this package |
| `ci_jobs` | list | yes | CI workflow files created |
| `created_files` | list | yes | Every file created, with path and type |
| `created_files[].type` | enum | yes | `skeleton`, `config`, `ci`, `docs` |
| `linting` | map | yes | Linter config per language |
| `dependencies` | list | yes | Upstream specs with `content_hash` |

---

## 3. implementation-manifest.yaml

**Producer:** rh-qs-implement
**Consumer:** rh-qs-deploy
**Category:** Manifest (records what was implemented)

Documents the endpoints, database models, services, and test coverage produced by the implementation skill.

### Schema

```yaml
spec_version: 1
quickstart_name: "Spending Transaction Monitor"
slug: spending-transaction-monitor
skill: rh-qs-implement
created_at: "2026-07-01T15:00:00Z"

packages:
  api:
    endpoints:
      - method: POST
        path: /api/v1/query
        description: "Submit a transaction query for RAG-augmented analysis"
        request_schema: QueryRequest
        response_schema: QueryResponse
      - method: GET
        path: /api/v1/health
        description: "Health check endpoint"
        request_schema: null
        response_schema: HealthResponse

    services:
      - name: llm_service
        file: packages/api/src/services/llm.py
        description: "vLLM client for inference"
      - name: retrieval_service
        file: packages/api/src/services/retrieval.py
        description: "pgvector retrieval for RAG context"

    db_models:
      - name: Transaction
        file: packages/api/src/models/transaction.py
        table: transactions
        fields: [id, description, amount, category, embedding]
      - name: QueryLog
        file: packages/api/src/models/query_log.py
        table: query_logs
        fields: [id, query_text, response_text, created_at]

    env_vars:
      - name: LLM_ENDPOINT
        description: "vLLM serving endpoint URL"
        example: "http://llm-service:8000/v1"
      - name: PGVECTOR_URL
        description: "pgvector connection string"
        example: "postgresql://user:pass@pgvector:5432/qs"

  ui:
    routes:
      - path: /
        component: ChatInterface
        description: "Main chat interface for transaction queries"
    env_vars:
      - name: API_URL
        description: "Backend API base URL"
        example: "http://localhost:8000"

test_coverage:
  total_tests: 24
  by_package:
    api: 18
    ui: 6
  test_command: "make test"
  test_result: pass

dependencies:
  - spec: scaffold-manifest.yaml
    fields_used: [packages, repo]
    content_hash: "sha256:..."
  - spec: architecture-spec.yaml
    fields_used: [components]
    content_hash: "sha256:..."
```

### Required fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `packages` | map | yes | Implemented packages keyed by package name |
| `packages.<name>.endpoints` | list | if backend | API endpoints with method, path, schemas |
| `packages.<name>.services` | list | if backend | Internal services with file paths |
| `packages.<name>.db_models` | list | if uses DB | Database models with table names and fields |
| `packages.<name>.env_vars` | list | yes | Environment variables this package requires |
| `packages.<name>.routes` | list | if frontend | UI routes with components |
| `test_coverage.total_tests` | integer | yes | Number of tests |
| `test_coverage.test_command` | string | yes | Command to run all tests |
| `test_coverage.test_result` | enum | yes | `pass` or `fail` |
| `dependencies` | list | yes | Upstream specs/manifests with `content_hash` |

---

## 4. deploy-manifest.yaml

**Producer:** rh-qs-deploy
**Consumer:** rh-qs-security
**Category:** Manifest (records deployment artifacts)

Documents the Helm charts, compose services, Containerfiles, routes, and environment variables for the deployment.

### Schema

```yaml
spec_version: 1
quickstart_name: "Spending Transaction Monitor"
slug: spending-transaction-monitor
skill: rh-qs-deploy
created_at: "2026-07-01T16:00:00Z"

helm:
  chart_path: deploy/helm
  dependencies:
    - name: llm-service
      chart: ai-architecture-charts/llm-service
      version: "0.3.0"
      values_file: deploy/helm/values-llm.yaml
    - name: pgvector
      chart: ai-architecture-charts/pgvector
      version: "0.2.1"
      values_file: deploy/helm/values-pgvector.yaml
  validation:
    helm_lint: pass
    helm_template: pass

compose:
  file: compose.yml
  services:
    - name: api
      build_context: packages/api
      ports: ["8000:8000"]
    - name: ui
      build_context: packages/ui
      ports: ["3000:3000"]
    - name: llm-service
      image: "vllm/vllm-openai:latest"
      ports: ["8001:8000"]
    - name: pgvector
      image: "pgvector/pgvector:pg16"
      ports: ["5432:5432"]

containerfiles:
  - package: api
    path: packages/api/Containerfile
    base_image: "registry.access.redhat.com/ubi9/python-312:latest"
    stages: [build, runtime]
  - package: ui
    path: packages/ui/Containerfile
    base_image: "registry.access.redhat.com/ubi9/nodejs-22:latest"
    stages: [build, runtime]

routes:
  - name: api
    path: /api
    service: api
    port: 8000
    tls: edge
  - name: ui
    path: /
    service: ui
    port: 3000
    tls: edge

env_vars:
  - name: LLM_ENDPOINT
    source: helm_values
    secret: false
  - name: PGVECTOR_URL
    source: kubernetes_secret
    secret: true

dependencies:
  - spec: implementation-manifest.yaml
    fields_used: [packages, test_coverage]
    content_hash: "sha256:..."
  - spec: architecture-spec.yaml
    fields_used: [components, technology_stack]
    content_hash: "sha256:..."
```

### Required fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `helm.chart_path` | string | yes | Path to the Helm chart directory |
| `helm.dependencies` | list | yes | Helm chart dependencies with name, chart, version |
| `helm.validation` | map | yes | Results of `helm lint` and `helm template` |
| `compose.file` | string | yes | Path to compose file |
| `compose.services` | list | yes | Compose services with name, build context or image |
| `containerfiles` | list | yes | Containerfiles with package, path, base image, stages |
| `routes` | list | yes | Ingress/Route definitions with TLS config |
| `env_vars` | list | yes | All environment variables with source and secret flag |
| `dependencies` | list | yes | Upstream specs/manifests with `content_hash` |

---

## 5. security-report.yaml

**Producer:** rh-qs-security
**Consumer:** rh-qs-debug-and-deploy
**Category:** Report (aggregated scan results)

Aggregates findings from the four parallel security scanners into a single report with severity categories.

### Schema

```yaml
spec_version: 1
quickstart_name: "Spending Transaction Monitor"
slug: spending-transaction-monitor
skill: rh-qs-security
created_at: "2026-07-01T17:00:00Z"

overall_status: PASS | PASS_WITH_WARNINGS | BLOCKED

scanners:
  code:
    status: PASS | FAIL
    source_file: .rhoai-qs/spending-transaction-monitor/pipeline/qs-security-code.yaml
  containers:
    status: PASS | FAIL
    source_file: .rhoai-qs/spending-transaction-monitor/pipeline/qs-security-containers.yaml
  helm:
    status: PASS | FAIL
    source_file: .rhoai-qs/spending-transaction-monitor/pipeline/qs-security-helm.yaml
  dependencies:
    status: PASS | FAIL
    source_file: .rhoai-qs/spending-transaction-monitor/pipeline/qs-security-deps.yaml

findings:
  - id: sec-1
    severity: CRITICAL | HIGH | MEDIUM | LOW
    scanner: code | containers | helm | dependencies
    description: "Hardcoded database password in packages/api/src/config.py"
    file: packages/api/src/config.py
    line: 42
    remediation: "Move to Kubernetes Secret, reference via env var"
    status: FIXED | OPEN | ACCEPTED
    fix_attempt: 1

summary:
  critical: 0
  high: 0
  medium: 2
  low: 3
  fixed_during_scan: 1

dependencies:
  - spec: deploy-manifest.yaml
    fields_used: [helm, containerfiles, env_vars]
    content_hash: "sha256:..."
```

### Required fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `overall_status` | enum | yes | `PASS`, `PASS_WITH_WARNINGS`, or `BLOCKED` |
| `scanners` | map | yes | Per-scanner status with source file reference |
| `scanners.<name>.status` | enum | yes | `PASS` or `FAIL` |
| `scanners.<name>.source_file` | string | yes | Path to the individual scanner's output |
| `findings` | list | yes | All findings (may be empty if none) |
| `findings[].severity` | enum | yes | `CRITICAL`, `HIGH`, `MEDIUM`, or `LOW` |
| `findings[].scanner` | enum | yes | Which scanner found this |
| `findings[].status` | enum | yes | `FIXED`, `OPEN`, or `ACCEPTED` (user accepted the risk) |
| `summary` | map | yes | Count of findings by severity |
| `dependencies` | list | yes | Upstream specs/manifests with `content_hash` |

---

## 6. deploy-state.yaml

**Producer:** rh-qs-debug-and-deploy
**Consumer:** rh-qs-document
**Category:** State (cluster health snapshot)

Captures the final state of all deployed resources after the debug loop completes.

### Schema

```yaml
spec_version: 1
quickstart_name: "Spending Transaction Monitor"
slug: spending-transaction-monitor
skill: rh-qs-debug-and-deploy
created_at: "2026-07-01T18:00:00Z"

cluster:
  namespace: spending-transaction-monitor
  api_server: "https://api.cluster.example.com:6443"

overall_status: HEALTHY | DEGRADED | FAILED

# Top-level shortcut lists — main agent reads these first without parsing full resources
unhealthy_resources: [api]
healthy_resources: [llm-service, pgvector, ui]

resources:
  - kind: Deployment
    name: api
    namespace: spending-transaction-monitor
    status: HEALTHY | UNHEALTHY | PENDING
    replicas:
      desired: 1
      ready: 1
    conditions:
      - type: Available
        status: "True"
  - kind: Deployment
    name: llm-service
    namespace: spending-transaction-monitor
    status: HEALTHY
    replicas:
      desired: 1
      ready: 1
    conditions:
      - type: Available
        status: "True"
  - kind: Route
    name: api
    namespace: spending-transaction-monitor
    status: HEALTHY
    url: "https://api-spending-transaction-monitor.apps.cluster.example.com"

missing_resources:
  - name: monitoring
    kind: Deployment
    note: "Optional — not deployed because PRD did not require observability"

debug_history:
  - resource: api
    attempts: 2
    root_cause: "Missing PGVECTOR_URL env var in deployment"
    root_cause_category: config
    fix_applied: "Added env var from Kubernetes Secret"
    fix_files:
      - deploy/helm/values-api.yaml
    resolved: true
  - resource: llm-service
    attempts: 0
    resolved: true

e2e_results:
  test_plan: TEST-PLAN.md
  status: PASS | PARTIAL | FAIL
  tests_run: 5
  tests_passed: 5
  tests_failed: 0
  tests:
    - name: "pgvector connectivity"
      command: "oc exec deploy/api -n spending-transaction-monitor -- pg_isready -h pgvector"
      expected: "accepting connections"
      actual: "pgvector:5432 - accepting connections"
      status: pass
    - name: "API health endpoint"
      command: "curl -sk https://api-spending-transaction-monitor.apps.cluster.example.com/api/v1/health"
      expected: "HTTP 200"
      actual: "HTTP 200"
      status: pass

dependencies:
  - spec: security-report.yaml
    fields_used: [overall_status, findings]
    content_hash: "sha256:..."
  - spec: deploy-manifest.yaml
    fields_used: [helm, routes, env_vars]
    content_hash: "sha256:..."
```

### Required fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `cluster.namespace` | string | yes | OpenShift namespace used for deployment |
| `overall_status` | enum | yes | `HEALTHY`, `DEGRADED`, or `FAILED` |
| `unhealthy_resources` | list of strings | yes | Resource names with `UNHEALTHY` or `PENDING` status — top-level shortcut so the main agent can read the actionable list first |
| `healthy_resources` | list of strings | yes | Resource names with `HEALTHY` status |
| `resources` | list | yes | Every deployed resource with kind, name, status, and details |
| `resources[].kind` | string | yes | Kubernetes resource kind |
| `resources[].name` | string | yes | Resource name |
| `resources[].status` | enum | yes | `HEALTHY`, `UNHEALTHY`, or `PENDING` |
| `missing_resources` | list | no | Resources expected from `deploy-manifest.yaml` but not found on the cluster |
| `debug_history` | list | yes | Per-resource debug attempts (empty list if no debugging needed) |
| `debug_history[].attempts` | integer | yes | Number of debug iterations (0 if healthy on first scan) |
| `debug_history[].root_cause_category` | enum | no | `security-context`, `storage`, `networking`, `config`, `image`, `dependency`, `resource-limits`, `other` |
| `debug_history[].resolved` | boolean | yes | Whether the resource is now healthy |
| `e2e_results` | map | yes | End-to-end test results from TEST-PLAN.md |
| `e2e_results.status` | enum | yes | `PASS`, `PARTIAL`, or `FAIL` |
| `e2e_results.tests` | list | yes | Per-test detail with command, expected, actual, and status |
| `dependencies` | list | yes | Upstream specs/manifests with `content_hash` |

---

## 7. doc-manifest.yaml

**Producer:** rh-qs-document
**Consumer:** rh-qs-ship
**Category:** Manifest (records documentation artifacts)

Lists all documentation files produced and their validation status.

### Schema

```yaml
spec_version: 1
quickstart_name: "Spending Transaction Monitor"
slug: spending-transaction-monitor
skill: rh-qs-document
created_at: "2026-07-01T19:00:00Z"

documentation:
  readme:
    path: README.md
    sections:
      - name: Overview
        status: complete
      - name: Architecture
        status: complete
        diagram_source: architecture-spec.yaml
      - name: Prerequisites
        status: complete
      - name: Quick Start
        status: complete
      - name: Configuration
        status: complete
      - name: API Reference
        status: complete
        source: implementation-manifest.yaml
      - name: Deployment
        status: complete

  additional_files:
    - path: TEST-PLAN.md
      description: "End-to-end test plan for cluster verification"
      status: complete
    - path: CONTRIBUTING.md
      description: "Contribution guidelines"
      status: complete

validation:
  all_make_targets_exist: true
  all_urls_well_formed: true
  diagram_matches_components: true
  user_approved: true

dependencies:
  - spec: deploy-state.yaml
    fields_used: [overall_status, resources, e2e_results]
    content_hash: "sha256:..."
  - spec: implementation-manifest.yaml
    fields_used: [packages]
    content_hash: "sha256:..."
  - spec: architecture-spec.yaml
    fields_used: [components, architecture_diagram_path]
    content_hash: "sha256:..."
  - spec: security-report.yaml
    fields_used: [overall_status, summary]
    content_hash: "sha256:..."
```

### Required fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `documentation.readme.path` | string | yes | Path to README file |
| `documentation.readme.sections` | list | yes | README sections with status |
| `documentation.readme.sections[].name` | string | yes | Section name |
| `documentation.readme.sections[].status` | enum | yes | `complete`, `draft`, or `missing` |
| `documentation.additional_files` | list | no | Other docs produced (TEST-PLAN.md, CONTRIBUTING.md, etc.) |
| `validation` | map | yes | Documentation validation checks |
| `validation.all_make_targets_exist` | boolean | yes | Every `make` target in README exists in Makefile |
| `validation.all_urls_well_formed` | boolean | yes | All URLs are syntactically valid |
| `validation.diagram_matches_components` | boolean | yes | Architecture diagram matches component list |
| `validation.user_approved` | boolean | yes | User reviewed and approved the documentation |
| `dependencies` | list | yes | Upstream specs/manifests with `content_hash` |

---

## Schema Evolution

When a handoff file's schema changes (new required fields, renamed fields, removed fields):

1. Bump `spec_version` in that file's schema definition above
2. Update the consuming skill to handle the new version
3. Add a note in this document under the affected file's section

Consuming skills must check `spec_version` on read and fail with a clear error if they encounter a version they don't support. See [spec-as-contract.md](spec-as-contract.md) for the full versioning convention.

## Relationship to Other Foundation Docs

- **[spec-as-contract.md](spec-as-contract.md)** — defines the common spec format; `architecture-spec.yaml` (file #1) uses a simplified architect-specific schema documented in section 1 above and in `core/skills/rh-qs-architect/references/architecture-spec-template.yaml`
- **[pipeline-convention.md](pipeline-convention.md)** — defines the `.rhoai-qs/<slug>/pipeline/` directory where all these files live
- **[skill-directory-structure.md](skill-directory-structure.md)** — each skill's `spec-template.md` defines skill-specific fields within these schemas
- **[acceptance-criteria.md](acceptance-criteria.md)** — defines how `acceptance_criteria` sections in specs are validated
- **[validation-skill-template.md](validation-skill-template.md)** — how `<slug>` is resolved before any of these files are read or written
