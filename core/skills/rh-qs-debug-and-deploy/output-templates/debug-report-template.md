# Debug Report Output Schema

Write/append to `{state_dir}/debug-{resource_name}.yaml` with this structure.

**Important:** Each attempt is tracked under a `{phase}_attempt_N` key (phase is `health` or `e2e`). On retries, append a new `{phase}_attempt_N` section — do NOT overwrite previous attempts. This preserves full diagnostic history across both phases.

**Order matters:** Root cause FIRST, then proposed fix. Never propose a fix without a clear root cause.

```yaml
resource: app-server
kind: Deployment
namespace: myns

# Key format: {phase}_attempt_{N} — phase is "health" or "e2e"
health_attempt_1:
  # Root cause — identified FIRST before any fix is proposed
  root_cause:
    summary: "SCC restricted-v2 prevents write to /app/data, container runs as non-root but /app/data has root ownership from image build"
    category: security-context | storage | networking | config | image | dependency | resource-limits | other

  # Evidence collected during diagnosis
  diagnostic_evidence:
    - source: "oc logs app-server-6d4c8b-j9m3n -n myns"
      finding: "PermissionError: [Errno 13] Permission denied: '/app/data'"
    - source: "oc describe deployment/app-server -n myns"
      finding: "Back-off restarting failed container, SecurityContext: runAsNonRoot=true"

  # Proposed fix — described but NOT applied
  proposed_fix:
    description: "Add emptyDir volume mount at /app/data so container gets writable directory under restricted-v2 SCC"
    fix_category: config | source-code
    files_to_change:
      - path: chart/templates/app-server.yaml
        what_to_change: "Add volumes section with emptyDir{} and volumeMounts for /app/data"
    redeploy_needed: true

  # These fields are filled by the NEXT attempt's debugger (not by this attempt)
  result: failed
  why_different_now: "Storage issue fixed but revealed networking issue — pod now starts but crashes on DB connection"

health_attempt_2:
  # Root cause — identified FIRST before any fix is proposed
  root_cause:
    summary: "POSTGRES_HOST env var set to 'postgresql' but service name is 'postgresql-svc'"
    category: networking

  # Evidence collected during diagnosis
  diagnostic_evidence:
    - source: "oc logs app-server-7e5d9c-k2n4p -n myns"
      finding: "connection refused to postgresql:5432"
    - source: "oc get svc -n myns"
      finding: "Service is named postgresql-svc, not postgresql"

  # Proposed fix — described but NOT applied
  proposed_fix:
    description: "Change POSTGRES_HOST from 'postgresql' to 'postgresql-svc'"
    fix_category: config
    files_to_change:
      - path: chart/templates/app-server.yaml
        what_to_change: "Update env POSTGRES_HOST value"
    redeploy_needed: true

  # result and why_different_now: not yet filled — this is the latest attempt
```

## On Retries

When this is attempt 2 or higher:
1. Read your own previous `{phase}_attempt_*` entries in `{state_dir}/debug-{resource_name}.yaml` to see what you already diagnosed
2. Read `{state_dir}/fix-{resource_name}.yaml` to see what fixes were applied and their results
3. Update the previous attempt's `result` and `why_different_now` fields based on what happened since that attempt
4. Do NOT propose the same fix that already failed
5. The new root cause may be different (previous fix resolved one layer, exposed another)
