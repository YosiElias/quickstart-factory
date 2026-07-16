---
name: mcp-servers
description: "Helm subchart for deploying MCP (Model Context Protocol) servers with dual-mode Toolhive operator or standard Deployment support"
summary: "Deploys one or more MCP (Model Context Protocol) servers on OpenShift/Kubernetes via a reusable Helm subchart (mcp-servers v0.5.7 from ai-architecture-charts) with dual-mode support for Toolhive operator MCPServer CRDs or standard Deployment+Service resources. Use deploymentMode \"auto\" (default) to auto-detect Toolhive via canDeployMCPServer helper (checks both MCPServer CRD and toolhive-system namespace), \"mcpserver\" to force Toolhive with permissionProfile/proxyMode features and stdio transport, or \"deployment\" for clusters without the operator; supports SSE and stdio transports with server configs merged from global and local values keys. Python consumers connect via async httpx MCP client implementing JSON-RPC 2.0 (initialize->get_tools->call_tool flow with Mcp-Session-Id headers), tools are wrapped as LangChain @tool functions calling the endpoint at LOKI_MCP_SERVER_URL, and the chart includes Toolhive operator-crds v0.0.34 and operator v0.2.21 as optional Chart.lock dependencies. Auto-detection silently falls back to Deployment mode if the Helm service account lacks cluster namespace-list permissions, the subchart's default weather server must be explicitly disabled in the parent chart, Oracle SQLcl server requires an ephemeral 5Gi gp3-csi PVC at /sqlcl-home, and each Python query creates a new MCP session rather than reusing connections."
metadata:
  type: component
tags:
  tech_stack: [helm, kubernetes, mcp, httpx, python]
  ai_pattern: [agents, model-serving]
  platform: [openshift, kubernetes, toolhive]
  data_layer: []
source_examples:
  - quickstart: "ansible-log-analysis"
    repo: "https://github.com/rh-ai-quickstart/ansible-log-analysis"
    notes: "MCP servers subchart deploying a Loki MCP server for log querying, consumed by a LangChain agent via an async Python MCP client"
    approach: "A"
---

# MCP Servers

## Overview

A reusable Helm subchart from `ai-architecture-charts` that deploys one or more MCP (Model Context Protocol) servers on OpenShift/Kubernetes. It supports two deployment modes: native `MCPServer` custom resources via the Toolhive operator, or standard Kubernetes `Deployment` + `Service` resources. The chart auto-detects Toolhive availability at install time and falls back gracefully, making it portable across clusters with or without the operator installed.

## Tech Stack & Dependencies
- **Runtime:** Container images per MCP server (e.g., `quay.io/rh-ai-quickstart/alm-loki-mcp-server`)
- **Container image:** Configurable per server entry in `values.yaml`; tag defaults to `.Chart.Version`
- **Key dependencies:** Toolhive operator CRDs (optional), Toolhive operator (optional)
- **Helm subchart:** `mcp-servers` v0.5.7 from `https://rh-ai-quickstart.github.io/ai-architecture-charts`
- **Toolhive dependencies (via Chart.lock):** `toolhive-operator-crds` v0.0.34 and `toolhive-operator` v0.2.21 from `https://stacklok.github.io/toolhive`

## Key Patterns

### Dual Deployment Mode (auto/mcpserver/deployment)

Each MCP server entry has a `deploymentMode` field that controls how it is deployed. The `auto` mode inspects the cluster at install time for both the `MCPServer` CRD and the `toolhive-system` namespace before deciding.

```yaml
# values.yaml — per-server deploymentMode options
mcp-servers:
  loki-server:
    enabled: true
    deploymentMode: deployment  # auto | mcpserver | deployment
    transport: sse
    targetPort: 8080
    image:
      repository: quay.io/rh-ai-quickstart/alm-loki-mcp-server
      tag: query-direction-support
```

The detection logic in `_helpers.tpl`:

```gotemplate
{{- define "mcp-servers.canDeployMCPServer" -}}
  {{- $hasCRD := .Capabilities.APIVersions.Has "toolhive.stacklok.dev/v1alpha1/MCPServer" }}
  {{- $hasToolhiveNamespace := false }}
  {{- if $hasCRD }}
    {{- $namespaces := lookup "v1" "Namespace" "" "" }}
    {{- range $namespaces.items }}
      {{- if eq .metadata.name "toolhive-system" }}
        {{- $hasToolhiveNamespace = true }}
      {{- end }}
    {{- end }}
  {{- end }}
  {{- and $hasCRD $hasToolhiveNamespace }}
{{- end }}
```

### Global Values Merge

The chart merges MCP server definitions from both `global.mcp-servers` and local `mcp-servers` keys, allowing parent charts to override individual server configs while the subchart provides defaults.

```gotemplate
{{- define "mcp-servers.mergeMcpServers" -}}
  {{- $globalServers := .Values.global | default dict }}
  {{- $globalServers := index $globalServers "mcp-servers" | default dict }}
  {{- $localServers := index .Values "mcp-servers" | default dict }}
  {{- $merged := merge $globalServers $localServers }}
  {{- toJson $merged }}
{{- end }}
```

### MCPServer CRD Resources (Toolhive Mode)

When Toolhive is available, the chart creates `MCPServer` custom resources (`toolhive.stacklok.dev/v1alpha1`) instead of raw Deployments. This supports features like `permissionProfile`, `proxyMode`, and automatic proxy sidecar injection.

```yaml
# Rendered MCPServer spec (from mcpserver.yaml template)
apiVersion: toolhive.stacklok.dev/v1alpha1
kind: MCPServer
spec:
  image: "quay.io/rh-ai-quickstart/oracle-sqlcl:0.5.7"
  proxyMode: streamable-http
  transport: stdio
  port: 8080
  permissionProfile:
    name: network
    type: builtin
```

### MCP Client Integration (Python Consumer)

The backend consumes MCP servers via an async Python client using `httpx`. The client implements the JSON-RPC 2.0 MCP protocol with session management via `Mcp-Session-Id` headers. Found in `src/alm/mcp/mcp_client.py`:

```python
class MCPClient:
    async def initialize(self):
        payload = {
            "jsonrpc": "2.0", "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "clientInfo": {"name": "test-chat", "version": "1.0.0"},
            },
        }
        response = await self.client.post(self.server_url, json=payload, ...)
        self.session_id = response.headers.get("Mcp-Session-Id")
```

Tool calls follow the pattern: `initialize()` -> `get_tools()` -> `call_tool(name, args)`, with the session ID passed in headers for each request.

### LangChain Tool Wrapping

MCP tool calls are wrapped as LangChain `@tool` functions in `src/alm/tools/loki_tools.py`. Each tool constructs a LogQL query and delegates execution to the MCP server's `loki_query` tool:

```python
_mcp_server_url = os.getenv("LOKI_MCP_SERVER_URL")

async def execute_loki_query(query, start, end, limit, ...):
    client = await create_mcp_client()
    result = await client.call_tool("loki_query", {
        "query": query, "start": start_parsed,
        "end": end_parsed, "limit": limit,
        "direction": direction, "format": "json",
    })
```

## Configuration
- **Environment variables:**
  - `LOKI_MCP_SERVER_URL` -- URL for the MCP server endpoint, consumed by the backend (e.g., `http://mcp-loki-server:8080/stream`)
  - `LOKI_URL` -- Loki endpoint URL, set on the MCP server container (e.g., `http://loki:3100`)
  - `PORT` -- Listen port for the MCP server container
  - `JAVA_TOOL_OPTIONS`, `_JAVA_OPTIONS`, `HOME` -- JVM config for Oracle SQLcl MCP server
- **Helm values:** Each server is a keyed entry under `mcp-servers:` with `enabled`, `deploymentMode`, `image`, `transport`, `targetPort`, `port`, `env`, `envSecrets`, `resources`, `securityContext`, `podSecurityContext`, `volumes`, `volumeMounts`, `permissionProfile`, and `oracleUserSecrets`
- **Transport modes:** `sse` (Server-Sent Events) for HTTP-native servers, `stdio` for servers that communicate over stdin/stdout (proxied by Toolhive)

## Known Gotchas
- **Toolhive detection requires namespace lookup permissions:** The `canDeployMCPServer` helper uses `lookup "v1" "Namespace" "" ""` which requires the Helm install service account to have cluster-level namespace list permissions. Without this, auto-detection silently falls back to Deployment mode.
- **Default weather server must be explicitly disabled:** The subchart ships with a `weather` server enabled by default. The parent chart overrides this with `weather: { enabled: false }` to avoid deploying an unwanted test server. Found in the parent `values.yaml`.
- **Port conflict in local compose:** The Loki MCP server uses host port 8081 instead of 8080 to avoid conflict with another service. A comment in `deploy/local/compose.yaml` documents this: `ports: - "8081:8080" # Changed host port to 8081 to avoid conflict with alm-embedding`.
- **New MCP client per query:** The Python client creates a fresh `MCPClient` and initializes a new MCP session for each query execution rather than reusing sessions. This is by design in `execute_loki_query()` -- each call does `create_mcp_client()` in a try/finally block with explicit cleanup.
- **Oracle SQLcl requires ephemeral volume:** The Oracle MCP server needs a writable `HOME` directory (`/sqlcl-home`) backed by an ephemeral PVC (5Gi, `gp3-csi` storage class) because SQLcl writes temporary files. This is configured via `volumes` and `volumeMounts` in values.yaml.

## Testing Notes
- For Deployment mode: `oc get deployments -l app.kubernetes.io/component=mcp-server` lists all MCP server deployments
- For Toolhive mode: `oc get mcpservers` lists MCPServer custom resources
- Service endpoints follow the pattern `http://mcp-<server-key>.<namespace>.svc.cluster.local:<port>`
- SSE transport servers expose an `/sse` endpoint for health/connectivity checks
- The NOTES.txt template provides cluster-specific verification commands after `helm install`

## Related Patterns
- Helm subchart wiring (global values merge pattern)
- LangChain agent tool integration
- Toolhive operator for managed MCP lifecycle
