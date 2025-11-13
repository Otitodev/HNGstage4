# AWS ECS Service Control Guide

Quick reference for pausing, starting, and managing your AWS ECS services.

## Configuration

```powershell
$AWS_REGION = "eu-north-1"
$AWS_PROFILE = "otito2"
$CLUSTER_NAME = "notification-services"
```

---

## 🛑 Pause Services (Stop Charges)

Use this when you don't need the services running (development, testing, or to save costs).

```powershell
# Pause notification router
aws ecs update-service `
    --cluster notification-services `
    --service notification-router `
    --desired-count 0 `
    --region eu-north-1 `
    --profile otito2

# Pause email service
aws ecs update-service `
    --cluster notification-services `
    --service email-service `
    --desired-count 0 `
    --region eu-north-1 `
    --profile otito2

Write-Host "✓ Services paused! No tasks running = no ECS charges." -ForegroundColor Green
```

**What happens:**
- All running tasks are stopped
- No ECS Fargate charges while paused
- Services remain configured and ready to resume
- Docker images stay in ECR
- CloudWatch logs are preserved

---

## ▶️ Start Services (Resume)

Use this to resume services after pausing.

```powershell
# Start notification router
aws ecs update-service `
    --cluster notification-services `
    --service notification-router `
    --desired-count 1 `
    --region eu-north-1 `
    --profile otito2

# Start email service
aws ecs update-service `
    --cluster notification-services `
    --service email-service `
    --desired-count 1 `
    --region eu-north-1 `
    --profile otito2

Write-Host "✓ Services starting... Wait 1-2 minutes for tasks to be ready." -ForegroundColor Green

# Wait for services to start
Start-Sleep -Seconds 60

# Check status
aws ecs describe-services `
    --cluster notification-services `
    --services notification-router email-service `
    --region eu-north-1 `
    --profile otito2 `
    --query 'services[*].[serviceName,runningCount,desiredCount]'
```

**Startup time:** ~1-2 minutes

---

## 📊 Check Service Status

```powershell
# Quick status check
aws ecs describe-services `
    --cluster notification-services `
    --services notification-router email-service `
    --region eu-north-1 `
    --profile otito2 `
    --query 'services[*].[serviceName,runningCount,desiredCount,status]'

# Detailed status with recent events
aws ecs describe-services `
    --cluster notification-services `
    --services notification-router email-service `
    --region eu-north-1 `
    --profile otito2 `
    --query 'services[*].[serviceName,runningCount,events[0].message]'
```

**Status meanings:**
- `runningCount: 0, desiredCount: 0` = Paused (no charges)
- `runningCount: 1, desiredCount: 1` = Running normally
- `runningCount: 0, desiredCount: 1` = Starting up (wait a moment)

---

## 📝 View Logs

```powershell
# Notification router logs (live)
aws logs tail /ecs/notification-router --follow --region eu-north-1 --profile otito2

# Email service logs (live)
aws logs tail /ecs/email-service --follow --region eu-north-1 --profile otito2

# Last 50 lines (no follow)
aws logs tail /ecs/email-service --since 10m --region eu-north-1 --profile otito2
```

Press `Ctrl+C` to stop following logs.

---

## 🔄 Update Services (Deploy New Code)

When you make changes to your code and want to deploy:

```powershell
# 1. Navigate to services folder
cd C:\Users\USER\Documents\HNGstage4\services

# 2. Login to ECR
aws ecr get-login-password --region eu-north-1 --profile otito2 | `
    docker login --username AWS --password-stdin 114498381496.dkr.ecr.eu-north-1.amazonaws.com

# 3. Build and push notification router
docker build -t notification-router:latest -f Dockerfile.router .
docker tag notification-router:latest 114498381496.dkr.ecr.eu-north-1.amazonaws.com/notification-router:latest
docker push 114498381496.dkr.ecr.eu-north-1.amazonaws.com/notification-router:latest

# 4. Build and push email service
docker build -t email-service:latest -f Dockerfile.email .
docker tag email-service:latest 114498381496.dkr.ecr.eu-north-1.amazonaws.com/email-service:latest
docker push 114498381496.dkr.ecr.eu-north-1.amazonaws.com/email-service:latest

# 5. Force new deployment
aws ecs update-service `
    --cluster notification-services `
    --service notification-router `
    --force-new-deployment `
    --region eu-north-1 `
    --profile otito2

aws ecs update-service `
    --cluster notification-services `
    --service email-service `
    --force-new-deployment `
    --region eu-north-1 `
    --profile otito2

Write-Host "✓ New deployment triggered! Wait 2-3 minutes for rollout." -ForegroundColor Green
```

---

## 📈 Scale Services

Increase or decrease the number of running tasks:

```powershell
# Scale up to 2 tasks (for higher load)
aws ecs update-service `
    --cluster notification-services `
    --service email-service `
    --desired-count 2 `
    --region eu-north-1 `
    --profile otito2

# Scale down to 1 task (normal operation)
aws ecs update-service `
    --cluster notification-services `
    --service email-service `
    --desired-count 1 `
    --region eu-north-1 `
    --profile otito2
```

**Cost impact:** Each task costs ~$31/month, so 2 tasks = $62/month per service.

---

## 🧪 Test the System

Send a test notification:

```powershell
curl.exe -X POST `
    "https://otitodrichukwu8668-4qj3sovv.leapcell.dev/v1/notifications" `
    -H "X-Idempotency-Key: test-$(Get-Date -Format 'yyyyMMddHHmmss')" `
    -H "Content-Type: application/json" `
    -d "{\"user_id\":\"b9a46664-0942-4475-b4fb-bb803655bb01\",\"template_key\":\"WEEKLY_DIGEST\",\"message_data\":{\"app_name\":\"MyApp\",\"new_updates\":\"50\",\"digest_link\":\"https://example.com/digest\"}}"
```

Then check:
1. CloudWatch logs
2. Your email inbox
3. Database: `python services/check_email_logs.py`

---

## 🗑️ Delete Services (Complete Cleanup)

**⚠️ WARNING:** This permanently deletes the services. Use only if you want to completely remove them.

```powershell
# 1. Scale down to 0 first
aws ecs update-service --cluster notification-services --service notification-router --desired-count 0 --region eu-north-1 --profile otito2
aws ecs update-service --cluster notification-services --service email-service --desired-count 0 --region eu-north-1 --profile otito2

# 2. Wait for tasks to stop
Start-Sleep -Seconds 30

# 3. Delete services
aws ecs delete-service --cluster notification-services --service notification-router --region eu-north-1 --profile otito2
aws ecs delete-service --cluster notification-services --service email-service --region eu-north-1 --profile otito2

# 4. Delete cluster (optional)
aws ecs delete-cluster --cluster notification-services --region eu-north-1 --profile otito2

# 5. Delete ECR repositories (optional)
aws ecr delete-repository --repository-name notification-router --force --region eu-north-1 --profile otito2
aws ecr delete-repository --repository-name email-service --force --region eu-north-1 --profile otito2

Write-Host "✓ Services deleted." -ForegroundColor Yellow
```

---

## 💰 Cost Management

### Current Setup Costs

**When Running (desired count = 1):**
- Notification Router: ~$31/month
- Email Service: ~$31/month
- **Total: ~$62/month**

**When Paused (desired count = 0):**
- ECS Fargate: $0/month
- ECR Storage: ~$0.20/month (for Docker images)
- CloudWatch Logs: ~$0.50/month
- **Total: ~$0.70/month**

### Cost Optimization Tips

1. **Pause when not in use** (development/testing)
2. **Use smaller task sizes** (current: 0.25 vCPU, 0.5 GB)
3. **Set up auto-scaling** based on queue depth
4. **Monitor CloudWatch logs** and set retention policies
5. **Delete old ECR images** to reduce storage costs

---

## 🔧 Troubleshooting

### Services won't start

```powershell
# Check service events
aws ecs describe-services `
    --cluster notification-services `
    --services email-service `
    --region eu-north-1 `
    --profile otito2 `
    --query 'services[0].events[0:5]'

# Check task stopped reason
aws ecs describe-tasks `
    --cluster notification-services `
    --tasks TASK_ARN `
    --region eu-north-1 `
    --profile otito2
```

### Can't pull Docker image

```powershell
# Verify image exists in ECR
aws ecr describe-images --repository-name email-service --region eu-north-1 --profile otito2

# If missing, rebuild and push
docker build -t email-service:latest -f Dockerfile.email .
docker tag email-service:latest 114498381496.dkr.ecr.eu-north-1.amazonaws.com/email-service:latest
docker push 114498381496.dkr.ecr.eu-north-1.amazonaws.com/email-service:latest
```

### Service stuck in "DRAINING"

```powershell
# Force delete the service
aws ecs delete-service --cluster notification-services --service email-service --force --region eu-north-1 --profile otito2
```

---

## 📚 Quick Reference

| Action | Command |
|--------|---------|
| Pause services | `desired-count 0` |
| Start services | `desired-count 1` |
| Check status | `describe-services` |
| View logs | `logs tail /ecs/service-name --follow` |
| Update code | Build → Push → `force-new-deployment` |
| Scale up | `desired-count 2` |
| Delete | Scale to 0 → `delete-service` |

---

## 🎯 Common Workflows

### Daily Development

```powershell
# Morning: Start services
aws ecs update-service --cluster notification-services --service notification-router --desired-count 1 --region eu-north-1 --profile otito2
aws ecs update-service --cluster notification-services --service email-service --desired-count 1 --region eu-north-1 --profile otito2

# Evening: Pause services
aws ecs update-service --cluster notification-services --service notification-router --desired-count 0 --region eu-north-1 --profile otito2
aws ecs update-service --cluster notification-services --service email-service --desired-count 0 --region eu-north-1 --profile otito2
```

### Deploy New Version

```powershell
# Build and push
.\deploy_to_aws.ps1

# Force deployment
aws ecs update-service --cluster notification-services --service email-service --force-new-deployment --region eu-north-1 --profile otito2
```

### Production Mode

```powershell
# Keep services running 24/7
# Set up CloudWatch alarms
# Enable auto-scaling
# Monitor costs daily
```

---

**💡 Pro Tip:** Create PowerShell aliases for common commands:

```powershell
# Add to your PowerShell profile
function Start-NotificationServices {
    aws ecs update-service --cluster notification-services --service notification-router --desired-count 1 --region eu-north-1 --profile otito2
    aws ecs update-service --cluster notification-services --service email-service --desired-count 1 --region eu-north-1 --profile otito2
}

function Stop-NotificationServices {
    aws ecs update-service --cluster notification-services --service notification-router --desired-count 0 --region eu-north-1 --profile otito2
    aws ecs update-service --cluster notification-services --service email-service --desired-count 0 --region eu-north-1 --profile otito2
}

# Usage:
# Start-NotificationServices
# Stop-NotificationServices
```

---

**Need help?** Check CloudWatch logs first, then review the troubleshooting section above.
