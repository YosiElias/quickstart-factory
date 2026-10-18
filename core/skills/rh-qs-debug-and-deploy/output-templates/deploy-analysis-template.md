# Deploy Analysis Output Schema

Write `{state_dir}/deploy-analysis.yaml` with this structure:

```yaml
project_path: /absolute/path/to/project
namespace: target-namespace
deployment_method: helm | oc-apply | custom-script

# Mutually-exclusive OpenShift deployment variants found in project docs.
# Omit this field entirely when the project has only one OpenShift deployment path.
deployment_options:
  - id: local-model
    label: "Local model serving (vLLM in-cluster)"
    description: "Deploys the llm-service chart; the model runs in-namespace on GPU"
    requires: { gpu: true, gpu_count: 1 }
    recommended: true
    rationale: "Documented as the primary path in README section 'Quickstart'"
    deploy_commands:
      - description: "Install with in-cluster model serving"
        command: "helm install my-quickstart ./chart -n <namespace> -f values-openshift.yaml"
  - id: external-endpoint
    label: "External inference endpoint"
    description: "Skips llm-service; the app points at an existing OpenAI-compatible endpoint"
    requires: { gpu: false, api_key: "LLM_API_KEY", endpoint_url: "LLM_ENDPOINT" }
    recommended: false
    rationale: "README section 'Bring your own model'"
    deploy_commands:
      - description: "Install with external endpoint"
        command: "helm install my-quickstart ./chart -n <namespace> -f values-external-llm.yaml"

# Which deployment_options entry was chosen. Written by the main agent in Phase 1d.
# null when deployment_options is absent (single deployment path).
selected_option_id: local-model

# Exact deploy commands found in project docs (README, DEPLOYMENT.md, Makefile, etc.)
# These are the ACTUAL commands for this specific project, not generic templates.
# When deployment_options is present, this is the selected option's deploy_commands —
# the analyzer seeds it with the recommended option, the main agent overwrites it in Phase 1d.
# Every phase after 1d reads deploy commands from here and nowhere else.
deploy_commands:  
  - description: "Install Helm chart with OpenShift mode"
    command: "helm install my-quickstart ./chart -n <namespace> --set openshiftMode=true -f values-openshift.yaml"
  - description: "Apply post-install config"
    command: "oc apply -f ./deploy/post-install/ -n <namespace>"

# Where deploy instructions were found
deploy_instructions_source: "README.md section 'RHOAI Deployment'"

# Helm-specific (if deployment_method is helm)
helm:
  chart_path: ./chart
  release_name: my-quickstart
  values_files: [values.yaml, values-openshift.yaml]

# All Kubernetes resources expected after deployment
expected_resources:
  deployments: [postgresql, redis, app-server, embedding-service]
  statefulsets: []
  services: [postgresql-svc, redis-svc, app-server-svc, embedding-svc]
  pvcs: [postgresql-data, redis-data]
  routes: [app-route]
  configmaps: [app-config, model-config]
  secrets: [db-credentials, api-keys]
  jobs: []

# Component details with dependencies
components:
  - name: postgresql
    kind: Deployment
    dependencies: []
    resource_requirements:
      storage: 10Gi
      gpu: false
      cpu: "500m"
      memory: "1Gi"
  - name: redis
    kind: Deployment
    dependencies: []
    resource_requirements:
      storage: 1Gi
      gpu: false
  - name: embedding-service
    kind: Deployment
    dependencies: [postgresql]
    resource_requirements:
      gpu: true
      gpu_count: 1
      gpu_type: "nvidia.com/gpu"
  - name: app-server
    kind: Deployment
    dependencies: [postgresql, redis, embedding-service]
    resource_requirements:
      gpu: false
      cpu: "1"
      memory: "2Gi"

# Dependency order — leaves first (resources with no dependencies)
dependency_order:
  - level_0: [postgresql, redis]        # No dependencies
  - level_1: [embedding-service]        # Depends on level_0
  - level_2: [app-server]              # Depends on level_0 + level_1

# High-level structure overview
structure_overview: |
  RAG pipeline quickstart with PostgreSQL for metadata, Redis for caching,
  embedding service for vector generation, and app-server as the main API.
  PostgreSQL and Redis are independent. Embedding service needs PostgreSQL
  for model config. App-server depends on all three.
```
