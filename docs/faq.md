# TVM Upload System - Frequently Asked Questions (FAQ)

This document answers common questions about the TVM Log Upload System's behavior, settings, and policies.

---

## Table of Contents

1. [Upload Scheduling & Timing](#upload-scheduling--timing)
2. [Batch Upload Settings](#batch-upload-settings)
3. [File Age & Queue Management](#file-age--queue-management)
4. [Deletion Policies](#deletion-policies)
5. [Queue and Deletion Interaction](#queue-and-deletion-interaction)
6. [Testing & Validation](#testing--validation)
7. [Quick Reference Tables](#quick-reference-tables)

---

## Upload Scheduling & Timing

### Q1: Are scheduled uploads independent of operational hours?

**Answer:** YES, scheduled uploads are completely independent of operational hours.

**Explanation:**
- **Operational hours** only control **immediate uploads** (when files become ready)
- **Scheduled uploads** (interval/daily) run at their configured times **regardless of operational hours**
- Files queued outside operational hours will be uploaded at the next scheduled time

**Example:**
```yaml
operational_hours:
  enabled: true
  start: "09:00"
  end: "18:00"

schedule:
  mode: "interval"
  interval_hours: 0
  interval_minutes: 10  # Every 10 minutes
```

**Timeline:**
```
12:00 PM - File becomes ready
         → Within operational hours (09:00-18:00)
         → UPLOADS IMMEDIATELY ✓

07:00 PM - File becomes ready
         → Outside operational hours
         → QUEUED (not uploaded) ✓
         → Waits in queue

07:10 PM - 10-minute interval reached
         → Scheduled upload triggered
         → UPLOADS queued file ✓ (ignores operational hours)

07:20 PM - Next scheduled upload
         → Another upload ✓ (ignores operational hours)
```

**Key Point:** Scheduled uploads ensure files eventually get uploaded even if they're queued outside operational hours.

---

### Q2: Does operational hours check happen during testing?

**Answer:** YES, and it can cause tests to fail if run outside operational hours.

**Problem:**
When running manual tests after 6:00 PM (if operational hours end at 18:00), files become ready but are queued instead of uploaded, causing test failures.

**Solution:**
All upload-dependent manual tests now include an operational hours check that displays ERROR-level warnings:

```
⚠️  WARNING: OUTSIDE OPERATIONAL HOURS ⚠️
⚠️  Current time: 18:30
⚠️  Operational hours: 09:00 - 18:00 (enabled: true)
⚠️  FILES WILL BE QUEUED BUT NOT UPLOADED UNTIL 09:00
⚠️  This test may FAIL if it expects immediate uploads
⚠️  Solution: Run test during operational hours OR disable operational_hours in config
```

**Tests with operational hours check:**
- Test 01 - Startup Scan
- Test 02 - Source Detection
- Test 03 - File Date Preservation
- Test 06 - Duplicate Prevention
- Test 08 - Batch Upload Performance
- Test 09 - Large File Upload
- Test 12 - Service Restart Resilience
- Test 13 - Pattern Matching
- Test 14 - Recursive Monitoring
- Test 15 - Basic File Upload

---

## Batch Upload Settings

### Q3: Does `batch_upload` setting apply to scheduled and startup uploads?

**Answer:** NO, `batch_upload` **ONLY** applies to immediate uploads (when files become ready).

**Explanation:**
The `batch_upload` setting controls behavior only when an individual file becomes ready for upload during operational hours. Scheduled uploads and startup uploads **ALWAYS** process the entire queue, regardless of this setting.

**Settings Breakdown:**

| Upload Type | Respects `batch_upload`? | Always Uploads Entire Queue? |
|-------------|-------------------------|------------------------------|
| **Immediate** (file becomes ready) | ✅ YES | Depends on setting |
| **Scheduled** (interval/daily) | ❌ NO | ✅ YES (always) |
| **Startup** (`upload_on_start`) | ❌ NO | ✅ YES (always) |

**Examples:**

#### With `batch_upload: enabled: true`
```
09:00 - Scheduled upload runs
      → Uploads 10 files from queue
      → 2 files fail (remain in queue)

10:05 - New file becomes ready
      → Within operational hours
      → batch_upload=true
      → Uploads new file + 2 failed files (entire queue) ✓
```

#### With `batch_upload: enabled: false`
```
09:00 - Scheduled upload runs
      → Uploads 10 files from queue (entire queue) ✓
      → 2 files fail (remain in queue)

10:05 - New file becomes ready
      → Within operational hours
      → batch_upload=false
      → Uploads ONLY the new file (2 failed files wait) ✓

11:00 - Next scheduled upload
      → Uploads 2 failed files (entire queue) ✓
```

**Key Point:** Scheduled uploads at 09:00, 11:00, 13:00, etc. will **ALWAYS** upload the entire queue, regardless of `batch_upload` setting.

**Rationale:**
- **Immediate uploads** = reactive (triggered by file becoming ready)
  - `batch_upload=true` → Upload entire queue when ONE file ready
  - `batch_upload=false` → Upload ONLY that one file
- **Scheduled uploads** = proactive (run at specific times)
  - Should ALWAYS process entire queue (that's the whole point!)
- **Startup uploads** = recovery (process queue after restart)
  - Should ALWAYS process entire queue (clear backlog)

---

## File Age & Queue Management

### Q4: If a file is in the queue and becomes more than 3 days old, will it still get uploaded?

**Answer:** YES, files already in the queue will be uploaded **regardless of age**.

**Explanation:**
The `scan_existing_files.max_age_days` setting **ONLY** applies to the startup scan when the service starts/restarts. It does NOT affect files already in the queue.

**Setting:**
```yaml
scan_existing_files:
  enabled: true
  max_age_days: 3  # Only applies to startup scan
```

**What This Setting Controls:**

| Situation | Will File Upload? | Reason |
|-----------|------------------|---------|
| File detected while service running | ✅ YES | Added to queue immediately |
| File already in queue, becomes 4+ days old | ✅ YES | Queue doesn't care about age |
| Service restarts, finds 2-day-old file on disk | ✅ YES | Within max_age_days (3) |
| Service restarts, finds 4-day-old file on disk | ❌ NO | Exceeds max_age_days (3), skipped |
| 4-day-old file manually added to queue | ✅ YES | Once in queue, age doesn't matter |

**Example Timeline:**
```
Day 1, 10:00 AM - File created
Day 1, 10:01 AM - File detected by service
                → Added to queue immediately ✓

Day 1, 10:02 AM - Upload attempt fails (network issue)
                → Remains in queue

Day 2, 11:00 AM - Scheduled upload attempts
                → Fails again
                → Remains in queue

Day 3, 11:00 AM - Scheduled upload attempts
                → Fails again
                → Remains in queue

Day 4, 11:00 AM - File is now 3+ days old
                → Scheduled upload runs
                → File IS in queue
                → File WILL BE UPLOADED ✓
                → Age doesn't matter for queued files
```

**Startup Scan Example:**
```
SERVICE RESTARTS at 10:00 AM on Day 5

Startup scan finds these files on disk:
├─ file1.log (2 days old) → ✅ Added to queue (< 3 days)
├─ file2.log (3 days old) → ✅ Added to queue (= 3 days, inclusive)
├─ file3.log (4 days old) → ❌ SKIPPED (> 3 days, not in queue)
├─ file4.log (10 days old) → ❌ SKIPPED (> 3 days, not in queue)

Files already in queue.json:
├─ file5.log (5 days old) → ✅ Will be uploaded (already in queue)
└─ file6.log (8 days old) → ✅ Will be uploaded (already in queue)
```

**Why This Design Makes Sense:**
1. **Startup scan filter** prevents uploading ancient log files on first startup
2. **Queue persistence** ensures files that failed to upload won't be abandoned just because they got old
3. **Retry logic** keeps trying to upload queued files until they succeed

**If You Want to Delete Old Queued Files:**
Use the age-based deletion policy:
```yaml
deletion:
  age_based:
    enabled: true
    max_age_days: 14  # Delete ANY file older than 14 days (even if in queue)
    schedule_time: "02:00"
```

---

## Deletion Policies

### Q5: What's the difference between "after_upload" deletion and "age_based" deletion?

**Answer:** They are **two different deletion policies** that serve different purposes and can conflict if misconfigured.

### Comparison Table

| Feature | After Upload | Age-Based |
|---------|-------------|-----------|
| **Trigger** | Successful upload | File age (days since creation) |
| **Considers upload status?** | ✅ YES - only uploaded files | ❌ NO - all files |
| **Purpose** | Clean up uploaded files | Safety net for old files |
| **When runs** | Immediately after upload | Daily at scheduled time (02:00) |
| **Deletes failed uploads?** | ❌ NO | ✅ YES |
| **Deletes unuploaded files?** | ❌ NO | ✅ YES |
| **Deletes uploaded files?** | ✅ YES (after keep_days) | ✅ YES (after max_age_days) |

### 1. DELETE AFTER UPLOAD (`deletion.after_upload`)

**Triggers:** After a file is **successfully uploaded** to S3

**Purpose:** Control how long to keep files **after they've been uploaded**

**Settings:**
```yaml
deletion:
  after_upload:
    enabled: true
    keep_days: 7  # Keep for 7 days after upload, then delete
```

**Options:**
- `keep_days: 0` → Delete **immediately** after upload
- `keep_days: 7` → Keep for **7 days** after upload, then delete
- `enabled: false` → Keep uploaded files **indefinitely**

**Example Timeline:**
```
Day 1, 10:00 AM - File uploaded successfully
Day 1, 10:00 AM - If keep_days=0: Delete immediately ✓
Day 8, 10:00 AM - If keep_days=7: Delete now (7 days later) ✓
```

**Use Cases:**
- Save disk space by removing uploaded files
- Keep files locally for debugging/verification period
- Clean up successfully processed files

### 2. AGE-BASED CLEANUP (`deletion.age_based`)

**Triggers:** Files older than `max_age_days`, **regardless of upload status**

**Purpose:** Safety net to prevent **old files from accumulating forever**

**Settings:**
```yaml
deletion:
  age_based:
    enabled: true
    max_age_days: 14  # Delete files older than 14 days (from file creation/modification)
    schedule_time: "02:00"  # Run daily at 2:00 AM
```

**Example Timeline:**
```
Day 1 - File created
Day 2 - Upload fails (file stays in queue)
Day 3 - Upload fails again
Day 4 - Upload fails again
...
Day 15 - Age-based cleanup runs at 02:00 AM
       → File is 14+ days old
       → File is DELETED (even though it never uploaded) ✓
```

**Use Cases:**
- Delete **failed uploads** that are too old
- Delete **orphaned files** that never got uploaded
- Prevent disk from filling up with very old files

### Configuration Conflict Warning

**⚠️ AVOID THIS Configuration:**
```yaml
deletion:
  after_upload:
    enabled: true
    keep_days: 14  # Keep uploaded files for 2 weeks

  age_based:
    enabled: true
    max_age_days: 7  # Delete ANY file older than 7 days
```

**Why This is a Problem:**
```
Day 1 - File uploaded successfully
      → Should be kept until Day 15 (keep_days=14)

Day 8 - Age-based cleanup runs
      → File is 7+ days old
      → File is DELETED ❌ (before 14-day retention period!)
```

**⚠️ CONFLICT:** When `max_age_days < keep_days`, age-based cleanup deletes uploaded files before the retention period expires!

### ✅ CORRECT Configuration

**Recommendation:** `max_age_days` should be **greater than** `keep_days`

```yaml
deletion:
  after_upload:
    enabled: true
    keep_days: 7  # Keep uploaded files for 1 week

  age_based:
    enabled: true
    max_age_days: 14  # Delete ANY file older than 14 days
    schedule_time: "02:00"
```

**Why This Works:**
```
Day 1 - File uploaded successfully

Day 8 - After-upload deletion runs
      → File is 7+ days post-upload
      → File is DELETED ✓ (uploaded files cleaned up)

Failed Upload Scenario:
Day 1 - File created
Day 2-14 - Upload keeps failing
Day 15 - Age-based cleanup runs
       → File is 14+ days old
       → File is DELETED ✓ (failed uploads cleaned up)
```

**Benefits:**
- Uploaded files deleted on Day 8 (keep_days=7)
- Failed/orphaned files deleted on Day 15 (max_age_days=14)
- No conflict between policies!
- Reasonable retention periods for debugging while saving disk space

### Summary of Deletion Policies

**Three deletion triggers:**

1. **After Upload** (`deletion.after_upload`)
   - Deletes files N days after successful upload
   - Only affects uploaded files
   - Runs immediately after upload (keeps for keep_days, then deletes)

2. **Age-Based** (`deletion.age_based`)
   - Deletes ALL files older than N days (uploaded or not)
   - Safety net for failed uploads and orphaned files
   - Runs daily at scheduled time

3. **Emergency** (`deletion.emergency`)
   - Deletes oldest uploaded files when disk is critically full
   - Last resort to prevent system failure
   - Runs automatically when disk usage > 95%

**Best Practice:**
- Use **after_upload** for normal cleanup of uploaded files
- Use **age_based** as a safety net with `max_age_days > keep_days`
- Enable **emergency** as a last resort

---

## Queue and Deletion Interaction

### Q6: What happens if a file in the queue gets deleted by the deletion policy?

**Answer:** The file is **gracefully removed from the queue** at the next upload attempt or system restart. No errors occur, and no duplicate uploads happen.

**Explanation:**

The system has **five layers of file existence checking** that ensure deleted files are handled safely:

**Five-Layer Protection:**

1. **Startup Cleanup** (`queue_manager.py:426-441`)
   - When service starts, `_cleanup_missing_files()` removes non-existent files from queue
   - Prevents attempting to upload files that disappeared while service was stopped

2. **Batch Retrieval Check** (`queue_manager.py:154-169`)
   - Before creating upload batch, `get_next_batch()` verifies file existence
   - Skips missing files automatically

3. **Upload Time Check** (`main.py:703-738`)
   - `_upload_file()` checks if file exists before starting upload
   - Returns early if file missing (no error raised)

4. **Upload Start Check** (`s3_uploader.py:88-133`)
   - `upload_file()` verifies file exists before opening
   - Raises FileNotFoundError if missing

5. **During Upload Catch** (`main.py:750-758`)
   - FileNotFoundError caught as **PERMANENT** error
   - File **removed from queue** immediately
   - File **removed from registry** (prevents duplicate uploads)

**Timeline Example:**

```
Day 1, 10:00 AM - File added to queue
                → upload_queue.json: ["file1.log"]
                → Scheduled for upload

Day 1, 10:05 AM - Upload attempt #1 fails (network issue)
                → File stays in queue
                → Will retry later

Day 3, 02:00 AM - Age-based deletion runs
                → File is 2+ days old
                → File DELETED from disk ✓
                → Queue still has entry: ["file1.log"]

Day 3, 09:00 AM - Scheduled upload runs
                → get_next_batch() checks file existence
                → File NOT found on disk
                → _upload_file() returns early
                → File REMOVED from queue ✓
                → upload_queue.json: []

Result: Clean queue, no errors, no duplicate uploads ✓
```

**What Gets Cleaned Up:**

When a queued file is deleted:

1. **Queue Entry** - Removed from `queue.json` at next upload attempt
2. **Registry Entry** - Removed from `processed_files.json` (allows re-upload if file recreated)
3. **Uploaded Files Tracking** - Entry removed from `disk_manager.uploaded_files` if it was uploaded
4. **No Error Logs** - File existence check happens before error, so no exceptions raised

**Startup Cleanup Example:**

```
SERVICE STOPS at 10:00 PM

During downtime:
├─ Age-based deletion runs at 02:00 AM
├─ Deletes: file1.log, file2.log (old files)
└─ Queue still has: ["file1.log", "file2.log", "file3.log"]

SERVICE STARTS at 08:00 AM
├─ _cleanup_missing_files() runs automatically
├─ Checks: file1.log ❌ missing
├─ Checks: file2.log ❌ missing
├─ Checks: file3.log ✅ exists
└─ Queue cleaned: ["file3.log"]

Result: Queue reflects actual disk state ✓
```

**Error Handling Categories:**

| Error Type | Cause | Queue Action | Registry Action |
|------------|-------|--------------|-----------------|
| **FileNotFoundError** | Deleted by policy or manually | ✅ Remove from queue | ✅ Remove from registry |
| **PermissionError** | File permissions changed | ✅ Remove from queue | ✅ Remove from registry |
| **OSError** | Disk corruption, I/O error | ✅ Remove from queue | ✅ Remove from registry |
| **NetworkError** | Upload failed (temporary) | ⏸️ Keep in queue | ⏸️ Keep in registry |
| **S3 Error** | AWS issue (temporary) | ⏸️ Keep in queue | ⏸️ Keep in registry |

**Why This Design Works:**

1. **Permanent vs Temporary Errors** (`main.py:750-758`)
   - File not found = PERMANENT → Remove from queue
   - Network issue = TEMPORARY → Keep in queue and retry

2. **Graceful Degradation**
   - No crashes or exceptions when files disappear
   - Queue self-heals at multiple points
   - Registry prevents duplicate uploads

3. **Atomic Queue Updates** (`queue_manager.py:314-351`)
   - Queue writes are atomic with backup
   - If corruption occurs, restores from `queue.json.bak`
   - Never loses queue state

**Configuration Impact:**

The interaction between queue and deletion depends on your configuration:

```yaml
deletion:
  after_upload:
    enabled: true
    keep_days: 7        # Uploaded files kept 7 days

  age_based:
    enabled: true
    max_age_days: 14    # ALL files deleted after 14 days
```

**Scenario 1: Upload succeeds before deletion**
```
Day 1 - File uploaded
Day 8 - After-upload deletion (7 days) → File deleted
      → File already uploaded, so queue entry already removed ✓
```

**Scenario 2: Upload fails repeatedly, then deletion**
```
Day 1-14 - Upload attempts fail (file stays in queue)
Day 15   - Age-based deletion → File deleted
Day 15   - Next upload attempt → File missing
         → Removed from queue gracefully ✓
         → Removed from registry ✓
         → Allows re-upload if file recreated
```

**Scenario 3: Service restart after deletion**
```
Service stopped
├─ Queue has: ["old_file.log"] (failed to upload)
├─ Deletion runs while service down
└─ File deleted from disk

Service starts
├─ _cleanup_missing_files() runs
├─ Detects "old_file.log" missing
└─ Removes from queue ✓
```

**Key Takeaways:**

✅ **Safe:** No errors when deletion removes queued files
✅ **Clean:** Queue automatically reflects disk state
✅ **Smart:** Distinguishes permanent (file missing) from temporary (network) errors
✅ **Resilient:** Five-layer checking ensures no edge cases
✅ **No Duplicates:** Registry cleanup prevents re-uploading deleted files

**Related Code Locations:**

- Queue startup cleanup: `src/queue_manager.py:426-441`
- Batch file existence check: `src/queue_manager.py:154-169`
- Upload file check: `src/main.py:703-738`
- Error handling: `src/main.py:750-758`
- Deletion policies: `src/disk_manager.py:107-487`

**For More Details:**

See the comprehensive analysis documents in the `/docs` folder:
- `queue_deletion_quick_reference.md` - Operational guide with diagrams
- `queue_deletion_analysis.md` - Complete technical deep-dive

---

## Testing & Validation

### Q7: Has CloudWatch functionality been tested in manual test cases, unit tests, integration tests, and E2E tests?

**Answer:** YES, CloudWatch functionality (`cloudwatch_enabled: true`) has been **comprehensively tested** across all test suites with **67+ total tests** and **~1,583 lines** of CloudWatch-specific test code.

**Test Coverage Summary:**

| Test Type | Location | Tests | Lines | Real AWS? | Status |
|-----------|----------|-------|-------|-----------|--------|
| **Manual** | `scripts/testing/manual-tests/` | 2 dedicated + 5 integrated | N/A | ✅ YES | ✅ Comprehensive |
| **Unit** | `tests/unit/test_cloudwatch.py` | ~40 methods | 602 lines | ❌ Mocked | ✅ Comprehensive |
| **Integration** | `tests/integration/` | 3+ tests | Distributed | ❌ Mocked | ✅ Covered |
| **E2E** | `tests/e2e/test_cloudwatch_real.py` | 25 tests | 981 lines | ✅ YES | ✅ Comprehensive |

---

### 1. Manual Test Cases (Shell Scripts)

**Location:** `scripts/testing/manual-tests/`

**Dedicated CloudWatch Tests:**

**Test 04: CloudWatch Metrics Publishing** (`04_cloudwatch_metrics.sh`)
- Verifies metrics are published to real AWS CloudWatch
- Tests metric aggregation (uploads 5 files)
- Validates metrics appear in CloudWatch console
- Waits for metric propagation
- Duration: ~10 minutes

**Test 05: CloudWatch Alarm Creation** (`05_cloudwatch_alarms.sh`)
- Verifies automatic alarm creation for low upload volume
- Tests alarm configuration (name, threshold, state)
- Validates alarm exists in AWS CloudWatch
- Duration: ~5 minutes

**Tests with CloudWatch Integration:**
- Tests 01, 13, 14, 16, 17 reference CloudWatch in their configuration
- All tests verify system works with CloudWatch enabled

**How to Run:**
```bash
# Run all manual tests (including CloudWatch tests)
./scripts/testing/run_manual_tests.sh

# Run specific CloudWatch test
./scripts/testing/manual-tests/04_cloudwatch_metrics.sh config/config.yaml test-vehicle-001
./scripts/testing/manual-tests/05_cloudwatch_alarms.sh config/config.yaml test-vehicle-001
```

---

### 2. Unit Tests

**Location:** `tests/unit/test_cloudwatch.py`

**Coverage:** 602 lines, ~40 test methods

**Test Categories:**

**A. Initialization & Configuration**
- `test_init_disabled()` - CloudWatch manager in disabled mode
- `test_init_enabled()` - CloudWatch manager with real AWS client (mocked)

**B. Metric Recording**
- `test_record_upload_success()` - Records successful upload with file size
- `test_record_upload_failure()` - Records upload failures
- `test_multiple_uploads_before_publish()` - Metric accumulation

**C. Metric Publishing**
- `test_publish_metrics()` - Publishing to CloudWatch (mocked boto3)
- `test_publish_metrics_disabled()` - No-op when disabled
- `test_metrics_reset_after_publish()` - Counters reset after successful publish

**D. Metric Types**
- Bytes uploaded (MB)
- File count (successful uploads)
- Failure count
- Disk usage percentage
- Queue depth
- Deletion counts

**E. Edge Cases**
- Zero values
- Very large values
- Rapid successive calls
- Error handling (AWS API failures)

**How to Run:**
```bash
# Run all CloudWatch unit tests
pytest tests/unit/test_cloudwatch.py -v

# Run specific test
pytest tests/unit/test_cloudwatch.py::TestCloudWatchManager::test_publish_metrics -v
```

---

### 3. Integration Tests

**Location:** `tests/integration/`

**CloudWatch Integration Tests:**

**test_main.py:639** - `test_cloudwatch_metrics_integration()`
- Tests CloudWatch metrics recorded during actual uploads
- Verifies `record_upload_success()` called with correct file size
- Mocks upload to S3, but tests real metric recording flow

**test_end_to_end.py:1132** - `test_cloudwatch_disabled()`
- Tests system works correctly when CloudWatch is disabled
- Ensures no errors when CloudWatch unavailable
- Validates graceful degradation

**Integration Approach:**
- All tests use `@patch('src.cloudwatch_manager.boto3.session.Session')`
- Mock CloudWatch client to avoid real AWS calls during CI/CD
- Set `cloudwatch_enabled: false` in test configs for faster tests
- Verify system works with CloudWatch both enabled and disabled

**How to Run:**
```bash
# Run all integration tests
pytest tests/integration/ -v

# Run specific CloudWatch integration test
pytest tests/integration/test_main.py::TestTVMUploadSystem::test_cloudwatch_metrics_integration -v
```

---

### 4. E2E (End-to-End) Tests with Real AWS

**Location:** `tests/e2e/test_cloudwatch_real.py`

**Coverage:** 981 lines, 25 comprehensive test functions using **REAL AWS CloudWatch**

**Test Categories:**

**A. Metric Publishing (6 tests)**
1. `test_publish_metrics_to_real_cloudwatch()` - Basic publishing
2. `test_publish_all_metric_types()` - All metric types
3. `test_publish_metrics_with_no_data()` - Empty metrics
4. `test_publish_deletion_metrics()` - Deletion metrics
5. `test_publish_queue_metrics()` - Queue depth metrics
6. `test_publish_zero_bytes_uploaded()` - Zero-value handling

**B. Alarm Management (5 tests)**
7. `test_cloudwatch_alarm_creation()` - Create and verify alarms
8. `test_alarm_with_different_thresholds()` - Multiple alarm configs
9. `test_alarm_state_verification()` - Monitor alarm states
10. `test_alarm_update_scenario()` - Update existing alarms
11. `test_alarm_creation_with_invalid_parameters()` - Error handling

**C. Error Handling (3 tests)**
12. `test_publish_metrics_with_api_error_simulation()` - API failures
13. `test_metrics_accumulate_after_publish_error()` - Metric persistence
14. `test_cloudwatch_disabled_mode()` - Disabled mode behavior

**D. Performance & Scale (6 tests)**
15. `test_extreme_disk_usage_values()` - Edge values (0%, 100%)
16. `test_very_large_upload_metrics()` - Large files (100GB simulation)
17. `test_many_small_uploads()` - High frequency (100 files)
18. `test_high_frequency_metric_publishing()` - Rapid publishing (10 cycles)
19. `test_rapid_successive_publishes()` - Back-to-back publishes
20. `test_sustained_metric_accumulation()` - Long-term accumulation

**E. Multi-Vehicle & Isolation (2 tests)**
21. `test_multi_vehicle_metrics_isolation()` - Multiple vehicle IDs
22. `test_mixed_success_and_failure_ratios()` - Success/failure scenarios

**F. System Integration (3 tests)**
23. `test_complete_monitoring_cycle()` - Full upload → metrics → alarm
24. `test_metric_dimensions_verification()` - Dimension correctness
25. `test_namespace_verification()` - Namespace (TVM/Upload)

**Prerequisites for E2E Tests:**
- Valid AWS credentials configured
- CloudWatch permissions (PutMetricData, DescribeAlarms, PutMetricAlarm)
- Test runs against **real AWS CloudWatch**

**How to Run:**
```bash
# Run all E2E CloudWatch tests (requires AWS credentials)
pytest tests/e2e/test_cloudwatch_real.py -v

# Run specific E2E test
pytest tests/e2e/test_cloudwatch_real.py::test_publish_metrics_to_real_cloudwatch -v

# Skip E2E tests (use in CI/CD without AWS access)
pytest tests/ -v -m "not e2e"
```

---

### Feature Coverage Matrix

**CloudWatch Features Tested:**

| Feature | Unit | Integration | E2E | Manual |
|---------|------|-------------|-----|--------|
| **Metric Publishing** | ✅ | ✅ | ✅ | ✅ |
| **Alarm Creation** | ✅ | ✅ | ✅ | ✅ |
| **Alarm State Monitoring** | ✅ | ❌ | ✅ | ✅ |
| **Metric Aggregation** | ✅ | ✅ | ✅ | ✅ |
| **Disabled Mode** | ✅ | ✅ | ✅ | N/A |
| **Error Handling (AWS API)** | ✅ | ✅ | ✅ | ✅ |
| **Multi-Vehicle Isolation** | ✅ | ❌ | ✅ | ❌ |
| **High-Frequency Publishing** | ✅ | ❌ | ✅ | ❌ |
| **Large File Metrics** | ✅ | ❌ | ✅ | ✅ |
| **Namespace Verification** | ✅ | ❌ | ✅ | ✅ |
| **Queue Depth Metrics** | ✅ | ❌ | ✅ | ❌ |
| **Deletion Metrics** | ✅ | ❌ | ✅ | ❌ |

---

### Test Execution Summary

**Local Development:**
```bash
# Fast feedback (unit + integration, mocked CloudWatch)
pytest tests/unit/ tests/integration/ -v

# Full validation (including E2E with real AWS)
pytest tests/ -v
```

**CI/CD Pipeline:**
```bash
# Unit and integration tests (no AWS required)
pytest tests/unit/ tests/integration/ -v --tb=short

# E2E tests (requires AWS credentials in CI)
pytest tests/e2e/ -v --tb=short
```

**Manual Testing:**
```bash
# Run all manual tests (real system, real AWS)
./scripts/testing/run_manual_tests.sh

# Run only CloudWatch manual tests
./scripts/testing/manual-tests/04_cloudwatch_metrics.sh config/config.yaml test-vehicle
./scripts/testing/manual-tests/05_cloudwatch_alarms.sh config/config.yaml test-vehicle
```

---

### Verification Checklist

Before deploying to production, verify CloudWatch functionality:

- [ ] **Unit tests pass** (`pytest tests/unit/test_cloudwatch.py`)
- [ ] **Integration tests pass** (`pytest tests/integration/`)
- [ ] **E2E tests pass** (`pytest tests/e2e/test_cloudwatch_real.py`)
- [ ] **Manual Test 04 passes** (metrics visible in CloudWatch console)
- [ ] **Manual Test 05 passes** (alarm created and visible)
- [ ] **Real metrics appear in CloudWatch** (check AWS console after upload)
- [ ] **Alarms trigger correctly** (test with low upload volume)

---

### Key Takeaways

✅ **Comprehensive Coverage:** 67+ tests across all test types
✅ **Real AWS Testing:** Manual and E2E tests validate against real CloudWatch
✅ **Mocked Testing:** Unit/integration tests for fast CI/CD
✅ **Edge Cases Covered:** Disabled mode, errors, extreme values, high frequency
✅ **Performance Tested:** Large files, many small files, sustained load
✅ **Production Ready:** Test coverage suitable for real-world deployment

**CloudWatch implementation has production-ready test coverage.**

---

## Quick Reference Tables

### Upload Types & Batch Setting

| Upload Type | Trigger | Respects batch_upload? | Respects operational_hours? |
|-------------|---------|----------------------|----------------------------|
| **Immediate Upload** | File becomes ready | ✅ YES | ✅ YES |
| **Scheduled Upload** (interval) | Time interval reached | ❌ NO (always batch) | ❌ NO (always runs) |
| **Scheduled Upload** (daily) | Daily time reached | ❌ NO (always batch) | ❌ NO (always runs) |
| **Startup Upload** | Service starts | ❌ NO (always batch) | ❌ NO (always runs) |

### File Age & Queue Behavior

| Scenario | Added to Queue? | Will Upload? | Reason |
|----------|----------------|-------------|---------|
| File detected while service running | ✅ YES | ✅ YES | Normal operation |
| File in queue becomes 5+ days old | N/A (already in) | ✅ YES | Queue ignores age |
| Service restarts, finds 2-day-old file (max_age=3) | ✅ YES | ✅ YES | Within scan threshold |
| Service restarts, finds 5-day-old file (max_age=3) | ❌ NO | ❌ NO | Exceeds scan threshold |
| File already in queue at restart | N/A (persisted) | ✅ YES | Queue survives restart |

### Deletion Policy Comparison

| Policy | Trigger | Uploaded Files | Failed Uploads | Unuploaded Files |
|--------|---------|---------------|---------------|------------------|
| **After Upload** | Successful upload | ✅ Deletes after keep_days | ❌ Never | ❌ Never |
| **Age-Based** | File age | ✅ Deletes after max_age_days | ✅ Deletes after max_age_days | ✅ Deletes after max_age_days |
| **Emergency** | Disk >95% full | ✅ Deletes oldest | ❌ Never | ❌ Never |

### Configuration Validation Rules

| Setting | Rule | Valid Example | Invalid Example |
|---------|------|--------------|-----------------|
| `keep_days` vs `max_age_days` | max_age_days > keep_days | keep:14, max:30 ✅ | keep:14, max:7 ❌ |
| `operational_hours` | start < end | 09:00-18:00 ✅ | 18:00-09:00 ❌ |
| `scan_existing_files.max_age_days` | >= 0 | 3 ✅ | -1 ❌ |
| `interval_hours + interval_minutes` | > 0 | 0h 10m ✅ | 0h 0m ❌ |

### Operational Hours Behavior

| Time | File Becomes Ready | Scheduled Upload | Startup Upload |
|------|-------------------|------------------|----------------|
| **Within hours** (09:00-18:00) | ✅ Uploads immediately | ✅ Runs (uploads queue) | ✅ Runs (uploads queue) |
| **Outside hours** (18:01-08:59) | ⏸️ Queued for later | ✅ Runs (uploads queue) | ✅ Runs (uploads queue) |

---

## Related Documentation

- [Configuration Reference](configuration_reference.md) - Detailed configuration options
- [Complete Reference](complete_reference.md) - Full system documentation
- [Testing Guide](manual_testing_guide.md) - Manual testing procedures
- [Queue Deletion Quick Reference](queue_deletion_quick_reference.md) - Queue and deletion interaction guide
- [Queue Deletion Analysis](queue_deletion_analysis.md) - Technical deep-dive

---

## Version History

- **v1.2** (2025-01-07) - Added testing & validation section
  - Q7: Has CloudWatch functionality been tested across all test suites?
  - Comprehensive test coverage documentation (67+ tests, ~1,583 lines)
  - Manual, unit, integration, and E2E test descriptions
  - Feature coverage matrix
  - Test execution commands and verification checklist

- **v1.1** (2025-01-07) - Added queue and deletion interaction
  - Q6: What happens if a file in the queue gets deleted by the deletion policy?
  - Five-layer file existence checking explanation
  - Error handling categories
  - Configuration impact scenarios
  - Updated deletion policy values (keep_days: 7, max_age_days: 14)

- **v1.0** (2025-01-07) - Initial FAQ document
  - Upload scheduling & operational hours
  - Batch upload settings clarification
  - File age & queue management
  - Deletion policies comparison

---

**Last Updated:** 2025-01-07
**Document Version:** 1.2
