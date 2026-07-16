---
name: github-actions-path-filtered-matrix-quay
description: "Path-filtered matrix builds to Quay.io with skopeo-based backend tag promotion"
summary: "Selective CI/CD for multi-service monorepos — uses GitHub Actions with dorny/paths-filter@v2 to detect changed service directories and matrix-build only modified containers (ui, annotation-interface, clustering, aap-log-collector) to Quay.io, while promoting the backend image via skopeo copy instead of rebuilding. Use when a monorepo has multiple independently-deployable services and you want to avoid rebuilding unchanged images; the backend uses skopeo tag promotion (branch-name tag to latest) for images built outside CI, while other services use docker/build-push-action@v5 with git SHA + latest tags. Uses pull_request_target (not pull_request) for Quay secret access via QUAY_USERNAME/QUAY_PASSWORD repository secrets; separate PR workflows run Ruff lint/format (astral-sh/ruff-action@v3) and pytest via uv (astral-sh/setup-uv@v5 with uv sync --frozen); references Containerfile (Podman convention) not Dockerfile. Backend image must be pre-pushed with branch-name tag (/ replaced with -) by the developer or skopeo promotion fails with a manual-intervention message; pull_request_target checks out base branch code by default; matrix covers only 4 of 7 services — backend, rag, and text-embeddings-inference are managed separately."
metadata:
  type: deployment-pattern
tags:
  tech_stack: [github-actions, podman, skopeo]
  platform: [openshift]
source_examples:
  - quickstart: "ansible-log-analysis"
    repo: "https://github.com/rh-ai-quickstart/ansible-log-analysis"
    notes: "3 workflows: path-filtered matrix build-and-push to Quay on merge, Ruff lint/format check on PR, pytest via uv on PR; backend uses skopeo tag promotion instead of rebuild"
    approach: "A"
---

# GitHub Actions with Path-Filtered Matrix Build and Skopeo Tag Promotion

## Overview

A CI/CD pattern using GitHub Actions with path-based change detection to build only modified service containers, push to Quay.io with git SHA and latest tags, and promote the backend image using skopeo tag copying instead of rebuilding. This is combined with separate PR workflows for linting and testing.

## Pattern Description

The ansible-log-analysis quickstart uses three GitHub Actions workflows. The build-and-push workflow triggers on merged PRs to main, detects which service directories changed using `dorny/paths-filter`, then runs a matrix build that conditionally builds and pushes only the changed services to Quay.io. A separate job promotes the backend image by copying the branch-tagged image to `latest` using skopeo, since the backend image is not built in this workflow (it is built separately, tagged with the branch name).

## Implementation

### Path-Filtered Matrix Build

From `.github/workflows/build-and-push.yml`:

```yaml
name: Build and push image
on:
  pull_request_target:
    types: [closed]
    branches: [main]

jobs:
  detect-changes:
    runs-on: ubuntu-latest
    if: github.event.pull_request.merged == true
    outputs:
      ui: ${{ steps.filter.outputs.ui }}
      annotation: ${{ steps.filter.outputs.annotation }}
      clustering: ${{ steps.filter.outputs.clustering }}
      collector: ${{ steps.filter.outputs.collector }}
    steps:
      - uses: dorny/paths-filter@v2
        id: filter
        with:
          filters: |
            ui:
              - 'services/ui/**'
            annotation:
              - 'services/annotation_interface/**'
            clustering:
              - 'services/clustering/**'
            collector:
              - 'services/aap-log-collector/**'

  build-image:
    needs: detect-changes
    if: github.event.pull_request.merged == true
    strategy:
      matrix:
        include:
          - name: alm-ui
            context: services/ui
            image-name: alm-ui
          - name: alm-annotation-interface
            context: services/annotation_interface
            image-name: alm-annotation-interface
          - name: alm-clustering
            context: services/clustering
            image-name: alm-clustering
          - name: alm-aap-log-collector
            context: services/aap-log-collector
            image-name: alm-aap-log-collector
    steps:
      - uses: actions/checkout@v3
      - uses: docker/setup-buildx-action@v2
      - uses: docker/login-action@v3
        with:
          registry: quay.io
          username: ${{ secrets.QUAY_USERNAME }}
          password: ${{ secrets.QUAY_PASSWORD }}
      - name: Build and push ${{ matrix.name }}
        if: |
          (matrix.image-name == 'alm-ui' && needs.detect-changes.outputs.ui == 'true') ||
          (matrix.image-name == 'alm-annotation-interface' && ...) ||
          ...
        uses: docker/build-push-action@v5
        with:
          context: ${{ matrix.context }}
          file: ${{ matrix.context }}/Containerfile
          push: true
          tags: |
            quay.io/rh-ai-quickstart/${{ matrix.image-name }}:${{ steps.version.outputs.tag }}
            quay.io/rh-ai-quickstart/${{ matrix.image-name }}:latest
```

### Backend Tag Promotion via Skopeo

From `.github/workflows/build-and-push.yml` (tag-backend-latest job):

```yaml
  tag-backend-latest:
    runs-on: ubuntu-latest
    if: github.event.pull_request.merged == true
    steps:
      - name: Extract source branch
        run: |
          BRANCH_NAME="${{ github.event.pull_request.head.ref }}"
          BRANCH_TAG=$(echo "$BRANCH_NAME" | sed 's/\//-/g')
          echo "branch_tag=$BRANCH_TAG" >> $GITHUB_OUTPUT
      - name: Install skopeo
        run: sudo apt-get install -y skopeo
      - name: Tag backend image as latest
        run: |
          skopeo copy \
            --src-creds="$QUAY_USERNAME:$QUAY_PASSWORD" \
            --dest-creds="$QUAY_USERNAME:$QUAY_PASSWORD" \
            docker://quay.io/rh-ai-quickstart/alm-backend:$BRANCH_TAG \
            docker://quay.io/rh-ai-quickstart/alm-backend:latest
```

### PR Lint and Format Check

From `.github/workflows/check-lint-and-format.yml`:

```yaml
name: Check Formatting and Linting
on:
  pull_request:
    types: [opened, synchronize, reopened, edited]
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

### PR Test Suite

From `.github/workflows/test.yml`:

```yaml
name: Run Tests
on:
  pull_request:
    types: [opened, synchronize, reopened, edited]
    branches: [main]
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

- **Key settings:** `pull_request_target` (not `pull_request`) is used for the build workflow, giving it access to secrets; `QUAY_USERNAME` and `QUAY_PASSWORD` are repository secrets
- **Defaults:** Image tags use git short SHA (`git rev-parse --short HEAD`) plus `latest`; skopeo sanitizes branch names by replacing `/` with `-`
- **Dependencies:** Requires Quay.io credentials as GitHub secrets; backend image must be pre-pushed with branch name tag by the developer

## Gotchas

- The backend image is NOT built by this CI workflow. It relies on the developer having pushed the image tagged with the branch name. If the branch-tagged image doesn't exist in Quay, the `tag-backend-latest` job fails with an error message suggesting manual intervention: "Please update the image alm-backend:latest manually from the latest version of main."
- The workflow uses `pull_request_target` instead of `pull_request` to access repository secrets for Quay authentication. This event runs in the context of the base branch, so `actions/checkout@v3` checks out the base branch code by default.
- The `build-push-action` references `${{ matrix.context }}/Containerfile` as the file path, matching the repo's Podman naming convention.
- The build matrix only covers 4 services (ui, annotation-interface, clustering, aap-log-collector), not the backend, rag, or text-embeddings-inference services, which are managed separately.

## Related Patterns

- `container-build-ubi-uv-multistage.md` - The Containerfile patterns that this CI workflow builds
- `container-build-tei-model-prebake.md` - TEI image built separately (not in this CI workflow)
