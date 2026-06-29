# AWS Foundation Setup: Healthcare Knowledge Multi-Agent

Version: 2.0  
Target stage: `dev`  
Default region: `eu-west-2`  
Base name: `dstrmaysam-healthcare-knowledge-multi-agent-dev`

This runbook creates the AWS foundation resources required by AWS mode. The foundation stack creates a small VPC, private subnets for RDS, optional public ALB/Fargate dev services, and an optional CodePipeline/CodeBuild/CodeDeploy flow so changes can be tested directly on AWS. For local PowerShell administration, it can also create an optional SSM-managed admin instance, but your AWS Organizations SCP may block EC2 instance creation.

## 1. Resources Created

The CloudFormation template `infra/aws-foundation.yml` creates:

- S3 bucket: `dstrmaysam-healthcare-knowledge-multi-agent-dev`
- S3 Gateway VPC endpoint attached to the private route table
- Secrets Manager secrets:
  - `/dstrmaysam-healthcare-knowledge-multi-agent-dev/app`
  - `/dstrmaysam-healthcare-knowledge-multi-agent-dev/azure-openai`
  - `/dstrmaysam-healthcare-knowledge-multi-agent-dev/langfuse`
- Isolated VPC and two private subnets for RDS networking
- Optional SSM-managed admin instance for local `psql` access to private RDS
- RDS Postgres instance with generated master password secret
- OpenSearch Serverless vector collection and access policies
- ECR repository: `dstrmaysam-healthcare-knowledge-multi-agent-dev`
- ECS cluster: `dstrmaysam-healthcare-knowledge-multi-agent-dev`
- ECS execution, backend task, and frontend task IAM roles
- Optional public ALB, backend/frontend ECS Fargate services, and target groups for dev testing
- Optional CodePipeline source/build/deploy pipeline:
  - CodeStar Connections GitHub source
  - CodeBuild Docker image build and ECR push
  - One-off ECS database initialization task for schema and seed SQL
  - ECS backend deploy
  - CodeDeploy blue/green frontend deploy
- CloudWatch log groups for backend/frontend ECS tasks

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
- AWS Session Manager plugin support for `aws ssm start-session`
- Docker
- `psql`
- AWS credentials with permission to create CloudFormation, S3, Secrets Manager, RDS, OpenSearch Serverless, ECR, ECS, ELBv2, IAM, CodePipeline, CodeBuild, CodeDeploy, CodeStar Connections, and CloudWatch Logs resources
- A CodeStar Connections connection to GitHub if `CicdEnabled=true`

Set local shell variables:

```powershell
$env:AWS_REGION = "eu-west-2"
$env:STACK_NAME = "dstrmaysam-healthcare-knowledge-multi-agent-dev"
$env:BASE_NAME = "dstrmaysam-healthcare-knowledge-multi-agent-dev"
$env:CFN_ARTIFACT_BUCKET = "$($env:BASE_NAME)-cfn-artifacts"
$env:VPC_CIDR = "10.40.0.0/16"
$env:PRIVATE_SUBNET_ONE_CIDR = "10.40.1.0/24"
$env:PRIVATE_SUBNET_TWO_CIDR = "10.40.2.0/24"
$env:PUBLIC_SUBNET_ONE_CIDR = "10.40.10.0/24"
$env:PUBLIC_SUBNET_TWO_CIDR = "10.40.11.0/24"
$env:DB_ADMIN_ACCESS_ENABLED = "false"
$env:CICD_ENABLED = "true"
$env:CODESTAR_CONNECTION_ARN = "arn:aws:codestar-connections:eu-west-2:666127452756:connection/replace-me"
$env:REPOSITORY_ID = "github-owner/github-repo"
$env:REPOSITORY_BRANCH = "master"
$env:PUBLIC_INGRESS_CIDR = "0.0.0.0/0"
$env:BACKEND_DESIRED_COUNT = "0"
$env:FRONTEND_DESIRED_COUNT = "0"
$env:DATABASE_INGRESS_CIDR = "10.40.0.0/16"
$env:AWS_ACCOUNT_ID = aws sts get-caller-identity --query Account --output text
```

Use `DB_ADMIN_ACCESS_ENABLED=false` in your current account because an AWS Organizations service control policy denied `ec2:RunInstances`. Use CloudShell VPC for the SQL step instead.

Keep `BACKEND_DESIRED_COUNT` and `FRONTEND_DESIRED_COUNT` at `0` on the first deploy unless you have already pushed `backend-latest` and `frontend-latest` images to ECR. The pipeline publishes immutable commit tags and refreshes the `backend-latest` and `frontend-latest` bootstrap tags on every run. After the first successful pipeline run builds images, update both values to `1`.

## 3. Validate And Deploy Foundation Stack

Create the CloudFormation artifact bucket before the first deploy. The foundation template is larger than the direct CloudFormation body limit, so `aws cloudformation deploy` must upload it to S3.

```powershell
aws s3api head-bucket --bucket $env:CFN_ARTIFACT_BUCKET 2>$null

if ($LASTEXITCODE -ne 0) {
  aws s3api create-bucket `
    --bucket $env:CFN_ARTIFACT_BUCKET `
    --region $env:AWS_REGION `
    --create-bucket-configuration LocationConstraint=$env:AWS_REGION

  aws s3api put-public-access-block `
    --bucket $env:CFN_ARTIFACT_BUCKET `
    --public-access-block-configuration BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true

  aws s3api put-bucket-encryption `
    --bucket $env:CFN_ARTIFACT_BUCKET `
    --server-side-encryption-configuration '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'
}
```

Preview a changeset without executing. This is the practical validation path for this large template:

```powershell
aws cloudformation deploy `
  --stack-name $env:STACK_NAME `
  --template-file infra/aws-foundation.yml `
  --s3-bucket $env:CFN_ARTIFACT_BUCKET `
  --s3-prefix cloudformation `
  --region $env:AWS_REGION `
  --capabilities CAPABILITY_NAMED_IAM `
  --no-execute-changeset `
  --parameter-overrides `
    VpcCidr=$env:VPC_CIDR `
    PrivateSubnetOneCidr=$env:PRIVATE_SUBNET_ONE_CIDR `
    PrivateSubnetTwoCidr=$env:PRIVATE_SUBNET_TWO_CIDR `
    PublicSubnetOneCidr=$env:PUBLIC_SUBNET_ONE_CIDR `
    PublicSubnetTwoCidr=$env:PUBLIC_SUBNET_TWO_CIDR `
    DbAdminAccessEnabled=$env:DB_ADMIN_ACCESS_ENABLED `
    CicdEnabled=$env:CICD_ENABLED `
    CodeStarConnectionArn=$env:CODESTAR_CONNECTION_ARN `
    RepositoryId=$env:REPOSITORY_ID `
    RepositoryBranch=$env:REPOSITORY_BRANCH `
    PublicIngressCidr=$env:PUBLIC_INGRESS_CIDR `
    BackendDesiredCount=$env:BACKEND_DESIRED_COUNT `
    FrontendDesiredCount=$env:FRONTEND_DESIRED_COUNT `
    DatabaseIngressCidr=$env:DATABASE_INGRESS_CIDR
```

Create/update:

```powershell
aws cloudformation deploy `
  --stack-name $env:STACK_NAME `
  --template-file infra/aws-foundation.yml `
  --s3-bucket $env:CFN_ARTIFACT_BUCKET `
  --s3-prefix cloudformation `
  --region $env:AWS_REGION `
  --capabilities CAPABILITY_NAMED_IAM `
  --parameter-overrides `
    VpcCidr=$env:VPC_CIDR `
    PrivateSubnetOneCidr=$env:PRIVATE_SUBNET_ONE_CIDR `
    PrivateSubnetTwoCidr=$env:PRIVATE_SUBNET_TWO_CIDR `
    PublicSubnetOneCidr=$env:PUBLIC_SUBNET_ONE_CIDR `
    PublicSubnetTwoCidr=$env:PUBLIC_SUBNET_TWO_CIDR `
    DbAdminAccessEnabled=$env:DB_ADMIN_ACCESS_ENABLED `
    CicdEnabled=$env:CICD_ENABLED `
    CodeStarConnectionArn=$env:CODESTAR_CONNECTION_ARN `
    RepositoryId=$env:REPOSITORY_ID `
    RepositoryBranch=$env:REPOSITORY_BRANCH `
    PublicIngressCidr=$env:PUBLIC_INGRESS_CIDR `
    BackendDesiredCount=$env:BACKEND_DESIRED_COUNT `
    FrontendDesiredCount=$env:FRONTEND_DESIRED_COUNT `
    DatabaseIngressCidr=$env:DATABASE_INGRESS_CIDR
```

Capture outputs:

```powershell
aws cloudformation describe-stacks `
  --stack-name $env:STACK_NAME `
  --region $env:AWS_REGION `
  --query "Stacks[0].Outputs" `
  --output table
```

Important outputs:

- `VpcId`
- `PrivateSubnetOneId`
- `PrivateSubnetTwoId`
- `DatabaseSecurityGroupId`
- `S3GatewayEndpointId`
- `DbAdminInstanceId`, when `DbAdminAccessEnabled=true`
- `DatabaseEndpoint`
- `DatabaseMasterSecretArn`
- `OpenSearchCollectionEndpoint`
- `EcrRepositoryUri`
- `EcsClusterName`
- `BackendTaskRoleArn`
- `FrontendTaskRoleArn`
- `EcsExecutionRoleArn`
- `DevApplicationUrl`, when `CicdEnabled=true`
- `BackendApiUrl`, when `CicdEnabled=true`
- `DevCodePipelineName`, when `CicdEnabled=true` and CodeStar parameters are provided

## 4. Populate Secrets Manager Values

The template creates the Secrets Manager secret resources but does not manage their secret values. This prevents stack updates from replacing real credentials with placeholders. Populate or update the values with `aws secretsmanager put-secret-value` before starting the backend.

The app, Azure OpenAI, and Langfuse secrets use `DeletionPolicy: Retain` and `UpdateReplacePolicy: Retain`, so deleting or replacing the stack will not intentionally delete the stored secret resources. If you need to remove them, delete them manually after confirming you no longer need the values.

Generate an app password hash:

```powershell
python -m backend.app.auth hash-password
```

Update the app secret:

```powershell
$appSecret = @'
{
  "session_secret": "replace-with-long-random-value",
  "guardian_api_key": "replace-with-guardian-content-api-key",
  "auth_users": {
    "admin": "pbkdf2_sha256$1000$436e10a3455a383cd122f9fee62bb2d9$55a52972c1069e44b24076f738daa09c01dbfd9a44a6356c50809d3008a1eae3"
  },
  "user_profiles": {
    "admin": {
      "roles": ["admin", "doctor"],
      "departments": ["clinical_governance"]
    }
  }
}
'@

aws secretsmanager put-secret-value `
  --region $env:AWS_REGION `
  --secret-id "/$($env:BASE_NAME)/app" `
  --secret-string $appSecret
```

The `guardian_api_key` value is optional for login, but required for the NHS news carousel/page in AWS mode. The backend reads it from the app secret when `GUARDIAN_API_KEY` is not set as an environment variable.

Update Azure OpenAI:

```powershell
$azureOpenAISecret = @'
{
  "endpoint": "https://YOUR-RESOURCE.openai.azure.com/",
  "api_key": "replace-with-azure-openai-key",
  "api_version": "2025-04-01-preview",
  "chat_deployment": "gpt-4.1-mini",
  "fast_chat_deployment": "gpt-4.1-mini",
  "embedding_deployment": "text-embedding-3-small"
}
'@

aws secretsmanager put-secret-value `
  --region $env:AWS_REGION `
  --secret-id "/$($env:BASE_NAME)/azure-openai" `
  --secret-string $azureOpenAISecret
```

Update Langfuse:

```powershell
$langfuseSecret = @'
{
  "public_key": "pk-lf-replace",
  "secret_key": "sk-lf-replace",
  "base_url": "https://cloud.langfuse.com"
}
'@

aws secretsmanager put-secret-value `
  --region $env:AWS_REGION `
  --secret-id "/$($env:BASE_NAME)/langfuse" `
  --secret-string $langfuseSecret
```

## 5. RDS Postgres Schema And Seed Data

When `CicdEnabled=true`, the pipeline handles schema and seed data automatically:

1. CodeBuild builds a small `db-init` image from `infra/db-init/Dockerfile`.
2. The image contains `database/init/01_schema.sql` and `database/init/02_seed.sql`.
3. CodeBuild starts a one-off ECS Fargate task inside the VPC.
4. The task connects to private RDS and runs the SQL files.
5. If the SQL task exits non-zero, the build fails and backend/frontend deployment does not continue.

The SQL files are idempotent: tables use `CREATE TABLE IF NOT EXISTS`, and seed inserts use `ON CONFLICT DO NOTHING`. That makes repeated pipeline runs safe for the seeded records.

The manual steps below are only needed when you want to diagnose RDS connectivity or run SQL outside the pipeline.

Get RDS outputs:

```powershell
$env:POSTGRES_HOST = aws cloudformation describe-stacks `
  --stack-name $env:STACK_NAME `
  --region $env:AWS_REGION `
  --query "Stacks[0].Outputs[?OutputKey=='DatabaseEndpoint'].OutputValue" `
  --output text

$env:DB_SECRET_ARN = aws cloudformation describe-stacks `
  --stack-name $env:STACK_NAME `
  --region $env:AWS_REGION `
  --query "Stacks[0].Outputs[?OutputKey=='DatabaseMasterSecretArn'].OutputValue" `
  --output text

$dbSecretJson = aws secretsmanager get-secret-value `
  --region $env:AWS_REGION `
  --secret-id $env:DB_SECRET_ARN `
  --query SecretString `
  --output text

$env:POSTGRES_PASSWORD = ($dbSecretJson | ConvertFrom-Json).password
```

The RDS instance is private inside the stack-created VPC. If you try to connect directly to the RDS endpoint from your laptop, you will see a timeout similar to:

```text
connection to server at "...rds.amazonaws.com" (10.40.x.x), port 5432 failed: Connection timed out
```

That means your laptop has no route to the private VPC address. Use the SSM port-forward path below when `DbAdminAccessEnabled=true`.

If EC2 instance creation is blocked by an AWS Organizations service control policy, set `DbAdminAccessEnabled=false` and use a CloudShell VPC environment instead. The stack creates an S3 Gateway Endpoint on the private route table, so CloudShell can copy SQL files from the project S3 bucket while running inside the private subnet.

Upload the SQL files to S3 from your local PowerShell session:

```powershell
aws s3 cp database/init/01_schema.sql "s3://$($env:BASE_NAME)/sql/01_schema.sql" --region $env:AWS_REGION
aws s3 cp database/init/02_seed.sql "s3://$($env:BASE_NAME)/sql/02_seed.sql" --region $env:AWS_REGION
```

Create a CloudShell VPC environment in the AWS console:

- Region: `eu-west-2`
- VPC: stack output `VpcId`
- Subnet: stack output `PrivateSubnetOneId` or `PrivateSubnetTwoId`
- Security group: one that allows egress to RDS on `5432`; the RDS security group already allows `10.40.0.0/16`

Inside the CloudShell VPC environment, copy the SQL files down from S3:

```bash
export AWS_REGION=eu-west-2
export BASE_NAME=dstrmaysam-healthcare-knowledge-multi-agent-dev
export POSTGRES_HOST='<DatabaseEndpoint stack output>'

aws s3 cp "s3://$BASE_NAME/sql/01_schema.sql" ./01_schema.sql --region "$AWS_REGION"
aws s3 cp "s3://$BASE_NAME/sql/02_seed.sql" ./02_seed.sql --region "$AWS_REGION"
```

Use the AWS console, your local PowerShell session, or normal non-VPC CloudShell to read `DatabaseEndpoint` and `DatabaseMasterSecretArn`. Only S3 has a VPC endpoint in this stack, so do not rely on CloudFormation or Secrets Manager CLI calls from the VPC CloudShell session unless you add interface endpoints for those services too.

Then run `psql` from CloudShell against the private RDS endpoint:

```bash
export PGSSLMODE=require
export PGPASSWORD='<database-password-from-DatabaseMasterSecretArn>'

psql \
  --host "$POSTGRES_HOST" \
  --port 5432 \
  --username healthcare_agent \
  --dbname healthcare_agent \
  --file ./01_schema.sql

psql \
  --host "$POSTGRES_HOST" \
  --port 5432 \
  --username healthcare_agent \
  --dbname healthcare_agent \
  --file ./02_seed.sql
```

CloudShell VPC environments are temporary. Keep the canonical SQL files in this repository and S3; treat the CloudShell copies as disposable.

Get the admin instance ID:

```powershell
$env:DB_ADMIN_INSTANCE_ID = aws cloudformation describe-stacks `
  --stack-name $env:STACK_NAME `
  --region $env:AWS_REGION `
  --query "Stacks[0].Outputs[?OutputKey=='DbAdminInstanceId'].OutputValue" `
  --output text
```

Start the port-forward in a dedicated PowerShell window and leave it open:

```powershell
$portForwardParameters = @{
  host = @($env:POSTGRES_HOST)
  portNumber = @("5432")
  localPortNumber = @("15432")
} | ConvertTo-Json -Compress

aws ssm start-session `
  --target $env:DB_ADMIN_INSTANCE_ID `
  --document-name AWS-StartPortForwardingSessionToRemoteHost `
  --parameters $portForwardParameters `
  --region $env:AWS_REGION
```

In a second PowerShell window, run schema and seed SQL through the local tunnel:

```powershell
$env:PGSSLMODE = "require"
$env:PGPASSWORD = $env:POSTGRES_PASSWORD

psql `
  --host localhost `
  --port 15432 `
  --username healthcare_agent `
  --dbname healthcare_agent `
  --file database/init/01_schema.sql

psql `
  --host localhost `
  --port 15432 `
  --username healthcare_agent `
  --dbname healthcare_agent `
  --file database/init/02_seed.sql
```

To remove the admin instance after setup:

```powershell
$env:DB_ADMIN_ACCESS_ENABLED = "false"

aws cloudformation deploy `
  --stack-name $env:STACK_NAME `
  --template-file infra/aws-foundation.yml `
  --s3-bucket $env:CFN_ARTIFACT_BUCKET `
  --s3-prefix cloudformation `
  --region $env:AWS_REGION `
  --capabilities CAPABILITY_NAMED_IAM `
  --parameter-overrides `
    VpcCidr=$env:VPC_CIDR `
    PrivateSubnetOneCidr=$env:PRIVATE_SUBNET_ONE_CIDR `
    PrivateSubnetTwoCidr=$env:PRIVATE_SUBNET_TWO_CIDR `
    PublicSubnetOneCidr=$env:PUBLIC_SUBNET_ONE_CIDR `
    PublicSubnetTwoCidr=$env:PUBLIC_SUBNET_TWO_CIDR `
    DbAdminAccessEnabled=$env:DB_ADMIN_ACCESS_ENABLED `
    CicdEnabled=$env:CICD_ENABLED `
    CodeStarConnectionArn=$env:CODESTAR_CONNECTION_ARN `
    RepositoryId=$env:REPOSITORY_ID `
    RepositoryBranch=$env:REPOSITORY_BRANCH `
    PublicIngressCidr=$env:PUBLIC_INGRESS_CIDR `
    BackendDesiredCount=$env:BACKEND_DESIRED_COUNT `
    FrontendDesiredCount=$env:FRONTEND_DESIRED_COUNT `
    DatabaseIngressCidr=$env:DATABASE_INGRESS_CIDR
```

## 6. Build And Push Images To One ECR Repository

The foundation stack creates one ECR repository. Use different image tags for backend and frontend.

```powershell
$env:ECR_REPOSITORY_URI = aws cloudformation describe-stacks `
  --stack-name $env:STACK_NAME `
  --region $env:AWS_REGION `
  --query "Stacks[0].Outputs[?OutputKey=='EcrRepositoryUri'].OutputValue" `
  --output text

aws ecr get-login-password --region $env:AWS_REGION `
  | docker login --username AWS --password-stdin "$($env:AWS_ACCOUNT_ID).dkr.ecr.$($env:AWS_REGION).amazonaws.com"

docker build -t "$($env:BASE_NAME):backend-latest" backend
docker tag "$($env:BASE_NAME):backend-latest" "$($env:ECR_REPOSITORY_URI):backend-latest"
docker push "$($env:ECR_REPOSITORY_URI):backend-latest"

docker build -t "$($env:BASE_NAME):frontend-latest" frontend
docker tag "$($env:BASE_NAME):frontend-latest" "$($env:ECR_REPOSITORY_URI):frontend-latest"
docker push "$($env:ECR_REPOSITORY_URI):frontend-latest"
```

The database image is for local Docker Compose only and is not required for RDS.

## 7. CI/CD Pipeline Use

When `CicdEnabled=true`, the stack creates:

- CodePipeline source stage from GitHub through CodeStar Connections.
- CodeBuild project that builds `backend`, `frontend`, and `db-init` Docker images and pushes them to the single ECR repository.
- One-off ECS `db-init` Fargate task that applies schema and seed SQL to RDS before app deployment.
- ECS deploy action for the backend service.
- CodeDeploy blue/green deployment for the frontend service.

First deploy should normally use:

```powershell
$env:BACKEND_DESIRED_COUNT = "0"
$env:FRONTEND_DESIRED_COUNT = "0"
```

This avoids ECS trying to start from `backend-latest` and `frontend-latest` before those images exist. The first pipeline execution builds images, pushes the `backend-latest` and `frontend-latest` tags, and runs database initialization. If the first deployment stage fails during bootstrap, rerun after images exist in ECR and redeploy the stack with:

```powershell
$env:BACKEND_DESIRED_COUNT = "1"
$env:FRONTEND_DESIRED_COUNT = "1"
```

Then run the same CloudFormation deploy command from section 3 and rerun the pipeline. The frontend should become available at `DevApplicationUrl`, and the backend API is exposed at `BackendApiUrl` for dev testing.

To start the pipeline manually:

```powershell
aws codepipeline start-pipeline-execution `
  --name "$($env:BASE_NAME)-pipeline" `
  --region $env:AWS_REGION
```

Keep `PublicIngressCidr` restricted to your IP or VPN CIDR where possible. The default `0.0.0.0/0` is convenient for quick dev testing but not appropriate for a real environment.

## 8. AWS Mode Runtime Environment

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

Frontend ECS task/service environment uses the dev ALB backend listener:

```env
BACKEND_URL=http://<DevApplicationLoadBalancer DNS>:8000
```

When `CicdEnabled=true`, the CloudFormation task definitions and services are created directly. The JSON task definition files in `infra/` remain standalone references.

## 9. OpenSearch Index Creation And Verification

The backend ingestion path calls the application index bootstrap logic and uses `infra/opensearch-index.json` shape internally. After the backend is running with AWS mode values:

1. Upload source documents to:

```text
s3://dstrmaysam-healthcare-knowledge-multi-agent-dev/raw/
```

2. Run ingestion from the admin UI or as a one-off backend task.

3. Verify documents and the manifest:

```powershell
aws s3 ls "s3://$($env:BASE_NAME)/raw/" --region $env:AWS_REGION
aws s3 cp "s3://$($env:BASE_NAME)/manifests/documents.json" - --region $env:AWS_REGION
```

If OpenSearch permissions fail, confirm:

- Backend task role has `aoss:APIAccessAll`.
- OpenSearch data access policy includes the backend task role ARN.
- Network policy allows the backend networking path.

## 10. Delete Resources

Before deleting the stack, empty mutable resources:

```powershell
aws s3 rm "s3://$($env:BASE_NAME)" --recursive --region $env:AWS_REGION

$imageIdsPath = Join-Path $env:TEMP "dstrmaysam-hkm-ecr-images.json"
$imageIdsUri = "file:///" + ($imageIdsPath -replace "\\", "/")

aws ecr list-images `
  --region $env:AWS_REGION `
  --repository-name $env:BASE_NAME `
  --query "imageIds" `
  --output json | Out-File -Encoding ascii $imageIdsPath

aws ecr batch-delete-image `
  --region $env:AWS_REGION `
  --repository-name $env:BASE_NAME `
  --image-ids $imageIdsUri
```

Delete the stack:

```powershell
aws cloudformation delete-stack `
  --stack-name $env:STACK_NAME `
  --region $env:AWS_REGION

aws cloudformation wait stack-delete-complete `
  --stack-name $env:STACK_NAME `
  --region $env:AWS_REGION
```

If deletion fails:

- Ensure the S3 bucket is empty, including versions/delete markers if versioning was used.
- Ensure ECR has no remaining images.
- Check whether RDS produced a final snapshot because of replacement/deletion behavior.

## 11. Compatibility Checklist

After switching from local to AWS mode:

- Backend starts with `APP_ENV=dev`.
- App auth loads from `/dstrmaysam-healthcare-knowledge-multi-agent-dev/app`.
- Chat history writes to RDS Postgres.
- Deterministic lookup uses RDS Postgres tables.
- Documents upload to S3.
- Ingestion writes chunks to OpenSearch Serverless.
- Langfuse tracing loads from the new Langfuse secret.

## 12. Files

| File | Purpose |
|---|---|
| `infra/aws-foundation.yml` | Foundation CloudFormation stack. |
| `infra/aws-foundation-parameters.example.json` | Example stack parameters. |
| `infra/ecs-backend-task-definition.json` | Backend ECS task definition example for future service deployment. |
| `infra/ecs-frontend-task-definition.json` | Frontend ECS task definition example for future service deployment. |
| `infra/db-init/Dockerfile` | Pipeline database initialization image with `psql`. |
| `infra/db-init/run-db-init.sh` | Entrypoint that runs schema and seed SQL with `ON_ERROR_STOP`. |
| `infra/iam-backend-task-policy.json` | Standalone backend IAM policy reference. |
| `infra/opensearch-index.json` | OpenSearch index mapping reference. |
| `database/init/01_schema.sql` | RDS schema initialization. |
| `database/init/02_seed.sql` | RDS seed data initialization. |
