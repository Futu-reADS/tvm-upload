# Gap Coverage Test Suite

## Overview

This test suite contains **5 additional manual tests** that cover configuration features and scenarios not fully tested in the original 16 manual tests (located in `scripts/testing/manual-tests/`).

These tests were created to address coverage gaps identified in the test coverage analysis (see `docs/MANUAL_TEST_COVERAGE_REPORT.md`).

---

## Test Suite Contents

| Test # | Test Name | Duration | What It Tests |
|--------|-----------|----------|---------------|
| 17 | Environment Variable Path Expansion | ~5 min | Verifies `${HOME}`, `${USER}`, `~` in log_directories paths |
| 18 | All 4 Log Sources Simultaneously | ~10 min | Tests terminal, ros, syslog, ros2 working together without interference |
| 19 | Deferred Deletion (keep_days > 0) | ~3 min | Verifies files kept for N days after upload before deletion |
| 20 | Queue Recovery After Crash | ~5 min | Tests queue survives crash (kill -9) and recovers |
| 21 | Registry Cleanup After Retention Days | ~5 min | Verifies old registry entries removed after retention_days |

**Total Duration:** ~30 minutes

---

## Key Features

### Isolated S3 Testing
Each test creates a **unique S3 folder** with timestamp to avoid interference:
- **Format:** `{vehicle_id}-TEST{number}-{timestamp}/`
- **Example:** `vehicle-CN-GAP-TEST17-20251030-143022/`
- **Cleanup:** Each test cleans its own S3 folder after completion

### Quick Testing with Workarounds
Some tests use workarounds to avoid long wait times:
- **Test 19 (Deferred Deletion):** Uses `keep_days=0.001` (~90 seconds) instead of 14 days
- **Test 21 (Registry Cleanup):** Manually seeds old registry entries instead of waiting 30 days

### No Restrictions
All tests in this suite are **fully automated** and have **no restrictions**:
- ✅ No root access required
- ✅ No network simulation
- ✅ No manual intervention
- ✅ No time-based delays (beyond upload stability periods)
- ✅ No external dependencies

---

## Quick Start

### Run All Gap Tests
```bash
# From project root
cd scripts/testing/gap-tests
./run_gap_tests.sh

# Or with custom config
./run_gap_tests.sh path/to/config.yaml vehicle-CN-TEST
```

### Run Individual Test
```bash
# Example: Run only Test 17
./17_env_var_expansion.sh config/config.yaml vehicle-CN-TEST
```

---

## Prerequisites

### Required
1. **AWS Credentials** configured with China profile:
   ```bash
   ~/.aws/credentials
   ~/.aws/config
   ```

2. **S3 Bucket** accessible in `cn-north-1` or `cn-northwest-1`

3. **Config File** at `config/config.yaml` (or provide path as argument)

4. **Python Environment** with TVM upload system installed:
   ```bash
   pip install -e ".[test]"
   ```

5. **Test Helpers** library:
   - Located at `scripts/lib/test_helpers.sh`
   - Automatically sourced by each test

### Optional
- **Base Vehicle ID:** Defaults to `vehicle-CN-GAP` if not provided

---

## Test Details

### Test 17: Environment Variable Path Expansion

**Purpose:** Verify that environment variables in `log_directories` paths are expanded correctly.

**Tests:**
- `${HOME}/path` → Expands to `/home/username/path`
- `/tmp/user-${USER}/path` → Expands to `/tmp/user-username/path`
- `~/path` → Expands to `/home/username/path` (tilde expansion)
- Absolute paths work as control (no expansion needed)

**Config Example:**
```yaml
log_directories:
  - path: ${HOME}/tvm-test/terminal
    source: terminal
  - path: /tmp/user-${USER}/ros
    source: ros
  - path: ~/logs/syslog
    source: syslog
```

**Expected Result:** All files upload to correct S3 paths regardless of env var usage

---

### Test 18: All 4 Log Sources Simultaneously

**Purpose:** Verify all 4 default log sources work together without interference.

**Tests:**
- **Terminal:** 2 files uploaded
- **ROS:** 4 files with nested structure (session1/, session2/subfolder/)
- **Syslog:** 2 files matching pattern `syslog*` (1 file filtered)
- **ROS2:** 2 files with nested structure
- **Total:** 10 files uploaded to 4 separate S3 source folders

**Features Tested:**
- Source-based organization
- Pattern matching (`syslog*`)
- Recursive monitoring (ROS, ROS2)
- Non-recursive monitoring (syslog)
- No interference between sources

**Expected Result:** All 4 sources create separate folders in S3 with correct files

---

### Test 19: Deferred Deletion (keep_days > 0)

**Purpose:** Verify files are kept for N days after upload before deletion.

**Tests:**
- Upload files with `keep_days=0.001` (~90 seconds)
- Verify files exist immediately after upload (deferred deletion)
- Wait 90 seconds
- Verify files deleted after keep_days period expires
- Compare with `keep_days=0` (immediate deletion)

**Config Example:**
```yaml
deletion:
  after_upload:
    enabled: true
    keep_days: 14  # Keep for 14 days (test uses 0.001 for speed)
```

**Expected Result:**
- Files kept locally during keep_days period
- Files deleted after period expires
- Files remain in S3 (deletion only affects local files)

**Note:** Test uses `keep_days=0.001` (~90 seconds) for quick testing. Production should use `keep_days=14` for 14-day retention.

---

### Test 20: Queue Recovery After Crash

**Purpose:** Verify queue survives crash (kill -9) and files upload after restart.

**Tests:**
- Create 3 files and wait for them to be queued
- Simulate crash with `kill -9` (SIGKILL)
- Verify queue file survives crash
- Restart service
- Verify all 3 files upload after recovery (no data loss)

**Config Example:**
```yaml
upload:
  queue_file: /var/lib/tvm-upload/queue.json  # Survives crashes
```

**Expected Result:**
- Queue file persists after crash
- All queued files upload after service restart
- No data loss

---

### Test 21: Registry Cleanup After Retention Days

**Purpose:** Verify old registry entries are removed after retention_days.

**Tests:**
- Manually seed registry with entries:
  - 50 days old (should be cleaned)
  - 35 days old (should be cleaned)
  - 1 day old (should be kept)
- Start service (triggers cleanup)
- Verify old entries removed
- Verify recent entries kept
- Upload new file and verify it's tracked

**Config Example:**
```yaml
upload:
  processed_files_registry:
    registry_file: /var/lib/tvm-upload/processed_files.json
    retention_days: 30  # Clean entries older than 30 days
```

**Expected Result:**
- Entries older than retention_days removed
- Recent entries kept
- New uploads tracked in registry

**Note:** Test uses manual seeding instead of waiting 30+ days.

---

## S3 Folder Management

### Folder Naming Convention
Each test creates a unique S3 folder:
```
s3://bucket/vehicle-CN-GAP-TEST17-20251030-143022/
s3://bucket/vehicle-CN-GAP-TEST18-20251030-143527/
s3://bucket/vehicle-CN-GAP-TEST19-20251030-144032/
...
```

### Automatic Cleanup
Each test cleans its own S3 folder at the end:
```bash
cleanup_test_s3_data "$VEHICLE_ID" "$S3_BUCKET" "$AWS_PROFILE" "$AWS_REGION" "$TODAY"
```

### Manual Cleanup (if needed)
If tests are interrupted, clean all test folders:
```bash
# List all test folders
aws s3 ls s3://bucket/ | grep TEST

# Delete specific test folder
aws s3 rm s3://bucket/vehicle-CN-GAP-TEST17-20251030-143022/ --recursive

# Delete all test folders (CAREFUL!)
aws s3 ls s3://bucket/ | grep TEST | awk '{print $2}' | while read folder; do
    aws s3 rm s3://bucket/$folder --recursive
done
```

---

## Interpreting Results

### Success (Exit Code 0)
```
✓ PASSED: Environment Variable Path Expansion
✓ PASSED: All 4 Log Sources Simultaneously
✓ PASSED: Deferred Deletion (keep_days > 0)
✓ PASSED: Queue Recovery After Crash
✓ PASSED: Registry Cleanup After Retention Days

╔════════════════════════════════════════════════════════════════╗
║          ALL GAP COVERAGE TESTS PASSED! ✓                      ║
╚════════════════════════════════════════════════════════════════╝

Success Rate: 100.0%
```

### Failure (Exit Code 1)
```
✗ FAILED: Queue Recovery After Crash

Passed: 4 / 5
Failed: 1 / 5
Success Rate: 80.0%

╔════════════════════════════════════════════════════════════════╗
║            SOME GAP COVERAGE TESTS FAILED ✗                    ║
╚════════════════════════════════════════════════════════════════╝
```

### Debugging Failed Tests
1. **Check service logs:** Each test creates `/tmp/tvm-service-gap{N}.log`
2. **Check test output:** Tests print detailed progress and error messages
3. **Check S3:** Verify files uploaded to expected paths
4. **Run individual test:** Run failing test alone for easier debugging

---

## Coverage Comparison

### Original 16 Tests (manual-tests/)
- ✅ Core functionality (upload, monitoring, deletion)
- ✅ Error handling and retry
- ✅ Operational hours and scheduling
- ✅ Service restart resilience
- ⚠️ Some features partially tested or not tested

### Gap Tests (gap-tests/)
- ✅ Environment variable path expansion
- ✅ All 4 sources simultaneously (comprehensive)
- ✅ Deferred deletion (keep_days > 0)
- ✅ Queue crash recovery (kill -9)
- ✅ Registry cleanup (retention_days)

### Combined Coverage
**Original Tests:** ~85%
**After Gap Tests:** ~95%

---

## Integration with Main Test Suite

These tests are **separate** from the main test suite but can be integrated later:

### Option 1: Keep Separate (Current)
```bash
# Run original tests
cd scripts/testing/manual-tests
./run_manual_tests.sh

# Run gap tests
cd scripts/testing/gap-tests
./run_gap_tests.sh
```

### Option 2: Merge Later
Copy gap tests to `manual-tests/` and renumber:
```bash
cp gap-tests/17_* manual-tests/
cp gap-tests/18_* manual-tests/
...
# Update run_manual_tests.sh to include tests 17-21
```

---

## Troubleshooting

### Test Hangs During Upload
- **Cause:** File stability period (60 seconds by default)
- **Solution:** Wait for stability + upload processing (~90 seconds)

### AWS Credentials Error
- **Cause:** Missing or incorrect AWS profile
- **Solution:** Verify `~/.aws/credentials` has `[china]` profile

### S3 Upload Fails
- **Cause:** Bucket not accessible or wrong region
- **Solution:** Verify bucket exists in `cn-north-1` or `cn-northwest-1`

### Queue File Not Found
- **Cause:** Service not creating queue file
- **Solution:** Check service logs for errors

### Registry File Not Cleaned
- **Cause:** retention_days logic may not be implemented
- **Solution:** Check service logs for cleanup messages

---

## Future Enhancements

### Additional Gap Tests (Not Implemented)
These gaps are lower priority or require more setup:

- **Gap 5:** SIGHUP config reload (requires SIGHUP handler in code)
- **Gap 6:** Interval min/max validation (requires validation in code)
- **Gap 7:** Age-based cleanup schedule timing (requires time manipulation)
- **Gap 9:** Multiple AWS profiles (requires profile setup)
- **Gap 13:** CloudWatch publish interval (long runtime + CloudWatch delays)
- **Gap 14:** End-to-end workflow integration (1-2 hour runtime)

### Why Not Included?
- **Time constraints:** Some tests require 1+ hour runtime
- **Manual setup:** Some require specific AWS profile configurations
- **Feature dependencies:** Some require features that may not be implemented yet

---

## Contributing

### Adding New Gap Tests
1. Create test file: `scripts/testing/gap-tests/22_test_name.sh`
2. Follow template from existing tests
3. Use unique test vehicle ID: `${VEHICLE_ID}-TEST22-${TIMESTAMP}`
4. Add cleanup at end of test
5. Update `run_gap_tests.sh` to include new test
6. Update this README with test details

### Test Template
```bash
#!/bin/bash
# TEST XX: Test Name
# Purpose: What this test verifies
# Duration: ~X minutes

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../../lib/test_helpers.sh"

CONFIG_FILE="${1:-config/config.yaml}"
TEST_VEHICLE_ID="${2}"
TEST_DIR="/tmp/tvm-gap-test-XX"
SERVICE_LOG="/tmp/tvm-service-gapXX.log"

print_test_header "Test Name" "XX"

# Load config and create unique vehicle ID
load_config "$CONFIG_FILE"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
if [ -n "$TEST_VEHICLE_ID" ]; then
    VEHICLE_ID="${TEST_VEHICLE_ID}-TESTXX-${TIMESTAMP}"
else
    VEHICLE_ID="vehicle-TESTXX-${TIMESTAMP}"
fi

# Test logic here...

# Cleanup
cleanup_test_s3_data "$VEHICLE_ID" "$S3_BUCKET" "$AWS_PROFILE" "$AWS_REGION" "$TODAY"
print_test_summary

# Exit
if [ $TESTS_FAILED -eq 0 ]; then
    log_success "TEST XX: PASSED"
    exit 0
else
    log_error "TEST XX: FAILED"
    exit 1
fi
```

---

## License

Same as main TVM Upload System project.

---

## Support

For issues or questions:
1. Check `docs/MANUAL_TEST_COVERAGE_REPORT.md` for detailed test case documentation
2. Review service logs in `/tmp/tvm-service-gapXX.log`
3. Check original test suite in `scripts/testing/manual-tests/`
