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