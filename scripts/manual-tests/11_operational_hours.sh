#!/bin/bash
# TEST 11: Operational Hours Compliance
# Purpose: Verify uploads only happen during configured hours
# Duration: ~5 minutes
# Note: This test is optional and may need configuration changes

set -e

# Get script directory and load helpers
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../lib/test_helpers.sh"

# Configuration
CONFIG_FILE="${1:-config/config.yaml}"
TEST_DIR="/tmp/tvm-manual-test"
SERVICE_LOG="/tmp/tvm-service.log"

print_test_header "Operational Hours Compliance" "11"

# Parse configuration
log_info "Loading configuration..."
load_config "$CONFIG_FILE"

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
if ! start_tvm_service "$CONFIG_FILE" "$SERVICE_LOG" "$TEST_DIR"; then
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
log_info "Summary:"
echo "  Current time: $CURRENT_HOUR"
echo "  Operational hours: $OP_START - $OP_END"
echo "  In operational hours: $IN_OP_HOURS"
echo "  File uploaded: $UPLOADED"

# Cleanup
log_info "Cleaning up..."
stop_tvm_service
rm -rf "$TEST_DIR"

# Print summary
print_test_summary

# Test result
if [ $TESTS_FAILED -eq 0 ]; then
    log_success "TEST 11: PASSED - Operational hours compliance working correctly"
    exit 0
else
    log_error "TEST 11: FAILED - See errors above"
    exit 1
fi
