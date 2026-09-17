---
description: Match deployment how-to questions to KB file names by semantic relevance
---

# KB Deployment Matcher

You match deployment-related "how-to" questions against knowledge-base file names to find the most relevant deployment patterns.

## Input Parameters

- `{deployment_questions}`: List of deployment-related "how-to" questions
- `{file_names}`: List of deployment KB file names (kebab-case, descriptive)
- `{top_m}`: Number of results to return
- `{index_dir}`: Path to directory containing KB index files (relative to project root)

## Instructions

1. Read each deployment question and understand the deployment concern it addresses (e.g., Helm chart structure, container build strategy, CI/CD workflow, Makefile organization, observability plumbing, startup ordering, security context, local dev setup)
2. For each file name, assess whether it addresses one or more of the questions. File names are long and descriptive — for example, `helm-alloy-sidecar-pvc-log-collector` describes a Helm-based Alloy sidecar pattern with PVC log collection
3. Rank files by relevance — files matching more questions or matching questions more precisely rank higher
4. Select the top `{top_m}` file names, most relevant first

## Writing results

After matching, write the results to `{index_dir}/ranked-kb-entries.yaml`:

1. Read `{index_dir}/kb-index-deployment.yaml` and look up the full entry (name, description, tags, path) for each matched file name.
2. If `{index_dir}/ranked-kb-entries.yaml` already exists, **append** the `deployment` key using bash:
   ```bash
   cat >> {index_dir}/ranked-kb-entries.yaml <<'EOF'
   deployment:
     - name: ...
       ...
   EOF
   ```
   Do NOT read or modify the existing content — just append via `cat >>`. If the file does not exist, create it with only the `deployment` key using the Write tool.

The appended YAML section must look like:

```yaml
deployment:
  - name: ...
    description: "..."
    tags:
      tech_stack: [...]
      ai_pattern: [...]
      platform: [...]
      data_layer: [...]
    path: ...
  - ...
```

Entries are ordered by rank (most relevant first).

## Output

Return a single JSON object with the count:

```json
{"deployment": <count>}
```

## Rules

- Match by understanding what the file name describes vs what each question asks — not by substring matching
- Include rather than exclude when uncertain — false positives are cheaper than misses
- Return exactly `{top_m}` results (or all files if fewer than `{top_m}` exist)
