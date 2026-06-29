# AWS Foundation Infrastructure

This folder contains AWS foundation infrastructure documents for the dev deployment of:

```text
dstrmaysam-healthcare-knowledge-multi-agent-dev
```

The foundation stack creates shared AWS resources and the isolated private networking required by RDS. It also creates an S3 Gateway Endpoint on the private route table so CloudShell VPC environments can copy SQL files from the project bucket. When `CicdEnabled=true`, it creates dev ALB/Fargate services plus CodePipeline, CodeBuild, and ECS deploy resources so changes can be tested directly on AWS.

## Primary Files

| File | Purpose |
|---|---|
| `aws-foundation.yml` | CloudFormation template for S3, S3 Gateway Endpoint, Secrets Manager, RDS Postgres, OpenSearch Serverless, ECR, ECS/ALB dev services, CodePipeline, CodeBuild, IAM roles, and log groups. |
| `aws-foundation-parameters.example.json` | Example CloudFormation parameter file for the stack-created VPC, private RDS subnets, database, and OpenSearch names. |
| `db-init/Dockerfile` | Pipeline image that runs RDS schema and seed SQL through `psql`. |
| `db-init/run-db-init.sh` | DB initialization entrypoint used by the one-off ECS task. |
| `ecs-backend-task-definition.json` | Backend ECS task definition example that uses RDS/Postgres and the single ECR repo with `backend-latest`. |
| `ecs-frontend-task-definition.json` | Frontend ECS task definition example that uses the single ECR repo with `frontend-latest`. |
| `iam-backend-task-policy.json` | Standalone backend task policy reference; the main CloudFormation template creates equivalent permissions. |
| `opensearch-index.json` | Expected OpenSearch vector index mapping. |

AWS mode uses RDS Postgres for chat history and deterministic lookup tables. DynamoDB is not part of the current AWS foundation path.

## Required Tags

All supported resources are tagged with:

```text
Project=dstrmaysam-healthcare-knowledge-multi-agent
Application=dstrmaysam
Owner=Sabin
```

## Name Constraints

The full base name is used where possible:

```text
dstrmaysam-healthcare-knowledge-multi-agent-dev
```

OpenSearch Serverless and IAM role names have stricter limits, so the template uses the deterministic short name:

```text
dstrmaysam-hkm-dev
```

The full name is preserved through tags and stack outputs.

## Deploy

Use the full runbook in `docs/aws_setup_instructions.md`. Minimal commands:

```powershell
$env:CFN_ARTIFACT_BUCKET = "dstrmaysam-healthcare-knowledge-multi-agent-dev-cfn-artifacts"

aws s3api head-bucket --bucket $env:CFN_ARTIFACT_BUCKET 2>$null

if ($LASTEXITCODE -ne 0) {
  aws s3api create-bucket `
    --bucket $env:CFN_ARTIFACT_BUCKET `
    --region eu-west-2 `
    --create-bucket-configuration LocationConstraint=eu-west-2
}

aws cloudformation deploy `
  --stack-name dstrmaysam-healthcare-knowledge-multi-agent-dev `
  --template-file infra/aws-foundation.yml `
  --s3-bucket $env:CFN_ARTIFACT_BUCKET `
  --s3-prefix cloudformation `
  --region eu-west-2 `
  --capabilities CAPABILITY_NAMED_IAM `
  --parameter-overrides `
    VpcCidr=10.40.0.0/16 `
    PrivateSubnetOneCidr=10.40.1.0/24 `
    PrivateSubnetTwoCidr=10.40.2.0/24 `
    PublicSubnetOneCidr=10.40.10.0/24 `
    PublicSubnetTwoCidr=10.40.11.0/24 `
    DbAdminAccessEnabled=false `
    CicdEnabled=true `
    CodeStarConnectionArn=arn:aws:codeconnections:eu-west-2:666127452756:connection/1cc25a96-45f6-418a-bfd0-e73ca9c818c7 `
    RepositoryId=sabin262/dstrmaysam-heakthcare-knowledge-agent-multi-agent `
    RepositoryBranch=master `
    PublicIngressCidr=0.0.0.0/0 `
    BackendDesiredCount=0 `
    FrontendDesiredCount=0 `
    DatabaseIngressCidr=10.40.0.0/16
```

Delete the stack after emptying the S3 bucket and ECR repository if CloudFormation cannot remove non-empty resources:

```powershell
aws cloudformation delete-stack `
  --stack-name dstrmaysam-healthcare-knowledge-multi-agent-dev
```


