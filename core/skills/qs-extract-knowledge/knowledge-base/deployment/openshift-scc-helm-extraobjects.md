---
name: openshift-scc-helm-extraobjects
description: "OpenShift SCC grants for third-party charts via Helm extraObjects (privileged and anyuid)"
summary: "Grants OpenShift SCCs to third-party Helm chart ServiceAccounts (Grafana, Loki) without forking upstream charts, using each chart's extraObjects values field to inject RBAC resources that override the default restricted SCC. Two strategies — bind to the built-in system:openshift:scc:privileged ClusterRole via RoleBinding (Grafana approach) when charts need writable directories and specific user permissions, or create a namespace-scoped Role granting use on security.openshift.io/securitycontextconstraints with resourceNames: [anyuid] (Loki approach) for a more self-contained grant without cluster-scoped role references. Critical config: Grafana requires initChownData.enabled: false and restrictive containerSecurityContext (drop ALL capabilities, readOnlyRootFilesystem: false) despite having privileged SCC, plus an extraObjects OpenShift Route since route.main.enabled: false disables Gateway API; Loki requires rbac.sccEnabled: false and the Role must bind all relevant ServiceAccounts (loki, loki-canary, minio-sa for internal MinIO chunk storage). Loki's minio-sa is its internal MinIO for chunk storage and is separate from any application-level MinIO chart — both need anyuid but are managed independently; omitting initChownData.enabled: false for Grafana causes a root init container that fails without additional SCC permissions."
metadata:
  type: deployment-pattern
tags:
  tech_stack: [helm, kubernetes]
  platform: [openshift]
source_examples:
  - quickstart: "ansible-log-analysis"
    repo: "https://github.com/rh-ai-quickstart/ansible-log-analysis"
    notes: "Grafana gets privileged SCC via ClusterRole binding; Loki, loki-canary, and minio-sa get anyuid SCC via Role with security.openshift.io resources"
    approach: "A"
---

# OpenShift SCC Grants via Helm extraObjects

## Overview

A pattern for granting OpenShift Security Context Constraints (SCCs) to third-party Helm chart service accounts using the chart's `extraObjects` mechanism. This avoids forking upstream charts while providing the SCC permissions that containers need to run on OpenShift.

## Pattern Description

Third-party Helm charts (Grafana, Loki) expect to run with specific user IDs or capabilities that conflict with OpenShift's default `restricted` SCC. Rather than modifying the charts or using cluster-wide policies, this pattern uses each chart's `extraObjects` values field to inject RBAC resources (Roles and RoleBindings) that grant the necessary SCC to the chart's ServiceAccounts. Two distinct SCC strategies are used: Grafana uses a direct ClusterRole binding to `system:openshift:scc:privileged`, while Loki uses a namespace-scoped Role that grants `use` verb on the `anyuid` SCC resource.

## Implementation

### Grafana: Privileged SCC via ClusterRole Binding

From `deploy/helm/ansible-log-monitor/values.yaml` (grafana.extraObjects):

```yaml
grafana:
  securityContext:
    runAsNonRoot: true
  extraObjects:
    - apiVersion: rbac.authorization.k8s.io/v1
      kind: RoleBinding
      metadata:
        name: grafana-privileged-scc
      subjects:
        - kind: ServiceAccount
          name: grafana
      roleRef:
        kind: ClusterRole
        name: system:openshift:scc:privileged
        apiGroup: rbac.authorization.k8s.io
```

This RoleBinding binds the `grafana` ServiceAccount directly to the pre-existing `system:openshift:scc:privileged` ClusterRole.

### Grafana: Container Security Context

From `deploy/helm/ansible-log-monitor/values.yaml`:

```yaml
grafana:
  containerSecurityContext:
    allowPrivilegeEscalation: false
    capabilities:
      drop:
      - ALL
    readOnlyRootFilesystem: false
    seccompProfile:
      type: RuntimeDefault
```

Despite having the `privileged` SCC, the container security context still restricts capabilities. The `privileged` SCC is needed because Grafana requires writable directories and specific user permissions, not because it needs elevated Linux capabilities.

### Grafana: OpenShift Route via extraObjects

The Grafana extraObjects also create an OpenShift Route since the Grafana chart's built-in Gateway API HTTPRoute is disabled:

```yaml
    - apiVersion: route.openshift.io/v1
      kind: Route
      metadata:
        name: grafana
      spec:
        to:
          name: grafana
          weight: 100
          kind: Service
        port:
          targetPort: service
```

### Loki: Anyuid SCC via Namespace-Scoped Role

From `deploy/helm/ansible-log-monitor/values.yaml` (loki.extraObjects):

```yaml
loki:
  rbac:
    sccEnabled: false  # Disable chart's built-in SCC handling
  extraObjects:
    - apiVersion: rbac.authorization.k8s.io/v1
      kind: Role
      metadata:
        name: loki-anyuid-scc
      rules:
        - apiGroups:
            - security.openshift.io
          resources:
            - securitycontextconstraints
          verbs:
            - use
          resourceNames:
            - anyuid
    - apiVersion: rbac.authorization.k8s.io/v1
      kind: RoleBinding
      metadata:
        name: loki-anyuid-scc
      subjects:
        - kind: ServiceAccount
          name: loki
        - kind: ServiceAccount
          name: loki-canary
        - kind: ServiceAccount
          name: minio-sa
      roleRef:
        kind: Role
        name: loki-anyuid-scc
        apiGroup: rbac.authorization.k8s.io
```

This creates a namespace-scoped Role that grants `use` on the `anyuid` SCC resource, then binds it to three ServiceAccounts: `loki`, `loki-canary`, and `minio-sa` (Loki's internal MinIO).

### AAP Mock: Restricted SCC Compliance

From `deploy/helm/ansible-log-monitor/charts/aap-mock/values.yaml`:

```yaml
podSecurityContext:
  runAsNonRoot: true
securityContext:
  allowPrivilegeEscalation: false
  runAsNonRoot: true
  capabilities:
    drop:
    - ALL
```

The aap-mock subchart is designed to work under the default `restricted` SCC without needing any SCC grants.

## Configuration

- **Key settings:** `loki.rbac.sccEnabled: false` disables the Loki chart's built-in SCC handling in favor of the custom extraObjects approach
- **Defaults:** Grafana chart's `route.main.enabled: false` disables Gateway API routing, requiring the extraObjects Route instead
- **Dependencies:** The `system:openshift:scc:privileged` ClusterRole must exist (it is a built-in OpenShift resource)

## Gotchas

- The two SCC strategies differ: Grafana uses a direct binding to a pre-existing ClusterRole (`system:openshift:scc:privileged`), while Loki creates a new namespace-scoped Role that explicitly grants `use` verb on the `securitycontextconstraints` resource. The Loki approach is more self-contained and doesn't reference cluster-scoped roles.
- Loki's `minio-sa` ServiceAccount refers to Loki's internal MinIO for chunk storage, not the application-level MinIO chart (which is a separate `ai-architecture-charts` dependency). Both need `anyuid` but are managed separately.
- The `grafana.initChownData.enabled: false` setting in values.yaml avoids running an init container as root to chown data directories, which would otherwise require additional SCC permissions.

## Related Patterns

- `helm-loki-singlebin-high-ingestion.md` - The Loki deployment these SCCs enable
- `helm-umbrella-mixed-remote-local-deps.md` - The umbrella chart where these values are set
