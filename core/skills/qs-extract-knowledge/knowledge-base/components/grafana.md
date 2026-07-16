---
name: grafana
description: "Grafana monitoring with Loki datasource, alerting rules, and webhook contact points for AI-driven log analysis"
summary: "Grafana provides monitoring and webhook-based alerting for AI-driven log analysis, connecting to Loki as datasource and POSTing alert payloads with Go-templated query parameters (log_message, detected_level, filename) to a FastAPI backend's /grafana-alert/ endpoint for LLM inference on failed Ansible logs. Deploy via Compose for local dev (inline entrypoint datasource provisioning, anonymous Admin via GF_AUTH_ANONYMOUS_ORG_ROLE=Admin) or Helm subchart 10.1.4 for OpenShift (values.yaml datasource provisioning, explicit adminUser/adminPassword, OpenShift Route and SCC privileged RoleBinding via extraObjects, fullnameOverride: grafana for fixed service name). Alert rules use count_over_time({status=\"failed\"}[5m]) LogQL instant queries with threshold gt 0, unified alerting enabled via grafana.ini.unified_alerting.enabled: true and alerting.enabled: false plus feature toggles alertingSimplifiedRouting,alertingQueryAndExpressionsStepMode; notification policies group by alertname/status/job with 10s wait, 1m interval, 4h repeat. Helm requires {{ \"{{\" }} double-brace escaping for Go template delimiters in webhook URLs (compose does not), backend filters out Grafana test notifications (\"Notification test\"/\"Grafana alert triggered\"), fatal-logs-alert is disabled in compose but enabled in Helm causing config divergence, and OpenShift needs an extraObjects RoleBinding granting system:openshift:scc:privileged to the grafana ServiceAccount."
metadata:
  type: component
tags:
  tech_stack: [grafana, loki, promtail, alloy]
  ai_pattern: []
  platform: [openshift, kubernetes]
  data_layer: []
source_examples:
  - quickstart: "ansible-log-analysis"
    repo: "https://github.com/rh-ai-quickstart/ansible-log-analysis"
    notes: "Grafana with Loki datasource and webhook alerting to trigger AI inference on failed logs"
    approach: "A"
---

# Grafana

## Overview

Grafana serves as the monitoring and alerting layer in quickstart architectures, connecting to Loki as a log datasource and firing webhook-based alerts to backend services for AI-driven log analysis. In the ansible-log-analysis quickstart, Grafana detects failed/fatal Ansible log entries via Loki queries and POSTs alert payloads to a FastAPI backend that runs LLM inference on the log content.

## Tech Stack & Dependencies

- **Runtime:** `grafana/grafana:latest` (compose) / `grafana-10.1.4.tgz` Helm subchart
- **Container image:** `grafana/grafana:latest`
- **Key dependencies:** Loki (log datasource), backend service (webhook target)
- **Helm subchart:** `grafana` version 10.1.4 (external chart bundled as `.tgz`)

## Key Patterns

### Loki Datasource Provisioning (Compose)

In the local compose setup, the datasource is provisioned inline via an entrypoint script that writes a YAML file at container startup:

```yaml
# From deploy/local/compose.yaml (grafana service entrypoint)
entrypoint:
  - sh
  - -euc
  - |
    mkdir -p /etc/grafana/provisioning/datasources
    cat <<EOF > /etc/grafana/provisioning/datasources/ds.yaml
    apiVersion: 1
    datasources:
    - name: Loki
      type: loki
      access: proxy
      orgId: 1
      url: http://loki:3100
      basicAuth: false
      isDefault: true
      version: 1
      editable: false
    EOF
    /run.sh
```

### Loki Datasource Provisioning (Helm)

In the Helm deployment, the datasource is declared in `values.yaml` under the `grafana.datasources` key, which the Grafana Helm chart provisions automatically:

```yaml
# From deploy/helm/ansible-log-monitor/values.yaml
grafana:
  datasources:
    datasources.yaml:
      apiVersion: 1
      datasources:
      - access: proxy
        editable: true
        isDefault: true
        name: Loki
        type: loki
        url: http://loki:3100
        uid: loki
```

### Webhook Contact Points for AI Inference

Grafana alert contact points are configured to POST to the backend's `/grafana-alert/` endpoint with templated query parameters extracted from alert labels and annotations. The compose version uses Go template syntax with `range` and `index`:

```yaml
# From deploy/local/config/grafana/alerting/contactpoints.yaml
contactPoints:
  - orgId: 1
    name: backend-inference-webhook
    receivers:
      - uid: backend-webhook-receiver
        type: webhook
        settings:
          url: >-
            http://backend:8000/grafana-alert/?log_message={{ if .Alerts }}{{ urlquery (index .Alerts 0).Annotations.description }}{{ else }}Test+alert{{ end }}&detected_level=unknown&filename={{ if .Alerts }}{{ urlquery (or (index (index .Alerts 0).Labels "filename") "Unknown filename") }}{{ else }}Unknown+filename{{ end }}
```

The Helm version uses a different template syntax to handle Helm's own Go template escaping:

```yaml
# From deploy/helm/ansible-log-monitor/values.yaml (grafana.alerting.contactpoints.yaml)
url: 'http://alm-backend:8000/grafana-alert/?log_message={{ "{{" }} urlquery (or .CommonAnnotations.description .CommonAnnotations.summary "Grafana alert triggered") {{ "}}" }}&detected_level={{ "{{" }} urlquery (or .CommonLabels.detected_level "error") {{ "}}" }}'
```

### Alert Rules Querying Loki

Alert rules use `count_over_time` LogQL queries against Loki to detect logs with specific status labels (set by Alloy/Promtail pipeline stages). The rule fires when the count exceeds zero in a 5-minute window:

```yaml
# From deploy/helm/ansible-log-monitor/values.yaml (grafana.alerting.rules.yaml)
- uid: failed-logs-alert
  title: Failed Ansible Logs
  condition: C
  data:
    - refId: A
      datasourceUid: loki
      model:
        expr: 'count_over_time({status="failed"}[5m])'
        queryType: instant
    - refId: B
      datasourceUid: __expr__
      model:
        expression: A
        reducer: sum
        type: reduce
    - refId: C
      datasourceUid: __expr__
      model:
        expression: B
        type: threshold
        conditions:
          - evaluator:
              params: [0]
              type: gt
```

### Notification Policies

Alerts are routed by `alertname` matcher to the backend webhook, with grouping by `alertname`, `status`, and `job`:

```yaml
# From deploy/helm/ansible-log-monitor/values.yaml (grafana.alerting.policies.yaml)
policies:
  - orgId: 1
    receiver: backend-inference-webhook
    group_by: [alertname, status, job]
    group_wait: 10s
    group_interval: 1m
    repeat_interval: 4h
    routes:
      - receiver: backend-inference-webhook
        matchers:
          - alertname = "Failed Ansible Logs"
        continue: false
```

## Configuration

- **Environment variables (compose):**
  - `GF_PATHS_PROVISIONING=/etc/grafana/provisioning` -- provisioning directory
  - `GF_AUTH_ANONYMOUS_ENABLED=true` -- anonymous access enabled for local dev
  - `GF_AUTH_ANONYMOUS_ORG_ROLE=Admin` -- anonymous users get Admin role (local dev only)
  - `GF_FEATURE_TOGGLES_ENABLE=alertingSimplifiedRouting,alertingQueryAndExpressionsStepMode` -- required feature toggles for unified alerting
- **Config files:**
  - `deploy/local/config/grafana/alerting/contactpoints.yaml` -- webhook contact point definitions
  - `deploy/local/config/grafana/alerting/policies.yaml` -- notification routing policies
  - `deploy/local/config/grafana/alerting/rules.yaml` -- LogQL-based alert rules
- **Helm values (key overrides):**
  - `grafana.fullnameOverride: grafana` -- fixed service name for routing
  - `grafana.adminUser` / `grafana.adminPassword` -- credentials (Helm only)
  - `grafana.grafana.ini.unified_alerting.enabled: true` -- enables Grafana 9+ unified alerting
  - `grafana.grafana.ini.alerting.enabled: false` -- disables legacy alerting
  - `grafana.grafana.ini.feature_toggles.enable` -- same feature toggles as compose

## Known Gotchas

- **Helm Go template escaping:** The Helm `values.yaml` uses `{{ "{{" }}` and `{{ "}}" }}` to pass literal Go template delimiters through to Grafana's webhook URL templates, since Helm itself interprets `{{ }}`. The compose version does not need this escaping. (Seen in `deploy/helm/ansible-log-monitor/values.yaml` grafana alerting contactpoints section.)
- **Fatal alert rule disabled in compose:** The fatal-logs-alert rule is commented out in `deploy/local/config/grafana/alerting/rules.yaml` with the comment "TEMPORARILY DISABLED", but is enabled in the Helm values. The compose and Helm alert configs may diverge.
- **Backend filters test alerts:** The backend `POST /grafana-alert/` endpoint in `src/alm/routes/grafana_alert.py` skips processing when `log_message` is `"Notification test"` or `"Grafana alert triggered"` to avoid wasting LLM tokens on Grafana's built-in test notifications (line 115-116).
- **OpenShift SCC required:** The Helm values include an `extraObjects` RoleBinding granting the `grafana` ServiceAccount the `system:openshift:scc:privileged` ClusterRole, which is needed to run on OpenShift. (Seen in `deploy/helm/ansible-log-monitor/values.yaml` under `grafana.extraObjects`.)
- **OpenShift Route via extraObjects:** Instead of using the Grafana Helm chart's built-in Gateway API HTTPRoute (which is disabled via `route.main.enabled: false`), an OpenShift `Route` is created via `extraObjects` for cluster access. (Seen in `deploy/helm/ansible-log-monitor/values.yaml`.)
- **Anonymous admin in compose:** The compose config enables anonymous access with Admin role (`GF_AUTH_ANONYMOUS_ORG_ROLE=Admin`), appropriate for local dev but not for production. The Helm version uses explicit `adminUser`/`adminPassword` instead.

## Testing Notes

- Verify Grafana is accessible on port 3000 (compose) or via the OpenShift Route (Helm)
- Confirm the Loki datasource appears in Grafana's datasource list and can query logs
- Trigger a test alert via Grafana UI and verify the backend receives the webhook POST at `/grafana-alert/`
- Check that the `Failed Ansible Logs` alert rule is firing by sending a log with `status="failed"` through the Loki pipeline

## Related Patterns

- Loki (log aggregation datasource)
- Alloy/Promtail (log collection pipeline that sets labels used by alert rules)
- FastAPI backend (webhook receiver for AI inference on alerted logs)
