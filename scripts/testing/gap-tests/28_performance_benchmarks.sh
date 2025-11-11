#!/bin/bash
# TEST 28: Performance Benchmarks
# Purpose: Establish performance baselines
# Duration: ~20 minutes

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../../lib/test_helpers.sh"

CONFIG_FILE="${1:-config/config.yaml}"
TEST_VEHICLE_ID="${2}"
TEST_DIR="/tmp/tvm-gap-test-28"
SERVICE_LOG="/tmp/tvm-service-gap28.log"

print_test_header "Performance Benchmarks" "28"

load_config "$CONFIG_FILE"

TIMESTAMP=$(date +%Y%m%d-%H%M%S)
VEHICLE_ID="${TEST_VEHICLE_ID:-vehicle-TEST28}-${TIMESTAMP}"
log_info "Using test vehicle ID: $VEHICLE_ID"

mkdir -p "$TEST_DIR/terminal"

# Test config with minimal stability time for performance testing
TEST_CONFIG="/tmp/tvm-test-config-perf.yaml"
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
    interval_minutes: 1
  file_stable_seconds: 2
  operational_hours:
    enabled: false
  batch_upload:
    enabled: true
  upload_on_start: true
  queue_file: /tmp/queue-gap28.json
  processed_files_registry:
    registry_file: /tmp/registry-gap28.json
    retention_days: 30
deletion:
  after_upload:
    enabled: false
disk:
  reserved_gb: 1
monitoring:
  cloudwatch_enabled: false
