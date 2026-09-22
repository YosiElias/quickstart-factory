---
name: rh-qs-architect
description: Architecture phase for AI Quickstarts. Reads the PRD, maps requirements to OpenShift AI and ai-architecture-charts, presents a bill of materials, generates a Mermaid diagram, and produces an architecture spec. Use when a PRD exists under .rhoai-qs/<slug>/prds/.
---

# rh-qs-architect

**Category:** `architecture/`  

## Trigger

PRD exists from `rh-qs-discovery` at `.rhoai-qs/<slug>/prds/prd.md`

## What it does

0. Resolves which quickstart this session is for (see Phase 0 in Workflow) before touching any files
1. Reads the PRD and extracts structured features (**prd-feature-extractor** subagent)
2. If `decision_points` exist — presents them to the user, refines `input_features` based on answers
3. Applies **technology defaults** (override only when the PRD requires it)
4. Selects **ai-architecture-charts** components (**chart-selector** subagent)
5. Maps leftover PRD features (no matching chart) to **OpenShift AI** features
6. Presents a **bill of materials** for user approval (`{role, technology, delivery}` per component)
7. Defines **integration patterns and data flow** (**integration-analyzer** subagent — protocols, data flows, security boundaries with KB grounding)
8. Generates a **Mermaid architecture diagram** (**diagram-generator** subagent)
9. Specifies **testing strategy** (levels and scope) based on components
10. Writes **architecture-spec.yaml** with all architecture decisions and component details

## Workflow

### Phase 0: Resolve Quickstart Context

Before reading any files, resolve which quickstart this session is for. Run `ls .rhoai-qs/ 2>/dev/null` (excluding `reports` and `blog-drafts`) and spawn the **validation-skill subagent**:

```python
Agent(
    description="Resolve which quickstart this architecture session is for",
    prompt=f"""
Read and follow instructions from:
core/skills/rh-qs-architect/subagents/validation-skill-prompt.md

User message: {user_message}
Existing slugs: {existing_slugs}
Is entry point: false
Calling skill: rh-qs-architect
"""
)
```

Handle the result per [validation-skill-template.md](../../../docs/foundation/validation-skill-template.md#main-agent-handling). If `resolution: error` (no slugs exist), tell the user to run `rh-qs-discovery` first and stop.

### Remaining phases

```
- [ ] 1. Read PRD from .rhoai-qs/<slug>/prds/prd.md
- [ ] 2. Extract features from PRD (prd-feature-extractor subagent)
- [ ] 3. If decision_points exist → present to user, refine input_features if needed
- [ ] 4. Apply technology defaults
- [ ] 5. Select ai-architecture-charts (chart-selector subagent)
- [ ] 6. Map to OpenShift AI features
- [ ] 7. Present bill of materials — get user approval
- [ ] 8. Define integration patterns and data flow
- [ ] 9. Generate Mermaid architecture diagram
- [ ] 10. Define testing strategy per component
- [ ] 11. Write architecture spec
```

#### Step 1: Read PRD

Read the PRD at `.rhoai-qs/<slug>/prds/prd.md`. Use it as the source of truth for later steps; do not modify it.

#### Step 2: Extract PRD features

Spawn the **prd-feature-extractor** subagent to parse the PRD and produce structured `input_features`:

```python
Agent(
    description="Extract structured features from PRD",
    prompt=f"""
Read and follow instructions from:
core/skills/rh-qs-architect/subagents/prd-feature-extractor-prompt.md

slug: {slug}
"""
)
```

The subagent writes `input_features`, `deployment_questions`, and `decision_points` to `.rhoai-qs/{slug}/pipeline/prd-features.yaml` and returns the same data as JSON.

#### Step 3: Resolve decision points

If `decision_points` is non-empty, present each to the user. Update `.rhoai-qs/{slug}/pipeline/prd-features.yaml` with any refined `input_features` (and related fields) before proceeding. If empty, continue.

#### Step 4: Apply technology defaults

**Technology defaults** — present as defaults; override only when PRD requires it.

| Layer | Default |
|-------|---------|
| Frontend | React 19, TypeScript, Vite, TanStack Router/Query |
| Backend | UV, Python 3.12+, FastAPI, Pydantic v2, SQLAlchemy 2 async |
| Database | PostgreSQL |
| Vector DB | pgvector (`pgvector` chart) |
| LLM orchestration | Llama Stack (optional — confirm) (`llama-stack` chart) |
| Model serving | vLLM via `llm-service` chart |
| Object storage | MinIO (when needed) (`minio` chart) |
| Local runtime | podman-compose |
| Monorepo | Turborepo, pnpm, uv |
| Deploy platform | Red Hat OpenShift AI |

#### Step 5: Select ai-architecture-charts

Spawn the **chart-selector** subagent with the refined features:

```python
Agent(
    description="Select ai-architecture-charts for this quickstart",
    prompt=f"""
Read and follow instructions from:
core/skills/rh-qs-architect/subagents/chart-selector-prompt.md

input_features: {input_features}
deployment_questions: {deployment_questions}
slug: {slug}
charts_reference_path: core/skills/rh-qs-architect/references/ai-architecture-charts.md
"""
)
```

#### Step 6: Map leftover features to OpenShift AI

Prefer the charts selected in Step 5. For each refined PRD feature:

1. If it already matches a selected chart, stop — that feature is covered.
2. If no chart matches, look it up in [references/rhoai-feature-mapping.md](./references/rhoai-feature-mapping.md) and note which OpenShift AI capability applies, if any.

Keep those OpenShift AI notes for the design document (Step 11, **Red Hat AI feature mapping**). For capabilities not listed in the table, or for more detail, use the documentation hub linked from that file.

#### Step 7: Present bill of materials

Present a structured bill of materials for user approval. One object per component:

- `role`: what it is for
- `technology`: the stack or runtime you build it with (not the chart or RHOAI feature name)
- `delivery`: the chart and/or RHOAI feature that delivers it (`application` when the quickstart's own code provides it)

```json
[
  {"role": "Frontend", "technology": "React", "delivery": "application"},
  {"role": "Backend", "technology": "FastAPI", "delivery": "application"},
  {"role": "Vector store", "technology": "PostgreSQL with pgvector", "delivery": "pgvector chart"},
  {"role": "Orchestration", "technology": "OGX", "delivery": "ogx-ai chart"},
  {"role": "Model serving", "technology": "vLLM", "delivery": "llm-service chart, RHOAI Model serving / KServe"},
  {"role": "Scheduled ingestion", "technology": "KFP 2.0", "delivery": "RHOAI AI pipelines"}
]
```

Do not continue until the user approves (or requests changes). Keep the approved list as `{bom}` for Step 9.

#### Step 8: Define integration patterns and data flow

Spawn the **integration-analyzer** subagent to analyze how BOM components communicate, map data flows, and define security considerations:

```python
Agent(
    description="Analyze integration patterns for {slug}",
    prompt=f"""
Read and follow instructions from:
core/skills/rh-qs-architect/subagents/integration-analyzer-prompt.md

slug: {slug}
bom: {bom}
"""
)
```

The subagent analyzes three integration fields and returns JSON:
- `protocols` — non-obvious communication patterns (skip REST/SQL)
- `data_flows` — user and system flows through components
- `security_boundaries` — auth, secrets, network policy considerations

Store the returned JSON as `{integration_patterns}` in context for Step 11.

#### Step 9: Generate Mermaid architecture diagram

Pass the approved `{bom}` from Step 7, the selected chart names from Step 5, and integration patterns from Step 8 to the **diagram-generator** subagent:

```python
Agent(
    description="Generate Mermaid architecture diagram",
    prompt=f"""
Read and follow instructions from:
core/skills/rh-qs-architect/subagents/diagram-generator-prompt.md

slug: {slug}
bom: {bom}
charts: {chart_names}
integration_patterns: {integration_patterns}
"""
)
```

The subagent writes `.rhoai-qs/{slug}/designs/architecture-diagram.mmd` and returns a short status JSON. If `status` is not `success`, report `message` and stop. Use that file in Step 11.

#### Step 10: Define testing strategy

Define the testing strategy per component. Note which `rh-qs-test-suite` profile applies (minimal / standard / agent+evals / release train).

| Level | Scope | Runs when |
|-------|-------|-----------|
| Unit (Python) | Routes, schemas, services | Every PR (`pr-checks` / `ci.yaml`) |
| Unit (TypeScript) | Components, hooks | Every PR |
| Integration | API + DB + in-cluster services | PR E2E workflow (`rh-qs-test-suite`) |
| E2E / LLM evals | Agent quality, RAG responses | `pull_request_target` or nightly |
| Helm | Exported manifests valid | Every PR |

#### Step 11: Write architecture spec

Write `.rhoai-qs/<slug>/designs/architecture-spec.yaml` following the template in [references/architecture-spec-template.yaml](./references/architecture-spec-template.yaml).

Include:
- **Header:** spec_version, quickstart_name, slug, skill, created_at
- **Technology Stack:** Full stack listing (frontend, backend, database, vector_db, model_serving, etc.)
- **Components:** Approved BOM with nested details per component (type, role, technology, delivery, chart config, rhoai_features, constraints, kb_sources with match_reason, dependencies)
- **Integration & Data Flow:** Pull from `{integration_patterns}` (protocols, data_flows, security_boundaries) returned by Step 8
- **Architecture Diagram:** Reference to `.rhoai-qs/{slug}/designs/architecture-diagram.mmd`
- **Testing Strategy:** Levels and scope
- **Dependencies:** Reference to prd.md, prd-features.yaml, and kb-scores.yaml with content_hash

Get user approval of the architecture spec before done.

## References

- [ai-architecture-charts](./references/ai-architecture-charts.md)
- [OpenShift AI feature mapping](./references/rhoai-feature-mapping.md)
- [GitHub workflow catalog](../rh-qs-test-suite/references/workflow-catalog.md)
- [subagents/validation-skill-prompt.md](./subagents/validation-skill-prompt.md) — pass by file path only, do NOT read directly
- [subagents/prd-feature-extractor-prompt.md](./subagents/prd-feature-extractor-prompt.md) — pass by file path only, do NOT read directly
- [subagents/chart-selector-prompt.md](./subagents/chart-selector-prompt.md) — pass by file path only, do NOT read directly
- [subagents/integration-analyzer-prompt.md](./subagents/integration-analyzer-prompt.md) — pass by file path only, do NOT read directly
- [subagents/diagram-generator-prompt.md](./subagents/diagram-generator-prompt.md) — pass by file path only, do NOT read directly

## Pipeline checkpoint

Run the checkpoint:

```bash
python3 core/flow/pipeline-checkpoint.py --skill-name rh-qs-architect --qs-name {qs-name}
```
Print the dashboard link to the user:
"Pipeline dashboard updated — track progress at [dashboard.md](.rhoai-qs/{qs-name}/flow/dashboard.md)"
