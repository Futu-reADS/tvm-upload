#!/bin/bash
# Master Test Runner for TVM Upload Manual Tests
# Runs all 17 manual test scenarios and generates comprehensive report
# Usage: ./scripts/run_manual_tests.sh [config_file] [test_numbers]
# Examples:
#   ./scripts/run_manual_tests.sh                    # Run all tests
#   ./scripts/run_manual_tests.sh config/config.yaml # Run all tests with custom config
#   ./scripts/run_manual_tests.sh config/config.yaml "1 2 3"  # Run only tests 1, 2, 3

set -e
set -o pipefail  # Propagate exit codes through pipes

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
SCRIPTS_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Change to project root so all relative paths work correctly
cd "$PROJECT_ROOT"

# Load helper functions
source "${SCRIPTS_ROOT}/lib/test_helpers.sh"

# Configuration
CONFIG_FILE="${1:-config/config.yaml}"
TESTS_TO_RUN="${2:-all}"
REPORT_FILE="/tmp/manual-test-results-$(date +%Y%m%d_%H%M%S).txt"
START_TIME=$(date +%s)

# Parse configuration to get original vehicle ID
ORIGINAL_VEHICLE_ID=$(grep "^vehicle_id:" "$CONFIG_FILE" | awk '{print $2}' | tr -d '"')

# Generate test vehicle ID based on original vehicle name
# Example: vehicle-CN-01 -> vehicle-TEST-CN-01-MANUAL-1730123456
if [ -n "$ORIGINAL_VEHICLE_ID" ]; then
    # Extract the vehicle name part (e.g., CN-01 from vehicle-CN-01)
    VEHICLE_NAME=$(echo "$ORIGINAL_VEHICLE_ID" | sed 's/^vehicle-//')
    # Create test vehicle ID with TEST prefix and MANUAL suffix
    TEST_VEHICLE_ID=$(generate_test_vehicle_id "vehicle-TEST-${VEHICLE_NAME}-MANUAL")
else
    # Fallback if vehicle_id not found in config
    TEST_VEHICLE_ID=$(generate_test_vehicle_id "vehicle-TEST-MANUAL")
fi
export TEST_VEHICLE_ID

# Parse S3 configuration for final cleanup
S3_BUCKET=$(grep "bucket:" "$CONFIG_FILE" | head -1 | awk '{print $2}' | tr -d '"')
AWS_REGION=$(grep "region:" "$CONFIG_FILE" | head -1 | awk '{print $2}' | tr -d '"')
AWS_PROFILE=$(grep "profile:" "$CONFIG_FILE" | head -1 | awk '{print $2}' | tr -d '"')
export S3_BUCKET AWS_REGION AWS_PROFILE

# Banner
echo ""
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║     TVM Upload System - Manual Test Suite Runner              ║"
echo "╔════════════════════════════════════════════════════════════════╗"
echo ""
log_info "Configuration file: $CONFIG_FILE"
log_info "Report file: $REPORT_FILE"
log_info "Test Vehicle ID: $TEST_VEHICLE_ID"
log_info "S3 Bucket: $S3_BUCKET"
log_info "Start time: $(date)"
echo ""

# Verify config file exists
if [ ! -f "$CONFIG_FILE" ]; then
    log_error "Configuration file not found: $CONFIG_FILE"
    exit 1
fi

# Change to project root
cd "$PROJECT_ROOT"

# ============================================================================
# PRE-FLIGHT CHECKS - Smart validation before running tests
# ============================================================================
echo ""
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║     PRE-FLIGHT CHECKS                                          ║"
echo "╔════════════════════════════════════════════════════════════════╗"
echo ""

PREFLIGHT_WARNINGS=0
PREFLIGHT_ERRORS=0

# ----------------------------------------------------------------------------
# Check 1: AWS Connectivity & S3 Access
# ----------------------------------------------------------------------------
log_info "Checking AWS connectivity and S3 access..."

if [ -n "$AWS_PROFILE" ]; then
    AWS_CMD="aws --profile $AWS_PROFILE --region $AWS_REGION"
else
    AWS_CMD="aws --region $AWS_REGION"
fi

# Test S3 bucket access
if $AWS_CMD s3 ls "s3://$S3_BUCKET" &> /dev/null; then
    log_success "AWS S3 bucket accessible: s3://$S3_BUCKET"
else
    log_error "Cannot access S3 bucket: s3://$S3_BUCKET"
    echo ""
    echo "  ${YELLOW}Possible causes:${NC}"
    echo "  • AWS credentials not configured or expired"
    echo "  • S3 bucket does not exist"
    echo "  • IAM permissions insufficient (need s3:ListBucket)"
    echo "  • Network connectivity issues"
    echo ""
    echo "  ${CYAN}Troubleshooting:${NC}"
    echo "  • Run: aws sts get-caller-identity --profile ${AWS_PROFILE:-default}"
    echo "  • Run: ./scripts/diagnostics/verify_aws_credentials.sh"
    echo "  • Run: ./scripts/deployment/verify_deployment.sh"
    echo ""

    PREFLIGHT_ERRORS=$((PREFLIGHT_ERRORS + 1))

    read -p "$(echo -e ${YELLOW}Do you want to continue anyway? [y/N]: ${NC})" -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log_error "Pre-flight checks failed. Exiting."
        exit 1
    fi
    log_warning "Continuing despite AWS connectivity issues (tests will likely fail)"
fi

# Test S3 write permission
TEST_KEY="${TEST_VEHICLE_ID}/preflight-test-$(date +%s).txt"
if echo "preflight test" | $AWS_CMD s3 cp - "s3://$S3_BUCKET/$TEST_KEY" &> /dev/null 2>&1; then
    log_success "S3 write permission verified"
    # Cleanup test file
    $AWS_CMD s3 rm "s3://$S3_BUCKET/$TEST_KEY" &> /dev/null 2>&1 || true
else
    log_error "S3 write permission denied"
    echo ""
    echo "  ${YELLOW}Possible causes:${NC}"
    echo "  • IAM policy missing s3:PutObject permission"
    echo "  • Bucket policy restricts write access"
    echo ""

    PREFLIGHT_ERRORS=$((PREFLIGHT_ERRORS + 1))

    read -p "$(echo -e ${YELLOW}Do you want to continue anyway? [y/N]: ${NC})" -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log_error "Pre-flight checks failed. Exiting."
        exit 1
    fi
    log_warning "Continuing despite S3 write permission issues (tests will likely fail)"
fi

# ----------------------------------------------------------------------------
# Check 2: Operational Hours Configuration
# ----------------------------------------------------------------------------
log_info "Checking operational hours configuration..."

# Parse operational hours from config
# Use awk to parse the YAML correctly (avoids commented sections)
OPERATIONAL_HOURS_ENABLED=$(awk '/^  operational_hours:/{flag=1; next} flag && /^    enabled:/{print $2; exit}' "$CONFIG_FILE" | tr -d '"')
OPERATIONAL_START=$(awk '/^  operational_hours:/{flag=1; next} flag && /^    start:/{print $2; exit}' "$CONFIG_FILE" | tr -d '"' | tr -d ' ')
OPERATIONAL_END=$(awk '/^  operational_hours:/{flag=1; next} flag && /^    end:/{print $2; exit}' "$CONFIG_FILE" | tr -d '"' | tr -d ' ')

if [ "$OPERATIONAL_HOURS_ENABLED" = "true" ] && [ -n "$OPERATIONAL_START" ] && [ -n "$OPERATIONAL_END" ]; then
    # Get current time in HH:MM format
    CURRENT_TIME=$(date +%H:%M)
    CURRENT_HOUR=$(date +%H | sed 's/^0//')  # Remove leading zero
    CURRENT_MIN=$(date +%M | sed 's/^0//')   # Remove leading zero

    # Handle empty minutes (becomes 0)
    [ -z "$CURRENT_MIN" ] && CURRENT_MIN=0

    # Parse start/end times (remove leading zeros)
    START_HOUR=$(echo "$OPERATIONAL_START" | cut -d: -f1 | sed 's/^0//')
    START_MIN=$(echo "$OPERATIONAL_START" | cut -d: -f2 | sed 's/^0//')
    END_HOUR=$(echo "$OPERATIONAL_END" | cut -d: -f1 | sed 's/^0//')
    END_MIN=$(echo "$OPERATIONAL_END" | cut -d: -f2 | sed 's/^0//')

    # Handle empty minutes (becomes 0)
    [ -z "$START_MIN" ] && START_MIN=0
    [ -z "$END_MIN" ] && END_MIN=0

    # Convert to minutes since midnight for comparison
    CURRENT_MINS=$((CURRENT_HOUR * 60 + CURRENT_MIN))
    START_MINS=$((START_HOUR * 60 + START_MIN))
    END_MINS=$((END_HOUR * 60 + END_MIN))

    # Check if current time is within operational hours
    if [ $CURRENT_MINS -ge $START_MINS ] && [ $CURRENT_MINS -lt $END_MINS ]; then
        log_success "Within operational hours (${OPERATIONAL_START}-${OPERATIONAL_END}, current: ${CURRENT_TIME})"
    else
        log_warning "OUTSIDE operational hours!"
        echo ""
        echo "  ${YELLOW}Current time:${NC}      $CURRENT_TIME"
        echo "  ${YELLOW}Operational hours:${NC} ${OPERATIONAL_START} - ${OPERATIONAL_END}"
        echo ""
        echo "  ${CYAN}Impact:${NC}"
        echo "  • Files will be queued instead of uploaded immediately"
        echo "  • Tests may fail because uploads won't happen within test duration"
        echo "  • Scheduled uploads (interval: 2 hours) won't trigger in short tests"
        echo ""
        echo "  ${CYAN}Recommendations:${NC}"
        echo "  1. Run tests during operational hours (${OPERATIONAL_START}-${OPERATIONAL_END})"
        echo "  2. Temporarily disable operational_hours in config:"
        echo "     ${BLUE}sed -i '/operational_hours:/,/enabled:/s/enabled: true/enabled: false/' $CONFIG_FILE${NC}"
        echo "  3. Continue anyway (tests will likely fail)"
        echo ""

        PREFLIGHT_WARNINGS=$((PREFLIGHT_WARNINGS + 1))

        read -p "$(echo -e ${YELLOW}Do you want to continue anyway? [y/N]: ${NC})" -n 1 -r
        echo ""
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            log_error "Tests cancelled due to operational hours restriction."
            exit 1
        fi
        log_warning "Continuing outside operational hours (expect test failures)"
    fi
else
    log_success "Operational hours disabled (immediate uploads 24/7)"
fi

# ----------------------------------------------------------------------------
# Check 3: Configuration Sanity
# ----------------------------------------------------------------------------
log_info "Checking configuration sanity..."

# Check vehicle_id
if [ -z "$ORIGINAL_VEHICLE_ID" ]; then
    log_warning "vehicle_id not set in config (will use generated ID)"
    PREFLIGHT_WARNINGS=$((PREFLIGHT_WARNINGS + 1))
else
    log_success "Vehicle ID configured: $ORIGINAL_VEHICLE_ID"
fi

# Check upload_on_start setting (for Test 12)
UPLOAD_ON_START=$(grep "upload_on_start:" "$CONFIG_FILE" | head -1 | awk '{print $2}' | tr -d '"')
if [ -n "$UPLOAD_ON_START" ]; then
    log_success "upload_on_start setting found: $UPLOAD_ON_START"
else
    log_warning "upload_on_start setting not found (Test 12 may have issues)"
    PREFLIGHT_WARNINGS=$((PREFLIGHT_WARNINGS + 1))
fi

# ----------------------------------------------------------------------------
# Check 4: Disk Space
# ----------------------------------------------------------------------------
log_info "Checking disk space..."

DISK_FREE_GB=$(df -BG /tmp | tail -1 | awk '{print $4}' | tr -d 'G')
if [ "$DISK_FREE_GB" -ge 10 ]; then
    log_success "Disk space: ${DISK_FREE_GB}GB free in /tmp"
elif [ "$DISK_FREE_GB" -ge 5 ]; then
    log_warning "Low disk space: ${DISK_FREE_GB}GB free in /tmp (tests need ~2GB)"
    PREFLIGHT_WARNINGS=$((PREFLIGHT_WARNINGS + 1))
else
    log_error "Insufficient disk space: ${DISK_FREE_GB}GB free in /tmp (need at least 5GB)"
    PREFLIGHT_ERRORS=$((PREFLIGHT_ERRORS + 1))

    read -p "$(echo -e ${YELLOW}Do you want to continue anyway? [y/N]: ${NC})" -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log_error "Pre-flight checks failed. Exiting."
        exit 1
    fi
fi

# ----------------------------------------------------------------------------
# Pre-flight Summary
# ----------------------------------------------------------------------------
echo ""
echo "════════════════════════════════════════════════════════════════"
if [ $PREFLIGHT_ERRORS -eq 0 ] && [ $PREFLIGHT_WARNINGS -eq 0 ]; then
    log_success "All pre-flight checks passed! ✓"
elif [ $PREFLIGHT_ERRORS -eq 0 ]; then
    log_warning "Pre-flight checks completed with $PREFLIGHT_WARNINGS warning(s)"
else
    log_warning "Pre-flight checks completed with $PREFLIGHT_ERRORS error(s) and $PREFLIGHT_WARNINGS warning(s)"
fi
echo "════════════════════════════════════════════════════════════════"
echo ""

# Pre-test cleanup: Remove any leftover state from previous test runs
log_info "Cleaning up any leftover state from previous test runs..."
cleanup_test_env "/tmp/tvm-manual-test" 2>/dev/null || true
sleep 1

# Initialize report
cat > "$REPORT_FILE" <<EOF
╔════════════════════════════════════════════════════════════════╗
║     TVM Upload System - Manual Test Results                   ║
╔════════════════════════════════════════════════════════════════╗

Test Suite Run: $(date)
Configuration: $CONFIG_FILE
Hostname: $(hostname)
User: $(whoami)

╔════════════════════════════════════════════════════════════════╗
║     Test Execution Log                                         ║
╔════════════════════════════════════════════════════════════════╗

EOF

# Test definitions
declare -A TEST_NAMES=(
    [1]="Startup Scan"
    [2]="Source-Based Path Detection"
    [3]="File Date Preservation"
    [4]="CloudWatch Metrics Publishing"
    [5]="CloudWatch Alarm Creation"
    [6]="Duplicate Upload Prevention"
    [7]="Disk Space Management"
    [8]="Batch Upload Performance"
    [9]="Large File Upload (Multipart)"
    [10]="Error Handling and Retry"
    [11]="Operational Hours & Schedule Modes"
    [12]="Service Restart Resilience"
    [13]="Pattern Matching"
    [14]="Recursive Monitoring"
    [15]="Basic File Upload"
    [16]="Emergency Cleanup Thresholds"
    [17]="Deletion Safety System"
)

declare -A TEST_DURATIONS=(
    [1]="10 min"
    [2]="5 min"
    [3]="5 min"
    [4]="10 min"
    [5]="5 min"
    [6]="10 min"
    [7]="15 min"
    [8]="10 min"
    [9]="10 min"
    [10]="15 min"
    [11]="10 min"
    [12]="10 min"
    [13]="5 min"
    [14]="5 min"
    [15]="10 min"
    [16]="10 min"
    [17]="5 min"
)

# Determine which tests to run
if [ "$TESTS_TO_RUN" = "all" ]; then
    TESTS=(1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17)
else
    TESTS=($TESTS_TO_RUN)
fi

log_info "Running ${#TESTS[@]} tests: ${TESTS[*]}"
echo ""

# Results tracking
TESTS_PASSED=0
TESTS_FAILED=0
TESTS_SKIPPED=0
declare -A TEST_RESULTS

# Run each test
for test_num in "${TESTS[@]}"; do
    TEST_SCRIPT="${SCRIPT_DIR}/manual-tests/$(printf "%02d" $test_num)_*.sh"
    TEST_NAME="${TEST_NAMES[$test_num]}"
    TEST_DURATION="${TEST_DURATIONS[$test_num]}"

    echo ""
    echo "╔════════════════════════════════════════════════════════════════╗"
    echo "║ TEST $test_num: $TEST_NAME"
    echo "║ Expected duration: $TEST_DURATION"
    echo "╔════════════════════════════════════════════════════════════════╗"
    echo ""

    # Find the actual test script
    ACTUAL_SCRIPT=$(ls $TEST_SCRIPT 2>/dev/null | head -1)

    if [ -z "$ACTUAL_SCRIPT" ]; then
        log_error "Test script not found for test $test_num"
        TEST_RESULTS[$test_num]="ERROR"
        TESTS_FAILED=$((TESTS_FAILED + 1))
        continue
    fi

    # Run the test
    TEST_START=$(date +%s)
    TEST_LOG="/tmp/test_${test_num}.log"

    # Generate test-specific vehicle ID for isolation
    TEST_SPECIFIC_ID="${TEST_VEHICLE_ID}-T$(printf "%02d" $test_num)"
    log_info "Test-specific vehicle ID: $TEST_SPECIFIC_ID"

    echo "Running: $ACTUAL_SCRIPT" | tee -a "$REPORT_FILE"
    echo "Test Vehicle ID: $TEST_SPECIFIC_ID" | tee -a "$REPORT_FILE"
    echo "" | tee -a "$REPORT_FILE"

    # Disable pipefail temporarily to capture exit code
    set +o pipefail
    bash "$ACTUAL_SCRIPT" "$CONFIG_FILE" "$TEST_SPECIFIC_ID" 2>&1 | tee -a "$TEST_LOG"
    EXIT_CODE=${PIPESTATUS[0]}  # Get exit code of bash, not tee
    set -o pipefail

    if [ $EXIT_CODE -eq 0 ]; then
        TEST_RESULTS[$test_num]="PASSED"
        TESTS_PASSED=$((TESTS_PASSED + 1))
        log_success "Test $test_num PASSED"
    else
        TEST_RESULTS[$test_num]="FAILED"
        TESTS_FAILED=$((TESTS_FAILED + 1))
        log_error "Test $test_num FAILED (exit code: $EXIT_CODE)"
    fi

    # Calculate test duration
    TEST_END=$(date +%s)
    TEST_ACTUAL_DURATION=$((TEST_END - TEST_START))
    TEST_DURATION_MIN=$(echo "scale=1; $TEST_ACTUAL_DURATION / 60" | bc)

    log_info "Actual duration: ${TEST_DURATION_MIN} minutes"

    # Append to report
    cat >> "$REPORT_FILE" <<EOF

────────────────────────────────────────────────────────────────
TEST $test_num: $TEST_NAME
Result: ${TEST_RESULTS[$test_num]}
Duration: ${TEST_DURATION_MIN} minutes
────────────────────────────────────────────────────────────────

EOF

    # Append test log to report
    if [ -f "$TEST_LOG" ]; then
        cat "$TEST_LOG" >> "$REPORT_FILE"
        echo "" >> "$REPORT_FILE"
    fi

    # Clean up test environment between tests (local files only)
    log_info "Cleaning up test environment..."
    cleanup_test_env "/tmp/tvm-manual-test" 2>/dev/null || true

    # Note: S3 cleanup moved to batch process at end (faster, better visibility)

    # Brief pause between tests
    sleep 1
done

# ============================================================================
# BATCH S3 CLEANUP - Clean all test data at once with verification
# ============================================================================

echo ""
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║     S3 CLEANUP - Batch Processing All Test Data               ║"
echo "╔════════════════════════════════════════════════════════════════╗"
echo ""

log_info "Starting batch S3 cleanup for all test vehicles..."

# Track cleanup statistics
CLEANUP_SUCCESS_COUNT=0
CLEANUP_FAIL_COUNT=0
CLEANUP_NOTFOUND_COUNT=0

# Array to store cleanup results for detailed reporting
declare -A CLEANUP_RESULTS

# Process each test-specific ID
for test_num in "${TESTS[@]}"; do
    # FIX: Reconstruct the same TEST_SPECIFIC_ID that was used during test execution
    TEST_SPECIFIC_ID="${TEST_VEHICLE_ID}-T$(printf "%02d" $test_num)"

    log_info "Cleaning Test ${test_num}: ${TEST_SPECIFIC_ID}"

    # Call cleanup function and capture result
    if cleanup_complete_vehicle_folder "$TEST_SPECIFIC_ID" "$S3_BUCKET" "$AWS_PROFILE" "$AWS_REGION"; then
        # Check the actual result type from log output
        # If cleanup says "No S3 data found", it's not an error but a skip
        if aws s3 ls "s3://${S3_BUCKET}/${TEST_SPECIFIC_ID}/" --profile "$AWS_PROFILE" --region "$AWS_REGION" &>/dev/null; then
            CLEANUP_FAIL_COUNT=$((CLEANUP_FAIL_COUNT + 1))
            CLEANUP_RESULTS[$test_num]="FAILED (data still exists)"
        else
            # Successfully cleaned or no data was present
            CLEANUP_SUCCESS_COUNT=$((CLEANUP_SUCCESS_COUNT + 1))
            CLEANUP_RESULTS[$test_num]="SUCCESS"
        fi
    else
        # Function returned error
        CLEANUP_FAIL_COUNT=$((CLEANUP_FAIL_COUNT + 1))
        CLEANUP_RESULTS[$test_num]="FAILED (cleanup error)"
    fi
done

echo ""
log_info "Batch cleanup completed. Generating verification report..."
echo ""

# ============================================================================
# CLEANUP VERIFICATION REPORT
# ============================================================================

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║     S3 CLEANUP VERIFICATION REPORT                             ║"
echo "╔════════════════════════════════════════════════════════════════╗"
echo ""

# Detailed cleanup results table
echo "Cleanup Results by Test:"
echo "┌──────┬─────────────────────────────────────────────┬──────────────┐"
echo "│ Test │ Vehicle ID                                  │ Status       │"
echo "├──────┼─────────────────────────────────────────────┼──────────────┤"

for test_num in "${TESTS[@]}"; do
    TEST_SPECIFIC_ID="${TEST_ID_PREFIX}${test_num}"
    CLEANUP_STATUS="${CLEANUP_RESULTS[$test_num]}"

    # Pad ID to 43 characters
    PADDED_ID=$(printf "%-43s" "$TEST_SPECIFIC_ID")

    # Color code status
    case "$CLEANUP_STATUS" in
        SUCCESS)
            STATUS_DISPLAY="${GREEN}SUCCESS${NC}     "
            ;;
        FAILED*)
            STATUS_DISPLAY="${RED}FAILED${NC}      "
            ;;
        *)
            STATUS_DISPLAY="${YELLOW}UNKNOWN${NC}     "
            ;;
    esac

    printf "│ %-4s │ %s │ %b │\n" "$test_num" "$PADDED_ID" "$STATUS_DISPLAY"
done

echo "└──────┴─────────────────────────────────────────────┴──────────────┘"
echo ""

# Cleanup summary statistics
echo "Cleanup Summary:"
echo "  Total Vehicles:     ${#TESTS[@]}"
echo -e "  ${GREEN}Cleaned:${NC}            $CLEANUP_SUCCESS_COUNT"
echo -e "  ${RED}Failed:${NC}             $CLEANUP_FAIL_COUNT"
echo ""

# Final verification check - scan entire bucket for any remaining test data
log_info "Performing final verification scan of S3 bucket..."
echo ""

REMAINING_TEST_DATA=$(aws s3 ls "s3://${S3_BUCKET}/" --profile "$AWS_PROFILE" --region "$AWS_REGION" 2>/dev/null | grep -i "test" | grep -i "$COMMON_PREFIX" || true)

if [ -z "$REMAINING_TEST_DATA" ]; then
    log_success "✓ Verification complete: No test data found in S3 bucket"
    echo ""
else
    log_warning "⚠ Warning: Found potential remaining test data in S3:"
    echo "$REMAINING_TEST_DATA" | while IFS= read -r line; do
        echo "    $line"
    done
    echo ""
    log_warning "You may want to manually verify and clean these folders if needed."
    echo ""
fi

# Calculate total duration
END_TIME=$(date +%s)
TOTAL_DURATION=$((END_TIME - START_TIME))
TOTAL_DURATION_MIN=$(echo "scale=1; $TOTAL_DURATION / 60" | bc)
TOTAL_DURATION_HOUR=$(echo "scale=2; $TOTAL_DURATION / 3600" | bc)

# Generate final summary
echo "" | tee -a "$REPORT_FILE"
echo "╔════════════════════════════════════════════════════════════════╗" | tee -a "$REPORT_FILE"
echo "║     FINAL TEST SUMMARY                                         ║" | tee -a "$REPORT_FILE"
echo "╔════════════════════════════════════════════════════════════════╗" | tee -a "$REPORT_FILE"
echo "" | tee -a "$REPORT_FILE"

# Test results table
echo "Test Results:" | tee -a "$REPORT_FILE"
echo "┌──────┬─────────────────────────────────────────────┬──────────┐" | tee -a "$REPORT_FILE"
echo "│ Test │ Name                                        │ Result   │" | tee -a "$REPORT_FILE"
echo "├──────┼─────────────────────────────────────────────┼──────────┤" | tee -a "$REPORT_FILE"

for test_num in "${TESTS[@]}"; do
    TEST_NAME="${TEST_NAMES[$test_num]}"
    TEST_RESULT="${TEST_RESULTS[$test_num]}"

    # Pad name to 43 characters
    PADDED_NAME=$(printf "%-43s" "$TEST_NAME")

    # Color code result
    case "$TEST_RESULT" in
        PASSED)
            RESULT_DISPLAY="${GREEN}PASSED${NC}  "
            ;;
        FAILED)
            RESULT_DISPLAY="${RED}FAILED${NC}  "
            ;;
        SKIPPED)
            RESULT_DISPLAY="${YELLOW}SKIPPED${NC} "
            ;;
        *)
            RESULT_DISPLAY="ERROR   "
            ;;
    esac

    printf "│ %-4s │ %s │ %b │\n" "$test_num" "$PADDED_NAME" "$RESULT_DISPLAY" | tee -a "$REPORT_FILE"
done

echo "└──────┴─────────────────────────────────────────────┴──────────┘" | tee -a "$REPORT_FILE"
echo "" | tee -a "$REPORT_FILE"

# Summary statistics
echo "Summary Statistics:" | tee -a "$REPORT_FILE"
echo "  Total Tests:    ${#TESTS[@]}" | tee -a "$REPORT_FILE"
echo -e "  ${GREEN}Passed:${NC}         $TESTS_PASSED" | tee -a "$REPORT_FILE"
echo -e "  ${RED}Failed:${NC}         $TESTS_FAILED" | tee -a "$REPORT_FILE"
echo -e "  ${YELLOW}Skipped:${NC}        $TESTS_SKIPPED" | tee -a "$REPORT_FILE"
echo "" | tee -a "$REPORT_FILE"

# Calculate pass rate
if [ ${#TESTS[@]} -gt 0 ]; then
    PASS_RATE=$(echo "scale=1; $TESTS_PASSED * 100 / ${#TESTS[@]}" | bc)
    echo "  Pass Rate:      ${PASS_RATE}%" | tee -a "$REPORT_FILE"
fi

echo "" | tee -a "$REPORT_FILE"
echo "Duration:" | tee -a "$REPORT_FILE"
echo "  Total Time:     ${TOTAL_DURATION_MIN} minutes (${TOTAL_DURATION_HOUR} hours)" | tee -a "$REPORT_FILE"
echo "  Start:          $(date -d @$START_TIME)" | tee -a "$REPORT_FILE"
echo "  End:            $(date -d @$END_TIME)" | tee -a "$REPORT_FILE"
echo "" | tee -a "$REPORT_FILE"

echo "╔════════════════════════════════════════════════════════════════╗" | tee -a "$REPORT_FILE"
echo "║     RECOMMENDATIONS                                            ║" | tee -a "$REPORT_FILE"
echo "╔════════════════════════════════════════════════════════════════╗" | tee -a "$REPORT_FILE"
echo "" | tee -a "$REPORT_FILE"

if [ $TESTS_FAILED -eq 0 ] && [ $TESTS_SKIPPED -eq 0 ]; then
    echo "✓ All tests passed! System is ready for production deployment." | tee -a "$REPORT_FILE"
elif [ $TESTS_FAILED -eq 0 ]; then
    echo "✓ All executed tests passed." | tee -a "$REPORT_FILE"
    echo "⚠ Some tests were skipped - review configuration and re-run if needed." | tee -a "$REPORT_FILE"
else
    echo "✗ Some tests failed. Review the failures above and:" | tee -a "$REPORT_FILE"
    echo "  1. Check service logs for detailed error messages" | tee -a "$REPORT_FILE"
    echo "  2. Verify AWS credentials and permissions" | tee -a "$REPORT_FILE"
    echo "  3. Confirm configuration settings" | tee -a "$REPORT_FILE"
    echo "  4. Re-run failed tests individually for debugging" | tee -a "$REPORT_FILE"
fi

echo "" | tee -a "$REPORT_FILE"
echo "Full report saved to: $REPORT_FILE" | tee -a "$REPORT_FILE"
echo "" | tee -a "$REPORT_FILE"

echo "════════════════════════════════════════════════════════════════" | tee -a "$REPORT_FILE"
echo "" | tee -a "$REPORT_FILE"

# Cleanup
log_info "Cleaning up temporary files..."
rm -f /tmp/test_*.log

# Final S3 cleanup - safety catch-all for any remaining test data
echo ""
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║     FINAL S3 CLEANUP (Safety Catch-All)                       ║"
echo "╔════════════════════════════════════════════════════════════════╗"
echo ""
log_info "Performing final safety cleanup for base test vehicle ID..."
log_info "Base Vehicle ID: $TEST_VEHICLE_ID"
log_info "Note: Individual tests already cleaned their own S3 folders (${TEST_VEHICLE_ID}-T01, T02, etc.)"
log_info "This cleanup catches any stragglers or test data left behind due to failures."
cleanup_complete_vehicle_folder "$TEST_VEHICLE_ID" "$S3_BUCKET" "$AWS_PROFILE" "$AWS_REGION"
echo ""

# Exit with appropriate code
if [ $TESTS_FAILED -eq 0 ]; then
    log_success "Manual test suite completed successfully!"
    exit 0
else
    log_error "Manual test suite completed with failures"
    exit 1
fi
