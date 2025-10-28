#!/bin/bash
# TEST 3: File Date Preservation
# Purpose: Verify that file modification dates are preserved in S3 path structure
# Duration: ~5 minutes

set -e

# Get script directory and load helpers
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../lib/test_helpers.sh"

# Configuration
CONFIG_FILE="${1:-config/config.yaml}"
TEST_DIR="/tmp/tvm-manual-test"
SERVICE_LOG="/tmp/tvm-service.log"

print_test_header "File Date Preservation" "3"

# Parse configuration
log_info "Loading configuration..."
load_config "$CONFIG_FILE"

# Create test directory
mkdir -p "$TEST_DIR/terminal"
log_success "Created test directory"

# Start service
log_info "Starting TVM upload service..."
if ! start_tvm_service "$CONFIG_FILE" "$SERVICE_LOG" "$TEST_DIR"; then
    log_error "Failed to start service"
    exit 1
fi

# Create file with old modification time (5 days ago)
TEST_FILE="$TEST_DIR/terminal/old_file.log"
DAYS_AGO=5
OLD_DATE=$(date -d "$DAYS_AGO days ago" +%Y-%m-%d)

log_info "Creating file with old modification time ($DAYS_AGO days ago)..."
touch "$TEST_FILE"
echo "Old data from $DAYS_AGO days ago" > "$TEST_FILE"

# Set modification time to 5 days ago
set_file_mtime "$TEST_FILE" "$DAYS_AGO"

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
