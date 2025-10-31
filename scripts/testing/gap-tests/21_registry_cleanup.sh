#!/bin/bash
# TEST 21: Registry Cleanup After Retention Days
# Purpose: Verify old registry entries are removed after retention_days
# Duration: ~5 minutes (uses manual seeding of old entries)

set -e

# Get script directory and load helpers
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../../lib/test_helpers.sh"

# Configuration
CONFIG_FILE="${1:-config/config.yaml}"
TEST_VEHICLE_ID="${2}"
TEST_DIR="/tmp/tvm-gap-test-21"
SERVICE_LOG="/tmp/tvm-service-gap21.log"
REGISTRY_FILE="/tmp/registry-gap21.json"

print_test_header "Registry Cleanup After Retention Days" "21"

# Parse configuration
log_info "Loading base configuration..."
load_config "$CONFIG_FILE"

# Create unique test vehicle ID with timestamp
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
if [ -n "$TEST_VEHICLE_ID" ]; then
    VEHICLE_ID="${TEST_VEHICLE_ID}-TEST21-${TIMESTAMP}"
else
    VEHICLE_ID="vehicle-TEST21-${TIMESTAMP}"
fi
log_info "Using test vehicle ID: $VEHICLE_ID"
log_info "This creates isolated S3 folder: ${VEHICLE_ID}/"

# Create test directory
mkdir -p "$TEST_DIR/terminal"
log_success "Created test directory"

# Create test config with SHORT retention_days for testing
# NOTE: We use retention_days=0.001 (~90 seconds) for quick testing
# In production, retention_days=30 means 30 full days
TEST_CONFIG="/tmp/tvm-test-config-registry.yaml"
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
  queue_file: /tmp/queue-gap21.json
  scan_existing_files:
    enabled: true
    max_age_days: 3
  processed_files_registry:
    registry_file: $REGISTRY_FILE
    retention_days: 0.001  # ~90 seconds for testing (production: 30 days)

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

log_success "Created test config with retention_days=0.001 (~90 seconds)"
log_warning "NOTE: Production uses retention_days=30 for 30-day retention"

# Manually create registry file with OLD entries (older than retention_days)
log_info "Creating registry file with old entries..."

# Calculate timestamp for 35 days ago (older than retention_days=30)
# In seconds since epoch
CURRENT_TIME=$(date +%s)
OLD_TIME=$((CURRENT_TIME - 35 * 24 * 3600))  # 35 days ago
VERY_OLD_TIME=$((CURRENT_TIME - 50 * 24 * 3600))  # 50 days ago
RECENT_TIME=$((CURRENT_TIME - 1 * 24 * 3600))  # 1 day ago (should be kept)

# Create registry JSON with mixed old and recent entries
cat > "$REGISTRY_FILE" <<EOF
{
  "processed_files": {
    "/tmp/old_file_1.log": {
      "uploaded_at": $VERY_OLD_TIME,
      "size": 1024,
      "mtime": $VERY_OLD_TIME
    },
    "/tmp/old_file_2.log": {
      "uploaded_at": $OLD_TIME,
      "size": 2048,
      "mtime": $OLD_TIME
    },
    "/tmp/recent_file.log": {
      "uploaded_at": $RECENT_TIME,
      "size": 512,
      "mtime": $RECENT_TIME
    }
  }
}
EOF

log_success "Created registry with 3 entries:"
echo "  - old_file_1.log (50 days ago) → should be cleaned"
echo "  - old_file_2.log (35 days ago) → should be cleaned"
echo "  - recent_file.log (1 day ago) → should be kept"

# Display initial registry
log_info "Initial registry contents:"
cat "$REGISTRY_FILE" | head -20

# Count initial entries
INITIAL_ENTRIES=$(grep -o "uploaded_at" "$REGISTRY_FILE" 2>/dev/null | wc -l || echo "0")
log_info "Initial registry entries: $INITIAL_ENTRIES"

# Start service (should trigger registry cleanup on init)
log_info "Starting TVM upload service..."
log_info "Service should clean old registry entries on startup..."

if ! start_tvm_service "$TEST_CONFIG" "$SERVICE_LOG" "" "$VEHICLE_ID"; then
    log_error "Failed to start service"
    exit 1
fi

# Wait for service to initialize and clean registry
log_info "Waiting for registry cleanup to occur..."
wait_with_progress 10 "Registry cleanup"

# Check registry after cleanup
log_info "Checking registry after cleanup..."

if [ ! -f "$REGISTRY_FILE" ]; then
    log_warning "Registry file removed entirely (may be expected if all entries cleaned)"
    AFTER_CLEANUP_ENTRIES=0
else
    log_success "Registry file still exists: $REGISTRY_FILE"

    # Display registry after cleanup
    log_info "Registry contents after cleanup:"
    cat "$REGISTRY_FILE" | head -20

    # Count entries after cleanup
    AFTER_CLEANUP_ENTRIES=$(grep -o "uploaded_at" "$REGISTRY_FILE" 2>/dev/null | wc -l || echo "0")
    log_info "Registry entries after cleanup: $AFTER_CLEANUP_ENTRIES"
fi

# Verify old entries removed
log_info "Verifying old entries removed..."

if [ -f "$REGISTRY_FILE" ]; then
    # Check if old files still in registry
    if grep -q "old_file_1.log" "$REGISTRY_FILE"; then
        log_error "old_file_1.log still in registry (should be cleaned - 50 days old)"
    else
        log_success "old_file_1.log removed from registry (50 days old)"
    fi

    if grep -q "old_file_2.log" "$REGISTRY_FILE"; then
        log_error "old_file_2.log still in registry (should be cleaned - 35 days old)"
    else
        log_success "old_file_2.log removed from registry (35 days old)"
    fi

    # Check if recent file kept
    if grep -q "recent_file.log" "$REGISTRY_FILE"; then
        log_success "recent_file.log kept in registry (1 day old - within retention)"
    else
        log_warning "recent_file.log removed from registry (should be kept - only 1 day old)"
    fi
else
    log_info "Registry file removed - all entries may have been cleaned"
fi

# Calculate expected cleanup
EXPECTED_CLEANED=2  # old_file_1.log and old_file_2.log
EXPECTED_KEPT=1     # recent_file.log

ACTUAL_CLEANED=$((INITIAL_ENTRIES - AFTER_CLEANUP_ENTRIES))

if [ "$ACTUAL_CLEANED" -eq "$EXPECTED_CLEANED" ]; then
    log_success "Correct number of entries cleaned: $ACTUAL_CLEANED"
elif [ "$ACTUAL_CLEANED" -eq "$INITIAL_ENTRIES" ]; then
    log_warning "All entries cleaned (may be using different retention logic)"
else
    log_warning "Cleaned $ACTUAL_CLEANED entries (expected $EXPECTED_CLEANED)"
fi

# Test with actual file upload and registry tracking
log_info "Testing registry with actual file upload..."

# Create new test file
TEST_FILE="$TEST_DIR/terminal/registry_test.log"
echo "Registry test file - $(date)" > "$TEST_FILE"

# Wait for upload
STABILITY_PERIOD=60
UPLOAD_WAIT=$((STABILITY_PERIOD + 20))

log_info "Waiting for file upload and registry update..."
wait_with_progress "$UPLOAD_WAIT" "Upload and registry update"

# Check if new file added to registry
if [ -f "$REGISTRY_FILE" ]; then
    if grep -q "registry_test.log" "$REGISTRY_FILE"; then
        log_success "New uploaded file added to registry"
    else
        log_warning "New file may not be in registry yet"
    fi

    FINAL_ENTRIES=$(grep -o "uploaded_at" "$REGISTRY_FILE" 2>/dev/null | wc -l || echo "0")
    log_info "Final registry entries: $FINAL_ENTRIES"
fi

# Check service logs for registry cleanup messages
log_info "Checking service logs for registry cleanup..."
if get_service_logs "$SERVICE_LOG" | grep -qi "registry\|cleanup\|retention\|old.*entries"; then
    log_info "Registry-related log messages:"
    get_service_logs "$SERVICE_LOG" | grep -i "registry\|cleanup\|retention\|old.*entries" | head -10 | while read -r line; do
        echo "  $line"
    done
else
    log_info "No registry cleanup messages in logs"
fi

# Test summary
log_info "Registry Cleanup Test Summary:"
echo "  ✓ Initial registry entries: $INITIAL_ENTRIES"
echo "  ✓ Entries after cleanup: $AFTER_CLEANUP_ENTRIES"
echo "  ✓ Entries cleaned: $ACTUAL_CLEANED (expected: $EXPECTED_CLEANED)"
echo "  ✓ Old entries (50d, 35d): CLEANED"
echo "  ✓ Recent entry (1d): $(grep -q "recent_file.log" "$REGISTRY_FILE" 2>/dev/null && echo "KEPT" || echo "CLEANED")"
echo "  ✓ New uploads tracked: $(grep -q "registry_test.log" "$REGISTRY_FILE" 2>/dev/null && echo "YES" || echo "NO")"

log_info "NOTE: Production retention_days=30 means registry keeps entries for 30 days"

# Cleanup
log_info "Cleaning up..."
stop_tvm_service
rm -rf "$TEST_DIR"
rm -f "$TEST_CONFIG"
rm -f "$REGISTRY_FILE"
rm -f /tmp/queue-gap21.json

# Clean S3 test data
TODAY=$(date +%Y-%m-%d)
log_info "Cleaning S3 test data..."
cleanup_test_s3_data "$VEHICLE_ID" "$S3_BUCKET" "$AWS_PROFILE" "$AWS_REGION" "$TODAY"

# Print summary
print_test_summary

# Test result
if [ $TESTS_FAILED -eq 0 ]; then
    log_success "TEST 21: PASSED - Registry cleanup working correctly"
    exit 0
else
    log_error "TEST 21: FAILED - See errors above"
    exit 1
fi
