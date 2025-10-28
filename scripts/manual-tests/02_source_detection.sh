#!/bin/bash
# TEST 2: Source-Based Path Detection
# Purpose: Verify that files are categorized by their source directory
# Duration: ~5 minutes

set -e

# Get script directory and load helpers
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../lib/test_helpers.sh"

# Configuration
CONFIG_FILE="${1:-config/config.yaml}"
TEST_DIR="/tmp/tvm-manual-test"
SERVICE_LOG="/tmp/tvm-service.log"

print_test_header "Source-Based Path Detection" "2"

# Parse configuration
log_info "Loading configuration..."
load_config "$CONFIG_FILE"

# Create test directories for different sources
mkdir -p "$TEST_DIR"/{terminal,ros,syslog,other}
log_success "Created test directories for all sources"

# Start service with test directory
log_info "Starting TVM upload service..."
if ! start_tvm_service "$CONFIG_FILE" "$SERVICE_LOG" "$TEST_DIR"; then
    log_error "Failed to start service"
    exit 1
fi

# Create test files in different source directories
log_info "Creating test files in different source directories..."

echo "Terminal log data" > "$TEST_DIR/terminal/terminal.log"
log_success "Created terminal/terminal.log"

echo "ROS log data" > "$TEST_DIR/ros/rosout.log"
log_success "Created ros/rosout.log"

echo "Syslog data" > "$TEST_DIR/syslog/messages.log"
log_success "Created syslog/messages.log"

echo "Other log data" > "$TEST_DIR/other/custom.log"
log_success "Created other/custom.log"

# Get expected S3 paths
TODAY=$(date +%Y-%m-%d)
S3_PREFIX="s3://${S3_BUCKET}/${VEHICLE_ID}/${TODAY}"

log_info "Expected S3 prefix: $S3_PREFIX"

# Wait for stability and uploads
STABILITY_PERIOD=$(grep "file_stable_seconds:" "$CONFIG_FILE" | awk '{print $2}' || echo "60")
TOTAL_WAIT=$((STABILITY_PERIOD + 20))  # Stability + processing time

log_info "Waiting for all files to upload..."
wait_with_progress "$TOTAL_WAIT" "Upload processing"

# Verify S3 structure
log_info "Verifying S3 structure..."

# Check terminal log
if aws s3 ls "${S3_PREFIX}/terminal/terminal.log" --profile "$AWS_PROFILE" --region "$AWS_REGION" > /dev/null 2>&1; then
    log_success "Terminal log uploaded to correct path: terminal/"
else
    log_error "Terminal log not found at: ${S3_PREFIX}/terminal/"
fi

# Check ROS log
if aws s3 ls "${S3_PREFIX}/ros/rosout.log" --profile "$AWS_PROFILE" --region "$AWS_REGION" > /dev/null 2>&1; then
    log_success "ROS log uploaded to correct path: ros/"
else
    log_error "ROS log not found at: ${S3_PREFIX}/ros/"
fi

# Check syslog
if aws s3 ls "${S3_PREFIX}/syslog/messages.log" --profile "$AWS_PROFILE" --region "$AWS_REGION" > /dev/null 2>&1; then
    log_success "Syslog uploaded to correct path: syslog/"
else
    log_error "Syslog not found at: ${S3_PREFIX}/syslog/"
fi

# Check other log
if aws s3 ls "${S3_PREFIX}/other/custom.log" --profile "$AWS_PROFILE" --region "$AWS_REGION" > /dev/null 2>&1; then
    log_success "Other log uploaded to correct path: other/"
else
    log_error "Other log not found at: ${S3_PREFIX}/other/"
fi

# Display actual S3 structure
log_info "Actual S3 structure:"
aws s3 ls "${S3_PREFIX}/" --recursive --profile "$AWS_PROFILE" --region "$AWS_REGION" | while read -r line; do
    echo "  $line"
done

# Verify all sources are properly categorized
log_info "Verifying source categorization..."
S3_STRUCTURE=$(aws s3 ls "${S3_PREFIX}/" --recursive --profile "$AWS_PROFILE" --region "$AWS_REGION")

if echo "$S3_STRUCTURE" | grep -q "/terminal/"; then
    log_success "Terminal source properly categorized"
else
    log_error "Terminal source not properly categorized"
fi

if echo "$S3_STRUCTURE" | grep -q "/ros/"; then
    log_success "ROS source properly categorized"
else
    log_error "ROS source not properly categorized"
fi

if echo "$S3_STRUCTURE" | grep -q "/syslog/"; then
    log_success "Syslog source properly categorized"
else
    log_error "Syslog source not properly categorized"
fi

# Cleanup
log_info "Cleaning up..."
stop_tvm_service
rm -rf "$TEST_DIR"

# Print summary
print_test_summary

# Test result
if [ $TESTS_FAILED -eq 0 ]; then
    log_success "TEST 2: PASSED - Source-based path detection working correctly"
    exit 0
else
    log_error "TEST 2: FAILED - See errors above"
    exit 1
fi
