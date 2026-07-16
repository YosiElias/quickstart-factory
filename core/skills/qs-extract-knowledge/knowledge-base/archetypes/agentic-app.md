---
name: agentic-app
description: "Agent-based architecture using LLM-powered workflows with tool use, routing, and multi-step reasoning"
summary: "An agentic app orchestrates multi-step LLM-powered workflows with reasoning, tool use, and conditional routing using FastAPI, LangGraph for agent orchestration, LangChain, and Gradio for expert-facing dashboards, served by RHOAI vLLM with MCP servers for external tool integration and TEI for embedding generation. Use when the solution path depends on intermediate LLM decisions requiring sub-agent delegation and LLM-powered routing — choose over model-serving app (single inference call) when multi-step tool invocation is needed, and over RAG chatbot when retrieval is one sub-step among several; ansible-log-analysis demonstrates the pattern with Grafana alert ingestion, Loki MCP log queries, RAG cheat-sheet retrieval, and remediation generation. The data layer combines PostgreSQL for persistent storage, FAISS for vector similarity search, and MinIO for object storage, with Phoenix plus OpenTelemetry for LLM observability and Grafana/Loki for log ingestion and alerting. Common gotcha: the defining distinction is that the agent makes routing decisions between LLM calls based on intermediate results — if the workflow is a fixed pipeline without LLM-driven branching, a simpler archetype (model-serving or RAG chatbot) will be easier to operate and debug."
metadata:
  type: archetype
tags:
  tech_stack: [fastapi, langgraph, langchain, gradio, postgresql]
  ai_pattern: [agents, rag, embeddings, vector-search, model-serving]
  platform: [rhoai, openshift, vllm]
  data_layer: [pgvector, faiss, minio]
source_examples:
  - quickstart: "ansible-log-analysis"
    repo: "https://github.com/rh-ai-quickstart/ansible-log-analysis"
    notes: "Multi-agent LangGraph workflow with MCP tool integration, sub-agent delegation, LLM-powered routing, and RAG-enhanced remediation for Ansible log errors"
    approach: "A"
---

# Agentic App

## Overview

An agentic app uses LLM-powered agents to orchestrate multi-step workflows that involve reasoning, tool use, and conditional routing. Rather than a single prompt-response cycle, the agent breaks a problem into stages, invokes external tools (databases, APIs, search indices) to gather context, and synthesizes a final output. This archetype leverages RHOAI for model serving while the agent orchestration layer runs as a standard application workload.

## Typical Components

- **Model serving:** RHOAI model serving (vLLM) or any OpenAI-compatible endpoint for LLM inference
- **Backend:** FastAPI for API endpoints, LangGraph for agent workflow orchestration, LangChain for LLM abstraction
- **Frontend:** Gradio for expert-facing dashboards and annotation interfaces
- **Data layer:** PostgreSQL for persistent storage, FAISS for vector similarity search, MinIO for object storage
- **Supporting:** MCP (Model Context Protocol) servers for tool integration, TEI for embedding generation, Grafana/Loki for log ingestion and alerting, Phoenix + OpenTelemetry for LLM observability

## When to Use

- The problem requires **multi-step reasoning** where the solution path is not known in advance and depends on intermediate LLM decisions
- The workflow needs to **invoke external tools** (databases, APIs, log systems) to gather context before generating a response
- Different inputs require **different processing paths**, determined by LLM-powered routing at runtime
- The application benefits from **sub-agent delegation**, where specialized agents handle specific subtasks (e.g., log querying, knowledge retrieval) within a larger workflow
- The system needs to **combine multiple AI capabilities** (summarization, classification, retrieval, generation) in a single coordinated pipeline

## Example Quickstarts

| Quickstart | What It Demonstrates |
|------------|---------------------|
| ansible-log-analysis | Multi-agent LangGraph workflow that receives Grafana alerts, clusters and summarizes logs, classifies errors by expert domain, routes to context-gathering sub-agents (Loki MCP queries, RAG cheat-sheet retrieval), and generates step-by-step remediation |

## Decision Criteria

### vs Model-Serving App

Pick **agentic-app** when the application needs multi-step reasoning, tool invocation, and conditional routing -- not just a single inference call. A model-serving app exposes a model endpoint and may wrap it with a thin API, but the logic is a single prompt-response cycle. An agentic app orchestrates multiple LLM calls, gathers external context between them, and makes routing decisions that determine the next step.

### vs RAG Chatbot

Pick **agentic-app** when retrieval is one tool among several in a larger workflow, rather than the core interaction pattern. A RAG chatbot centers on retrieve-then-generate for user queries against a knowledge base. An agentic app may include RAG as a sub-step (e.g., retrieving a "cheat sheet" of previously solved errors), but the defining pattern is the multi-step agent orchestration with routing and tool use beyond just retrieval.
