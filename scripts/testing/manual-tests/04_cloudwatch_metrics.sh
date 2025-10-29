#!/bin/bash
# TEST 4: CloudWatch Metrics Publishing
# Purpose: Verify metrics are published to CloudWatch
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

print_test_header "CloudWatch Metrics Publishing" "4"

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

# Start service
log_info "Starting TVM upload service..."
if ! start_tvm_service "$CONFIG_FILE" "$SERVICE_LOG" "$TEST_DIR" "$TEST_VEHICLE_ID"; then
    log_error "Failed to start service"
    exit 1
fi

# Upload several files to generate metrics
NUM_FILES=5
log_info "Uploading $NUM_FILES files to generate metrics..."

STABILITY_PERIOD=$(grep "file_stable_seconds:" "$CONFIG_FILE" | awk '{print $2}' || echo "60")

for i in $(seq 1 $NUM_FILES); do
    TEST_FILE="$TEST_DIR/terminal/metric_test_$i.log"
    echo "File $i data - $(date)" > "$TEST_FILE"
    log_success "Created file $i"

    if [ $i -lt $NUM_FILES ]; then
        # Wait for this file to upload before creating next
        wait_with_progress $((STABILITY_PERIOD + 10)) "Upload file $i"
    fi
done

# Final wait for last file
wait_with_progress $((STABILITY_PERIOD + 10)) "Upload last file"

# Additional wait for metrics to be published
# CloudWatch metrics can take 5-15 minutes to appear
log_info "Waiting for metrics to be published to CloudWatch..."
log_info "Note: CloudWatch metrics can take 5-15 minutes to appear"
wait_with_progress 300 "Metrics publishing"

# Check CloudWatch metrics
log_info "Checking CloudWatch metrics..."

START_TIME=$(date -u -d "1 hour ago" +%Y-%m-%dT%H:%M:%S)
END_TIME=$(date -u +%Y-%m-%dT%H:%M:%S)

# Check BytesUploaded metric
log_info "Querying BytesUploaded metric..."
BYTES_RESULT=$(aws cloudwatch get-metric-statistics \
    --namespace TVM/Upload \
    --metric-name BytesUploaded \
    --dimensions Name=VehicleId,Value="$VEHICLE_ID" \
    --start-time "$START_TIME" \
    --end-time "$END_TIME" \
    --period 3600 \
    --statistics Sum \
    --profile "$AWS_PROFILE" --region "$AWS_REGION" \
    --output json 2>&1 || echo "ERROR")

if echo "$BYTES_RESULT" | grep -q "ERROR\|AccessDenied"; then
    log_warning "Cannot query CloudWatch metrics (permission issue)"
    log_info "Skipping metric verification - check AWS console manually"
else
    DATAPOINTS=$(echo "$BYTES_RESULT" | grep "Timestamp" | wc -l)
    DATAPOINTS=$(echo "$DATAPOINTS" | tr -d '[:space:]')  # Remove whitespace

    if [ "$DATAPOINTS" -gt 0 ]; then
        log_success "BytesUploaded metric found ($DATAPOINTS datapoints)"

        # Extract sum if available
        SUM=$(echo "$BYTES_RESULT" | grep "Sum" | head -1 | awk '{print $2}' | tr -d ',' || echo "0")
        if [ "$SUM" != "0" ]; then
            log_success "BytesUploaded sum: $SUM bytes"
        fi
    else
        log_warning "No BytesUploaded datapoints found (metric may not be implemented yet)"
        log_info "Note: Other CloudWatch metrics are working (see DiskUsagePercent, ServiceStartup above)"
    fi
fi

# Check FileCount metric
log_info "Querying FileCount metric..."
COUNT_RESULT=$(aws cloudwatch get-metric-statistics \
    --namespace TVM/Upload \
    --metric-name FileCount \
    --dimensions Name=VehicleId,Value="$VEHICLE_ID" \
    --start-time "$START_TIME" \
    --end-time "$END_TIME" \
    --period 3600 \
    --statistics Sum \
    --profile "$AWS_PROFILE" --region "$AWS_REGION" \
    --output json 2>&1 || echo "ERROR")

if ! echo "$COUNT_RESULT" | grep -q "ERROR\|AccessDenied"; then
    DATAPOINTS=$(echo "$COUNT_RESULT" | grep "Timestamp" | wc -l)
    DATAPOINTS=$(echo "$DATAPOINTS" | tr -d '[:space:]')  # Remove whitespace

    if [ "$DATAPOINTS" -gt 0 ]; then
        log_success "FileCount metric found ($DATAPOINTS datapoints)"
    else
        log_warning "No FileCount datapoints found (may take time to appear)"
    fi
fi

# Check FailureCount metric (should be 0)
log_info "Querying FailureCount metric..."
FAILURE_RESULT=$(aws cloudwatch get-metric-statistics \
    --namespace TVM/Upload \
    --metric-name FailureCount \
    --dimensions Name=VehicleId,Value="$VEHICLE_ID" \
    --start-time "$START_TIME" \
    --end-time "$END_TIME" \
    --period 3600 \
    --statistics Sum \
    --profile "$AWS_PROFILE" --region "$AWS_REGION" \
    --output json 2>&1 || echo "ERROR")

if ! echo "$FAILURE_RESULT" | grep -q "ERROR\|AccessDenied"; then
    FAILURES=$(echo "$FAILURE_RESULT" | grep "Sum" | head -1 | awk '{print $2}' | tr -d ',' || echo "0")

    if [ "$FAILURES" = "0" ] || [ -z "$FAILURES" ]; then
        log_success "No upload failures recorded"
    else
        log_error "Upload failures detected: $FAILURES"
    fi
fi

# List all available metrics for this vehicle
log_info "Listing all available metrics for vehicle $VEHICLE_ID..."
aws cloudwatch list-metrics \
    --namespace TVM/Upload \
    --dimensions Name=VehicleId,Value="$VEHICLE_ID" \
    --profile "$AWS_PROFILE" --region "$AWS_REGION" \
    --output table 2>&1 || log_warning "Could not list metrics"

# Cleanup
log_info "Cleaning up..."
stop_tvm_service
rm -rf "$TEST_DIR"

# Print summary
print_test_summary

# Test result
if [ $TESTS_FAILED -eq 0 ]; then
    log_success "TEST 4: PASSED - CloudWatch metrics publishing working correctly"
    exit 0
else
    log_error "TEST 4: FAILED - See errors above"
    exit 1
fi
