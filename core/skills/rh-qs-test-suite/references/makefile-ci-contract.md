# Makefile CI contract

GitHub Actions should call **Make targets**, not duplicate `uv sync` / `helm` logic. Align `UV_VERSION` in the Makefile with workflow `env.UV_VERSION` (it-self-service-agent uses `0.8.9` as the canonical example).

## Version and dependency hygiene

| Target | CI usage |
|--------|----------|
| `check-uv-version` | Fail if runner uv ≠ Makefile `UV_VERSION` |
| `check-lockfiles` | `uv lock` drift detection |
| `check-requirements` | `requirements.txt` in sync with lockfiles (if pip path used) |
| `deps-all` | Install all workspace packages for lint/test |

## Quality and unit tests

| Target | CI usage |
|--------|----------|
| `lint` / per-linter targets | flake8, black, isort, ruff—match scaffold choices |
| `lint-mypy-per-directory` | Optional; mypy per package |
| `check-logging` | Custom logging policy (if adopted) |
| `test-all` / `test` | pytest across packages |

## Helm validation (no cluster)

| Target | CI usage |
|--------|----------|
| `helm-export-validate-demo` | Render manifests + kubeconform; env `NAMESPACE`, mock `HF_TOKEN` |
| `helm-depend` | `helm dependency build` before Kind install |

## Kind / E2E

| Target | CI usage |
|--------|----------|
| `oc` | Install `oc` CLI into `$GITHUB_WORKSPACE/bin` |
| `build-all-images` | `REGISTRY=localhost:5001`, optional `USE_PIP_INSTALL=true` |
| `push-all-images` | `PUSH_EXTRA_AGRS="--tls-verify=false"` for local registry |
| `namespace` | `NAMESPACE=<test>` |
| `helm-install-test` | Chart install with `LLM`, `LLM_ID`, `LLM_URL`, `LLM_API_TOKEN`, Kind-specific `--set` |
| `helm-uninstall` | Cleanup prod/nightly namespaces |

## Integration tests (name per quickstart)

Examples from it-self-service-agent—replace with design-specific targets:

| Target | Purpose |
|--------|---------|
| `test-session-serialization-integration` | Session store behavior |
| `test-session-reclaim-integration` | Reclaim path |
| `test-short-resp-integration-request-mgr` | Short LLM eval on Request Manager |
| `test-long-resp-integration-request-mgr` | Nightly long eval |

## Evaluations

| Target | CI usage |
|--------|----------|
| `sync-evaluations` | Install eval harness deps (separate uv project or extra) |
| `check-known-bad-conversations` | Regression gate without full deploy |

## Release / versioning

| Target | CI usage |
|--------|----------|
| `version` | Emit semver for image tags (`build-and-push`) |
| `helm-install-prod` | Nightly against real cluster |

## Nightly contract (canonical names)

`subagents/nightly-tests-prompt.md` expects the canonical names `rh-qs-deploy`/`rh-qs-scaffold` already establish: `deploy` (install), `test`, `undeploy` (uninstall), `verify-deploy` (smoke test). Any quickstart that went through `rh-qs-deploy` should already have all three. For older quickstarts missing one, the subagent searches for an equivalent existing target (e.g. `install-full`, `helm-install-prod`, `e2e-ui`, `helm-uninstall`) rather than renaming anything — it uses whatever real name it finds and records the mapping in `.qs-factory/pipeline/nightly-tests-manifest.yaml`.

## Environment variables workflows pass

| Variable | Set by |
|----------|--------|
| `NAMESPACE` | Workflow `env.E2E_NAMESPACE` or job input |
| `REGISTRY` | `localhost:5001` for Kind; `quay.io/rh-ai-quickstart` for push |
| `VERSION` | `steps.version.outputs.version` on prod nightlies |
| `LLM_URL`, `LLM_API_TOKEN`, `LLM_ID`, `LLM` | secrets + vars |

## Monorepo quickstart (packages/*) mapping

| it-self-service-agent style | Quickstart factory layout |
|----------------------------|---------------------------|
| Multi-service `build-all-images` | `make build` or per-package Containerfile targets |
| `helm-install-test` | Kind E2E |
| `verify-deploy` | Post-install smoke — gate before `rh-qs-document` |
| `test-all` | `make test` → turbo/pytest/vitest per design |

Keep target names stable once branch protection references job names tied to those makes.
