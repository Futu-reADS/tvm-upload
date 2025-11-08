# TVM Upload System - Error Handling Guide

**Version:** 1.0
**Last Updated:** 2025-11-06
**Target Audience:** System administrators, DevOps engineers

---

## Overview

The TVM Upload System distinguishes between **temporary** and **permanent** errors to handle upload failures intelligently. Understanding this behavior is critical for troubleshooting and maintaining the system.

---

## Error Classification

### Temporary Errors (Retryable)

These errors are typically transient network or service issues. The system will **retry up to 10 times** with exponential backoff.

**Examples:**
- Network connectivity issues
- DNS resolution failures
- AWS service temporarily unavailable (503 Service Unavailable)
- Rate limiting / throttling (429 Too Many Requests)
- Connection timeouts
- Temporary authentication failures

**System Behavior:**
- File remains in upload queue
- Retry attempts: 1, 2, 4, 8, 16, 32, 64, 128, 256, 512 seconds (exponential backoff)
- After 10 failures: File marked as permanently failed and removed from queue
- Logs: `Retry X/10 for file.log`

**Resolution:**
- Usually resolves automatically when network/service recovers
- Monitor logs for persistent temporary errors
- Check network connectivity if errors persist

---

### Permanent Errors (Non-Retryable)

These errors indicate fundamental problems that won't be fixed by retrying. The system **immediately removes the file from queue** to prevent infinite retry loops.

**Examples:**

#### 1. File System Errors
- **File not found** - File was deleted before upload
- **Permission denied** - System doesn't have read access
- **Disk read error** - File corrupted or disk failure
- **File too large** - Exceeds system limits

#### 2. AWS Credential Errors
- **Invalid access key** - Credentials are wrong
- **Access key expired** - Temporary credentials expired
- **Signature mismatch** - Credential configuration error

#### 3. AWS Permission Errors
- **Access denied (403)** - IAM policy doesn't allow PutObject
- **Bucket not found (404)** - S3 bucket doesn't exist or wrong region
- **Bucket access forbidden** - Bucket policy denies access

#### 4. AWS Validation Errors
- **Invalid bucket name** - Configuration error
- **Invalid object key** - Filename contains illegal characters

**System Behavior:**
- File **immediately removed** from queue (no retry)
- Logs: `PERMANENT FAILURE` or `Permanent upload error`
- Requires manual intervention to fix

**Resolution:**
1. Check system logs for specific error
2. Fix underlying issue (permissions, credentials, configuration)
3. Manually re-queue file if needed (or wait for next startup scan)

---

## Monitoring Upload Errors

### Check for Temporary Errors

```bash
# View recent retry attempts
journalctl -u tvm-upload -n 100 | grep "Retry"

# Count retry attempts
journalctl -u tvm-upload --since "1 hour ago" | grep -c "Retry"

# See which files are failing temporarily
journalctl -u tvm-upload --since "1 hour ago" | grep "Retry" | awk '{print $NF}' | sort | uniq -c
```

**Expected Output:**
```
Retry 1/10 for test.log (next attempt in 1s)
Retry 2/10 for test.log (next attempt in 2s)
Retry 3/10 for test.log (next attempt in 4s)
```

**Action Required:**
- If same file retries > 5 times: Investigate network or AWS service issues
- If multiple files retry: Likely system-wide network problem

---

### Check for Permanent Errors

```bash
# Find all permanent failures
journalctl -u tvm-upload | grep "PERMANENT FAILURE"

# Find permanent failures in last 24 hours
journalctl -u tvm-upload --since "24 hours ago" | grep "Permanent upload error"

# Get detailed error messages
journalctl -u tvm-upload --since "24 hours ago" | grep -A 5 "PERMANENT FAILURE"
```

**Expected Output:**
```
PERMANENT FAILURE: File not found: /var/log/test.log
Permanent upload error for test.log: [Errno 2] No such file or directory
```

**Action Required:**
- **Always** investigate permanent failures
- Fix underlying issue (credentials, permissions, configuration)
- Files won't retry automatically

---

## Common Error Scenarios

### Scenario 1: Network Outage

**Symptoms:**
```
Retry 1/10 for file1.log (next attempt in 1s)
Retry 1/10 for file2.log (next attempt in 1s)
Retry 1/10 for file3.log (next attempt in 1s)
```

**Diagnosis:** Multiple files failing simultaneously → Network issue

**Resolution:**
- Check WiFi connectivity: `ping 8.8.8.8`
- Check AWS connectivity: `ping s3.cn-north-1.amazonaws.com.cn`
- Wait for network to recover
- Files will upload automatically when network returns

---

### Scenario 2: Invalid AWS Credentials

**Symptoms:**
```
PERMANENT FAILURE: InvalidAccessKeyId: The AWS Access Key Id you provided does not exist
```

**Diagnosis:** Credentials wrong or expired

**Resolution:**
```bash
# Verify credentials are configured
cat ~/.aws/credentials

# Test credentials
aws sts get-caller-identity --profile china --region cn-north-1

# If invalid, reconfigure
aws configure --profile china

# Restart service to pick up new credentials
sudo systemctl restart tvm-upload
```

---

### Scenario 3: IAM Permission Denied

**Symptoms:**
```
PERMANENT FAILURE: AccessDenied: Access Denied
```

**Diagnosis:** IAM policy missing required permissions

**Resolution:**
```bash
# Check current IAM permissions
aws iam get-user-policy --user-name tvm-upload-service --policy-name TvmUploadPolicy --region cn-north-1

# Verify S3 access
aws s3 ls s3://t01logs --profile china --region cn-north-1
```

Required IAM permissions:
- `s3:PutObject`
- `s3:GetObject`
- `s3:ListBucket`
- `cloudwatch:PutMetricData`

---

### Scenario 4: File Deleted Before Upload

**Symptoms:**
```
PERMANENT FAILURE: File not found: /var/log/old.log
```

**Diagnosis:** File was deleted (likely by logrotate or cleanup script) before upload completed

**Resolution:**
- **Normal behavior** - File was cleaned up before upload
- If frequent: Adjust `deletion.after_upload.keep_days` to give more time
- If critical logs: Disable deletion or increase retention

---

### Scenario 5: Disk Full During Upload

**Symptoms:**
```
PERMANENT FAILURE: [Errno 28] No space left on device
```

**Diagnosis:** Disk filled up during upload operation

**Resolution:**
```bash
# Check disk space
df -h /

# Enable emergency cleanup
sudo nano /etc/tvm-upload/config.yaml
# Set: deletion.emergency.enabled: true
# Set: deletion.emergency.threshold: 0.95

# Restart service
sudo systemctl restart tvm-upload

# Manually free space if needed
sudo journalctl --vacuum-time=7d
```

---

## Queue Management

### View Current Upload Queue

```bash
# View queue file
cat /var/lib/tvm-upload/queue.json | jq '.'

# Count pending files
cat /var/lib/tvm-upload/queue.json | jq '.files | length'

# See which files are queued
cat /var/lib/tvm-upload/queue.json | jq '.files[].filepath'
```

---

### Manually Re-Queue Failed Files

If you've fixed a permanent error and want to retry a file:

```bash
# Option 1: Wait for next startup scan (if file < 3 days old)
sudo systemctl restart tvm-upload

# Option 2: Touch the file to update modification time
touch /path/to/file.log
# System will detect change and re-queue (after 60s stability period)

# Option 3: Manually edit queue.json (advanced)
sudo nano /var/lib/tvm-upload/queue.json
# Add file to "files" array
sudo systemctl restart tvm-upload
```

---

## Preventing Common Errors

### Best Practices

1. **Monitor disk space**
   - Keep > 15% free space
   - Enable emergency cleanup
   - Regular monitoring: `df -h /`

2. **Validate credentials regularly**
   - Test monthly: `./scripts/diagnostics/verify_aws_credentials.sh`
   - Rotate credentials securely
   - Use IAM roles instead of access keys when possible

3. **Monitor error rates**
   ```bash
   # Daily error check
   journalctl -u tvm-upload --since "24 hours ago" | grep "PERMANENT FAILURE" | wc -l
   ```

4. **Review logs weekly**
   ```bash
   # Check for patterns
   journalctl -u tvm-upload --since "7 days ago" | grep -E "PERMANENT|Retry 10/10"
   ```

5. **Configure appropriate retention**
   - Balance between disk space and upload reliability
   - `deletion.after_upload.keep_days: 7` (recommended)
   - Adjust based on WiFi reliability

---

## CloudWatch Metrics

Monitor upload health via CloudWatch:

### Key Metrics

| Metric | Healthy Value | Alert Threshold |
|--------|---------------|-----------------|
| `FailureCount` | 0-2 per hour | > 5 per hour |
| `FileCount` | Varies | < 1 per day (no activity) |
| `DiskUsagePercent` | < 85% | > 90% |

### View Metrics

```bash
# Check failure count
aws cloudwatch get-metric-statistics \
  --namespace TVM/Upload \
  --metric-name FailureCount \
  --dimensions Name=VehicleId,Value=vehicle-CN-001 \
  --start-time 2025-11-06T00:00:00Z \
  --end-time 2025-11-06T23:59:59Z \
  --period 3600 \
  --statistics Sum \
  --profile china --region cn-north-1
```

---

## Troubleshooting Checklist

When uploads are failing:

- [ ] Check service status: `sudo systemctl status tvm-upload`
- [ ] Check recent logs: `journalctl -u tvm-upload -n 50`
- [ ] Check for permanent errors: `journalctl -u tvm-upload | grep "PERMANENT"`
- [ ] Check network: `ping s3.cn-north-1.amazonaws.com.cn`
- [ ] Check credentials: `aws sts get-caller-identity --profile china`
- [ ] Check disk space: `df -h /`
- [ ] Check queue size: `cat /var/lib/tvm-upload/queue.json | jq '.files | length'`
- [ ] Run health check: `sudo ./scripts/deployment/health_check.sh`

---

## Related Documentation

- [Deployment Guide](./deployment_guide.md) - Initial setup and configuration
- [Complete Reference](./complete_reference.md) - All features and configuration
- [Manual Testing Guide](./manual_testing_guide.md) - Test error scenarios

---

**Document Version:** 1.0
**Last Updated:** 2025-11-06
**Maintained By:** TVM Upload Team

### Changelog
- **v1.0** (2025-11-06): Initial error handling guide with temporary vs. permanent error classification
