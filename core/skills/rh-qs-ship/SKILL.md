---
name: rh-qs-ship
description: Ship an AI Quickstart. Creates a pull request with structured summary, generates a blog post draft, and updates backlog status. Use when documentation is complete from rh-qs-document.
---

# rh-qs-ship

**Category:** `github/`  
**Replaces:** rh-qs-gh-pr-creator, rh-qs-blog-writer, rh-qs-release-management

## Trigger

Documentation is complete from `rh-qs-document`

## Where This Runs

This skill works inside `.rhoai-qs/<slug>/` — the scaffolded quickstart's own repo, since it creates a PR against that repo. `rh-qs-ship` is also where `.qs-factory/` gets **removed** — the PRD, design, pipeline state, and dashboard were tracked and pushed throughout development so the team could collaborate on them, but the finished, published quickstart shouldn't carry internal factory bookkeeping. See [pipeline-convention.md](../../../docs/foundation/pipeline-convention.md#nested-quickstart-repos).

`.qs-factory/` has no exceptions — everything inside it goes, so the cleanup is one `git rm -r` with no pathspec to maintain. The blog draft is the reason that used to be untrue, and it now lives in the factory repo at `.blog-drafts/<slug>-<date>.md`, outside the quickstart entirely.

## What it does

1. Creates a **pull request** with structured summary (what was built, how to test, architecture diagram)
2. Generates a **blog post draft** for announcing the quickstart (using messaging guidelines)
3. Updates the **quickstart backlog** (marks issue in-progress or done)
4. Provides the **PR URL** and next steps for human review

## Workflow

### Phase 0: Resolve Quickstart Context

Before doing anything, resolve which quickstart this session is for. Run `ls -1 ../ 2>/dev/null` (every entry is a quickstart — no filtering) and spawn the **validation-skill subagent**:

```python
Agent(
    description="Resolve which quickstart this ship session is for",
    prompt=f"""
Read and follow instructions from:
core/skills/rh-qs-ship/subagents/validation-skill-prompt.md

User message: {user_message}
Existing slugs: {existing_slugs}
Is entry point: false
Calling skill: rh-qs-ship
"""
)
```

Handle the result per [validation-skill-template.md](../../../docs/foundation/validation-skill-template.md#main-agent-handling).

### Remaining phases

```
- [ ] 1. Verify git state (no secrets committed)
- [ ] 2. Draft blog post (writes .blog-drafts/<slug>-<date>.md in the factory repo)
- [ ] 3. Clean up factory bookkeeping (remove .qs-factory/ — all of it)
- [ ] 4. Create pull request (includes the bookkeeping removal as part of the diff)
- [ ] 5. Update backlog issue
- [ ] 6. Return PR URL and review checklist
```

### Blog post draft

1. Fetch issue: `python3 core/skills/github/rh-qs-gh-backlog-reader/scripts/read_backlog.py --issue <N>`
2. Read repo README and architecture
3. Draft using [assets/blog-template.md](./assets/blog-template.md) and [references/messaging-guidelines.md](./references/messaging-guidelines.md)

**Required links:**

- Catalog: https://docs.redhat.com/en/learn/ai-quickstarts
- Implementation repo URL
- Contrib: https://github.com/rh-ai-quickstart/ai-quickstart-contrib

Save to **`.blog-drafts/<slug>-YYYY-MM-DD.md`** in the quickstart-factory repo — from inside the quickstart that is `../../.blog-drafts/<slug>-$(date +%F).md`. It is gitignored there, so the draft is never part of any commit, in this repo or the quickstart's. Drafts require human review before publication; leave it for the user to remove once the post is actually published.

### Clean up factory bookkeeping

Now that the PRD, design, and pipeline state have served their purpose — collaborative development via normal PRs — remove them so the finished, published quickstart doesn't carry internal factory bookkeeping:

```bash
git rm -r --ignore-unmatch .qs-factory
git commit -m "chore: remove factory pipeline bookkeeping before shipping"
```

One pathspec, no exceptions: everything under `.qs-factory/` goes, including `flow/dashboard.md`. `--ignore-unmatch` only guards the case where the folder is already gone (e.g. ship re-run after a partial cleanup).

No `.gitignore` entry is needed afterwards — `git rm -r` removes the files from the working tree as well as the index, and nothing re-creates them.

### Create pull request

This removal commit is included as part of the PR being created below — reviewers will see the bookkeeping cleanup alongside the final implementation changes.

Dry-run first:

```bash
python3 core/skills/github/rh-qs-ship/scripts/create_pr.py --dry-run
python3 core/skills/github/rh-qs-ship/scripts/create_pr.py --base main
```

| Mode | When |
|------|------|
| `branch` (default) | All commits on feature branch vs base |
| `last-commit` | Only latest commit |
| `working-tree` | Commit staged + unstaged, then PR |

**PR body template:**

```markdown
## Summary
- What was built and why
- Key components (from design doc)

## Architecture
- Link to diagram in docs/images/

## Test plan
- [ ] make lint
- [ ] make test
- [ ] make dev — health check
- [ ] helm lint / template
- [ ] Deploy to OpenShift (if tested)

## Related issue
- Closes rh-ai-quickstart/ai-quickstart-contrib#<N>
```

**Safety:** Never force-push to main. Never commit `.env` or credentials.

### Update backlog

Comment on or close the related contrib issue. Mark in-progress during review, closed when merged and catalog-ready.

## Standalone usage

| Request | Action |
|---------|--------|
| "Create PR" / "Open pull request" | PR workflow only — includes the bookkeeping cleanup step |
| "Write blog draft" / "Announce quickstart" | Blog workflow only — does **not** trigger bookkeeping cleanup, since the quickstart isn't necessarily shipping yet |

## Output

| Artifact | Path |
|----------|------|
| Pull request | GitHub URL |
| Blog draft | `.blog-drafts/<slug>-<date>.md` (quickstart-factory repo, gitignored) |

## References

- [Blog template](./assets/blog-template.md)
- [Messaging guidelines](./references/messaging-guidelines.md)
- [subagents/validation-skill-prompt.md](./subagents/validation-skill-prompt.md) — pass by file path only, do NOT read directly

## Closing message

`rh-qs-ship` runs **no pipeline checkpoint** — it just deleted the dashboard, so there is nothing left to update. Close with a plain message instead:

> "Factory bookkeeping removed — `.qs-factory/` (including the pipeline dashboard) is staged for deletion in this PR. The blog draft is at `.blog-drafts/<slug>-<date>.md` in the factory repo."
