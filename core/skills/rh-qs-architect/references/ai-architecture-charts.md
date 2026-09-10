# ai-architecture-charts

Repository: https://github.com/rh-ai-quickstart/ai-architecture-charts  
Helm repo: https://rh-ai-quickstart.github.io/ai-architecture-charts

Use during `rh-qs-architect` to select subcharts; `rh-qs-deploy` wires them as Helm dependencies.

## Architecture Components

### Core AI Services

#### LlamaStack (`llama-stack`)
Comprehensive AI orchestration platform that provides a unified API for multiple model providers, safety shields, and AI agent capabilities. Supports local models (via LLM Service), remote vLLM endpoints, and VertexAI integration.

**Key Features:**
- Multi-provider model support (local, remote, VertexAI)
- Safety shields with Llama Guard and other safety models
- AI agent capabilities with persistent memory
- Automatic model discovery and URL generation

#### OGX (`ogx-ai`)
Successor chart for OGX (formerly Llama Stack). Provides the same orchestration role as the llama-stack chart with OpenAI-compatible APIs, multi-provider model support, and MCP-style tool integration. Use **ogx-ai** for new deployments; **llama-stack** remains available for backwards compatibility.

**Key Features:**
- OpenAI-compatible agentic API server
- Multi-provider model support (local, remote, VertexAI)
- Content moderation via OpenAI-compatible `/v1/moderations` endpoint
- AI agent capabilities with persistent memory
- Automatic model discovery and URL generation

#### LLM Service (`llm-service`)
High-performance model serving infrastructure using vLLM runtime with OpenShift AI/KServe integration. Supports GPU and CPU deployment modes with any models compatible with vLLM.

**Key Features:**
- vLLM-based model serving with OpenAI-compatible API
- Support for any vLLM-compatible models and sizes
- GPU/CPU deployment flexibility
- Tool calling and function execution support

### Data & Storage Services

#### PGVector (`pgvector`)
PostgreSQL with pgvector extension providing high-performance vector database capabilities for storing and querying embeddings in AI/ML applications.

**Key Features:**
- Vector similarity search (cosine, L2, inner product)
- Multiple index types (IVFFlat, HNSW)
- Support for various embedding dimensions
- ACID compliance with PostgreSQL reliability

#### MinIO (`minio`)
S3-compatible object storage server for documents, models, and data in AI/ML pipelines. Provides scalable storage with web console management.

**Key Features:**
- S3-compatible API
- Web-based management console
- Bucket policies and lifecycle management
- Sample file upload functionality

#### Oracle 23ai (`oracle-db`)
Oracle Database Free 23ai with AI Vector features, providing enterprise-grade database capabilities with built-in vector operations for AI applications.

**Key Features:**
- Native vector operations and similarity search
- JSON duality and graph analytics
- Enterprise database reliability
- AI-optimized storage and indexing

**TPC-DS Data Population Job:**
The Oracle 23ai chart includes an automated TPC-DS data population job that creates comprehensive test datasets for AI/ML applications. This Kubernetes Job replaces manual database setup scripts with a cloud-native approach:

- **Purpose**: Automatically populates the Oracle database with standardized TPC-DS benchmark data (25 tables with synthetic retail/e-commerce data)
- **Scale Factor**: Configurable data volume (default generates ~1GB of test data)
- **Schema Management**: Creates both SYSTEM and Sales schemas with proper data distribution
- **Security**: Applies read-only restrictions to the Sales user for safe AI MCP server integration
- **Automation**: Eliminates manual database setup, ensuring consistent test data across deployments
- **Integration**: Provides realistic datasets for RAG applications, vector search testing, and AI agent development

The job runs automatically when `tpcds.enabled=true` and handles the complete lifecycle from database readiness verification to data loading and security configuration.

### Pipeline & Processing Services

#### Ingestion Pipeline (`ingestion-pipeline`)
Comprehensive data ingestion pipeline that processes documents from various sources (S3, GitHub, URLs) and stores vector embeddings for semantic search and RAG applications.

**Key Features:**
- Multi-source data ingestion (S3/MinIO, GitHub, URLs)
- Document chunking and embedding generation
- REST API for pipeline management
- Integration with vector databases

#### Configure Pipeline (`configure-pipeline`)
Jupyter notebook environment for RAG configuration and pipeline setup. Provides interactive tools for configuring and testing AI pipelines.

**Key Features:**
- Pre-configured Jupyter environment
- RAG pipeline configuration tools
- MinIO integration for data access
- Template and configuration management

### Integration & Tools

#### MCP Servers (`mcp-servers`)
Model Context Protocol servers that provide external tools and capabilities to AI models, enabling AI agents to interact with external systems and APIs.

**Key Features:**
- Weather information services
- Server-Sent Events (SSE) endpoints
- Custom tool development framework
- Integration with LlamaStack and OGX agents

#### Oracle SQLcl MCP (`oracle-sqlcl`)
MCP server that exposes Oracle SQLcl capabilities to AI agents via Toolhive, enabling database tooling and interactions from LlamaStack, OGX, and compatible clients.

**Key Features:**
- Execute SQL/PLSQL against Oracle databases via Model Context Protocol
- Integrates with Toolhive Operator (CRDs and operator managed as chart dependencies)
- Oracle connection managed via Kubernetes secrets and configurable service

### Security & Identity

#### Keycloak (`keycloak`)
Identity and access management solution providing authentication and authorization for AI applications. Supports OAuth2, OpenID Connect, and SAML protocols.

**Key Features:**
- Official Keycloak container images
- Built-in PostgreSQL database (via pgvector subchart) or external database support
- OpenShift Routes and Kubernetes Ingress support
- Production-ready configuration with health checks and metrics
- Flexible authentication and authorization policies
