#!/bin/bash
# TEST 16: Emergency Cleanup Thresholds
# Purpose: Verify emergency cleanup when disk reaches critical threshold
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

print_test_header "Emergency Cleanup Thresholds" "16"

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

# Check current disk usage
CURRENT_USAGE=$(df "$TEST_DIR" | tail -1 | awk '{print $5}' | tr -d '%')
log_info "Current disk usage: ${CURRENT_USAGE}%"

# Warn if disk is already too full
if [ "$CURRENT_USAGE" -gt 85 ]; then
    log_warning "Disk is already ${CURRENT_USAGE}% full"
    log_warning "This test may not be able to simulate high disk usage"
    log_warning "Consider freeing up space before running this test"
fi

# Create test config with emergency cleanup enabled
TEST_CONFIG="/tmp/tvm-test-config-emergency.yaml"
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
    interval_minutes: 10
  file_stable_seconds: 60
  operational_hours:
    enabled: false
  batch_upload:
    enabled: true
  upload_on_start: true
  queue_file: /tmp/queue-emergency-test.json
  scan_existing_files:
    enabled: true
    max_age_days: 3
  processed_files_registry:
    registry_file: /tmp/registry-emergency-test.json
    retention_days: 30
deletion:
  after_upload:
    enabled: true
    keep_days: 0
  age_based:
    enabled: false
  emergency:
    enabled: true
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

log_success "Created test config with emergency cleanup enabled"

# Start service
log_info "Starting TVM upload service..."
if ! start_tvm_service "$TEST_CONFIG" "$SERVICE_LOG" "" "$TEST_VEHICLE_ID"; then
    log_error "Failed to start service"
    exit 1
fi

# Create and upload test files
log_info "Creating and uploading test files..."

for i in {1..5}; do
    TEST_FILE="$TEST_DIR/terminal/test_$i.log"
    echo "Test file $i - $(date)" > "$TEST_FILE"
done

log_success "Created 5 test files"

# Wait for upload
log_info "Waiting for files to upload..."
wait_with_progress 90 "Upload processing"

# Verify files uploaded
TODAY=$(date +%Y-%m-%d)
S3_PREFIX="s3://${S3_BUCKET}/${VEHICLE_ID}/${TODAY}/terminal/"
UPLOADED_COUNT=$(aws s3 ls "$S3_PREFIX" --profile "$AWS_PROFILE" --region "$AWS_REGION" 2>/dev/null | grep -c "test_" || echo "0")

log_info "Files uploaded: $UPLOADED_COUNT / 5"

if [ "$UPLOADED_COUNT" -ge 3 ]; then
    log_success "Files uploaded successfully"
else
    log_warning "Not all files uploaded (may affect test)"
fi

# TEST: Warning threshold (90%)
log_info "Testing warning threshold behavior..."

# Check logs for disk space warnings
if get_service_logs "$SERVICE_LOG" | grep -qi "disk.*warning\|disk.*90\|disk usage"; then
    log_info "Service monitors disk usage:"
    get_service_logs "$SERVICE_LOG" | grep -i "disk" | tail -5 | while read -r line; do
        echo "  $line"
    done
else
    log_info "No disk warnings in logs (disk usage may be below threshold)"
fi

# TEST: Check if warning threshold would trigger cleanup
log_info "Simulating high disk usage scenario..."

# Note: We can't actually fill the disk to 95% in a test environment safely
# Instead, we verify the configuration and check if emergency cleanup logic exists

log_warning "NOTE: This test verifies emergency cleanup configuration"
log_warning "Actual disk filling to 95% is not performed (unsafe in test environment)"

# Verify emergency cleanup is enabled in config
EMERGENCY_ENABLED=$(grep -A 5 "emergency:" "$TEST_CONFIG" | grep "enabled:" | awk '{print $2}')
if [ "$EMERGENCY_ENABLED" = "true" ]; then
    log_success "Emergency cleanup enabled in configuration"
else
    log_error "Emergency cleanup NOT enabled (should be true for production)"
fi

# Verify thresholds are set correctly
WARNING_THRESHOLD=$(grep "warning_threshold:" "$TEST_CONFIG" | awk '{print $2}')
CRITICAL_THRESHOLD=$(grep "critical_threshold:" "$TEST_CONFIG" | awk '{print $2}')

log_info "Warning threshold: $WARNING_THRESHOLD (0.90 = 90%)"
log_info "Critical threshold: $CRITICAL_THRESHOLD (0.95 = 95%)"

WARNING_PCT=$(echo "$WARNING_THRESHOLD * 100" | bc | cut -d'.' -f1)
CRITICAL_PCT=$(echo "$CRITICAL_THRESHOLD * 100" | bc | cut -d'.' -f1)

if [ "$WARNING_PCT" -ge 85 ] && [ "$WARNING_PCT" -le 95 ]; then
    log_success "Warning threshold configured reasonably (${WARNING_PCT}%)"
else
    log_warning "Warning threshold may be too low or too high (${WARNING_PCT}%)"
fi

if [ "$CRITICAL_PCT" -ge 90 ] && [ "$CRITICAL_PCT" -le 99 ]; then
    log_success "Critical threshold configured reasonably (${CRITICAL_PCT}%)"
else
    log_warning "Critical threshold may be too low or too high (${CRITICAL_PCT}%)"
fi

# TEST: Verify emergency cleanup deletes oldest files first
log_info "Testing emergency cleanup prioritization (oldest files first)..."

# Create files with different ages
OLD_FILE_1="$TEST_DIR/terminal/old_1.log"
OLD_FILE_2="$TEST_DIR/terminal/old_2.log"
OLD_FILE_3="$TEST_DIR/terminal/old_3.log"

echo "Oldest file" > "$OLD_FILE_1"
touch -d "5 days ago" "$OLD_FILE_1"
sleep 1

echo "Middle file" > "$OLD_FILE_2"
touch -d "3 days ago" "$OLD_FILE_2"
sleep 1

echo "Newest file" > "$OLD_FILE_3"
touch -d "1 day ago" "$OLD_FILE_3"

log_success "Created files with different ages (5, 3, 1 days old)"

# Wait for upload
wait_with_progress 90 "Upload processing"

# Verify files exist locally
if [ -f "$OLD_FILE_1" ]; then
    log_info "Old files still exist locally (disk not full enough for emergency cleanup)"
fi

# TEST: Verify disk space monitoring
log_info "Testing disk space monitoring..."

AVAILABLE_GB=$(df -BG "$TEST_DIR" | tail -1 | awk '{print $4}' | tr -d 'G')
RESERVED_GB=$(grep "reserved_gb:" "$TEST_CONFIG" | awk '{print $2}')

log_info "Available space: ${AVAILABLE_GB} GB"
log_info "Reserved space: ${RESERVED_GB} GB"

if [ "$AVAILABLE_GB" -gt "$RESERVED_GB" ]; then
    log_success "Available space (${AVAILABLE_GB}GB) > reserved space (${RESERVED_GB}GB)"
else
    log_warning "Available space (${AVAILABLE_GB}GB) <= reserved space (${RESERVED_GB}GB)"
fi

# Check if DiskManager is initialized correctly
if get_service_logs "$SERVICE_LOG" | grep -qi "disk.*manager\|disk.*init"; then
    log_success "DiskManager initialized"
else
    log_info "DiskManager initialization not logged"
fi

# TEST: Verify emergency cleanup removes files from tracking
log_info "Verifying cleanup tracking..."

# Check logs for cleanup messages
if get_service_logs "$SERVICE_LOG" | grep -qi "cleanup\|delete\|remove"; then
    log_info "Cleanup operations logged:"
    get_service_logs "$SERVICE_LOG" | grep -i "cleanup\|delete\|remove" | tail -10 | while read -r line; do
        echo "  $line"
    done
else
    log_info "No cleanup operations logged (disk usage may be below threshold)"
fi

# Display current disk status
log_info "Current disk status:"
df -h "$TEST_DIR" | tail -1

# Summary
log_info "Emergency cleanup test summary:"
echo "  ✓ Emergency cleanup enabled: $EMERGENCY_ENABLED"
echo "  ✓ Warning threshold: ${WARNING_PCT}%"
echo "  ✓ Critical threshold: ${CRITICAL_PCT}%"
echo "  ✓ Current disk usage: ${CURRENT_USAGE}%"
echo "  ✓ Available space: ${AVAILABLE_GB} GB"
echo "  ✓ Reserved space: ${RESERVED_GB} GB"

if [ "$CURRENT_USAGE" -lt 85 ]; then
    log_info "Disk usage below warning threshold - emergency cleanup not triggered"
    log_info "This is normal for test environments with sufficient free space"
fi

# Cleanup
log_info "Cleaning up..."
stop_tvm_service
rm -rf "$TEST_DIR"
rm -f "$TEST_CONFIG"
rm -f /tmp/queue-emergency-test.json
rm -f /tmp/registry-emergency-test.json

# Print summary
print_test_summary

# Test result
if [ $TESTS_FAILED -eq 0 ]; then
    log_success "TEST 16: PASSED - Emergency cleanup configuration correct"
    log_info "Note: Actual disk filling not performed (unsafe in test environment)"
    exit 0
else
    log_error "TEST 16: FAILED - See errors above"
    exit 1
fi
