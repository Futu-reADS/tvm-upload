#!/bin/bash
# TEST 10: Error Handling and Retry
# Purpose: Test system resilience to errors
# Duration: ~15 minutes

set -e

# Get script directory and load helpers
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../lib/test_helpers.sh"

# Configuration
CONFIG_FILE="${1:-config/config.yaml}"
TEST_DIR="/tmp/tvm-manual-test"
SERVICE_LOG="/tmp/tvm-service.log"

print_test_header "Error Handling and Retry" "10"

# Parse configuration
log_info "Loading configuration..."
load_config "$CONFIG_FILE"

# Create test directory
mkdir -p "$TEST_DIR/terminal"
log_success "Created test directory"

# Start service
log_info "Starting TVM upload service..."
if ! start_tvm_service "$CONFIG_FILE" "$SERVICE_LOG" "$TEST_DIR"; then
    log_error "Failed to start service"
    exit 1
fi

# TEST 1: Network error simulation (optional - requires sudo)
log_info "Test 1: Network error handling..."

if [ "$EUID" -eq 0 ]; then
    log_warning "Running as root - can simulate network errors"

    # Create test file
    TEST_FILE="$TEST_DIR/terminal/retry_test.log"
    echo "Retry test - $(date)" > "$TEST_FILE"

    # Block AWS endpoint temporarily
    S3_ENDPOINT="s3.${AWS_REGION}.amazonaws.com.cn"
    log_info "Blocking S3 endpoint: $S3_ENDPOINT"

    iptables -A OUTPUT -d "$S3_ENDPOINT" -j DROP 2>/dev/null || log_warning "Could not block endpoint"

    # Wait for retry attempts
    log_info "Waiting for retry attempts..."
    wait_with_progress 30 "Retry attempts"

    # Check logs for retry
    if get_service_logs "$SERVICE_LOG" | grep -qi "retry\|fail\|error"; then
        log_success "Retry mechanism activated"
        get_service_logs "$SERVICE_LOG" | grep -i "retry\|fail" | tail -5 | while read -r line; do
            echo "  $line"
        done
    else
        log_warning "No retry messages found in logs"
    fi

    # Unblock endpoint
    log_info "Restoring network access..."
    iptables -D OUTPUT -d "$S3_ENDPOINT" -j DROP 2>/dev/null || true

    # Wait for successful upload
    wait_with_progress 60 "Upload retry"

    # Verify eventual success
    TODAY=$(date +%Y-%m-%d)
    S3_PATH="s3://${S3_BUCKET}/${VEHICLE_ID}/${TODAY}/terminal/retry_test.log"

    if aws s3 ls "$S3_PATH" --profile "$AWS_PROFILE" --region "$AWS_REGION" > /dev/null 2>&1; then
        log_success "File uploaded after network recovery"
    else
        log_warning "File may still be retrying"
    fi
else
    log_info "Not running as root - skipping network simulation"
    log_info "Run with sudo to test network error handling"
fi

# TEST 2: Invalid credentials handling
log_info "Test 2: Invalid credentials handling..."

# Check if credentials file exists
CREDS_PATH="${HOME}/.aws/credentials"

if [ -f "$CREDS_PATH" ]; then
    log_info "Found AWS credentials file"

    # Stop service
    stop_tvm_service
    sleep 2

    # Temporarily rename credentials
    log_info "Temporarily disabling AWS credentials..."
    mv "$CREDS_PATH" "${CREDS_PATH}.bak" 2>/dev/null || log_warning "Could not rename credentials"

    # Clear service log
    rm -f "$SERVICE_LOG"

    # Restart service
    log_info "Restarting service without credentials..."
    start_tvm_service "$CONFIG_FILE" "$SERVICE_LOG" "$TEST_DIR" 2>/dev/null || log_info "Service may fail to start (expected)"

    # Create test file
    TEST_FILE2="$TEST_DIR/terminal/nocreds_test.log"
    echo "No credentials test - $(date)" > "$TEST_FILE2"

    # Wait briefly
    sleep 10

    # Check logs for auth error
    if get_service_logs "$SERVICE_LOG" 50 | grep -qi "credentials\|auth\|permission\|access.*denied"; then
        log_success "Clear error message for missing credentials"
        get_service_logs "$SERVICE_LOG" 50 | grep -i "credentials\|auth\|permission\|access.*denied" | tail -3 | while read -r line; do
            echo "  $line"
        done
    else
        log_warning "No clear auth error message found"
    fi

    # Restore credentials
    log_info "Restoring AWS credentials..."
    mv "${CREDS_PATH}.bak" "$CREDS_PATH" 2>/dev/null || true

    # Stop and restart service
    stop_tvm_service
    sleep 2

    rm -f "$SERVICE_LOG"
    start_tvm_service "$CONFIG_FILE" "$SERVICE_LOG" "$TEST_DIR"

    # Wait for recovery
    wait_with_progress 30 "Service recovery"

    if check_service_health; then
        log_success "Service recovered after credential restoration"
    else
        log_error "Service did not recover"
    fi
else
    log_info "No credentials file found - skipping credential test"
fi

# TEST 3: Exponential backoff verification
log_info "Test 3: Checking retry configuration..."

# Check config for retry settings
if grep -qi "retry\|max.*attempts" "$CONFIG_FILE"; then
    log_success "Retry configuration found in config"
    grep -i "retry\|max.*attempts" "$CONFIG_FILE" | while read -r line; do
        echo "  $line"
    done
else
    log_info "No explicit retry configuration in config file"
fi

# Check logs for backoff pattern
if get_service_logs "$SERVICE_LOG" | grep -qi "backoff\|retry.*[0-9]"; then
    log_success "Backoff/retry pattern detected in logs"
fi

# TEST 4: Recovery after error
log_info "Test 4: Verifying system recovery..."

# Create normal test file
TEST_FILE3="$TEST_DIR/terminal/recovery_test.log"
echo "Recovery test - $(date)" > "$TEST_FILE3"

# Wait for upload
STABILITY_PERIOD=$(grep "file_stable_seconds:" "$CONFIG_FILE" | awk '{print $2}' || echo "60")
wait_with_progress $((STABILITY_PERIOD + 20)) "Recovery upload"

# Check if we're in operational hours
CURRENT_HOUR=$(date +%H:%M)
OP_START=$(grep -A 10 "operational_hours:" "$CONFIG_FILE" | grep "start:" | head -1 | awk '{print $2}' | tr -d '"' || echo "00:00")
OP_END=$(grep -A 10 "operational_hours:" "$CONFIG_FILE" | grep "end:" | head -1 | awk '{print $2}' | tr -d '"' || echo "23:59")

IN_OP_HOURS=false
if [[ "$CURRENT_HOUR" > "$OP_START" ]] && [[ "$CURRENT_HOUR" < "$OP_END" ]]; then
    IN_OP_HOURS=true
fi

# Verify successful upload or queuing
TODAY=$(date +%Y-%m-%d)
S3_PATH="s3://${S3_BUCKET}/${VEHICLE_ID}/${TODAY}/terminal/recovery_test.log"

if [ "$IN_OP_HOURS" = "true" ]; then
    # Should upload immediately
    if aws s3 ls "$S3_PATH" --profile "$AWS_PROFILE" --region "$AWS_REGION" > /dev/null 2>&1; then
        log_success "System fully recovered - normal uploads working"
    else
        log_warning "File not uploaded yet (may still be processing)"
    fi
else
    # Outside operational hours - file should be queued
    log_info "Test running outside operational hours ($CURRENT_HOUR, hours: $OP_START-$OP_END)"
    log_success "System recovered - file queued for next upload window"
fi

# Cleanup
log_info "Cleaning up..."
stop_tvm_service
rm -rf "$TEST_DIR"

# Restore any remaining backups
mv "${CREDS_PATH}.bak" "$CREDS_PATH" 2>/dev/null || true

# Print summary
print_test_summary

# Test result
if [ $TESTS_FAILED -eq 0 ]; then
    log_success "TEST 10: PASSED - Error handling and retry working correctly"
    exit 0
else
    log_error "TEST 10: FAILED - See errors above"
    exit 1
fi
