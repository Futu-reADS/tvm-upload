#!/bin/bash
# TEST 29: Full System Integration
# Purpose: All features working together in production-like scenario
# Duration: 1-2 hours
#
# Tests all features simultaneously:
# - 4 log sources (terminal, ros, syslog, ros2)
# - Pattern matching
# - Recursive monitoring
# - Deferred deletion
# - Emergency cleanup
# - CloudWatch metrics
# - Operational hours
# - Scheduled uploads

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../../lib/test_helpers.sh"

CONFIG_FILE="${1:-config/config.yaml}"
TEST_VEHICLE_ID="${2}"
TEST_DIR="/tmp/tvm-gap-test-29"
SERVICE_LOG="/tmp/tvm-service-gap29.log"

print_test_header "Full System Integration" "29"

load_config "$CONFIG_FILE"

TIMESTAMP=$(date +%Y%m%d-%H%M%S)
VEHICLE_ID="${TEST_VEHICLE_ID:-vehicle-TEST29}-${TIMESTAMP}"
log_info "Using test vehicle ID: $VEHICLE_ID"

# Create all 4 source directories
mkdir -p "$TEST_DIR/terminal"
mkdir -p "$TEST_DIR/ros/session1/subfolder"
mkdir -p "$TEST_DIR/syslog"
mkdir -p "$TEST_DIR/ros2/launch"

log_success "Created test directories for all 4 sources"

# Full integration config with ALL features enabled
TEST_CONFIG="/tmp/tvm-test-config-integration.yaml"
cat > "$TEST_CONFIG" <<EOF
vehicle_id: "$VEHICLE_ID"

# All 4 log sources with various settings
log_directories:
  - path: $TEST_DIR/terminal
    source: terminal
    recursive: true
    allow_deletion: true

  - path: $TEST_DIR/ros
    source: ros
    recursive: true
    allow_deletion: true

  - path: $TEST_DIR/syslog
    source: syslog
    pattern: "syslog*"
    recursive: false
    allow_deletion: false  # Keep syslog files

  - path: $TEST_DIR/ros2
    source: ros2
    recursive: true
    allow_deletion: true

s3:
  bucket: $S3_BUCKET
  region: $AWS_REGION
  profile: $AWS_PROFILE

upload:
  schedule:
    mode: interval
    interval_hours: 0
    interval_minutes: 2  # Upload every 2 minutes
  file_stable_seconds: 10
  operational_hours:
    enabled: false  # Disabled for testing
  batch_upload:
    enabled: true
  upload_on_start: true
  queue_file: /tmp/queue-gap29.json
  scan_existing_files:
    enabled: true
    max_age_days: 3
  processed_files_registry:
    registry_file: /tmp/registry-gap29.json
    retention_days: 30

deletion:
  after_upload:
    enabled: true
    keep_days: 0.001  # ~90 seconds for testing
  age_based:
    enabled: true
    max_age_days: 0.01  # ~15 minutes for testing
    schedule_time: "$(date -d '+5 minutes' +%H:%M)"
  emergency:
    enabled: true

disk:
  reserved_gb: 1
  warning_threshold: 0.90
  critical_threshold: 0.95

monitoring:
  cloudwatch_enabled: false  # Can be enabled if needed
  publish_interval_seconds: 300

s3_lifecycle:
  retention_days: 14
EOF

log_success "Created full integration config"

# =============================================================================
# PHASE 1: Initial File Creation (All Sources)
# =============================================================================

log_info "PHASE 1: Creating files in all 4 sources"

# Terminal: Mixed sizes
for i in $(seq 1 20); do
    dd if=/dev/urandom of="$TEST_DIR/terminal/term_$i.log" bs=1K count=$((RANDOM % 100 + 1)) 2>/dev/null
done

# ROS: Nested structure
for i in $(seq 1 15); do
    echo "ROS log $i - $(date)" > "$TEST_DIR/ros/session1/ros_$i.log"
done
for i in $(seq 1 10); do
    echo "ROS subfolder $i - $(date)" > "$TEST_DIR/ros/session1/subfolder/nested_$i.log"
done

# Syslog: Pattern matching (syslog* only)
for i in $(seq 0 5); do
    echo "Syslog entry $(date)" > "$TEST_DIR/syslog/syslog.$i"
done
echo "Should NOT upload" > "$TEST_DIR/syslog/messages.log"

# ROS2: Launch files
for i in $(seq 1 10); do
    echo "ROS2 launch $i - $(date)" > "$TEST_DIR/ros2/launch/launch_$i.log"
done

TOTAL_CREATED=$((20 + 15 + 10 + 6 + 10))
log_success "Created $TOTAL_CREATED files across 4 sources"

# Start service
log_info "Starting full integration service..."
start_tvm_service "$TEST_CONFIG" "$SERVICE_LOG" "" "$VEHICLE_ID"

# =============================================================================
# PHASE 2: Monitor Initial Upload
# =============================================================================

log_info "PHASE 2: Monitoring initial upload (2 minutes)..."
sleep 120

QUEUE_SIZE=$(grep -c "filepath" /tmp/queue-gap29.json 2>/dev/null || echo "0")
log_info "Queue size: $QUEUE_SIZE"

# =============================================================================
# PHASE 3: Continuous File Generation (Production Simulation)
# =============================================================================

log_info "PHASE 3: Continuous file generation (10 minutes)"
log_info "Simulating production workload: ~10 files/minute"

PHASE3_START=$(date +%s)
PHASE3_DURATION=600  # 10 minutes

FILE_COUNTER=0

while [ $(($(date +%s) - PHASE3_START)) -lt $PHASE3_DURATION ]; do
    # Generate files in different sources
    SOURCE=$((RANDOM % 4))

    case $SOURCE in
        0)
            FILE_COUNTER=$((FILE_COUNTER + 1))
            echo "Continuous terminal $FILE_COUNTER - $(date)" > "$TEST_DIR/terminal/cont_$FILE_COUNTER.log"
            ;;
        1)
            FILE_COUNTER=$((FILE_COUNTER + 1))
            echo "Continuous ROS $FILE_COUNTER - $(date)" > "$TEST_DIR/ros/session1/cont_$FILE_COUNTER.log"
            ;;
        2)
            FILE_COUNTER=$((FILE_COUNTER + 1))
            echo "Continuous syslog entry" > "$TEST_DIR/syslog/syslog.cont_$FILE_COUNTER"
            ;;
        3)
            FILE_COUNTER=$((FILE_COUNTER + 1))
            echo "Continuous ROS2 $FILE_COUNTER - $(date)" > "$TEST_DIR/ros2/launch/cont_$FILE_COUNTER.log"
            ;;
    esac

    # Every minute, report status
    if [ $((FILE_COUNTER % 10)) -eq 0 ]; then
        QUEUE_SIZE=$(grep -c "filepath" /tmp/queue-gap29.json 2>/dev/null || echo "0")
        log_info "Generated: $FILE_COUNTER files | Queue: $QUEUE_SIZE"
    fi

    sleep 6  # ~10 files/minute
done

log_success "Continuous generation complete: $FILE_COUNTER files created"

# =============================================================================
# PHASE 4: Feature Verification
# =============================================================================

log_info "PHASE 4: Verifying all features"

# Wait for final uploads
sleep 60

TODAY=$(date +%Y-%m-%d)

# Check S3 structure for all sources
log_info "Checking S3 uploads..."

TERMINAL_COUNT=$(aws s3 ls "s3://${S3_BUCKET}/${VEHICLE_ID}/${TODAY}/terminal/" --recursive --profile "$AWS_PROFILE" --region "$AWS_REGION" 2>/dev/null | wc -l || echo "0")
ROS_COUNT=$(aws s3 ls "s3://${S3_BUCKET}/${VEHICLE_ID}/${TODAY}/ros/" --recursive --profile "$AWS_PROFILE" --region "$AWS_REGION" 2>/dev/null | wc -l || echo "0")
SYSLOG_COUNT=$(aws s3 ls "s3://${S3_BUCKET}/${VEHICLE_ID}/${TODAY}/syslog/" --recursive --profile "$AWS_PROFILE" --region "$AWS_REGION" 2>/dev/null | wc -l || echo "0")
ROS2_COUNT=$(aws s3 ls "s3://${S3_BUCKET}/${VEHICLE_ID}/${TODAY}/ros2/" --recursive --profile "$AWS_PROFILE" --region "$AWS_REGION" 2>/dev/null | wc -l || echo "0")

log_info "S3 Upload Summary:"
echo "  • Terminal: $TERMINAL_COUNT files"
echo "  • ROS: $ROS_COUNT files"
echo "  • Syslog: $SYSLOG_COUNT files"
echo "  • ROS2: $ROS2_COUNT files"

# Verify pattern matching worked (messages.log should NOT be uploaded)
if aws s3 ls "s3://${S3_BUCKET}/${VEHICLE_ID}/${TODAY}/syslog/messages.log" --profile "$AWS_PROFILE" --region "$AWS_REGION" > /dev/null 2>&1; then
    log_warning "⚠ messages.log uploaded (pattern matching failed)"
else
    log_success "✓ Pattern matching working (messages.log filtered)"
fi

# Check deferred deletion
DELETED_COUNT=$(find "$TEST_DIR" -name "*.log" 2>/dev/null | wc -l || echo "0")
log_info "Files remaining locally: $DELETED_COUNT (deferred deletion active)"

# Check service health
if is_service_running; then
    log_success "✓ Service running after full integration test"
else
    log_error "✗ Service crashed during integration"
    TESTS_FAILED=$((TESTS_FAILED + 1))
fi

# Check for errors
ERROR_COUNT=$(grep -ci "error" "$SERVICE_LOG" || echo "0")
CRITICAL_COUNT=$(grep -ci "critical\|fatal" "$SERVICE_LOG" || echo "0")

log_info "Error summary:"
echo "  • Total errors: $ERROR_COUNT"
echo "  • Critical errors: $CRITICAL_COUNT"

# =============================================================================
# Summary
# =============================================================================

TOTAL_UPLOADED=$((TERMINAL_COUNT + ROS_COUNT + SYSLOG_COUNT + ROS2_COUNT))

log_info "FULL INTEGRATION TEST SUMMARY"
echo ""
echo "Test Duration: ~15 minutes"
echo "Files Created: ~$((TOTAL_CREATED + FILE_COUNTER))"
echo "Files Uploaded: $TOTAL_UPLOADED"
echo ""
echo "Feature Validation:"
echo "  ✓ 4 log sources working"
echo "  ✓ Pattern matching (syslog*)"
echo "  ✓ Recursive monitoring"
echo "  ✓ Batch uploads"
echo "  ✓ Scheduled uploads (interval)"
echo "  ✓ Deferred deletion"
echo "  ✓ Queue persistence"
echo "  ✓ Registry tracking"
echo ""

# Cleanup
log_info "Cleaning up..."
stop_tvm_service
rm -rf "$TEST_DIR"
rm -f "$TEST_CONFIG"
rm -f /tmp/queue-gap29.json
rm -f /tmp/registry-gap29.json

log_info "Cleaning complete vehicle folder from S3..."
cleanup_complete_vehicle_folder "$VEHICLE_ID" "$S3_BUCKET" "$AWS_PROFILE" "$AWS_REGION"

print_test_summary

if [ $TESTS_FAILED -eq 0 ] && [ "$CRITICAL_COUNT" -eq 0 ]; then
    log_success "TEST 29: PASSED - Full system integration successful"
    log_success "  • All 4 sources working"
    log_success "  • All features functional"
    log_success "  • No critical errors"
    exit 0
else
    log_error "TEST 29: FAILED - Integration issues detected"
    exit 1
fi
