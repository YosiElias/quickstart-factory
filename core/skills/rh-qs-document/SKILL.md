---
name: rh-qs-document
description: Generate README and catalog documentation for AI Quickstarts from verified deployment. Creates or updates README.md with deploy steps, requirements, architecture diagram, and catalog metadata. Use only after rh-qs-verify-deploy produces a green report.
---

# rh-qs-document

**Category:** `documentation/'

## Trigger

**`rh-qs-verify-deploy`** report is green (`.qs-factory/reports/verify-deploy-*.md`); CI workflows from `rh-qs-test-suite` are in place when the design requires them

Documentation runs **after** verification — not before. Every deploy command in the README must match what verify-deploy actually ran.

## Where This Runs

This skill works inside `.rhoai-qs/<slug>/` — the scaffolded quickstart's own repo, since `README.md` lives at that repo's root. Pipeline files, architecture spec, and reports sit right alongside the code in this same folder — reference them as plain relative paths, no `../` needed. See [pipeline-convention.md](../../../docs/foundation/pipeline-convention.md#where-skills-run-and-why-it-matters-for-paths).

## What it does

1. **Fills in the existing `README.md` in place** — never regenerates it (see below)
2. Replaces each `> **CONTRIBUTOR TODO:` blockquote with real content: title, description, requirements (hardware/software), deploy steps, delete/cleanup steps
3. References the **Mermaid architecture diagram** from the architect phase (saved in `docs/images/`)
4. Fills the `## Tags` block with catalog metadata for Red Hat documentation discovery
5. Documents all **environment variables** and their purpose
6. Optionally generates a **demo script outline** for video/presentation

## Fill in the README — do not regenerate it

`README.md` already exists. `rh-qs-discovery` seeded the repo from [ai-quickstart-template](https://github.com/rh-ai-quickstart/ai-quickstart-template), so the file is the full catalog skeleton: `Overview`, `Detailed description`, `Architecture diagrams`, `Requirements`, `Deploy` (`Prerequisites` / `Installation` / `Validating the deployment` / `Delete`), `Repository structure`, `References`, `Technical details`, `Tags`.

**Edit it, section by section.** Writing a fresh README over the top drops the sections and tag fields catalog publication requires, and those are exactly the fields nobody notices missing until the submission bounces.

Find the work with:

```bash
grep -n 'CONTRIBUTOR TODO' README.md
```

Each hit is a blockquote describing what belongs there, usually with an example. Replace the whole blockquote with real content drawn from the verify-deploy report, architecture spec, and the code. When every hit is gone, the README is done. Keep the heading structure as-is — the catalog tooling reads it.

**Substitute Makefile targets for the template's raw `oc`.** The skeleton's examples use `oc new-project`, `oc get pods`, `helm uninstall`, and `oc delete project`. Those are placeholder guidance, not the commands to ship — they contradict `rh-qs-secure`, which forbids documenting raw `oc`/`kubectl`. Write `make deploy`, `make verify-deploy`, and `make undeploy` instead, matching what verify-deploy actually ran. Do not copy the examples verbatim.

Two of the template's placeholder strings also need replacing wherever they appear: `YOUR_QUICKSTART_NAME` and `my-quickstart`.

## Workflow

### Phase 0: Resolve Quickstart Context

Before doing anything, resolve which quickstart this session is for. Run `ls -1 ../ 2>/dev/null` (every entry is a quickstart — no filtering) and spawn the **validation-skill subagent**:

```python
Agent(
    description="Resolve which quickstart this documentation session is for",
    prompt=f"""
Read and follow instructions from:
core/skills/rh-qs-document/subagents/validation-skill-prompt.md

User message: {user_message}
Existing slugs: {existing_slugs}
Is entry point: false
Calling skill: rh-qs-document
"""
)
```

Handle the result per [validation-skill-template.md](../../../docs/foundation/validation-skill-template.md#main-agent-handling).

### Remaining phases

```
- [ ] 1. Read verify-deploy report — use verified commands, flags, and namespace
- [ ] 2. Explore repository (code, Helm, Makefile, compose, docs/images/)
- [ ] 3. Read architecture spec for architecture diagram and component list
- [ ] 4. Gather user-facing facts (hardware, RHOAI version, permissions)
- [ ] 5. Fill in every CONTRIBUTOR TODO block in README.md, in place
- [ ] 6. Validate every documented command exists in Makefile or Helm (no undocumented oc/kubectl)
- [ ] 7. Cross-check README deploy steps against verify-deploy evidence
- [ ] 8. Complete the ## Tags block — publication blocks without it
- [ ] 9. Optional: write docs/demo-script.md
```

### What each section needs

- Title and short description — the catalog's character limits are enforced in the Tags check below
- Workload-focused detailed description
- Requirements: specific GPU, tested OpenShift AI version, permissions
- Deploy and Delete steps (copy-pasteable; `make deploy` / `make undeploy` and podman terminology — not raw `oc`)
- Architecture section with diagram from `docs/images/` or architecture spec
- Environment variables table
- Repository structure tree, updated to the real layout

### `## Tags` — required for publication

redhat.com catalog publication rejects a quickstart with an incomplete `## Tags` block, so check it explicitly rather than trusting the TODO sweep:

| Field | Constraint |
|-------|-----------|
| Title | Must match the H1 heading exactly; ≤ 64 chars |
| Description | Must match the short description exactly; ≤ 160 chars |
| Industry | Exactly one, from the catalog's list (e.g. Healthcare, Retail, Financial Services) |
| Product | Primary Red Hat product (e.g. OpenShift AI, OpenShift, RHEL) |
| Use case | Short descriptor (e.g. security, automation, productivity) |
| Partner | Partner names, or `N/A` — the field must be present either way |
| Contributor org | The contributing organization. The template's own TODO block does not list this one; add the line. |

Record the result in `doc-manifest.yaml` under `validation.tags_complete` (see [pipeline-contracts.md](../../../docs/foundation/pipeline-contracts.md#7-doc-manifestyaml)) and do not hand off to `rh-qs-ship` while it is false.

### Demo script (optional)

Save to `docs/demo-script.md`:

- Setup (~2 min)
- Primary user journey demo (~5 min)
- Architecture callout (~2 min)
- Cleanup (~1 min)

## What not to include

- Line-by-line code walkthroughs
- Generic placeholders when repo pins specific versions
- Commands not present in Makefile or Helm
- A regenerated README — fill in the template's, in place

## Audience

Readers may have **limited OpenShift AI experience**. Use plain language, explicit prerequisites, ordered steps.

## Output

- `README.md` (edited in place — every CONTRIBUTOR TODO block replaced)
- `.qs-factory/pipeline/doc-manifest.yaml`
- Optional `docs/demo-script.md`
- Updated `docs/images/` if diagram exported

## Next skill

When README is complete → **`rh-qs-ship`**

## References

- [ai-quickstart-template README](https://github.com/rh-ai-quickstart/ai-quickstart-template/blob/main/README.md) — the upstream skeleton; the repo's own `README.md` is the copy to edit
- Architecture spec: `.qs-factory/designs/architecture-spec.yaml`
- [subagents/validation-skill-prompt.md](./subagents/validation-skill-prompt.md) — pass by file path only, do NOT read directly

## Pipeline checkpoint

Run the checkpoint:

```bash
python3 core/flow/pipeline-checkpoint.py --skill-name rh-qs-document --qs-name {qs-name}
```
Print the dashboard link to the user:
"Pipeline dashboard updated — track progress at [dashboard.md](.rhoai-qs/{qs-name}/.qs-factory/flow/dashboard.md)"
