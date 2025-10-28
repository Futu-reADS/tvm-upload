# TVM Upload System - Automated Manual Test Scripts

This directory contains automated scripts for running manual test scenarios described in `docs/manual_testing_guide.md`.

## Overview

These scripts automate the 12 manual test scenarios, allowing you to:
- Validate system functionality before deployment
- Verify features work correctly in your environment
- Run regression tests after code changes
- Generate comprehensive test reports

## Quick Start

### Run All Tests

```bash
# From project root
./scripts/run_manual_tests.sh
```

This will:
1. Run all 12 test scenarios sequentially
2. Generate a detailed test report
3. Display pass/fail summary
4. Save results to `/tmp/manual-test-results-<timestamp>.txt`

### Run Specific Tests

```bash
# Run only tests 1, 2, and 3
./scripts/run_manual_tests.sh config/config.yaml "1 2 3"

# Run a single test
./scripts/manual-tests/01_basic_upload.sh
```

### Custom Configuration

```bash
# Use a different config file
./scripts/run_manual_tests.sh path/to/custom/config.yaml
```

## Test Scenarios

| Test | Name | Duration | Description |
|------|------|----------|-------------|
| 01 | Basic File Upload | 10 min | Verify basic monitoring and S3 upload |
| 02 | Source-Based Path Detection | 5 min | Verify source directory categorization |
| 03 | File Date Preservation | 5 min | Verify file dates preserved in S3 paths |
| 04 | CloudWatch Metrics | 10 min | Verify metrics published to CloudWatch |
| 05 | CloudWatch Alarms | 5 min | Verify alarm creation and configuration |
| 06 | Duplicate Prevention | 10 min | Verify registry prevents re-uploads |
| 07 | Disk Space Management | 15 min | Verify cleanup and disk management |
| 08 | Batch Upload Performance | 10 min | Test multiple file handling |
| 09 | Large File Upload | 10 min | Test multipart upload for files > 5MB |
| 10 | Error Handling & Retry | 15 min | Test resilience to network/auth errors |
| 11 | Operational Hours & Schedule Modes | 10 min | Verify operational hours and schedule modes (interval/daily) |
| 12 | Service Restart Resilience | 10 min | Verify graceful shutdown, recovery, and upload_on_start |
| 13 | Pattern Matching | 5 min | Verify log_directories pattern filtering (e.g., "syslog*") |
| 14 | Recursive Monitoring | 5 min | Verify recursive vs non-recursive directory monitoring |
| 15 | Startup Scan | 10 min | Verify scan_existing_files and max_age_days behavior |
| 16 | Emergency Cleanup Thresholds | 10 min | Verify emergency cleanup at critical disk threshold (95%) |

**Total Duration:** ~2.5 hours for all tests

## Prerequisites

### System Requirements
- Ubuntu/Linux system
- Python 3.8+ installed
- AWS CLI configured
- Minimum 10GB free disk space
- Network access to AWS China (cn-north-1)

### AWS Permissions Required
```yaml
S3:
  - s3:PutObject
  - s3:GetObject
  - s3:ListBucket

CloudWatch:
  - cloudwatch:PutMetricData
  - cloudwatch:PutMetricAlarm
  - cloudwatch:DescribeAlarms
  - cloudwatch:GetMetricStatistics  # Optional, for verification
  - cloudwatch:ListMetrics          # Optional, for verification
```

### Configuration
Ensure `config/config.yaml` is properly configured with:
- Valid `vehicle_id`
- Correct S3 bucket and region
- AWS credentials path
- Upload settings (schedule, stability period, etc.)

## Test Script Architecture

### Helper Library
All test scripts use `scripts/lib/test_helpers.sh` which provides:

**Logging Functions:**
- `log_info()` - Blue info messages
- `log_success()` - Green success messages (increments pass counter)
- `log_error()` - Red error messages (increments fail counter)
- `log_warning()` - Yellow warnings
- `log_skip()` - Yellow skip messages

**Test Management:**
- `print_test_header()` - Print test banner
- `print_test_summary()` - Display pass/fail counts
- `wait_with_progress()` - Progress bar for waits

**File Operations:**
- `create_test_dir()` - Create test directory structure
- `generate_test_file()` - Create files with specific sizes
- `set_file_mtime()` - Set file modification time
- `assert_file_exists()` - Verify file presence
- `assert_file_not_exists()` - Verify file deletion

**Service Management:**
- `start_tvm_service()` - Start service in background
- `stop_tvm_service()` - Graceful shutdown
- `check_service_health()` - Verify service running
- `get_service_logs()` - Retrieve log entries

**Assertions:**
- `assert_equals()` - Compare strings
- `assert_contains()` - Check substring
- `assert_greater_than()` - Numeric comparison

### Script Structure
Each test script follows this pattern:

```bash
#!/bin/bash
# TEST N: Test Name
# Purpose: Brief description
# Duration: X minutes

set -e  # Exit on error

# Load helpers
source "$(dirname "${BASH_SOURCE[0]}")/../lib/test_helpers.sh"

# Configuration
CONFIG_FILE="${1:-config/config.yaml}"
TEST_DIR="/tmp/tvm-manual-test"
SERVICE_LOG="/tmp/tvm-service.log"

# Print header
print_test_header "Test Name" "N"

# Load and verify config
load_config "$CONFIG_FILE"

# Run test steps
# ...

# Cleanup
cleanup_test_env "$TEST_DIR"

# Print results
print_test_summary

# Exit with appropriate code
if [ $TESTS_FAILED -eq 0 ]; then
    log_success "TEST N: PASSED"
    exit 0
else
    log_error "TEST N: FAILED"
    exit 1
fi
```

## Running Tests

### Individual Test Execution

Each test can be run independently:

```bash
# Basic file upload test
./scripts/manual-tests/01_basic_upload.sh

# With custom config
./scripts/manual-tests/01_basic_upload.sh config/custom.yaml

# CloudWatch metrics test
./scripts/manual-tests/04_cloudwatch_metrics.sh
```

### Master Test Runner

The master runner (`run_manual_tests.sh`) provides:

**Features:**
- Runs multiple tests sequentially
- Generates comprehensive report
- Tracks pass/fail statistics
- Calculates test duration
- Provides recommendations
- Cleans up between tests

**Usage:**
```bash
# Run all tests
./scripts/run_manual_tests.sh

# Run specific tests
./scripts/run_manual_tests.sh config/config.yaml "1 2 3 6 7"

# Run with custom config
./scripts/run_manual_tests.sh config/production.yaml
```

**Output:**
```
╔════════════════════════════════════════════════════════════════╗
║     TVM Upload System - Manual Test Suite Runner              ║
╔════════════════════════════════════════════════════════════════╗

Running 16 tests: 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16

[Test execution logs...]

╔════════════════════════════════════════════════════════════════╗
║     FINAL TEST SUMMARY                                         ║
╔════════════════════════════════════════════════════════════════╗

Test Results:
┌──────┬─────────────────────────────────────────────┬──────────┐
│ Test │ Name                                        │ Result   │
├──────┼─────────────────────────────────────────────┼──────────┤
│ 1    │ Basic File Upload                           │ PASSED   │
│ 2    │ Source-Based Path Detection                 │ PASSED   │
│ 3    │ File Date Preservation                      │ PASSED   │
│ 4    │ CloudWatch Metrics                          │ PASSED   │
│ 5    │ CloudWatch Alarms                           │ PASSED   │
│ 6    │ Duplicate Prevention                        │ PASSED   │
│ 7    │ Disk Space Management                       │ PASSED   │
│ 8    │ Batch Upload Performance                    │ PASSED   │
│ 9    │ Large File Upload                           │ PASSED   │
│ 10   │ Error Handling & Retry                      │ PASSED   │
│ 11   │ Operational Hours & Schedule Modes          │ PASSED   │
│ 12   │ Service Restart Resilience                  │ PASSED   │
│ 13   │ Pattern Matching                            │ PASSED   │
│ 14   │ Recursive Monitoring                        │ PASSED   │
│ 15   │ Startup Scan                                │ PASSED   │
│ 16   │ Emergency Cleanup Thresholds                │ PASSED   │
└──────┴─────────────────────────────────────────────┴──────────┘

Summary Statistics:
  Total Tests:    16
  Passed:         16
  Failed:         0
  Pass Rate:      100%

Full report saved to: /tmp/manual-test-results-20250127_143022.txt
```

## Test Reports

Test reports are saved to `/tmp/manual-test-results-<timestamp>.txt` and include:

1. **Header** - Test run metadata (date, config, hostname)
2. **Execution Log** - Detailed output from each test
3. **Test Results Table** - Summary of all tests
4. **Statistics** - Pass/fail counts and percentages
5. **Duration** - Total time and per-test timing
6. **Recommendations** - Next steps based on results

## Troubleshooting

### Common Issues

**Test fails with "Service failed to start":**
```bash
# Check if service is already running
ps aux | grep "tvm.*upload"

# Kill existing processes
pkill -f "python.*src.main"

# Check logs
cat /tmp/tvm-service.log
```

**AWS permission errors:**
```bash
# Verify AWS credentials
aws sts get-caller-identity --region cn-north-1

# Test S3 access
aws s3 ls s3://your-bucket --region cn-north-1

# Test CloudWatch access
aws cloudwatch list-metrics --namespace TVM/Upload --region cn-north-1
```

**File not found in S3:**
```bash
# Check S3 path format
aws s3 ls s3://your-bucket/vehicle-id/ --recursive --region cn-north-1

# Verify file stability period
grep "file_stable_seconds" config/config.yaml

# Check service logs for upload confirmation
cat /tmp/tvm-service.log | grep -i "upload\|s3"
```

**Tests run too slowly:**
```bash
# Reduce file stability period for testing
# Edit config/config.yaml:
upload:
  file_stable_seconds: 30  # Reduce from 60

# Run fewer tests
./scripts/run_manual_tests.sh config/config.yaml "1 2 3"
```

### Debug Mode

Run individual tests with bash debug mode:

```bash
bash -x ./scripts/manual-tests/01_basic_upload.sh
```

## Best Practices

### Before Running Tests

1. **Backup configuration:**
   ```bash
   cp config/config.yaml config/config.yaml.bak
   ```

2. **Verify AWS credentials:**
   ```bash
   aws sts get-caller-identity --region cn-north-1
   ```

3. **Check disk space:**
   ```bash
   df -h /tmp
   ```

4. **Stop any running TVM services:**
   ```bash
   pkill -f "python.*src.main"
   ```

### During Tests

1. **Monitor service logs:**
   ```bash
   tail -f /tmp/tvm-service.log
   ```

2. **Watch S3 uploads:**
   ```bash
   watch -n 10 'aws s3 ls s3://your-bucket/vehicle-id/ --recursive --region cn-north-1 | tail -20'
   ```

### After Tests

1. **Review test report:**
   ```bash
   cat /tmp/manual-test-results-*.txt
   ```

2. **Clean up test artifacts:**
   ```bash
   ./scripts/lib/test_helpers.sh
   # Call cleanup_test_env function
   ```

3. **Check for orphaned processes:**
   ```bash
   ps aux | grep tvm
   ```

## Integration with CI/CD

These scripts can be integrated into CI/CD pipelines:

```yaml
# GitHub Actions example
- name: Run Manual Test Suite
  run: |
    ./scripts/run_manual_tests.sh config/ci-config.yaml
  env:
    AWS_REGION: cn-north-1

- name: Upload Test Report
  uses: actions/upload-artifact@v3
  with:
    name: manual-test-report
    path: /tmp/manual-test-results-*.txt
```

## Contributing

### Adding New Tests

1. Create new script: `scripts/manual-tests/13_new_test.sh`
2. Follow existing script structure
3. Use helper functions from `test_helpers.sh`
4. Update `run_manual_tests.sh` with new test entry
5. Update this README

### Modifying Tests

1. Test changes locally first
2. Ensure cleanup functions are called
3. Update test duration estimates if needed
4. Document any new prerequisites

## Related Documentation

- [manual_testing_guide.md](../../docs/manual_testing_guide.md) - Detailed manual test procedures
- [autonomous_testing_guide.md](../../docs/autonomous_testing_guide.md) - Automated test architecture
- [testing_strategy_overview.md](../../docs/testing_strategy_overview.md) - Overall testing strategy

## Support

For issues or questions:
1. Check the troubleshooting section above
2. Review service logs: `/tmp/tvm-service.log`
3. Review test report for detailed error messages
4. Consult main documentation in `docs/`

---

**Last Updated:** 2025-01-27
**Maintained By:** TVM Upload Team
