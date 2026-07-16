---
name: agent-orchestration
description: "LangGraph multi-graph agent orchestration with conditional routing, MCP tools, and structured LLM outputs"
summary: "LangGraph StateGraph orchestrates Ansible log error triage triggered by Grafana webhook POSTs to FastAPI, with nodes for embedding-based cluster labeling, summarization, classification into eight expert categories via Literal-constrained Pydantic schemas, conditional routing, FAISS RAG + Loki MCP context retrieval via nested sub-graph, and remediation generation — all sharing a GrafanaAlertState and persisting results to PostgreSQL. Use when building multi-step LLM pipelines requiring conditional branching (with_structured_output drives binary routing decisions), tool-calling agents backed by MCP servers, and nested sub-graph composition where each node returns a Command specifying the next node and state updates. Critical pattern: dual LLM endpoints — default for structured output, separate OPENAI_API_ENDPOINT_WITH_TOOL_CALLING for tool-calling agents (with fallback); prompts loaded from external Markdown files; MCPClient manages JSON-RPC session lifecycle (initialize, get_tools, call_tool) with Mcp-Session-Id header tracking; closure-bound @tool functions bind per-alert context at creation to avoid LLM serialization. Gotchas: context retrieval is best-effort (try/except wrapping continues without context on failure), Loki tool results are cached in-memory via LightweightToolResponse because full log payloads exceed LangChain message chain capacity, and streaming collects partial output on interruption rather than failing."
metadata:
  type: architecture
tags:
  tech_stack: [fastapi, langchain, langgraph, python, gradio]
  ai_pattern: [agents, prompt-chaining, embeddings]
  platform: [openshift]
  data_layer: [faiss, minio, pgvector]
source_examples:
  - quickstart: "ansible-log-analysis"
    repo: "https://github.com/rh-ai-quickstart/ansible-log-analysis"
    notes: "LangGraph StateGraph with nested sub-graphs for Ansible error triage: summarize, classify, route, fetch context via MCP/RAG, and generate remediation"
    approach: "A"
---

# Agent Orchestration

## Overview

This architecture uses LangGraph `StateGraph` to build a multi-step agent pipeline where each node performs a distinct LLM-powered task (summarize, classify, route, retrieve context, generate solution). Nodes communicate through a shared Pydantic state object, and conditional edges route execution based on LLM-generated structured outputs. Sub-graphs handle complex retrieval tasks, including a tool-calling agent that queries an MCP server for log data.

## Data Flow

1. Grafana alert webhook POSTs a log message to the FastAPI `/grafana-alert/` endpoint (`src/alm/routes/grafana_alert.py:101`)
2. The endpoint constructs a `LogEntry` and invokes the top-level `inference_graph` (`src/alm/routes/grafana_alert.py:132`)
3. `cluster_logs_node` embeds the log and infers its cluster label via the clustering service or a local model (`src/alm/agents/graph.py:23-28`)
4. `summarize_log_node` asks the LLM to produce a structured `SummarySchema` from the raw log (`src/alm/agents/graph.py:32-35`)
5. `classify_log_node` classifies the summary into one of eight expert categories via `ClassifySchema` (`src/alm/agents/graph.py:38-46`)
6. `router_step_by_step_solution_node` decides whether more context is needed using `RouterStepByStepSolutionSchema` (`src/alm/agents/graph.py:68-78`)
7. If more context is needed, `get_more_context_node` invokes a **sub-graph** that retrieves context from RAG and optionally from Loki via an MCP-backed tool-calling agent (`src/alm/agents/graph.py:81-110`)
8. `suggest_step_by_step_solution_node` generates the final remediation using the log, summary, and any retrieved context (`src/alm/agents/graph.py:49-65`)
9. The resulting state is persisted to PostgreSQL as a `GrafanaAlert` record (`src/alm/routes/grafana_alert.py:134-138`)

## Component Wiring

| From | To | Protocol | Purpose |
|------|----|----------|---------|
| Grafana | FastAPI backend | REST (webhook POST) | Delivers alert with log message |
| FastAPI backend | LangGraph inference_graph | In-process Python | Orchestrates the agent pipeline |
| LangGraph nodes | LLM (OpenAI-compatible API) | REST (ChatOpenAI) | Summarization, classification, routing, solution generation |
| get_more_context_node | more_context_agent sub-graph | In-process (LangGraph sub-graph invocation) | Retrieves RAG + Loki context |
| RAGHandler | RAG service | REST (`/rag/query`) | Retrieves cheat-sheet context from FAISS knowledge base |
| Loki agent | MCP server | JSON-RPC over HTTP | Executes LogQL queries against Loki |
| Loki agent | LLM (tool-calling endpoint) | REST (ChatOpenAI with tools) | LLM selects and invokes Loki tools |
| clustering node | Clustering service | REST (`/cluster`) | Infers cluster label from embeddings |
| FastAPI backend | PostgreSQL (pgvector) | SQLModel/asyncpg | Persists GrafanaAlert records |

## Key Integration Points

### LangGraph StateGraph with Pydantic State

The entire pipeline shares a single `GrafanaAlertState` Pydantic model. Each node returns a `Command` that specifies the next node and state updates:

```python
# src/alm/agents/state.py
class GrafanaAlertState(BaseModel):
    log_entry: LogEntry = Field(description="The log entry that triggered the alert")
    logSummary: Optional[str] = None
    expertClassification: Optional[str] = None
    logCluster: Optional[str] = None
    needMoreContext: Optional[bool] = None
    stepByStepSolution: Optional[str] = None
    contextForStepByStepSolution: Optional[str] = None
```

### Conditional Routing via LLM Structured Output

The router node uses `with_structured_output` to constrain the LLM to a binary decision, which drives the graph edge:

```python
# src/alm/agents/graph.py:68-78
async def router_step_by_step_solution_node(state: GrafanaAlertState) -> Command:
    log_summary = state.logSummary
    classification = await router_step_by_step_solution(log_summary, llm)
    return Command(
        goto="suggest_step_by_step_solution_node"
        if classification == "No More Context Needed"
        else "get_more_context_node",
        update={"needMoreContext": classification == "Need More Context"},
    )
```

### Nested Sub-Graph Invocation

The `get_more_context_node` invokes a compiled sub-graph (`more_context_agent_graph`) as a nested LangGraph execution, passing a separate `ContextAgentState`:

```python
# src/alm/agents/graph.py:81-110
async def get_more_context_node(state: GrafanaAlertState) -> Command:
    subgraph_state = await more_context_agent_graph.ainvoke(
        ContextAgentState(
            log_summary=log_summary,
            log_entry=state.log_entry,
            expert_classification=state.expertClassification,
        )
    )
    context_agent_state = ContextAgentState.model_validate(subgraph_state)
    loki_context = context_agent_state.loki_context
    cheat_sheet_context = f"Context from cheat sheet:\n{context_agent_state.cheat_sheet_context}"
    context = (
        f"Context logs from loki:\n{loki_context}\n\n{cheat_sheet_context}"
        if loki_context else cheat_sheet_context
    )
    return Command(goto="suggest_step_by_step_solution_node",
                   update={"contextForStepByStepSolution": context})
```

### MCP Client for Loki Tool Calling

The Loki sub-agent uses an MCP client to query a Loki MCP server via JSON-RPC. The `MCPClient` manages session lifecycle (initialize, get_tools, call_tool):

```python
# src/alm/mcp/mcp_client.py:14-55
class MCPClient:
    def __init__(self, server_url):
        self.server_url = server_url
        self.session_id = None

    async def initialize(self):
        payload = {
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "clientInfo": {"name": "test-chat", "version": "1.0.0"},
            },
        }
        response = await self.client.post(self.server_url, json=payload, ...)
        self.session_id = response.headers.get("Mcp-Session-Id")

    async def call_tool(self, tool_name, arguments):
        payload = {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                   "params": {"name": tool_name, "arguments": arguments}}
        # ...
```

### LangChain Tool-Calling Agent with Closure-Bound Tools

The `LokiQueryAgent` uses `langchain.agents.create_agent` with LangChain `@tool`-decorated functions. One tool (`get_log_lines_above`) uses a Python closure factory to bind per-alert context (file_name, log_message, log_timestamp) at creation time, avoiding complex JSON serialization by the LLM:

```python
# src/alm/tools/loki_tools.py:347-368
def create_log_lines_above_tool(file_name, log_message, log_timestamp):
    @tool(args_schema=LogLinesAboveSchema)
    async def get_log_lines_above(lines_above: int = DEFAULT_LINE_ABOVE) -> str:
        # Uses closure-captured file_name, log_message, log_timestamp
        ...
    return get_log_lines_above
```

### Dual LLM Endpoint Configuration

The system supports two separate LLM endpoints: a default endpoint for structured-output tasks (summarize, classify, route) and a separate tool-calling-capable endpoint for the Loki agent. This accommodates model-serving platforms where tool calling may require a different model or endpoint:

```python
# src/alm/llm.py:67-91
def get_llm_support_tool_calling():
    API_KEY_WITH_TOOL_CALLING = os.getenv("OPENAI_API_TOKEN_WITH_TOOL_CALLING")
    BASE_URL_WITH_TOOL_CALLING = os.getenv("OPENAI_API_ENDPOINT_WITH_TOOL_CALLING")
    MODEL_WITH_TOOL_CALLING = os.getenv("OPENAI_MODEL_WITH_TOOL_CALLING")
    if API_KEY_WITH_TOOL_CALLING and BASE_URL_WITH_TOOL_CALLING and MODEL_WITH_TOOL_CALLING:
        return ChatOpenAI(api_key=API_KEY_WITH_TOOL_CALLING,
                          base_url=BASE_URL_WITH_TOOL_CALLING,
                          model=MODEL_WITH_TOOL_CALLING, ...)
    else:
        return get_llm()  # fallback to default
```

## Prompt / Chain Patterns

The system loads prompts from external Markdown files at module import time and uses them as system messages in structured-output LLM calls. Each node has a dedicated prompt file:

- `src/alm/agents/prompts/summarize_error_log.md` -- Extracts a concise summary from raw Ansible logs
- `src/alm/agents/prompts/classifiy_log.md` -- Classifies errors into one of eight expert categories (Cloud Infrastructure, Kubernetes, DevOps, Networking, SysAdmin, AppDev/GitOps, IAM, Other)
- `src/alm/agents/prompts/router_step_by_step_solution.md` -- Binary routing decision: "No More Context Needed" vs "Need More Context"
- `src/alm/agents/prompts/create_step_by_step_sol.md` -- Generates step-by-step remediation given log, summary, and optional context
- `src/alm/agents/get_more_context_agent/prompts/loki_router.md` -- Determines if Loki DB querying is needed after RAG retrieval
- `src/alm/agents/loki_agent/prompts/loki_agent_system_prompt.md` -- System prompt for the tool-calling Loki agent

All structured-output calls use Pydantic schemas with `Literal` type constraints to force the LLM into producing valid structured responses:

```python
# src/alm/agents/output_scheme.py
class ClassifySchema(BaseModel):
    category: Literal[
        "Cloud Infrastructure / AWS Engineers",
        "Kubernetes / OpenShift Cluster Admins",
        "DevOps / CI/CD Engineers (Ansible + Automation Platform)",
        "Networking / Security Engineers",
        "System Administrators / OS Engineers",
        "Application Developers / GitOps / Platform Engineers",
        "Identity & Access Management (IAM) Engineers",
        "Other / Miscellaneous",
    ] = Field(description="Category of the log")
```

## Gotchas

- The Loki tool-calling agent uses a separate LLM endpoint (`OPENAI_API_ENDPOINT_WITH_TOOL_CALLING`) because the primary RHOAI model serving endpoint may not support tool calling. The `get_llm_support_tool_calling()` function in `src/alm/llm.py:67` implements this workaround with a fallback to the default endpoint.
- Tool results from the Loki agent are cached in-memory (`src/alm/tools/loki_tool_cache.py`) and referenced by ID in `LightweightToolResponse` objects, because full log payloads are too large to pass through the LangChain agent message chain. The agent only sees a compact summary; full results are retrieved from cache by the graph node (`src/alm/agents/loki_agent/agent.py:151`).
- The `get_more_context_node` wraps the entire sub-graph invocation in a try/except and continues without context on failure (`src/alm/agents/graph.py:103-106`), making the context retrieval best-effort rather than required.
- Streaming with fallback (`src/alm/llm.py:48-64`) collects partial output if the stream is interrupted mid-response, returning whatever was received rather than failing completely.

## Related Architectures

- [rag-pipeline](rag-pipeline.md) -- The RAG sub-system that provides "cheat sheet" context to this agent orchestration via the RAGHandler
