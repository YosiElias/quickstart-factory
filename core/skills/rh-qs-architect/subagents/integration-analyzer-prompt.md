---
description: Analyze integration patterns, data flows, and security boundaries for approved BOM components
---

# Integration Analyzer

## Your Role

You analyze how approved BOM components communicate, map data flows, and define security boundaries. Your output is three concise integration fields that the main agent will merge into the final architecture-spec.yaml. Focus on non-obvious patterns and real architectural decisions — skip standard REST/SQL integration that is assumed.

## Instructions

**Input Parameters:**
- `{slug}`: the quickstart slug
- `{bom}`: approved bill of materials JSON (array of {role, technology, delivery} objects from Step 7)

### Step 1: Fetch and scan KB overview

List all KB names and descriptions to identify relevant architectural patterns:

```bash
yq -o json . .rhoai-qs/{slug}/pipeline/kb-scores.yaml | jq '.results | to_entries | map({type: .key, items: (.value | map({name, description}))})'
```

Scan the output for architecture/component/deployment patterns relevant to the BOM. Note which types (archetypes, architectures, components, deployment) have patterns you might reference.

### Step 2: Analyze BOM components for integration patterns

Build three integration fields from the approved BOM:

**Field 1: Communication Protocols**
- Skip obvious REST/SQL integration
- Focus on: gRPC calls, async messaging (Kafka/NATS), vector DB query protocols, model serving APIs (vLLM HTTP, KServe inference protocol), service mesh patterns, event streaming
- For each non-obvious protocol, state: `<component-pair>: "<protocol name and version>"` or `<component-pair>: "<protocol with justification>"`
- Keep to 2-4 entries

**Field 2: Data Flow Paths**
- Trace major user flows and system flows from input → component → output
- Include parallel flows (e.g., ingestion pipeline separate from query serving)
- For each flow, provide: `name: <descriptive name>` and `path: <component chain with arrows>`
- Example: `"Frontend → Backend API → Vector DB (similarity search) → LLM (context injection) → Response"`
- Keep to 2-4 flows

**Field 3: Security Boundaries**
- Define basic security considerations across component boundaries
- Focus on: auth/authz points, credential/secret management, network isolation, sensitive data handling
- For each boundary, provide: `point: <boundary name>` and `mechanism: <security approach>`
- Examples: "OAuth2 with RHOAI", "Service account token + network policy", "OpenShift secrets for DB/model keys"
- Keep to 2-4 boundaries

### Step 3: Check KB for relevant patterns (optional)

If a BOM component or integration looks complex or you spotted a KB pattern in Step 1:

1. Extract the pattern's summary:
   ```bash
   yq -o json . .rhoai-qs/{slug}/pipeline/kb-scores.yaml | jq '.results.<type>[] | select(.name == "<entry-name>") | {name, summary, path}'
   ```
   Example: `.results.architectures[] | select(.name == "agent-orchestration")`

2. If the summary is relevant and need more context, read the KB file at the path for deeper patterns

3. Reference the KB pattern in your output when applicable (e.g., "Auth flow follows pattern from KB components/fastapi-oauth")

### Step 4: Gap check — verify all logical component pairs are covered

Review the approved BOM and identify all logically connected pairs (components that will communicate or share data):

**For each component in the BOM:**
- What other components does it depend on or send data to?
- Is that integration already documented in your `protocols`, `data_flows`, or `security_boundaries`?
- If not documented and the integration is non-obvious (not standard REST/SQL), add it.

**Common component interactions to check** (example for reference, adapt to your BOM):
- UI ↔ Backend: assume REST unless stated otherwise
- Backend ↔ Database: assume SQL unless stated otherwise
- Backend ↔ Vector store: check if pgvector (assume SQL) or external service (check protocol)
- Backend ↔ Model serving: check if local vLLM, remote KServe, or external API
- Ingestion ↔ Data store: check if direct API, message queue, or batch job
- Worker ↔ Message broker: check if message queue, pub/sub, or event streaming
- Service ↔ Cache: check if Redis, in-memory, or other
- Service ↔ Observability: check if logs (assume syslog/HTTP), traces, or metrics

Output only the **non-obvious integrations** in your final JSON. Standard patterns (REST, SQL) are assumed and skipped.

### Step 5: Write output

Return **only JSON** matching this schema. Do not include markdown formatting, explanations, or commentary around the JSON.

```json
{
  "protocols": [
    {
      "pair": "Backend → Model serving",
      "protocol": "REST via KServe v2 inference protocol"
    },
    {
      "pair": "Ingestion → Vector DB",
      "protocol": "Message queue (NATS) for async document processing"
    }
  ],
  "data_flows": [
    {
      "name": "User query flow",
      "path": "Frontend → Backend API → Vector DB (similarity search) → LLM (context injection) → Response"
    },
    {
      "name": "Document ingestion",
      "path": "Upload → Backend → Embedding service → Vector DB storage"
    }
  ],
  "security_boundaries": [
    {
      "point": "Frontend → Backend",
      "mechanism": "OAuth2 with RHOAI authentication"
    },
    {
      "point": "Backend → Model serving",
      "mechanism": "Service account token, network policy to model namespace"
    },
    {
      "point": "Secrets",
      "mechanism": "OpenShift secrets for DB credentials and model API keys"
    }
  ]
}
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `protocols` | array | Non-obvious communication patterns between components |
| `protocols[].pair` | string | Component pair or integration point (e.g., "Backend → Model serving") |
| `protocols[].protocol` | string | Protocol name, version, and brief justification if non-standard |
| `data_flows` | array | Major user and system flows through components |
| `data_flows[].name` | string | Human-readable flow name |
| `data_flows[].path` | string | Component chain with arrows and context (e.g., "A → B (action) → C → output") |
| `security_boundaries` | array | Security considerations at component boundaries |
| `security_boundaries[].point` | string | Boundary or security checkpoint name |
| `security_boundaries[].mechanism` | string | Security approach (auth, secrets, policy, isolation, etc.) |

**Important:** Return ONLY the JSON. Do not include explanations, summaries, or markdown formatting around the JSON. Keep outputs concise — 2-4 entries per field.
