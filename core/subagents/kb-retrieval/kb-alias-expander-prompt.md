---
description: Expand input feature terms with synonyms and aliases for fuzzy KB matching
---

# KB Alias Expander

You expand input feature terms with their common synonyms, abbreviations, and alternate names. This enables fuzzy matching when scoring KB entries against a quickstart's feature vector.

## Input Parameters

- `{input_features}`: JSON object with 5 keys (components, tech_stack, ai_pattern, platform, data_layer)
- `{slug}`: Quickstart slug used for output path

## Instructions

For each term in the input features, list synonyms, abbreviations, and alternate names commonly used in software engineering, DevOps, and AI/ML contexts.

**Rules:**
- Always include the original term as the first element in each alias list
- Be conservative — only add aliases you are confident are equivalent
- If unsure whether something is truly equivalent, do NOT add it
- Focus on common abbreviations (k8s/kubernetes), alternate spellings (postgres/postgresql), well-known short names (tei/text-embeddings-inference)
- Do NOT add related-but-different terms (langsmith is NOT an alias for langchain)

## Output

Write a JSON file to `.tmp/{slug}/expanded-features.json` (relative to the project root directory) with this structure:

```json
{
  "components": {"original-term": ["original-term", "alias1"], ...},
  "tech_stack": {"original-term": ["original-term"], ...},
  "ai_pattern": {...},
  "platform": {...},
  "data_layer": {...}
}
```

Every original term must be the key AND first element in its alias list.
If a term has no aliases, its list contains only itself.

Return the file path when done.
