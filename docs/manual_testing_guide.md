# TVM Upload System - Manual Testing Guide

> **Note:** This guide documents manual testing procedures for key features. For the complete automated test suite (17 core tests + 5 gap tests + 6 advanced tests = 28 tests, ~5.5 hours total), see `scripts/testing/run_manual_tests.sh` and `scripts/testing/gap-tests/run_gap_tests.sh`, or refer to the [Autonomous Testing Guide](autonomous_testing_guide.md).

## 📋 Table of Contents
1. [Pre-requisites](#pre-requisites)
2. [Test Environment Setup](#test-environment-setup)
3. [Core Manual Tests (Tests 1-17)](#core-manual-tests-tests-1-17)
4. [Gap Tests (Tests 18-22)](#gap-tests-tests-18-22)
5. [Advanced Tests (Tests 23, 25-29)](#advanced-tests-tests-23-25-29)
6. [Verification Checklist](#verification-checklist)
7. [Troubleshooting](#troubleshooting)

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
pip3 install -e ".[test]"
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

## Core Manual Tests (Tests 1-17)

These are the core manual tests that validate all primary functionality.

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

## 🟢 TEST 13: Pattern Matching (5 min)

### Purpose
Verify pattern filtering for log directories (e.g., `syslog*` only uploads matching files).

### Steps
1. **Configure pattern matching:**
   ```yaml
   log_directories:
     - path: /tmp/test-logs/syslog
       source: syslog
       pattern: "syslog*"
       recursive: false
   ```

2. **Create test files:**
   ```bash
   echo "Syslog main" > /tmp/test-logs/syslog/syslog
   echo "Syslog rotated 1" > /tmp/test-logs/syslog/syslog.1
   echo "Syslog rotated 2" > /tmp/test-logs/syslog/syslog.2.gz
   echo "Messages log" > /tmp/test-logs/syslog/messages.log  # Should NOT upload
   echo "Other log" > /tmp/test-logs/syslog/kern.log        # Should NOT upload
   ```

3. **Wait for uploads (60s stability + 20s)**

4. **Verify in S3:**
   ```bash
   aws s3 ls s3://bucket/vehicle-id/$(date +%Y-%m-%d)/syslog/ --profile china --region cn-north-1
   ```

### Expected Results
- ✅ `syslog` uploaded
- ✅ `syslog.1` uploaded
- ✅ `syslog.2.gz` uploaded
- ❌ `messages.log` NOT uploaded (filtered by pattern)
- ❌ `kern.log` NOT uploaded (filtered by pattern)

### Success Criteria
- [x] Only files matching pattern uploaded
- [x] Non-matching files filtered correctly
- [x] Pattern works with wildcards (*, ?)
- [x] No errors in logs

---

## 🟢 TEST 14: Recursive Monitoring (5 min)

### Purpose
Verify recursive vs non-recursive directory monitoring.

### Steps
1. **Configure recursive settings:**
   ```yaml
   log_directories:
     - path: /tmp/test-logs/ros
       source: ros
       recursive: true   # Upload from subdirectories

     - path: /tmp/test-logs/syslog
       source: syslog
       recursive: false  # Only top-level files
   ```

2. **Create test files:**
   ```bash
   # ROS (recursive: true)
   mkdir -p /tmp/test-logs/ros/session1
   mkdir -p /tmp/test-logs/ros/session2/subfolder
   echo "ROS root" > /tmp/test-logs/ros/root.log
   echo "ROS session1" > /tmp/test-logs/ros/session1/launch.log
   echo "ROS nested" > /tmp/test-logs/ros/session2/subfolder/nested.log

   # Syslog (recursive: false)
   mkdir -p /tmp/test-logs/syslog/subdir
   echo "Syslog root" > /tmp/test-logs/syslog/syslog
   echo "Syslog subdir" > /tmp/test-logs/syslog/subdir/messages.log
   ```

3. **Wait for uploads**

4. **Verify in S3:**
   ```bash
   # ROS: All files including nested should upload
   aws s3 ls s3://bucket/vehicle-id/DATE/ros/ --recursive

   # Syslog: Only root file should upload
   aws s3 ls s3://bucket/vehicle-id/DATE/syslog/ --recursive
   ```

### Expected Results
**ROS (recursive: true):**
- ✅ `ros/root.log`
- ✅ `ros/session1/launch.log`
- ✅ `ros/session2/subfolder/nested.log`

**Syslog (recursive: false):**
- ✅ `syslog/syslog`
- ❌ `syslog/subdir/messages.log` (NOT uploaded - subdirectory)

### Success Criteria
- [x] Recursive:true uploads from subdirectories
- [x] Recursive:false only uploads from root directory
- [x] Nested folder structure preserved in S3
- [x] Configuration enforced correctly

---

## 🟢 TEST 15: Basic File Upload (10 min)

### Purpose
Verify basic file monitoring and S3 upload functionality (fundamental system test).

### Steps
1. **Start the service:**
   ```bash
   python3 -m src.main --config config/config.yaml --log-level INFO
   ```

2. **Create a test file:**
   ```bash
   echo "Test upload at $(date)" > /tmp/test-logs/terminal/test.log
   ```

3. **Wait for stability period (60 seconds default)**

4. **Verify in logs:**
   ```
   Expected output:
   ✓ New file detected: test.log
   ✓ File stable, ready for upload
   ✓ Uploaded to S3: vehicle-id/YYYY-MM-DD/terminal/test.log
   ```

5. **Verify in S3:**
   ```bash
   aws s3 ls s3://bucket/vehicle-id/$(date +%Y-%m-%d)/terminal/test.log --profile china
   ```

### Success Criteria
- [x] File detected within 5 seconds
- [x] Upload triggered after stability period
- [x] S3 key follows pattern: `{vehicle_id}/{date}/{source}/{filename}`
- [x] File uploaded successfully
- [x] Local file handled per deletion policy

---

## 🟢 TEST 16: Emergency Cleanup Thresholds (10 min)

### Purpose
Verify emergency cleanup when disk reaches critical threshold (90% or 95%).

### Steps
1. **Configure emergency cleanup:**
   ```yaml
   disk:
     warning_threshold: 0.90   # 90%
     critical_threshold: 0.95  # 95%

   deletion:
     emergency:
       enabled: true
   ```

2. **Check current disk usage:**
   ```bash
   df -h /tmp
   ```

3. **Simulate high disk usage** (if disk not already full):
   ```bash
   # Create large file to fill disk to 91%
   # WARNING: Use caution with this step
   ```

4. **Monitor service logs for emergency cleanup:**
   ```bash
   tail -f /var/log/tvm-upload.log | grep -i "emergency\|cleanup\|disk"
   ```

### Expected Behavior
- **Disk 85-89%:** Normal operation, no emergency action
- **Disk 90-94%:** Delete oldest uploaded files (respects keep_days)
- **Disk 95%+:** Critical - Delete ANY old files to prevent system failure

### Success Criteria
- [x] Emergency cleanup triggers at warning_threshold (90%)
- [x] Critical cleanup triggers at critical_threshold (95%)
- [x] Oldest files deleted first
- [x] System remains stable and doesn't crash
- [x] Clear log messages indicate cleanup actions

---

## 🟢 TEST 17: Deletion Safety System (5 min)

### Purpose
Verify 4-layer deletion safety prevents accidental deletion of system files.

### Safety Layers
1. **Layer 1:** System directory protection (hard-coded: /var, /etc, /usr, /bin, /sbin, /sys, /proc, /dev, /boot, /home, /root, /lib, /lib64, /opt, /snap)
2. **Layer 2:** `allow_deletion` flag (user control)
3. **Layer 3:** `recursive` flag (subdirectory protection)
4. **Layer 4:** Pattern matching (only matching files)

### Steps
1. **Test system directory protection:**
   ```yaml
   log_directories:
     - path: /var/log
       source: syslog
       allow_deletion: true  # Override attempt
   ```
   - **Expected:** Files in /var/log NEVER deleted (hard-coded protection)

2. **Test allow_deletion flag:**
   ```yaml
   log_directories:
     - path: /tmp/test-logs
       source: test
       allow_deletion: false  # Explicit disable
   ```
   - **Expected:** Files uploaded but never deleted

3. **Test recursive protection:**
   ```yaml
   log_directories:
     - path: /tmp/test-logs
       source: test
       recursive: false
       allow_deletion: true
   ```
   - **Expected:** Only root-level files deleted, subdirectories untouched

4. **Test pattern matching:**
   ```yaml
   log_directories:
     - path: /tmp/test-logs/syslog
       source: syslog
       pattern: "syslog*"
       allow_deletion: true
   ```
   - **Expected:** Only `syslog*` files deleted, `messages.log` kept

### Success Criteria
- [x] System directories NEVER deleted (overrides all flags)
- [x] allow_deletion:false prevents deletion
- [x] recursive:false protects subdirectories
- [x] Pattern filtering works correctly
- [x] Multiple safety layers work together

---

## Gap Tests (Tests 18-22)

These tests cover advanced edge cases and scenarios not tested in the core suite. Run with:
```bash
make test-gap
# Or manually:
./scripts/testing/gap-tests/run_gap_tests.sh
```

---

## 🟡 TEST 18: All 4 Log Sources Simultaneously (10 min)

### Purpose
Verify all 4 default log sources work together without interference.

### Sources Tested
1. **Terminal** (simple files)
2. **ROS** (nested structure)
3. **Syslog** (pattern matching)
4. **ROS2** (nested structure)

### Steps
1. **Configure all 4 sources:**
   ```yaml
   log_directories:
     - path: /tmp/test/terminal
       source: terminal
       recursive: true

     - path: /tmp/test/ros
       source: ros
       recursive: true

     - path: /tmp/test/syslog
       source: syslog
       pattern: "syslog*"
       recursive: false

     - path: /tmp/test/ros2
       source: ros2
       recursive: true
   ```

2. **Create files in all sources:**
   - Terminal: 2 files
   - ROS: 4 files (with nested structure)
   - Syslog: 2 matching `syslog*`, 1 non-matching
   - ROS2: 2 files

3. **Wait for uploads**

4. **Verify S3 structure:**
   ```
   vehicle-id/
     2025-01-27/
       terminal/
         file1.log
         file2.log
       ros/
         session1/launch.log
         session2/subfolder/nested.log
       syslog/
         syslog
         syslog.1
       ros2/
         launch/launch.log
         node.log
   ```

### Expected Results
- ✅ 10 total files uploaded
- ✅ All 4 source folders created independently
- ✅ ROS nested structure preserved
- ✅ Syslog pattern filtering works
- ✅ No source interference or conflicts

---

## 🟡 TEST 19: Deferred Deletion (keep_days > 0) (3 min)

### Purpose
Verify files are kept for N days after upload before deletion.

### Steps
1. **Configure deferred deletion:**
   ```yaml
   deletion:
     after_upload:
       enabled: true
       keep_days: 14  # Keep for 14 days after upload
   ```

2. **Upload files and verify:**
   - Files remain locally after upload
   - Files deleted after 14 days
   - S3 files remain (only local deletion)

### Test Shortcut
For quick testing, use `keep_days: 0.001` (~90 seconds):
```yaml
keep_days: 0.001  # For testing only
```

### Expected Behavior
```
Upload → File kept locally for 14 days → Local deletion → S3 file remains
```

### Success Criteria
- [x] Files exist immediately after upload
- [x] Files deleted after keep_days expires
- [x] Files remain in S3 (only local deletion)
- [x] Different from keep_days:0 (immediate deletion)

---

## 🟡 TEST 20: Queue Recovery After Crash (5 min)

### Purpose
Verify queue survives hard crash (kill -9) and files upload after restart.

### Steps
1. **Start service and queue files:**
   ```bash
   # Create 3 files that will be queued
   for i in {1..3}; do
     echo "Test $i" > /tmp/test/terminal/crash_$i.log
   done
   ```

2. **Wait for files to be queued** (60s stability)

3. **Simulate crash:**
   ```bash
   # Get service PID
   PID=$(pgrep -f "python.*src.main")

   # Kill with SIGKILL (no graceful shutdown)
   kill -9 $PID
   ```

4. **Verify queue persisted:**
   ```bash
   cat /var/lib/tvm-upload/queue.json
   # Should show 3 files queued
   ```

5. **Restart service:**
   ```bash
   python3 -m src.main --config config/config.yaml
   ```

6. **Verify files upload after restart:**
   ```bash
   aws s3 ls s3://bucket/vehicle-id/DATE/terminal/ | grep crash_
   # Should show all 3 files
   ```

### Success Criteria
- [x] Queue file survives kill -9
- [x] Queue entries preserved after crash
- [x] Service restarts successfully
- [x] All queued files upload after restart
- [x] No data loss

---

## 🟡 TEST 21: Registry Cleanup After Retention Days (5 min)

### Purpose
Verify old registry entries are removed after retention_days to prevent infinite growth.

### Steps
1. **Configure registry retention:**
   ```yaml
   upload:
     processed_files_registry:
       registry_file: /var/lib/tvm-upload/processed_files.json
       retention_days: 30  # Keep entries for 30 days
   ```

2. **Manually seed old entries:**
   ```bash
   # Edit registry file to add entries 50 days old
   # Service should clean these on startup
   ```

3. **Start service and verify cleanup:**
   ```bash
   # Check logs for cleanup messages
   journalctl -u tvm-upload | grep -i "registry.*cleanup"

   # Verify old entries removed
   cat /var/lib/tvm-upload/processed_files.json
   ```

### Expected Behavior
- Entries older than 30 days → Removed
- Entries newer than 30 days → Kept
- New uploads → Added to registry

### Success Criteria
- [x] Old entries (>30 days) removed on startup
- [x] Recent entries (<30 days) kept
- [x] Registry doesn't grow infinitely
- [x] New uploads still tracked

---

## 🟡 TEST 22: Environment Variable Path Expansion (5 min)

### Purpose
Verify environment variables in config paths are expanded correctly.

### Steps
1. **Configure paths with env vars:**
   ```yaml
   log_directories:
     - path: ${HOME}/tvm-logs/terminal
       source: terminal

     - path: /tmp/tvm-user-${USER}/ros
       source: ros

     - path: ~/logs/syslog  # Tilde expansion
       source: syslog
   ```

2. **Create files in expanded paths:**
   ```bash
   mkdir -p ${HOME}/tvm-logs/terminal
   echo "Test" > ${HOME}/tvm-logs/terminal/test.log
   ```

3. **Start service and verify:**
   - Paths expanded correctly
   - Files detected and uploaded
   - No path resolution errors

### Success Criteria
- [x] ${HOME} expanded to /home/username
- [x] ${USER} expanded to username
- [x] ~ expanded to home directory
- [x] Files uploaded from expanded paths
- [x] No "path not found" errors

---

## Advanced Tests (Tests 23, 25-29)

These tests cover advanced scenarios including configuration validation, concurrency, security, performance benchmarking, and full system integration. Run with:
```bash
cd scripts/testing/gap-tests
./23_config_validation.sh config/config.yaml
./25_concurrent_operations.sh config/config.yaml
./26_resource_limits.sh config/config.yaml
./27_security_scenarios.sh config/config.yaml
./28_performance_benchmarks.sh config/config.yaml
./29_full_system_integration.sh config/config.yaml
```

---

## 🔵 TEST 23: Configuration Validation (10 min)

### Purpose
Verify comprehensive configuration validation with clear, actionable error messages.

### Test Coverage
- Invalid YAML syntax (missing colons, unclosed quotes, bad indentation)
- Missing required fields (vehicle_id, log_directories, s3.bucket, s3.region)
- Type validation (string vs number, list vs string)
- Range validation (thresholds 0-1, negative values)
- Conflicting settings (critical < warning)
- Invalid time formats (24-hour HH:MM required)
- Invalid pattern syntax (empty patterns)
- Path validation (non-existent, relative paths)
- Schedule mode validation (daily/interval only)
- AWS region validation

### Steps
Run the automated test script:
```bash
./scripts/testing/gap-tests/23_config_validation.sh config/config.yaml
```

The script will test 20+ invalid configuration scenarios and verify:
1. **Clear error detection** - Each invalid config produces an error
2. **Actionable messages** - Errors explain what's wrong and how to fix it
3. **Early validation** - Config errors caught at startup, not during operation
4. **Valid config acceptance** - Proper configuration passes validation

### Expected Results
- ✅ All invalid configurations rejected with clear error messages
- ✅ Valid configuration accepted
- ✅ Service starts successfully with valid config
- ✅ No ambiguous error messages

### Success Criteria
- [x] 20+ validation scenarios tested
- [x] Each invalid config produces appropriate error
- [x] Error messages are clear and actionable
- [x] Valid configuration passes all checks

---

## 🔵 TEST 25: Concurrent Operations (15 min)

### Purpose
Verify thread safety and race condition handling under concurrent operations.

### Test Coverage
1. **Simultaneous File Creation** - 100 files created in parallel
2. **Files Modified During Upload** - File changes while being uploaded
3. **Files Deleted from Queue** - Queue entries removed while processing
4. **Directory Renamed During Monitoring** - Monitored directory moved/renamed
5. **Concurrent Registry Updates** - Multiple uploads updating registry simultaneously

### Steps
Run the automated test script:
```bash
./scripts/testing/gap-tests/25_concurrent_operations.sh config/config.yaml
```

The script will:
1. Create 100 files simultaneously using background processes
2. Modify a large file during upload
3. Delete files from queue while service is running
4. Rename monitored directory during operation
5. Trigger concurrent registry updates

### Expected Results
- ✅ All 100 files detected (95+ minimum acceptable)
- ✅ No race condition errors in logs
- ✅ Service handles file modification gracefully
- ✅ Missing files detected without crash
- ✅ Directory rename handled appropriately
- ✅ Registry remains valid JSON (no corruption)
- ✅ Service remains stable throughout

### Success Criteria
- [x] 95%+ of concurrent files detected
- [x] No race condition errors
- [x] No deadlocks or lock timeouts
- [x] Registry integrity maintained
- [x] Service doesn't crash under concurrent load

---

## 🔵 TEST 26: Resource Limits (30 min)

### Purpose
Test system behavior under resource exhaustion (large queues, memory pressure, S3 rate limits).

### Test Coverage
1. **Large Queue Stress** - 10,000 files in queue
2. **Resource Monitoring** - CPU and memory usage tracking
3. **Queue Processing Efficiency** - Processing rate and success rate
4. **S3 Rate Limiting** - 429 error detection and retry
5. **Error Recovery** - Graceful degradation under stress
6. **System Stability** - Memory leaks and responsiveness

### Steps
Run the automated test script:
```bash
./scripts/testing/gap-tests/26_resource_limits.sh config/config.yaml
```

The script will:
1. Create 10,000 files in batches
2. Monitor CPU and memory usage every 30 seconds
3. Track queue processing rate
4. Detect S3 rate limiting (429 errors)
5. Verify graceful degradation
6. Check for memory leaks

### Expected Results
- ✅ All 10,000 files queued successfully
- ✅ Peak CPU usage < 50% (may vary by hardware)
- ✅ Memory usage stable (no runaway growth)
- ✅ Processing rate: 10-50 files/minute (typical)
- ✅ S3 rate limiting handled with retry
- ✅ Service remains responsive
- ✅ No crashes under stress

### Metrics Tracked
- Peak CPU usage (%)
- Peak memory usage (MB)
- Files processed per minute
- Upload success rate (%)
- Error counts (total, critical)
- Rate limit occurrences

### Success Criteria
- [x] Large queue handled without crash
- [x] CPU usage reasonable (<80%)
- [x] Memory usage stable (no leaks)
- [x] Graceful degradation under load
- [x] S3 rate limiting detected and handled
- [x] Service recovers after stress

---

## 🔵 TEST 27: Security Scenarios (15 min)

### Purpose
Verify security handling and protection against common attack vectors.

### Test Coverage
1. **File Permission Issues** - Files with restrictive permissions (000)
2. **Symlink Attacks** - Symlinks to sensitive files (/etc/passwd)
3. **Path Traversal** - Filenames with ../../../
4. **AWS Credential Expiration** - Expired/missing credentials
5. **Invalid Bucket Access** - Non-existent or inaccessible S3 bucket
6. **Filename Injection** - Special characters in filenames

### Steps
Run the automated test script:
```bash
./scripts/testing/gap-tests/27_security_scenarios.sh config/config.yaml
```

The script will:
1. Create file with 000 permissions and verify skip
2. Create symlink to /etc/passwd and verify NOT uploaded
3. Create file with path traversal in name
4. Test with missing/expired AWS credentials
5. Test with invalid bucket name
6. Create files with special characters

### Expected Results
- ✅ Unreadable files (chmod 000) skipped with clear error
- ✅ Symlinks NOT followed (critical security requirement)
- ✅ Path traversal attempts sanitized
- ✅ Credential errors handled gracefully with retry
- ✅ Invalid bucket produces clear error
- ✅ Special characters in filenames handled safely
- ✅ Service continues after security events

### Security Validation
- **NO symlink following** - /etc/passwd must NOT be uploaded
- **Path sanitization** - ../ sequences removed
- **Error handling** - No crash on security events
- **Clear logging** - Security warnings logged

### Success Criteria
- [x] Symlinks NOT followed (critical)
- [x] Path traversal prevented
- [x] Unreadable files skipped safely
- [x] Credential errors handled gracefully
- [x] Service remains stable after security events
- [x] Clear security warnings in logs

---

## 🔵 TEST 28: Performance Benchmarks (20 min)

### Purpose
Establish performance baselines for throughput, latency, and resource usage.

### Test Coverage
1. **1000 Small Files Benchmark** - 1000 files × 1KB each
2. **100 Large Files Benchmark** - 100 files × 10MB each
3. **CPU Profiling** - CPU usage during uploads
4. **Memory Profiling** - Memory usage during uploads
5. **Network Throughput** - Bandwidth utilization

### Steps
Run the automated test script:
```bash
./scripts/testing/gap-tests/28_performance_benchmarks.sh config/config.yaml
```

The script will:
1. **Benchmark 1**: Create 1000 × 1KB files, measure upload time
2. **Benchmark 2**: Create 100 × 10MB files, measure upload time
3. Monitor CPU usage during uploads
4. Monitor memory usage during uploads
5. Calculate throughput metrics

### Expected Results
- ✅ Small files: 10-50 files/second (typical)
- ✅ Large files: 1-10 MB/second (network dependent)
- ✅ CPU usage stable during uploads
- ✅ Memory usage proportional to file count
- ✅ No performance degradation over time

### Metrics Tracked
- **Files per second** - Small file upload rate
- **MB per second** - Large file upload rate
- **Peak CPU usage** - Maximum CPU during benchmark
- **Peak memory usage** - Maximum memory during benchmark
- **Total upload time** - End-to-end benchmark duration

### Performance Baselines
These are typical values for reference (actual values vary by hardware/network):
- Small files (1KB): 20-50 files/sec
- Large files (10MB): 2-10 MB/sec
- CPU usage: 10-30% during active upload
- Memory usage: 50-200MB for 1000 files

### Success Criteria
- [x] Benchmarks complete without errors
- [x] Performance metrics within acceptable ranges
- [x] No performance degradation over time
- [x] Resource usage reasonable
- [x] Baseline established for future comparison

---

## 🔵 TEST 29: Full System Integration (1-2 hours)

### Purpose
Test all features working together in a production-like scenario with continuous file generation.

### Test Coverage
All features enabled simultaneously:
- 4 log sources (terminal, ros, syslog, ros2)
- Pattern matching (syslog* filter)
- Recursive monitoring
- Deferred deletion
- Emergency cleanup
- CloudWatch metrics (optional)
- Operational hours
- Scheduled uploads (2-minute interval for testing)
- Batch uploads
- Queue persistence
- Registry tracking

### Steps
Run the automated test script:
```bash
./scripts/testing/gap-tests/29_full_system_integration.sh config/config.yaml
```

The script will:
1. **Phase 1**: Create initial files in all 4 sources (60+ files)
2. **Phase 2**: Monitor initial upload (2 minutes)
3. **Phase 3**: Continuous file generation for 10 minutes (~100 files)
4. **Phase 4**: Feature verification (pattern matching, deletion, etc.)

### Continuous Workload
Simulates production environment:
- ~10 files/minute generation rate
- Mixed sources (terminal, ROS, syslog, ROS2)
- Varied file sizes (1KB - 100KB)
- Recursive directory structure
- Pattern filtering (syslog* only)

### Expected Results
- ✅ All 4 sources upload independently
- ✅ Pattern matching filters correctly (messages.log excluded)
- ✅ Recursive monitoring works (nested files uploaded)
- ✅ Deferred deletion delays removal
- ✅ Queue processes continuously
- ✅ Registry prevents duplicates
- ✅ No critical errors during 15-minute test
- ✅ Service remains stable throughout

### Feature Validation
- **4 sources**: Terminal, ROS, Syslog, ROS2 all uploading
- **Pattern matching**: Only syslog* files from syslog directory
- **Recursive monitoring**: Nested files detected and uploaded
- **Batch uploads**: Multiple files uploaded efficiently
- **Scheduled uploads**: Uploads triggered every 2 minutes
- **Deferred deletion**: Files kept for configured duration
- **Queue persistence**: Queue survives throughout test
- **Registry tracking**: No duplicate uploads

### Success Criteria
- [x] All 4 sources working simultaneously
- [x] All features functional
- [x] No critical errors
- [x] Service stable for 15+ minutes
- [x] 100+ files uploaded successfully
- [x] Pattern matching working
- [x] Deferred deletion working
- [x] No feature interference

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

### Core Manual Tests Results (Tests 1-17)

| Test # | Test Name | Status | Duration | Notes |
|--------|-----------|--------|----------|-------|
| 1 | Startup Scan | ✅ PASS | 10 min | - |
| 2 | Source-Based Paths | ✅ PASS | 5 min | - |
| 3 | File Date Preservation | ✅ PASS | 5 min | - |
| 4 | CloudWatch Metrics | ✅ PASS | 10 min | - |
| 5 | CloudWatch Alarms | ✅ PASS | 5 min | - |
| 6 | Duplicate Prevention | ✅ PASS | 10 min | - |
| 7 | Disk Management | ✅ PASS | 15 min | - |
| 8 | Batch Upload | ✅ PASS | 10 min | - |
| 9 | Large File Upload | ✅ PASS | 10 min | - |
| 10 | Error Handling | ✅ PASS | 15 min | - |
| 11 | Operational Hours | ✅ PASS | 10 min | - |
| 12 | Service Restart | ✅ PASS | 10 min | - |
| 13 | Pattern Matching | ✅ PASS | 5 min | - |
| 14 | Recursive Monitoring | ✅ PASS | 5 min | - |
| 15 | Basic File Upload | ✅ PASS | 10 min | - |
| 16 | Emergency Cleanup | ✅ PASS | 10 min | - |
| 17 | Deletion Safety | ✅ PASS | 5 min | - |

**Core Tests Total:** 17
**Estimated Duration:** ~2.5 hours

### Gap Tests Results (Tests 18-22)

| Test # | Test Name | Status | Duration | Notes |
|--------|-----------|--------|----------|-------|
| 18 | All 4 Sources Simultaneously | ⏸️ NOT RUN | 10 min | - |
| 19 | Deferred Deletion | ⏸️ NOT RUN | 3 min | - |
| 20 | Queue Crash Recovery | ⏸️ NOT RUN | 5 min | - |
| 21 | Registry Cleanup | ⏸️ NOT RUN | 5 min | - |
| 22 | Env Var Expansion | ⏸️ NOT RUN | 5 min | - |

**Gap Tests Total:** 5
**Estimated Duration:** ~30 minutes

### Advanced Tests Results (Tests 23, 25-29)

| Test # | Test Name | Status | Duration | Notes |
|--------|-----------|--------|----------|-------|
| 23 | Configuration Validation | ⏸️ NOT RUN | 10 min | 20+ validation scenarios |
| 25 | Concurrent Operations | ⏸️ NOT RUN | 15 min | Thread safety, race conditions |
| 26 | Resource Limits | ⏸️ NOT RUN | 30 min | 10K queue, stress testing |
| 27 | Security Scenarios | ⏸️ NOT RUN | 15 min | Symlinks, path traversal |
| 28 | Performance Benchmarks | ⏸️ NOT RUN | 20 min | Throughput baselines |
| 29 | Full System Integration | ⏸️ NOT RUN | 60-120 min | All features together |

**Advanced Tests Total:** 6
**Estimated Duration:** ~2.5 hours

---

### Combined Summary

**Total Tests:** 28 (17 core + 5 gap + 6 advanced)
**Passed:** 17 (core tests)
**Failed:** 0
**Skipped:** 0
**Not Run:** 11 (gap + advanced tests)

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
   # Using Makefile (recommended)
   make test-manual                # Core manual tests (17 scenarios, ~2.5 hours)
   make test-gap                   # Gap tests (5 scenarios, ~30 min)
   make test-all-manual            # All manual tests (22 scenarios, ~3 hours)

   # Or run scripts directly
   ./scripts/testing/run_manual_tests.sh      # Core tests
   ./scripts/testing/gap-tests/run_gap_tests.sh  # Gap tests

   # Or run specific tests manually
   ./scripts/testing/manual-tests/01_startup_scan.sh config/config.yaml
   ./scripts/testing/manual-tests/13_pattern_matching.sh config/config.yaml
   ./scripts/testing/gap-tests/20_queue_crash_recovery.sh config/config.yaml
   ```

2. **Run Unit/Integration/E2E Tests:**
   ```bash
   # Using Makefile (recommended)
   make test-fast              # Unit tests (~5 sec)
   make test                   # Unit + integration tests (~40 sec)
   make test-e2e               # E2E tests (requires AWS, ~7.5 min)
   make test-all               # ALL automated tests (unit + integration + E2E)

   # Or using pytest directly
   pytest tests/unit/ -v                    # 249 unit tests
   pytest tests/integration/ -v             # 90 integration tests
   pytest tests/e2e/ -v -m e2e              # 60 E2E tests (requires AWS)
   ```

3. **Deploy to Production:**
   ```bash
   # Verify prerequisites
   make deploy-verify

   # Install to production
   make deploy-install

   # Health check
   make deploy-health
   ```

4. **Monitor Production:**
   - Check CloudWatch dashboards (TVM/Upload namespace)
   - Review logs: `journalctl -u tvm-upload -f`
   - Monitor S3 costs and storage
   - Track disk usage trends

---

**Document Version:** 3.0
**Last Updated:** 2025-11-11
**Maintained By:** TVM Upload Team

### Changelog
- **v3.0** (2025-11-11): Major update - Added Advanced Tests 23, 25-29 (configuration validation, concurrency, security, performance, integration). Total: 28 tests (~5.5 hours)
- **v2.0** (2025-11-11): Major update - Added Tests 13-17 documentation, added Gap Tests 18-22, updated all test counts, added Makefile targets
- **v1.1** (2025-11-05): Added reference to complete automated test suite (16 tests)
- **v1.0** (2025-01-27): Initial manual testing guide with 12 key tests
