---
name: blog-writer
description: Generate blog post drafts for completed AI Quickstarts. Use when announcing new quickstarts to Red Hat audience.
---

# blog-writer

## Purpose

Generate blog post drafts for completed AI Quickstarts. Outputs to `.blog-drafts/` in the quickstart-factory root. Drafts require review before publication.

## Workflow

1. **Identify candidate:** Use `gh-backlog-reader --issue <N>` to view the issue, its comments, and linked repositories.
2. **Gather context:** If a linked implementation repo exists (auto-extracted from comments), browse the repo README and code to understand what the quickstart does, its architecture, and how to run it.
3. **Study reference examples:** Fetch the example blog posts listed in [references/blog-examples.md](references/blog-examples.md) using WebFetch. Analyze their structure, tone, and business framing. Use them as stylistic guides — match their narrative depth and enterprise perspective, not just the template structure.
4. **Draft the blog post:** Use the format and template below.

Issues with an implementation repo linked in the comments are prime candidates for blog posts — the quickstart is being built or is already done.

## Blog Format Selection

Choose format based on quickstart type:
- **Standard announcement:** Use template (Hook, What It Does, How It Works, Get Started, What's Next, CTA)
- **Technical deep-dive:** Add architecture diagram, code snippets
- **Use case spotlight:** Emphasize industry and outcome

## Standard Links

Include in every blog post:
- **Catalog:** https://docs.redhat.com/en/learn/ai-quickstarts
- **Repository:** Link to the quickstart's implementation GitHub repo (from issue comments)
- **Contrib:** https://github.com/rh-ai-quickstart/ai-quickstart-contrib

## Output

`.blog-drafts/<quickstart-slug>-YYYY-MM-DD.md` in the quickstart-factory root — e.g. `.blog-drafts/vllm-cpu-2025-03-11.md`.

One rule, no conditionals: the path works whether or not the quickstart has a slug folder under `.rhoai-qs/`, which matters because blog-writer is often run against an older quickstart that never went through the factory pipeline. Drafts are factory-side working material — review-before-publication artifacts with no business in a published quickstart repo — so they live outside `.rhoai-qs/` and are gitignored. See [pipeline-convention.md](../../../docs/foundation/pipeline-convention.md#factory-side-locations).

## References

- **Template:** [assets/blog-template.md](assets/blog-template.md)
- **Messaging:** [references/messaging-guidelines.md](references/messaging-guidelines.md)
- **Examples:** [references/blog-examples.md](references/blog-examples.md)
