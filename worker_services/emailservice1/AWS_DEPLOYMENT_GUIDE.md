# AWS ECS Deployment Guide for Email & Push Services

## Overview

This guide walks you through deploying your email and push notification services to AWS ECS (Elastic Container Service) with Fargate. These services will run as always-on containers that consume messages from RabbitMQ.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Leapcell.io                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │ API Gateway  │  │  Template    │  │    User      │ │
│  │              │  │   Service    │  │   Service    │ │
│  └──────┬───────┘  └──────────────┘  └──────────────┘ │
└─────────┼───────────────────────────────────────────────┘
          │ Publishes to RabbitMQ
          ↓
┌─────────────────────────────────────────────────────────┐
│              CloudAMQP / RabbitMQ                       │
└─────────┬───────────────────────────────┬───────────────┘
          │                               │
          ↓                               ↓
┌─────────────────────┐         ┌─────────────────────┐
│   AWS ECS Fargate   │         │   AWS ECS Fargate   │
│  ┌───────────────┐  │         │  ┌───────────────┐  │
│  │ Email Service │  │         │  │ Push Service  │  │
│  │  (Container)  │  │         │  │  (Container)  │  │
│  └───────────────┘  │         │  └───────────────┘  │
└─────────────────────┘         └─────────────────────┘
```

## Prerequisites

### 1. AWS Account Setup

- Active AWS account
- AWS CLI installed and configured
- Docker installed locally

### 2. Install AWS CLI

**Windows:**
```powershell
# Download and run the MSI installer from:
# https://awscli.amazonaws.com/AWSCLIV2.msi
```

**Verify installation:**
```bash
aws --version
```

### 3. Configure AWS CLI

```bash
aws configure
```

Enter:
- AWS Access Key ID
- AWS Secret Access Key
- Default region (e.g., `us-east-1`)
- Default output format: `json`

### 4. Install Docker Desktop

Download from: https://www.docker.com/products/docker-desktop

## Step-by-Step Deployment

### Step 1: Set Up RabbitMQ (CloudAMQP)

1. Go to [CloudAMQP](https://www.cloudamqp.com/)
2. Sign up and create a free instance
3. Copy your AMQP URL (format: `amqp://user:pass@host/vhost`)

### Step 2: Store Secrets in AWS Secrets Manager

```bash
# Store RabbitMQ URL
aws secretsmanager create-secret \
    --name RABBITMQ_URL \
    --secret-string "amqp://user:pass@your-cloudamqp-host/vhost" \
    --region us-east-1

# Store SendGrid API Key
aws secretsmanager create-secret \
    --name SENDGRID_API_KEY \
    --secret-string "SG.your_sendgrid_api_key" \
    --region us-east-1
```

**Note the ARNs returned** - you'll need them for task definitions.

### Step 3: Create IAM Role for ECS Tasks

```bash
# Create trust policy file
cat > trust-policy.json << EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "ecs-tasks.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
EOF

# Create the role
aws iam create-role \
    --role-name ecsTaskExecutionRole \
    --assume-role-policy-document file://trust-policy.json

# Attach AWS managed policy
aws iam attach-role-policy \
    --role-name ecsTaskExecutionRole \
    --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy

# Add Secrets Manager access
cat > secrets-policy.json << EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "secretsmanager:GetSecretValue"
      ],
      "Resource": [
        "arn:aws:secretsmanager:us-east-1:YOUR_ACCOUNT_ID:secret:*"
      ]
    }
  ]
}
EOF

aws iam put-role-policy \
    --role-name ecsTaskExecutionRole \
    --policy-name SecretsManagerAccess \
    --policy-document file://secrets-policy.json
```

### Step 4: Update Configuration Files

**Get your AWS Account ID:**
```bash
aws sts get-caller-identity --query Account --output text
```

**Update these files with your values:**

1. `task-definition-email.json` - Replace:
   - `YOUR_ACCOUNT_ID`
   - `YOUR_REGION`
   - Secret ARNs

2. `task-definition-push.json` - Replace:
   - `YOUR_ACCOUNT_ID`
   - `YOUR_REGION`
   - Secret ARNs

3. `deploy.sh` - Replace:
   - `AWS_REGION`
   - `AWS_ACCOUNT_ID`

### Step 5: Run Deployment Script

```bash
cd services

# Make script executable
chmod +x deploy.sh

# Run deployment
./deploy.sh
```

This script will:
- Create ECR repositories
- Build Docker images
- Push images to ECR
- Create ECS cluster
- Create CloudWatch log groups

### Step 6: Register Task Definitions

```bash
# Register email service task
aws ecs register-task-definition \
    --cli-input-json file://task-definition-email.json \
    --region us-east-1

# Register push service task
aws ecs register-task-definition \
    --cli-input-json file://task-definition-push.json \
    --region us-east-1
```

### Step 7: Create VPC and Security Group (if needed)

**Get default VPC:**
```bash
aws ec2 describe-vpcs --filters "Name=isDefault,Values=true" --query "Vpcs[0].VpcId" --output text
```

**Get subnets:**
```bash
aws ec2 describe-subnets --filters "Name=vpc-id,Values=YOUR_VPC_ID" --query "Subnets[*].SubnetId" --output text
```

**Create security group:**
```bash
aws ec2 create-security-group \
    --group-name ecs-services-sg \
    --description "Security group for ECS services" \
    --vpc-id YOUR_VPC_ID

# Allow outbound traffic (for RabbitMQ, SendGrid, Firebase)
aws ec2 authorize-security-group-egress \
    --group-id YOUR_SG_ID \
    --protocol all \
    --cidr 0.0.0.0/0
```

### Step 8: Create ECS Services

**Email Service:**
```bash
aws ecs create-service \
    --cluster notification-services-cluster \
    --service-name email-service \
    --task-definition email-service \
    --desired-count 1 \
    --launch-type FARGATE \
    --network-configuration "awsvpcConfiguration={subnets=[subnet-xxx,subnet-yyy],securityGroups=[sg-xxx],assignPublicIp=ENABLED}" \
    --region us-east-1
```

**Push Service:**
```bash
aws ecs create-service \
    --cluster notification-services-cluster \
    --service-name push-service \
    --task-definition push-service \
    --desired-count 1 \
    --launch-type FARGATE \
    --network-configuration "awsvpcConfiguration={subnets=[subnet-xxx,subnet-yyy],securityGroups=[sg-xxx],assignPublicIp=ENABLED}" \
    --region us-east-1
```

## Verification

### Check Service Status

```bash
# List services
aws ecs list-services --cluster notification-services-cluster --region us-east-1

# Describe email service
aws ecs describe-services \
    --cluster notification-services-cluster \
    --services email-service \
    --region us-east-1

# Describe push service
aws ecs describe-services \
    --cluster notification-services-cluster \
    --services push-service \
    --region us-east-1
```

### View Logs

**Via AWS CLI:**
```bash
# Email service logs
aws logs tail /ecs/email-service --follow --region us-east-1

# Push service logs
aws logs tail /ecs/push-service --follow --region us-east-1
```

**Via AWS Console:**
1. Go to CloudWatch → Log groups
2. Select `/ecs/email-service` or `/ecs/push-service`
3. View log streams

### Test the Services

**Publish a test message to RabbitMQ:**
```python
import pika
import json

connection = pika.BlockingConnection(
    pika.URLParameters('your-cloudamqp-url')
)
channel = connection.channel()

# Test email
email_message = {
    "to": "test@example.com",
    "subject": "Test from AWS ECS",
    "content": "<h1>Success!</h1><p>Email service is running on AWS.</p>"
}

channel.basic_publish(
    exchange='notifications.direct',
    routing_key='notify.email',
    body=json.dumps(email_message)
)

print("Test message sent!")
connection.close()
```

## Cost Estimation

### AWS ECS Fargate Pricing (us-east-1)

**Per task (0.25 vCPU, 0.5 GB memory):**
- vCPU: $0.04048 per hour
- Memory: $0.004445 per GB per hour
- **Total per task: ~$0.043/hour or ~$31/month**

**For 2 services (email + push):**
- **~$62/month** for always-on services

**Additional costs:**
- CloudWatch Logs: ~$0.50/GB ingested
- Data transfer: First 100 GB/month free
- ECR storage: $0.10/GB per month

**Total estimated cost: ~$65-70/month**

### Free Tier Benefits

- CloudWatch Logs: 5 GB ingestion free
- ECR: 500 MB storage free for 12 months
- Data transfer: 100 GB/month free

## Scaling

### Manual Scaling

```bash
# Scale email service to 2 tasks
aws ecs update-service \
    --cluster notification-services-cluster \
    --service email-service \
    --desired-count 2 \
    --region us-east-1
```

### Auto Scaling (Optional)

```bash
# Register scalable target
aws application-autoscaling register-scalable-target \
    --service-namespace ecs \
    --scalable-dimension ecs:service:DesiredCount \
    --resource-id service/notification-services-cluster/email-service \
    --min-capacity 1 \
    --max-capacity 5

# Create scaling policy based on CPU
aws application-autoscaling put-scaling-policy \
    --service-namespace ecs \
    --scalable-dimension ecs:service:DesiredCount \
    --resource-id service/notification-services-cluster/email-service \
    --policy-name cpu-scaling-policy \
    --policy-type TargetTrackingScaling \
    --target-tracking-scaling-policy-configuration file://scaling-policy.json
```

## Updating Services

### Update Docker Image

```bash
# Rebuild and push new image
cd services
docker build -t email-service:latest -f Dockerfile.email .
docker tag email-service:latest $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/email-service:latest
docker push $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/email-service:latest

# Force new deployment
aws ecs update-service \
    --cluster notification-services-cluster \
    --service email-service \
    --force-new-deployment \
    --region us-east-1
```

## Monitoring

### CloudWatch Metrics

Key metrics to monitor:
- CPUUtilization
- MemoryUtilization
- RunningTaskCount

### Set Up Alarms

```bash
# CPU alarm
aws cloudwatch put-metric-alarm \
    --alarm-name email-service-high-cpu \
    --alarm-description "Alert when CPU exceeds 80%" \
    --metric-name CPUUtilization \
    --namespace AWS/ECS \
    --statistic Average \
    --period 300 \
    --threshold 80 \
    --comparison-operator GreaterThanThreshold \
    --evaluation-periods 2
```

## Troubleshooting

### Service Won't Start

**Check task status:**
```bash
aws ecs describe-tasks \
    --cluster notification-services-cluster \
    --tasks TASK_ARN \
    --region us-east-1
```

**Common issues:**
- Incorrect secret ARNs in task definition
- IAM role missing permissions
- Network configuration issues (subnets, security groups)
- Image pull errors (check ECR permissions)

### Can't Connect to RabbitMQ

- Verify security group allows outbound traffic
- Check RabbitMQ URL in Secrets Manager
- Ensure tasks have public IP or NAT gateway for internet access

### High Costs

- Reduce task size (0.25 vCPU, 0.5 GB is minimum)
- Use Spot instances (up to 70% savings)
- Stop services when not needed (dev/test environments)

## Cleanup

### Delete Services

```bash
# Delete email service
aws ecs update-service \
    --cluster notification-services-cluster \
    --service email-service \
    --desired-count 0 \
    --region us-east-1

aws ecs delete-service \
    --cluster notification-services-cluster \
    --service email-service \
    --region us-east-1

# Delete push service
aws ecs update-service \
    --cluster notification-services-cluster \
    --service push-service \
    --desired-count 0 \
    --region us-east-1

aws ecs delete-service \
    --cluster notification-services-cluster \
    --service push-service \
    --region us-east-1
```

### Delete Cluster

```bash
aws ecs delete-cluster \
    --cluster notification-services-cluster \
    --region us-east-1
```

### Delete ECR Repositories

```bash
aws ecr delete-repository \
    --repository-name email-service \
    --force \
    --region us-east-1

aws ecr delete-repository \
    --repository-name push-service \
    --force \
    --region us-east-1
```

## Alternative: AWS Lambda (Serverless Option)

If you want to avoid always-on costs, you can modify services to use Lambda with EventBridge scheduled rules to poll RabbitMQ every minute. This would cost ~$0.20/month but adds latency.

## Support

For issues:
- Check CloudWatch logs first
- Verify secrets in Secrets Manager
- Test RabbitMQ connectivity
- Review ECS task stopped reasons

## Next Steps

1. Set up monitoring and alarms
2. Configure auto-scaling based on queue depth
3. Implement health checks
4. Set up CI/CD pipeline for automated deployments
5. Consider using AWS Copilot CLI for easier management

## Useful Commands Reference

```bash
# View running tasks
aws ecs list-tasks --cluster notification-services-cluster

# Stop a task
aws ecs stop-task --cluster notification-services-cluster --task TASK_ARN

# View service events
aws ecs describe-services --cluster notification-services-cluster --services email-service --query 'services[0].events'

# Update environment variables
aws ecs register-task-definition --cli-input-json file://task-definition-email.json
aws ecs update-service --cluster notification-services-cluster --service email-service --task-definition email-service:NEW_REVISION
```
