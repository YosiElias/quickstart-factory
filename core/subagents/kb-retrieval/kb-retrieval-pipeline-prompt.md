---
description: Orchestrate KB retrieval pipeline — alias expansion, IDF scoring, filtering, ranking, and deployment question matching
---

# KB Retrieval Pipeline

You orchestrate a multi-step process to find the most relevant knowledge-base (KB) files for a quickstart being designed. Your output is a ranked YAML file that downstream skills (like `rh-qs-architect`) use to load proven patterns from prior quickstarts.

Think like a senior engineer picking which prior projects to study before starting a new one.

## Input Parameters

- `{slug}`: Quickstart slug (e.g. `test-rag-chatbot`)
- `{input_features}`: Optional JSON object with 5 keys. When provided, drives IDF+filter+ranker retrieval for archetypes, architectures, and components.
  - `components` — component names (e.g. `["fastapi-backend", "pgvector", "vllm"]`)
  - `tech_stack` — technologies (e.g. `["fastapi", "python", "react"]`)
  - `ai_pattern` — AI patterns (e.g. `["rag", "agents", "embeddings"]`)
  - `platform` — platforms (e.g. `["rhoai", "openshift", "kserve"]`)
  - `data_layer` — data stores (e.g. `["pgvector", "postgresql"]`)
- `{top_n_overrides}`: Optional JSON to override per-type defaults (e.g. `{"components": 8}`)
- `{deployment_questions}`: Optional list of deployment-related "how-to" questions. When provided, deployment retrieval uses question-to-name matching instead of the IDF+filter+ranker pipeline.

## Workflow

Execute these 7 steps in order. At least one of `{input_features}` or `{deployment_questions}` must be provided. Steps 2–5 require `{input_features}` — skip them entirely when it is not provided. Step 5b requires `{deployment_questions}` — skip it when not provided.

### Step 0: Validate slug and clean workspace

Validate the slug is safe kebab-case, then remove stale data:

```bash
[[ "{slug}" =~ ^[a-z0-9]([a-z0-9-]*[a-z0-9])?$ ]] || { echo "ERROR: invalid slug '{slug}'"; exit 1; }
rm -rf ".tmp/{slug}/kb-indexes"
```

### Step 1: Generate indexes

Run the index generation script:

```bash
python3 core/scripts/generate-kb-index.py --output-dir ".tmp/{slug}/kb-indexes"
```

This creates 4 index files in `.tmp/{slug}/kb-indexes/`. If the script exits non-zero, stop and report the error.

### Step 2: Expand aliases

Skip this step if `{input_features}` was NOT provided.

Spawn a single alias expansion subagent to produce a synonym map for tag matching. Pass the prompt by file path — do NOT read the prompt file yourself:

```
Agent(
    description="Expand aliases for {slug}",
    model="haiku",
    prompt="""
Read and follow instructions from:
core/subagents/kb-retrieval/kb-alias-expander-prompt.md

input_features: {input_features}
slug: {slug}
"""
)
```

If the agent fails, create a fallback `.tmp/{slug}/expanded-features.json` where each term maps to `[itself]`.

After Step 2 completes, validate the JSON is parseable:

```bash
python3 -c "import json; json.load(open('.tmp/{slug}/expanded-features.json'))"
```

If validation fails, replace the file with the identity fallback.

### Step 3: Score entries with IDF

Skip this step if `{input_features}` was NOT provided.

Run the IDF scoring script:

```bash
python3 core/scripts/idf-score-kb.py --index-dir ".tmp/{slug}/kb-indexes" --features-file ".tmp/{slug}/expanded-features.json"
```

This creates 4 scored index files (`scored-kb-index-{type}.yaml`) in the same directory. Each entry is enriched with:
- `idf_score` — IDF-weighted sum of matching tags (higher = more specific matches)
- `matching_tags` — which tags matched input features
- `matching_components` — which component names match tokens in the entry name

If the script exits non-zero, stop and report the error.

### Step 4: Spawn filter subagents

Skip this step if `{input_features}` was NOT provided.

Spawn **3 filter subagents sequentially** (one per type) using a cheap model, each with `run_in_background: false` so you block until it completes before launching the next. Pass the prompt by file path — do NOT read the prompt file yourself:

```
Agent(
    description="Filter KB {type} for {slug}",
    model="haiku",
    run_in_background=false,
    prompt="""
Read and follow instructions from:
core/subagents/kb-retrieval/kb-idf-filter-prompt.md

input_features: {input_features}
index_dir: .tmp/{slug}/kb-indexes
type: {type}
"""
)
```

Where `{type}` is each of: `archetypes`, `architectures`, `components`.

Deployment is never filtered here — it is retrieved exclusively via Step 5b.

Launch them **one at a time** — wait for each to finish before starting the next.

Collect the returned JSON from each agent to get match counts per type. If all 3 return 0 matches, skip to Step 7 and write an output file with `results: {}`.

### Step 5: Rank filtered entries

Skip this step if `{input_features}` was NOT provided.

Spawn a ranking subagent to rank the filtered entries by relevance. Pass the prompt by file path — do NOT read the prompt file yourself:

```
Agent(
    description="Rank KB entries for {slug}",
    run_in_background=false,
    prompt="""
Read and follow instructions from:
core/subagents/kb-retrieval/kb-semantic-ranker-prompt.md

input_features: {input_features}
index_dir: .tmp/{slug}/kb-indexes
"""
)
```

The agent writes ranked entries to `.tmp/{slug}/kb-indexes/ranked-kb-entries.yaml`. If the agent fails, read the filtered index files directly and proceed with unranked entries.

### Step 5b: Match deployment by questions (only when deployment_questions provided)

Skip this step if `{deployment_questions}` was NOT provided.

1. Read `.tmp/{slug}/kb-indexes/kb-index-deployment.yaml` and extract all entry names into a list.

2. Determine `top_m`: use `{top_n_overrides}.deployment` if provided, otherwise default to `max(5, ceil(number_of_questions * 1.2))`.

3. Spawn a deployment matcher subagent. Pass the prompt by file path — do NOT read the prompt file yourself:

```
Agent(
    description="Match deployment KB for {slug}",
    run_in_background=false,
    prompt="""
Read and follow instructions from:
core/subagents/kb-retrieval/kb-deployment-matcher-prompt.md

deployment_questions: {deployment_questions}
file_names: [<comma-separated list of all deployment entry names>]
top_m: <top_m>
index_dir: .tmp/{slug}/kb-indexes
"""
)
```

The subagent writes matched entries directly to `.tmp/{slug}/kb-indexes/ranked-kb-entries.yaml` (appending if the file already exists from Step 5, creating it otherwise).

### Step 6: Select top-N and extract summaries

Run the top-N selection script:

```bash
python3 core/scripts/select-top-kb.py \
    --ranked-file ".tmp/{slug}/kb-indexes/ranked-kb-entries.yaml" \
    --output-file ".tmp/{slug}/kb-indexes/top-kb-entries.yaml"
```

If `{input_features}` was provided (Steps 2–5 ran), add: `--features-file ".tmp/{slug}/expanded-features.json"`

If `{deployment_questions}` was provided, add: `--deployment-questions-count <number of questions>`

If `{top_n_overrides}` is provided, add: `--top-n-overrides '{top_n_overrides}'`

This selects the top-N entries per type (defaults: archetypes=2, architectures=3, components=max(5, ceil(component_count*1.2)), deployment=max(5, ceil(question_count*1.2))), extracts summaries, and writes the result. If the script exits non-zero, stop and report the error.

### Step 7: Write output

Read the top-N results from `.tmp/{slug}/kb-indexes/top-kb-entries.yaml`.

Create the output directory and file:

```bash
mkdir -p ".rhoai-qs/{slug}/pipeline"
```

Write the file `.rhoai-qs/{slug}/pipeline/kb-scores.yaml` with this structure:

```yaml
knowledge_base_root: core/skills/qs-extract-knowledge/knowledge-base
generated_at: "<current ISO timestamp>"
input_features:          # include ONLY if {input_features} was provided
  components: [...]
  tech_stack: [...]
  ai_pattern: [...]
  platform: [...]
  data_layer: [...]
deployment_questions_count: <N>  # include ONLY if {deployment_questions} was provided
top_n:                   # only keys for types that were actually queried
  archetypes: <N used>
  architectures: <N used>
  components: <N used>
  deployment: <N used>
results:                 # only types that have results; omit types with zero entries
  archetypes:
    - path: archetypes/rag-chatbot.md
      name: rag-chatbot
      description: "..."
      summary: "..."
      match_reason: "..."
  architectures: [...]
  components: [...]
  deployment: [...]
```

Each result entry has:
- `path` — relative to KB root (e.g. `components/fastapi-backend.md`)
- `name` — from the index entry
- `description` — from the index entry
- `summary` — from the extract-summaries output
- `match_reason` — a single sentence explaining relevance. When driven by `input_features`, reference matching features (e.g. "Covers FastAPI backend with pgvector, matching 3 requested components"). When driven by `deployment_questions`, reference question numbers (e.g. "Addresses Q4 (Grafana alerting) and Q1 (Loki wiring)").

## Edge Cases

- **Index script fails** → stop and report the error, do not continue
- **Filter returns 0 total matches** → write output with `results: {}`
- **Pipeline directory missing** → create it with `mkdir -p`
- **A type has fewer candidates than N** → include all candidates for that type
- **Summary extraction fails for a file** → use empty string for summary, note in match_reason

## Rules

- Do NOT read the subagent prompt files — pass them by path only
- Do NOT read full KB files — use only index data and the extract-summaries script
- Do NOT modify any KB files or index files (only create the filtered indexes via the filter subagent)
- Write ONLY the `kb-scores.yaml` output file — no other files
- The `match_reason` must reference specific input features or deployment question numbers that matched — no generic statements
