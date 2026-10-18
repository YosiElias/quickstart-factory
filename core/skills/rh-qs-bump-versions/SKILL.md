---
name: rh-qs-bump-versions
description: |
  Update dependency and chart versions across an AI Quickstart monorepo. Bumps Python (uv),
  Node (pnpm), Helm subcharts, and container base images with lockfile refresh and verification.
  Use when upgrading packages, patching CVEs, or aligning with a new OpenShift AI release.
---

# rh-qs-bump-versions

**Category:** `maintenance/`

## Trigger

- Security patch or CVE in a dependency
- New **ai-architecture-charts** or OpenShift AI release
- User asks to upgrade Python, Node, Llama Stack, or subchart versions
- Periodic maintenance before **`rh-qs-ship`**

## What it does

1. Inventories version pins: `pyproject.toml`, `package.json`, `Chart.yaml`, Containerfiles, workflow `env` blocks
2. Proposes a **minimal bump plan** (only what the user requested or what CVEs require)
3. Updates versions and refreshes lockfiles (`uv lock`, `pnpm install`)
4. Runs quality gates: `make lint`, `make test`, `make helm-lint`, `make helm-template`
5. Optionally re-runs **`rh-qs-verify-build`** and **`rh-qs-verify-deploy`** when cluster-facing charts change

## Workflow

```
- [ ] 1. List current pins (grep Chart.yaml, pyproject.toml, package.json, .github/workflows)
- [ ] 2. Confirm bump scope with user (single package vs platform-wide)
- [ ] 3. Bump versions in source files — keep Makefile UV_VERSION / tool pins in sync with CI
- [ ] 4. Refresh lockfiles (uv lock, pnpm install --lockfile-only)
- [ ] 5. Run make lint && make test && make helm-lint && make helm-template
- [ ] 6. Document changes in PR body or CHANGELOG snippet
- [ ] 7. If Helm subcharts changed → recommend rh-qs-verify-deploy on a test namespace
```

## Version locations

| Artifact | Typical files |
|----------|---------------|
| Python packages | `packages/*/pyproject.toml`, root `uv.lock` |
| Node packages | `packages/*/package.json`, `pnpm-lock.yaml` |
| Helm app chart | `chart/Chart.yaml` (`version`, `appVersion`) |
| Helm subcharts | `dependencies[]` in `Chart.yaml` — pin from [ai-architecture-charts](https://github.com/rh-ai-quickstart/ai-architecture-charts) |
| Container bases | `Containerfile` `FROM` lines |
| CI tool pins | `.github/workflows/*.yml` `env:` (`UV_VERSION`, Helm installer version) |
| Gaussia / SDK specs | Helm values or provider env (`packageSpec`, `evalhubSdkSpec`) |

## Rules

- **Pin, do not float.** Prefer explicit versions over `@latest` in production paths
- **One concern per PR** when possible — easier to bisect failures
- **Never** bump secrets or credentials
- After subchart major bumps, read upstream changelog for breaking value renames

## Commands (examples)

```bash
# Python
uv lock --upgrade-package <name>

# Node
pnpm update <name> --filter <package>

# Helm subchart
helm dependency update chart/

# Verify
make lint test helm-lint helm-template
```

## Output

- Updated version pins and lockfiles
- Short summary of what changed and why
- Recommendation to run verify-build / verify-deploy when deploy surface changed

## References

- [ai-architecture-charts](https://github.com/rh-ai-quickstart/ai-architecture-charts)
- [Makefile CI contract](../rh-qs-test-suite/references/makefile-ci-contract.md)
- **`rh-qs-verify-build`** — local build after bump
- **`rh-qs-verify-deploy`** — cluster check after chart bump
