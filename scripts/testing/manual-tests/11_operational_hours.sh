#!/bin/bash
# TEST 11: Operational Hours & Schedule Modes
# Purpose: Verify operational hours compliance and schedule mode behavior
# Duration: ~10 minutes
# Note: This test is optional and may need configuration changes

set -e

# Get script directory and load helpers
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../../lib/test_helpers.sh"

# Configuration
CONFIG_FILE="${1:-config/config.yaml}"
TEST_VEHICLE_ID="${2}"  # Test vehicle ID passed from run_manual_tests.sh
TEST_DIR="/tmp/tvm-manual-test"
SERVICE_LOG="/tmp/tvm-service.log"

print_test_header "Operational Hours Compliance" "11"

# Parse configuration
log_info "Loading configuration..."
load_config "$CONFIG_FILE"

# Override vehicle ID with test-specific ID
if [ -n "$TEST_VEHICLE_ID" ]; then
    VEHICLE_ID="$TEST_VEHICLE_ID"
    log_info "Using test vehicle ID: $VEHICLE_ID"
fi

# Check if operational hours are configured
OP_HOURS_ENABLED=$(grep -A 4 "operational_hours:" "$CONFIG_FILE" | grep "enabled:" | head -1 | awk '{print $2}' || echo "false")

log_info "Operational hours enabled: $OP_HOURS_ENABLED"

if [ "$OP_HOURS_ENABLED" != "true" ]; then
    log_warning "Operational hours not enabled in configuration"
    log_info "To test this feature, enable it in config.yaml:"
    echo "  upload:"
    echo "    operational_hours:"
    echo "      enabled: true"
    echo "      start: \"09:00\""
    echo "      end: \"17:00\""
    log_skip "Operational hours test (feature disabled)"
    print_test_summary
    exit 0
fi

# Get operational hours
OP_START=$(grep -A 8 "operational_hours:" "$CONFIG_FILE" | grep "start:" | head -1 | awk '{print $2}' | tr -d '"')
OP_END=$(grep -A 10 "operational_hours:" "$CONFIG_FILE" | grep "end:" | head -1 | awk '{print $2}' | tr -d '"')

log_info "Operational hours: $OP_START - $OP_END"

# Get current time
CURRENT_HOUR=$(date +%H:%M)
log_info "Current time: $CURRENT_HOUR"

# Determine if we're in operational hours
IN_OP_HOURS=false

# Simple time comparison (assumes HH:MM format)
if [[ "$CURRENT_HOUR" > "$OP_START" ]] && [[ "$CURRENT_HOUR" < "$OP_END" ]]; then
    IN_OP_HOURS=true
    log_info "Currently INSIDE operational hours"
else
    log_info "Currently OUTSIDE operational hours"
fi

# Create test directory
mkdir -p "$TEST_DIR/terminal"
log_success "Created test directory"

# Start service
log_info "Starting TVM upload service..."
if ! start_tvm_service "$CONFIG_FILE" "$SERVICE_LOG" "$TEST_DIR" "$TEST_VEHICLE_ID"; then
    log_error "Failed to start service"
    exit 1
fi

# Create test file
TEST_FILE="$TEST_DIR/terminal/ophours_test.log"
echo "Operational hours test - $(date)" > "$TEST_FILE"
log_success "Created test file"

# Wait for stability period
STABILITY_PERIOD=$(grep "file_stable_seconds:" "$CONFIG_FILE" | awk '{print $2}' || echo "60")
TOTAL_WAIT=$((STABILITY_PERIOD + 30))

log_info "Waiting for upload processing..."
wait_with_progress "$TOTAL_WAIT" "Upload processing"

# Check if file was uploaded or queued
TODAY=$(date +%Y-%m-%d)
S3_PATH="s3://${S3_BUCKET}/${VEHICLE_ID}/${TODAY}/terminal/ophours_test.log"

UPLOADED=$(aws s3 ls "$S3_PATH" --profile "$AWS_PROFILE" --region "$AWS_REGION" > /dev/null 2>&1 && echo "true" || echo "false")

# Verify behavior matches operational hours
if [ "$IN_OP_HOURS" = "true" ]; then
    # Should be uploaded
    if [ "$UPLOADED" = "true" ]; then
        log_success "File uploaded during operational hours (correct behavior)"
    else
        log_error "File NOT uploaded during operational hours (should be uploaded)"
    fi
else
    # Should be queued, not uploaded
    if [ "$UPLOADED" = "false" ]; then
        log_success "File NOT uploaded outside operational hours (correct behavior)"

        # Check if file is queued
        QUEUE_FILE=$(grep "queue.*file:" "$CONFIG_FILE" | awk '{print $2}' || echo "/tmp/upload_queue.json")
        log_info "Checking queue file: $QUEUE_FILE"

        if [ -f "$QUEUE_FILE" ]; then
            log_success "Queue file exists"

            if grep -q "ophours_test.log" "$QUEUE_FILE"; then
                log_success "File found in upload queue"
            else
                log_warning "File may not be in queue yet"
            fi
        else
            log_warning "Queue file not found (may use different location)"
        fi
    else
        log_error "File uploaded outside operational hours (should be queued)"
    fi
fi

# Check service logs for operational hours messages
log_info "Checking service logs for operational hours messages..."
if get_service_logs "$SERVICE_LOG" | grep -qi "operational.*hours\|queued\|schedule"; then
    log_success "Service logs show operational hours handling"
    get_service_logs "$SERVICE_LOG" | grep -i "operational.*hours\|queued\|schedule" | tail -5 | while read -r line; do
        echo "  $line"
    done
else
    log_info "No operational hours messages in logs"
fi

# Additional info
log_info "Operational Hours Summary:"
echo "  Current time: $CURRENT_HOUR"
echo "  Operational hours: $OP_START - $OP_END"
echo "  In operational hours: $IN_OP_HOURS"
echo "  File uploaded: $UPLOADED"

# ============================================
# SCHEDULE MODE TESTING
# ============================================
log_info ""
log_info "============================================"
log_info "Testing Schedule Modes (interval vs daily)"
log_info "============================================"

# Get schedule mode from config
SCHEDULE_MODE=$(grep -A 15 "schedule:" "$CONFIG_FILE" | grep "mode:" | head -1 | awk '{print $2}' | tr -d '"')
log_info "Current schedule mode: $SCHEDULE_MODE"

if [ "$SCHEDULE_MODE" = "interval" ]; then
    log_success "Schedule mode: interval detected"

    # Get interval settings
    INTERVAL_HOURS=$(grep -A 15 "schedule:" "$CONFIG_FILE" | grep "interval_hours:" | awk '{print $2}' || echo "0")
    INTERVAL_MINUTES=$(grep -A 15 "schedule:" "$CONFIG_FILE" | grep "interval_minutes:" | awk '{print $2}' || echo "0")

    TOTAL_INTERVAL_MIN=$((INTERVAL_HOURS * 60 + INTERVAL_MINUTES))
    log_info "Upload interval: ${INTERVAL_HOURS}h ${INTERVAL_MINUTES}m (${TOTAL_INTERVAL_MIN} minutes)"

    if [ "$TOTAL_INTERVAL_MIN" -ge 5 ] && [ "$TOTAL_INTERVAL_MIN" -le 1440 ]; then
        log_success "Interval within valid range (5 min - 24 hours)"
    else
        log_error "Interval outside valid range: ${TOTAL_INTERVAL_MIN} minutes"
    fi

    # Check logs for interval scheduling
    if get_service_logs "$SERVICE_LOG" | grep -qi "interval\|next.*upload"; then
        log_success "Service logs show interval scheduling"
        get_service_logs "$SERVICE_LOG" | grep -i "interval\|next.*upload" | tail -3 | while read -r line; do
            echo "  $line"
        done
    fi

elif [ "$SCHEDULE_MODE" = "daily" ]; then
    log_success "Schedule mode: daily detected"

    # Get daily time setting
    DAILY_TIME=$(grep -A 15 "schedule:" "$CONFIG_FILE" | grep "daily_time:" | awk '{print $2}' | tr -d '"')
    log_info "Daily upload time: $DAILY_TIME"

    # Validate time format (HH:MM)
    if echo "$DAILY_TIME" | grep -qE "^[0-2][0-9]:[0-5][0-9]$"; then
        log_success "Daily time format valid (HH:MM)"
    else
        log_error "Daily time format invalid: $DAILY_TIME"
    fi

    # Check logs for daily scheduling
    if get_service_logs "$SERVICE_LOG" | grep -qi "daily\|scheduled.*upload"; then
        log_success "Service logs show daily scheduling"
        get_service_logs "$SERVICE_LOG" | grep -i "daily\|scheduled.*upload" | tail -3 | while read -r line; do
            echo "  $line"
        done
    fi

else
    log_warning "Unknown schedule mode: $SCHEDULE_MODE"
fi

# TEST: Verify batch_upload setting
BATCH_UPLOAD=$(grep -A 20 "batch_upload:" "$CONFIG_FILE" | grep "enabled:" | head -1 | awk '{print $2}' || echo "false")
log_info "Batch upload enabled: $BATCH_UPLOAD"

if [ "$BATCH_UPLOAD" = "true" ]; then
    log_success "Batch upload enabled (uploads entire queue on trigger)"
else
    log_info "Batch upload disabled (uploads only triggered file)"
fi

# Display schedule configuration summary
log_info "Schedule Configuration Summary:"
echo "  Mode: $SCHEDULE_MODE"
if [ "$SCHEDULE_MODE" = "interval" ]; then
    echo "  Interval: ${INTERVAL_HOURS}h ${INTERVAL_MINUTES}m"
elif [ "$SCHEDULE_MODE" = "daily" ]; then
    echo "  Daily time: $DAILY_TIME"
fi
echo "  Batch upload: $BATCH_UPLOAD"
echo "  Operational hours: $OP_HOURS_ENABLED ($OP_START - $OP_END)"

# Cleanup
log_info "Cleaning up..."
stop_tvm_service
rm -rf "$TEST_DIR"

# Print summary
print_test_summary

# Test result
if [ $TESTS_FAILED -eq 0 ]; then
    log_success "TEST 11: PASSED - Operational hours & schedule modes working correctly"
    exit 0
else
    log_error "TEST 11: FAILED - See errors above"
    exit 1
fi
