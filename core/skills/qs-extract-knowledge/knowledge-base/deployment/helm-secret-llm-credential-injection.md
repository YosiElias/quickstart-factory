---
name: helm-secret-llm-credential-injection
description: "LLM API credentials injected via Helm secret with interactive prompt or .env file fallback"
summary: "Injects LLM API credentials into Kubernetes via a Helm-templated Secret (`model-secret`) with 7 `OPENAI_*` fields covering primary model (TOKEN, ENDPOINT, MODEL, TEMPERATURE) and optional tool-calling model (3 fields) for dual-model configurations where the primary model lacks tool-calling capability. Use when deploying OpenAI-compatible LLM services via Helm where both a backend Deployment and init Job need credentials via `envFrom: secretRef` alongside a separate `configMapRef` for non-secret config; the `OPENAI_*` naming is generic and works with any compatible endpoint. The Makefile sources credentials from interactive prompt or `.env` fallback (tool-calling fields commented out by default), writes a temp values file to `/tmp/rhdp-values.yaml`, passes it as `-f` to `helm install`, and cleans up with `@rm -f`; the Secret uses `stringData` so Kubernetes handles base64 encoding. Gotchas: `model-secret` name is hardcoded across secret, deployment, and job templates; only `OPENAI_TEMPERATURE: \"0.7\"` has a non-empty default; and the temp values file briefly exposes plaintext credentials on disk before deletion."
metadata:
  type: deployment-pattern
tags:
  tech_stack: [helm, kubernetes]
  ai_pattern: [agents]
  platform: [openshift]
source_examples:
  - quickstart: "ansible-log-analysis"
    repo: "https://github.com/rh-ai-quickstart/ansible-log-analysis"
    notes: "Backend secret template creates model-secret with 7 LLM credential fields; Makefile prompts interactively or reads from .env; supports dual-model config for tool-calling models"
    approach: "A"
---

# Helm Secret with LLM Credential Injection

## Overview

A pattern for managing LLM API credentials in Kubernetes deployments where credentials are injected via a Helm Secret created from values, with credentials sourced either from an interactive Makefile prompt or from a `.env` file. This supports dual-model configurations where the primary model and a tool-calling model may use different endpoints and credentials.

## Pattern Description

The ansible-log-analysis quickstart uses a Kubernetes Secret (`model-secret`) to store LLM API credentials. The Secret is created by a Helm template that reads values from the `backend.secret` section of `values.yaml`. At install time, the Makefile generates a temporary values file with credentials (from interactive prompt or `.env`), passes it as a `-f` flag to `helm install`, and deletes it afterward. Both the backend Deployment and init Job consume these credentials via `envFrom: secretRef`.

## Implementation

### Secret Template

From `deploy/helm/ansible-log-monitor/charts/backend/templates/secret.yaml`:

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: model-secret
type: Opaque
stringData:
  OPENAI_API_TOKEN: {{ .Values.secret.OPENAI_API_TOKEN | quote }}
  OPENAI_API_ENDPOINT: {{ .Values.secret.OPENAI_API_ENDPOINT | quote }}
  OPENAI_MODEL: {{ .Values.secret.OPENAI_MODEL | quote }}
  OPENAI_TEMPERATURE: {{ .Values.secret.OPENAI_TEMPERATURE | quote }}
  OPENAI_API_TOKEN_WITH_TOOL_CALLING: {{ .Values.secret.OPENAI_API_TOKEN_WITH_TOOL_CALLING | quote }}
  OPENAI_API_ENDPOINT_WITH_TOOL_CALLING: {{ .Values.secret.OPENAI_API_ENDPOINT_WITH_TOOL_CALLING | quote }}
  OPENAI_MODEL_WITH_TOOL_CALLING: {{ .Values.secret.OPENAI_MODEL_WITH_TOOL_CALLING | quote }}
```

### Secret Consumption in Deployment and Init Job

From `deploy/helm/ansible-log-monitor/charts/backend/templates/deployment.yaml`:

```yaml
containers:
  - name: backend
    envFrom:
      - configMapRef:
          name: {{ include "backend.fullname" . }}-config
      - secretRef:
          name: model-secret
```

The same `envFrom` pattern is used in the init Job template (`init-job.yaml`), ensuring both the initialization pipeline and the running server have access to the same credentials.

### Default Values (Empty Credentials)

From `deploy/helm/ansible-log-monitor/values.yaml`:

```yaml
backend:
  secret:
    OPENAI_API_TOKEN: ""
    OPENAI_API_ENDPOINT: ""
    OPENAI_MODEL: ""
    OPENAI_TEMPERATURE: "0.7"
    OPENAI_API_TOKEN_WITH_TOOL_CALLING: ""
    OPENAI_API_ENDPOINT_WITH_TOOL_CALLING: ""
    OPENAI_MODEL_WITH_TOOL_CALLING: ""
```

### Dual-Model Configuration

From `.env`:

```bash
# Optional: Separate model for tool calling
# Only set these if your main model (OPENAI_MODEL) does not support tool calling
# OPENAI_API_TOKEN_WITH_TOOL_CALLING=your_api_token_here
# OPENAI_API_ENDPOINT_WITH_TOOL_CALLING=https://your-endpoint.com/v1
# OPENAI_MODEL_WITH_TOOL_CALLING=your_model_name
```

The dual-model pattern allows using one LLM for general inference and a separate one for tool-calling operations, supporting configurations where the primary model may not have tool-calling capabilities.

## Configuration

- **Key settings:** 7 credential fields covering primary model (TOKEN, ENDPOINT, MODEL, TEMPERATURE) and optional tool-calling model (3 fields)
- **Defaults:** `OPENAI_TEMPERATURE: "0.7"` is the only non-empty default; all other credential fields default to empty strings
- **Dependencies:** The `model-secret` name is hardcoded in both the secret template and the deployment/job templates

## Gotchas

- The Makefile writes credentials to `/tmp/rhdp-values.yaml` and deletes it after `helm install`. This temp file contains plaintext credentials briefly on disk. The `@rm -f $(MODEL_VALUES_FILE)` line in the install target handles cleanup.
- The `.env` file uses `OPENAI_*` naming for environment variables but these are generic LLM API credentials that work with any OpenAI-compatible API endpoint. The `.env` file includes an example endpoint pointing to a Red Hat-hosted Llama model: `https://llama-4-scout-17b-16e-w4a16-maas-apicast-production.apps.prod.rhoai.rh-aiservices-bu.com:443/v1`.
- The Secret uses `stringData` (not `data`), so values are stored as plain text in the template but Kubernetes base64-encodes them at creation time.

## Related Patterns

- `makefile-delegating-local-cluster-router.md` - The Makefile that runs the interactive credential prompt
- `helm-init-job-chained-readiness-gates.md` - The init Job that consumes the model-secret
