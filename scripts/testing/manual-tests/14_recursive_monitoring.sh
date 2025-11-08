#!/bin/bash
# TEST 14: Recursive Monitoring
# Purpose: Verify recursive vs non-recursive directory monitoring
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

print_test_header "Recursive Monitoring" "14"

# Parse configuration
log_info "Loading configuration..."
load_config "$CONFIG_FILE"

# Override vehicle ID with test-specific ID
if [ -n "$TEST_VEHICLE_ID" ]; then
    VEHICLE_ID="$TEST_VEHICLE_ID"
    log_info "Using test vehicle ID: $VEHICLE_ID"
fi

# Create test directories with subdirectories
mkdir -p "$TEST_DIR/ros/session1"
mkdir -p "$TEST_DIR/ros/session2/subfolder"
mkdir -p "$TEST_DIR/syslog/subdir1"
mkdir -p "$TEST_DIR/syslog/subdir2"
log_success "Created test directories with subdirectories"

# Check operational hours (critical for upload tests)
check_operational_hours "$CONFIG_FILE"

# Create test config with recursive settings
TEST_CONFIG="/tmp/tvm-test-config-recursive.yaml"
cat > "$TEST_CONFIG" <<EOF
vehicle_id: "$VEHICLE_ID"
log_directories:
  - path: $TEST_DIR/ros
    source: ros
    recursive: true
  - path: $TEST_DIR/syslog
    source: syslog
    recursive: false
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
  queue_file: /tmp/queue-recursive-test.json
  scan_existing_files:
    enabled: true
    max_age_days: 3
  processed_files_registry:
    registry_file: /tmp/registry-recursive-test.json
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

log_success "Created test config: ros (recursive: true), syslog (recursive: false)"

# Create test files in ROS directory (recursive: true)
log_info "Creating files in ROS directory (recursive: true)..."

echo "ROS root file" > "$TEST_DIR/ros/root.log"
log_success "Created: ros/root.log (root level)"

echo "ROS session 1 launch log" > "$TEST_DIR/ros/session1/launch.log"
log_success "Created: ros/session1/launch.log (subdirectory)"

echo "ROS session 1 rosout log" > "$TEST_DIR/ros/session1/rosout.log"
log_success "Created: ros/session1/rosout.log (subdirectory)"

echo "ROS session 2 nested file" > "$TEST_DIR/ros/session2/subfolder/nested.log"
log_success "Created: ros/session2/subfolder/nested.log (nested subdirectory)"

# Create test files in syslog directory (recursive: false)
log_info "Creating files in syslog directory (recursive: false)..."

echo "Syslog root file" > "$TEST_DIR/syslog/syslog"
log_success "Created: syslog/syslog (root level)"

echo "Syslog subdir1 file" > "$TEST_DIR/syslog/subdir1/messages.log"
log_success "Created: syslog/subdir1/messages.log (subdirectory - should be ignored)"

echo "Syslog subdir2 file" > "$TEST_DIR/syslog/subdir2/kern.log"
log_success "Created: syslog/subdir2/kern.log (subdirectory - should be ignored)"

# Start service with test config
log_info "Starting TVM upload service..."
if ! start_tvm_service "$TEST_CONFIG" "$SERVICE_LOG" "" "$TEST_VEHICLE_ID"; then
    log_error "Failed to start service"
    exit 1
fi

# Wait for stability and upload
STABILITY_PERIOD=$(grep "file_stable_seconds:" "$TEST_CONFIG" | awk '{print $2}' || echo "60")
TOTAL_WAIT=$((STABILITY_PERIOD + 30))

log_info "Waiting for file processing..."
wait_with_progress "$TOTAL_WAIT" "Recursive monitoring and upload"

# Get expected S3 paths
TODAY=$(date +%Y-%m-%d)
S3_ROS_PREFIX="s3://${S3_BUCKET}/${VEHICLE_ID}/${TODAY}/ros/"
S3_SYSLOG_PREFIX="s3://${S3_BUCKET}/${VEHICLE_ID}/${TODAY}/syslog/"

# Verify ROS files (recursive: true - ALL files should be uploaded)
log_info "Verifying ROS files (recursive: true) - all subdirectories uploaded..."

if aws s3 ls "${S3_ROS_PREFIX}root.log" --profile "$AWS_PROFILE" --region "$AWS_REGION" > /dev/null 2>&1; then
    log_success "ROS root file uploaded: root.log"
else
    log_error "ROS root file NOT uploaded: root.log"
fi

if aws s3 ls "${S3_ROS_PREFIX}session1/launch.log" --profile "$AWS_PROFILE" --region "$AWS_REGION" > /dev/null 2>&1; then
    log_success "ROS subdirectory file uploaded: session1/launch.log"
else
    log_error "ROS subdirectory file NOT uploaded: session1/launch.log"
fi

if aws s3 ls "${S3_ROS_PREFIX}session1/rosout.log" --profile "$AWS_PROFILE" --region "$AWS_REGION" > /dev/null 2>&1; then
    log_success "ROS subdirectory file uploaded: session1/rosout.log"
else
    log_error "ROS subdirectory file NOT uploaded: session1/rosout.log"
fi

if aws s3 ls "${S3_ROS_PREFIX}session2/subfolder/nested.log" --profile "$AWS_PROFILE" --region "$AWS_REGION" > /dev/null 2>&1; then
    log_success "ROS nested file uploaded: session2/subfolder/nested.log"
else
    log_error "ROS nested file NOT uploaded: session2/subfolder/nested.log"
fi

# Verify syslog files (recursive: false - ONLY root level uploaded)
log_info "Verifying syslog files (recursive: false) - subdirectories ignored..."

if aws s3 ls "${S3_SYSLOG_PREFIX}syslog" --profile "$AWS_PROFILE" --region "$AWS_REGION" > /dev/null 2>&1; then
    log_success "Syslog root file uploaded: syslog"
else
    log_error "Syslog root file NOT uploaded: syslog"
fi

if aws s3 ls "${S3_SYSLOG_PREFIX}subdir1/messages.log" --profile "$AWS_PROFILE" --region "$AWS_REGION" > /dev/null 2>&1; then
    log_error "Syslog subdirectory file uploaded: subdir1/messages.log (should be ignored)"
else
    log_success "Syslog subdirectory file NOT uploaded: subdir1/messages.log (correctly ignored)"
fi

if aws s3 ls "${S3_SYSLOG_PREFIX}subdir2/kern.log" --profile "$AWS_PROFILE" --region "$AWS_REGION" > /dev/null 2>&1; then
    log_error "Syslog subdirectory file uploaded: subdir2/kern.log (should be ignored)"
else
    log_success "Syslog subdirectory file NOT uploaded: subdir2/kern.log (correctly ignored)"
fi

# Display actual S3 structure
log_info "Actual ROS S3 structure:"
aws s3 ls "$S3_ROS_PREFIX" --recursive --profile "$AWS_PROFILE" --region "$AWS_REGION" | while read -r line; do
    echo "  $line"
done

log_info "Actual syslog S3 structure:"
aws s3 ls "$S3_SYSLOG_PREFIX" --recursive --profile "$AWS_PROFILE" --region "$AWS_REGION" | while read -r line; do
    echo "  $line"
done

# Count uploaded files (filter out empty lines and directory markers)
ROS_COUNT=$(aws s3 ls "$S3_ROS_PREFIX" --recursive --profile "$AWS_PROFILE" --region "$AWS_REGION" 2>/dev/null | grep -v "^$" | grep -v "PRE " | wc -l || echo "0")
SYSLOG_COUNT=$(aws s3 ls "$S3_SYSLOG_PREFIX" --recursive --profile "$AWS_PROFILE" --region "$AWS_REGION" 2>/dev/null | grep -v "^$" | grep -v "PRE " | wc -l || echo "0")

log_info "ROS files uploaded: $ROS_COUNT (expected: 4 - root + subdirectories)"
log_info "Syslog files uploaded: $SYSLOG_COUNT (expected: 1 - root only)"

EXPECTED_ROS=4
EXPECTED_SYSLOG=1

if [ "$ROS_COUNT" -eq "$EXPECTED_ROS" ]; then
    log_success "Correct ROS file count (recursive: true includes all subdirectories)"
else
    log_error "Incorrect ROS file count (expected $EXPECTED_ROS, got $ROS_COUNT)"
fi

if [ "$SYSLOG_COUNT" -eq "$EXPECTED_SYSLOG" ]; then
    log_success "Correct syslog file count (recursive: false ignores subdirectories)"
else
    log_error "Incorrect syslog file count (expected 1, got $SYSLOG_COUNT)"
fi

# Verify ROS folder structure preserved
log_info "Verifying ROS folder structure preserved in S3..."
if aws s3 ls "${S3_ROS_PREFIX}session1/" --profile "$AWS_PROFILE" --region "$AWS_REGION" | grep -q "launch.log\|rosout.log"; then
    log_success "ROS folder structure preserved: session1/ contains files"
else
    log_warning "ROS folder structure may not be preserved"
fi

# Cleanup
log_info "Cleaning up..."
stop_tvm_service
rm -rf "$TEST_DIR"
rm -f "$TEST_CONFIG"
rm -f /tmp/queue-recursive-test.json
rm -f /tmp/registry-recursive-test.json

# Print summary
print_test_summary

# Test result
if [ $TESTS_FAILED -eq 0 ]; then
    log_success "TEST 14: PASSED - Recursive monitoring working correctly"
    exit 0
else
    log_error "TEST 14: FAILED - See errors above"
    exit 1
fi
