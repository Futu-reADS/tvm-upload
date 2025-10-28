#!/bin/bash
# TEST 13: Pattern Matching
# Purpose: Verify pattern filtering for log directories
# Duration: ~5 minutes

set -e

# Get script directory and load helpers
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../../lib/test_helpers.sh"

# Configuration
CONFIG_FILE="${1:-config/config.yaml}"
TEST_DIR="/tmp/tvm-manual-test"
SERVICE_LOG="/tmp/tvm-service.log"

print_test_header "Pattern Matching" "13"

# Parse configuration
log_info "Loading configuration..."
load_config "$CONFIG_FILE"

# Create test directory
mkdir -p "$TEST_DIR/syslog"
log_success "Created test directory"

# Create test config with pattern matching
TEST_CONFIG="/tmp/tvm-test-config-pattern.yaml"
cat > "$TEST_CONFIG" <<EOF
vehicle_id: "$VEHICLE_ID"
log_directories:
  - path: $TEST_DIR/syslog
    source: syslog
    pattern: "syslog*"
    recursive: false
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
  queue_file: /tmp/queue-pattern-test.json
  scan_existing_files:
    enabled: true
    max_age_days: 3
  processed_files_registry:
    registry_file: /tmp/registry-pattern-test.json
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

log_success "Created test config with pattern: 'syslog*'"

# Create test files with different names
log_info "Creating test files..."

# Files that SHOULD be uploaded (match pattern "syslog*")
echo "Syslog data 1" > "$TEST_DIR/syslog/syslog"
log_success "Created: syslog (should upload)"

echo "Syslog data 2" > "$TEST_DIR/syslog/syslog.1"
log_success "Created: syslog.1 (should upload)"

echo "Syslog data 3" > "$TEST_DIR/syslog/syslog.2.gz"
log_success "Created: syslog.2.gz (should upload)"

# Files that SHOULD NOT be uploaded (don't match pattern)
echo "Other log data" > "$TEST_DIR/syslog/messages.log"
log_success "Created: messages.log (should NOT upload)"

echo "Kernel log data" > "$TEST_DIR/syslog/kern.log"
log_success "Created: kern.log (should NOT upload)"

echo "Auth log data" > "$TEST_DIR/syslog/auth.log"
log_success "Created: auth.log (should NOT upload)"

# Start service with test config
log_info "Starting TVM upload service with pattern filtering..."
if ! start_tvm_service "$TEST_CONFIG" "$SERVICE_LOG"; then
    log_error "Failed to start service"
    exit 1
fi

# Wait for stability and upload
STABILITY_PERIOD=$(grep "file_stable_seconds:" "$TEST_CONFIG" | awk '{print $2}' || echo "60")
TOTAL_WAIT=$((STABILITY_PERIOD + 30))

log_info "Waiting for file processing..."
wait_with_progress "$TOTAL_WAIT" "Pattern matching and upload"

# Get expected S3 path
TODAY=$(date +%Y-%m-%d)
S3_PREFIX="s3://${S3_BUCKET}/${VEHICLE_ID}/${TODAY}/syslog/"

log_info "Expected S3 prefix: $S3_PREFIX"

# Verify MATCHING files are uploaded
log_info "Verifying files matching pattern 'syslog*' are uploaded..."

if aws s3 ls "${S3_PREFIX}syslog" --profile "$AWS_PROFILE" --region "$AWS_REGION" > /dev/null 2>&1; then
    log_success "File uploaded: syslog (matches pattern)"
else
    log_error "File NOT uploaded: syslog (should match pattern)"
fi

if aws s3 ls "${S3_PREFIX}syslog.1" --profile "$AWS_PROFILE" --region "$AWS_REGION" > /dev/null 2>&1; then
    log_success "File uploaded: syslog.1 (matches pattern)"
else
    log_error "File NOT uploaded: syslog.1 (should match pattern)"
fi

if aws s3 ls "${S3_PREFIX}syslog.2.gz" --profile "$AWS_PROFILE" --region "$AWS_REGION" > /dev/null 2>&1; then
    log_success "File uploaded: syslog.2.gz (matches pattern)"
else
    log_error "File NOT uploaded: syslog.2.gz (should match pattern)"
fi

# Verify NON-MATCHING files are NOT uploaded
log_info "Verifying files NOT matching pattern are NOT uploaded..."

if aws s3 ls "${S3_PREFIX}messages.log" --profile "$AWS_PROFILE" --region "$AWS_REGION" > /dev/null 2>&1; then
    log_error "File uploaded: messages.log (should NOT match pattern)"
else
    log_success "File NOT uploaded: messages.log (correctly filtered)"
fi

if aws s3 ls "${S3_PREFIX}kern.log" --profile "$AWS_PROFILE" --region "$AWS_REGION" > /dev/null 2>&1; then
    log_error "File uploaded: kern.log (should NOT match pattern)"
else
    log_success "File NOT uploaded: kern.log (correctly filtered)"
fi

if aws s3 ls "${S3_PREFIX}auth.log" --profile "$AWS_PROFILE" --region "$AWS_REGION" > /dev/null 2>&1; then
    log_error "File uploaded: auth.log (should NOT match pattern)"
else
    log_success "File NOT uploaded: auth.log (correctly filtered)"
fi

# Display actual S3 contents
log_info "Actual S3 contents:"
aws s3 ls "$S3_PREFIX" --profile "$AWS_PROFILE" --region "$AWS_REGION" | while read -r line; do
    echo "  $line"
done

# Count uploaded files
UPLOADED_COUNT=$(aws s3 ls "$S3_PREFIX" --profile "$AWS_PROFILE" --region "$AWS_REGION" | wc -l || echo "0")
log_info "Total files uploaded: $UPLOADED_COUNT"

if [ "$UPLOADED_COUNT" -eq 3 ]; then
    log_success "Correct number of files uploaded (3 matching pattern)"
else
    log_error "Incorrect number of files uploaded (expected 3, got $UPLOADED_COUNT)"
fi

# Check service logs for pattern matching
log_info "Checking service logs for pattern matching messages..."
if get_service_logs "$SERVICE_LOG" | grep -qi "pattern\|filter"; then
    log_info "Service logs show pattern matching:"
    get_service_logs "$SERVICE_LOG" | grep -i "pattern\|filter" | tail -5 | while read -r line; do
        echo "  $line"
    done
fi

# Cleanup
log_info "Cleaning up..."
stop_tvm_service
rm -rf "$TEST_DIR"
rm -f "$TEST_CONFIG"
rm -f /tmp/queue-pattern-test.json
rm -f /tmp/registry-pattern-test.json

# Print summary
print_test_summary

# Test result
if [ $TESTS_FAILED -eq 0 ]; then
    log_success "TEST 13: PASSED - Pattern matching working correctly"
    exit 0
else
    log_error "TEST 13: FAILED - See errors above"
    exit 1
fi
