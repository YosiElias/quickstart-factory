# PRD Features Schema

Defines the structure for `.rhoai-qs/{slug}/pipeline/prd-features.yaml`, the intermediate file that bridges PRD extraction and architecture design.

## Example

```json
{
  "input_features": {
    "components": ["api", "ui", "db"],
    "tech_stack": ["python", "fastapi", "react"],
    "ai_pattern": ["rag", "embeddings"],
    "platform": ["openshift-ai", "gpu"],
    "data_layer": ["postgresql", "vector-store", "document-upload"]
  },
  "deployment_questions": [
    "How should the ingestion pipeline be triggered — on upload or scheduled batch?"
  ],
  "decision_points": [
    "PRD mentions agents but does not specify Llama Stack — confirm orchestration approach",
    "Storage for uploaded documents not specified — MinIO or alternative?"
  ]
}
```

## Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `input_features` | object | 5-key feature classification from the PRD |
| `input_features.components` | array of strings | Application packages needed |
| `input_features.tech_stack` | array of strings | Frameworks, languages, runtimes |
| `input_features.ai_pattern` | array of strings | AI/ML patterns used |
| `input_features.platform` | array of strings | Deployment targets and infrastructure |
| `input_features.data_layer` | array of strings | Storage and data handling requirements |
| `deployment_questions` | array of strings | How-to questions about deployment/wiring |
| `decision_points` | array of strings | Unresolved choices the user needs to make |
