# Red Hat OpenShift AI 3.4 feature mapping

| RHOAI feature | Maps to |
|---------------|---------|
| Model Serving (KServe / ModelMesh) | llm-service chart, vLLM runtime |
| Data Science Pipelines (Tekton) | configure-pipeline, ingestion-pipeline |
| Workbenches (JupyterLab) | configure-pipeline chart |
| Model Registry | model-registry chart |
| TrustyAI (bias/explainability) | Llama Stack safety shields |
| Distributed Workloads (Ray/Kueue) | Custom — not in charts yet |
| GPU autoscaling | llm-service tolerations + node selectors |
