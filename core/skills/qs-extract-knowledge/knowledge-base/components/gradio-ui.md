---
name: gradio-ui
description: "Gradio-based frontend for AI Quickstarts — async backend proxy, CSS-only expand/collapse, dark theme, Helm subchart"
summary: "Gradio UI provides a lightweight single-file Python frontend (port 7860, quay.io/rh-ai-quickstart/alm-ui on UBI8 Python 3.12 with uv) as an alternative to React/PatternFly, using httpx.AsyncClient to proxy all data and AI requests to the backend API. Use when a Python-only UI suffices — backend URL set via BACKEND_URL env var (internal ClusterIP) or backendRouteHost Helm value (HTTPS Route); bind address/port configurable via GRADIO_SERVER_NAME/GRADIO_SERVER_PORT; Helm subchart supports OpenShift Route (edge TLS), Kubernetes Ingress with WebSocket annotations, and HPA autoscaling (1-5 replicas, 200m CPU/512Mi to 500m/1Gi limits). Critical implementation: dark theme uses gr.themes.Soft with slate/blue hues and auto-redirect script; CSS-only expand/collapse via hidden checkbox sibling selectors; Markdown rendering with fenced_code/tables/nl2br extensions; Gradio sync callbacks bridge to async via asyncio.new_event_loop() per handler; Containerfile copies only pyproject.toml and app.py. Gotchas: global.servicesNames.backend must match actual backend service name or UI fails silently (errors server-side only); Ingress requires WebSocket nginx annotations (proxy-read-timeout: \"3600\", upgrade) or Gradio falls to polling; uv.lock excluded from container so versions resolve at build time; new asyncio event loop per handler creates overhead; health probes use HTTP GET on / with liveness delay 30s."
metadata:
  type: component
tags:
  tech_stack: [gradio, python, httpx, markdown]
  ai_pattern: []
  platform: [openshift, kubernetes]
  data_layer: []
source_examples:
  - quickstart: "ansible-log-analysis"
    repo: "https://github.com/rh-ai-quickstart/ansible-log-analysis"
    notes: "Gradio UI with async httpx backend proxy, CSS-only expandable log clusters, and dark theme"
    approach: "A"
---

# Gradio UI

## Overview

Gradio frontend component used in AI Quickstarts to provide a web-based dashboard for viewing and interacting with backend data. In the RHOAI context, it serves as a lightweight Python-only UI alternative to React/PatternFly, running on port 7860 behind an OpenShift Route with edge TLS termination. The single-file `app.py` pattern keeps the frontend simple while relying on the backend service for all data and AI logic.

## Tech Stack & Dependencies

- **Runtime:** Python >= 3.12
- **Container image:** `quay.io/rh-ai-quickstart/alm-ui` (based on `registry.access.redhat.com/ubi8/python-312`)
- **Key dependencies:** `gradio>=5.42.0`, `httpx>=0.27.0`, `markdown>=3.6`, `pandas>=2.0.0`
- **Package manager:** uv (copied from `ghcr.io/astral-sh/uv:0.9.7` in Containerfile)
- **Helm subchart:** Local subchart at `deploy/helm/ansible-log-monitor/charts/ui/` (v0.1.0)

## Key Patterns

### Single-File App with Async Backend Proxy

The entire UI is a single `app.py` that uses `httpx.AsyncClient` to proxy requests to the backend API. The backend URL is injected via environment variable. Gradio event handlers bridge sync callbacks to async via `asyncio.new_event_loop()`.

```python
# services/ui/app.py — async fetch pattern
BACKEND_URL = os.getenv("BACKEND_URL")

async def fetch_all_alerts() -> List[Dict[str, Any]]:
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{BACKEND_URL}/grafana-alert/")
            response.raise_for_status()
            return response.json()
    except Exception as e:
        logger.error(f"Error fetching all alerts: {e}")
        return []
```

### Sync-to-Async Bridge in Event Handlers

Gradio dropdown change handlers are synchronous, but HTTP calls use async httpx. The code bridges this with a manual event loop per handler invocation.

```python
# services/ui/app.py — sync-to-async bridge in on_expert_change
def on_expert_change(expert: str):
    import asyncio
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        alerts = loop.run_until_complete(fetch_all_alerts())
        # ... process alerts ...
    finally:
        loop.close()
```

### CSS-Only Expandable Content

Log details and cluster contents use a pure-CSS expand/collapse pattern with hidden checkboxes and sibling selectors, avoiding JavaScript toggle logic entirely.

```css
/* services/ui/app.py — CSS-only toggle via hidden checkbox */
input[type="checkbox"] { display: none !important; }
.log-details-content {
    max-height: 0 !important;
    overflow: hidden !important;
    transition: all 0.4s ease !important;
}
input[type="checkbox"]:checked ~ .log-details-content {
    max-height: none !important;
    padding: 1.5rem !important;
}
```

### Dark Theme with Auto-Redirect

The interface uses `gr.themes.Soft` with slate/blue hue overrides and injects a head script that forces the `?__theme=dark` query parameter if not already set.

```python
# services/ui/app.py — theme configuration
gr.Blocks(
    theme=gr.themes.Soft(
        primary_hue="blue",
        secondary_hue="slate",
        neutral_hue="slate",
        font=gr.themes.GoogleFont("Inter"),
        font_mono=gr.themes.GoogleFont("JetBrains Mono"),
    ).set(
        body_background_fill="*neutral_950",
        body_text_color="*neutral_200",
        block_background_fill="*neutral_900",
    ),
    head='<script>...force dark theme redirect...</script>',
)
```

### Markdown Rendering for Solutions

Backend responses include a `stepByStepSolution` field in Markdown. The UI converts this to HTML using the `markdown` library with `fenced_code`, `tables`, and `nl2br` extensions before embedding it in the generated HTML output.

```python
# services/ui/app.py — markdown-to-HTML for solution display
step_by_step_solution_html = markdown.markdown(
    step_by_step_solution.strip(),
    extensions=["fenced_code", "tables", "nl2br"],
)
```

### UBI Base Image with uv Package Manager

The Containerfile uses a Red Hat UBI8 Python 3.12 base image and copies `uv` from the official image for fast dependency installation, then runs `uv sync --no-dev`.

```dockerfile
# services/ui/Containerfile
FROM registry.access.redhat.com/ubi8/python-312
USER root
COPY --from=ghcr.io/astral-sh/uv:0.9.7 /uv /uvx /bin/
WORKDIR /app
COPY pyproject.toml ./
RUN uv sync --no-dev
COPY app.py .
EXPOSE 7860
ENTRYPOINT ["python","app.py"]
```

## Configuration

- **Environment variables:**
  - `BACKEND_URL` — Full URL to the backend API (set by Helm; defaults to internal service `http://alm-backend:8000` or HTTPS via Route if `backendRouteHost` is set)
  - `GRADIO_SERVER_NAME` — Bind address (default `0.0.0.0`)
  - `GRADIO_SERVER_PORT` — Listen port (default `7860`)

- **Helm values (key overrides):**
  - `image.repository` / `image.tag` — Container image coordinates
  - `backendRouteHost` — When set, the UI connects to the backend over HTTPS via the Route hostname instead of internal ClusterIP
  - `route.enabled` — Toggles OpenShift Route creation (default `true`, edge TLS)
  - `ingress.enabled` — Toggles Kubernetes Ingress with nginx WebSocket annotations
  - `autoscaling.enabled` — HPA with CPU/memory targets (default `true`, 1-5 replicas)
  - `resources.requests` — 200m CPU / 512Mi memory
  - `resources.limits` — 500m CPU / 1Gi memory

- **Global values (parent chart):**
  - `global.servicesNames.backend` — Backend service name used in the deployment template to construct `BACKEND_URL` when `backendRouteHost` is empty

## Known Gotchas

- The deployment template references `global.servicesNames.backend` for constructing the internal backend URL (`http://{{ .Values.global.servicesNames.backend }}:8000`). This value is defined in the parent chart's `global-values.yaml` as `alm-backend` and must match the actual backend service name, or the UI will fail to connect.
- The ingress values include WebSocket-specific nginx annotations (`proxy-read-timeout: "3600"`, `upgrade`, `connection`) because Gradio uses WebSocket connections for live updates. Omitting these causes the UI to fall back to polling or fail to load.
- The Containerfile copies only `pyproject.toml` and `app.py` — there is no `uv.lock` copy step, so builds use whatever versions `uv sync` resolves at build time rather than locked versions. The `uv.lock` file exists in the source tree but is excluded by `.containerignore` patterns.
- Event handlers create a new `asyncio` event loop per invocation (`asyncio.new_event_loop()`) rather than reusing Gradio's loop. This is a workaround for Gradio's synchronous callback model and works but creates overhead per request.

## Testing Notes

- After deployment, port-forward with `make port-forward-ui` (defined in `deploy/helm/Makefile`) to access the UI at `localhost:7860`
- Verify the backend connection by selecting an expert class from the dropdown; if the backend is unreachable, the UI shows "No clusters found" with no error surfaced to the user (errors go to the server log)
- Health probes use HTTP GET on `/` with `initialDelaySeconds: 30` for liveness and `5` for readiness

## Related Patterns

- Backend API component that this UI proxies to
- Helm subchart wiring via parent chart `global-values.yaml`
- OpenShift Route with edge TLS termination
