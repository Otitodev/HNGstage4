# AWS ECS Fargate Deployment Script (PowerShell)
# Deploys Email Service and Notification Router to AWS

# Configuration - UPDATE THESE
$AWS_REGION = "eu-north-1"
$AWS_PROFILE = "otito2"
$CLUSTER_NAME = "notification-services"
$ECR_REPO_EMAIL = "email-service"
$ECR_REPO_ROUTER = "notification-router"

Write-Host "=== AWS ECS Fargate Deployment ===" -ForegroundColor Blue
Write-Host "Region: $AWS_REGION"
Write-Host "Profile: $AWS_PROFILE"
Write-Host "Cluster: $CLUSTER_NAME"
Write-Host ""

# Get AWS Account ID
Write-Host "Getting AWS Account ID..." -ForegroundColor Green
$AWS_ACCOUNT_ID = aws sts get-caller-identity --profile $AWS_PROFILE --query Account --output text
Write-Host "Account ID: $AWS_ACCOUNT_ID"
Write-Host ""

# Step 1: Create ECR Repositories
Write-Host "Step 1: Creating ECR repositories..." -ForegroundColor Green
aws ecr create-repository `
    --repository-name $ECR_REPO_EMAIL `
    --region $AWS_REGION `
    --profile $AWS_PROFILE 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Repository $ECR_REPO_EMAIL already exists or error occurred"
}

aws ecr create-repository `
    --repository-name $ECR_REPO_ROUTER `
    --region $AWS_REGION `
    --profile $AWS_PROFILE 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Repository $ECR_REPO_ROUTER already exists or error occurred"
}

Write-Host ""

# Step 2: Login to ECR
Write-Host "Step 2: Logging in to ECR..." -ForegroundColor Green
$ECR_PASSWORD = aws ecr get-login-password --region $AWS_REGION --profile $AWS_PROFILE
$ECR_PASSWORD | docker login --username AWS --password-stdin "$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com"

Write-Host ""

# Step 3: Build and Push Email Service
Write-Host "Step 3: Building Email Service Docker image..." -ForegroundColor Green
docker build -t ${ECR_REPO_EMAIL}:latest -f Dockerfile.email .

Write-Host "Tagging and pushing Email Service..." -ForegroundColor Green
docker tag ${ECR_REPO_EMAIL}:latest "$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/${ECR_REPO_EMAIL}:latest"
docker push "$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/${ECR_REPO_EMAIL}:latest"

Write-Host ""

# Step 4: Build and Push Notification Router
Write-Host "Step 4: Building Notification Router Docker image..." -ForegroundColor Green
docker build -t ${ECR_REPO_ROUTER}:latest -f Dockerfile.router .

Write-Host "Tagging and pushing Notification Router..." -ForegroundColor Green
docker tag ${ECR_REPO_ROUTER}:latest "$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/${ECR_REPO_ROUTER}:latest"
docker push "$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/${ECR_REPO_ROUTER}:latest"

Write-Host ""

# Step 5: Create ECS Cluster
Write-Host "Step 5: Creating ECS Cluster..." -ForegroundColor Green
aws ecs create-cluster `
    --cluster-name $CLUSTER_NAME `
    --region $AWS_REGION `
    --profile $AWS_PROFILE 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Cluster already exists or error occurred"
}

Write-Host ""

# Step 6: Create CloudWatch Log Groups
Write-Host "Step 6: Creating CloudWatch Log Groups..." -ForegroundColor Green
aws logs create-log-group `
    --log-group-name /ecs/email-service `
    --region $AWS_REGION `
    --profile $AWS_PROFILE 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Log group /ecs/email-service already exists"
}

aws logs create-log-group `
    --log-group-name /ecs/notification-router `
    --region $AWS_REGION `
    --profile $AWS_PROFILE 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Log group /ecs/notification-router already exists"
}

Write-Host ""
Write-Host "=== Images Built and Pushed Successfully! ===" -ForegroundColor Blue
Write-Host ""
Write-Host "Next Steps:" -ForegroundColor Green
Write-Host "1. Store secrets in AWS Secrets Manager (see below)"
Write-Host "2. Update task definition files with your Account ID"
Write-Host "3. Register task definitions"
Write-Host "4. Create ECS services"
Write-Host ""
Write-Host "=== Store Secrets ===" -ForegroundColor Blue
Write-Host "Run these commands to store your secrets:"
Write-Host ""
Write-Host "aws secretsmanager create-secret --name RABBITMQ_URL --secret-string `"YOUR_RABBITMQ_URL`" --region $AWS_REGION --profile $AWS_PROFILE"
Write-Host "aws secretsmanager create-secret --name SENDGRID_API_KEY --secret-string `"YOUR_SENDGRID_KEY`" --region $AWS_REGION --profile $AWS_PROFILE"
Write-Host "aws secretsmanager create-secret --name NEON_DATABASE_URL --secret-string `"YOUR_DB_URL`" --region $AWS_REGION --profile $AWS_PROFILE"
Write-Host "aws secretsmanager create-secret --name FROM_EMAIL --secret-string `"mail@otito.site`" --region $AWS_REGION --profile $AWS_PROFILE"
