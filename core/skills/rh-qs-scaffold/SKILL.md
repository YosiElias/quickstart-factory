---
name: rh-qs-scaffold
description: Scaffold a new AI Quickstart GitHub repository with CI/CD, linting, testing frameworks, monorepo structure, branch protection, and Makefile targets. Use when a design document is approved from rh-qs-architect.
---

# rh-qs-scaffold

**Category:** `github/`  
**Replaces:** rh-qs-repo-bootstrap, rh-qs-github-project-management, rh-qs-cicd-automation, rh-qs-testing-validation

## Trigger

Architecture spec approved from `rh-qs-architect` at `.rhoai-qs/<slug>/.qs-factory/designs/architecture-spec.yaml`

## What it does

1. Verifies the quickstart repo already exists and is pushed to `rh-ai-quickstart/<slug>`
2. Configures branch protection: require CI passing, require 1 review, no direct push to main
3. Creates directory structure based on the design
4. Sets up GitHub Actions: minimal CI (lint + unit tests on PR); full Kind/E2E/evals → **`rh-qs-test-suite`** after deploy
5. Configures linting: ruff + ruff format (Python), eslint + prettier (TypeScript)
6. Sets up testing: pytest, vitest, playwright (e2e)
7. Configures pre-commit hooks: ruff, eslint, type checking
8. Creates Makefile with standard targets
9. Creates `.env.example` with documented environment variables
10. Initializes `turbo.json` for monorepo orchestration

## Workflow

### Phase 0: Resolve Quickstart Context

Before doing anything, resolve which quickstart this session is for. Run `ls -1 .rhoai-qs/ 2>/dev/null` (every entry is a quickstart — no filtering) and spawn the **validation-skill subagent**:

```python
Agent(
    description="Resolve which quickstart this scaffold session is for",
    prompt=f"""
Read and follow instructions from:
core/skills/rh-qs-scaffold/subagents/validation-skill-prompt.md

User message: {user_message}
Existing slugs: {existing_slugs}
Is entry point: false
Calling skill: rh-qs-scaffold
"""
)
```

Handle the result per [validation-skill-template.md](../../../docs/foundation/validation-skill-template.md#main-agent-handling). If `resolution: error` (no slugs exist), tell the user to run `rh-qs-discovery` and `rh-qs-architect` first and stop.

### Remaining phases

```
- [ ] 1. Verify the repo precondition
- [ ] 2. Configure branch protection
- [ ] 3. Scaffold directory structure
- [ ] 4. Add GitHub Actions workflows
- [ ] 5. Configure linting + pre-commit
- [ ] 6. Scaffold test frameworks
- [ ] 7. Add Makefile + turbo.json + .env.example
- [ ] 8. Push initial commit and verify CI
```

### Repo precondition

Scaffold does **not** create the repo. `rh-qs-discovery` already seeded `.rhoai-qs/<slug>/` from [ai-quickstart-template](https://github.com/rh-ai-quickstart/ai-quickstart-template) and committed it locally, and the user already pushed it to `rh-ai-quickstart/<slug>`. Verify both before touching anything:

```bash
DIR=".rhoai-qs/<slug>"
[ -d "$DIR/.git" ] || { echo "ERROR: $DIR is not a git repo"; exit 1; }
git -C "$DIR" remote get-url origin || { echo "ERROR: no origin remote"; exit 1; }
```

If either check fails, **stop** and tell the user to push the repo first with the command `rh-qs-discovery` printed at the end of its run:

```bash
cd .rhoai-qs/<slug>
gh repo create rh-ai-quickstart/<slug> --public --source=. --remote=origin --push \
  --description "<one-liner from the PRD>"
```

Do not work around a missing remote by creating the repo yourself — branch protection and CI both target `rh-ai-quickstart/<slug>`, and who creates it under that org is the user's call.

**Do NOT gitignore `.qs-factory/` in this repo.** It stays tracked and gets pushed to the quickstart's own GitHub remote throughout development — this is intentional, so the team can collaborate on the PRD, design doc, and pipeline state via normal pull requests (e.g., reviewing a design doc together), not just on one engineer's local machine. It is removed wholesale as a final cleanup step in `rh-qs-ship`, right before the quickstart is considered done. See [pipeline-convention.md](../../../docs/foundation/pipeline-convention.md#nested-quickstart-repos) for the full rationale.

### Branch protection

- Require pull request reviews (minimum 1)
- Require status checks (CI workflow) before merge
- Require branches up to date before merging
- Restrict direct pushes to `main`
- Do not allow bypassing the above

## Repository structure

This lives at `.rhoai-qs/<slug>/`. Entries marked **(template)** already exist — discovery seeded them from `ai-quickstart-template` and scaffold must not recreate or overwrite them. `.qs-factory/` is factory bookkeeping from earlier phases, tracked and pushed like everything else during development so the team can collaborate on the PRD, design, etc., then removed wholesale as a final cleanup step in `rh-qs-ship` (see Repo precondition above). Everything else is what scaffold adds:

```
.rhoai-qs/<slug>/               # = this repo's root
├── .qs-factory/                 # ─┐  factory bookkeeping — tracked during
│   ├── prds/                    #  │  development, removed by rh-qs-ship
│   ├── designs/                 #  │  right before the quickstart is done
│   ├── pipeline/                #  │
│   ├── flow/                    #  │
│   └── reports/                 # ─┘
│
├── .github/
│   ├── workflows/
│   │   ├── ci.yaml              # Lint + unit tests (runs on PR)
│   │   ├── integration.yaml     # Integration tests (runs on merge to main)
│   │   └── deploy.yaml          # Deploy to OpenShift (manual trigger)
│   ├── CODEOWNERS
│   └── pull_request_template.md
├── packages/
│   ├── api/                     # FastAPI application
│   │   ├── src/
│   │   ├── tests/
│   │   ├── Containerfile
│   │   ├── pyproject.toml
│   │   └── ruff.toml
│   ├── ui/                      # React + Vite application
│   │   ├── src/
│   │   ├── tests/
│   │   ├── Containerfile
│   │   ├── package.json
│   │   ├── eslint.config.js
│   │   └── vite.config.ts
│   ├── db/                      # SQLAlchemy + Alembic
│   │   ├── src/
│   │   ├── alembic/
│   │   └── pyproject.toml
│   └── ingestion/               # (if RAG) Document ingestion job
│       ├── src/
│       ├── tests/
│       └── pyproject.toml
├── chart/                       # (template) Helm chart — fill in, do not move
│   ├── Chart.yaml               #   name + maintainer already substituted
│   ├── values.yaml
│   └── templates/
├── tests/
│   ├── integration/
│   └── e2e/
│       └── playwright.config.ts
├── docs/
│   └── images/                  # (template) architecture diagrams
├── compose.yml
├── Makefile
├── turbo.json
├── .env.example
├── .pre-commit-config.yaml
├── .gitignore
├── LICENSE                      # (template)
└── README.md                    # (template) catalog skeleton — rh-qs-document
                                 #   fills its CONTRIBUTOR TODO blocks in place
```

The chart lives at `chart/` — the org template's layout, and what the catalog tooling expects. Do not introduce a `deploy/helm/<slug>/` path.

## GitHub Actions CI (ci.yaml)

**Trigger:** Pull request to main

| Job | Command |
|-----|---------|
| lint-python | `ruff check` + `ruff format --check` |
| lint-typescript | `eslint` |
| type-check | pyright/mypy + `tsc` |
| unit-tests-api | `pytest packages/api/` |
| unit-tests-ui | `vitest packages/ui/` |
| helm-lint | `helm lint chart/` |

All jobs must pass before PR can merge.

## Makefile targets

```makefile
setup              # pnpm install + uv sync
dev                # podman-compose local stack
lint               # ruff + eslint
test               # unit tests
test-integration   # integration tests
test-e2e           # playwright
deploy             # helm upgrade --install (Helm only — no oc/kubectl in docs)
undeploy           # helm uninstall
verify-deploy      # post-install smoke test
```

## Linting configuration

**Python (`ruff.toml`):**

```toml
line-length = 120
target-version = "py312"
select = ["E", "F", "W", "I", "UP", "B", "SIM"]
```

**TypeScript:** ESLint recommended + typescript-eslint strict, Prettier integration, React hooks rules.

## Output

A GitHub repository with CI/CD configured, project structure created, and linting/testing ready to use. No domain logic yet.

## Verification

```bash
make lint
helm lint chart/
```

## Next skill

When scaffold is pushed and CI is green → **`rh-qs-implement`**

## References

- [ai-quickstart-template](https://github.com/rh-ai-quickstart/ai-quickstart-template)
- [it-self-service-agent CI patterns](../rh-qs-test-suite/SKILL.md) — production workflow split (post-deploy)
- Architecture spec: `.rhoai-qs/<slug>/.qs-factory/designs/architecture-spec.yaml`
- [subagents/validation-skill-prompt.md](./subagents/validation-skill-prompt.md) — pass by file path only, do NOT read directly

## Pipeline checkpoint

Run the checkpoint:

```bash
python3 core/flow/pipeline-checkpoint.py --skill-name rh-qs-scaffold --qs-name {qs-name}
```
Print the dashboard link to the user:
"Pipeline dashboard updated — track progress at [dashboard.md](.rhoai-qs/{qs-name}/.qs-factory/flow/dashboard.md)"
