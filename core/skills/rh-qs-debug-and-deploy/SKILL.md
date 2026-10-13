---
name: rh-qs-debug-and-deploy
description: Deploy an AI Quickstart to OpenShift, debug failures in dependency order until all resources are healthy, and verify end-to-end
argument-hint: <qs-slug> [namespace]
allowed-tools: Bash, Read, Write, Edit, Agent, AskUserQuestion, WebSearch
---

# rh-qs-debug-and-deploy

**Category:** `deployment/`  

You are deploying an AI Quickstart to an OpenShift cluster, debugging any failures systematically in dependency order, and verifying end-to-end functionality.

## Goal

Deploy the quickstart, get all resources healthy, and pass the full test plan — with minimal changes that preserve the original application flow.

## Input

This skill runs with the working directory at the **`quickstart-factory` repo root** — every path below is relative to it.

User provides:
- **Quickstart slug**: resolved in Phase 0. From it the skill derives the two paths used everywhere else:
  - `{project_path}` = `.rhoai-qs/{slug}` — the quickstart's own repo (application code, Helm charts, Makefile, deployment docs). Its `pipeline/` subdirectory holds the files that must outlive a run.
  - `{state_dir}` = `.tmp/{slug}/debug` — all per-run working files (gitignored, rotated on every run).
- **Namespace** _(optional)_: Target OpenShift namespace. If omitted, the Cluster Access Validator subagent derives a unique default namespace (see Phase 1a).

## Critical Rules

1. **Every oc/helm command MUST use `-n <namespace>` explicitly** — never rely on current context
2. **Do NOT change the intention of the original application flow** — fix deployment/config so the existing architecture works on OpenShift
3. **Auto-apply** config/infra fixes: ports, service names, storage classes, security contexts, resource limits, env vars, image tags, probes, volumes, SCCs
4. **Auto-apply** source code changes explicitly related to OpenShift (inside `if openshift_mode` blocks, OCP-specific config)
5. **Ask user** for source code changes NOT explicitly related to OpenShift — use AskUserQuestion
6. **Project-specific deploy commands** — never hardcode generic helm/oc commands; use what the Project Analyzer discovers
7. **Never guess the deployment variant** — when the analyzer finds multiple mutually-exclusive OpenShift deployment paths, ask the user before deploying (Phase 1d)
8. **Max 3 fix attempts per resource per phase** — escalate to user after 3 failed attempts (health and e2e phases each get 3 attempts)

## Workflow

> **Note:** Some phases below spawn subagents via the Agent tool. Subagent prompt files in `subagents/` are loaded by those subagents — do not read them yourself.

### Phase 0: Resolve Quickstart Context

Before touching any files, resolve which quickstart this session is for. Run `ls -1 .rhoai-qs/ 2>/dev/null` (every entry is a quickstart — no filtering) and spawn the **validation-skill subagent**:

```python
Agent(
    description="Resolve which quickstart this deploy-and-debug session is for",
    prompt=f"""
Read and follow instructions from:
./subagents/validation-skill-prompt.md

User message: {user_message}
Existing slugs: {existing_slugs}
Is entry point: false
Calling skill: rh-qs-debug-and-deploy
"""
)
```

Handle the result per [validation-skill-template.md](../../../docs/foundation/validation-skill-template.md#main-agent-handling). If `resolution: error` (no slugs exist), tell the user to run the earlier pipeline stages first.

Once resolved, set `{project_path}` = `.rhoai-qs/{slug}` and `{state_dir}` = `.tmp/{slug}/debug` for every phase below.

### Phase 1: Pre-deployment Analysis

#### 1a. Spawn Cluster Access Validator Subagent

```python
result = Agent(
    description="Validate cluster access",
    prompt=f"""
Read and follow instructions from:
./subagents/cluster-access-validator-prompt.md

Slug: {slug}
Namespace: {namespace if provided, else ""}
"""
)
namespace = result.split("namespace:")[1].strip()  # extract from "namespace: <value>"
```

Verifies login and namespace existence — prompts user interactively if anything needs fixing. If no namespace was provided, the subagent derives a unique default. Returns `namespace: <value>` on success — this serves as the success marker for the subagent.

**Output validation**: If the subagent returns no text or the returned text does not contain `namespace:`, treat it as a validation failure and re-run the subagent (max 2 retries). If it still fails after retries, stop and report the cluster access failure to the user. Extract the namespace value from the `namespace:` line.

Use the returned namespace as `{namespace}` for all subsequent phases.

#### 1b. Create State Directory

```bash
if [ -d ".tmp/{slug}/debug" ]; then
  mv ".tmp/{slug}/debug" ".tmp/{slug}/debug.old.$(date +%Y%m%d-%H%M%S)"
fi
mkdir -p ".tmp/{slug}/debug"
mkdir -p ".rhoai-qs/{slug}/.qs-factory/pipeline"
```

Rotation only ever touches `{state_dir}` — the persistent files under `{project_path}/pipeline/` (`deploy-state.yaml`, `test-plan.md`) survive every run.

#### 1c. Spawn Project Analyzer Subagent

```python
Agent(
    description="Analyze project for deployment",
    prompt=f"""
Read and follow instructions from:
./subagents/project-analyzer-prompt.md

Project directory: {project_path}
State dir: {state_dir}
Namespace: {namespace}
"""
)
```

**Output**: `{state_dir}/deploy-analysis.yaml` with deploy commands, expected resources, dependency order

Read the analysis result. Understand the deployment method, components, and dependency graph.

#### 1d. Resolve Deployment Option

Some quickstarts document more than one mutually-exclusive way to deploy to OpenShift — in-cluster model serving vs. an external inference endpoint, GPU vs. CPU-only, full vs. minimal profile. Never guess which one the user wants.

```bash
yq eval '.deployment_options' {state_dir}/deploy-analysis.yaml
```

- **Field absent or `null`** — the project has a single deployment path. Nothing to ask; continue to Phase 2.
- **Two or more options** — AskUserQuestion, one choice per entry, the `recommended: true` entry first:

  ```
  "This quickstart supports more than one deployment path. Which one should be deployed to {namespace}?

  {label} — {description}
  Requires: {requires}
  Why suggested: {rationale}"
  ```

Once the user chooses, update `{state_dir}/deploy-analysis.yaml` in place:

- Set `selected_option_id` to the chosen option's `id`
- Set the top-level `deploy_commands` to that option's `deploy_commands`

`deploy-analysis.yaml` is the single source of truth for the chosen path — do not write the selection anywhere else. Every later phase keeps reading `deploy_commands` exactly as before, so the deploy executor and fix applier need no knowledge of options.

---

### Phase 2: Deploy

Spawn Deploy Executor subagent:

```python
Agent(
    description="Deploy to OpenShift",
    prompt=f"""
Read and follow instructions from:
./subagents/deploy-executor-prompt.md

Namespace: {namespace}
Project path: {project_path}
State dir: {state_dir}
"""
)
```

**Output validation**: If the subagent's return text does not contain `deploy-execute-status: success`, treat it as a deployment failure and re-run the subagent (max 2 retries). If it still fails after retries, stop and report the deployment failure to the user.

---

### Phase 3: Initial Health Scan

Spawn Health Scanner subagent:

```python
Agent(
    description="Scan namespace health",
    prompt=f"""
Read and follow instructions from:
./subagents/health-scanner-prompt.md

Namespace: {namespace}
Project path: {project_path}
Expected resources file: {state_dir}/deploy-analysis.yaml (read ONLY the expected_resources field)
"""
)
```

**Output**: `{project_path}/pipeline/deploy-state.yaml`

Read `unhealthy_resources` field from the state file.
- If empty (all healthy) → skip to Phase 5
- If unhealthy resources exist → enter Phase 4

---

### Phase 4: Debug Loop

Read `dependency_order` from `{state_dir}/deploy-analysis.yaml` to sort unhealthy resources — fix leaves first (resources with no dependencies), then work up.

**For each unhealthy resource** (in dependency order):

#### 4a. Spawn Debugger Subagent

```python
Agent(
    description=f"Debug {resource_name}",
    prompt=f"""
Read and follow instructions from:
./subagents/resource-debugger-prompt.md

Resource name: {resource_name}
Resource kind: {resource_kind}
Namespace: {namespace}
Project path: {project_path}
State dir: {state_dir}
Phase: health
Current attempt number (attempt_number): {attempt_number}
"""
)
```

**Output**: `{state_dir}/debug-{resource_name}.yaml` — appended with `health_attempt_{N}` entry containing root cause and proposed fix

#### 4b. Spawn Fix Applier Subagent

Extract deploy commands to pass to the fix applier:

```bash
yq eval '.deploy_commands' {state_dir}/deploy-analysis.yaml
```

```python
Agent(
    description=f"Fix {resource_name}",
    prompt=f"""
Read and follow instructions from:
./subagents/fix-applier-prompt.md

Debug report: {state_dir}/debug-{resource_name}.yaml
Namespace: {namespace}
Project path: {project_path}
State dir: {state_dir}
Deploy commands: {deploy_commands}
Phase: health
Current attempt number (attempt_number): {attempt_number}
"""
)
```

**Output**: `{state_dir}/fix-{resource_name}.yaml` updated with `health_attempt_{N}` entry

#### 4c. Re-scan Health

Spawn Health Scanner subagent (same as Phase 3) to re-scan ALL resources.

**Output**: Updated `{project_path}/pipeline/deploy-state.yaml`

#### 4d. Evaluate Result

Read `unhealthy_resources` from updated state file:

- **Resource now healthy** → move to next unhealthy resource
- **Still unhealthy AND attempt < 3** → back to 4a with incremented attempt number
  - Debugger reads previous `health_attempt_*` entries from both `{state_dir}/debug-{resource_name}.yaml` and `{state_dir}/fix-{resource_name}.yaml`
- **Attempt = 3** → AskUserQuestion:
  ```
  "Resource {resource_name} ({resource_kind}) is still unhealthy after 3 fix attempts:

  Attempt 1: {issue} → {fix_applied} → {result}
  Attempt 2: {issue} → {fix_applied} → {result}
  Attempt 3: {issue} → {fix_applied} → {result}

  Options:
  A. Skip this resource and continue with others
  B. Provide guidance on how to fix this resource
  C. Stop deployment and investigate manually"
  ```

Continue to next unhealthy resource until all processed.

**Note:** Since every resource either gets fixed or is escalated to the user at attempt 3, reaching Phase 5 with unhealthy resources should be very rare (only if user chose to skip).

---

### Phase 5: E2E Testing & Debug

#### 5a. Run E2E Tests

Spawn E2E Tester subagent:

```python
Agent(
    description="Run E2E tests",
    prompt=f"""
Read and follow instructions from:
./subagents/e2e-tester-prompt.md

Project path: {project_path}
State dir: {state_dir}
Namespace: {namespace}
"""
)
```

**Output**: `{state_dir}/e2e-results.yaml`

Read the results:
- All tests pass → skip to Phase 6
- Failures → read `failure_summary` to identify which resource(s) are causing failures, enter 5b

#### 5b. E2E Debug Loop

Same debug→fix cycle as Phase 4, but with `Phase: e2e` and max 3 attempts per resource.

For each implicated resource (in dependency order):

1. Spawn Debugger subagent (same as 4a, but pass `Phase: e2e`)
2. Spawn Fix Applier subagent (same as 4b, but pass `Phase: e2e`)
3. Re-run E2E Tester (same as 5a) to check if the failure is resolved
4. Evaluate:
   - **E2E test now passes for this resource** → move to next implicated resource
   - **Still failing AND attempt < 3** → retry with incremented attempt number
   - **Attempt = 3** → escalate to user (same AskUserQuestion format as Phase 4d)

The debug/fix files (`{state_dir}/debug-{resource_name}.yaml`, `{state_dir}/fix-{resource_name}.yaml`) are the same files used in Phase 4. E2E attempts are written under `e2e_attempt_N` keys — separate from `health_attempt_N` keys, so full history is preserved.

---

### Phase 6: Final Report

**Read `output-templates/final-report-template.md` before continuing** for report format.

Generate the final report including:
- Deployment status
- Deployment option deployed (read `selected_option_id` from `{state_dir}/deploy-analysis.yaml`; omit when the project had a single path)
- Resources deployed and final state
- Issues found and fixes applied (read from `{state_dir}/fix-*.yaml` files)
- E2E test results (pass/fail per test)
- If E2E failures: clear description of what failed and why
- Files modified during debugging

Print it to the user **and** write the same content to `{state_dir}/deploy-report.md`. Write it on every outcome, including partial success and E2E failures.

---

## Important Guidelines

### DO:
- Always use `-n <namespace>` on every oc/helm command
- Use project-specific deploy commands from analysis (not generic templates)
- Ask the user which deployment option to use when the analyzer found more than one (Phase 1d), and report which one was deployed
- Fix resources in dependency order (leaves first)
- Read `unhealthy_resources` field first from state file
- Let subagents handle diagnosis and fixing — keep orchestration clean
- Escalate to user after 3 failed attempts per resource per phase (health and e2e are separate)
- Debug E2E failures using the same debug→fix cycle with `Phase: e2e`

### DON'T (never do any of these):
- Never read subagent prompt files in the main agent
- Never hardcode generic helm install / oc apply commands
- Never deploy a project that has `deployment_options` without a `selected_option_id` recorded in `{state_dir}/deploy-analysis.yaml`
- Never record the selected deployment option anywhere other than `{state_dir}/deploy-analysis.yaml`
- Never change the intention of the original application flow
- Never apply source code changes not related to OpenShift without user approval
- Never skip health scan after a fix (always re-scan full namespace)
- Never exceed 3 debug attempts per resource per phase

## References

- [output-templates/deploy-analysis-template.md](./output-templates/deploy-analysis-template.md)
- [output-templates/deploy-state-template.md](./output-templates/deploy-state-template.md)
- [output-templates/debug-report-template.md](./output-templates/debug-report-template.md)
- [output-templates/fix-report-template.md](./output-templates/fix-report-template.md)
- [output-templates/e2e-results-template.md](./output-templates/e2e-results-template.md)
- [output-templates/final-report-template.md](./output-templates/final-report-template.md)
- [subagents/<subagent-prompt>.md](./subagents/<subagent-prompt>.md) — pass by file path only, do NOT read directly

## Pipeline checkpoint

Run the checkpoint:

```bash
python3 core/flow/pipeline-checkpoint.py --skill-name rh-qs-debug-and-deploy --qs-name {qs-name}
```
Print the dashboard link to the user:
"Pipeline dashboard updated — track progress at [dashboard.md](.rhoai-qs/{qs-name}/.qs-factory/flow/dashboard.md)"
