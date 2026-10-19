#!/usr/bin/env python3
"""
OpenAI Decision API chart selector for AI Quickstarts.
Evaluates 11 charts in parallel using predicate questions.
"""

import argparse
import json
import os
import sys
from pathlib import Path

try:
    from openai import OpenAI
    import openai
except ImportError:
    print("Error: openai package not installed. Run: pip install openai", file=sys.stderr)
    sys.exit(1)

import yaml

# Constants
CHARTS_JSON_PATH = "core/skills/rh-qs-architect/references/ai-architecture-charts.json"
DEFAULT_INCLUDE_THRESHOLD = 0.7
DEFAULT_REVIEW_THRESHOLD = 0.4


def load_prd_features(path: Path) -> dict:
    """Load prd-features.yaml and return input_features and deployment_questions."""
    try:
        with open(path) as f:
            data = yaml.safe_load(f)
        return {
            "input_features": data.get("input_features", {}),
            "deployment_questions": data.get("deployment_questions", [])
        }
    except FileNotFoundError:
        print(f"Error: prd-features.yaml not found at {path}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error loading prd-features.yaml: {e}", file=sys.stderr)
        sys.exit(1)


def load_chart_capabilities(path: Path) -> dict:
    """Load ai-architecture-charts.json."""
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Error: ai-architecture-charts.json not found at {path}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error loading ai-architecture-charts.json: {e}", file=sys.stderr)
        sys.exit(1)


def build_input_context(input_features: dict, deployment_questions: list, chart_capabilities: dict) -> str:
    """Build input context JSON string for Decision API.

    Includes chart descriptions, capabilities (provides), and use_when guidance.
    """
    context = {
        "input_features": input_features,
        "deployment_questions": deployment_questions,
        "chart_capabilities": chart_capabilities
    }
    return json.dumps(context, indent=2)


def get_predicate_questions() -> list:
    """Define 11 predicate questions for chart selection."""
    return [
        {
            "type": "predicate",
            "name": "needs_llama_stack",
            "instructions": """Based on the llama-stack chart description and capabilities, does this quickstart need it?

NOTE: llama-stack is available for backwards compatibility. For new deployments, prefer ogx-ai.

Evaluate TRUE if:
- The quickstart requires multi-provider model access, safety shields, or comprehensive AI orchestration platform capabilities that LlamaStack provides
- The input_features or deployment_questions explicitly require LlamaStack-specific features
- This is an existing quickstart already using llama-stack

Evaluate FALSE if:
- The quickstart doesn't need these capabilities
- Uses a simpler orchestration approach
- This is a new deployment (prefer ogx-ai)
- Already uses OGX (which supersedes LlamaStack for new deployments)
- No orchestration framework mentioned"""
        },
        {
            "type": "predicate",
            "name": "needs_ogx",
            "instructions": """Based on the ogx-ai chart description and capabilities, does this quickstart need it?

NOTE: ogx-ai is the successor to llama-stack. Use for new deployments.

Evaluate TRUE if:
- The ai_pattern includes 'agents' or 'tool-calling'
- The tech_stack includes 'OGX'
- deployment_questions mention agent orchestration or tool integration
- Components include 'agents' or similar
- This is a new deployment requiring orchestration

Evaluate FALSE if:
- No agent orchestration needs
- Uses a custom framework without OGX
- Already using LlamaStack (backward compatibility case)"""
        },
        {
            "type": "predicate",
            "name": "needs_llm_service",
            "instructions": """Based on the llm-service chart description and capabilities, does this quickstart need it?

Evaluate TRUE if:
- The quickstart requires GPU/CPU model serving
- tech_stack includes 'vLLM' or 'model-serving'
- ai_pattern includes 'text-generation', 'classification', or other LLM-based patterns
- deployment_questions mention model serving strategy
- components include 'ml-serving'

Evaluate FALSE if:
- Uses external model APIs only (e.g., OpenAI, VertexAI)
- Doesn't serve models locally
- No LLM inference needed"""
        },
        {
            "type": "predicate",
            "name": "needs_pgvector",
            "instructions": """Based on the pgvector chart description and capabilities, does this quickstart need it?

Evaluate TRUE if:
- The ai_pattern includes 'rag', 'semantic-search', or 'retrieval'
- data_layer includes 'vector-store'
- tech_stack includes 'pgvector'
- deployment_questions mention vector search or embeddings

Evaluate FALSE if:
- No vector search or RAG capabilities needed
- Uses a different vector database (e.g., Oracle with vector features)
- No semantic retrieval required"""
        },
        {
            "type": "predicate",
            "name": "needs_minio",
            "instructions": """Based on the minio chart description and capabilities, does this quickstart need it?

Evaluate TRUE if:
- The quickstart needs S3-compatible storage for documents, models, or datasets
- tech_stack includes 'minio' or 's3'
- data_layer includes 'object-storage'
- deployment_questions mention object storage strategy
- components include 'storage'

Evaluate FALSE if:
- No object storage needs
- Uses external S3/cloud storage
- Only needs relational database storage"""
        },
        {
            "type": "predicate",
            "name": "needs_oracle_db",
            "instructions": """Based on the oracle-db chart description and capabilities, does this quickstart need it?

Evaluate TRUE if:
- The quickstart specifically requires Oracle database with vector operations
- tech_stack includes 'oracle' or 'Oracle'
- data_layer includes 'enterprise-db' or 'tpc-ds'
- deployment_questions mention Oracle-specific features

Evaluate FALSE if:
- Uses PostgreSQL or another database
- Doesn't need Oracle-specific features
- No enterprise database requirements"""
        },
        {
            "type": "predicate",
            "name": "needs_ingestion_pipeline",
            "instructions": """Based on the ingestion-pipeline chart description and capabilities, does this quickstart need it?

Evaluate TRUE if:
- The quickstart requires automated document ingestion from S3/GitHub/URLs
- deployment_questions mention data ingestion pipeline or automated ingestion
- ai_pattern includes 'rag' AND data needs to be ingested (not just queried)
- components include 'ingestion' or 'pipeline'

Evaluate FALSE if:
- Manual data upload only
- Application handles ingestion directly in code
- No automated ingestion needs"""
        },
        {
            "type": "predicate",
            "name": "needs_configure_pipeline",
            "instructions": """Based on the configure-pipeline chart description and capabilities, does this quickstart need it?

Evaluate TRUE if:
- The quickstart benefits from Jupyter-based RAG configuration tools
- platform includes 'interactive' or components include 'notebook'
- deployment_questions mention interactive pipeline setup or experimentation
- ai_pattern includes 'experimentation'

Evaluate FALSE if:
- RAG configuration is coded directly in the application
- No RAG needed
- No interactive development environment required"""
        },
        {
            "type": "predicate",
            "name": "needs_mcp_servers",
            "instructions": """Based on the mcp-servers chart description and capabilities, does this quickstart need it?

Evaluate TRUE if:
- The quickstart's agents require external tools (weather, custom MCP servers)
- deployment_questions mention tool integration, external tools, or MCP
- ai_pattern includes 'tool-calling' or 'agents' AND external tools are mentioned
- components include 'mcp' or 'tools'

Evaluate FALSE if:
- Agents use only built-in tools
- No agent capabilities needed
- No external tool integration required"""
        },
        {
            "type": "predicate",
            "name": "needs_oracle_sqlcl",
            "instructions": """Based on the oracle-sqlcl chart description and capabilities, does this quickstart need it?

Evaluate TRUE if:
- The quickstart's agents need to execute SQL/PLSQL against Oracle databases
- tech_stack includes 'oracle' AND ai_pattern includes 'agents' or 'tool-calling'
- deployment_questions specifically mention Oracle database interaction for agents
- ai_pattern includes 'text-to-sql' AND tech_stack includes 'oracle'

Evaluate FALSE if:
- No Oracle database
- Agents don't need database tooling
- Uses PostgreSQL or other databases"""
        },
        {
            "type": "predicate",
            "name": "needs_keycloak",
            "instructions": """Based on the keycloak chart description and capabilities, does this quickstart need it?

Evaluate TRUE if:
- The quickstart requires OAuth2, OpenID Connect, SAML, or multi-user authentication
- tech_stack includes 'keycloak'
- platform includes 'multi-user'
- components include 'auth' or 'authentication'
- deployment_questions mention IAM, authentication, or authorization

Evaluate FALSE if:
- Single-user demo
- No authentication needed
- Uses external IdP (identity provider)"""
        }
    ]


def call_decision_api(client: OpenAI, input_context: str, questions: list) -> dict:
    """Call OpenAI Decision API and return the response."""
    try:
        decision = client.decisions.create(
            model="gpt-6-luna",
            input=input_context,
            questions=questions
        )
        return decision
    except openai.APIError as e:
        print(f"Error: OpenAI API error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: Unexpected error calling Decision API: {e}", file=sys.stderr)
        sys.exit(1)


def process_answers(answers: list, include_threshold: float, review_threshold: float) -> tuple:
    """
    Process Decision API answers and return (selected_charts, uncertain_charts).

    Applies thresholds and enforces mutual exclusion (ogx over llama-stack).
    """
    selected = []
    uncertain = []

    for answer in answers:
        if answer.type == "refusal":
            print(f"Error: Question {answer.name} was refused by Decision API", file=sys.stderr)
            sys.exit(1)

        chart_name = answer.name.replace("needs_", "")
        chart_name = chart_name.replace("_", "-")  # needs_llm_service -> llm-service
        probability = answer.probability

        if probability >= include_threshold:
            selected.append({
                "name": chart_name,
                "reason": f"Selected with {probability:.2f} probability"
            })
        elif probability >= review_threshold:
            uncertain.append({
                "name": chart_name,
                "reason": f"Uncertain with {probability:.2f} probability"
            })

    # Enforce mutual exclusion: ogx over llama-stack
    selected_names = [c["name"] for c in selected]
    if "ogx-ai" in selected_names and "llama-stack" in selected_names:
        selected = [c for c in selected if c["name"] != "llama-stack"]

    return selected, uncertain


def print_chart_probabilities(answers: list, questions: list) -> None:
    """Print each chart's Decision API probability to stderr for debugging."""
    probabilities = {
        answer.name: answer.probability
        for answer in answers
        if answer.type != "refusal"
    }

    print("Chart probabilities (0-1):", file=sys.stderr)
    for question in questions:
        question_name = question["name"]
        chart_name = question_name.replace("needs_", "", 1).replace("_", "-")
        probability = probabilities.get(question_name)
        value = f"{probability:.3f}" if probability is not None else "unavailable"
        print(f"  {chart_name}: {value}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(
        description="Select ai-architecture-charts using OpenAI Decision API"
    )
    parser.add_argument("--slug", required=True, help="Quickstart slug")
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Print the probability of each chart to stderr"
    )
    parser.add_argument(
        "--prd-features-path",
        type=Path,
        help="Path to prd-features.yaml (optional, computed from slug if not provided)"
    )
    args = parser.parse_args()

    # Check for OPENAI_API_KEY
    if not os.getenv("OPENAI_API_KEY"):
        print("Error: OPENAI_API_KEY environment variable not set", file=sys.stderr)
        sys.exit(1)

    # Get thresholds from env vars or defaults
    include_threshold = float(os.getenv("CHART_SELECTOR_INCLUDE_THRESHOLD", DEFAULT_INCLUDE_THRESHOLD))
    review_threshold = float(os.getenv("CHART_SELECTOR_REVIEW_THRESHOLD", DEFAULT_REVIEW_THRESHOLD))

    # Compute paths
    if args.prd_features_path:
        prd_features_path = args.prd_features_path
    else:
        prd_features_path = Path(f".rhoai-qs/{args.slug}/.qs-factory/pipeline/prd-features.yaml")

    charts_json_path = Path(CHARTS_JSON_PATH)

    # Load inputs
    prd_data = load_prd_features(prd_features_path)
    chart_capabilities = load_chart_capabilities(charts_json_path)

    # Build input context
    input_context = build_input_context(
        prd_data["input_features"],
        prd_data["deployment_questions"],
        chart_capabilities
    )

    # Get predicate questions
    questions = get_predicate_questions()

    # Call Decision API
    client = OpenAI()
    decision = call_decision_api(client, input_context, questions)

    if args.debug:
        print_chart_probabilities(decision.answers, questions)

    # Process answers
    selected_charts, uncertain_charts = process_answers(
        decision.answers,
        include_threshold,
        review_threshold
    )

    # Output JSON
    output = {
        "selected": selected_charts,
        "uncertain": uncertain_charts
    }
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
