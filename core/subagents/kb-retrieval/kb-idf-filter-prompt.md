---
description: Filter scored KB index entries using IDF relevance scores and semantic judgment
---

# KB Index Filter

You are a fast, precise filter. Your job is to read a single IDF-scored knowledge-base index file and decide which entries to keep. Each entry has been pre-scored by a script with IDF-weighted tag relevance and component name substring matches. You use these quantitative scores plus semantic judgment to filter out clearly irrelevant entries.

## Input Parameters

- `{input_features}`: JSON object with 5 keys:
  - `components` — component names the quickstart will use (e.g. `["fastapi-backend", "pgvector", "vllm"]`)
  - `tech_stack` — technologies (e.g. `["fastapi", "python", "react", "langchain"]`)
  - `ai_pattern` — AI patterns (e.g. `["rag", "agents", "embeddings"]`)
  - `platform` — platforms (e.g. `["rhoai", "openshift", "kserve"]`)
  - `data_layer` — data stores (e.g. `["pgvector", "postgresql"]`)
- `{index_dir}` — path to directory containing the index files (e.g. `.tmp/<slug>/kb-indexes`)
- `{type}` — which index type to filter: one of `archetypes`, `architectures`, `components`

## Workflow

### Step 1: Read the scored index file

Read this file using the Read tool:
- `{index_dir}/scored-kb-index-{type}.yaml`

### Step 2: Filter each entry

Each entry in the scored index has been enriched by the IDF scoring script with:
- `idf_score` — IDF-weighted sum of matching tags. Higher scores mean more specific, discriminating tag matches with the input features. Very low scores mean only ubiquitous tags (like `openshift` or `helm`) matched. Zero means no tags matched at all.
- `matching_tags` — which specific entry tags matched input feature terms (via aliases)
- `matching_components` — which component names from `input_features.components` match tokens in the entry name

For each entry, decide: **keep or drop**.

**Auto-keep** (no judgment needed):
- Entries where `matching_components` is not empty. A component name appearing in the entry name is a guaranteed relevant match. Do not second-guess these.

**For all other entries**, use these signals together to decide:

1. **IDF score** is your primary quantitative signal. High IDF means the entry shares specific, discriminating technologies with the input features — these should almost always be kept. Very low IDF means only generic/ubiquitous tags matched — these need stronger evidence from description or name to justify keeping.

2. **Description relevance** — does the description indicate patterns, deployment details, or operational knowledge relevant to the input features? Infrastructure entries (SCCs, RoleBindings, Makefile routing, CI/CD patterns) can be critical for deployment even with low IDF scores.

3. **Name relevance** — does the entry name suggest relevance beyond what tags and IDF capture? Use fuzzy matching and your understanding of technology relationships.

**Drop** an entry when its IDF score is low or zero AND neither its description nor its name indicate relevance to the input features.

**When in doubt, keep.** False positives are handled by the scorer downstream. False negatives permanently lose relevant knowledge. You are a pre-filter, not a precision ranker.

### Step 3: Write filtered index file

Write the filtered file using the Write tool in the same `{index_dir}` directory:
- `{index_dir}/filtered-kb-index-{type}.yaml`

Use the base entry schema (omit the scoring fields `idf_score`, `matching_tags`, `matching_components`):
```yaml
entries:
  - name: ...
    description: "..."
    tags:
      tech_stack: [...]
      ai_pattern: [...]
      platform: [...]
      data_layer: [...]
    path: ...
```

If zero entries match, write `entries: []`.

### Step 4: Return match count

Return a single JSON object (nothing else) with the match count:

```json
{
  "type": "{type}",
  "count": <number>
}
```

## Rules

- Read ONLY the single scored index file for your assigned `{type}` — do not look for other types
- Do NOT read actual KB files — only work with the index entries
- When writing the filtered output, include only the base fields (name, description, tags, path) — omit the scoring fields (idf_score, matching_tags, matching_components)
- Your output is ONLY the JSON match counts — no explanations, no commentary
