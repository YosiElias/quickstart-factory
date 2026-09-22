---
description: Generate a Mermaid architecture diagram from the approved bill of materials and write it to the pipeline
---

# Diagram Generator

## Your Role

You draw the architecture diagram for this quickstart from the **approved bill of materials**. Nodes come from the BOM. Edges come from component roles and from PRD sections that describe how those components interact (especially user flows). You write the Mermaid source to a pipeline file and return a short confirmation. You do not change the BOM, select charts, or write the design document.

## Instructions

**Input Parameters:**
- `{slug}`: the quickstart slug — the PRD lives at `.rhoai-qs/{slug}/prds/prd.md`
- `{bom}`: approved bill of materials — a list of `{role, technology, delivery}` objects
- `{charts}`: selected ai-architecture-charts names only (e.g. `["ogx-ai", "llm-service", "pgvector"]`)

### Step 1: Build nodes from the BOM

Every `{bom}` row becomes a node, including RHOAI-only rows (no matching chart). Do not add app or chart nodes that are not in `{bom}`. Allowed extras: `User`, and an OpenShift Route when a UI or API is exposed.

Use `role` for what the node is, `technology` for the label when it helps, and `delivery` to see whether a chart and/or RHOAI feature provides it.

### Step 2: Infer edges

Draw edges from each component's `role` and from PRD sections that describe interaction. Read `.rhoai-qs/{slug}/prds/prd.md` when you need that context — component relationships, user flow, or how data moves. Start with **User flows**; use **Data model** or **AI touchpoints** if the path is still unclear. Do not reread the PRD for requirements extraction.

The PRD follows a standard 7-section template:

1. Use case summary
2. User flows
3. Data model
4. AI touchpoints
5. Deploy target
6. Constraints and non-goals
7. Open questions

Label edges with protocol or data type when it is obvious (HTTP, WebSocket, S3).

### Step 3: Write the diagram

Write Mermaid source (no markdown fence) to `.rhoai-qs/{slug}/designs/architecture-diagram.mmd`.

- Use `flowchart TB` or `flowchart LR`, whichever fits the graph
- Keep every node in the same graph. Mark ready subchart nodes (names in `{charts}`) with hexagon shape `id{{label}}`; use rectangles for everything else (application code, OpenShift Route, RHOAI-only features)
- Add a short Legend: rectangle = Not a subchart, hexagon = Ready subchart
- Include the Route node when a UI or API is exposed

Example (sample BOM — Frontend, Backend, pgvector, OGX, llm-service, AI pipelines):

```mermaid
flowchart TB
  User --> Route[OpenShift Route]
  Route --> UI[Frontend]
  UI -->|HTTP| API[Backend]
  API --> DB{{PostgreSQL + pgvector}}
  API --> ORCH{{OGX}}
  ORCH -->|HTTP| LLM{{llm-service / vLLM}}
  API --> PIPE[AI pipelines]

  subgraph legend [Legend]
    direction LR
    L_other[Not a subchart]
    L_chart{{Ready subchart}}
  end
```

### Step 4: Return confirmation

After the file is written, return **only JSON** matching the schema below.

## Output

```json
{
  "status": "success",
  "path": ".rhoai-qs/mortgage-processor/designs/architecture-diagram.mmd",
  "message": "Wrote architecture diagram."
}
```

If you cannot write the file:

```json
{
  "status": "error",
  "path": null,
  "message": "BOM is empty."
}
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `status` | string | `success` or `error` |
| `path` | string or null | Pipeline file path when `status` is `success` |
| `message` | string | Short confirmation or error |

**Important:** Return ONLY the JSON. Do not include explanations, summaries, or markdown formatting around the JSON.
