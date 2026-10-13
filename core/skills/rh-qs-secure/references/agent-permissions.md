# Agent permissions and cluster access guardrails

Quickstart Factory agents should operate with **minimal cluster access**. All cluster changes go through **Helm charts and Makefile targets** — never ad-hoc `oc` or `kubectl`.

## Hard rules for agents

1. **No direct cluster commands.** Do not run `oc`, `kubectl`, `helm` against a live cluster unless the user explicitly asks and the command is a documented Makefile target.
2. **Helm-only deployment surface.** Every install, upgrade, and uninstall is expressed as:
   ```bash
   make deploy NAMESPACE=<ns>
   make undeploy NAMESPACE=<ns>
   make verify-deploy NAMESPACE=<ns>
   ```
3. **Do not adopt foreign resources.** If Helm reports ownership conflicts on existing CRs (e.g. shared MLflow), set `create=false` and use service aliases — do not patch annotations on resources owned by other releases.
4. **Namespace scope.** Default to a single project/namespace provided by the user. No cluster-scoped changes unless the design doc requires them and the user approves.

### Exception: `rh-qs-debug-and-deploy`

`rh-qs-debug-and-deploy` is the one skill out of scope for rules 1–2. Diagnosing why a pod is in `CrashLoopBackOff` — logs, events, describe, exec, SCC inspection — cannot be expressed as Helm or Makefile targets, and the fix loop has to re-deploy and re-inspect repeatedly. That skill gets **full `oc` access, not read-only**: it reads *and* mutates cluster state within its namespace.

Rule 4 still binds it without exception: a single namespace (`opg-<slug>-<user>` by default), explicit `-n <namespace>` on **every** command, no cluster-scoped changes. Rule 3 still applies too — it must not adopt resources owned by other releases.

## Access profiles

| Profile | OpenShift role | Use when |
|---------|----------------|----------|
| **Local-only** | None | Scaffold, implement, `helm template`, CI lint |
| **Namespace edit** | `edit` in target namespace | Deploy and verify a dedicated quickstart namespace |
| **Read-only verify** | `view` in target namespace | Human runs deploy; agent only validates docs match Makefile |
| **CI service account** | Scoped token in GitHub Actions | E2E/nightly workflows via `make helm-install-test` |

Prefer **dedicated users or ServiceAccounts** that only have access to the quickstart namespace. Never use cluster-admin for agent or CI automation.

## Deployment sub-agent pattern

For live cluster deployment, **spawn a sub-agent** (Task) with a narrow mandate:

```
Task: Deploy <slug> to namespace <ns>
Allowed: make deploy, make verify-deploy, make helm-lint, make helm-template
Forbidden: oc, kubectl, editing resources outside chart/
Output: verify-deploy log + any values overrides needed for shared services
```

The parent agent wires Helm charts; the sub-agent runs deployment and reports results. Documentation (`rh-qs-document`) runs **after** successful `verify-deploy`.

## MCP server bridge (future / optional)

An MCP server may expose OpenShift operations to Claude with an explicit tool allowlist.

| Tool (example) | Purpose |
|----------------|---------|
| `helm_template` | Render manifests locally |
| `helm_lint` | Lint chart |
| `make_target` | Run allowlisted Makefile targets only |
| `verify_deploy_status` | Read structured output from `make verify-deploy` |

**Do not expose:**

- Generic `kubectl_get`, `kubectl_apply`, `kubectl_delete`
- `oc_login`, `oc_adm`, or cluster-admin operations

Agents may attempt to work around restrictions if generic kubectl is available. Keep the surface **Helm + Makefile** only.

**Status:** Custom Quickstart Factory MCP is not implemented yet. Until then, humans or CI run `make deploy` and `make verify-deploy`; agents prepare charts and docs. The sole exception is `rh-qs-debug-and-deploy`, which runs the deploy and debug loop itself with direct `oc` access — see [Exception: rh-qs-debug-and-deploy](#exception-rh-qs-debug-and-deploy).

## What to record in the design doc

```markdown
## Security considerations — cluster access
- Target namespace: <ns>
- Agent profile: local-only | namespace-edit
- Shared services: <list; alias pattern if any>
- CI profile: <GitHub Actions SA / PROD_TOKEN scope>
- MCP tools (if any): <allowlist>
```
