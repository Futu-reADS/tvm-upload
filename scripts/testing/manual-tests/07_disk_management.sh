#!/bin/bash
# TEST 7: Disk Space Management
# Purpose: Verify disk cleanup and management features
# Duration: ~15 minutes

set -e

# Get script directory and load helpers
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../../lib/test_helpers.sh"

# Configuration
CONFIG_FILE="${1:-config/config.yaml}"
TEST_DIR="/tmp/tvm-manual-test"
SERVICE_LOG="/tmp/tvm-service.log"

print_test_header "Disk Space Management" "7"

# Parse configuration
log_info "Loading configuration..."
load_config "$CONFIG_FILE"

# Create test directory
mkdir -p "$TEST_DIR/terminal"
log_success "Created test directory"

# Check deletion configuration
DELETE_ENABLED=$(grep -A 10 "after_upload:" "$CONFIG_FILE" | grep "enabled:" | head -1 | awk '{print $2}' || echo "false")
KEEP_DAYS=$(grep -A 10 "after_upload:" "$CONFIG_FILE" | grep "keep_days:" | awk '{print $2}' || echo "0")
log_info "Delete after upload: $DELETE_ENABLED (keep_days: $KEEP_DAYS)"

# Start service
log_info "Starting TVM upload service..."
if ! start_tvm_service "$CONFIG_FILE" "$SERVICE_LOG" "$TEST_DIR"; then
    log_error "Failed to start service"
    exit 1
fi

# TEST: Delete after upload
if [ "$DELETE_ENABLED" = "true" ]; then
    log_info "Testing delete after upload..."

    TEST_FILE="$TEST_DIR/terminal/delete_test.log"
    echo "Delete me after upload - $(date)" > "$TEST_FILE"
    log_success "Created test file: $TEST_FILE"

    # Wait for upload
    STABILITY_PERIOD=$(grep "file_stable_seconds:" "$CONFIG_FILE" | awk '{print $2}' || echo "60")
    TOTAL_WAIT=$((STABILITY_PERIOD + 20))

    wait_with_progress "$TOTAL_WAIT" "Upload and deletion"

    # Verify file behavior based on keep_days setting
    if [ "$KEEP_DAYS" -eq 0 ]; then
        # Should be deleted immediately
        if [ -f "$TEST_FILE" ]; then
            log_error "File still exists (should be deleted immediately with keep_days: 0)"
        else
            log_success "File deleted immediately after upload"
        fi
    else
        # Should be kept for keep_days
        if [ -f "$TEST_FILE" ]; then
            log_success "File kept after upload (keep_days: $KEEP_DAYS)"
            log_info "File will be deleted after $KEEP_DAYS days"
        else
            log_warning "File was deleted (expected to be kept for $KEEP_DAYS days)"
        fi
    fi

    # Verify file exists in S3
    TODAY=$(date +%Y-%m-%d)
    S3_PATH="s3://${S3_BUCKET}/${VEHICLE_ID}/${TODAY}/terminal/delete_test.log"

    if aws s3 ls "$S3_PATH" --profile "$AWS_PROFILE" --region "$AWS_REGION" > /dev/null 2>&1; then
        log_success "File exists in S3 (uploaded before deletion)"
    else
        log_error "File not found in S3"
    fi
else
    log_info "Delete after upload disabled - skipping deletion test"
fi

# TEST: Age-based cleanup
log_info "Testing age-based cleanup..."

# Create old file (10 days ago)
OLD_FILE="$TEST_DIR/terminal/very_old.log"
echo "Very old data" > "$OLD_FILE"

# Set file time to 10 days ago
touch -t $(date -d "10 days ago" +%Y%m%d0000) "$OLD_FILE" 2>/dev/null || log_warning "Could not set old timestamp"

FILE_AGE=$(find "$OLD_FILE" -mtime +9 2>/dev/null | wc -l)
if [ "$FILE_AGE" -gt 0 ]; then
    log_success "Old file created (>9 days old)"
else
    log_warning "File may not be old enough for cleanup test"
fi

# Check if age-based cleanup is enabled
AGE_CLEANUP=$(grep -A 10 "age_based:" "$CONFIG_FILE" | grep "enabled:" | head -1 | awk '{print $2}' || echo "false")
MAX_AGE=$(grep -A 10 "age_based:" "$CONFIG_FILE" | grep "max_age_days:" | awk '{print $2}' || echo "7")

log_info "Age-based cleanup: $AGE_CLEANUP (max age: $MAX_AGE days)"

if [ "$AGE_CLEANUP" = "true" ]; then
    log_info "Waiting for cleanup cycle..."
    wait_with_progress 30 "Cleanup processing"

    if [ -f "$OLD_FILE" ]; then
        log_warning "Old file still exists (cleanup may run on schedule)"
        log_info "File may be cleaned up in next scheduled cleanup cycle"
    else
        log_success "Old file cleaned up"
    fi
else
    log_info "Age-based cleanup disabled - skipping"
fi

# TEST: Disk space monitoring
log_info "Testing disk space monitoring..."

DISK_USAGE=$(df -h "$TEST_DIR" | tail -1 | awk '{print $5}' | tr -d '%')
log_info "Current disk usage: ${DISK_USAGE}%"

THRESHOLD=$(grep "warning_threshold:" "$CONFIG_FILE" | awk '{print $2}' || echo "0.85")
THRESHOLD_PCT=$(echo "$THRESHOLD * 100" | bc -l | cut -d'.' -f1)

log_info "Warning threshold: ${THRESHOLD_PCT}%"

if [ "$DISK_USAGE" -lt "$THRESHOLD_PCT" ]; then
    log_success "Disk usage below warning threshold"
else
    log_warning "Disk usage above warning threshold"
fi

# Check service logs for disk space warnings
if get_service_logs "$SERVICE_LOG" | grep -qi "disk\|space"; then
    log_info "Service monitors disk space:"
    get_service_logs "$SERVICE_LOG" | grep -i "disk\|space" | tail -3 | while read -r line; do
        echo "  $line"
    done
fi

# TEST: Reserved space
RESERVED_GB=$(grep "reserved_gb:" "$CONFIG_FILE" | awk '{print $2}' || echo "5")
log_info "Reserved disk space: ${RESERVED_GB} GB"

AVAILABLE_GB=$(df -BG "$TEST_DIR" | tail -1 | awk '{print $4}' | tr -d 'G')

if [ "$AVAILABLE_GB" -gt "$RESERVED_GB" ]; then
    log_success "Available space (${AVAILABLE_GB}GB) > reserved space (${RESERVED_GB}GB)"
else
    log_warning "Available space (${AVAILABLE_GB}GB) <= reserved space (${RESERVED_GB}GB)"
fi

# Cleanup
log_info "Cleaning up..."
stop_tvm_service
rm -rf "$TEST_DIR"

# Print summary
print_test_summary

# Test result
if [ $TESTS_FAILED -eq 0 ]; then
    log_success "TEST 7: PASSED - Disk space management working correctly"
    exit 0
else
    log_error "TEST 7: FAILED - See errors above"
    exit 1
fi
