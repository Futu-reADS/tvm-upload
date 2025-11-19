#!/bin/bash
# TEST 20: Queue Recovery After Crash
# Purpose: Verify queue survives crash (kill -9) and files upload after restart
# Duration: ~5 minutes

set -e

# Get script directory and load helpers
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../../lib/test_helpers.sh"

# Configuration
CONFIG_FILE="${1:-config/config.yaml}"
TEST_VEHICLE_ID="${2}"
TEST_DIR="/tmp/tvm-gap-test-20"
SERVICE_LOG="/tmp/tvm-service-gap20.log"
QUEUE_FILE="/tmp/queue-gap20.json"

print_test_header "Queue Recovery After Crash" "20"

# Parse configuration
log_info "Loading base configuration..."
load_config "$CONFIG_FILE"

# Create unique test vehicle ID with timestamp
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
if [ -n "$TEST_VEHICLE_ID" ]; then
    VEHICLE_ID="${TEST_VEHICLE_ID}-TEST20-${TIMESTAMP}"
else
    VEHICLE_ID="vehicle-TEST20-${TIMESTAMP}"
fi
log_info "Using test vehicle ID: $VEHICLE_ID"
log_info "This creates isolated S3 folder: ${VEHICLE_ID}/"

# Create test directory
mkdir -p "$TEST_DIR/terminal"
log_success "Created test directory"

# Create test config
TEST_CONFIG="/tmp/tvm-test-config-crash.yaml"
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
  queue_file: $QUEUE_FILE
  scan_existing_files:
    enabled: true
    max_age_days: 3
  processed_files_registry:
    registry_file: /tmp/registry-gap20.json
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

log_success "Created test config with queue_file: $QUEUE_FILE"

# Start service
log_info "Starting TVM upload service (first time)..."
if ! start_tvm_service "$TEST_CONFIG" "$SERVICE_LOG" "" "$VEHICLE_ID"; then
    log_error "Failed to start service"
    exit 1
fi

# Create test files that will be queued
log_info "Creating test files..."
for i in {1..3}; do
    echo "Crash test file $i - $(date)" > "$TEST_DIR/terminal/crash_$i.log"
done
log_success "Created 3 test files"

# Wait for files to be detected and queued (file_stable_seconds=60 + buffer)
# Files need to be stable for 60 seconds before being queued
log_info "Waiting for files to be detected and queued..."
wait_with_progress 70 "File detection"

# Check if queue file exists and has entries
if [ -f "$QUEUE_FILE" ]; then
    log_success "Queue file exists: $QUEUE_FILE"
    QUEUE_ENTRIES=$(grep -o "filepath" "$QUEUE_FILE" 2>/dev/null | wc -l || echo "0")
    log_info "Queue entries before crash: $QUEUE_ENTRIES"

    # Display queue contents
    log_info "Queue file contents before crash:"
    cat "$QUEUE_FILE" | head -20
else
    log_warning "Queue file not found yet (files may not be queued)"
fi

# Get service PID from PID file (created by start_tvm_service)
if [ -f /tmp/tvm-service.pid ]; then
    SERVICE_PID=$(cat /tmp/tvm-service.pid 2>/dev/null || echo "")
else
    log_warning "PID file not found, trying process search..."
    SERVICE_PID=$(pgrep -f "python.*src.main" | head -1 || echo "")
fi

if [ -z "$SERVICE_PID" ]; then
    log_error "Cannot find service PID - service may not be running"
    log_info "Checking for any TVM processes:"
    ps aux | grep -E "python.*main|tvm.*upload" | grep -v grep || true
    exit 1
fi

# Verify PID is actually running
if ! ps -p "$SERVICE_PID" > /dev/null 2>&1; then
    log_error "PID $SERVICE_PID from PID file is not running"
    log_info "Checking for any TVM processes:"
    ps aux | grep -E "python.*main|tvm.*upload" | grep -v grep || true
    exit 1
fi

log_info "Service PID: $SERVICE_PID"
log_info "Verifying PID belongs to TVM service..."
ps -p "$SERVICE_PID" -o comm,args || log_error "PID verification failed"

# SIMULATE CRASH: Kill service with SIGKILL (kill -9)
log_warning "Simulating crash with kill -9 (SIGKILL)..."
kill -9 "$SERVICE_PID" 2>/dev/null || log_warning "Process may have already exited"

# Wait to ensure process is dead
sleep 2

# Verify service is dead
if is_service_running; then
    log_error "Service still running after kill -9"
else
    log_success "Service crashed successfully (killed with SIGKILL)"
fi

# Check queue file still exists after crash
log_info "Verifying queue file survived crash..."
if [ -f "$QUEUE_FILE" ]; then
    log_success "Queue file survived crash: $QUEUE_FILE"

    QUEUE_ENTRIES_AFTER=$(grep -o "filepath" "$QUEUE_FILE" 2>/dev/null | wc -l || echo "0")
    log_info "Queue entries after crash: $QUEUE_ENTRIES_AFTER"

    # Display queue contents after crash
    log_info "Queue file contents after crash:"
    cat "$QUEUE_FILE" | head -20

    # Verify queue has entries
    if [ "$QUEUE_ENTRIES_AFTER" -gt 0 ]; then
        log_success "Queue preserved $QUEUE_ENTRIES_AFTER file(s) after crash"
    else
        log_warning "Queue file exists but has no entries"
    fi
else
    log_error "Queue file missing after crash (should persist)"
fi

# Restart service to test recovery
log_info "Restarting service to test queue recovery..."
rm -f "$SERVICE_LOG"  # Clear log for fresh start

if ! start_tvm_service "$TEST_CONFIG" "$SERVICE_LOG" "" "$VEHICLE_ID"; then
    log_error "Failed to restart service after crash"
    exit 1
fi

log_success "Service restarted successfully"

# Wait for service to process queue and upload files
STABILITY_PERIOD=60
RECOVERY_WAIT=$((STABILITY_PERIOD + 30))

log_info "Waiting for queue recovery and upload..."
wait_with_progress "$RECOVERY_WAIT" "Queue recovery"

# Verify files uploaded to S3 after recovery
TODAY=$(date +%Y-%m-%d)
S3_PREFIX="s3://${S3_BUCKET}/${VEHICLE_ID}/${TODAY}/terminal/"

log_info "Verifying files uploaded after recovery..."

UPLOADED_COUNT=0
for i in {1..3}; do
    if aws s3 ls "${S3_PREFIX}crash_$i.log" --profile "$AWS_PROFILE" --region "$AWS_REGION" > /dev/null 2>&1; then
        log_success "File uploaded after recovery: crash_$i.log"
        UPLOADED_COUNT=$((UPLOADED_COUNT + 1))
    else
        log_error "File NOT uploaded after recovery: crash_$i.log"
    fi
done

if [ "$UPLOADED_COUNT" -eq 3 ]; then
    log_success "All 3 files uploaded successfully after crash recovery"
elif [ "$UPLOADED_COUNT" -gt 0 ]; then
    log_warning "Only $UPLOADED_COUNT/3 files uploaded after recovery"
else
    log_error "No files uploaded after recovery"
fi

# Check queue file after successful upload
log_info "Checking queue state after upload..."
if [ -f "$QUEUE_FILE" ]; then
    QUEUE_AFTER_UPLOAD=$(grep -o "filepath" "$QUEUE_FILE" 2>/dev/null | wc -l || echo "0")
    log_info "Queue entries after upload: $QUEUE_AFTER_UPLOAD"

    if [ "$QUEUE_AFTER_UPLOAD" -eq 0 ]; then
        log_success "Queue cleared after successful upload"
    else
        log_warning "Queue still has $QUEUE_AFTER_UPLOAD entries (may be retrying failed uploads)"
    fi
fi

# Check service logs for recovery messages
log_info "Checking service logs for recovery messages..."
if get_service_logs "$SERVICE_LOG" | grep -qi "queue\|recover\|load\|restart"; then
    log_info "Service recovery messages:"
    get_service_logs "$SERVICE_LOG" | grep -i "queue\|recover\|load\|restart" | head -10 | while read -r line; do
        echo "  $line"
    done
fi

# Verify no data loss
log_info "Verifying no data loss during crash..."
if [ "$UPLOADED_COUNT" -eq 3 ]; then
    log_success "No data loss - all files uploaded after crash recovery"
else
    log_error "Data loss detected - $((3 - UPLOADED_COUNT)) files not uploaded"
fi

# Test summary
log_info "Queue Crash Recovery Test Summary:"
echo "  ✓ Service crashed with kill -9 (SIGKILL)"
echo "  ✓ Queue file survived crash: $([ -f "$QUEUE_FILE" ] && echo "YES" || echo "NO")"
echo "  ✓ Queue entries preserved: $QUEUE_ENTRIES_AFTER"
echo "  ✓ Service restarted successfully: YES"
echo "  ✓ Files uploaded after recovery: $UPLOADED_COUNT/3"
echo "  ✓ Data loss: $((3 - UPLOADED_COUNT)) files"

# Cleanup
log_info "Cleaning up..."
stop_tvm_service
rm -rf "$TEST_DIR"
rm -f "$TEST_CONFIG"
rm -f "$QUEUE_FILE"
rm -f /tmp/registry-gap20.json

# Clean S3 test data
log_info "Cleaning complete vehicle folder from S3..."
cleanup_complete_vehicle_folder "$VEHICLE_ID" "$S3_BUCKET" "$AWS_PROFILE" "$AWS_REGION"

# Print summary
print_test_summary

# Test result
if [ $TESTS_FAILED -eq 0 ]; then
    log_success "TEST 20: PASSED - Queue survives crash and recovers successfully"
    exit 0
else
    log_error "TEST 20: FAILED - See errors above"
    exit 1
fi
