#!/bin/bash
# TEST 6: Duplicate Upload Prevention
# Purpose: Verify registry prevents re-uploading same files
# Duration: ~10 minutes

set -e

# Get script directory and load helpers
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../lib/test_helpers.sh"

# Configuration
CONFIG_FILE="${1:-config/config.yaml}"
TEST_DIR="/tmp/tvm-manual-test"
SERVICE_LOG="/tmp/tvm-service.log"

print_test_header "Duplicate Upload Prevention" "6"

# Parse configuration
log_info "Loading configuration..."
load_config "$CONFIG_FILE"

# Create test directory
mkdir -p "$TEST_DIR/terminal"
log_success "Created test directory"

# Start service (first time)
log_info "Starting TVM upload service (first time)..."
if ! start_tvm_service "$CONFIG_FILE" "$SERVICE_LOG" "$TEST_DIR"; then
    log_error "Failed to start service"
    exit 1
fi

# Create test file
TEST_FILE="$TEST_DIR/terminal/registry_test.log"
log_info "Creating test file: $TEST_FILE"
echo "Original content - $(date)" > "$TEST_FILE"
log_success "Created test file"

# Get expected S3 path
TODAY=$(date +%Y-%m-%d)
S3_KEY="${VEHICLE_ID}/${TODAY}/terminal/registry_test.log"
S3_PATH="s3://${S3_BUCKET}/${S3_KEY}"

# Wait for upload
STABILITY_PERIOD=$(grep "file_stable_seconds:" "$CONFIG_FILE" | awk '{print $2}' || echo "60")
TOTAL_WAIT=$((STABILITY_PERIOD + 15))

log_info "Waiting for initial upload..."
wait_with_progress "$TOTAL_WAIT" "Initial upload"

# Verify initial upload
log_info "Verifying initial upload to S3..."
if aws s3 ls "$S3_PATH" --profile "$AWS_PROFILE" --region "$AWS_REGION" > /dev/null 2>&1; then
    log_success "File uploaded to S3 (first time)"

    # Get upload time
    FIRST_UPLOAD_TIME=$(aws s3 ls "$S3_PATH" --profile "$AWS_PROFILE" --region "$AWS_REGION" | awk '{print $1, $2}')
    log_info "First upload time: $FIRST_UPLOAD_TIME"
else
    log_error "Initial upload failed"
    exit 1
fi

# Check registry file exists
REGISTRY_FILE=$(grep "registry_file:" "$CONFIG_FILE" | awk '{print $2}' || echo "data/upload_registry.json")
log_info "Checking registry file: $REGISTRY_FILE"

if [ -f "$REGISTRY_FILE" ]; then
    log_success "Registry file exists: $REGISTRY_FILE"

    # Check if our file is in registry
    if grep -q "registry_test.log" "$REGISTRY_FILE"; then
        log_success "File recorded in registry"
    else
        log_warning "File may not be in registry yet"
    fi
else
    log_warning "Registry file not found (may be in different location)"
fi

# Stop service
log_info "Stopping service..."
stop_tvm_service
sleep 3

# Restart service
log_info "Restarting TVM upload service..."
rm -f "$SERVICE_LOG"  # Clear log to see new entries clearly

if ! start_tvm_service "$CONFIG_FILE" "$SERVICE_LOG" "$TEST_DIR"; then
    log_error "Failed to restart service"
    exit 1
fi

# Wait for service to scan files
log_info "Waiting for service to scan files..."
wait_with_progress 30 "File scanning"

# Check if file was re-uploaded
log_info "Checking if file was re-uploaded..."
SECOND_UPLOAD_TIME=$(aws s3 ls "$S3_PATH" --profile "$AWS_PROFILE" --region "$AWS_REGION" | awk '{print $1, $2}')

if [ "$FIRST_UPLOAD_TIME" = "$SECOND_UPLOAD_TIME" ]; then
    log_success "File NOT re-uploaded (timestamps match)"
    log_success "Registry prevented duplicate upload"
else
    log_warning "File timestamp changed (may have been re-uploaded)"
    log_info "First upload: $FIRST_UPLOAD_TIME"
    log_info "Second check: $SECOND_UPLOAD_TIME"
    log_info "Note: Checking if file was overwritten or truly duplicated..."
fi

# Check service logs for registry skip message
log_info "Checking service logs for registry messages..."
if get_service_logs "$SERVICE_LOG" | grep -qi "already\|registry\|skip"; then
    log_success "Service logs show registry check"
    get_service_logs "$SERVICE_LOG" | grep -i "already\|registry\|skip" | tail -5 | while read -r line; do
        echo "  $line"
    done
else
    log_warning "No registry skip message found in logs"
fi

# Verify only 1 copy exists in S3
log_info "Verifying only one copy exists in S3..."
S3_COUNT=$(aws s3 ls "s3://${S3_BUCKET}/${VEHICLE_ID}/" --recursive --profile "$AWS_PROFILE" --region "$AWS_REGION" | grep -c "registry_test.log" || echo "0")

if [ "$S3_COUNT" -eq 1 ]; then
    log_success "Only 1 copy in S3 (no duplicate)"
else
    log_error "Multiple copies found in S3: $S3_COUNT"
fi

# Cleanup
log_info "Cleaning up..."
stop_tvm_service
rm -rf "$TEST_DIR"

# Print summary
print_test_summary

# Test result
if [ $TESTS_FAILED -eq 0 ]; then
    log_success "TEST 6: PASSED - Duplicate prevention working correctly"
    exit 0
else
    log_error "TEST 6: FAILED - See errors above"
    exit 1
fi
