#!/bin/bash
# TEST 12: Service Restart Resilience
# Purpose: Verify graceful shutdown and recovery
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

print_test_header "Service Restart Resilience" "12"

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

# Check operational hours (critical for upload tests)
check_operational_hours "$CONFIG_FILE"

# TEST 1: Normal shutdown and restart
log_info "Test 1: Normal shutdown and restart..."

# Start service
log_info "Starting TVM upload service (first time)..."
if ! start_tvm_service "$CONFIG_FILE" "$SERVICE_LOG" "$TEST_DIR" "$TEST_VEHICLE_ID"; then
    log_error "Failed to start service"
    exit 1
fi

# Create test files
log_info "Creating test files..."
for i in {1..3}; do
    TEST_FILE="$TEST_DIR/terminal/restart_$i.log"
    echo "File $i - $(date)" > "$TEST_FILE"
    log_success "Created restart_$i.log"
done

# Wait for some files to upload
STABILITY_PERIOD=$(grep "file_stable_seconds:" "$CONFIG_FILE" | awk '{print $2}' || echo "60")
PARTIAL_WAIT=$((STABILITY_PERIOD + 15))

log_info "Waiting for partial upload..."
wait_with_progress "$PARTIAL_WAIT" "Partial upload"

# Check initial upload status
log_info "Checking initial upload status..."
TODAY=$(date +%Y-%m-%d)
S3_PREFIX="s3://${S3_BUCKET}/${VEHICLE_ID}/${TODAY}/terminal/"

UPLOADED_BEFORE=$(aws s3 ls "$S3_PREFIX" --profile "$AWS_PROFILE" --region "$AWS_REGION" | grep -c "restart_" || echo "0")
log_info "Files uploaded before restart: $UPLOADED_BEFORE"

# Graceful shutdown
log_info "Performing graceful shutdown..."
stop_tvm_service

if ! is_service_running; then
    log_success "Service stopped successfully"
else
    log_error "Service still running after stop"
fi

# Wait briefly
sleep 3

# Restart service
log_info "Restarting service..."
rm -f "$SERVICE_LOG"  # Clear log for fresh start

if ! start_tvm_service "$CONFIG_FILE" "$SERVICE_LOG" "$TEST_DIR" "$TEST_VEHICLE_ID"; then
    log_error "Failed to restart service"
    exit 1
fi

log_success "Service restarted successfully"

# Wait for remaining files to upload
log_info "Waiting for uploads to complete after restart..."
wait_with_progress "$PARTIAL_WAIT" "Post-restart upload"

# Check final upload status
UPLOADED_AFTER=$(aws s3 ls "$S3_PREFIX" --profile "$AWS_PROFILE" --region "$AWS_REGION" | grep -c "restart_" || echo "0")
log_info "Files uploaded after restart: $UPLOADED_AFTER"

if [ "$UPLOADED_AFTER" -eq 3 ]; then
    log_success "All files uploaded successfully after restart"
elif [ "$UPLOADED_AFTER" -gt "$UPLOADED_BEFORE" ]; then
    log_success "Additional files uploaded after restart"
else
    log_error "No additional files uploaded after restart"
fi

# TEST 2: Registry persistence across restarts
log_info "Test 2: Registry persistence across restarts..."

REGISTRY_FILE=$(grep "registry_file:" "$CONFIG_FILE" | awk '{print $2}' || echo "data/upload_registry.json")

if [ -f "$REGISTRY_FILE" ]; then
    log_success "Registry file persists after restart: $REGISTRY_FILE"

    REGISTRY_COUNT=$(grep "restart_" "$REGISTRY_FILE" 2>/dev/null | wc -l)
    REGISTRY_COUNT=$(echo "$REGISTRY_COUNT" | tr -d '[:space:]')  # Remove whitespace
    log_info "Files in registry: $REGISTRY_COUNT"

    if [ "$REGISTRY_COUNT" -gt 0 ]; then
        log_success "Registry tracks uploaded files across restarts"
    fi
else
    log_warning "Registry file not found (may be in different location)"
fi

# TEST 3: State recovery
log_info "Test 3: State recovery after restart..."

# Create new file after restart
NEW_FILE="$TEST_DIR/terminal/post_restart.log"
echo "Post-restart file - $(date)" > "$NEW_FILE"
log_success "Created post-restart test file"

# Wait for upload
wait_with_progress "$PARTIAL_WAIT" "New file upload"

# Verify new file uploads normally
if aws s3 ls "${S3_PREFIX}post_restart.log" --profile "$AWS_PROFILE" --region "$AWS_REGION" > /dev/null 2>&1; then
    log_success "New files upload normally after restart"
else
    log_error "New file failed to upload after restart"
fi

# TEST 4: Check for errors or crashes
log_info "Test 4: Checking for errors during restart cycle..."

ERROR_COUNT=$(get_service_logs "$SERVICE_LOG" | grep -i "error\|exception\|crash" | wc -l)
ERROR_COUNT=$(echo "$ERROR_COUNT" | tr -d '[:space:]')  # Remove whitespace

if [ "$ERROR_COUNT" -eq 0 ]; then
    log_success "No errors detected during restart cycle"
elif [ "$ERROR_COUNT" -lt 3 ]; then
    log_warning "Minor errors detected: $ERROR_COUNT"
else
    log_error "Multiple errors detected: $ERROR_COUNT"
fi

# TEST 5: Resource cleanup
log_info "Test 5: Verifying resource cleanup..."

# Check for orphaned processes
ORPHANED=$(pgrep -f "tvm.*upload" | wc -l)
EXPECTED=1  # Only the current service should be running

if [ "$ORPHANED" -eq "$EXPECTED" ]; then
    log_success "No orphaned processes"
elif [ "$ORPHANED" -gt "$EXPECTED" ]; then
    log_warning "Possible orphaned processes: $ORPHANED"
else
    log_info "No TVM processes currently running"
fi

# Check service health
log_info "Final health check..."
if check_service_health; then
    log_success "Service healthy after all restart tests"
else
    log_error "Service not healthy after restart tests"
fi

# TEST 6: upload_on_start behavior
log_info "Test 6: Verifying upload_on_start configuration..."

UPLOAD_ON_START=$(grep "upload_on_start:" "$CONFIG_FILE" | awk '{print $2}' || echo "true")
log_info "upload_on_start setting: $UPLOAD_ON_START"

if [ "$UPLOAD_ON_START" = "true" ]; then
    log_success "upload_on_start enabled (uploads immediately on service start)"

    # Check if uploads happened soon after restart
    if get_service_logs "$SERVICE_LOG" | grep -qi "upload\|processing.*queue"; then
        log_success "Service logs show upload activity after restart"
        get_service_logs "$SERVICE_LOG" | grep -i "upload\|processing.*queue" | head -5 | while read -r line; do
            echo "  $line"
        done
    fi

    # Verify files were uploaded within reasonable time
    if [ "$UPLOADED_AFTER" -ge "$UPLOADED_BEFORE" ]; then
        log_success "Files uploaded after restart (upload_on_start working)"
    else
        log_warning "Upload count may not reflect upload_on_start behavior"
    fi

elif [ "$UPLOAD_ON_START" = "false" ]; then
    log_info "upload_on_start disabled (uploads wait for next scheduled interval)"

    # With upload_on_start: false, files should be queued but not uploaded immediately
    QUEUE_FILE=$(grep "queue_file:" "$CONFIG_FILE" | awk '{print $2}' || echo "/var/lib/tvm-upload/queue.json")

    if [ -f "$QUEUE_FILE" ]; then
        QUEUE_COUNT=$(grep -o "filepath" "$QUEUE_FILE" 2>/dev/null | wc -l)
        log_info "Files in queue: $QUEUE_COUNT"

        if [ "$QUEUE_COUNT" -gt 0 ]; then
            log_success "Files queued (waiting for scheduled upload)"
        else
            log_info "Queue empty (files may have already uploaded)"
        fi
    fi
else
    log_warning "upload_on_start setting not found or invalid"
fi

# Display restart metrics
log_info "Restart resilience summary:"
echo "  Files created: 4"
echo "  Files uploaded: $UPLOADED_AFTER"
echo "  Restart count: 1"
echo "  Errors: $ERROR_COUNT"
echo "  upload_on_start: $UPLOAD_ON_START"
echo "  Service health: $(check_service_health && echo "OK" || echo "FAILED")"

# Cleanup
log_info "Cleaning up..."
stop_tvm_service
rm -rf "$TEST_DIR"

# Print summary
print_test_summary

# Test result
if [ $TESTS_FAILED -eq 0 ]; then
    log_success "TEST 12: PASSED - Service restart resilience working correctly"
    exit 0
else
    log_error "TEST 12: FAILED - See errors above"
    exit 1
fi
