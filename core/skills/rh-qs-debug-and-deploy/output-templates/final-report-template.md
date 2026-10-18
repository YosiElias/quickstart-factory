# Final Report Template

Print this report to the user at Phase 6 **and** save it to `{state_dir}/deploy-report.md`. Adapt sections based on actual results — skip sections that don't apply.

The saved copy is a local run log for whoever ran the factory — it is not committed and not a handoff. Write it on every outcome, including `PARTIAL SUCCESS` and `E2E FAILURES`; a failed run is exactly when someone needs to read it.

```markdown
# Deployment Report: {quickstart_name}

**Namespace:** {namespace}
**Deployment Method:** {helm | oc-apply | custom}
**Deployment Option:** {label of selected_option_id — omit this line when the project had a single deployment path}
**Status:** {SUCCESS | PARTIAL SUCCESS | E2E FAILURES}

---

## Deployment Summary

| Resource | Kind | Status | Fix Applied |
|----------|------|--------|-------------|
| postgresql | Deployment | Running | - |
| redis | StatefulSet | Running | Fixed: storage class mismatch |
| app-server | Deployment | Running | Fixed: SCC + service name |
| embedding-svc | Deployment | Running | - |

## Issues Found & Fixed

### {resource-name} — {phase} (Attempt {N})
- **Issue:** {brief issue description}
- **Root Cause:** {root cause}
- **Fix:** {what was changed}
- **Files Modified:** {list}

{repeat for each resource that needed fixes — group by phase: health fixes first, then e2e fixes}

## Unresolved Issues
{list any resources where user chose to skip, or issues that couldn't be fixed}
{empty if all resolved}

## E2E Test Results

**Source:** {TEST-PLAN.md}
**Result:** {X}/{Y} tests passed

| Test | Status |
|------|--------|
| PostgreSQL connectivity | PASS |
| Redis connectivity | PASS |
| API health endpoint | FAIL - embedding service port mismatch |

{if failures}
### Failure Details
{clear description of what failed and likely root cause}
{/if}

## Files Modified During Debug
- `chart/templates/app-server.yaml` — added emptyDir volume, fixed env var
- `chart/values.yaml` — updated storage class name

## Artifacts
- Cluster state (handoff to `rh-qs-document`): `{project_path}/pipeline/deploy-state.yaml`
- This report: `{state_dir}/deploy-report.md`
```
