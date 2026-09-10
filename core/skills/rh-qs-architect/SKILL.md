---
name: rh-qs-architect
description: Architecture phase for AI Quickstarts. Reads the PRD, maps requirements to OpenShift AI 3.4 and ai-architecture-charts, presents a bill of materials, generates a Mermaid diagram, and produces a design document. Use when a PRD exists under .rhoai-qs/<slug>/prds/.
---

# rh-qs-architect

**Category:** `architecture/`  

## Trigger

PRD exists from `rh-qs-discovery` at `.rhoai-qs/<slug>/prds/prd.md`

## What it does

0. Resolves which quickstart this session is for (see Phase 0 in Workflow) before touching any files
1. Reads the PRD and extracts structured features (**prd-feature-extractor** subagent)
2. If `decision_points` exist — presents them to the user, refines `input_features` based on answers
3. Selects **ai-architecture-charts** components (**chart-selector** subagent)
4. Maps refined features to **Red Hat OpenShift AI 3.4** features
5. Presents a clear **bill of materials**, e.g.:
   > I will create: React frontend, FastAPI backend, PostgreSQL with pgvector, Llama Stack for orchestration, llm-service for model serving
6. Generates a **Mermaid architecture diagram** (see [references/diagram-guide.md](./references/diagram-guide.md))
7. Documents which ai-architecture-charts will be used as Helm subchart dependencies
8. Specifies **testing strategy** (unit/integration/e2e) based on components

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
- [ ] 4. Select ai-architecture-charts (chart-selector subagent)
- [ ] 5. Map to OpenShift AI 3.4 features
- [ ] 6. Present bill of materials — get user approval
- [ ] 7. Generate Mermaid architecture diagram
- [ ] 8. Define testing strategy per component
- [ ] 9. Write design document
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

#### Step 4: Select ai-architecture-charts

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

#### Step 5: Map to OpenShift AI 3.4 features

Map the refined features and selected charts to Red Hat OpenShift AI capabilities using [references/rhoai-feature-mapping.md](./references/rhoai-feature-mapping.md). Record the mapping for the design document.

#### Step 6: Present bill of materials

Present a clear bill of materials for user approval, covering application packages, selected charts, and technology choices. Example:

> I will create: React frontend, FastAPI backend, PostgreSQL with pgvector, Llama Stack for orchestration, llm-service for model serving

**Application package matrix**

| Package | Include when |
|---------|--------------|
| `packages/api` | Always (unless pure static demo) |
| `packages/ui` | User-facing browser experience |
| `packages/db` | Persistent or relational data |
| `packages/ingestion` | RAG: documents loaded into vector store |

**Technology defaults** — present as defaults; override only when PRD requires it.

| Layer | Default |
|-------|---------|
| Frontend | React 19, TypeScript, Vite, TanStack Router/Query |
| Backend | UV, Python 3.12+, FastAPI, Pydantic v2, SQLAlchemy 2 async |
| Database | PostgreSQL |
| Vector DB | pgvector |
| LLM orchestration | Llama Stack (optional — confirm) |
| Model serving | vLLM via llm-service chart |
| Object storage | MinIO (when needed) |
| Local runtime | podman-compose |
| Monorepo | Turborepo, pnpm, uv |
| Deploy platform | Red Hat OpenShift AI 3.4 |

Do not continue until the user approves (or requests changes).

#### Step 7: Generate Mermaid architecture diagram

Generate a Mermaid architecture diagram following [references/diagram-guide.md](./references/diagram-guide.md). Include application components and selected ai-architecture-charts relationships.

#### Step 8: Define testing strategy

Define the testing strategy per component. Note which `rh-qs-test-suite` profile applies (minimal / standard / agent+evals / release train).

| Level | Tool | Scope | Runs when |
|-------|------|-------|-----------|
| Unit (Python) | pytest | Routes, schemas, services | Every PR (`pr-checks` / `ci.yaml`) |
| Unit (TypeScript) | vitest | Components, hooks | Every PR |
| Integration | pytest + Kind/compose | API + DB + in-cluster services | PR E2E workflow (`rh-qs-test-suite`) |
| E2E / LLM evals | evaluations harness | Agent quality, RAG responses | `pull_request_target` or nightly |
| Helm | helm lint + kubeconform | Exported manifests valid | Every PR |

#### Step 9: Write design document

Write `.rhoai-qs/<slug>/designs/design.md` containing:

```markdown
# <Title> — Design
## Component list (include/exclude matrix)
## ai-architecture-charts selections (with versions)
## Red Hat AI feature mapping
## Mermaid architecture diagram
## Technology decisions (defaults or overrides)
## Testing strategy per component
## Repository structure notes
```

Include the approved BOM, chart selections (with versions where known), RHOAI feature mapping, Mermaid diagram, technology decisions, testing strategy, and repository structure notes.

Get user approval of the design before done.

## References

- [ai-architecture-charts](./references/ai-architecture-charts.md)
- [OpenShift AI feature mapping](./references/rhoai-feature-mapping.md)
- [Architecture diagram guide](./references/diagram-guide.md)
- [GitHub workflow catalog](../rh-qs-test-suite/references/workflow-catalog.md)
- [subagents/validation-skill-prompt.md](./subagents/validation-skill-prompt.md) — pass by file path only, do NOT read directly
- [subagents/prd-feature-extractor-prompt.md](./subagents/prd-feature-extractor-prompt.md) — pass by file path only, do NOT read directly
- [subagents/chart-selector-prompt.md](./subagents/chart-selector-prompt.md) — pass by file path only, do NOT read directly
