# AWS CI/CD Deployment

This runbook deploys `dstrmaysam-healthcare-knowledge-multi-agent` from GitHub to AWS with CodePipeline, CodeBuild, CodeDeploy, ECR, ECS Fargate, S3, OpenSearch Serverless, Secrets Manager, and RDS PostgreSQL.

The new deployment path does not use DynamoDB. Chat history and structured lookup storage use PostgreSQL.

## Deployed Architecture

- GitHub stores the source repository.
- CodePipeline watches the configured GitHub branch through a CodeStar connection.
- CodeBuild builds backend and frontend container images and pushes them to ECR.
- CodeDeploy performs blue/green deployments for the backend and frontend ECS services.
- ECS Fargate runs the FastAPI backend and Streamlit frontend.
- S3 stores uploaded source documents and manifests.
- OpenSearch Serverless stores retrieval indexes.
- Secrets Manager stores app secrets, Azure OpenAI credentials, Langfuse credentials, and the RDS password.
- RDS PostgreSQL stores deterministic lookup rows, uploaded CSV-derived rows, chat history, metadata, and outbox records.

## Resource Tags

Every CloudFormation-created resource that supports tagging uses:

| Key | Value |
| --- | --- |
| `dstrmaysam` | `true` |
| `project` | `healthcare-knowledge-multi-agent` |
| `owner` | `sabin` by default |

The template keeps the official project name as `dstrmaysam-healthcare-knowledge-multi-agent`, but uses the shorter `ResourceNamePrefix` parameter, default `dstrmaysam-hk-ma`, for AWS physical names that have strict length limits.

## Files

| File | Purpose |
| --- | --- |
| `infra/cloudformation/dstrmaysam-healthcare-knowledge-multi-agent-cicd.yml` | Main AWS runtime and CI/CD stack |
| `infra/cicd/buildspec.yml` | Builds Docker images, pushes to ECR, and creates ECS deployment artifacts |
| `infra/cicd/appspec-backend.yaml` | CodeDeploy AppSpec for the backend ECS service |
| `infra/cicd/appspec-frontend.yaml` | CodeDeploy AppSpec for the frontend ECS service |
| `infra/cicd/taskdef-backend.template.json` | Backend task definition template rendered by CodeBuild |
| `infra/cicd/taskdef-frontend.template.json` | Frontend task definition template rendered by CodeBuild |

## Prerequisites

1. Create or choose a VPC with at least two public subnets and two private subnets.
2. Create an AWS CodeStar Connections connection to GitHub and record its ARN.
3. Ensure your AWS account has permissions to create IAM roles, ECS, ECR, RDS, S3, OpenSearch Serverless, CodeBuild, CodeDeploy, and CodePipeline resources.
4. Keep Azure OpenAI and Langfuse values ready as JSON strings for the CloudFormation parameters.

## Secret JSON Parameters

`AppSecretJson` should contain app-level settings. Example:

```json
{
  "admin_password": "replace-me",
  "jwt_secret": "replace-me"
}
```

`AzureOpenAISecretJson` should contain:

```json
{
  "endpoint": "https://example.openai.azure.com/",
  "api_key": "replace-me",
  "chat_deployment": "replace-me",
  "fast_chat_deployment": "replace-me",
  "embedding_deployment": "replace-me"
}
```

`LangfuseSecretJson` should contain:

```json
{
  "public_key": "replace-me",
  "secret_key": "replace-me",
  "host": "https://cloud.langfuse.com"
}
```

The RDS password is generated into the `/dstrmaysam-healthcare-knowledge-multi-agent/<env>/postgres` secret by CloudFormation.

## Deploy The Stack

1. Validate the template locally:

```bash
aws cloudformation validate-template \
  --template-body file://infra/cloudformation/dstrmaysam-healthcare-knowledge-multi-agent-cicd.yml
```

2. Deploy the stack:

```bash
aws cloudformation deploy \
  --stack-name dstrmaysam-healthcare-knowledge-multi-agent-dev \
  --template-file infra/cloudformation/dstrmaysam-healthcare-knowledge-multi-agent-cicd.yml \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides \
    EnvironmentName=dev \
    ResourceNamePrefix=dstrmaysam-hk-ma \
    GitHubConnectionArn=arn:aws:codestar-connections:eu-west-2:<account-id>:connection/<connection-id> \
    GitHubRepository=<github-owner>/<github-repo> \
    GitHubBranch=feature/cicd_implementation \
    VpcId=vpc-xxxxxxxx \
    PublicSubnetIds=subnet-public-a,subnet-public-b \
    PrivateSubnetIds=subnet-private-a,subnet-private-b \
    DatabaseUsername=app_user \
    AppSecretJson='{"admin_password":"replace-me","jwt_secret":"replace-me"}' \
    AzureOpenAISecretJson='{"endpoint":"https://example.openai.azure.com/","api_key":"replace-me","chat_deployment":"replace-me","fast_chat_deployment":"replace-me","embedding_deployment":"replace-me"}' \
    LangfuseSecretJson='{"public_key":"replace-me","secret_key":"replace-me","host":"https://cloud.langfuse.com"}'
```

3. Open CodePipeline and confirm the source, build, and deploy stages complete.
4. Open the CloudFormation output `LoadBalancerUrl`.
5. Test `/health` on the backend route and the Streamlit frontend.

## First Deployment Notes

- The ECS task definitions in CloudFormation use `bootstrap` image tags. The first CodePipeline run replaces them with the image tag built from the Git commit SHA.
- The backend task sets `CHAT_HISTORY_BACKEND=postgres`.
- The backend task sets `TOOL_EXECUTION_BACKEND=local` by default. Change it to `mcp` only after an external FastMCP tool server is available.
- The OpenSearch Serverless collection is created by the stack, but index mappings may still need to be applied by your ingestion/bootstrap process before production use.
- The OpenSearch network policy in this starter template is public. Tighten it for production by limiting collection access to the VPC or private endpoint pattern you choose.

## Operational Checklist

1. Confirm ECS services are healthy after CodeDeploy swaps traffic.
2. Confirm the backend task can read S3, OpenSearch Serverless, Secrets Manager, and RDS.
3. Upload a CSV and verify rows are written to PostgreSQL.
4. Ask a deterministic lookup question and verify the multi-agent supervisor routes to `DeterministicLookupAgent`.
5. Upload documents and verify RAG questions use OpenSearch.
6. Check Langfuse traces and the Postgres outbox if trace publishing is unavailable.

## Changing To MCP Tool Execution

After the external FastMCP tool server is deployed:

1. Add the MCP service endpoint to the backend task definition:

```env
TOOL_EXECUTION_BACKEND=mcp
MCP_TOOL_SERVER_URL=https://<internal-tool-service>/mcp
MCP_TOOL_TIMEOUT_SECONDS=20
```

2. Ensure the MCP service implements the same tool names exposed by `backend/app/tooling/`.
3. Redeploy through CodePipeline.
4. Validate that the supervisor flow and saved `tools_used` values remain unchanged.
