# AWS Dev Deployment Notes

Use the JSON templates in this folder as starting points for ECS Fargate task definitions and IAM policies. The CloudFormation and CodePipeline deployment path lives under `infra/cloudformation/` and `infra/cicd/`.

Required AWS resources:

- S3 bucket for raw documents and document manifests
- RDS PostgreSQL database for chat history and structured lookup storage
- OpenSearch Serverless vector collection and index
- ECR repository for backend image
- ECR repository for frontend image
- ECS cluster with two Fargate services
- Application Load Balancer with routes for Streamlit and FastAPI
- CloudWatch log groups
- Secrets Manager secrets:
- `/dstrmaysam-healthcare-knowledge-multi-agent/dev/app`
- `/dstrmaysam-healthcare-knowledge-multi-agent/dev/azure-openai`
- `/dstrmaysam-healthcare-knowledge-multi-agent/dev/langfuse`

The ECS task execution role pulls images and writes logs. The ECS task role reads only the required secret ARNs and application resources.

Use `opensearch-index.json` as the expected OpenSearch index mapping; adjust `embedding.dimension` if your Azure embedding deployment uses a different vector dimension. The older `dynamodb-chat-history-table.json` is kept only as a legacy reference; new AWS deployments should use RDS PostgreSQL.
