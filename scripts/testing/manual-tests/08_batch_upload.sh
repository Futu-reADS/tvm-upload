#!/bin/bash
# TEST 8: Batch Upload Performance
# Purpose: Test handling multiple files simultaneously
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
NUM_FILES=20

print_test_header "Batch Upload Performance" "8"

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

# Record start time
START_TIME=$(date +%s)
log_info "Batch upload test start time: $(date)"

# Create multiple files at once
log_info "Creating $NUM_FILES files simultaneously..."
for i in $(seq 1 $NUM_FILES); do
    TEST_FILE="$TEST_DIR/terminal/batch_$i.log"
    echo "Batch file $i content - $(date)" > "$TEST_FILE"
done
log_success "Created $NUM_FILES test files"

# Wait for files to stabilize and upload
STABILITY_PERIOD=$(grep "file_stable_seconds:" "$CONFIG_FILE" | awk '{print $2}' || echo "60")
# Add extra time for batch processing
TOTAL_WAIT=$((STABILITY_PERIOD + 60))

log_info "Waiting for batch upload (this may take a while)..."
wait_with_progress "$TOTAL_WAIT" "Batch upload processing"

# Record end time
END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))
log_info "Total batch upload duration: ${DURATION} seconds"

# Verify all files uploaded to S3
TODAY=$(date +%Y-%m-%d)
S3_PREFIX="s3://${S3_BUCKET}/${VEHICLE_ID}/${TODAY}/terminal/"

log_info "Verifying all files uploaded to S3..."
S3_COUNT=$(aws s3 ls "$S3_PREFIX" --profile "$AWS_PROFILE" --region "$AWS_REGION" | grep -c "batch_" || echo "0")

log_info "Files found in S3: $S3_COUNT / $NUM_FILES"

if [ "$S3_COUNT" -eq "$NUM_FILES" ]; then
    log_success "All $NUM_FILES files uploaded successfully"
elif [ "$S3_COUNT" -gt 0 ]; then
    log_warning "Only $S3_COUNT of $NUM_FILES files uploaded"
    MISSING=$((NUM_FILES - S3_COUNT))
    log_warning "Missing $MISSING files"
else
    log_error "No batch files found in S3"
fi

# List uploaded files
log_info "Uploaded files:"
aws s3 ls "$S3_PREFIX" --profile "$AWS_PROFILE" --region "$AWS_REGION" | grep "batch_" | while read -r line; do
    echo "  $line"
done

# Check for any missing files
log_info "Checking for missing files..."
MISSING_FILES=0
for i in $(seq 1 $NUM_FILES); do
    if ! aws s3 ls "${S3_PREFIX}batch_$i.log" --profile "$AWS_PROFILE" --region "$AWS_REGION" > /dev/null 2>&1; then
        log_warning "Missing: batch_$i.log"
        MISSING_FILES=$((MISSING_FILES + 1))
    fi
done

if [ "$MISSING_FILES" -eq 0 ]; then
    log_success "No missing files - batch upload complete"
else
    log_error "Missing $MISSING_FILES files in S3"
fi

# Performance analysis
AVG_TIME=$(echo "scale=2; $DURATION / $NUM_FILES" | bc)
log_info "Average time per file: ${AVG_TIME} seconds"

if [ "$DURATION" -lt 300 ]; then
    log_success "Batch upload completed in reasonable time (< 5 min)"
elif [ "$DURATION" -lt 600 ]; then
    log_warning "Batch upload slower than expected (5-10 min)"
else
    log_error "Batch upload too slow (> 10 min)"
fi

# Check service logs for batch processing
log_info "Checking service logs for batch processing..."
UPLOAD_COUNT=$(get_service_logs "$SERVICE_LOG" | grep -c "uploaded\|success" || echo "0")
log_info "Upload log entries: $UPLOAD_COUNT"

# Check system responsiveness
log_info "Checking system responsiveness..."
if check_service_health; then
    log_success "Service remains responsive after batch upload"
else
    log_error "Service may have crashed during batch upload"
fi

# Cleanup
log_info "Cleaning up..."
stop_tvm_service
rm -rf "$TEST_DIR"

# Print summary
print_test_summary

# Test result
if [ $TESTS_FAILED -eq 0 ]; then
    log_success "TEST 8: PASSED - Batch upload performance acceptable"
    exit 0
else
    log_error "TEST 8: FAILED - See errors above"
    exit 1
fi
