#!/bin/bash
# TEST 15: Basic File Upload
# Purpose: Verify basic file monitoring and S3 upload functionality
# Duration: ~10 minutes

set -e

# Get script directory and load helpers
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../../lib/test_helpers.sh"

# Configuration
CONFIG_FILE="${1:-config/config.yaml}"
TEST_VEHICLE_ID="${2}"  # Test vehicle ID passed from run_manual_tests.sh
TEST_DIR="/tmp/tvm-manual-test"
SERVICE_LOG="/tmp/tvm-service.log"

print_test_header "Basic File Upload" "15"

# Add trap handler to ensure cleanup on exit
cleanup_test_15() {
    log_info "Running Test 15 cleanup handler..."
    stop_tvm_service 2>/dev/null || true
    rm -rf "$TEST_DIR" 2>/dev/null || true
}
trap cleanup_test_15 EXIT

# Parse configuration
log_info "Loading configuration..."
load_config "$CONFIG_FILE"

# Override vehicle ID with test-specific ID
if [ -n "$TEST_VEHICLE_ID" ]; then
    VEHICLE_ID="$TEST_VEHICLE_ID"
    log_info "Using test vehicle ID: $VEHICLE_ID"
fi

if [ -z "$VEHICLE_ID" ] || [ -z "$S3_BUCKET" ] || [ -z "$AWS_REGION" ]; then
    log_error "Failed to load configuration. Check $CONFIG_FILE"
    exit 1
fi

# Create test directory
TEST_TERMINAL_DIR="$TEST_DIR/terminal"
mkdir -p "$TEST_TERMINAL_DIR"
log_success "Created test directory: $TEST_TERMINAL_DIR"

# Check operational hours (critical for upload tests)
check_operational_hours "$CONFIG_FILE"

# Start service with test directory
log_info "Starting TVM upload service..."
if ! start_tvm_service "$CONFIG_FILE" "$SERVICE_LOG" "$TEST_DIR" "$TEST_VEHICLE_ID"; then
    log_error "Failed to start service. Check logs:"
    get_service_logs "$SERVICE_LOG" 20
    exit 1
fi

# Create test file
TEST_FILE="$TEST_TERMINAL_DIR/test1.log"
log_info "Creating test file: $TEST_FILE"
echo "Test upload at $(date)" > "$TEST_FILE"
log_success "Created test file: $TEST_FILE"

# Get expected S3 path
TODAY=$(date +%Y-%m-%d)
S3_KEY="${VEHICLE_ID}/${TODAY}/terminal/test1.log"
S3_PATH="s3://${S3_BUCKET}/${S3_KEY}"

log_info "Expected S3 path: $S3_PATH"

# Wait for stability period (default 60 seconds)
STABILITY_PERIOD=$(grep "file_stable_seconds:" "$CONFIG_FILE" | awk '{print $2}' || echo "60")
log_info "Waiting for file stability period (${STABILITY_PERIOD}s)..."
wait_with_progress "$STABILITY_PERIOD" "Stability period"

# Additional wait for upload processing
wait_with_progress 10 "Upload processing"

# Check service logs
log_info "Checking service logs for upload confirmation..."
get_service_logs "$SERVICE_LOG" 20 | tail -20

# Verify file detected
if get_service_logs "$SERVICE_LOG" | grep -q "test1.log"; then
    log_success "File detected in service logs"
else
    log_error "File not detected in service logs"
fi

# Verify S3 upload
log_info "Verifying S3 upload..."
if aws s3 ls "$S3_PATH" --profile "$AWS_PROFILE" --region "$AWS_REGION" > /dev/null 2>&1; then
    log_success "File uploaded to S3: $S3_PATH"

    # Get file details
    FILE_SIZE=$(aws s3 ls "$S3_PATH" --profile "$AWS_PROFILE" --region "$AWS_REGION" | awk '{print $3}')
    log_info "Uploaded file size: ${FILE_SIZE} bytes"
else
    log_error "File not found in S3: $S3_PATH"
    log_info "Listing S3 bucket contents:"
    aws s3 ls "s3://${S3_BUCKET}/${VEHICLE_ID}/${TODAY}/" --recursive --profile "$AWS_PROFILE" --region "$AWS_REGION" || true
fi

# Verify S3 key pattern
log_info "Verifying S3 key pattern..."
if echo "$S3_KEY" | grep -qE "^[^/]+/[0-9]{4}-[0-9]{2}-[0-9]{2}/[^/]+/[^/]+$"; then
    log_success "S3 key follows correct pattern: {vehicle_id}/{YYYY-MM-DD}/{source}/{filename}"
else
    log_error "S3 key pattern incorrect: $S3_KEY"
fi

# Check if local file was deleted (if deletion enabled)
DELETE_ENABLED=$(grep "delete_after_upload:" "$CONFIG_FILE" | awk '{print $2}' || echo "false")
log_info "Delete after upload setting: $DELETE_ENABLED"

if [ "$DELETE_ENABLED" = "true" ]; then
    if [ -f "$TEST_FILE" ]; then
        log_warning "Local file still exists (deletion enabled but not completed)"
    else
        log_success "Local file deleted after upload"
    fi
else
    log_info "File deletion disabled - skipping deletion check"
fi

# Cleanup
log_info "Cleaning up..."
stop_tvm_service
rm -f "$TEST_FILE"

# Print summary
print_test_summary

# Test result
if [ $TESTS_FAILED -eq 0 ]; then
    log_success "TEST 15: PASSED - Basic file upload working correctly"
    exit 0
else
    log_error "TEST 15: FAILED - See errors above"
    exit 1
fi
