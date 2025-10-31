#!/bin/bash
# TEST 18: All 4 Log Sources Simultaneously (Complete Test)
# Purpose: Verify all 4 default sources work together without interference
# Duration: ~10 minutes

set -e

# Get script directory and load helpers
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../../lib/test_helpers.sh"

# Configuration
CONFIG_FILE="${1:-config/config.yaml}"
TEST_VEHICLE_ID="${2}"
TEST_DIR="/tmp/tvm-gap-test-18"
SERVICE_LOG="/tmp/tvm-service-gap18.log"

print_test_header "All 4 Log Sources Simultaneously (Complete)" "18"

# Parse configuration
log_info "Loading base configuration..."
load_config "$CONFIG_FILE"

# Create unique test vehicle ID with timestamp
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
if [ -n "$TEST_VEHICLE_ID" ]; then
    VEHICLE_ID="${TEST_VEHICLE_ID}-TEST18-${TIMESTAMP}"
else
    VEHICLE_ID="vehicle-TEST18-${TIMESTAMP}"
fi
log_info "Using test vehicle ID: $VEHICLE_ID"
log_info "This creates isolated S3 folder: ${VEHICLE_ID}/"

# Create all 4 source directories with subdirectories
log_info "Creating all 4 log source directories..."

mkdir -p "$TEST_DIR/terminal"
mkdir -p "$TEST_DIR/ros/session1"
mkdir -p "$TEST_DIR/ros/session2/subfolder"
mkdir -p "$TEST_DIR/syslog"
mkdir -p "$TEST_DIR/ros2/launch"

log_success "Created all 4 source directories (terminal, ros, syslog, ros2)"

# Create test config with all 4 sources
TEST_CONFIG="/tmp/tvm-test-config-all4.yaml"
cat > "$TEST_CONFIG" <<EOF
vehicle_id: "$VEHICLE_ID"
log_directories:
  # Source 1: Terminal logs
  - path: $TEST_DIR/terminal
    source: terminal
    recursive: true

  # Source 2: ROS logs (with nested structure)
  - path: $TEST_DIR/ros
    source: ros
    recursive: true

  # Source 3: Syslog (with pattern matching)
  - path: $TEST_DIR/syslog
    source: syslog
    pattern: "syslog*"
    recursive: false

  # Source 4: ROS2 logs
  - path: $TEST_DIR/ros2
    source: ros2
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
  queue_file: /tmp/queue-gap18.json
  scan_existing_files:
    enabled: true
    max_age_days: 3
  processed_files_registry:
    registry_file: /tmp/registry-gap18.json
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

log_success "Created test config with all 4 sources configured"

# Create test files in all sources with various scenarios
log_info "Creating test files in all 4 sources..."

# Terminal: Simple files
echo "Terminal log 1 - $(date)" > "$TEST_DIR/terminal/terminal_1.log"
echo "Terminal log 2 - $(date)" > "$TEST_DIR/terminal/terminal_2.log"
log_success "Created 2 terminal files"

# ROS: Nested structure (mimics real ROS folder structure)
echo "ROS launch log - $(date)" > "$TEST_DIR/ros/session1/launch.log"
echo "ROS rosout log - $(date)" > "$TEST_DIR/ros/session1/rosout.log"
echo "ROS nested log - $(date)" > "$TEST_DIR/ros/session2/subfolder/nested.log"
echo "ROS root log - $(date)" > "$TEST_DIR/ros/root.log"
log_success "Created 4 ROS files (with nested structure)"

# Syslog: With pattern matching (only syslog* files should upload)
echo "Syslog main - $(date)" > "$TEST_DIR/syslog/syslog"
echo "Syslog rotated - $(date)" > "$TEST_DIR/syslog/syslog.1"
echo "Other log - $(date)" > "$TEST_DIR/syslog/messages.log"  # Should NOT upload
log_success "Created 3 syslog files (2 matching pattern, 1 non-matching)"

# ROS2: Nested structure
echo "ROS2 launch log - $(date)" > "$TEST_DIR/ros2/launch/launch.log"
echo "ROS2 node log - $(date)" > "$TEST_DIR/ros2/node.log"
log_success "Created 2 ROS2 files"

# Summary of files created
log_info "Files created summary:"
echo "  Terminal: 2 files (all should upload)"
echo "  ROS:      4 files (all should upload, with nested structure)"
echo "  Syslog:   2 files matching pattern (syslog, syslog.1)"
echo "            1 file NOT matching (messages.log - should NOT upload)"
echo "  ROS2:     2 files (all should upload)"
echo "  ---"
echo "  Expected total uploads: 10 files"

# Start service
log_info "Starting TVM upload service with all 4 sources..."
if ! start_tvm_service "$TEST_CONFIG" "$SERVICE_LOG" "" "$VEHICLE_ID"; then
    log_error "Failed to start service"
    exit 1
fi

# Wait for all files to upload
STABILITY_PERIOD=60
TOTAL_WAIT=$((STABILITY_PERIOD + 40))

log_info "Waiting for all files to process and upload..."
wait_with_progress "$TOTAL_WAIT" "Multi-source upload"

# Get S3 paths
TODAY=$(date +%Y-%m-%d)
S3_PREFIX="s3://${S3_BUCKET}/${VEHICLE_ID}/${TODAY}"

# Verify each source separately
log_info "Verifying uploads for each source..."

# Source 1: Terminal
log_info "Checking Terminal source..."
TERMINAL_COUNT=$(aws s3 ls "${S3_PREFIX}/terminal/" --profile "$AWS_PROFILE" --region "$AWS_REGION" 2>/dev/null | grep -c "\.log" || echo "0")
TERMINAL_COUNT=$(echo "$TERMINAL_COUNT" | tr -d '[:space:]')
if [ "$TERMINAL_COUNT" -eq 2 ]; then
    log_success "Terminal: 2/2 files uploaded"
else
    log_error "Terminal: $TERMINAL_COUNT/2 files uploaded"
fi

# Source 2: ROS (check nested structure preserved)
log_info "Checking ROS source (with nested structure)..."
ROS_COUNT=$(aws s3 ls "${S3_PREFIX}/ros/" --recursive --profile "$AWS_PROFILE" --region "$AWS_REGION" 2>/dev/null | grep -c "\.log" || echo "0")
ROS_COUNT=$(echo "$ROS_COUNT" | tr -d '[:space:]')
if [ "$ROS_COUNT" -eq 4 ]; then
    log_success "ROS: 4/4 files uploaded (nested structure)"
else
    log_error "ROS: $ROS_COUNT/4 files uploaded"
fi

# Verify ROS nested structure preserved
if aws s3 ls "${S3_PREFIX}/ros/session1/launch.log" --profile "$AWS_PROFILE" --region "$AWS_REGION" > /dev/null 2>&1; then
    log_success "ROS nested structure preserved: session1/launch.log"
else
    log_error "ROS nested structure NOT preserved"
fi

if aws s3 ls "${S3_PREFIX}/ros/session2/subfolder/nested.log" --profile "$AWS_PROFILE" --region "$AWS_REGION" > /dev/null 2>&1; then
    log_success "ROS deeply nested structure preserved: session2/subfolder/nested.log"
else
    log_error "ROS deeply nested structure NOT preserved"
fi

# Source 3: Syslog (check pattern matching worked)
log_info "Checking Syslog source (pattern matching)..."
SYSLOG_COUNT=$(aws s3 ls "${S3_PREFIX}/syslog/" --profile "$AWS_PROFILE" --region "$AWS_REGION" 2>/dev/null | grep -v "^$" | wc -l || echo "0")
SYSLOG_COUNT=$(echo "$SYSLOG_COUNT" | tr -d '[:space:]')
if [ "$SYSLOG_COUNT" -eq 2 ]; then
    log_success "Syslog: 2/2 files uploaded (pattern matched)"
else
    log_warning "Syslog: $SYSLOG_COUNT/2 files uploaded"
fi

# Verify pattern filtering worked (messages.log should NOT be uploaded)
if aws s3 ls "${S3_PREFIX}/syslog/messages.log" --profile "$AWS_PROFILE" --region "$AWS_REGION" > /dev/null 2>&1; then
    log_error "Syslog: messages.log uploaded (should be filtered by pattern)"
else
    log_success "Syslog: messages.log correctly filtered (not uploaded)"
fi

# Source 4: ROS2
log_info "Checking ROS2 source..."
ROS2_COUNT=$(aws s3 ls "${S3_PREFIX}/ros2/" --recursive --profile "$AWS_PROFILE" --region "$AWS_REGION" 2>/dev/null | grep -c "\.log" || echo "0")
ROS2_COUNT=$(echo "$ROS2_COUNT" | tr -d '[:space:]')
if [ "$ROS2_COUNT" -eq 2 ]; then
    log_success "ROS2: 2/2 files uploaded"
else
    log_error "ROS2: $ROS2_COUNT/2 files uploaded"
fi

# Display complete S3 structure
log_info "Complete S3 structure (all 4 sources):"
aws s3 ls "${S3_PREFIX}/" --recursive --profile "$AWS_PROFILE" --region "$AWS_REGION" | while read -r line; do
    echo "  $line"
done

# Total file count verification
TOTAL_UPLOADED=$(aws s3 ls "${S3_PREFIX}/" --recursive --profile "$AWS_PROFILE" --region "$AWS_REGION" 2>/dev/null | grep -c "\.log" || echo "0")
TOTAL_UPLOADED=$(echo "$TOTAL_UPLOADED" | tr -d '[:space:]')
EXPECTED_TOTAL=10

log_info "Total files uploaded: $TOTAL_UPLOADED / $EXPECTED_TOTAL"

if [ "$TOTAL_UPLOADED" -eq "$EXPECTED_TOTAL" ]; then
    log_success "All expected files uploaded successfully"
elif [ "$TOTAL_UPLOADED" -ge 9 ]; then
    log_warning "Almost all files uploaded ($TOTAL_UPLOADED/$EXPECTED_TOTAL)"
else
    log_error "Missing files: uploaded $TOTAL_UPLOADED, expected $EXPECTED_TOTAL"
fi

# Verify no source interference
log_info "Verifying no source interference..."

# Check that each source has its own folder
SOURCES_FOUND=0
for source in "terminal" "ros" "syslog" "ros2"; do
    if aws s3 ls "${S3_PREFIX}/${source}/" --profile "$AWS_PROFILE" --region "$AWS_REGION" > /dev/null 2>&1; then
        SOURCES_FOUND=$((SOURCES_FOUND + 1))
        log_success "Source folder exists: $source/"
    else
        log_error "Source folder missing: $source/"
    fi
done

if [ "$SOURCES_FOUND" -eq 4 ]; then
    log_success "All 4 source folders created (no interference)"
else
    log_error "Only $SOURCES_FOUND/4 source folders found"
fi

# Check service logs for multi-source monitoring
log_info "Checking service logs for source monitoring..."
MONITOR_COUNT=$(get_service_logs "$SERVICE_LOG" | grep -c "monitoring\|watching" || echo "0")
MONITOR_COUNT=$(echo "$MONITOR_COUNT" | tr -d '[:space:]')
log_info "Monitoring log entries: $MONITOR_COUNT"

if [ "$MONITOR_COUNT" -gt 0 ]; then
    log_info "Service monitoring messages:"
    get_service_logs "$SERVICE_LOG" | grep "monitoring\|watching" | head -5 | while read -r line; do
        echo "  $line"
    done
fi

# Test summary
log_info "All 4 Sources Test Summary:"
echo "  Terminal:  $TERMINAL_COUNT/2 files"
echo "  ROS:       $ROS_COUNT/4 files (nested structure)"
echo "  Syslog:    $SYSLOG_COUNT/2 files (pattern filtered)"
echo "  ROS2:      $ROS2_COUNT/2 files"
echo "  ---"
echo "  Total:     $TOTAL_UPLOADED/$EXPECTED_TOTAL files"
echo "  Sources:   $SOURCES_FOUND/4 folders"

# Cleanup
log_info "Cleaning up..."
stop_tvm_service
rm -rf "$TEST_DIR"
rm -f "$TEST_CONFIG"
rm -f /tmp/queue-gap18.json
rm -f /tmp/registry-gap18.json

# Clean S3 test data
log_info "Cleaning S3 test data..."
cleanup_test_s3_data "$VEHICLE_ID" "$S3_BUCKET" "$AWS_PROFILE" "$AWS_REGION" "$TODAY"

# Print summary
print_test_summary

# Test result
if [ $TESTS_FAILED -eq 0 ]; then
    log_success "TEST 18: PASSED - All 4 log sources working simultaneously without interference"
    exit 0
else
    log_error "TEST 18: FAILED - See errors above"
    exit 1
fi
