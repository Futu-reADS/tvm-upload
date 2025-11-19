#!/bin/bash
# TEST 22: Environment Variable Path Expansion
# Purpose: Verify that environment variables in paths are expanded correctly
# Duration: ~5 minutes

set -e

# Get script directory and load helpers
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../../lib/test_helpers.sh"

# Configuration
CONFIG_FILE="${1:-config/config.yaml}"
TEST_VEHICLE_ID="${2}"  # Test vehicle ID passed from run script
TEST_DIR="/tmp/tvm-gap-test-22"
SERVICE_LOG="/tmp/tvm-service-gap22.log"

print_test_header "Environment Variable Path Expansion" "22"

# Parse configuration for AWS settings
log_info "Loading base configuration..."
load_config "$CONFIG_FILE"

# Create unique test vehicle ID with timestamp
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
if [ -n "$TEST_VEHICLE_ID" ]; then
    VEHICLE_ID="${TEST_VEHICLE_ID}-TEST22-${TIMESTAMP}"
else
    VEHICLE_ID="vehicle-TEST22-${TIMESTAMP}"
fi
log_info "Using test vehicle ID: $VEHICLE_ID"
log_info "This creates isolated S3 folder: ${VEHICLE_ID}/"

# Create test directories using actual environment variables
# We'll create directories that will be referenced via env vars in config
mkdir -p "${HOME}/tvm-test-envvar/terminal"
mkdir -p "/tmp/tvm-user-${USER}/ros"
mkdir -p "${TEST_DIR}/syslog"

log_success "Created test directories in various locations"

# Create test config with environment variables in paths
TEST_CONFIG="/tmp/tvm-test-config-envvar.yaml"
cat > "$TEST_CONFIG" <<EOF
vehicle_id: "$VEHICLE_ID"
log_directories:
  # Test 1: \${HOME} expansion
  - path: \${HOME}/tvm-test-envvar/terminal
    source: terminal
    recursive: true

  # Test 2: \${USER} expansion in middle of path
  - path: /tmp/tvm-user-\${USER}/ros
    source: ros
    recursive: true

  # Test 3: Normal absolute path (control - no expansion needed)
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
  queue_file: /tmp/queue-gap22.json
  scan_existing_files:
    enabled: true
    max_age_days: 3
  processed_files_registry:
    registry_file: /tmp/registry-gap22.json
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

log_success "Created test config with environment variable paths"

# Display the paths that will be tested
log_info "Environment variable paths to test:"
echo "  1. \${HOME}/tvm-test-envvar/terminal → ${HOME}/tvm-test-envvar/terminal"
echo "  2. /tmp/tvm-user-\${USER}/ros → /tmp/tvm-user-${USER}/ros"
echo "  3. $TEST_DIR/syslog → $TEST_DIR/syslog (control - no expansion)"

# Create test files in each directory
log_info "Creating test files in environment-variable-based paths..."

echo "Test HOME expansion - $(date)" > "${HOME}/tvm-test-envvar/terminal/test_home.log"
log_success "Created test file in \${HOME} path"

echo "Test USER expansion - $(date)" > "/tmp/tvm-user-${USER}/ros/test_user.log"
log_success "Created test file in \${USER} path"

echo "Test syslog - $(date)" > "$TEST_DIR/syslog/test_syslog.log"
log_success "Created test file in absolute path (control)"

# Start service with test config
log_info "Starting TVM upload service with env-var config..."
if ! start_tvm_service "$TEST_CONFIG" "$SERVICE_LOG" "" "$VEHICLE_ID"; then
    log_error "Failed to start service"
    log_info "Check service logs for path expansion errors:"
    get_service_logs "$SERVICE_LOG" 50
    exit 1
fi

log_success "Service started successfully (env vars expanded correctly)"

# Wait for stability and upload
STABILITY_PERIOD=60
TOTAL_WAIT=$((STABILITY_PERIOD + 30))

log_info "Waiting for file processing..."
wait_with_progress "$TOTAL_WAIT" "Upload processing"

# Get expected S3 paths
TODAY=$(date +%Y-%m-%d)
S3_PREFIX="s3://${S3_BUCKET}/${VEHICLE_ID}/${TODAY}"

# Verify files uploaded from environment-variable paths
log_info "Verifying files uploaded from env-var paths..."

# Test 1: ${HOME} expansion
if aws s3 ls "${S3_PREFIX}/terminal/test_home.log" --profile "$AWS_PROFILE" --region "$AWS_REGION" > /dev/null 2>&1; then
    log_success "File uploaded from \${HOME} path"
else
    log_error "File NOT uploaded from \${HOME} path"
    log_info "Expected: ${S3_PREFIX}/terminal/test_home.log"
fi

# Test 2: ${USER} expansion
if aws s3 ls "${S3_PREFIX}/ros/test_user.log" --profile "$AWS_PROFILE" --region "$AWS_REGION" > /dev/null 2>&1; then
    log_success "File uploaded from \${USER} path"
else
    log_error "File NOT uploaded from \${USER} path"
    log_info "Expected: ${S3_PREFIX}/ros/test_user.log"
fi

# Test 3: Absolute path (control)
if aws s3 ls "${S3_PREFIX}/syslog/test_syslog.log" --profile "$AWS_PROFILE" --region "$AWS_REGION" > /dev/null 2>&1; then
    log_success "File uploaded from absolute path (control)"
else
    log_error "File NOT uploaded from absolute path"
fi

# Check service logs for path expansion messages
log_info "Checking service logs for path handling..."
if get_service_logs "$SERVICE_LOG" | grep -i "monitoring\|watching\|directory"; then
    log_info "Service directory monitoring messages:"
    get_service_logs "$SERVICE_LOG" | grep -i "monitoring\|watching\|directory" | head -10 | while read -r line; do
        echo "  $line"
    done
fi

# Verify no errors related to path expansion
log_info "Checking for path-related errors..."
ERROR_COUNT=$(get_service_logs "$SERVICE_LOG" | grep -i "error.*path\|not found\|does not exist" | wc -l)
ERROR_COUNT=$(echo "$ERROR_COUNT" | tr -d '[:space:]')

if [ "$ERROR_COUNT" -eq 0 ]; then
    log_success "No path expansion errors detected"
else
    log_warning "Found $ERROR_COUNT path-related errors/warnings"
    get_service_logs "$SERVICE_LOG" | grep -i "error.*path\|not found\|does not exist" | while read -r line; do
        echo "  $line"
    done
fi

# Display actual S3 structure
log_info "Actual S3 structure for all sources:"
aws s3 ls "${S3_PREFIX}/" --recursive --profile "$AWS_PROFILE" --region "$AWS_REGION" | while read -r line; do
    echo "  $line"
done

# Count total uploaded files
UPLOADED_COUNT=$(aws s3 ls "${S3_PREFIX}/" --recursive --profile "$AWS_PROFILE" --region "$AWS_REGION" 2>/dev/null | grep -v "^$" | wc -l || echo "0")
log_info "Total files uploaded: $UPLOADED_COUNT"

# We expect at least 3 files (HOME, USER, absolute path)
# Tilde may or may not create duplicate depending on implementation
if [ "$UPLOADED_COUNT" -ge 3 ]; then
    log_success "Environment variable expansion working correctly"
else
    log_error "Expected at least 3 files, got $UPLOADED_COUNT"
fi

# Count total uploaded files and clean variable
UPLOADED_COUNT=$(aws s3 ls "${S3_PREFIX}/" --recursive --profile "$AWS_PROFILE" --region "$AWS_REGION" 2>/dev/null | grep -v "^$" | wc -l || echo "0")
UPLOADED_COUNT=$(echo "$UPLOADED_COUNT" | tr -d '[:space:]')

# Test summary
log_info "Environment Variable Expansion Test Summary:"
echo "  ✓ \${HOME} expansion tested"
echo "  ✓ \${USER} expansion in middle of path tested"
echo "  ✓ Absolute path (control) tested"
echo "  ✓ Total files uploaded: $UPLOADED_COUNT / 3 expected"

# Cleanup
log_info "Cleaning up..."
stop_tvm_service
rm -rf "${HOME}/tvm-test-envvar"
rm -rf "/tmp/tvm-user-${USER}"
rm -rf "$TEST_DIR"
rm -f "$TEST_CONFIG"
rm -f /tmp/queue-gap22.json
rm -f /tmp/registry-gap22.json

# Clean S3 test data
log_info "Cleaning complete vehicle folder from S3..."
cleanup_complete_vehicle_folder "$VEHICLE_ID" "$S3_BUCKET" "$AWS_PROFILE" "$AWS_REGION"

# Print summary
print_test_summary

# Test result
if [ $TESTS_FAILED -eq 0 ]; then
    log_success "TEST 22: PASSED - Environment variable path expansion working correctly"
    exit 0
else
    log_error "TEST 22: FAILED - See errors above"
    exit 1
fi
