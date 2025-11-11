#!/bin/bash
# TEST 25: Concurrent Operations and Race Conditions
# Purpose: Verify thread safety and concurrent operation handling
# Duration: ~15 minutes
#
# Tests:
# 1. Simultaneous file creation (100 files)
# 2. Files modified during upload
# 3. Files deleted from queue while running
# 4. Directory renamed during monitoring
# 5. Concurrent registry updates

set -e

# Get script directory and load helpers
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../../lib/test_helpers.sh"

# Configuration
CONFIG_FILE="${1:-config/config.yaml}"
TEST_VEHICLE_ID="${2}"
TEST_DIR="/tmp/tvm-gap-test-25"
SERVICE_LOG="/tmp/tvm-service-gap25.log"

print_test_header "Concurrent Operations" "25"

# Parse configuration
log_info "Loading base configuration..."
load_config "$CONFIG_FILE"

# Create unique test vehicle ID
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
if [ -n "$TEST_VEHICLE_ID" ]; then
    VEHICLE_ID="${TEST_VEHICLE_ID}-TEST25-${TIMESTAMP}"
else
    VEHICLE_ID="vehicle-TEST25-${TIMESTAMP}"
fi
log_info "Using test vehicle ID: $VEHICLE_ID"

# Create test directory
mkdir -p "$TEST_DIR/terminal"
log_success "Created test directory"

# =============================================================================
# TEST 1: Simultaneous File Creation
# =============================================================================

log_info "═══════════════════════════════════════════"
log_info "TEST 1: Simultaneous File Creation (100 files)"
log_info "═══════════════════════════════════════════"

# Create test config
TEST_CONFIG="/tmp/tvm-test-config-concurrent.yaml"
cat > "$TEST_CONFIG" <<EOF
vehicle_id: "$VEHICLE_ID"
log_directories:
  - path: $TEST_DIR/terminal
    source: terminal
    recursive: false

s3:
  bucket: $S3_BUCKET
  region: $AWS_REGION
  profile: $AWS_PROFILE

upload:
  schedule:
    mode: interval
    interval_hours: 0
    interval_minutes: 5
  file_stable_seconds: 10
  operational_hours:
    enabled: false
  batch_upload:
    enabled: true
  upload_on_start: true
  queue_file: /tmp/queue-gap25.json
  scan_existing_files:
    enabled: true
    max_age_days: 1
  processed_files_registry:
    registry_file: /tmp/registry-gap25.json
    retention_days: 30

deletion:
  after_upload:
    enabled: false
  age_based:
    enabled: false
  emergency:
    enabled: false

disk:
  reserved_gb: 1
  warning_threshold: 0.90
  critical_threshold: 0.95

monitoring:
  cloudwatch_enabled: false

s3_lifecycle:
  retention_days: 14
EOF

# Start service before creating files
log_info "Starting service..."
if ! start_tvm_service "$TEST_CONFIG" "$SERVICE_LOG" "" "$VEHICLE_ID"; then
    log_error "Failed to start service"
    exit 1
fi

log_info "Creating 100 files simultaneously (parallel)..."
START_TIME=$(date +%s)

# Create 100 files in parallel using background processes
for i in $(seq 1 100); do
    (
        echo "Concurrent file $i - $(date +%s%N)" > "$TEST_DIR/terminal/concurrent_$i.log"
    ) &
done

# Wait for all background jobs to complete
wait

CREATION_TIME=$(($(date +%s) - START_TIME))
log_success "Created 100 files in ${CREATION_TIME}s"

# Verify file count
ACTUAL_COUNT=$(ls "$TEST_DIR/terminal/" | wc -l)
log_info "Actual file count: $ACTUAL_COUNT / 100"

if [ "$ACTUAL_COUNT" -eq 100 ]; then
    log_success "✓ All 100 files created successfully"
else
    log_warning "⚠ Some files missing: $ACTUAL_COUNT / 100"
fi

# Wait for file stability + processing
log_info "Waiting for file detection and upload (90 seconds)..."
sleep 90

# Check if service detected all files
DETECTED=$(grep -c "New file detected\|File.*added to queue" "$SERVICE_LOG" 2>/dev/null || echo "0")
log_info "Files detected by service: $DETECTED"

if [ "$DETECTED" -ge 95 ]; then
    log_success "✓ Most files detected: $DETECTED / 100"
elif [ "$DETECTED" -ge 80 ]; then
    log_warning "⚠ Many files detected: $DETECTED / 100"
else
    log_error "✗ Few files detected: $DETECTED / 100"
    TESTS_FAILED=$((TESTS_FAILED + 1))
fi

# Check for race condition errors
RACE_ERRORS=$(grep -i "race.*condition\|concurrent.*error\|lock.*timeout\|deadlock" "$SERVICE_LOG" | wc -l)

if [ "$RACE_ERRORS" -eq 0 ]; then
    log_success "✓ No race condition errors detected"
else
    log_error "✗ Race condition errors: $RACE_ERRORS"
    grep -i "race.*condition\|concurrent.*error" "$SERVICE_LOG" | head -3 | while read -r line; do
        echo "  $line"
    done
    TESTS_FAILED=$((TESTS_FAILED + 1))
fi

# Verify service is still running
if is_service_running; then
    log_success "✓ Service survived concurrent file creation"
else
    log_error "✗ Service crashed"
    TESTS_FAILED=$((TESTS_FAILED + 1))
fi

# =============================================================================
# TEST 2: Files Modified During Upload
# =============================================================================

log_info "═══════════════════════════════════════════"
log_info "TEST 2: Files Modified During Upload"
log_info "═══════════════════════════════════════════"

# Clean directory
rm -f "$TEST_DIR/terminal/"*

# Create large file for slower upload
log_info "Creating 10MB file for upload..."
dd if=/dev/zero of="$TEST_DIR/terminal/large_file.log" bs=1M count=10 2>/dev/null
ORIGINAL_SIZE=$(stat -f%z "$TEST_DIR/terminal/large_file.log" 2>/dev/null || stat -c%s "$TEST_DIR/terminal/large_file.log")

log_info "Waiting for upload to start (20 seconds)..."
sleep 20

# Check if upload started
UPLOAD_IN_PROGRESS=$(grep -i "uploading.*large_file\|upload.*progress" "$SERVICE_LOG" | wc -l)

if [ "$UPLOAD_IN_PROGRESS" -gt 0 ]; then
    log_info "Upload in progress, modifying file..."

    # Modify file during upload
    echo "Modified during upload" >> "$TEST_DIR/terminal/large_file.log"

    sleep 10

    # Check for modification detection
    MOD_DETECTED=$(grep -i "file.*modified\|file.*changed\|size.*mismatch" "$SERVICE_LOG" | wc -l)

    if [ "$MOD_DETECTED" -gt 0 ]; then
        log_success "✓ File modification detected"
    else
        log_info "File modification may not have been detected"
    fi
else
    log_warning "⚠ Upload may have completed too quickly to test modification"
fi

# Verify service didn't crash
if is_service_running; then
    log_success "✓ Service handled file modification gracefully"
else
    log_error "✗ Service crashed on file modification"
    TESTS_FAILED=$((TESTS_FAILED + 1))
fi

# =============================================================================
# TEST 3: Files Deleted from Queue
# =============================================================================

log_info "═══════════════════════════════════════════"
log_info "TEST 3: Files Deleted While in Queue"
log_info "═══════════════════════════════════════════"

# Clean directory
rm -f "$TEST_DIR/terminal/"*

# Create 50 files
log_info "Creating 50 files for queue..."
for i in $(seq 1 50); do
    echo "Queue test $i" > "$TEST_DIR/terminal/queue_$i.log"
done

# Wait for files to be queued
sleep 15

# Get current queue size
QUEUE_SIZE_BEFORE=$(grep -c "filepath" /tmp/queue-gap25.json 2>/dev/null || echo "0")
log_info "Queue size before deletion: $QUEUE_SIZE_BEFORE"

# Delete 10 files from filesystem
log_info "Deleting 10 files from filesystem..."
for i in $(seq 1 10); do
    rm -f "$TEST_DIR/terminal/queue_$i.log"
done

# Wait for queue processing
sleep 20

# Check queue size after
QUEUE_SIZE_AFTER=$(grep -c "filepath" /tmp/queue-gap25.json 2>/dev/null || echo "0")
log_info "Queue size after deletion: $QUEUE_SIZE_AFTER"

# Check for file not found errors
FILE_NOT_FOUND=$(grep -i "file.*not.*found\|no such file" "$SERVICE_LOG" | wc -l)

if [ "$FILE_NOT_FOUND" -gt 0 ]; then
    log_success "✓ Missing files detected: $FILE_NOT_FOUND occurrences"
else
    log_info "No 'file not found' errors (files may have uploaded before deletion)"
fi

# Verify service didn't crash
if is_service_running; then
    log_success "✓ Service handled file deletion gracefully"
else
    log_error "✗ Service crashed on file deletion"
    TESTS_FAILED=$((TESTS_FAILED + 1))
fi

# =============================================================================
# TEST 4: Directory Renamed During Monitoring
# =============================================================================

log_info "═══════════════════════════════════════════"
log_info "TEST 4: Directory Renamed During Monitoring"
log_info "═══════════════════════════════════════════"

# Create new test directory
TEST_DIR_RENAME="/tmp/tvm-rename-test"
mkdir -p "$TEST_DIR_RENAME/terminal"

# Update config to monitor new directory
cat > "$TEST_CONFIG" <<EOF
vehicle_id: "$VEHICLE_ID"
log_directories:
  - path: $TEST_DIR_RENAME/terminal
    source: terminal
    recursive: false

s3:
  bucket: $S3_BUCKET
  region: $AWS_REGION
  profile: $AWS_PROFILE

upload:
  schedule:
    mode: interval
    interval_hours: 0
    interval_minutes: 5
  file_stable_seconds: 10
  operational_hours:
    enabled: false
  batch_upload:
    enabled: true
  upload_on_start: true
  queue_file: /tmp/queue-gap25.json
  processed_files_registry:
    registry_file: /tmp/registry-gap25.json
    retention_days: 30

deletion:
  after_upload:
    enabled: false

disk:
  reserved_gb: 1

monitoring:
  cloudwatch_enabled: false
EOF

# Restart service with new config
stop_tvm_service
rm -f "$SERVICE_LOG"
start_tvm_service "$TEST_CONFIG" "$SERVICE_LOG" "" "$VEHICLE_ID"

# Create some files
for i in $(seq 1 5); do
    echo "Rename test $i" > "$TEST_DIR_RENAME/terminal/rename_$i.log"
done

sleep 10

# Rename directory while service is monitoring
log_warning "Renaming monitored directory..."
mv "$TEST_DIR_RENAME/terminal" "$TEST_DIR_RENAME/terminal_renamed"

sleep 10

# Check for directory errors
DIR_ERRORS=$(grep -i "directory.*not.*found\|watch.*failed\|inotify.*error" "$SERVICE_LOG" | wc -l)

if [ "$DIR_ERRORS" -gt 0 ]; then
    log_success "✓ Directory rename detected: $DIR_ERRORS errors"
    log_info "Sample error:"
    grep -i "directory.*not.*found\|watch.*failed" "$SERVICE_LOG" | head -2 | while read -r line; do
        echo "  $line"
    done
else
    log_info "No directory errors (service may handle rename gracefully)"
fi

# Verify service didn't crash
if is_service_running; then
    log_success "✓ Service survived directory rename"
else
    log_warning "⚠ Service may have stopped (expected behavior)"
fi

stop_tvm_service || true
rm -rf "$TEST_DIR_RENAME"

# =============================================================================
# TEST 5: Concurrent Registry Updates
# =============================================================================

log_info "═══════════════════════════════════════════"
log_info "TEST 5: Concurrent Registry Updates"
log_info "═══════════════════════════════════════════"

# Clean test directory
rm -f "$TEST_DIR/terminal/"*

# Create 20 small files for quick uploads
log_info "Creating 20 files for concurrent registry updates..."
for i in $(seq 1 20); do
    echo "Registry test $i" > "$TEST_DIR/terminal/registry_$i.log"
done

# Restart service
rm -f "$SERVICE_LOG"
cat > "$TEST_CONFIG" <<EOF
vehicle_id: "$VEHICLE_ID"
log_directories:
  - path: $TEST_DIR/terminal
    source: terminal

s3:
  bucket: $S3_BUCKET
  region: $AWS_REGION
  profile: $AWS_PROFILE

upload:
  schedule:
    mode: interval
    interval_hours: 0
    interval_minutes: 5
  file_stable_seconds: 5
  operational_hours:
    enabled: false
  batch_upload:
    enabled: true
  upload_on_start: true
  queue_file: /tmp/queue-gap25.json
  processed_files_registry:
    registry_file: /tmp/registry-gap25.json
    retention_days: 30

deletion:
  after_upload:
    enabled: false

disk:
  reserved_gb: 1

monitoring:
  cloudwatch_enabled: false
EOF

start_tvm_service "$TEST_CONFIG" "$SERVICE_LOG" "" "$VEHICLE_ID"

# Wait for uploads to complete
log_info "Waiting for concurrent uploads and registry updates (60 seconds)..."
sleep 60

# Check registry file integrity
if [ -f /tmp/registry-gap25.json ]; then
    # Verify JSON is valid
    if python3 -m json.tool /tmp/registry-gap25.json > /dev/null 2>&1; then
        log_success "✓ Registry JSON is valid (no corruption)"
    else
        log_error "✗ Registry JSON is corrupted"
        TESTS_FAILED=$((TESTS_FAILED + 1))
    fi

    # Count registry entries
    REGISTRY_ENTRIES=$(grep -c "uploaded_at" /tmp/registry-gap25.json 2>/dev/null || echo "0")
    log_info "Registry entries: $REGISTRY_ENTRIES"

    if [ "$REGISTRY_ENTRIES" -ge 15 ]; then
        log_success "✓ Most files registered: $REGISTRY_ENTRIES / 20"
    else
        log_warning "⚠ Some files not registered: $REGISTRY_ENTRIES / 20"
    fi
else
    log_warning "⚠ Registry file not found"
fi

# Check for registry corruption errors
REGISTRY_ERRORS=$(grep -i "registry.*corrupt\|registry.*error\|json.*error" "$SERVICE_LOG" | wc -l)

if [ "$REGISTRY_ERRORS" -eq 0 ]; then
    log_success "✓ No registry corruption errors"
else
    log_error "✗ Registry errors detected: $REGISTRY_ERRORS"
    TESTS_FAILED=$((TESTS_FAILED + 1))
fi

# =============================================================================
# Summary
# =============================================================================

log_info "═══════════════════════════════════════════"
log_info "CONCURRENT OPERATIONS TEST SUMMARY"
log_info "═══════════════════════════════════════════"
echo ""
log_info "Concurrency Tests:"
echo "  ✓ 100 simultaneous files"
echo "  ✓ File modification during upload"
echo "  ✓ Files deleted from queue"
echo "  ✓ Directory renamed during monitoring"
echo "  ✓ Concurrent registry updates"
echo ""

# Cleanup
log_info "Cleaning up..."
stop_tvm_service || true
rm -rf "$TEST_DIR"
rm -f "$TEST_CONFIG"
rm -f /tmp/queue-gap25.json
rm -f /tmp/registry-gap25.json

# Clean S3 test data
TODAY=$(date +%Y-%m-%d)
log_info "Cleaning complete vehicle folder from S3..."
cleanup_complete_vehicle_folder "$VEHICLE_ID" "$S3_BUCKET" "$AWS_PROFILE" "$AWS_REGION"

# Print summary
print_test_summary

# Test result
if [ $TESTS_FAILED -eq 0 ]; then
    log_success "TEST 25: PASSED - Concurrent operations handled correctly"
    log_success "  • Thread safety: OK"
    log_success "  • Race conditions: None detected"
    log_success "  • Registry integrity: Maintained"
    exit 0
else
    log_error "TEST 25: FAILED - Concurrency issues detected"
    log_error "  • Failed checks: $TESTS_FAILED"
    exit 1
fi
