---
name: ci-precommit-ruff-gitleaks
description: "Pre-commit hooks with Ruff linting/formatting and Gitleaks secret scanning plus custom git hooks"
summary: "Enforces Python code quality (linting/formatting via Ruff v0.12.10) and secret scanning (Gitleaks v8.24.2) through pre-commit hooks, with a local sync-pre-push-hook that auto-installs a custom pre-push hook from .githooks/ to .git/hooks/ on every commit. Use as the standard pre-commit config for Python quickstarts needing automated lint, format, and secret detection both locally and in CI -- CI mirrors checks via astral-sh/ruff-action@v3 running check and format --check, while tests use astral-sh/setup-uv@v5 with uv 0.7.19 and uv sync --frozen. Critical config: the sync hook uses entry: bash -c 'cp .githooks/pre-push .git/hooks/pre-push && chmod +x ...' with always_run: true, pass_filenames: false, and language: system at the pre-commit stage to ensure all developers get the hook without manual setup. The .githooks/pre-push file must exist in the repo or the sync hook fails; uv sync --frozen in CI matches Containerfile builds to prevent lockfile drift (see container-build-ubi-uv-multistage.md); only root-level tests/ runs in CI -- service-level test directories like services/rag/tests/ are excluded."
metadata:
  type: deployment-pattern
tags:
  tech_stack: [python, ruff, gitleaks, pre-commit]
source_examples:
  - quickstart: "ansible-log-analysis"
    repo: "https://github.com/rh-ai-quickstart/ansible-log-analysis"
    notes: "Pre-commit config with Ruff v0.12.10, Gitleaks v8.24.2, and a custom hook that syncs .githooks/pre-push to .git/hooks/ on every commit"
    approach: "A"
---

# Pre-Commit Hooks with Ruff and Gitleaks

## Overview

A code quality and security scanning pattern using pre-commit hooks for Python linting (Ruff), code formatting (Ruff), and secret detection (Gitleaks), combined with a custom hook that maintains a pre-push hook in the `.git/hooks/` directory.

## Pattern Description

The ansible-log-analysis quickstart uses the `pre-commit` framework with three hook sources: the `astral-sh/ruff-pre-commit` repository for Python linting and formatting, the `gitleaks/gitleaks` repository for secret scanning, and a local hook that copies a custom pre-push hook from `.githooks/` to `.git/hooks/` on every commit. The same Ruff checks are enforced in CI via the `astral-sh/ruff-action@v3` GitHub Action.

## Implementation

### Pre-Commit Configuration

From `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.12.10
    hooks:
      - id: ruff
      - id: ruff-format
  - repo: https://github.com/gitleaks/gitleaks
    rev: v8.24.2
    hooks:
      - id: gitleaks
  - repo: local
    hooks:
      - id: sync-pre-push-hook
        name: Sync pre-push hook to .git/hooks
        entry: bash -c 'cp .githooks/pre-push .git/hooks/pre-push && chmod +x .git/hooks/pre-push'
        language: system
        always_run: true
        pass_filenames: false
        stages: [pre-commit]
```

### CI Mirror of Lint Checks

From `.github/workflows/check-lint-and-format.yml`:

```yaml
jobs:
  lint-and-format:
    steps:
      - uses: actions/checkout@v3
      - uses: astral-sh/ruff-action@v3
        with:
          args: 'check'
      - uses: astral-sh/ruff-action@v3
        with:
          args: 'format --check'
```

### Test Workflow with uv

From `.github/workflows/test.yml`:

```yaml
jobs:
  tests:
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
        with:
          version: "0.7.19"
      - run: uv sync --frozen
      - run: uv run pytest tests/ -v
```

## Configuration

- **Key settings:** Ruff version `v0.12.10`; Gitleaks version `v8.24.2`; uv version `0.7.19` in CI
- **Defaults:** Ruff runs both `check` and `format` as separate hooks; Gitleaks runs with default configuration
- **Dependencies:** Requires `pre-commit` installed locally; CI requires GitHub Actions

## Gotchas

- The `sync-pre-push-hook` local hook copies `.githooks/pre-push` to `.git/hooks/pre-push` on every commit. This ensures all developers have the pre-push hook installed without requiring manual setup, but the `.githooks/pre-push` file must exist in the repo.
- The test workflow uses `uv sync --frozen` to ensure the lockfile is not modified during CI, matching the `--frozen` flag used in Containerfile builds.
- The `pytest` test path is `tests/` (at repo root), not the service-level tests like `services/rag/tests/` or `services/annotation_interface/test_end_to_end.py`, which are not run in CI.

## Related Patterns

- `github-actions-path-filtered-matrix-quay.md` - The build-and-push CI workflow that runs alongside these checks
- `container-build-ubi-uv-multistage.md` - Containerfile builds that use the same uv lockfile these hooks validate
