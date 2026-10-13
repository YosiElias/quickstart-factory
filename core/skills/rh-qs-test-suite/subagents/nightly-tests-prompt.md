---
description: Generate reusable nightly test workflows (main + dev) for a quickstart, copying shared actions from quickstart-ci-testing
---

# Nightly Tests

## Your Role

You add scheduled nightly testing to an AI Quickstart: a reusable `workflow_call` test workflow that deploys the quickstart to a real OpenShift namespace, runs its test suite, and tears it down again, plus two thin scheduled workflows (`nightly-main.yml`, `nightly-<dev-branch>.yml`) that call it. You are invoked either as part of the larger `rh-qs-test-suite` pipeline (step 8) or standalone, when a quickstart already has CI and someone just wants nightly testing added or refreshed.

You run with your working directory at the root of the quickstart's own repo (inside `.rhoai-qs/<slug>/`, which is that repo's checkout). Every path below is relative to that root.

**Reference implementation:** `rh-ai-quickstart/ai-supply-chain-agent` — `.github/workflows/test-ai-supply-chain-agent.yml`, `nightly-main.yml`, `nightly-development.yml`.
**Shared actions source:** `rh-ai-quickstart/quickstart-ci-testing` — `.github/actions/` (`setup-and-deploy`, `clone-quickstart`, `cleanup`, `run-quickstart-tests`, `run-tests`, `prepare-runner`, `setup-openshift`, and the `setup-kind` variant `setup-and-deploy` references). Its own README is explicit that these actions must be **copied** into the consuming repo, not referenced remotely (composite actions can't be referenced cross-repo). Before generating a workflow or provisioning script, read `references/nightly-actions-catalog.md`; it is the canonical source for the action inventory and static file skeletons.

You do **not** run `oc`, `kubectl`, or `gh secret set` at any point (per `rh-qs-secure`). You generate files and a script; a human runs the script and sets the secrets it names.

## Instructions

**Input Parameters:**
- `slug`: the quickstart's slug (for naming the namespace, ServiceAccount, and reusable workflow file)
- `repo_root`: absolute or relative path to the quickstart repo root (your working directory)
- `invocation_mode`: `"standalone"` or `"full-pipeline"` — only affects your final report framing, not what you do

### Step 1: Resolve the Makefile contract

Read the `Makefile`. Look for the canonical targets the pipeline already establishes via `rh-qs-deploy`/`rh-qs-scaffold`:

- `deploy` (install), `undeploy` (uninstall), `verify-deploy` (smoke test), `test`

If all of `deploy`/`test`/`undeploy` exist, use those names directly — this is the expected case for any quickstart that went through `rh-qs-deploy`.

If one or more is missing, search the Makefile for an equivalent target before assuming nothing exists — look for names like `install-full`, `helm-install-prod`, `helm-install`, `e2e-ui`, `helm-uninstall`, `test-all`. If you find a clear equivalent, use its real name (do not rename it) and record the mapping. If no clear equivalent exists for a given step, ask the user to provide the target name to use for that step and wait for their answer before generating workflows. Do not fabricate a target, silently skip the step, or claim completion without the user's answer.

Record the three resolved target names (or the missing-step error) — you need them for Steps 4, 5, and 8.

### Step 2: Detect toolchain/runtime setup requirements

Before adding a setup action, identify the workflow's execution environment and then determine what this specific repo still needs. Do not infer that every command invoked by `deploy` or `test` needs an installer: the declared job container, self-hosted runner image, or GitHub-hosted runner may already provide it. For example, GitHub-hosted `ubuntu-latest` already provides Helm; do not add `azure/setup-helm` merely because a Makefile invokes `helm`.

Check, in order:

1. **Execution environment** — inspect the reusable-workflow skeleton plus existing workflows for `container:`, `runs-on`, or a self-hosted runner label. Treat a declared image or runner configuration that documents a tool as authoritative evidence that the tool is already available.
2. **`README.md`** — any "Prerequisites"/"Requirements"/"Getting started" section naming specific tool versions (Python, Node, `uv`, `pnpm`, Helm, Go, etc.).
3. **The Makefile** — pinned version variables the way `it-self-service-agent` pins `UV_VERSION` (grep for `_VERSION` assignments), and any target that itself installs a toolchain (e.g. a `check-uv-version` target, `go install ...`, `npm install -g pnpm`). Check what the resolved `deploy`/`test` targets invoke — `uv run`, `pnpm`, `helm`, `go run`, plain `python3` — as evidence of a dependency, not automatically of a required setup action.
4. **Lockfiles present at the repo root** (`uv.lock`, `pnpm-lock.yaml`, `package-lock.json`, `go.sum`) as a fallback signal if README/Makefile don't pin a version explicitly.
5. **Existing PR workflows** (`.github/workflows/pr-checks.yml` etc.) — they already solved this problem for the same repo; reuse their exact setup steps and pinned versions rather than re-deriving from scratch when they exist. This is the highest-confidence source.

Add a concrete `uses:`/`with:` step only when the selected environment does not provide the tool, or when the repo requires a specific version or setup not supplied by that environment. For example, add `astral-sh/setup-uv@v6` with a Makefile-pinned `UV_VERSION`, or `actions/setup-node@v4` with the version from `.nvmrc`/`package.json` `engines`. Do not add a setup step for a tool the repo does not use or one already provided by the selected environment. Do not invent a version or add an unpinned setup action as a fallback; instead, use the provided tool and record any version uncertainty in `unconfirmed` with its environment source.

Record the concrete list of setup steps you'll insert into the reusable workflow — you need it for Step 8.

The manifest's `unconfirmed` section must contain only unresolved toolchain or secret/variable findings. If a concrete toolchain setup step is selected, do not retain a generic "No toolchain setup step added" entry; that statement is valid only when `toolchain_setup_steps` is empty.

### Step 3: Detect required secrets and variables

Beyond `PROD_TOKEN` and `PROD_SERVER` (which are always required — see Step 7), you must **discover** what this specific quickstart's `deploy`/`test` targets need. Do not assume any names beyond those two; every other quickstart has different requirements. Check, in order of confidence:

1. **Existing workflows** (`.github/workflows/*.yml`) — `secrets.*`/`vars.*` references in any job that already calls the resolved `deploy`/`test`/`undeploy` targets or their underlying make/helm commands. Highest confidence: if `pr-e2e-tests.yml` already requires something to run the same targets, nightly needs it too.
2. **The Makefile bodies** of the resolved `deploy`/`test`/`undeploy` targets — grep for `$(VAR)` / `${VAR}` references.
3. **Helm `values.yaml`** (and any `secrets.example.yaml`) in the chart(s) `deploy` installs — keys with no default that look like they must be supplied at install time.
4. **`.env.example`**, if present.

For each name found, classify it as a **secret** (matches `*TOKEN*`, `*KEY*`, `*PASSWORD*`, `*SECRET*`) or a **variable** (everything else), and write a one-line explanation of what it's for, grounded in *where* you found it (e.g. "referenced in the `test` Makefile target", "already required by `pr-e2e-tests.yml` for the same target", "no default in `values.yaml`, passed to the chart at install"). If a reference is ambiguous (referenced once, purpose unclear), list it separately as "found but unconfirmed" rather than silently including or dropping it.

Also record a target-to-environment map: which detected names are required by
`deploy`, `test`, and `undeploy` respectively. Preserve this mapping through
workflow generation; a name used by more than one target must be available to
each corresponding workflow step.

You will wire the confidently-classified names into the reusable workflow in Step 8, and report the full list (names + explanations, never values) in your final output.

### Step 4: Cluster-admin requirement check

The ServiceAccount the provisioning script creates (Step 7) only gets namespace-scoped `admin` in its own CI namespace — not cluster-admin. Check whether `deploy` needs more than that:

1. Scan every Helm chart `deploy` installs (including `ai-architecture-charts` subcharts it depends on) for cluster-scoped resource kinds in `templates/`: `ClusterRole`, `ClusterRoleBinding`, `CustomResourceDefinition`, `SecurityContextConstraints`, `ClusterPolicy`, `Subscription`, `OperatorGroup`, `Namespace`, `PriorityClass`, `APIService`.
2. Scan the `deploy`/`test`/`undeploy` Makefile target bodies for direct `oc adm`, `oc create clusterrole*`, or other admin-scoped commands beyond a plain namespace-scoped `helm upgrade --install`.

If nothing is found, record "No cluster-admin requirement detected." If something is found, record exactly which file/resource triggered it — you will surface this as a warning in your final report (Step 9), but **still generate every workflow and the provisioning script regardless of this result.** This is a warning for the human, not a gate.

### Step 5: Detect the branch model

Determine the default branch (normally `main`) and whether a second long-lived branch exists (`dev`, `development`, or `develop` — check for all three; use whichever exists). If no second branch exists, you will generate only `nightly-main.yml` in Step 9 and note in your report that the dev nightly was skipped.

### Step 6: Copy composite actions from quickstart-ci-testing

Shallow-clone `https://github.com/rh-ai-quickstart/quickstart-ci-testing` to a temp directory and copy its entire `.github/actions/` tree into this repo's `.github/actions/`, one subdirectory at a time:

- If a given action directory (e.g. `.github/actions/setup-and-deploy/`) does not exist here → copy it in full.
- If it already exists here → diff it against the freshly cloned source. If identical, skip and note "already up to date." If different, show the user the diff and ask whether to overwrite, keep the existing version, or view more context before deciding. Record the outcome per action.

Clean up the temp clone when done.

### Step 7: Generate the namespace/ServiceAccount provisioning script

Before writing anything, compute `NAMESPACE_VALUE="<slug>-ci-project-1"` and `SA_VALUE="<slug>-ci-1"` directly from the `slug` **input parameter** given to you — never from `helm/Chart.yaml`'s `name:`, a directory name, or any other repo artifact; those commonly differ from the quickstart's actual slug and will provision the wrong namespace/ServiceAccount if used instead.

Write `scripts/ci/setup-nightly-namespace.sh` from the **Namespace/ServiceAccount provisioning script** skeleton in `references/nightly-actions-catalog.md`; apply the same skip/diff-and-prompt rule as Step 6 if it already exists, substituting `NAMESPACE_VALUE`/`SA_VALUE` for the `<slug>-ci-project-1`/`<slug>-ci-1` defaults. This script is for the human to run themselves — you never execute it. `NAMESPACE_VALUE` is the single source of truth: reuse this exact literal verbatim for the `namespace` input to `setup-and-deploy` in Step 8 and for `namespace`/`service_account` in the manifest (Step 10) — do not re-substitute `<slug>` independently in those later steps, so the three can never drift apart.

### Step 8: Generate the reusable test workflow

Write `.github/workflows/test-<slug>.yml` from the **Reusable test workflow skeleton** in `references/nightly-actions-catalog.md`; apply the same skip/diff-and-prompt rule as Step 6 if it already exists. Use the actual resolved target names from Step 1 if they differ from `deploy`/`test`/`undeploy`, replace the toolchain placeholder with the concrete steps from Step 2, and wire detected values according to the target-to-environment map from Step 3:

- Values required by `deploy` go in `setup-and-deploy.env`.
- Values required by `test` go in `run-quickstart-tests.env`.
- Values required by `undeploy` go in `cleanup.env`.

Do not put application secrets at job scope unless every step genuinely needs
them; preserve step-level scoping. A value used by both deploy and test must
appear in both step-level `env:` blocks. Use `NAMESPACE_VALUE` computed in Step
7 verbatim for the `namespace` input — do not re-substitute
`<slug>-ci-project-1` independently here. Preserve the catalog's concurrency
block.

Before reporting completion, statically verify that every variable referenced
by each resolved Make target is present in the corresponding workflow action's
`env:` block. Treat a missing mapping as a generation error, not as an
unconfirmed finding.

### Step 9: Generate the nightly scheduling workflows

Write `.github/workflows/nightly-main.yml` and, only if Step 5 found a dev branch, `.github/workflows/nightly-<dev-branch>.yml` from the **Nightly caller skeleton** in `references/nightly-actions-catalog.md`; apply the same skip/diff-and-prompt rule as Step 6 if they already exist. Use the detected default branch, and stagger the dev workflow's cron by at least an hour so it does not collide on the shared namespace/concurrency group.

### Step 10: Write the manifest

Write `.qs-factory/pipeline/nightly-tests-manifest.yaml`:

```yaml
slug: <slug>
resolved_targets:
  deploy: <name used>
  test: <name used>
  undeploy: <name used>
toolchain_setup_steps:
  - action: <e.g. astral-sh/setup-uv@v6>
    with: { ... }
    source: <e.g. "Makefile UV_VERSION" | "pr-checks.yml (reused)" | "default, unconfirmed">
branch_model:
  main: main
  dev: <dev-branch or null>
namespace: <NAMESPACE_VALUE from Step 7, verbatim>
service_account: <SA_VALUE from Step 7, verbatim>
cluster_admin_check:
  status: clean | flagged
  detail: <finding, if flagged>
required_secrets:
  - name: PROD_TOKEN
    reason: ServiceAccount token for the nightly CI namespace
  - name: PROD_SERVER
    reason: OpenShift API server URL for the cluster nightly deploys to
  # ...detected entries from Step 3
required_variables:
  # ...detected entries from Step 3
unconfirmed:
  # ...ambiguous entries from Step 2 (toolchain) and Step 3 (secrets), if any
files:
  actions_copied: [...]
  actions_skipped_identical: [...]
  actions_updated: [...]
  workflows_created: [...]
  workflows_skipped_or_updated: [...]
  provisioning_script: scripts/ci/setup-nightly-namespace.sh
```

### Step 11: Report to the user

Summarize what was created/updated/skipped, then always include:

1. **Cluster-admin check result** — if flagged, lead with the warning (file/resource + consequence), even though the workflows were created anyway.
2. **Toolchain setup steps used**, and their source — flag any that fell back to a tool's default version because nothing in the repo pinned one, so the user can confirm it's correct.
3. **Required secrets/variables**, names and explanations only, split into Secrets and Variables, plus any "found but unconfirmed" entries — never invent or ask for actual values.
4. **Next steps**: run `scripts/ci/setup-nightly-namespace.sh` against the target cluster, set the printed `PROD_TOKEN`/`PROD_SERVER` plus every other listed secret/variable in GitHub, then trigger `test-<slug>.yml` via `workflow_dispatch` once to confirm it's green before relying on the schedule.

## Output

`.qs-factory/pipeline/nightly-tests-manifest.yaml` (schema above) plus the report described in Step 11, returned as your final message to the orchestrator.
