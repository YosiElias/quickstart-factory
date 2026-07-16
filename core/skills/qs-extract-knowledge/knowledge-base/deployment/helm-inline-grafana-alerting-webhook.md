---
name: helm-inline-grafana-alerting-webhook
description: "Grafana alerting with webhook contact points to backend, configured entirely in Helm values"
summary: "Configures Grafana 9+ unified alerting entirely through Helm values.yaml to create an event-driven pipeline where LogQL queries detect log patterns in Loki and fire webhook POSTs to a backend endpoint with Go-templated URL parameters for AI inference. Use when log-pattern detection should trigger backend processing without custom controllers — requires unified_alerting.enabled: true with legacy alerting disabled, feature_toggles alertingSimplifiedRouting,alertingQueryAndExpressionsStepMode, and a Loki datasource with uid loki. Webhook contact points use Go template urlquery function to pass parameters (log_message, detected_level, filename, job) to the backend URL; alert rules evaluate every 1m with for: 0s for immediate firing, noDataState: NoData to avoid false positives, and notification policies group by alertname/status/job with repeat_interval: 4h. Webhook URL Go templates require Helm double-escaping via {{ \"{{\" }} since both Helm and Grafana process templates; the status label in LogQL queries (e.g., count_over_time({status=\"fatal\"}[5m])) is set by the Alloy pipeline not Loki natively so pipeline changes break alerts; the alert condition chain requires all three refId steps (A: Loki query, B: reduce to sum, C: threshold > 0)."
metadata:
  type: deployment-pattern
tags:
  tech_stack: [helm, grafana, kubernetes]
  ai_pattern: [agents]
  platform: [openshift]
  data_layer: [loki]
source_examples:
  - quickstart: "ansible-log-analysis"
    repo: "https://github.com/rh-ai-quickstart/ansible-log-analysis"
    notes: "Grafana alerting rules query Loki for fatal/failed Ansible logs and webhook POST to FastAPI backend inference endpoint with templated query params"
    approach: "A"
---

# Grafana Alerting with Webhook to Backend via Helm Values

## Overview

A pattern where Grafana's unified alerting system is configured entirely through Helm values.yaml, with alert rules that query Loki for log patterns and fire webhooks to the application backend. This creates an event-driven pipeline: logs are ingested into Loki, Grafana detects patterns via LogQL queries, and alerts trigger AI inference via HTTP webhooks.

## Pattern Description

In the ansible-log-analysis quickstart, Grafana monitors Loki for Ansible logs with `fatal` or `failed` status labels. When detected, Grafana fires a webhook POST to the backend's `/grafana-alert/` endpoint, passing the log message, detected severity level, filename, and job name as URL-encoded query parameters. The backend then runs its AI agent pipeline to analyze and remediate the error.

## Implementation

### Contact Points (Webhook Configuration)

From `deploy/helm/ansible-log-monitor/values.yaml` (grafana.alerting.contactpoints):

```yaml
grafana:
  alerting:
    contactpoints.yaml:
      apiVersion: 1
      contactPoints:
        - orgId: 1
          name: backend-inference-webhook
          receivers:
            - uid: backend-webhook-receiver
              type: webhook
              settings:
                url: >-
                  http://alm-backend:8000/grafana-alert/
                  ?log_message={{ "{{" }} urlquery (or .CommonAnnotations.description
                    .CommonAnnotations.summary "Grafana alert triggered") {{ "}}" }}
                  &detected_level={{ "{{" }} urlquery (or .CommonLabels.detected_level
                    "error") {{ "}}" }}
                  &filename={{ "{{" }} urlquery (or .CommonLabels.filename
                    "unknown") {{ "}}" }}
                  &job={{ "{{" }} urlquery (or .CommonLabels.job
                    "ansible_logs") {{ "}}" }}
                  &service_name=grafana
                httpMethod: POST
```

### Alert Rules (LogQL Queries)

From `deploy/helm/ansible-log-monitor/values.yaml` (grafana.alerting.rules):

```yaml
    rules.yaml:
      apiVersion: 1
      groups:
        - orgId: 1
          name: ansible-log-alerts
          folder: Ansible Logs
          interval: 1m
          rules:
            - uid: fatal-logs-alert
              title: Fatal Ansible Logs
              condition: C
              data:
                - refId: A
                  datasourceUid: loki
                  model:
                    expr: 'count_over_time({status="fatal"}[5m])'
                    queryType: instant
              noDataState: NoData
              for: 0s
              labels:
                severity: critical
                alert_type: ansible_fatal
            - uid: failed-logs-alert
              title: Failed Ansible Logs
              condition: C
              data:
                - refId: A
                  datasourceUid: loki
                  model:
                    expr: 'count_over_time({status="failed"}[5m])'
                    queryType: instant
              labels:
                severity: warning
                alert_type: ansible_failed
```

### Notification Policies (Alert Routing)

From `deploy/helm/ansible-log-monitor/values.yaml` (grafana.alerting.policies):

```yaml
    policies.yaml:
      apiVersion: 1
      policies:
        - orgId: 1
          receiver: backend-inference-webhook
          group_by:
            - alertname
            - status
            - job
          group_wait: 10s
          group_interval: 1m
          repeat_interval: 4h
          routes:
            - receiver: backend-inference-webhook
              matchers:
                - alertname = "Fatal Ansible Logs"
            - receiver: backend-inference-webhook
              matchers:
                - alertname = "Failed Ansible Logs"
```

### Grafana INI Configuration for Unified Alerting

From `deploy/helm/ansible-log-monitor/values.yaml` (grafana.grafana.ini):

```yaml
  grafana.ini:
    unified_alerting:
      enabled: true
    alerting:
      enabled: false  # Disable legacy alerting
    feature_toggles:
      enable: alertingSimplifiedRouting,alertingQueryAndExpressionsStepMode
```

## Configuration

- **Key settings:** `unified_alerting.enabled: true` enables Grafana 9+ alerting; `repeat_interval: 4h` controls re-notification frequency; alert evaluation runs every 1 minute
- **Defaults:** `for: 0s` on both rules means alerts fire immediately without a pending period; `noDataState: NoData` avoids false positives when no logs match
- **Dependencies:** Requires Loki datasource configured with uid `loki` and the backend service reachable at `http://alm-backend:8000`

## Gotchas

- The webhook URL uses Go template syntax (`{{ "{{" }}` and `{{ "}}" }}`) which must be double-escaped because both Helm and Grafana process templates. The `{{ "{{" }}` syntax is Helm's way of producing literal `{{` in the output.
- The `status` label used in LogQL queries (`{status="fatal"}`) is set by the Alloy log processing pipeline, not by Loki natively. If the Alloy pipeline stages change, these alert rules may stop matching.
- The alert condition chain (refId A -> B -> C) uses Grafana's expression pipeline: A queries Loki, B reduces to a single sum, C applies a threshold (`> 0`). All three refIds are required for the condition to evaluate.

## Related Patterns

- `helm-alloy-sidecar-pvc-log-collection.md` - Alloy pipeline that sets the `status` label used by these alert rules
- `helm-loki-singlebin-high-ingestion.md` - Loki configuration receiving the logs that alerts query
