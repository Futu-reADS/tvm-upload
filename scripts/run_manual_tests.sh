#!/bin/bash
# Master Test Runner for TVM Upload Manual Tests
# Runs all 12 manual test scenarios and generates comprehensive report
# Usage: ./scripts/run_manual_tests.sh [config_file] [test_numbers]
# Examples:
#   ./scripts/run_manual_tests.sh                    # Run all tests
#   ./scripts/run_manual_tests.sh config/config.yaml # Run all tests with custom config
#   ./scripts/run_manual_tests.sh config/config.yaml "1 2 3"  # Run only tests 1, 2, 3

set -e
set -o pipefail  # Propagate exit codes through pipes

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Load helper functions
source "${SCRIPT_DIR}/lib/test_helpers.sh"

# Configuration
CONFIG_FILE="${1:-config/config.yaml}"
TESTS_TO_RUN="${2:-all}"
REPORT_FILE="/tmp/manual-test-results-$(date +%Y%m%d_%H%M%S).txt"
START_TIME=$(date +%s)

# Banner
echo ""
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║     TVM Upload System - Manual Test Suite Runner              ║"
echo "╔════════════════════════════════════════════════════════════════╗"
echo ""
log_info "Configuration file: $CONFIG_FILE"
log_info "Report file: $REPORT_FILE"
log_info "Start time: $(date)"
echo ""

# Verify config file exists
if [ ! -f "$CONFIG_FILE" ]; then
    log_error "Configuration file not found: $CONFIG_FILE"
    exit 1
fi

# Change to project root
cd "$PROJECT_ROOT"

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
    [1]="Basic File Upload"
    [2]="Source-Based Path Detection"
    [3]="File Date Preservation"
    [4]="CloudWatch Metrics Publishing"
    [5]="CloudWatch Alarm Creation"
    [6]="Duplicate Upload Prevention"
    [7]="Disk Space Management"
    [8]="Batch Upload Performance"
    [9]="Large File Upload (Multipart)"
    [10]="Error Handling and Retry"
    [11]="Operational Hours Compliance"
    [12]="Service Restart Resilience"
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
    [11]="5 min"
    [12]="10 min"
)

# Determine which tests to run
if [ "$TESTS_TO_RUN" = "all" ]; then
    TESTS=(1 2 3 4 5 6 7 8 9 10 11 12)
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

    echo "Running: $ACTUAL_SCRIPT" | tee -a "$REPORT_FILE"
    echo "" | tee -a "$REPORT_FILE"

    # Disable pipefail temporarily to capture exit code
    set +o pipefail
    bash "$ACTUAL_SCRIPT" "$CONFIG_FILE" 2>&1 | tee -a "$TEST_LOG"
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

    # Clean up test environment between tests
    log_info "Cleaning up test environment..."
    cleanup_test_env "/tmp/tvm-manual-test" 2>/dev/null || true

    # Brief pause between tests
    sleep 3
done

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

# Exit with appropriate code
if [ $TESTS_FAILED -eq 0 ]; then
    log_success "Manual test suite completed successfully!"
    exit 0
else
    log_error "Manual test suite completed with failures"
    exit 1
fi
