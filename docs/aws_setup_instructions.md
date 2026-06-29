# AWS Foundation Setup: Healthcare Knowledge Multi-Agent

Version: 2.0  
Target stage: `dev`  
Default region: `eu-west-2`  
Base name: `dstrmaysam-healthcare-knowledge-multi-agent-dev`

This runbook creates the AWS foundation resources required by AWS mode. The foundation stack now creates a small isolated VPC and two private subnets for RDS. ALB HTTPS, ECS service creation, and CICD are intentionally left for the future CICD pipeline phase.

## 1. Resources Created

The CloudFormation template `infra/aws-foundation.yml` creates:

- S3 bucket: `dstrmaysam-healthcare-knowledge-multi-agent-dev`
- Secrets Manager secrets:
  - `/dstrmaysam-healthcare-knowledge-multi-agent-dev/app`
  - `/dstrmaysam-healthcare-knowledge-multi-agent-dev/azure-openai`
  - `/dstrmaysam-healthcare-knowledge-multi-agent-dev/langfuse`
- Isolated VPC and two private subnets for RDS networking
- RDS Postgres instance with generated master password secret
- OpenSearch Serverless vector collection and access policies
- ECR repository: `dstrmaysam-healthcare-knowledge-multi-agent-dev`
- ECS cluster: `dstrmaysam-healthcare-knowledge-multi-agent-dev`
- ECS execution, backend task, and frontend task IAM roles
- CloudWatch log groups for future backend/frontend ECS tasks

All supported resources are tagged:

```text
Project=dstrmaysam-healthcare-knowledge-multi-agent
Application=dstrmaysam
Owner=Sabin
```

OpenSearch Serverless and IAM role physical names use the short name `dstrmaysam-hkm-dev` where AWS limits prevent the full base name.

## 2. Prerequisites

Install/configure:

- AWS CLI v2
- Docker
- `psql`
- `jq`
- AWS credentials with permission to create CloudFormation, S3, Secrets Manager, RDS, OpenSearch Serverless, ECR, ECS, IAM, and CloudWatch Logs resources

Set local shell variables:

```bash
export AWS_REGION=eu-west-2
export STACK_NAME=dstrmaysam-healthcare-knowledge-multi-agent-dev
export BASE_NAME=dstrmaysam-healthcare-knowledge-multi-agent-dev
export VPC_CIDR=10.40.0.0/16
export PRIVATE_SUBNET_ONE_CIDR=10.40.1.0/24
export PRIVATE_SUBNET_TWO_CIDR=10.40.2.0/24
export DATABASE_INGRESS_CIDR=10.40.0.0/16
export AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
```

## 3. Validate And Deploy Foundation Stack

Validate:

```bash
aws cloudformation validate-template \
  --template-body file://infra/aws-foundation.yml \
  --region "$AWS_REGION"
```

Preview a changeset without executing:

```bash
aws cloudformation deploy \
  --stack-name "$STACK_NAME" \
  --template-file infra/aws-foundation.yml \
  --region "$AWS_REGION" \
  --capabilities CAPABILITY_NAMED_IAM \
  --no-execute-changeset \
  --parameter-overrides \
    VpcCidr="$VPC_CIDR" \
    PrivateSubnetOneCidr="$PRIVATE_SUBNET_ONE_CIDR" \
    PrivateSubnetTwoCidr="$PRIVATE_SUBNET_TWO_CIDR" \
    DatabaseIngressCidr="$DATABASE_INGRESS_CIDR"
```

Create/update:

```bash
aws cloudformation deploy \
  --stack-name "$STACK_NAME" \
  --template-file infra/aws-foundation.yml \
  --region "$AWS_REGION" \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides \
    VpcCidr="$VPC_CIDR" \
    PrivateSubnetOneCidr="$PRIVATE_SUBNET_ONE_CIDR" \
    PrivateSubnetTwoCidr="$PRIVATE_SUBNET_TWO_CIDR" \
    DatabaseIngressCidr="$DATABASE_INGRESS_CIDR"
```

Capture outputs:

```bash
aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --region "$AWS_REGION" \
  --query "Stacks[0].Outputs" \
  --output table
```

Important outputs:

- `VpcId`
- `PrivateSubnetOneId`
- `PrivateSubnetTwoId`
- `DatabaseSecurityGroupId`
- `DatabaseEndpoint`
- `DatabaseMasterSecretArn`
- `OpenSearchCollectionEndpoint`
- `EcrRepositoryUri`
- `EcsClusterName`
- `BackendTaskRoleArn`
- `FrontendTaskRoleArn`
- `EcsExecutionRoleArn`

## 4. Populate Secrets Manager Values

The template creates placeholder secrets. Replace them before starting the backend.

Generate an app password hash:

```bash
python -m backend.app.auth hash-password
```

Update the app secret:

```bash
aws secretsmanager put-secret-value \
  --region "$AWS_REGION" \
  --secret-id "/$BASE_NAME/app" \
  --secret-string '{
    "session_secret": "replace-with-long-random-value",
    "auth_users": {
      "admin": "replace-with-generated-password-hash"
    },
    "user_profiles": {
      "admin": {
        "roles": ["admin", "doctor"],
        "departments": ["clinical_governance"]
      }
    }
  }'
```

Update Azure OpenAI:

```bash
aws secretsmanager put-secret-value \
  --region "$AWS_REGION" \
  --secret-id "/$BASE_NAME/azure-openai" \
  --secret-string '{
    "endpoint": "https://YOUR-RESOURCE.openai.azure.com/",
    "api_key": "replace-with-azure-openai-key",
    "api_version": "2025-04-01-preview",
    "chat_deployment": "gpt-4.1-mini",
    "fast_chat_deployment": "gpt-4.1-mini",
    "embedding_deployment": "text-embedding-3-small"
  }'
```

Update Langfuse:

```bash
aws secretsmanager put-secret-value \
  --region "$AWS_REGION" \
  --secret-id "/$BASE_NAME/langfuse" \
  --secret-string '{
    "public_key": "pk-lf-...",
    "secret_key": "sk-lf-...",
    "base_url": "https://cloud.langfuse.com"
  }'
```

## 5. Initialize RDS Postgres Schema And Seed Data

Get RDS outputs:

```bash
export POSTGRES_HOST=$(aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --region "$AWS_REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='DatabaseEndpoint'].OutputValue" \
  --output text)

export DB_SECRET_ARN=$(aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --region "$AWS_REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='DatabaseMasterSecretArn'].OutputValue" \
  --output text)

export POSTGRES_PASSWORD=$(aws secretsmanager get-secret-value \
  --region "$AWS_REGION" \
  --secret-id "$DB_SECRET_ARN" \
  --query SecretString \
  --output text | jq -r .password)
```

Run schema and seed SQL from a network location allowed by `DatabaseIngressCidr`. The RDS instance is private inside the stack-created VPC, so a local laptop will not connect directly unless you provide a network path such as VPN, peering, an admin host, or a future ECS task in the VPC.

```bash
export PGSSLMODE=require
export PGPASSWORD="$POSTGRES_PASSWORD"

psql \
  --host "$POSTGRES_HOST" \
  --port 5432 \
  --username healthcare_agent \
  --dbname healthcare_agent \
  --file database/init/01_schema.sql

psql \
  --host "$POSTGRES_HOST" \
  --port 5432 \
  --username healthcare_agent \
  --dbname healthcare_agent \
  --file database/init/02_seed.sql
```

## 6. Build And Push Images To One ECR Repository

The foundation stack creates one ECR repository. Use different image tags for backend and frontend.

```bash
export ECR_REPOSITORY_URI=$(aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --region "$AWS_REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='EcrRepositoryUri'].OutputValue" \
  --output text)

aws ecr get-login-password --region "$AWS_REGION" \
  | docker login --username AWS --password-stdin "$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com"

docker build -t "$BASE_NAME:backend-latest" backend
docker tag "$BASE_NAME:backend-latest" "$ECR_REPOSITORY_URI:backend-latest"
docker push "$ECR_REPOSITORY_URI:backend-latest"

docker build -t "$BASE_NAME:frontend-latest" frontend
docker tag "$BASE_NAME:frontend-latest" "$ECR_REPOSITORY_URI:frontend-latest"
docker push "$ECR_REPOSITORY_URI:frontend-latest"
```

The database image is for local Docker Compose only and is not required for RDS.

## 7. AWS Mode Runtime Environment

Backend ECS task/service environment should use:

```env
APP_ENV=dev
AWS_REGION=eu-west-2
SECRETS_STAGE=dev
LOCAL_TEST_ADMIN_ENABLED=false

APP_SECRET_NAME=/dstrmaysam-healthcare-knowledge-multi-agent-dev/app
AZURE_OPENAI_SECRET_NAME=/dstrmaysam-healthcare-knowledge-multi-agent-dev/azure-openai
LANGFUSE_SECRET_NAME=/dstrmaysam-healthcare-knowledge-multi-agent-dev/langfuse

S3_BUCKET=dstrmaysam-healthcare-knowledge-multi-agent-dev
S3_RAW_PREFIX=raw/
S3_MANIFEST_KEY=manifests/documents.json

OPENSEARCH_ENDPOINT=<OpenSearchCollectionEndpoint output>
OPENSEARCH_INDEX=dstrmaysam-healthcare-knowledge-multi-agent-dev

CHAT_HISTORY_BACKEND=postgres
POSTGRES_HOST=<DatabaseEndpoint output>
POSTGRES_PORT=5432
POSTGRES_DB=healthcare_agent
POSTGRES_USER=healthcare_agent
POSTGRES_PASSWORD=<inject from DatabaseMasterSecretArn password>
POSTGRES_SSLMODE=require
```

Frontend ECS task/service environment should use:

```env
BACKEND_URL=http://<backend-service-discovery-name>:8000
```

The example task definitions in `infra/` use these values as placeholders. The future CICD/networking phase should substitute stack outputs into ECS task definitions and services.

## 8. OpenSearch Index Creation And Verification

The backend ingestion path calls the application index bootstrap logic and uses `infra/opensearch-index.json` shape internally. After the backend is running with AWS mode values:

1. Upload source documents to:

```text
s3://dstrmaysam-healthcare-knowledge-multi-agent-dev/raw/
```

2. Run ingestion from the admin UI or as a one-off backend task.

3. Verify documents and the manifest:

```bash
aws s3 ls "s3://$BASE_NAME/raw/" --region "$AWS_REGION"
aws s3 cp "s3://$BASE_NAME/manifests/documents.json" - --region "$AWS_REGION"
```

If OpenSearch permissions fail, confirm:

- Backend task role has `aoss:APIAccessAll`.
- OpenSearch data access policy includes the backend task role ARN.
- Network policy allows the backend networking path.

## 9. Delete Resources

Before deleting the stack, empty mutable resources:

```bash
aws s3 rm "s3://$BASE_NAME" --recursive --region "$AWS_REGION"

aws ecr list-images \
  --region "$AWS_REGION" \
  --repository-name "$BASE_NAME" \
  --query 'imageIds' \
  --output json > /tmp/dstrmaysam-hkm-ecr-images.json

aws ecr batch-delete-image \
  --region "$AWS_REGION" \
  --repository-name "$BASE_NAME" \
  --image-ids file:///tmp/dstrmaysam-hkm-ecr-images.json
```

Delete the stack:

```bash
aws cloudformation delete-stack \
  --stack-name "$STACK_NAME" \
  --region "$AWS_REGION"

aws cloudformation wait stack-delete-complete \
  --stack-name "$STACK_NAME" \
  --region "$AWS_REGION"
```

If deletion fails:

- Ensure the S3 bucket is empty, including versions/delete markers if versioning was used.
- Ensure ECR has no remaining images.
- Check whether RDS produced a final snapshot because of replacement/deletion behavior.

## 10. Compatibility Checklist

After switching from local to AWS mode:

- Backend starts with `APP_ENV=dev`.
- App auth loads from `/dstrmaysam-healthcare-knowledge-multi-agent-dev/app`.
- Chat history writes to RDS Postgres.
- Deterministic lookup uses RDS Postgres tables.
- Documents upload to S3.
- Ingestion writes chunks to OpenSearch Serverless.
- Langfuse tracing loads from the new Langfuse secret.

## 11. Files

| File | Purpose |
|---|---|
| `infra/aws-foundation.yml` | Foundation CloudFormation stack. |
| `infra/aws-foundation-parameters.example.json` | Example stack parameters. |
| `infra/ecs-backend-task-definition.json` | Backend ECS task definition example for future service deployment. |
| `infra/ecs-frontend-task-definition.json` | Frontend ECS task definition example for future service deployment. |
| `infra/iam-backend-task-policy.json` | Standalone backend IAM policy reference. |
| `infra/opensearch-index.json` | OpenSearch index mapping reference. |
| `database/init/01_schema.sql` | RDS schema initialization. |
| `database/init/02_seed.sql` | RDS seed data initialization. |
