# TVM Upload System - Manual Testing Guide

> **Note:** This guide documents manual testing procedures for key features. For the complete automated test suite (16 tests, ~24 minutes), see `scripts/testing/run_manual_tests.sh` or refer to the [Autonomous Testing Guide](autonomous_testing_guide.md).

## 📋 Table of Contents
1. [Pre-requisites](#pre-requisites)
2. [Test Environment Setup](#test-environment-setup)
3. [Feature Testing Sequence](#feature-testing-sequence)
4. [Verification Checklist](#verification-checklist)
5. [Troubleshooting](#troubleshooting)

---

## Pre-requisites

### System Requirements
- [ ] Ubuntu/Linux system (tested on Ubuntu 20.04+)
- [ ] Python 3.8+ installed
- [ ] AWS CLI configured with China region credentials
- [ ] Minimum 10GB free disk space
- [ ] Network access to AWS China (cn-north-1)

### AWS Resources Required
- [ ] S3 bucket: `t01logs` (or configured bucket)
- [ ] IAM user/role with permissions:
  - S3: `s3:PutObject`, `s3:GetObject`, `s3:DeleteObject`, `s3:ListBucket`
  - CloudWatch: `cloudwatch:PutMetricData`, `cloudwatch:PutMetricAlarm`, `cloudwatch:DescribeAlarms`

### Test Data Preparation
```bash
# Create test log directories
mkdir -p ~/test-logs/terminal
mkdir -p ~/test-logs/ros
mkdir -p ~/test-logs/syslog

# Create sample log files
echo "Terminal log data" > ~/test-logs/terminal/session_$(date +%Y%m%d_%H%M%S).log
echo "ROS log data" > ~/test-logs/ros/rosout_$(date +%Y%m%d_%H%M%S).log
echo "Syslog data" > ~/test-logs/syslog/messages_$(date +%Y%m%d).log
```

---

## Test Environment Setup

### Step 1: Install Application
```bash
cd ~/tvm-upload
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Step 2: Configure Application
```bash
# Copy sample config
cp config/config.yaml.sample config/config.yaml

# Edit with your settings
nano config/config.yaml
```

**Critical Configuration Items to Verify:**
```yaml
vehicle_id: "test-vehicle-001"  # Change to unique ID

log_directories:
  - /home/autoware/.parcel/log/terminal
  - /home/autoware/.ros/log
  - /var/log
  # Add your test directories

s3:
  bucket: t01logs
  region: cn-north-1
  credentials_path: ~/.aws  # Verify this path

upload:
  schedule: "15:00"
  file_stable_seconds: 60

disk:
  reserved_gb: 5
  warning_threshold: 0.85
```

### Step 3: Verify AWS Credentials
```bash
# Test S3 access
aws s3 ls s3://t01logs --region cn-north-1

# Test CloudWatch access
aws cloudwatch list-metrics --namespace TVM/Upload --region cn-north-1
```

---

## Feature Testing Sequence

## 🟢 TEST 1: Basic File Upload (10 min)

### Purpose
Verify basic file monitoring and S3 upload functionality.

### Steps
1. **Start the service in foreground mode:**
   ```bash
   cd ~/tvm-upload
   source venv/bin/activate
   python3 -m src.main --config config/config.yaml
   ```

2. **Create a test file:**
   ```bash
   # In another terminal
   echo "Test upload at $(date)" > ~/test-logs/terminal/test1.log
   ```

3. **Wait for stability period (60 seconds by default)**

4. **Verify in logs:**
   ```
   Expected output:
   ✓ New file detected: test1.log
   ✓ File stable, ready for upload
   ✓ Uploaded to S3: test-vehicle-001/2025-01-XX/terminal/test1.log
   ```

5. **Verify in S3:**
   ```bash
   aws s3 ls s3://t01logs/test-vehicle-001/ --recursive --region cn-north-1
   ```

### Success Criteria
- [x] File detected within 5 seconds
- [x] Upload triggered after stability period
- [x] S3 key follows pattern: `{vehicle_id}/{YYYY-MM-DD}/{source}/{filename}`
- [x] File uploaded successfully
- [x] Local file deleted after upload (if deletion enabled)

---

## 🟢 TEST 2: Source-Based Path Detection (5 min)

### Purpose
Verify that files are categorized by their source directory.

### Steps
1. **Create files in different directories:**
   ```bash
   echo "Terminal log" > ~/test-logs/terminal/terminal.log
   echo "ROS log" > ~/test-logs/ros/rosout.log
   echo "Syslog" > ~/test-logs/syslog/messages.log
   ```

2. **Wait for uploads (60 seconds each)**

3. **Verify S3 paths:**
   ```bash
   aws s3 ls s3://t01logs/test-vehicle-001/$(date +%Y-%m-%d)/ --region cn-north-1
   ```

### Expected S3 Structure
```
test-vehicle-001/
  └── 2025-01-27/
      ├── terminal/
      │   └── terminal.log
      ├── ros/
      │   └── rosout.log
      └── syslog/
          └── messages.log
```

### Success Criteria
- [x] Terminal logs go to `terminal/` prefix
- [x] ROS logs go to `ros/` prefix
- [x] Syslog goes to `syslog/` prefix
- [x] Unknown sources go to `other/` prefix

---

## 🟢 TEST 3: File Date Preservation (5 min)

### Purpose
Verify that file modification dates are preserved in S3 path structure.

### Steps
1. **Create an old file (5 days ago):**
   ```bash
   touch -t $(date -d "5 days ago" +%Y%m%d0000) ~/test-logs/terminal/old_file.log
   echo "Old data" > ~/test-logs/terminal/old_file.log
   ```

2. **Wait for upload**

3. **Verify S3 path uses file date, not upload date:**
   ```bash
   # Should be in folder from 5 days ago
   aws s3 ls s3://t01logs/test-vehicle-001/$(date -d "5 days ago" +%Y-%m-%d)/ --region cn-north-1
   ```

### Success Criteria
- [x] S3 path uses file's modification date
- [x] Not using current upload date
- [x] Date format is YYYY-MM-DD

---

## 🟢 TEST 4: CloudWatch Metrics Publishing (10 min)

### Purpose
Verify metrics are published to CloudWatch.

### Steps
1. **Upload several files to generate metrics:**
   ```bash
   for i in {1..5}; do
     echo "File $i data" > ~/test-logs/terminal/file_$i.log
     sleep 70  # Wait for stability + upload
   done
   ```

2. **Check CloudWatch metrics:**
   ```bash
   aws cloudwatch get-metric-statistics \
     --namespace TVM/Upload \
     --metric-name BytesUploaded \
     --dimensions Name=VehicleId,Value=test-vehicle-001 \
     --start-time $(date -u -d "1 hour ago" +%Y-%m-%dT%H:%M:%S) \
     --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
     --period 3600 \
     --statistics Sum \
     --region cn-north-1
   ```

### Expected Metrics
- **BytesUploaded**: Total bytes (should be > 0)
- **FileCount**: Number of files (should be 5)
- **FailureCount**: Should be 0
- **DiskUsagePercent**: Current disk usage

### Success Criteria
- [x] Metrics appear in CloudWatch within 5 minutes
- [x] BytesUploaded > 0
- [x] FileCount matches uploaded files
- [x] No failures recorded

---

## 🟢 TEST 5: CloudWatch Alarm Creation (5 min)

### Purpose
Verify alarm creation for low upload volume.

### Steps
1. **Trigger alarm creation (if not auto-created):**
   ```bash
   # Check if alarm exists
   aws cloudwatch describe-alarms \
     --alarm-names "TVM-LowUpload-test-vehicle-001" \
     --region cn-north-1
   ```

2. **Verify alarm configuration:**
   - Threshold: 100 MB (configurable)
   - Evaluation periods: 3
   - Metric: BytesUploaded
   - Comparison: LessThanThreshold

### Success Criteria
- [x] Alarm created with correct name
- [x] Threshold configured correctly
- [x] Alarm is in INSUFFICIENT_DATA or OK state

---

## 🟢 TEST 6: Duplicate Upload Prevention (10 min)

### Purpose
Verify registry prevents re-uploading same files.

### Steps
1. **Upload a file:**
   ```bash
   echo "Original content" > ~/test-logs/terminal/registry_test.log
   # Wait for upload (70 seconds)
   ```

2. **Check S3:**
   ```bash
   aws s3 ls s3://t01logs/test-vehicle-001/ --recursive --region cn-north-1 | grep registry_test
   ```

3. **Stop and restart the service:**
   ```bash
   # Stop with Ctrl+C
   # Restart
   python3 -m src.main --config config/config.yaml
   ```

4. **Verify file is NOT re-uploaded:**
   - Check logs: Should see "File already in registry, skipping"
   - Check S3: Should still have only 1 copy

### Success Criteria
- [x] File uploaded once
- [x] Registry tracks uploaded files
- [x] Restart does not re-upload
- [x] Registry file exists at configured location

---

## 🟢 TEST 7: Disk Space Management (15 min)

### Purpose
Verify disk cleanup and management features.

### Steps
1. **Configure deletion policies in config.yaml:**
   ```yaml
   deletion:
     after_upload:
       enabled: true
       keep_days: 0  # Delete immediately after upload
     age_based:
       enabled: true
       max_age_days: 14
   ```

2. **Upload a file and verify deletion:**
   ```bash
   echo "Delete me after upload" > ~/test-logs/terminal/delete_test.log
   # Wait for upload (70 seconds)
   # Check if file is deleted locally
   ls ~/test-logs/terminal/delete_test.log  # Should not exist
   ```

3. **Test age-based cleanup:**
   ```bash
   # Create old file (10 days old)
   touch -t $(date -d "10 days ago" +%Y%m%d0000) ~/test-logs/terminal/very_old.log
   echo "Very old data" > ~/test-logs/terminal/very_old.log

   # Wait for cleanup cycle (runs at configured schedule)
   # Or manually trigger via service restart
   ```

### Success Criteria
- [x] Files deleted after successful upload
- [x] Old files (> max_age_days) are cleaned up
- [x] Disk space monitoring works
- [x] Emergency cleanup triggers at critical threshold

---

## 🟢 TEST 8: Batch Upload Performance (10 min)

### Purpose
Test handling multiple files simultaneously.

### Steps
1. **Create 20 files at once:**
   ```bash
   for i in {1..20}; do
     echo "Batch file $i content" > ~/test-logs/terminal/batch_$i.log
   done
   ```

2. **Monitor upload progress:**
   - Watch logs for batch processing
   - All files should stabilize
   - All files should upload

3. **Verify in S3:**
   ```bash
   aws s3 ls s3://t01logs/test-vehicle-001/$(date +%Y-%m-%d)/terminal/ \
     --region cn-north-1 | wc -l
   # Should show 20 files
   ```

### Success Criteria
- [x] All 20 files uploaded
- [x] No files missed
- [x] Upload completes within reasonable time
- [x] System remains responsive

---

## 🟢 TEST 9: Large File Upload (Multipart) (10 min)

### Purpose
Test multipart upload for files > 5MB.

### Steps
1. **Create large file (10MB):**
   ```bash
   dd if=/dev/urandom of=~/test-logs/terminal/large_file.log bs=1M count=10
   ```

2. **Monitor upload:**
   - Should see "Using multipart upload" in logs
   - Progress updates during upload

3. **Verify in S3:**
   ```bash
   aws s3api head-object \
     --bucket t01logs \
     --key test-vehicle-001/$(date +%Y-%m-%d)/terminal/large_file.log \
     --region cn-north-1
   ```

### Success Criteria
- [x] Multipart upload triggered for file > 5MB
- [x] File uploaded successfully
- [x] File size matches in S3
- [x] No corruption (verify checksum if possible)

---

## 🟢 TEST 10: Error Handling and Retry (15 min)

### Purpose
Test system resilience to errors.

### Steps
1. **Simulate network error:**
   ```bash
   # Temporarily block AWS endpoint
   sudo iptables -A OUTPUT -d s3.cn-north-1.amazonaws.com.cn -j DROP

   # Create test file
   echo "Retry test" > ~/test-logs/terminal/retry.log

   # Wait - should see retry attempts in logs
   # After 3-5 retries, unblock:
   sudo iptables -D OUTPUT -d s3.cn-north-1.amazonaws.com.cn -j DROP
   ```

2. **Verify retry mechanism:**
   - Logs should show retry attempts
   - File eventually uploads when network restored

3. **Test invalid credentials:**
   ```bash
   # Temporarily rename AWS credentials
   mv ~/.aws/credentials ~/.aws/credentials.bak

   # Create file - should fail with clear error
   echo "No creds" > ~/test-logs/terminal/nocreds.log

   # Restore credentials
   mv ~/.aws/credentials.bak ~/.aws/credentials
   ```

### Success Criteria
- [x] Retry mechanism activates on network errors
- [x] Exponential backoff observed
- [x] Clear error messages for auth failures
- [x] System recovers when issues resolved

---

## 🟢 TEST 11: Operational Hours Compliance (Optional, 5 min)

### Purpose
Verify uploads only happen during configured hours.

### Steps
1. **Configure operational hours:**
   ```yaml
   upload:
     operational_hours:
       enabled: true
       start: "09:00"
       end: "17:00"
   ```

2. **Test outside operational hours:**
   ```bash
   # If current time is outside 9AM-5PM:
   echo "Off hours test" > ~/test-logs/terminal/offhours.log
   # Should be queued, not uploaded immediately
   ```

3. **Check queue:**
   ```bash
   cat /tmp/upload_queue.json  # Or configured queue file
   # Should see file queued
   ```

### Success Criteria
- [x] Files queued outside operational hours
- [x] Files uploaded during operational hours
- [x] Queue persists across restarts

---

## 🟢 TEST 12: Service Restart Resilience (10 min)

### Purpose
Verify graceful shutdown and recovery.

### Steps
1. **Upload files during service run:**
   ```bash
   # Create some files
   for i in {1..3}; do
     echo "File $i" > ~/test-logs/terminal/restart_$i.log
   done
   ```

2. **Stop service gracefully (Ctrl+C)**

3. **Verify:**
   - Registry saved
   - Queue persisted (if any pending uploads)
   - No corrupted state

4. **Restart service:**
   ```bash
   python3 -m src.main --config config/config.yaml
   ```

5. **Verify:**
   - Service resumes from saved state
   - Pending uploads complete
   - No duplicate uploads

### Success Criteria
- [x] Graceful shutdown
- [x] State persisted
- [x] Clean restart
- [x] No data loss

---

## Verification Checklist

### Post-Testing Verification

#### S3 Bucket Structure
```bash
aws s3 ls s3://t01logs/test-vehicle-001/ --recursive --region cn-north-1
```

**Expected structure:**
```
test-vehicle-001/
  ├── 2025-01-22/
  │   ├── terminal/
  │   │   ├── file1.log
  │   │   └── file2.log
  │   ├── ros/
  │   │   └── rosout.log
  │   └── syslog/
  │       └── messages.log
  ├── 2025-01-23/
  │   └── ...
```

#### CloudWatch Metrics
```bash
# Check all metrics exist
aws cloudwatch list-metrics \
  --namespace TVM/Upload \
  --dimensions Name=VehicleId,Value=test-vehicle-001 \
  --region cn-north-1
```

**Expected metrics:**
- BytesUploaded
- FileCount
- FailureCount
- DiskUsagePercent

#### Local State Files
```bash
# Registry
cat /tmp/upload_registry.json | jq .

# Queue (if exists)
cat /tmp/upload_queue.json | jq .
```

#### System Logs
```bash
# Check for errors
journalctl -u tvm-upload -p err --since today  # If running as systemd service

# Or check application logs
tail -100 logs/tvm-upload.log
```

---

## Troubleshooting

### Issue: Files not uploading

**Symptoms:** Files detected but not uploaded

**Debug steps:**
```bash
# 1. Check stability period
grep "File stable" logs/tvm-upload.log

# 2. Check AWS credentials
aws sts get-caller-identity --region cn-north-1

# 3. Check S3 permissions
aws s3 ls s3://t01logs --region cn-north-1

# 4. Check network connectivity
ping s3.cn-north-1.amazonaws.com.cn
```

**Common causes:**
- Stability period not elapsed
- Network issues
- Invalid credentials
- Insufficient S3 permissions

---

### Issue: Duplicate uploads

**Symptoms:** Same file uploaded multiple times

**Debug steps:**
```bash
# Check registry
cat /tmp/upload_registry.json | grep filename

# Check file modification time
stat ~/test-logs/terminal/file.log
```

**Common causes:**
- Registry file corrupted
- File modified after upload
- Registry path misconfigured

---

### Issue: CloudWatch metrics not appearing

**Symptoms:** No metrics in CloudWatch

**Debug steps:**
```bash
# 1. Check CloudWatch permissions
aws cloudwatch list-metrics --namespace TVM/Upload --region cn-north-1

# 2. Check logs for publish errors
grep "CloudWatch" logs/tvm-upload.log

# 3. Verify namespace
aws cloudwatch list-metrics --region cn-north-1 | grep TVM
```

**Common causes:**
- CloudWatch disabled in config
- Insufficient permissions
- Network issues to CloudWatch endpoint

---

### Issue: Disk cleanup not working

**Symptoms:** Old files not deleted

**Debug steps:**
```bash
# Check deletion config
grep -A 5 "deletion:" config/config.yaml

# Check disk usage
df -h

# Check cleanup logs
grep "cleanup" logs/tvm-upload.log
```

**Common causes:**
- Deletion disabled in config
- Disk not at threshold
- File permissions prevent deletion

---

## Manual Testing Summary Report Template

After completing all tests, fill out this report:

```markdown
## TVM Upload System - Manual Testing Report

**Test Date:** YYYY-MM-DD
**Tester:** [Your Name]
**System:** [Ubuntu 20.04 / Vehicle ID / etc.]
**Version:** [Git commit hash]

### Test Results Summary

| Test # | Test Name | Status | Duration | Notes |
|--------|-----------|--------|----------|-------|
| 1 | Basic File Upload | ✅ PASS | 10 min | - |
| 2 | Source-Based Paths | ✅ PASS | 5 min | - |
| 3 | File Date Preservation | ✅ PASS | 5 min | - |
| 4 | CloudWatch Metrics | ✅ PASS | 10 min | - |
| 5 | CloudWatch Alarms | ✅ PASS | 5 min | - |
| 6 | Duplicate Prevention | ✅ PASS | 10 min | - |
| 7 | Disk Management | ✅ PASS | 15 min | - |
| 8 | Batch Upload | ✅ PASS | 10 min | - |
| 9 | Large File Upload | ✅ PASS | 10 min | - |
| 10 | Error Handling | ✅ PASS | 15 min | - |
| 11 | Operational Hours | ⏭️ SKIP | - | Not configured |
| 12 | Service Restart | ✅ PASS | 10 min | - |

**Total Tests:** 12
**Passed:** 11
**Failed:** 0
**Skipped:** 1

### Issues Found
1. [List any issues discovered]

### Recommendations
1. [Any suggestions for improvement]

### Attachments
- [ ] CloudWatch screenshots
- [ ] S3 bucket structure screenshot
- [ ] Log files
- [ ] Configuration used
```

---

## Next Steps After Manual Testing

1. **Run Complete Automated Test Suite:**
   ```bash
   # Complete manual test suite (16 tests, ~24 minutes)
   cd scripts/testing
   ./run_manual_tests.sh

   # Or run specific tests
   cd manual-tests
   ./01_startup_scan.sh
   ./02_source_based_path_detection.sh
   # ... etc
   ```

2. **Run Unit/Integration/E2E Tests:**
   ```bash
   # Unit tests (159 tests)
   pytest tests/unit/ -v

   # Integration tests (42 tests)
   pytest tests/integration/ -v

   # E2E tests (60 tests, requires AWS)
   pytest tests/e2e/ -v -m e2e
   ```

3. **Deploy to Production:**
   - Update config with production values
   - Set up as systemd service
   - Configure monitoring and alerts

4. **Monitor Production:**
   - Check CloudWatch dashboards
   - Review logs regularly
   - Monitor S3 costs

---

**Document Version:** 1.1
**Last Updated:** 2025-11-05
**Maintained By:** TVM Upload Team

### Changelog
- **v1.1** (2025-11-05): Added reference to complete automated test suite (16 tests)
- **v1.0** (2025-01-27): Initial manual testing guide with 12 key tests
