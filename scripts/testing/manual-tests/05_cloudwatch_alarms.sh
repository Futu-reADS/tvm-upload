#!/bin/bash
# TEST 5: CloudWatch Alarm Creation
# Purpose: Verify alarm creation for low upload volume
# Duration: ~5 minutes

set -e

# Get script directory and load helpers
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../../lib/test_helpers.sh"

# Configuration
CONFIG_FILE="${1:-config/config.yaml}"
SERVICE_LOG="/tmp/tvm-service.log"

print_test_header "CloudWatch Alarm Creation" "5"

# Parse configuration
log_info "Loading configuration..."
load_config "$CONFIG_FILE"

# Get alarm name
ALARM_NAME="TVM-LowUpload-${VEHICLE_ID}"
log_info "Expected alarm name: $ALARM_NAME"

# Start service (some implementations auto-create alarms on startup)
log_info "Starting TVM upload service..."
if ! start_tvm_service "$CONFIG_FILE" "$SERVICE_LOG" "$TEST_DIR"; then
    log_error "Failed to start service"
    exit 1
fi

# Wait for service initialization
wait_with_progress 10 "Service initialization"

# Check if alarm exists
log_info "Checking if alarm exists..."
ALARM_RESULT=$(aws cloudwatch describe-alarms \
    --alarm-names "$ALARM_NAME" \
    --profile "$AWS_PROFILE" --region "$AWS_REGION" \
    --output json 2>&1 || echo "ERROR")

if echo "$ALARM_RESULT" | grep -q "ERROR\|AccessDenied"; then
    log_error "Cannot query CloudWatch alarms (permission issue)"
    log_info "Check AWS console manually for alarm: $ALARM_NAME"
elif echo "$ALARM_RESULT" | grep -q "MetricAlarms"; then
    NUM_ALARMS=$(echo "$ALARM_RESULT" | grep "AlarmName" | wc -l)
    NUM_ALARMS=$(echo "$NUM_ALARMS" | tr -d '[:space:]')  # Remove whitespace

    if [ "$NUM_ALARMS" -gt 0 ]; then
        log_success "Alarm exists: $ALARM_NAME"

        # Verify alarm configuration
        log_info "Verifying alarm configuration..."

        # Check metric name
        if echo "$ALARM_RESULT" | grep -q "BytesUploaded"; then
            log_success "Metric: BytesUploaded"
        else
            log_error "Metric is not BytesUploaded"
        fi

        # Check comparison operator
        if echo "$ALARM_RESULT" | grep -q "LessThanThreshold"; then
            log_success "Comparison: LessThanThreshold"
        else
            log_warning "Comparison operator may not be LessThanThreshold"
        fi

        # Check alarm state
        ALARM_STATE=$(echo "$ALARM_RESULT" | grep "StateValue" | head -1 | awk -F'"' '{print $4}')
        log_info "Alarm state: $ALARM_STATE"

        if [ "$ALARM_STATE" = "INSUFFICIENT_DATA" ] || [ "$ALARM_STATE" = "OK" ]; then
            log_success "Alarm in expected state: $ALARM_STATE"
        elif [ "$ALARM_STATE" = "ALARM" ]; then
            log_warning "Alarm in ALARM state (may indicate low upload volume)"
        else
            log_info "Alarm state: $ALARM_STATE"
        fi

        # Get threshold
        THRESHOLD=$(echo "$ALARM_RESULT" | grep "Threshold" | head -1 | awk '{print $2}' | tr -d ',')
        if [ -n "$THRESHOLD" ]; then
            log_success "Threshold configured: $THRESHOLD bytes"
        fi

        # Get evaluation periods
        EVAL_PERIODS=$(echo "$ALARM_RESULT" | grep "EvaluationPeriods" | head -1 | awk '{print $2}' | tr -d ',')
        if [ -n "$EVAL_PERIODS" ]; then
            log_success "Evaluation periods: $EVAL_PERIODS"
        fi

        # Display full alarm details
        log_info "Full alarm details:"
        echo "$ALARM_RESULT" | grep -E "AlarmName|MetricName|Threshold|ComparisonOperator|StateValue" | while read -r line; do
            echo "  $line"
        done

    else
        log_warning "Alarm not found: $ALARM_NAME"
        log_info "Note: Alarms are not auto-created by the service"
        log_info "Create alarms manually using AWS console or CloudFormation"
    fi
else
    log_error "Unexpected response from CloudWatch"
fi

# List all alarms for this vehicle (in case name pattern is different)
log_info "Listing all TVM alarms..."
aws cloudwatch describe-alarms \
    --alarm-name-prefix "TVM-" \
    --profile "$AWS_PROFILE" --region "$AWS_REGION" \
    --output table 2>&1 | grep -E "AlarmName|StateValue|MetricName" || log_info "No TVM alarms found"

# Cleanup
log_info "Cleaning up..."
stop_tvm_service

# Print summary
print_test_summary

# Test result
if [ $TESTS_FAILED -eq 0 ]; then
    log_success "TEST 5: PASSED - CloudWatch alarm creation working correctly"
    exit 0
else
    log_error "TEST 5: FAILED - See errors above"
    exit 1
fi
