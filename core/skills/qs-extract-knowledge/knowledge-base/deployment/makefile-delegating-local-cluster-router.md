---
name: makefile-delegating-local-cluster-router
description: "Root Makefile routing local/* and cluster/* targets to separate sub-Makefiles with credential prompting"
summary: "Solves deployment routing for quickstarts needing both local dev and cluster deployment by splitting a root Makefile into `local/%` and `cluster/%` pattern-rule targets that delegate via `make -C deploy/local` and `make -C deploy/helm` respectively, with `.EXPORT_ALL_VARIABLES` and convenience aliases like `rag-status: local/rag-status`. Use when a quickstart requires both compose-based local development (auto-detecting `docker-compose` or `podman-compose` for infrastructure, `uv run` for hot-reload app services) and Helm-based cluster deployment with interactive credential prompting and `.env` file fallback. The Helm Makefile loads `.env` via `-include ../../.env` with `export $(shell sed 's/=.*//' ../../.env | xargs)`, prompts interactively with `read -s` for tokens when env vars are empty, writes credentials to a temp `MODEL_VALUES_FILE` (`/tmp/rhdp-values.yaml`) passed to `helm install` alongside `env_args` then deleted; cluster login validated via `oc whoami` with port-forward targets for UI (:7860), backend (:8000), and Grafana (:3000). Gotchas: `.env` values silently override interactive prompts (checked via `if [ -z \"$(OPENAI_API_TOKEN)\" ]`), the `install` target's `namespace` prerequisite creates the namespace via `oc new-project` with app labeling, and the `-include` dash prefix suppresses errors when `.env` is absent."
metadata:
  type: deployment-pattern
tags:
  tech_stack: [makefile, helm]
  platform: [openshift]
source_examples:
  - quickstart: "ansible-log-analysis"
    repo: "https://github.com/rh-ai-quickstart/ansible-log-analysis"
    notes: "Root Makefile routes local/X to deploy/local/Makefile and cluster/X to deploy/helm/Makefile; Helm Makefile prompts for LLM credentials interactively and writes temp values file"
    approach: "A"
---

# Makefile Delegating Router for Local and Cluster Deployment

## Overview

A Makefile pattern where the root Makefile acts as a router, delegating `local/*` targets to a local development Makefile and `cluster/*` targets to a Helm deployment Makefile. Each sub-Makefile manages its own deployment method independently: compose-based local dev and Helm-based cluster deployment.

## Pattern Description

The ansible-log-analysis quickstart splits deployment concerns across three Makefiles: a root router (`Makefile`), a local dev controller (`deploy/local/Makefile`), and a Helm deployment controller (`deploy/helm/Makefile`). The root Makefile uses pattern rules (`local/%` and `cluster/%`) to forward targets, so `make local/dev` becomes `make -C deploy/local dev` and `make cluster/install` becomes `make -C deploy/helm install`. The Helm Makefile includes an interactive credential prompt that writes LLM API credentials to a temporary values file used during `helm install`.

## Implementation

### Root Router Makefile

From `Makefile` (project root):

```makefile
.EXPORT_ALL_VARIABLES:

all: ## Show usage instructions
	@echo "Usage:"
	@echo "  make local/<target>   - Run local development targets"
	@echo "  make cluster/<target> - Run helm deployment targets"
	@echo ""
	@echo "Examples:"
	@echo "  make local/dev        - Start local development environment"
	@echo "  make cluster/install  - Install via helm (requires NAMESPACE)"

local/%: ## Route local targets to deploy/local/Makefile
	@$(MAKE) -C deploy/local $*

cluster/%: ## Route deploy targets to deploy/helm/Makefile
	@$(MAKE) -C deploy/helm $*

# Convenience targets
rag-status: local/rag-status
test-rag: local/test-rag
```

### Helm Makefile with Interactive Credential Prompt

From `deploy/helm/Makefile`:

```makefile
-include ../../.env
ifneq (,$(wildcard ../../.env))
export $(shell sed 's/=.*//' ../../.env | xargs)
endif

NAMESPACE ?= $(shell oc project -q 2>/dev/null || echo "default")
ANSIBLE_LOG_MONITOR_CHART := alm
MODEL_VALUES_FILE := /tmp/rhdp-values.yaml

define prompt_openai_credentials
	@bash -c '\
	if [ -z "$(OPENAI_API_TOKEN)" ]; then \
		echo -n "Enter LLM API TOKEN: "; \
		read -s OPENAI_API_TOKEN; echo ""; \
	else \
		OPENAI_API_TOKEN="$(OPENAI_API_TOKEN)"; \
	fi; \
	# ... similar for ENDPOINT, MODEL, TEMPERATURE ...
	echo "backend:" > $(MODEL_VALUES_FILE); \
	echo "  secret:" >> $(MODEL_VALUES_FILE); \
	echo "    OPENAI_API_TOKEN: \"$$OPENAI_API_TOKEN\"" >> $(MODEL_VALUES_FILE); \
	# ...'
endef

install: namespace
	$(call prompt_openai_credentials)
	helm install $(ANSIBLE_LOG_MONITOR_CHART) ./ansible-log-monitor \
		-n $(NAMESPACE) $(env_args) -f $(MODEL_VALUES_FILE)
	@rm -f $(MODEL_VALUES_FILE)
```

### Local Dev Makefile with Compose + Native Processes

From `deploy/local/Makefile`:

```makefile
COMPOSE_CMD := $(shell command -v docker-compose 2>/dev/null \
    || command -v podman-compose 2>/dev/null)

start: stop
	@$(MAKE) -s postgres
	@$(MAKE) -s phoenix
	@$(MAKE) -s loki-stack
	@$(MAKE) -s rag-stack & $(MAKE) -s aap-mock-stack & wait
	@$(MAKE) -s backend
	@$(MAKE) -s ui
	@$(MAKE) -s annotation

backend:
	@cd ../.. && uv run uvicorn alm.main_fastapi:app --reload &

ui:
	@cd ../../services/ui && uv run gradio app.py &
```

The local Makefile uses compose for infrastructure services (Loki, Grafana, PostgreSQL, etc.) and `uv run` for application services (backend, UI, annotation interface) to enable hot-reload during development.

### Cluster Login Validation

From `deploy/helm/Makefile`:

```makefile
define check_cluster_login
	@if ! oc whoami > /dev/null 2>&1; then \
		echo "Error: Not logged into OpenShift cluster"; \
		echo "   Run: oc login <cluster-url>"; \
		exit 1; \
	fi
endef

define check_namespace
	$(call check_cluster_login)
	@echo "Using namespace: $(NAMESPACE)"
endef
```

### Port Forwarding Targets

From `deploy/helm/Makefile`:

```makefile
port-forward-ui:
	@oc port-forward -n $(NAMESPACE) svc/ui 7860:7860

port-forward-backend:
	@oc port-forward -n $(NAMESPACE) svc/backend 8000:8000

port-forward-grafana:
	@oc port-forward -n $(NAMESPACE) svc/grafana 3000:3000
```

## Configuration

- **Key settings:** `NAMESPACE` defaults to the current `oc project`; LLM credentials can come from `.env` file or interactive prompt
- **Defaults:** `ANSIBLE_LOG_MONITOR_CHART := alm` is the Helm release name; `MODEL_VALUES_FILE := /tmp/rhdp-values.yaml` is deleted after install
- **Dependencies:** Helm Makefile requires `oc` CLI and cluster login; local Makefile requires `docker-compose` or `podman-compose` and `uv`

## Gotchas

- The credential prompt uses `read -s` for the API token (silent input) but regular `read` for other fields. Values from `.env` take precedence over interactive prompts, checked via `if [ -z "$(OPENAI_API_TOKEN)" ]`.
- The `.env` file is included with `-include ../../.env` (the leading dash prevents errors if the file doesn't exist). The `export $(shell sed 's/=.*//' ../../.env | xargs)` line exports all variable names from the file.
- The local Makefile auto-detects the compose command: `$(shell command -v docker-compose 2>/dev/null || command -v podman-compose 2>/dev/null)`, supporting both Docker and Podman environments.
- The `install` target includes a `namespace` prerequisite that creates the namespace via `oc new-project` and labels it with `app=ansible-log-monitor`.

## Related Patterns

- `compose-hybrid-loki-observability-stack.md` - The compose file used by the local dev Makefile
- `helm-umbrella-mixed-remote-local-deps.md` - The Helm chart installed by the cluster Makefile
