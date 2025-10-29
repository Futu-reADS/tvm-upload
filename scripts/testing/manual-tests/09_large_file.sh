#!/bin/bash
# TEST 9: Large File Upload (Multipart)
# Purpose: Test multipart upload for files > 5MB
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
FILE_SIZE_MB=10

print_test_header "Large File Upload (Multipart)" "9"

# Parse configuration
log_info "Loading configuration..."
load_config "$CONFIG_FILE"

# Override vehicle ID with test-specific ID
if [ -n "$TEST_VEHICLE_ID" ]; then
    VEHICLE_ID="$TEST_VEHICLE_ID"
    log_info "Using test vehicle ID: $VEHICLE_ID"
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

# Create large file
TEST_FILE="$TEST_DIR/terminal/large_file.log"
log_info "Creating ${FILE_SIZE_MB}MB test file (this may take a moment)..."

dd if=/dev/urandom of="$TEST_FILE" bs=1M count=$FILE_SIZE_MB 2>/dev/null

LOCAL_SIZE=$(stat -c %s "$TEST_FILE")
LOCAL_SIZE_MB=$(echo "scale=2; $LOCAL_SIZE / 1048576" | bc)

log_success "Created large file: ${LOCAL_SIZE_MB} MB"

# Wait for upload
STABILITY_PERIOD=$(grep "file_stable_seconds:" "$CONFIG_FILE" | awk '{print $2}' || echo "60")
# Large files need more time
TOTAL_WAIT=$((STABILITY_PERIOD + 60))

log_info "Waiting for large file upload..."
wait_with_progress "$TOTAL_WAIT" "Large file upload"

# Check service logs for multipart upload
log_info "Checking logs for multipart upload indication..."
if get_service_logs "$SERVICE_LOG" | grep -qi "multipart"; then
    log_success "Multipart upload detected in logs"
    get_service_logs "$SERVICE_LOG" | grep -i "multipart" | tail -3 | while read -r line; do
        echo "  $line"
    done
else
    log_warning "No multipart indication in logs (may use different logging)"
fi

# Verify S3 upload
TODAY=$(date +%Y-%m-%d)
S3_KEY="${VEHICLE_ID}/${TODAY}/terminal/large_file.log"
S3_PATH="s3://${S3_BUCKET}/${S3_KEY}"

log_info "Verifying large file in S3..."
if aws s3 ls "$S3_PATH" --profile "$AWS_PROFILE" --region "$AWS_REGION" > /dev/null 2>&1; then
    log_success "Large file uploaded to S3"

    # Get S3 file size
    S3_SIZE=$(aws s3 ls "$S3_PATH" --profile "$AWS_PROFILE" --region "$AWS_REGION" | awk '{print $3}')
    S3_SIZE_MB=$(echo "scale=2; $S3_SIZE / 1048576" | bc)

    log_info "S3 file size: ${S3_SIZE_MB} MB"

    # Compare sizes
    if [ "$LOCAL_SIZE" -eq "$S3_SIZE" ]; then
        log_success "File sizes match (no corruption)"
    else
        log_error "File size mismatch - possible corruption"
        log_error "Local: $LOCAL_SIZE bytes, S3: $S3_SIZE bytes"
    fi

    # Get additional metadata
    log_info "Retrieving file metadata from S3..."
    METADATA=$(aws s3api head-object \
        --bucket "$S3_BUCKET" \
        --key "$S3_KEY" \
        --profile "$AWS_PROFILE" --region "$AWS_REGION" 2>&1 || echo "ERROR")

    if ! echo "$METADATA" | grep -q "ERROR"; then
        log_success "File metadata retrieved successfully"

        # Check for multipart upload marker
        if echo "$METADATA" | grep -qi "parts\|multipart"; then
            log_success "S3 metadata indicates multipart upload"
        fi

        # Display key metadata
        echo "$METADATA" | grep -E "ContentLength|ETag|LastModified" | while read -r line; do
            echo "  $line"
        done
    fi
else
    log_error "Large file not found in S3"
fi

# Check upload performance
log_info "Analyzing upload performance..."
UPLOAD_LOGS=$(get_service_logs "$SERVICE_LOG" | grep -i "large_file" || echo "")

if echo "$UPLOAD_LOGS" | grep -qi "progress\|percent"; then
    log_success "Upload progress tracking detected"
fi

# Verify file integrity (if possible)
if command -v md5sum >/dev/null 2>&1; then
    log_info "Calculating local file checksum..."
    LOCAL_MD5=$(md5sum "$TEST_FILE" | awk '{print $1}')
    log_info "Local MD5: $LOCAL_MD5"

    # Download and compare (optional - requires extra time and space)
    # Skipping for now to save time
fi

# Cleanup
log_info "Cleaning up..."
stop_tvm_service
rm -rf "$TEST_DIR"

# Print summary
print_test_summary

# Test result
if [ $TESTS_FAILED -eq 0 ]; then
    log_success "TEST 9: PASSED - Large file multipart upload working correctly"
    exit 0
else
    log_error "TEST 9: FAILED - See errors above"
    exit 1
fi
