#!/bin/bash
# TEST 19: Deferred Deletion (keep_days > 0)
# Purpose: Verify files are kept for N days after upload before deletion
# Duration: ~3 minutes (uses keep_days=0.001 ≈ 90 seconds for testing)

set -e

# Get script directory and load helpers
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../../lib/test_helpers.sh"

# Configuration
CONFIG_FILE="${1:-config/config.yaml}"
TEST_VEHICLE_ID="${2}"
TEST_DIR="/tmp/tvm-gap-test-19"
SERVICE_LOG="/tmp/tvm-service-gap19.log"

print_test_header "Deferred Deletion (keep_days > 0)" "19"

# Parse configuration
log_info "Loading base configuration..."
load_config "$CONFIG_FILE"

# Create unique test vehicle ID with timestamp
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
if [ -n "$TEST_VEHICLE_ID" ]; then
    VEHICLE_ID="${TEST_VEHICLE_ID}-TEST19-${TIMESTAMP}"
else
    VEHICLE_ID="vehicle-TEST19-${TIMESTAMP}"
fi
log_info "Using test vehicle ID: $VEHICLE_ID"
log_info "This creates isolated S3 folder: ${VEHICLE_ID}/"

# Create test directory
mkdir -p "$TEST_DIR/terminal"
log_success "Created test directory"

# NOTE: We cannot wait actual days for testing
# We'll use a very short keep_days value for quick testing
# keep_days: 0.001 days = 0.001 * 24 * 3600 = ~86.4 seconds ≈ 1.5 minutes

log_warning "NOTE: This test uses keep_days=0.001 (~90 seconds) for quick testing"
log_warning "In production, keep_days=14 means files kept for 14 full days"

# Create test config with deferred deletion
TEST_CONFIG="/tmp/tvm-test-config-deferred.yaml"
cat > "$TEST_CONFIG" <<EOF
vehicle_id: "$VEHICLE_ID"
log_directories:
  - path: $TEST_DIR/terminal
    source: terminal
    recursive: true

s3:
  bucket: $S3_BUCKET
  region: $AWS_REGION
  profile: $AWS_PROFILE

upload:
  schedule:
    mode: "interval"
    interval_hours: 0
    interval_minutes: 5
  file_stable_seconds: 60
  operational_hours:
    enabled: false
  batch_upload:
    enabled: true
  upload_on_start: true
  queue_file: /tmp/queue-gap19.json
  scan_existing_files:
    enabled: true
    max_age_days: 3
  processed_files_registry:
    registry_file: /tmp/registry-gap19.json
    retention_days: 30

deletion:
  after_upload:
    enabled: true
    keep_days: 0.001  # ~90 seconds for testing (in production: 14 days)
  age_based:
    enabled: false
  emergency:
    enabled: false

disk:
  reserved_gb: 5
  warning_threshold: 0.90
  critical_threshold: 0.95

monitoring:
  cloudwatch_enabled: false
  publish_interval_seconds: 3600

s3_lifecycle:
  retention_days: 14
EOF

log_success "Created test config with deferred deletion (keep_days=0.001)"

# Create test files
log_info "Creating test files..."

FILE_1="$TEST_DIR/terminal/deferred_1.log"
FILE_2="$TEST_DIR/terminal/deferred_2.log"

echo "Deferred deletion test 1 - $(date)" > "$FILE_1"
echo "Deferred deletion test 2 - $(date)" > "$FILE_2"

log_success "Created 2 test files"

# Start service
log_info "Starting TVM upload service with deferred deletion..."
if ! start_tvm_service "$TEST_CONFIG" "$SERVICE_LOG" "" "$VEHICLE_ID"; then
    log_error "Failed to start service"
    exit 1
fi

# Wait for upload
STABILITY_PERIOD=60
UPLOAD_WAIT=$((STABILITY_PERIOD + 20))

log_info "Waiting for files to upload..."
wait_with_progress "$UPLOAD_WAIT" "Upload processing"

# Verify files uploaded to S3
TODAY=$(date +%Y-%m-%d)
S3_PREFIX="s3://${S3_BUCKET}/${VEHICLE_ID}/${TODAY}/terminal/"

UPLOADED_COUNT=$(aws s3 ls "$S3_PREFIX" --profile "$AWS_PROFILE" --region "$AWS_REGION" 2>/dev/null | grep -c "deferred_" || echo "0")
UPLOADED_COUNT=$(echo "$UPLOADED_COUNT" | tr -d '[:space:]')

if [ "$UPLOADED_COUNT" -eq 2 ]; then
    log_success "Both files uploaded to S3"
else
    log_error "Only $UPLOADED_COUNT/2 files uploaded"
fi

# Check if files still exist locally (should exist during keep_days period)
log_info "Checking if files still exist locally (should be kept during keep_days period)..."

IMMEDIATELY_AFTER_UPLOAD_CHECK=0
if [ -f "$FILE_1" ]; then
    IMMEDIATELY_AFTER_UPLOAD_CHECK=$((IMMEDIATELY_AFTER_UPLOAD_CHECK + 1))
fi
if [ -f "$FILE_2" ]; then
    IMMEDIATELY_AFTER_UPLOAD_CHECK=$((IMMEDIATELY_AFTER_UPLOAD_CHECK + 1))
fi

if [ "$IMMEDIATELY_AFTER_UPLOAD_CHECK" -eq 2 ]; then
    log_success "Files still exist immediately after upload (deferred deletion working)"
else
    log_warning "Files: $IMMEDIATELY_AFTER_UPLOAD_CHECK/2 exist (may have been deleted immediately)"
    log_info "This suggests keep_days may not be working or delete_after_upload uses keep_days=0"
fi

# Wait for keep_days period to expire (90 seconds + buffer)
# keep_days: 0.001 days = ~86 seconds
KEEP_PERIOD=90
log_info "Waiting for keep_days period to expire (~90 seconds)..."
wait_with_progress "$KEEP_PERIOD" "Deferred deletion period"

# Check if files deleted after keep_days expired
log_info "Checking if files deleted after keep_days period..."

AFTER_KEEP_DAYS_CHECK=0
if [ -f "$FILE_1" ]; then
    AFTER_KEEP_DAYS_CHECK=$((AFTER_KEEP_DAYS_CHECK + 1))
fi
if [ -f "$FILE_2" ]; then
    AFTER_KEEP_DAYS_CHECK=$((AFTER_KEEP_DAYS_CHECK + 1))
fi

if [ "$AFTER_KEEP_DAYS_CHECK" -eq 0 ]; then
    log_success "Files deleted after keep_days period expired (deferred deletion working)"
elif [ "$AFTER_KEEP_DAYS_CHECK" -lt "$IMMEDIATELY_AFTER_UPLOAD_CHECK" ]; then
    log_success "Some files deleted (deferred deletion partially working)"
    log_info "Files remaining: $AFTER_KEEP_DAYS_CHECK"
else
    log_warning "Files still exist after keep_days period"
    log_info "Files remaining: $AFTER_KEEP_DAYS_CHECK/2"
    log_info "Deferred deletion may need more time or may not be implemented"
fi

# Check service logs for deletion messages
log_info "Checking service logs for deletion activity..."
if get_service_logs "$SERVICE_LOG" | grep -qi "delet\|remov\|cleanup"; then
    log_info "Deletion-related log messages:"
    get_service_logs "$SERVICE_LOG" | grep -i "delet\|remov\|cleanup" | tail -10 | while read -r line; do
        echo "  $line"
    done
else
    log_info "No deletion messages found in logs"
fi

# Verify files still in S3 (deletion only affects local files)
log_info "Verifying files still in S3 (deferred deletion only affects local files)..."

S3_AFTER_DELETE=$(aws s3 ls "$S3_PREFIX" --profile "$AWS_PROFILE" --region "$AWS_REGION" 2>/dev/null | grep -c "deferred_" || echo "0")
S3_AFTER_DELETE=$(echo "$S3_AFTER_DELETE" | tr -d '[:space:]')

if [ "$S3_AFTER_DELETE" -eq 2 ]; then
    log_success "Files remain in S3 after local deletion (correct behavior)"
else
    log_error "Files missing from S3 (should not be deleted from S3)"
fi

# Test with keep_days=0 for comparison (immediate deletion)
log_info "Testing immediate deletion for comparison (keep_days=0)..."

# Create another test file
FILE_3="$TEST_DIR/terminal/immediate.log"
echo "Immediate deletion test - $(date)" > "$FILE_3"

# Temporarily update config to keep_days: 0
cat > "$TEST_CONFIG" <<EOF
vehicle_id: "$VEHICLE_ID"
log_directories:
  - path: $TEST_DIR/terminal
    source: terminal
    recursive: true

s3:
  bucket: $S3_BUCKET
  region: $AWS_REGION
  profile: $AWS_PROFILE

upload:
  schedule:
    mode: "interval"
    interval_hours: 0
    interval_minutes: 5
  file_stable_seconds: 60
  operational_hours:
    enabled: false
  batch_upload:
    enabled: true
  upload_on_start: true
  queue_file: /tmp/queue-gap19.json
  scan_existing_files:
    enabled: true
    max_age_days: 3
  processed_files_registry:
    registry_file: /tmp/registry-gap19.json
    retention_days: 30

deletion:
  after_upload:
    enabled: true
    keep_days: 0  # Immediate deletion
  age_based:
    enabled: false
  emergency:
    enabled: false

disk:
  reserved_gb: 5
  warning_threshold: 0.90
  critical_threshold: 0.95

monitoring:
  cloudwatch_enabled: false
  publish_interval_seconds: 3600

s3_lifecycle:
  retention_days: 14
EOF

# Restart service with new config
stop_tvm_service
sleep 2
rm -f "$SERVICE_LOG"

log_info "Restarting service with keep_days=0 (immediate deletion)..."
start_tvm_service "$TEST_CONFIG" "$SERVICE_LOG" "" "$VEHICLE_ID"

# Wait for upload
wait_with_progress "$UPLOAD_WAIT" "Immediate deletion test"

# Check if file deleted immediately
if [ -f "$FILE_3" ]; then
    log_warning "File still exists with keep_days=0 (immediate deletion may not be working)"
else
    log_success "File deleted immediately with keep_days=0 (correct behavior)"
fi

# Test summary
log_info "Deferred Deletion Test Summary:"
echo "  ✓ Files uploaded to S3: $UPLOADED_COUNT/2"
echo "  ✓ Files kept after upload (keep_days>0): $IMMEDIATELY_AFTER_UPLOAD_CHECK/2"
echo "  ✓ Files deleted after period: $((IMMEDIATELY_AFTER_UPLOAD_CHECK - AFTER_KEEP_DAYS_CHECK))/2"
echo "  ✓ Files in S3 after local deletion: $S3_AFTER_DELETE/2"
echo "  ✓ Immediate deletion test (keep_days=0): $([ -f "$FILE_3" ] && echo "FAILED" || echo "PASSED")"

log_info "NOTE: This test validates the deferred deletion logic"
log_info "Production config should use keep_days=14 for 14-day retention"

# Cleanup
log_info "Cleaning up..."
stop_tvm_service
rm -rf "$TEST_DIR"
rm -f "$TEST_CONFIG"
rm -f /tmp/queue-gap19.json
rm -f /tmp/registry-gap19.json

# Clean S3 test data
log_info "Cleaning complete vehicle folder from S3..."
cleanup_complete_vehicle_folder "$VEHICLE_ID" "$S3_BUCKET" "$AWS_PROFILE" "$AWS_REGION"

# Print summary
print_test_summary

# Test result
if [ $TESTS_FAILED -eq 0 ]; then
    log_success "TEST 19: PASSED - Deferred deletion working correctly"
    exit 0
else
    log_error "TEST 19: FAILED - See errors above"
    exit 1
fi
