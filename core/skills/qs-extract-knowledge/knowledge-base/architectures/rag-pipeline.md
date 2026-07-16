---
name: rag-pipeline
description: "PDF-to-FAISS RAG pipeline with TEI embeddings, MinIO index storage, and HTTP query API for error resolution"
summary: "Implements offline PDF-to-FAISS RAG for Ansible error resolution — an init job (AnsibleErrorParser + AnsibleErrorEmbedder) parses PDFs into structured error chunks, embeds via TEI nomic-embed-text-v1.5 with \"search_document:\" prefix, and stores FAISS index plus error store in MinIO over S3 API. Single-approach split build/serve architecture for offline-ingestion RAG pipelines — init job skips rebuilds when an index exists in MinIO unless RAG_FORCE_REBUILD=true; RAGHandler singleton gracefully degrades (returns empty string) when RAG_ENABLED=false or service unreachable, letting the agent pipeline continue without context. FastAPI query service at /rag/query embeds queries (\"search_query:\" prefix) via persistent httpx.AsyncClient (20 keepalive/100 max connections), normalizes vectors for FAISS similarity search filtered by RAG_SIMILARITY_THRESHOLD/RAG_TOP_K/RAG_TOP_N env vars, and background-polls MinIO using LATEST.json pointer for hot-reload of new index builds. Key gotchas: nomic-embed-text-v1.5 requires distinct task prefixes (\"search_document:\" for ingest vs \"search_query:\" for queries), wait_for_rag_service blocks polling /ready every 5s up to 10min TimeoutError for init synchronization, and RAG results are injected into the agent solution prompt via {context} template variable — not a standalone chain."
metadata:
  type: architecture
tags:
  tech_stack: [fastapi, python, minio]
  ai_pattern: [rag, embeddings, vector-search]
  platform: [openshift]
  data_layer: [faiss, minio]
source_examples:
  - quickstart: "ansible-log-analysis"
    repo: "https://github.com/rh-ai-quickstart/ansible-log-analysis"
    notes: "Offline PDF ingestion pipeline builds FAISS index in MinIO; separate FastAPI service serves similarity queries using TEI for embeddings"
    approach: "A"
---

# RAG Pipeline

## Overview

This architecture implements retrieval-augmented generation for Ansible error resolution. An offline init job parses PDF knowledge-base documents, chunks them into structured error records, embeds them using a TEI (Text Embeddings Inference) service running nomic-embed-text-v1.5, builds a FAISS index, and stores all artifacts in MinIO. A separate FastAPI RAG service loads the index from MinIO on startup, accepts query requests, embeds the query via TEI, performs FAISS similarity search, and returns matching error solutions. The main application backend consumes this service through an HTTP client (`RAGHandler`) to inject "cheat sheet" context into the agent pipeline.

## Data Flow

### Index Build (Offline Init Job)

1. `rag_init_pipeline.py` starts the init job (`services/rag/rag_init_pipeline.py:156-175`)
2. `AnsibleErrorParser.parse_pdf_to_chunks()` extracts structured error chunks from PDF files in the knowledge base directory (`services/rag/rag_init_pipeline.py:126`)
3. All chunks from all PDFs are collected into a single list (`services/rag/rag_init_pipeline.py:122-139`)
4. `AnsibleErrorEmbedder.ingest_and_index_to_minio()` embeds chunks via TEI and builds a FAISS index (`services/rag/rag_init_pipeline.py:143`)
5. The FAISS index, error store, and metadata are uploaded to MinIO (`services/rag/rag_init_pipeline.py:143`)

### Query Time (Online)

1. The main backend's `RAGHandler` sends a POST to `/rag/query` with the log summary (`src/alm/utils/rag_handler.py:175-183`)
2. The RAG service embeds the query text via TEI using a persistent `httpx.AsyncClient` with connection pooling (`services/rag/main.py:265-271`)
3. The query embedding is normalized and searched against the FAISS index (`services/rag/main.py:298-300`)
4. Results are filtered by similarity threshold and limited to top-N (`services/rag/main.py:310-343`)
5. The RAGHandler formats results into a markdown string for LLM consumption (`src/alm/utils/rag_handler.py:87-135`)

## Component Wiring

| From | To | Protocol | Purpose |
|------|----|----------|---------|
| Init job | Knowledge base PDFs | Filesystem | Reads PDF documents for chunking |
| Init job (AnsibleErrorEmbedder) | TEI service | REST (`/embeddings`) | Generates embeddings for error chunks |
| Init job | MinIO | S3 API | Stores FAISS index, error store, and metadata |
| RAG service | MinIO | S3 API | Loads FAISS index on startup and polls for updates |
| RAG service | TEI service | REST (`/embeddings`) | Embeds query text at query time |
| Main backend (RAGHandler) | RAG service | REST (`/rag/query`) | Retrieves matching error solutions |

## Key Integration Points

### RAG Service Query Endpoint

The RAG service exposes a `/rag/query` endpoint that handles the full query pipeline (embed, search, filter, return):

```python
# services/rag/main.py:215-368
@app.post("/rag/query", response_model=QueryResponse)
async def query_rag(request: QueryRequest):
    # Step 1: Generate query embedding via TEI
    query_text = f"search_query: {request.query}"
    embedding_response = await embedding_client.post(
        "/embeddings",
        json={"input": [query_text], "model": "nomic-embed-text-v1.5"},
    )
    # Step 2: Normalize and search FAISS
    query_vector = query_embedding.reshape(1, -1)
    similarities, indices = index_loader.index.search(query_vector, request.top_k)
    # Step 3: Filter by threshold, return top-N
```

### RAGHandler Singleton Client

The main backend uses a singleton `RAGHandler` that lazily initializes an `httpx.AsyncClient` and queries the RAG service. It gracefully degrades when RAG is disabled or the service is unavailable:

```python
# src/alm/utils/rag_handler.py:137-200
async def get_cheat_sheet_context(self, log_summary: str) -> str:
    if not self._initialize_rag_service():
        return ""
    response = await self._client.post(
        "/rag/query",
        json={
            "query": log_summary,
            "top_k": int(os.getenv("RAG_TOP_K", "3")),
            "top_n": int(os.getenv("RAG_TOP_N", "1")),
            "similarity_threshold": float(os.getenv("RAG_SIMILARITY_THRESHOLD", "0.6")),
        },
    )
    return self._format_rag_results(response.json())
```

### Index Loading with Background Polling

The RAG service attempts to load the FAISS index from MinIO at startup. If the index is not yet available (init job still running), a background polling task retries every 20 seconds. It also supports hot-reloading when a new index build is detected:

```python
# services/rag/main.py:103-168
async def poll_for_index():
    while True:
        if index_loader is not None and index_loader.index is not None:
            # Check for rebuild via LATEST.json pointer
            if force_rebuild:
                response = index_loader.minio_client.get_object(
                    index_loader.bucket_name, "LATEST.json")
                pointer = json.loads(response.read().decode())
                latest_build_id = pointer.get("build_id")
                if latest_build_id != index_loader.last_loaded_build_id:
                    await index_loader.reload_index()
            await asyncio.sleep(poll_interval)
            continue
        success = await load_index()
        await asyncio.sleep(poll_interval)
```

### Nomic Embedding Task Prefix

The TEI service uses nomic-embed-text-v1.5, which requires task-specific prefixes. The RAG service prepends `"search_query: "` to queries at query time (`services/rag/main.py:260`). The ingest pipeline uses `"search_document: "` as the prefix for document chunks (handled in `services/rag/src/rag/embed_and_index.py`).

## Prompt / Chain Patterns

The RAG pipeline does not use prompt chains itself. It provides context to the agent orchestration pipeline, which injects RAG results into the solution-generation prompt as `{context}`:

```python
# src/alm/agents/prompts/prompts.py:31-42
suggest_step_by_step_solution_with_context_user_message = """**Log Summary:**
```
{log_summary}
```
**Additional Context:**
```
{context}
```
**Error Log:**
```
{log}
```"""
```

## Gotchas

- The RAG init job checks MinIO for an existing index before rebuilding (`services/rag/rag_init_pipeline.py:76-91`). To force a rebuild, set `RAG_FORCE_REBUILD=true`. Without this, upgrades skip the expensive PDF-parse-and-embed step if an index already exists.
- The `RAGHandler` is a singleton with lazy initialization (`src/alm/utils/rag_handler.py:23-25`). The RAG service URL comes from `RAG_SERVICE_URL` env var, and the feature can be disabled entirely via `RAG_ENABLED=false`. When disabled or when the service is unreachable, the handler returns an empty string, and the agent pipeline continues without RAG context.
- The RAG service uses a persistent `httpx.AsyncClient` with connection pooling (20 keepalive connections, 100 max) for the TEI embedding service (`services/rag/main.py:173-180`), initialized at startup and closed on shutdown.
- The `wait_for_rag_service` utility in `src/alm/utils/rag_service.py` is a blocking wait used by init jobs that depend on the RAG service being ready. It polls the `/ready` endpoint every 5 seconds for up to 10 minutes and raises `TimeoutError` on failure.

## Related Architectures

- [agent-orchestration](agent-orchestration.md) -- The agent pipeline that consumes RAG results as "cheat sheet" context for error remediation
