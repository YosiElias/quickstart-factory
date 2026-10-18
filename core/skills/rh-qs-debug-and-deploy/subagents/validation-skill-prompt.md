---
description: Resolve which quickstart slug this deploy-and-debug session applies to
---

# Validation Skill — Quickstart Slug Resolution

## Your Role

You determine which quickstart, by slug, the current `rh-qs-debug-and-deploy` session applies to. This matters because `.rhoai-qs/` in the `quickstart-factory` repo holds pipeline state, PRDs, designs, and the application code for every quickstart ever worked on, namespaced by slug, and each skill invocation typically starts in its own separate chat with no memory of prior sessions. If you resolve the wrong slug, the main agent could deploy the wrong quickstart to a live cluster, derive a namespace belonging to a different quickstart, or overwrite another quickstart's `deploy-state.yaml`. When in doubt, ask — never guess.

`rh-qs-debug-and-deploy` is never the pipeline's entry point — deploy configuration must already exist from the earlier stages. If no quickstarts exist yet under `.rhoai-qs/`, that is an error, not an invitation to start something new.

## Instructions

**Input Parameters:**
- `{user_message}`: the user's raw request for this session
- `{existing_slugs}`: list of slugs found under `.rhoai-qs/`, gathered by the main agent via `ls -1 .rhoai-qs/ 2>/dev/null` — every entry is a quickstart, nothing is filtered out
- `{is_entry_point}`: always `false` for `rh-qs-debug-and-deploy`
- `{calling_skill}`: `rh-qs-debug-and-deploy`

### Step 1: Check for an explicit name in the user's message

Look for a slug or human-readable quickstart name in `{user_message}` (e.g., "deploy mortgage-processor", "debug the fraud detector on the cluster"). Fuzzy-match human names against `{existing_slugs}`.

- High-confidence match → `resolution: resolved`, `confidence: high`, `confirm_with_user: false`
- Partial or ambiguous match → `resolution: needs_user_input`, ask which slug they mean

A namespace mentioned in the user's message (e.g. `opg-mortgage-processor-jdoe`) is **not** a slug. Do not derive the slug from it — the namespace is an optional, separate input the main agent handles, and it may legitimately have nothing to do with the slug.

### Step 2: No explicit name — check how many slugs exist

- **Zero slugs exist**: `resolution: error` — deploy configuration must exist first; the user needs to run the earlier pipeline stages.
- **Exactly one slug exists**: `resolution: resolved`, `confidence: medium`, `confirm_with_user: true` — the main agent will do a quick confirmation before proceeding.
- **Multiple slugs exist**: `resolution: needs_user_input` — list all of `{existing_slugs}` in `question_for_user` and ask the user to pick.

### Step 3: Never guess silently

If there is more than one existing slug and the user's message doesn't clearly name one, you must return `needs_user_input`. A wrong guess here reaches a real cluster — the main agent would deploy, patch, and re-deploy the wrong quickstart.

## Output

```json
{
  "resolution": "resolved | needs_user_input | error",
  "slug": "<matched slug or null>",
  "confidence": "high | medium | low",
  "confirm_with_user": false,
  "question_for_user": null,
  "error_message": null
}
```

**Example — user named it, unambiguous:**

Input: `user_message: "deploy and debug mortgage-processor"`, `existing_slugs: ["mortgage-processor", "spending-transaction-monitor"]`

```json
{
  "resolution": "resolved",
  "slug": "mortgage-processor",
  "confidence": "high",
  "confirm_with_user": false,
  "question_for_user": null,
  "error_message": null
}
```

**Example — ambiguous, multiple slugs, no name given:**

Input: `user_message: "deploy it to the cluster and fix whatever breaks"`, `existing_slugs: ["mortgage-processor", "spending-transaction-monitor"]`

```json
{
  "resolution": "needs_user_input",
  "slug": null,
  "confidence": "low",
  "confirm_with_user": false,
  "question_for_user": "Which quickstart are we deploying and debugging — mortgage-processor or spending-transaction-monitor?",
  "error_message": null
}
```

**Example — no quickstarts exist yet:**

Input: `user_message: "deploy it to the cluster"`, `existing_slugs: []`

```json
{
  "resolution": "error",
  "slug": null,
  "confidence": "high",
  "confirm_with_user": false,
  "question_for_user": null,
  "error_message": "No quickstarts found under .rhoai-qs/. rh-qs-debug-and-deploy requires an existing quickstart with deploy configuration — run the earlier pipeline stages first, starting with rh-qs-discovery."
}
```
