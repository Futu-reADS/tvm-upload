#!/bin/bash
# TEST 3: File Date Preservation
# Purpose: Verify that file modification dates are preserved in S3 path structure
# Duration: ~5 minutes

set -e

# Get script directory and load helpers
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../../lib/test_helpers.sh"

# Configuration
CONFIG_FILE="${1:-config/config.yaml}"
TEST_VEHICLE_ID="${2}"  # Test vehicle ID passed from run_manual_tests.sh
TEST_DIR="/tmp/tvm-manual-test"
SERVICE_LOG="/tmp/tvm-service.log"

print_test_header "File Date Preservation" "3"

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

# Create file with old modification time (2 days ago) BEFORE starting service
# This ensures startup scan picks it up with the correct mtime
# Note: Must be within max_age_days limit (3 days by default) for startup scan to detect it
TEST_FILE="$TEST_DIR/terminal/old_file.log"
DAYS_AGO=2
OLD_DATE=$(date -d "$DAYS_AGO days ago" +%Y-%m-%d)

log_info "Creating file with old modification time ($DAYS_AGO days ago)..."
echo "Old data from $DAYS_AGO days ago" > "$TEST_FILE"

# Set modification time to DAYS_AGO (do this immediately after creation)
set_file_mtime "$TEST_FILE" "$DAYS_AGO"

# Check operational hours (critical for upload tests)
check_operational_hours "$CONFIG_FILE"

# Start service AFTER file is created with correct mtime
# This way startup scan will detect it with the old date
log_info "Starting TVM upload service..."
if ! start_tvm_service "$CONFIG_FILE" "$SERVICE_LOG" "$TEST_DIR" "$TEST_VEHICLE_ID"; then
    log_error "Failed to start service"
    exit 1
fi

# Verify file timestamp
FILE_MTIME=$(stat -c %y "$TEST_FILE" | cut -d' ' -f1)
log_info "File modification time: $FILE_MTIME"

# Get expected S3 path (should use file's date, not today's date)
S3_KEY="${VEHICLE_ID}/${OLD_DATE}/terminal/old_file.log"
S3_PATH="s3://${S3_BUCKET}/${S3_KEY}"

log_info "Expected S3 path (using file date): $S3_PATH"

# Also check it's NOT in today's folder
TODAY=$(date +%Y-%m-%d)
S3_TODAY="s3://${S3_BUCKET}/${VEHICLE_ID}/${TODAY}/terminal/old_file.log"
log_info "Should NOT be at (today's date): $S3_TODAY"

# Wait for stability and upload
STABILITY_PERIOD=$(grep "file_stable_seconds:" "$CONFIG_FILE" | awk '{print $2}' || echo "60")
TOTAL_WAIT=$((STABILITY_PERIOD + 15))

wait_with_progress "$TOTAL_WAIT" "Upload processing"

# Verify S3 upload to correct date folder
log_info "Verifying file uploaded to correct date folder..."

if aws s3 ls "$S3_PATH" --profile "$AWS_PROFILE" --region "$AWS_REGION" > /dev/null 2>&1; then
    log_success "File uploaded to correct date folder: $OLD_DATE"
else
    log_error "File NOT found at expected path: $S3_PATH"

    # Check if it ended up in today's folder (wrong behavior)
    if aws s3 ls "$S3_TODAY" --profile "$AWS_PROFILE" --region "$AWS_REGION" > /dev/null 2>&1; then
        log_error "File incorrectly uploaded to today's folder instead of file date"
    fi

    # List what's actually there
    log_info "Listing S3 bucket contents:"
    aws s3 ls "s3://${S3_BUCKET}/${VEHICLE_ID}/" --recursive --profile "$AWS_PROFILE" --region "$AWS_REGION" | grep "old_file" || true
fi

# Verify date format
log_info "Verifying date format (YYYY-MM-DD)..."
if echo "$OLD_DATE" | grep -qE "^[0-9]{4}-[0-9]{2}-[0-9]{2}$"; then
    log_success "Date format correct: YYYY-MM-DD"
else
    log_error "Date format incorrect: $OLD_DATE"
fi

# Verify file is NOT in today's folder
log_info "Verifying file is NOT in today's folder..."
if aws s3 ls "$S3_TODAY" --profile "$AWS_PROFILE" --region "$AWS_REGION" > /dev/null 2>&1; then
    log_error "File found in today's folder (should use file date, not upload date)"
else
    log_success "File correctly NOT in today's folder"
fi

# Cleanup
log_info "Cleaning up..."
stop_tvm_service
rm -rf "$TEST_DIR"

# Print summary
print_test_summary

# Test result
if [ $TESTS_FAILED -eq 0 ]; then
    log_success "TEST 3: PASSED - File date preservation working correctly"
    exit 0
else
    log_error "TEST 3: FAILED - See errors above"
    exit 1
fi
