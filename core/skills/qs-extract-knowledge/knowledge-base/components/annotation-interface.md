---
name: annotation-interface
description: "Gradio-based data annotation UI for reviewing AI pipeline outputs and running LLM-as-judge evaluations"
summary: "Provides a Gradio dark-themed human-in-the-loop annotation UI for reviewing AI pipeline outputs from PostgreSQL, with integrated deepeval GEval LLM-as-judge evaluation (root cause accuracy + solution steps alignment, 1-10 scale) via vLLM OpenAI-compatible endpoint. Use when a quickstart needs annotators to review AI outputs, provide golden solutions, and run batch or per-entry LLM evaluation against them -- sourced from ansible-log-analysis (Approach A); supports cluster sampling toggle for grouped log messages. DATABASE_URL injected from pgvector secret key `uri` requires runtime conversion from asyncpg to psycopg2 via `.replace(\"+asyncpg\", \"\").replace(\"postgresql\", \"postgresql+psycopg2\")`; table set via ALERTS_TABLE_NAME; model-secret provides OPENAI_MODEL/API_ENDPOINT/API_TOKEN/TEMPERATURE for deepeval; Helm init container seeds annotation.json to PVC only if absent; serves on port 7861 with OpenShift Route edge TLS. Deepeval needs `chmod 777 /app/.deepeval` and `HOME=/app` for non-root containers; DATABASE_URL string replace silently produces wrong connection string if secret format changes; pod blocks on backend-init job via `oc wait --timeout=600s` and is stuck if that job is missing; UndefinedTable is caught gracefully when the pipeline hasn't populated the table yet."
metadata:
  type: component
tags:
  tech_stack: [gradio, python, sqlalchemy, psycopg2, deepeval, pandas]
  ai_pattern: [evaluation, data-pipeline]
  platform: [openshift, rhoai]
  data_layer: [pgvector]
source_examples:
  - quickstart: "ansible-log-analysis"
    repo: "https://github.com/rh-ai-quickstart/ansible-log-analysis"
    notes: "Gradio annotation interface for reviewing Ansible log error analysis pipeline outputs with integrated deepeval LLM-as-judge evaluation"
    approach: "A"
---

# Annotation Interface

## Overview

A Gradio-based web application that provides a human-in-the-loop annotation interface for reviewing AI pipeline outputs. In quickstart architectures it sits downstream of a processing pipeline, reads structured results from PostgreSQL, and lets annotators provide feedback, golden solutions, and context assessments. It also integrates LLM-as-judge evaluation via deepeval to score AI-generated solutions against human-authored golden answers.

## Tech Stack & Dependencies

- **Runtime:** Python 3.12 on `registry.access.redhat.com/ubi8/python-312`
- **Container image:** `quay.io/rh-ai-quickstart/alm-annotation-interface:latest`
- **Key dependencies:** gradio>=5.42.0, deepeval>=3.7.9, sqlalchemy>=2.0.0, psycopg2-binary>=2.9.0
- **Package manager:** uv (copied from `ghcr.io/astral-sh/uv:0.9.7` multi-stage)
- **Helm subchart:** `annotation-interface` (v0.1.0) under `deploy/helm/ansible-log-monitor/charts/annotation-interface/`

## Key Patterns

### Gradio Dark-Themed Annotation UI

The interface uses `gr.Blocks` with a `gr.themes.Soft` theme customized for a dark palette, plus injected JavaScript to force dark mode via URL parameter. The UI is organized into sections: navigation, AI-generated outputs (toggleable), and human annotation tabs.

```python
# From services/annotation_interface/app.py
head_js = """
<script>
    const url = new URL(window.location);
    if (url.searchParams.get('__theme') !== 'dark') {
        url.searchParams.set('__theme', 'dark');
        window.location.href = url.href;
    }
</script>
"""
with gr.Blocks(
    css=css,
    head=head_js,
    theme=gr.themes.Soft(
        primary_hue="indigo",
        secondary_hue="blue",
        neutral_hue="slate",
    ).set(
        body_background_fill="*neutral_950",
        block_background_fill="*neutral_900",
    ),
    title="Ansible Log Annotation Interface",
) as interface:
```

### SQLAlchemy Database Loading with Dynamic Table Name

The component connects to PostgreSQL using SQLAlchemy and reads from a configurable table name set via the `ALERTS_TABLE_NAME` environment variable. It converts the asyncpg-style DATABASE_URL to a psycopg2-compatible one at runtime.

```python
# From services/annotation_interface/app.py
self.table_name = os.getenv("ALERTS_TABLE_NAME", "grafanaalert")
self.engine = create_engine(
    os.getenv("DATABASE_URL")
    .replace("+asyncpg", "")
    .replace("postgresql", "postgresql+psycopg2")
)
```

### Cluster Sampling Toggle

Supports toggling between showing all data rows and showing one sample per log cluster. This is useful when the upstream pipeline groups similar log messages into clusters and the annotator wants to review one representative per cluster.

```python
# From services/annotation_interface/app.py
def toggle_cluster_sampling(self, show_sample: bool):
    if show_sample:
        cluster_samples = {}
        for entry in self.all_data:
            cluster_id = entry.get("log_cluster")
            if cluster_id is None:
                cluster_id = f"_no_cluster_{entry.get('id')}"
            if cluster_id not in cluster_samples:
                cluster_samples[cluster_id] = entry
        self.data = list(cluster_samples.values())
```

### Deepeval LLM-as-Judge Evaluation

Integrates deepeval's `GEval` metric with a `LocalModel` pointing at a vLLM-served model (via OpenAI-compatible API). Defines custom evaluation metrics for root cause accuracy and solution steps alignment, scored on a 1-10 scale.

```python
# From services/annotation_interface/test_end_to_end.py
llm_vllm = LocalModel(
    model=os.environ.get("OPENAI_MODEL"),
    base_url=os.environ.get("OPENAI_API_ENDPOINT"),
    api_key=os.environ.get("OPENAI_API_TOKEN"),
    temperature=float(os.environ.get("OPENAI_TEMPERATURE")),
)

root_cause_metric = GEval(
    name="Root Cause Accuracy",
    criteria="Evaluate whether the actual output correctly identifies the same root cause...",
    evaluation_params=[
        LLMTestCaseParams.INPUT,
        LLMTestCaseParams.ACTUAL_OUTPUT,
        LLMTestCaseParams.EXPECTED_OUTPUT,
    ],
    model=llm_vllm,
)
```

### Annotation Persistence with Atomic Writes

Feedback is persisted to a JSON file (`data/feedback/annotation.json`). The write uses a temp-file-then-rename pattern for atomicity, and evaluation results are merged back into the same file.

```python
# From services/annotation_interface/app.py
temp_file = self.feedback_file + ".tmp"
with open(temp_file, "w") as f:
    json.dump(self.feedback_data, f, indent=2)
os.replace(temp_file, self.feedback_file)
```

### Init Container for Data Seeding

The Helm deployment uses an init container to copy the seed `annotation.json` from the container image to the PVC only if it does not already exist, preserving user annotations across pod restarts.

```yaml
# From deploy/helm/.../annotation-interface/templates/deployment.yaml
- name: init-annotation-data
  image: "{{ .Values.image.repository }}:{{ .Values.image.tag }}"
  command:
    - sh
    - -c
    - |
      if [ -f /mnt/data/feedback/annotation.json ]; then
        echo "annotation.json already exists, skipping copy."
      else
        mkdir -p /mnt/data/feedback
        cp /app/data/feedback/annotation.json /mnt/data/feedback/annotation.json
      fi
  volumeMounts:
    - name: data-volume
      mountPath: /mnt/data
```

## Configuration

- **Environment variables:**
  - `DATABASE_URL` -- PostgreSQL connection string (injected from `pgvector` secret key `uri`)
  - `ALERTS_TABLE_NAME` -- Database table to read pipeline results from (default: `grafanaalert`)
  - `GRADIO_SERVER_NAME` -- Bind address (default: `0.0.0.0`)
  - `GRADIO_SERVER_PORT` -- Listen port (default: `7861`)
  - `OPENAI_MODEL`, `OPENAI_API_ENDPOINT`, `OPENAI_API_TOKEN`, `OPENAI_TEMPERATURE` -- Model serving config for deepeval evaluations (injected from `model-secret` secret via `envFrom`)
  - `PYTHONPATH` -- Set to `/app` in the container
- **Config files:** `data/feedback/annotation.json` -- persisted annotation data (mounted from PVC)
- **Helm values:**
  - `image.repository` / `image.tag` -- Container image reference
  - `persistence.enabled` / `persistence.size` -- PVC for annotation data (default: 1Gi, ReadWriteOnce)
  - `route.enabled` -- OpenShift Route with edge TLS termination
  - `service.port` / `service.targetPort` -- Both default to `7861`
  - `env` -- List of environment variables injected into the deployment

## Known Gotchas

- **DATABASE_URL format conversion:** The app receives an asyncpg-style DATABASE_URL but needs psycopg2, so it does a string replace at runtime (`.replace("+asyncpg", "").replace("postgresql", "postgresql+psycopg2")`). If the URL format from the secret changes, this conversion will silently produce a wrong connection string.
- **Deepeval cache directory permissions:** The Containerfile explicitly creates `/app/.deepeval` with `chmod 777` and sets `HOME=/app` because deepeval tries to create a cache directory under `$HOME` and fails with PermissionError when running as non-root. This is documented in a comment in the Containerfile.
- **Init container dependency on backend-init job:** The deployment waits for a backend init job to complete (`oc wait --for=condition=complete --timeout=600s job/<backend>-init`). If that job does not exist or fails, the annotation interface pod will be stuck.
- **UndefinedTable handling:** If the configured table does not exist yet (pipeline hasn't run), the app catches `psycopg2.errors.UndefinedTable` and starts with an empty dataset rather than crashing, with a warning log message.

## Testing Notes

- The evaluation system uses deepeval's `GEval` with two custom metrics: "Root Cause Accuracy" and "Solution Steps Alignment", both comparing AI outputs against human golden solutions.
- Evaluation requires a running vLLM-compatible model endpoint configured via `OPENAI_*` environment variables.
- The annotation interface exposes both per-entry and batch evaluation from the UI.
- Health checks use HTTP GET on `/` with liveness probe starting at 30s and readiness at 15s.

## Related Patterns

- Database connection shares the `pgvector` secret with other services in the quickstart.
- The `model-secret` used for deepeval is shared with other components that access the vLLM model server.
- Data flows from the upstream processing pipeline into the same PostgreSQL table that this interface reads.
