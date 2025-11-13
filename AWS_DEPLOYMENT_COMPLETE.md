# Complete AWS ECS Deployment Guide

## Overview

Deploy your Email Service and Notification Router to AWS ECS Fargate for production use.

## Prerequisites

1. **AWS Account** with appropriate permissions
2. **AWS CLI** installed and configured
3. **Docker** installed locally
4. **Services tested locally** and working

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Leapcell.io                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │ API Gateway  │  │  Template    │  │    User      │ │
│  └──────┬───────┘  └──────────────┘  └──────────────┘ │
└─────────┼───────────────────────────────────────────────┘
          │
          ↓
┌─────────────────────────────────────────────────────────┐
│              RabbitMQ (Railway/CloudAMQP)               │
└─────────┬───────────────────────────────┬───────────────┘
          │                               │
          ↓                               ↓
┌─────────────────────┐         ┌─────────────────────┐
│   AWS ECS Fargate   │         │   AWS ECS Fargate   │
│  ┌───────────────┐  │         │  ┌───────────────┐  │
│  │ Notification  │  │         │  │ Email Service │  │
│  │    Router     │  │         │  │  + Database   │  │
│  └───────────────┘  │         │  └───────────────┘  │
└─────────────────────┘         └─────────────────────┘
          │                               │
          └───────────────┬───────────────┘
                          ↓
                ┌──────────────────┐
                │  Neon PostgreSQL │
                └──────────────────┘
```

## Step-by-Step Deployment

### Step 1: Configure AWS CLI

```bash
# Configure AWS credentials
aws configure --profile otito2

# Verify configuration
aws sts get-caller-identity --profile otito2
```

### Step 2: Store Secrets in AWS Secrets Manager

```bash
# Set your region
export AWS_REGION=us-east-1
export AWS_PROFILE=otito2

# Store RabbitMQ URL
aws secretsmanager create-secret \
    --name RABBITMQ_URL \
    --secret-string "amqp://user:pass@your-rabbitmq-host:5672/" \
    --region $AWS_REGION \
    --profile $AWS_PROFILE

# Store SendGrid API Key
aws secretsmanager create-secret \
    --name SENDGRID_API_KEY \
    --secret-string "SG.your_sendgrid_api_key" \
    --region $AWS_REGION \
    --profile $AWS_PROFILE

# Store Database URL
aws secretsmanager create-secret \
    --name NEON_DATABASE_URL \
    --secret-string "postgresql://user:pass@host/db?sslmode=require" \
    --region $AWS_REGION \
    --profile $AWS_PROFILE

# Store From Email
aws secretsmanager create-secret \
    --name FROM_EMAIL \
    --secret-string "mail@otito.site" \
    --region $AWS_REGION \
    --profile $AWS_PROFILE
```

**Note the ARNs returned** - you'll need them for task definitions.

### Step 3: Create IAM Role for ECS Tasks

```bash
# Create trust policy
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
    --assume-role-policy-document file://trust-policy.json \
    --profile $AWS_PROFILE

# Attach AWS managed policy
aws iam attach-role-policy \
    --role-name ecsTaskExecutionRole \
    --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy \
    --profile $AWS_PROFILE

# Create and attach Secrets Manager policy
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
        "arn:aws:secretsmanager:$AWS_REGION:*:secret:*"
      ]
    }
  ]
}
EOF

aws iam put-role-policy \
    --role-name ecsTaskExecutionRole \
    --policy-name SecretsManagerAccess \
    --policy-document file://secrets-policy.json \
    --profile $AWS_PROFILE
```

### Step 4: Run Deployment Script

```bash
cd services

# Make script executable
chmod +x deploy_to_aws.sh

# Run deployment
./deploy_to_aws.sh
```

This will:
- Create ECR repositories
- Build Docker images
- Push images to ECR
- Create ECS cluster
- Create CloudWatch log groups

### Step 5: Update Task Definitions

Get your AWS Account ID:
```bash
aws sts get-caller-identity --profile otito2 --query Account --output text
```

Update these files with your Account ID and Secret ARNs:
- `task-def-email-updated.json`
- `task-def-router-updated.json`

### Step 6: Register Task Definitions

```bash
# Register notification router task
aws ecs register-task-definition \
    --cli-input-json file://task-def-router-updated.json \
    --region $AWS_REGION \
    --profile $AWS_PROFILE

# Register email service task
aws ecs register-task-definition \
    --cli-input-json file://task-def-email-updated.json \
    --region $AWS_REGION \
    --profile $AWS_PROFILE
```

### Step 7: Set Up Networking

**Get VPC and Subnets:**
```bash
# Get default VPC
VPC_ID=$(aws ec2 describe-vpcs \
    --filters "Name=isDefault,Values=true" \
    --query "Vpcs[0].VpcId" \
    --output text \
    --profile $AWS_PROFILE)

echo "VPC ID: $VPC_ID"

# Get subnets
SUBNETS=$(aws ec2 describe-subnets \
    --filters "Name=vpc-id,Values=$VPC_ID" \
    --query "Subnets[*].SubnetId" \
    --output text \
    --profile $AWS_PROFILE)

echo "Subnets: $SUBNETS"
```

**Create Security Group:**
```bash
# Create security group
SG_ID=$(aws ec2 create-security-group \
    --group-name notification-services-sg \
    --description "Security group for notification services" \
    --vpc-id $VPC_ID \
    --profile $AWS_PROFILE \
    --query 'GroupId' \
    --output text)

echo "Security Group ID: $SG_ID"

# Allow all outbound traffic (for RabbitMQ, SendGrid, Database)
aws ec2 authorize-security-group-egress \
    --group-id $SG_ID \
    --protocol all \
    --cidr 0.0.0.0/0 \
    --profile $AWS_PROFILE
```

### Step 8: Create ECS Services

**Create Notification Router Service:**
```bash
aws ecs create-service \
    --cluster notification-services \
    --service-name notification-router \
    --task-definition notification-router \
    --desired-count 1 \
    --launch-type FARGATE \
    --network-configuration "awsvpcConfiguration={subnets=[$SUBNETS],securityGroups=[$SG_ID],assignPublicIp=ENABLED}" \
    --region $AWS_REGION \
    --profile $AWS_PROFILE
```

**Create Email Service:**
```bash
aws ecs create-service \
    --cluster notification-services \
    --service-name email-service \
    --task-definition email-service \
    --desired-count 1 \
    --launch-type FARGATE \
    --network-configuration "awsvpcConfiguration={subnets=[$SUBNETS],securityGroups=[$SG_ID],assignPublicIp=ENABLED}" \
    --region $AWS_REGION \
    --profile $AWS_PROFILE
```

### Step 9: Verify Deployment

**Check service status:**
```bash
# List services
aws ecs list-services \
    --cluster notification-services \
    --region $AWS_REGION \
    --profile $AWS_PROFILE

# Describe notification router
aws ecs describe-services \
    --cluster notification-services \
    --services notification-router \
    --region $AWS_REGION \
    --profile $AWS_PROFILE

# Describe email service
aws ecs describe-services \
    --cluster notification-services \
    --services email-service \
    --region $AWS_REGION \
    --profile $AWS_PROFILE
```

**View logs:**
```bash
# Notification router logs
aws logs tail /ecs/notification-router --follow --region $AWS_REGION --profile $AWS_PROFILE

# Email service logs
aws logs tail /ecs/email-service --follow --region $AWS_REGION --profile $AWS_PROFILE
```

### Step 10: Test the Deployment

Send a test notification through your API Gateway:

```bash
curl -X 'POST' \
  'https://otitodrichukwu8668-4qj3sovv.leapcell.dev/v1/notifications' \
  -H 'X-Idempotency-Key: aws-test-001' \
  -H 'Content-Type: application/json' \
  -d '{
    "user_id": "b9a46664-0942-4475-b4fb-bb803655bb01",
    "template_key": "WEEKLY_DIGEST",
    "message_data": {
      "app_name": "MyApp",
      "new_updates": "10",
      "digest_link": "https://example.com/digest"
    }
  }'
```

Then check:
1. CloudWatch logs for both services
2. Your email inbox
3. Database logs: `python services/check_email_logs.py`

## Cost Estimation

**Per Service (0.25 vCPU, 0.5 GB memory):**
- vCPU: $0.04048/hour
- Memory: $0.004445/GB/hour
- **Total: ~$0.043/hour or ~$31/month**

**For 2 services:**
- **~$62/month** for always-on services

**Additional:**
- CloudWatch Logs: ~$0.50/GB
- Data transfer: First 100 GB free
- ECR storage: $0.10/GB

**Total: ~$65-70/month**

## Scaling

### Manual Scaling
```bash
# Scale email service to 2 tasks
aws ecs update-service \
    --cluster notification-services \
    --service email-service \
    --desired-count 2 \
    --region $AWS_REGION \
    --profile $AWS_PROFILE
```

### Auto Scaling
```bash
# Register scalable target
aws application-autoscaling register-scalable-target \
    --service-namespace ecs \
    --scalable-dimension ecs:service:DesiredCount \
    --resource-id service/notification-services/email-service \
    --min-capacity 1 \
    --max-capacity 5 \
    --profile $AWS_PROFILE

# Create CPU-based scaling policy
aws application-autoscaling put-scaling-policy \
    --service-namespace ecs \
    --scalable-dimension ecs:service:DesiredCount \
    --resource-id service/notification-services/email-service \
    --policy-name cpu-scaling \
    --policy-type TargetTrackingScaling \
    --target-tracking-scaling-policy-configuration file://scaling-policy.json \
    --profile $AWS_PROFILE
```

## Updating Services

### Update Docker Image
```bash
cd services

# Rebuild and push
./deploy_to_aws.sh

# Force new deployment
aws ecs update-service \
    --cluster notification-services \
    --service email-service \
    --force-new-deployment \
    --region $AWS_REGION \
    --profile $AWS_PROFILE
```

## Monitoring

### CloudWatch Dashboards

Create a dashboard to monitor:
- Task count
- CPU/Memory utilization
- Log errors
- Message processing rate

### Set Up Alarms

```bash
# High CPU alarm
aws cloudwatch put-metric-alarm \
    --alarm-name email-service-high-cpu \
    --alarm-description "Alert when CPU exceeds 80%" \
    --metric-name CPUUtilization \
    --namespace AWS/ECS \
    --statistic Average \
    --period 300 \
    --threshold 80 \
    --comparison-operator GreaterThanThreshold \
    --evaluation-periods 2 \
    --profile $AWS_PROFILE
```

## Troubleshooting

### Service Won't Start

**Check task logs:**
```bash
# Get task ARN
TASK_ARN=$(aws ecs list-tasks \
    --cluster notification-services \
    --service-name email-service \
    --query 'taskArns[0]' \
    --output text \
    --profile $AWS_PROFILE)

# Describe task
aws ecs describe-tasks \
    --cluster notification-services \
    --tasks $TASK_ARN \
    --region $AWS_REGION \
    --profile $AWS_PROFILE
```

**Common issues:**
- Incorrect secret ARNs
- IAM role missing permissions
- Network configuration (subnets, security groups)
- Image pull errors

### Can't Connect to RabbitMQ

- Verify security group allows outbound traffic
- Check RabbitMQ URL in Secrets Manager
- Ensure tasks have public IP or NAT gateway

### Database Connection Issues

- Verify database URL in Secrets Manager
- Check security group allows outbound HTTPS
- Ensure SSL mode is set correctly

## Cleanup

### Delete Services
```bash
# Scale down to 0
aws ecs update-service \
    --cluster notification-services \
    --service email-service \
    --desired-count 0 \
    --profile $AWS_PROFILE

# Delete service
aws ecs delete-service \
    --cluster notification-services \
    --service email-service \
    --profile $AWS_PROFILE
```

### Delete Cluster
```bash
aws ecs delete-cluster \
    --cluster notification-services \
    --profile $AWS_PROFILE
```

### Delete ECR Repositories
```bash
aws ecr delete-repository \
    --repository-name email-service \
    --force \
    --profile $AWS_PROFILE
```

## Production Checklist

- [ ] Secrets stored in AWS Secrets Manager
- [ ] IAM roles configured with least privilege
- [ ] Security groups properly configured
- [ ] CloudWatch alarms set up
- [ ] Auto-scaling configured
- [ ] Database backups enabled
- [ ] Monitoring dashboard created
- [ ] Cost alerts configured
- [ ] Documentation updated
- [ ] Team trained on deployment process

## Support

For issues:
- Check CloudWatch logs
- Review ECS task stopped reasons
- Verify secrets in Secrets Manager
- Test RabbitMQ connectivity
- Check database connection

## Next Steps

1. Set up CI/CD pipeline (GitHub Actions, AWS CodePipeline)
2. Implement blue-green deployments
3. Add health checks
4. Configure custom domains
5. Set up centralized logging (ELK, Datadog)

---

**Deployment Complete!** Your notification services are now running on AWS ECS Fargate with full observability and scalability.
