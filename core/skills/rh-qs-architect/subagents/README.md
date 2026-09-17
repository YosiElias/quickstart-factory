# Architect Subagents

This directory contains the subagents used by `rh-qs-architect` ([../SKILL.md](../SKILL.md)). The validation-skill resolves which quickstart a session applies to, the prd-feature-extractor parses the PRD into structured features, and the chart-selector selects Helm subcharts by matching chart capabilities to those features.

## Subagent Prompts

### 1. validation-skill-prompt.md

| Field | Description |
|-------|-------------|
| **Name** | `validation-skill-prompt.md` |
| **Purpose** | Resolve which quickstart (by slug) this session applies to |
| **Input** | User's raw message, list of existing slugs under `.rhoai-qs/` (excluding `reports` and `blog-drafts`), `is_entry_point: false`, calling skill name |
| **Output** | Resolution status as JSON — resolved/needs_user_input/error, with slug and confidence |
| **When used** | Phase 0 — before reading the PRD or writing the design doc |
| **Why subagent** | Mechanical slug matching against a list, self-contained — see [validation-skill-template.md](../../../../docs/foundation/validation-skill-template.md) for the full spec |

**Output schema:**

```json
{
  "resolution": "resolved|needs_user_input|error",
  "slug": "mortgage-processor",
  "confidence": "high|medium|low",
  "confirm_with_user": false,
  "question_for_user": null,
  "error_message": null
}
```

### 2. prd-feature-extractor-prompt.md

| Field | Description |
|-------|-------------|
| **Name** | `prd-feature-extractor-prompt.md` |
| **Purpose** | Extract structured `input_features` from a PRD for chart selection and architecture mapping |
| **Input** | `slug` — the quickstart slug (PRD path derived as `.rhoai-qs/{slug}/prds/prd.md`) |
| **Output** | JSON with `input_features` (5-key schema), `deployment_questions`, and `decision_points` |
| **When used** | Step 2 — after slug resolution, before chart selection |
| **Why subagent** | Pure extraction/classification task, self-contained — keeps the main agent's context free for orchestration and design decisions |

**Output schema:**

```json
{
  "input_features": {
    "components": [],
    "tech_stack": [],
    "ai_pattern": [],
    "platform": [],
    "data_layer": []
  },
  "deployment_questions": [],
  "decision_points": []
}
```

The subagent also writes this data to `.rhoai-qs/{slug}/pipeline/prd-features.yaml`. If the main agent refines `input_features` after resolving decision points with the user, it updates that file directly.

### 3. chart-selector-prompt.md

| Field | Description |
|-------|-------------|
| **Name** | `chart-selector-prompt.md` |
| **Purpose** | Select ai-architecture-charts by matching each chart's capabilities to extracted features and deployment questions |
| **Input** | `input_features` (5-key object), `deployment_questions`, `slug` (for PRD fallback), `charts_reference_path` |
| **Output** | JSON with `charts` array — each entry has `name` and `reason` |
| **When used** | Step 4 — after features are extracted and decision points resolved |
| **Why subagent** | Capability-based selection against the charts reference, self-contained — isolates chart selection from the main agent |

**Output schema:**

```json
{
  "charts": [
    {"name": "ogx-ai", "reason": "Needs agent orchestration and multi-provider LLM access"}
  ]
}
```

## Important Notes

**DO NOT read subagent prompt files directly.** Pass them by file path to the Agent tool — see [../SKILL.md](../SKILL.md) for spawn blocks.

Unlike `rh-qs-discovery`, `rh-qs-architect` is never the pipeline's entry point, so `is_entry_point` is always `false`: if zero slugs exist under `.rhoai-qs/`, that's an error state (the user must run `rh-qs-discovery` first), not a signal to start something new.
