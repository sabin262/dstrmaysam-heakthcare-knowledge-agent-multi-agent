# AWS Foundation Infrastructure

This folder contains AWS foundation infrastructure documents for the dev deployment of:

```text
dstrmaysam-healthcare-knowledge-multi-agent-dev
```

The foundation stack creates shared AWS resources and the isolated private networking required by RDS. The later CICD/networking phase can reuse these VPC/subnet outputs or add separate ECS service networking. It does not create ALBs, listeners, or ECS services.

## Primary Files

| File | Purpose |
|---|---|
| `aws-foundation.yml` | CloudFormation template for S3, Secrets Manager, RDS Postgres, OpenSearch Serverless, ECR, ECS cluster, IAM roles, and log groups. |
| `aws-foundation-parameters.example.json` | Example CloudFormation parameter file for the stack-created VPC, private RDS subnets, database, and OpenSearch names. |
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

```bash
aws cloudformation validate-template \
  --template-body file://infra/aws-foundation.yml

aws cloudformation deploy \
  --stack-name dstrmaysam-healthcare-knowledge-multi-agent-dev \
  --template-file infra/aws-foundation.yml \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides \
    VpcCidr=10.40.0.0/16 \
    PrivateSubnetOneCidr=10.40.1.0/24 \
    PrivateSubnetTwoCidr=10.40.2.0/24 \
    DatabaseIngressCidr=10.40.0.0/16
```

Delete the stack after emptying the S3 bucket and ECR repository if CloudFormation cannot remove non-empty resources:

```bash
aws cloudformation delete-stack \
  --stack-name dstrmaysam-healthcare-knowledge-multi-agent-dev
```
