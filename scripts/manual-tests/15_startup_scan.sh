#!/bin/bash
# TEST 15: Startup Scan
# Purpose: Verify startup scan behavior (existing file detection)
# Duration: ~10 minutes

set -e

# Get script directory and load helpers
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../lib/test_helpers.sh"

# Configuration
CONFIG_FILE="${1:-config/config.yaml}"
TEST_DIR="/tmp/tvm-manual-test"
SERVICE_LOG="/tmp/tvm-service.log"

print_test_header "Startup Scan" "15"

# Parse configuration
log_info "Loading configuration..."
load_config "$CONFIG_FILE"

# Create test directory
mkdir -p "$TEST_DIR/terminal"
log_success "Created test directory"

# Create test config with startup scan enabled
TEST_CONFIG="/tmp/tvm-test-config-startup.yaml"
cat > "$TEST_CONFIG" <<EOF
vehicle_id: "$VEHICLE_ID"
log_directories:
  - path: $TEST_DIR/terminal
    source: terminal
    recursive: true
s3:
  bucket: $S3_BUCKET
  region: $AWS_REGION
  credentials_path: /home/$(whoami)/.aws
  profile: $AWS_PROFILE
upload:
  schedule:
    mode: "interval"
    interval_hours: 0
    interval_minutes: 10
  file_stable_seconds: 60
  operational_hours:
    enabled: false
  batch_upload:
    enabled: true
  upload_on_start: true
  queue_file: /tmp/queue-startup-test.json
  scan_existing_files:
    enabled: true
    max_age_days: 3
  processed_files_registry:
    registry_file: /tmp/registry-startup-test.json
    retention_days: 30
deletion:
  after_upload:
    enabled: false
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

log_success "Created test config with scan_existing_files.max_age_days: 3"

# Create files with different ages BEFORE starting service
log_info "Creating files with different ages (before service starts)..."

# File 1: 1 day old (should be uploaded)
FILE_1DAY="$TEST_DIR/terminal/file_1day_old.log"
echo "1 day old file" > "$FILE_1DAY"
touch -d "1 day ago" "$FILE_1DAY"
log_success "Created: file_1day_old.log (1 day old - should upload)"

# File 2: 2 days old (should be uploaded)
FILE_2DAY="$TEST_DIR/terminal/file_2days_old.log"
echo "2 days old file" > "$FILE_2DAY"
touch -d "2 days ago" "$FILE_2DAY"
log_success "Created: file_2days_old.log (2 days old - should upload)"

# File 3: 3 days old (should be uploaded - at boundary)
FILE_3DAY="$TEST_DIR/terminal/file_3days_old.log"
echo "3 days old file" > "$FILE_3DAY"
touch -d "3 days ago" "$FILE_3DAY"
log_success "Created: file_3days_old.log (3 days old - should upload)"

# File 4: 5 days old (should be ignored)
FILE_5DAY="$TEST_DIR/terminal/file_5days_old.log"
echo "5 days old file" > "$FILE_5DAY"
touch -d "5 days ago" "$FILE_5DAY"
log_success "Created: file_5days_old.log (5 days old - should be ignored)"

# File 5: 10 days old (should be ignored)
FILE_10DAY="$TEST_DIR/terminal/file_10days_old.log"
echo "10 days old file" > "$FILE_10DAY"
touch -d "10 days ago" "$FILE_10DAY"
log_success "Created: file_10days_old.log (10 days old - should be ignored)"

# Verify file ages
log_info "Verifying file ages..."
DAYS_1=$(find "$FILE_1DAY" -mtime -2 | wc -l)
DAYS_5=$(find "$FILE_5DAY" -mtime +4 | wc -l)
DAYS_10=$(find "$FILE_10DAY" -mtime +9 | wc -l)

if [ "$DAYS_1" -eq 1 ]; then
    log_success "File age verified: 1 day old file is < 2 days"
fi

if [ "$DAYS_5" -eq 1 ]; then
    log_success "File age verified: 5 day old file is > 4 days"
fi

if [ "$DAYS_10" -eq 1 ]; then
    log_success "File age verified: 10 day old file is > 9 days"
fi

# Start service (this should trigger startup scan)
log_info "Starting TVM upload service (should trigger startup scan)..."
if ! start_tvm_service "$TEST_CONFIG" "$SERVICE_LOG"; then
    log_error "Failed to start service"
    exit 1
fi

# Wait for startup scan and upload
log_info "Waiting for startup scan and upload..."
wait_with_progress 90 "Startup scan and upload"

# Get S3 paths for different dates
DATE_1DAY=$(date -d "1 day ago" +%Y-%m-%d)
DATE_2DAY=$(date -d "2 days ago" +%Y-%m-%d)
DATE_3DAY=$(date -d "3 days ago" +%Y-%m-%d)
DATE_5DAY=$(date -d "5 days ago" +%Y-%m-%d)
DATE_10DAY=$(date -d "10 days ago" +%Y-%m-%d)

# Verify files within max_age_days are uploaded
log_info "Verifying files within 3 days are uploaded..."

S3_PATH_1DAY="s3://${S3_BUCKET}/${VEHICLE_ID}/${DATE_1DAY}/terminal/file_1day_old.log"
if aws s3 ls "$S3_PATH_1DAY" --profile "$AWS_PROFILE" --region "$AWS_REGION" > /dev/null 2>&1; then
    log_success "1-day old file uploaded (within max_age_days)"
else
    log_error "1-day old file NOT uploaded (should be within max_age_days)"
fi

S3_PATH_2DAY="s3://${S3_BUCKET}/${VEHICLE_ID}/${DATE_2DAY}/terminal/file_2days_old.log"
if aws s3 ls "$S3_PATH_2DAY" --profile "$AWS_PROFILE" --region "$AWS_REGION" > /dev/null 2>&1; then
    log_success "2-day old file uploaded (within max_age_days)"
else
    log_error "2-day old file NOT uploaded (should be within max_age_days)"
fi

S3_PATH_3DAY="s3://${S3_BUCKET}/${VEHICLE_ID}/${DATE_3DAY}/terminal/file_3days_old.log"
if aws s3 ls "$S3_PATH_3DAY" --profile "$AWS_PROFILE" --region "$AWS_REGION" > /dev/null 2>&1; then
    log_success "3-day old file uploaded (at boundary of max_age_days)"
else
    log_warning "3-day old file NOT uploaded (boundary case may vary)"
fi

# Verify files older than max_age_days are NOT uploaded
log_info "Verifying files older than 3 days are NOT uploaded..."

S3_PATH_5DAY="s3://${S3_BUCKET}/${VEHICLE_ID}/${DATE_5DAY}/terminal/file_5days_old.log"
if aws s3 ls "$S3_PATH_5DAY" --profile "$AWS_PROFILE" --region "$AWS_REGION" > /dev/null 2>&1; then
    log_error "5-day old file uploaded (should exceed max_age_days)"
else
    log_success "5-day old file NOT uploaded (exceeds max_age_days)"
fi

S3_PATH_10DAY="s3://${S3_BUCKET}/${VEHICLE_ID}/${DATE_10DAY}/terminal/file_10days_old.log"
if aws s3 ls "$S3_PATH_10DAY" --profile "$AWS_PROFILE" --region "$AWS_REGION" > /dev/null 2>&1; then
    log_error "10-day old file uploaded (should exceed max_age_days)"
else
    log_success "10-day old file NOT uploaded (exceeds max_age_days)"
fi

# TEST: Duplicate prevention on restart
log_info "Testing duplicate prevention after restart..."

# Stop service
log_info "Stopping service..."
stop_tvm_service
sleep 3

# Get current S3 upload time for 1-day file
FIRST_UPLOAD_TIME=$(aws s3 ls "$S3_PATH_1DAY" --profile "$AWS_PROFILE" --region "$AWS_REGION" 2>/dev/null | awk '{print $1, $2}' || echo "")

log_info "First upload time: $FIRST_UPLOAD_TIME"

# Restart service
log_info "Restarting service (should check registry, not re-upload)..."
rm -f "$SERVICE_LOG"
if ! start_tvm_service "$TEST_CONFIG" "$SERVICE_LOG"; then
    log_error "Failed to restart service"
    exit 1
fi

# Wait for startup scan
wait_with_progress 90 "Restart and startup scan"

# Check if file was re-uploaded
SECOND_UPLOAD_TIME=$(aws s3 ls "$S3_PATH_1DAY" --profile "$AWS_PROFILE" --region "$AWS_REGION" 2>/dev/null | awk '{print $1, $2}' || echo "")

if [ "$FIRST_UPLOAD_TIME" = "$SECOND_UPLOAD_TIME" ]; then
    log_success "File NOT re-uploaded after restart (registry prevented duplicate)"
else
    log_warning "File timestamp changed (may have been re-uploaded)"
    log_info "First:  $FIRST_UPLOAD_TIME"
    log_info "Second: $SECOND_UPLOAD_TIME"
fi

# Check registry file
REGISTRY_FILE="/tmp/registry-startup-test.json"
if [ -f "$REGISTRY_FILE" ]; then
    log_success "Registry file exists: $REGISTRY_FILE"

    if grep -q "file_1day_old.log" "$REGISTRY_FILE"; then
        log_success "1-day old file recorded in registry"
    fi
fi

# Check service logs
log_info "Checking service logs for startup scan messages..."
if get_service_logs "$SERVICE_LOG" | grep -qi "startup\|scan\|existing"; then
    log_info "Service logs show startup scan:"
    get_service_logs "$SERVICE_LOG" | grep -i "startup\|scan\|existing" | head -10 | while read -r line; do
        echo "  $line"
    done
fi

# Display S3 structure
log_info "Displaying uploaded files by date..."
for date in "$DATE_1DAY" "$DATE_2DAY" "$DATE_3DAY"; do
    PREFIX="s3://${S3_BUCKET}/${VEHICLE_ID}/${date}/terminal/"
    COUNT=$(aws s3 ls "$PREFIX" --profile "$AWS_PROFILE" --region "$AWS_REGION" 2>/dev/null | wc -l || echo "0")
    if [ "$COUNT" -gt 0 ]; then
        log_info "Date: $date ($COUNT files)"
        aws s3 ls "$PREFIX" --profile "$AWS_PROFILE" --region "$AWS_REGION" | while read -r line; do
            echo "    $line"
        done
    fi
done

# Cleanup
log_info "Cleaning up..."
stop_tvm_service
rm -rf "$TEST_DIR"
rm -f "$TEST_CONFIG"
rm -f /tmp/queue-startup-test.json
rm -f /tmp/registry-startup-test.json

# Print summary
print_test_summary

# Test result
if [ $TESTS_FAILED -eq 0 ]; then
    log_success "TEST 15: PASSED - Startup scan working correctly"
    exit 0
else
    log_error "TEST 15: FAILED - See errors above"
    exit 1
fi
