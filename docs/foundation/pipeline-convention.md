# Pipeline File Convention

This document defines how factory skills store and pass structured artifacts between pipeline stages, and where each quickstart's actual code lives. Everything for a given quickstart — pipeline specs, PRD, architecture spec, reports, **and its application code** — lives together in one place inside the **`quickstart-factory`** repo, namespaced by quickstart slug. This ensures a full audit trail that survives reboots and is deleted only when the user chooses.

## Why Everything Lives Under `.rhoai-qs/<slug>/`

Every skill's bookkeeping — specs, manifests, PRDs, designs, reports — and the quickstart's own application code live together under one folder: `quickstart-factory/.rhoai-qs/<slug>/`. One canonical location per quickstart means every skill can always find everything it needs without hopping between repos or guessing where things are on disk.

Because `.rhoai-qs/` holds data for **every** quickstart ever worked on, every skill must first determine *which* quickstart the current session applies to. See [Resolving the Quickstart Slug](#resolving-the-quickstart-slug).

## The Two Invariants

Everything else in this document follows from these two rules:

1. **Every direct child of `.rhoai-qs/` is a quickstart.** Nothing else lives there — no cross-cutting reports, no shared drafts, no scratch folders. Slug resolution is therefore a plain directory listing, with no allowlist, denylist, or filter step.
2. **All factory bookkeeping lives in exactly one folder per quickstart: `.qs-factory/`.** It has no exceptions — nothing inside it survives `rh-qs-ship`, so a single rule can track it, ignore it, or delete it.

## Directory Structure

`quickstart-factory/.rhoai-qs/<slug>/` **is the quickstart's git repo root.** It is one of two things:

- a **real directory**, seeded by `rh-qs-discovery` from the org template (the normal case), or
- a **symlink** to a repo living elsewhere on disk, for a quickstart you already had checked out before adopting this convention.

Both shapes behave identically for every skill: `ls`, `cd`, and relative paths all work through a symlink, and the checkpoint's dashboard links are computed relative to the dashboard itself, so they stay correct either way.

**Example:** `quickstart-factory/.rhoai-qs/mortgage-processor/`

The `.rhoai-qs/` directory is gitignored by the factory repo, so none of this ever ends up in the factory's own commits. (The quickstart's own code, however, is committed to its own separate repo — see [Nested Quickstart Repos](#nested-quickstart-repos).)

### Full Layout

```
quickstart-factory/
├── .blog-drafts/                           ← gitignored; factory-side, slug-prefixed
│   └── mortgage-processor-2026-03-11.md
├── .reports/                               ← gitignored; cross-cutting reports
│   └── grooming-report-2026-03-11.md
│
└── .rhoai-qs/                              ← gitignored; QUICKSTARTS ONLY, nothing else
    └── mortgage-processor/                 ← the quickstart's own git repo root
        ├── .git/                           ←   (or a symlink to a repo elsewhere)
        │
        ├── .qs-factory/                    ◄══ ALL factory bookkeeping, one folder
        │   ├── prds/
        │   │   └── prd.md
        │   ├── designs/
        │   │   ├── architecture-spec.yaml          # Also the handoff to scaffold
        │   │   └── architecture-diagram.mmd
        │   ├── pipeline/
        │   │   ├── discovery-spec.yaml
        │   │   ├── scaffold-spec.yaml
        │   │   ├── scaffold-manifest.yaml          # Handoff to implement
        │   │   ├── implementation-spec.yaml
        │   │   ├── implementation-manifest.yaml    # Handoff to deploy
        │   │   ├── deploy-spec.yaml
        │   │   ├── deploy-manifest.yaml            # Handoff to security
        │   │   ├── security-report.yaml            # Handoff to debug-and-deploy
        │   │   ├── deploy-state.yaml               # Handoff to document
        │   │   └── doc-manifest.yaml               # Handoff to ship
        │   ├── flow/
        │   │   └── dashboard.md                    # pipeline-checkpoint.py
        │   └── reports/
        │       └── verify-deploy-2026-07-29.md
        │
        ├── chart/                           ─┐
        │   ├── Chart.yaml                    │  seeded from
        │   ├── values.yaml                   │  rh-ai-quickstart/
        │   └── templates/                    │  ai-quickstart-template
        ├── docs/images/                      │  by rh-qs-discovery
        ├── LICENSE                           │
        └── README.md                        ─┘  (catalog skeleton, incl. ## Tags)

            ── added later by scaffold / implement / deploy ──
            packages/{api,ui,db}/ · .github/workflows/ · tests/
            Makefile · compose.yml · turbo.json · .env.example
```

Note what is **not** there: no `blog-drafts/` inside the quickstart (drafts are factory-side working material — see [Factory-Side Locations](#factory-side-locations)), and no sibling folders under `.rhoai-qs/` itself.

## Nested Quickstart Repos

`rh-qs-discovery` seeds `quickstart-factory/.rhoai-qs/<slug>/` from the org template as a **local** git repo as soon as the slug is minted. The **user** pushes it to `rh-ai-quickstart/<slug>` after approving the PRD. From then on this folder has its own `.git/`, its own remote, its own commit history and CI, independent of the factory repo.

`rh-qs-scaffold` does not create the repo — it verifies the remote is set and adds the application scaffolding on top of the template.

### `.qs-factory/` is tracked, not gitignored

`.qs-factory/` lives inside the quickstart's own repo and is **committed and pushed like everything else** throughout development — it is deliberately **not** added to the quickstart's `.gitignore`. This is intentional: it lets the team collaborate on the PRD, design doc, and pipeline state through normal pull requests (reviewing a design doc together, discussing an open question in the PRD, etc.), not just on whichever engineer's machine happened to run the factory pipeline.

It is removed **wholesale** as a final cleanup step in `rh-qs-ship`, right before the quickstart is considered done:

```bash
git rm -r --ignore-unmatch .qs-factory
```

There are no exceptions to that command — nothing inside `.qs-factory/` belongs in a published quickstart. So the finished repo carries none of this internal bookkeeping, but the team had full visibility into it while the work was in progress. See `rh-qs-ship/SKILL.md` for the exact steps.

This is a **separate concern** from the factory's own `.gitignore`, which simply ignores `.rhoai-qs/` as one blanket rule (see the factory's `.gitignore`) — git never looks inside an ignored directory, so it never notices there's another repo nested inside it, and the two repos' git histories don't interact.

## Where Skills Run (and Why It Matters for Paths)

Skills fall into two groups, based on whether they run inside the quickstart's repo:

**At the `quickstart-factory` root** (`rh-qs-discovery`, `rh-qs-architect`, `rh-qs-scaffold`, plus factory-level skills like `pipeline-grooming`, `blog-writer`): paths are written in full, `.rhoai-qs/<slug>/.qs-factory/prds/prd.md`.

**Inside `.rhoai-qs/<slug>/`** (`rh-qs-implement`, `rh-qs-deploy`, `rh-qs-verify-deploy`, `rh-qs-document`, `rh-qs-test-suite`, `rh-qs-ship`): that's where the application code lives and where `make`/`helm`/etc. need to run. From there:

- Reading/writing bookkeeping files uses the `.qs-factory/` prefix: `.qs-factory/prds/prd.md`, `.qs-factory/designs/architecture-spec.yaml`, `.qs-factory/pipeline/deploy-spec.yaml`, `.qs-factory/reports/...`
- Listing other quickstarts (for slug resolution) means going up one level: `ls -1 ../`.

`pipeline-checkpoint.py` is the exception that needs no care here — it anchors every path off the factory root itself, so it writes to the same place from either working directory.

## Resolving the Quickstart Slug

Because `.rhoai-qs/` can hold multiple quickstarts at once, and each skill typically runs in its own separate chat session (no shared conversational memory to rely on), every skill delegates slug resolution to a dedicated subagent, **`validation-skill`**, as **Phase 0** — before any other work.

See [validation-skill-template.md](validation-skill-template.md) for the full resolution logic, inputs/outputs, and required `subagents/validation-skill-prompt.md` file every skill must have.

In short:

1. If the user named the quickstart in their message → use it.
2. Otherwise, list existing slugs — every direct child of `.rhoai-qs/` is one, so this is a plain `ls` with no filtering:
   - Exactly one → confirm with the user, then proceed.
   - Multiple → ask the user which one.
   - None → only valid if this is `rh-qs-discovery` starting a brand-new idea; otherwise, stop and report the error.

**Never guess silently when more than one quickstart exists.** A wrong guess means writing into the wrong quickstart's files.

## File Categories

Four categories of pipeline files exist within `.rhoai-qs/<slug>/.qs-factory/pipeline/`:

### 1. Spec files

Generated during the Analyze phase, consumed by validators and implementers.

| File | Producing Skill | Purpose |
|------|----------------|---------|
| `discovery-spec.yaml` | rh-qs-discovery | Interview plan |
| `scaffold-spec.yaml` | rh-qs-scaffold | Repo structure plan |
| `implementation-spec.yaml` | rh-qs-implement | Endpoints, schemas, services |
| `deploy-spec.yaml` | rh-qs-deploy | Chart deps, values, Containerfiles |
| `security-spec.yaml` | rh-qs-security | Scan targets, severity thresholds |
| `update-spec.yaml` | rh-qs-update | Change type, affected files |

After validation, a refined variant is written:

```
<skill>-spec.yaml          → initial spec
<skill>-spec-refined.yaml  → after validator feedback
```

### 2. Handoff manifests

Output artifacts that the next pipeline stage consumes. These are the inter-skill contracts. All locations are relative to `.qs-factory/`.

| File | Producer | Consumer | Location |
|------|----------|----------|----------|
| `architecture-spec.yaml` | rh-qs-architect | rh-qs-scaffold | `designs/` |
| `scaffold-manifest.yaml` | rh-qs-scaffold | rh-qs-implement | `pipeline/` |
| `implementation-manifest.yaml` | rh-qs-implement | rh-qs-deploy | `pipeline/` |
| `deploy-manifest.yaml` | rh-qs-deploy | rh-qs-security | `pipeline/` |
| `security-report.yaml` | rh-qs-security | rh-qs-debug-and-deploy | `pipeline/` |
| `deploy-state.yaml` | rh-qs-debug-and-deploy | rh-qs-document | `pipeline/` |
| `doc-manifest.yaml` | rh-qs-document | rh-qs-ship | `pipeline/` |

See [pipeline-contracts.md](pipeline-contracts.md) for the YAML schema of each handoff file.

Note: `.qs-factory/designs/architecture-spec.yaml` serves double duty — it is both the architect's spec file and the handoff manifest to scaffold. It has no `-refined` variant; user approval happens on the spec itself.

### 3. Internal working files

Files used within a single skill's execution, not consumed by other skills.

| File Pattern | Skill | Purpose |
|-------------|-------|---------|
| `test-spec.yaml` | rh-qs-implement | Test inventory from test-writer |
| `test-results.yaml` | rh-qs-implement | Test run outcomes |
| `deploy-validation.yaml` | rh-qs-deploy | Deploy reviewer results |
| `qs-security-code.yaml` | rh-qs-security | Code scanner findings |
| `qs-security-containers.yaml` | rh-qs-security | Container scanner findings |
| `qs-security-helm.yaml` | rh-qs-security | Helm scanner findings |
| `qs-security-deps.yaml` | rh-qs-security | Dependency scanner findings |
| `qs-deploy-analysis.yaml` | rh-qs-debug-and-deploy | Deploy command analysis |
| `qs-e2e-results.yaml` | rh-qs-debug-and-deploy | E2E test results |
| `qs-update-analysis.yaml` | rh-qs-update | Change analysis |
| `qs-update-impact.yaml` | rh-qs-update | Impact assessment |
| `qs-handoff-state.yaml` | rh-qs-handoff | Pipeline state detection |
| `qs-handoff-gaps.yaml` | rh-qs-handoff | Gap analysis |
| `qs-kb-components.yaml` | rh-qs-extract-knowledge | Component pattern extraction |
| `qs-kb-deployment.yaml` | rh-qs-extract-knowledge | Deployment pattern extraction |
| `qs-kb-industry.yaml` | rh-qs-extract-knowledge | Industry pattern extraction |
| `qs-kb-security.yaml` | rh-qs-extract-knowledge | Security pattern extraction |
| `qs-kb-update-plan.yaml` | rh-qs-extract-knowledge | KB dedup/update plan |
| `qs-kb-extraction-report.yaml` | rh-qs-extract-knowledge | Extraction summary |

### 4. Debug and fix files

Per-resource debug artifacts that accumulate during the debug loop.

| File Pattern | Skill | Purpose |
|-------------|-------|---------|
| `qs-debug-{resource}.yaml` | rh-qs-debug-and-deploy | Root-cause analysis per resource |
| `qs-fix-{resource}.yaml` | rh-qs-debug-and-deploy | Fix attempt records per resource |

Debug and fix files append `attempt_N` keys — they never overwrite previous attempts. This lets the debugger review what was already tried before proposing a new fix.

## Non-Pipeline Categories (also under `.qs-factory/`)

Three more categories sit alongside `pipeline/` inside `.qs-factory/`, but are human-readable deliverables or generated views rather than skill-to-skill contracts:

| Directory | File | Producing Skill | Purpose |
|-----------|------|------------------|---------|
| `prds/` | `prd.md` | rh-qs-discovery | The PRD — the actual handoff artifact to rh-qs-architect |
| `designs/` | `architecture-spec.yaml`, `architecture-diagram.mmd` | rh-qs-architect | Architecture spec and Mermaid diagram — handoff artifacts to rh-qs-scaffold |
| `flow/` | `dashboard.md` | pipeline-checkpoint.py | Live pipeline progress view |
| `reports/` | `verify-deploy-<date>.md`, etc. | rh-qs-verify-deploy | Per-quickstart reports |

The slug isn't repeated in these filenames — the parent `.rhoai-qs/<slug>/` folder already disambiguates which quickstart a file belongs to. Filenames only need to name the *type* of artifact (`prd`, `architecture-spec`) or add a date when multiple versions can exist over time (`reports/`).

## Factory-Side Locations

Two gitignored folders sit at the **factory root**, not under `.rhoai-qs/` — keeping them out preserves the "every direct child of `.rhoai-qs/` is a quickstart" invariant, and keeping them out of the quickstart repo means ship's cleanup needs no exceptions.

```
quickstart-factory/
├── .blog-drafts/      ← <slug>-YYYY-MM-DD.md
└── .reports/          ← cross-cutting reports, not tied to one quickstart
```

**`.blog-drafts/<slug>-YYYY-MM-DD.md`** — draft announcements from `rh-qs-ship` and `blog-writer`. These are review-before-publication working material with no business in a published quickstart repo. The filename is always slug-prefixed, so one naming rule covers every quickstart whether or not it has a slug folder.

**`.reports/<name>-YYYY-MM-DD.md`** — reports that survey the whole backlog rather than one quickstart: `gap-analysis-<date>.md` from `rh-qs-discovery`'s gap-analysis mode (which runs *before* any slug exists), `grooming-report-<date>.md` from `pipeline-grooming`, and coverage analyses from `quickstart-identifier`. Created on demand.

Per-quickstart reports are a different thing entirely and stay in `.qs-factory/reports/`.

## Cleanup Policy

### During execution

Skills do NOT clean up pipeline files during execution. Files accumulate throughout the pipeline run. This is intentional — it creates a full audit trail and supports resumability.

### User-controlled cleanup

Pipeline files persist until the user explicitly deletes them. To reset a single quickstart's factory bookkeeping without touching its code:

```bash
rm -rf .rhoai-qs/mortgage-processor/.qs-factory/
```

To remove everything for that quickstart, **including its code repo**:

```bash
rm -rf .rhoai-qs/mortgage-processor/
```

This is safe — it only removes that one quickstart's folder, not other quickstarts' data. The user decides when cleanup happens — after shipping, after review, or never. Note the code itself still exists on GitHub (`rh-ai-quickstart/<slug>`) even after deleting the local copy.

This is a different, complementary concern from the **ship-time cleanup** in `rh-qs-ship` (see [`.qs-factory/` is tracked, not gitignored](#qs-factory-is-tracked-not-gitignored)): that one removes `.qs-factory/` from the quickstart's own git history as a standard, non-optional step before shipping, so the published repo doesn't carry it. This section is about the *local* `.rhoai-qs/<slug>/` folder in the factory — always user-controlled, never automatic.

## Concurrency

### Different quickstarts

Different quickstarts share the same `quickstart-factory` repo, but each has its own namespaced folder under `.rhoai-qs/<slug>/` — so running skills for two different quickstarts (in separate sessions) is always safe, as long as each session correctly resolves its own slug (see [Resolving the Quickstart Slug](#resolving-the-quickstart-slug)).

### Same quickstart

Running the same quickstart concurrently (e.g., two agents both running `rh-qs-deploy` for `mortgage-processor` at the same time) is NOT safe. Both would write to the same `.rhoai-qs/mortgage-processor/.qs-factory/pipeline/deploy-spec.yaml`, causing race conditions.

This is a known constraint. The factory is designed for one pipeline execution per quickstart at a time.

## Resumability

Since pipeline files are persistent, resumability works naturally. When a skill starts, after resolving its slug via `validation-skill`, it checks whether `.qs-factory/pipeline/` already contains artifacts from a previous run:

```
1. Resolve the slug (validation-skill)
2. Check if .rhoai-qs/<slug>/.qs-factory/pipeline/ exists
3. If it exists, check for artifacts from this skill and upstream skills
4. If upstream handoff manifests exist:
   → Check content_hash against the current upstream file (see below)
   → If hashes match: offer to resume from current stage
   → If hashes differ: warn that upstream has changed, offer to re-run
   → Or start fresh (rm -rf .rhoai-qs/<slug>/.qs-factory/pipeline/)
5. If this skill's own spec exists:
   → Offer to reuse the existing spec
   → Or regenerate
```

### Staleness detection via content hash

Every spec and manifest records a `content_hash` of the upstream files it was built from (see [spec-as-contract.md](spec-as-contract.md)). When resuming, a skill hashes the current upstream file and compares it to the recorded hash. If they differ, the downstream artifact is stale — the upstream skill was re-run with different results.

This catches the common case where a user re-runs an early stage (e.g., `rh-qs-architect`) but forgets to re-run the stages that depend on it.

This enables the "pick up where you left off" pattern, especially useful when a skill fails mid-execution and the user restarts it.

## Relationship to Other Foundation Docs

- **[validation-skill-template.md](validation-skill-template.md)** — defines the required `validation-skill` subagent every skill uses for Phase 0 slug resolution
- **[pipeline-contracts.md](pipeline-contracts.md)** — defines the YAML schema for each handoff manifest
- **[spec-as-contract.md](spec-as-contract.md)** — defines the spec file format (category 1 above)
- **[skill-directory-structure.md](skill-directory-structure.md)** — each skill's `output-templates.md` defines the format of its temp file outputs; also lists `validation-skill-prompt.md` as a required subagent
