# Fix Report Output Schema

Write/append to `{state_dir}/fix-{resource-name}.yaml` with this structure.

**Important:** Each attempt is tracked under a `{phase}_attempt_N` key (phase is `health` or `e2e`). On retries, append a new `{phase}_attempt_N` section — do NOT overwrite previous attempts. Both the debugger and fix applier read this file on retries to understand what was already tried.

```yaml
resource: app-server
kind: Deployment
namespace: myns

# Key format: {phase}_attempt_{N} — phase is "health" or "e2e"
health_attempt_1:
  debugger:
    issue: "CrashLoopBackOff - permission denied writing to /app/data"
    root_cause: "SCC restricted-v2 prevents write to /app/data"
    proposed_fix: "Add emptyDir volume mount at /app/data"
  fix_applier:
    best_practice_source: "Red Hat docs - emptyDir volumes under restricted-v2 SCC"
    best_practice_check: "Red Hat docs confirm emptyDir is the correct pattern for writable temp dirs under restricted-v2 SCC"
    alternative_considered: "Could use PVC but emptyDir is simpler for temp data"
    chosen_fix: "emptyDir volume mount (aligns with debugger proposal + Red Hat best practice)"
    fix_applied: "Added emptyDir volume mount at /app/data, set securityContext runAsNonRoot"
    fix_category: config
    files_modified:
      - path: chart/templates/app-server.yaml
        change: "Added volumes section with emptyDir{}, volumeMounts for /app/data"
    redeploy_command: "helm upgrade my-quickstart ./chart -n myns --set openshiftMode=true"
    result: failed
    post_fix_status: "Still CrashLoopBackOff - different error: connection refused to postgresql:5432"
    user_approval_required: false

health_attempt_2:
  debugger:
    issue: "CrashLoopBackOff - connection refused to postgresql:5432"
    root_cause: "POSTGRES_HOST env var set to 'postgresql' but service name is 'postgresql-svc'"
    proposed_fix: "Change POSTGRES_HOST from 'postgresql' to 'postgresql-svc'"
  fix_applier:
    best_practice_source: "Kubernetes service DNS naming convention"
    best_practice_check: "Service name in K8s DNS is the metadata.name of the Service resource"
    alternative_considered: "None - straightforward service name mismatch"
    chosen_fix: "Update POSTGRES_HOST env var to match actual service name"
    fix_applied: "Updated POSTGRES_HOST env var in deployment template from 'postgresql' to 'postgresql-svc'"
    fix_category: config
    files_modified:
      - path: chart/templates/app-server.yaml
        change: "Changed env POSTGRES_HOST value from 'postgresql' to 'postgresql-svc'"
    redeploy_command: "helm upgrade my-quickstart ./chart -n myns --set openshiftMode=true"
    result: success
    post_fix_status: "Running, 1/1 ready"
    user_approval_required: false
```

## Rules

- Never overwrite previous attempts — always append under next `{phase}_attempt_N`
- `fix_category` is either `config` (auto-applied) or `source-code` (may need user approval)
- `user_approval_required: true` when the fix changed non-OpenShift source code and user was asked
- `result` is one of: `success`, `failed`, `partial`
- `post_fix_status` is what `oc get` shows after the fix was applied
