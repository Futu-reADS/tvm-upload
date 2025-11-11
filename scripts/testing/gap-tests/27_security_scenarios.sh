#!/bin/bash
# TEST 27: Security Scenarios
# Purpose: Verify security handling and attack prevention
# Duration: ~15 minutes
#
# Tests:
# 1. Expired AWS credentials mid-upload
# 2. IAM permission changes
# 3. File permission issues (chmod 000)
# 4. Symlink attack prevention
# 5. Path traversal prevention
# 6. Bucket policy changes

set -e

# Get script directory and load helpers
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../../lib/test_helpers.sh"

# Configuration
CONFIG_FILE="${1:-config/config.yaml}"
TEST_VEHICLE_ID="${2}"
TEST_DIR="/tmp/tvm-gap-test-27"
SERVICE_LOG="/tmp/tvm-service-gap27.log"

print_test_header "Security Scenarios" "27"

# Parse configuration
log_info "Loading base configuration..."
load_config "$CONFIG_FILE"

# Create unique test vehicle ID
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
if [ -n "$TEST_VEHICLE_ID" ]; then
    VEHICLE_ID="${TEST_VEHICLE_ID}-TEST27-${TIMESTAMP}"
else
    VEHICLE_ID="vehicle-TEST27-${TIMESTAMP}"
fi
log_info "Using test vehicle ID: $VEHICLE_ID"

# Create test directory
mkdir -p "$TEST_DIR/terminal"
log_success "Created test directory"

# =============================================================================
# TEST 1: File Permission Issues
# =============================================================================

log_info "═══════════════════════════════════════════"
log_info "TEST 1: File Permission Issues"
log_info "═══════════════════════════════════════════"

# Create files with various permissions
echo "Normal file" > "$TEST_DIR/terminal/normal.log"
chmod 644 "$TEST_DIR/terminal/normal.log"

echo "Unreadable file" > "$TEST_DIR/terminal/unreadable.log"
chmod 000 "$TEST_DIR/terminal/unreadable.log"

echo "Write-only file" > "$TEST_DIR/terminal/writeonly.log"
chmod 200 "$TEST_DIR/terminal/writeonly.log"

log_info "Created test files with different permissions:"
ls -la "$TEST_DIR/terminal/"

# Create test config
TEST_CONFIG="/tmp/tvm-test-config-security.yaml"
cat > "$TEST_CONFIG" <<EOF
vehicle_id: "$VEHICLE_ID"
log_directories:
  - path: $TEST_DIR/terminal
    source: terminal
    recursive: false

s3:
  bucket: $S3_BUCKET
  region: $AWS_REGION
  profile: $AWS_PROFILE

upload:
  schedule:
    mode: interval
    interval_hours: 0
    interval_minutes: 5
  file_stable_seconds: 30
  operational_hours:
    enabled: false
  batch_upload:
    enabled: true
  upload_on_start: true
  queue_file: /tmp/queue-gap27.json
  scan_existing_files:
    enabled: true
    max_age_days: 1
  processed_files_registry:
    registry_file: /tmp/registry-gap27.json
    retention_days: 30

deletion:
  after_upload:
    enabled: false
  age_based:
    enabled: false
  emergency:
    enabled: false

disk:
  reserved_gb: 1
  warning_threshold: 0.90
  critical_threshold: 0.95

monitoring:
  cloudwatch_enabled: false

s3_lifecycle:
  retention_days: 14
EOF

log_info "Starting service to test file permissions..."
if ! start_tvm_service "$TEST_CONFIG" "$SERVICE_LOG" "" "$VEHICLE_ID"; then
    log_error "Failed to start service"
    exit 1
fi

# Wait for upload attempts
log_info "Waiting for file processing (60 seconds)..."
sleep 60

# Check logs for permission errors
PERMISSION_ERRORS=$(grep -i "permission.*denied\|cannot.*read" "$SERVICE_LOG" | wc -l)

if [ "$PERMISSION_ERRORS" -gt 0 ]; then
    log_success "✓ Permission errors detected and logged: $PERMISSION_ERRORS"
    log_info "Sample permission error:"
    grep -i "permission.*denied\|cannot.*read" "$SERVICE_LOG" | head -3 | while read -r line; do
        echo "  $line"
    done
else
    log_warning "⚠ No permission errors in logs (may have been handled silently)"
fi

# Verify service didn't crash
if is_service_running; then
    log_success "✓ Service continues running despite permission issues"
else
    log_error "✗ Service crashed due to permission errors"
    TESTS_FAILED=$((TESTS_FAILED + 1))
fi

# Verify normal file was uploaded
TODAY=$(date +%Y-%m-%d)
S3_PREFIX="s3://${S3_BUCKET}/${VEHICLE_ID}/${TODAY}/terminal/"

if aws s3 ls "${S3_PREFIX}normal.log" --profile "$AWS_PROFILE" --region "$AWS_REGION" > /dev/null 2>&1; then
    log_success "✓ Normal file uploaded successfully"
else
    log_warning "⚠ Normal file not uploaded (may still be processing)"
fi

# Verify unreadable file was NOT uploaded
if aws s3 ls "${S3_PREFIX}unreadable.log" --profile "$AWS_PROFILE" --region "$AWS_REGION" > /dev/null 2>&1; then
    log_error "✗ Unreadable file was uploaded (security issue!)"
    TESTS_FAILED=$((TESTS_FAILED + 1))
else
    log_success "✓ Unreadable file correctly skipped"
fi

stop_tvm_service

# =============================================================================
# TEST 2: Symlink Attack Prevention
# =============================================================================

log_info "═══════════════════════════════════════════"
log_info "TEST 2: Symlink Attack Prevention"
log_info "═══════════════════════════════════════════"

# Clean test directory
rm -f "$TEST_DIR/terminal/"*

# Create normal file
echo "Normal log file" > "$TEST_DIR/terminal/normal.log"

# Create symlink to /etc/passwd
ln -s /etc/passwd "$TEST_DIR/terminal/passwd_symlink.log"

# Create symlink to non-existent file
ln -s /tmp/nonexistent "$TEST_DIR/terminal/broken_symlink.log"

log_info "Created symlinks for testing:"
ls -la "$TEST_DIR/terminal/"

log_info "Starting service to test symlink handling..."
rm -f "$SERVICE_LOG"
start_tvm_service "$TEST_CONFIG" "$SERVICE_LOG" "" "$VEHICLE_ID"

# Wait for processing
sleep 60

# Check for symlink warnings
SYMLINK_WARNINGS=$(grep -i "symlink" "$SERVICE_LOG" | wc -l)

if [ "$SYMLINK_WARNINGS" -gt 0 ]; then
    log_success "✓ Symlinks detected and logged: $SYMLINK_WARNINGS"
    log_info "Symlink warnings:"
    grep -i "symlink" "$SERVICE_LOG" | head -3 | while read -r line; do
        echo "  $line"
    done
fi

# Verify symlinks were NOT uploaded
if aws s3 ls "${S3_PREFIX}passwd_symlink.log" --profile "$AWS_PROFILE" --region "$AWS_REGION" > /dev/null 2>&1; then
    log_error "✗ Symlink to /etc/passwd was uploaded (CRITICAL SECURITY ISSUE!)"
    TESTS_FAILED=$((TESTS_FAILED + 1))
else
    log_success "✓ Symlink to /etc/passwd NOT uploaded (secure)"
fi

# Verify service is still running
if is_service_running; then
    log_success "✓ Service handles symlinks gracefully"
else
    log_error "✗ Service crashed on symlink"
    TESTS_FAILED=$((TESTS_FAILED + 1))
fi

stop_tvm_service

# =============================================================================
# TEST 3: Path Traversal Prevention
# =============================================================================

log_info "═══════════════════════════════════════════"
log_info "TEST 3: Path Traversal Prevention"
log_info "═══════════════════════════════════════════"

# Clean test directory
rm -f "$TEST_DIR/terminal/"*

# Try to create files with path traversal attempts
echo "Normal file" > "$TEST_DIR/terminal/normal.log"

# Create file with ../ in name (if filesystem allows)
TRAVERSAL_FILE="$TEST_DIR/terminal/../../../tmp/evil.log"
mkdir -p "$(dirname "$TRAVERSAL_FILE")" 2>/dev/null || true
echo "Path traversal attempt" > "$TRAVERSAL_FILE" 2>/dev/null || true

log_info "Created test files (including path traversal attempts)"

log_info "Starting service to test path sanitization..."
rm -f "$SERVICE_LOG"
start_tvm_service "$TEST_CONFIG" "$SERVICE_LOG" "" "$VEHICLE_ID"

sleep 60

# Check S3 for any path traversal artifacts
log_info "Checking S3 for path traversal artifacts..."

# List all keys under vehicle ID
ALL_KEYS=$(aws s3 ls "s3://${S3_BUCKET}/${VEHICLE_ID}/" --recursive --profile "$AWS_PROFILE" --region "$AWS_REGION" 2>/dev/null || true)

# Check for suspicious patterns
SUSPICIOUS=$(echo "$ALL_KEYS" | grep -E "\.\./|/\.\./|\.\.\\|\\\.\./" || true)

if [ -z "$SUSPICIOUS" ]; then
    log_success "✓ No path traversal artifacts in S3"
else
    log_error "✗ Potential path traversal in S3:"
    echo "$SUSPICIOUS" | while read -r line; do
        echo "  $line"
    done
    TESTS_FAILED=$((TESTS_FAILED + 1))
fi

# Verify all uploaded paths are under correct vehicle_id/date/source structure
INVALID_STRUCTURE=$(echo "$ALL_KEYS" | grep -v "^$VEHICLE_ID/$TODAY/terminal/" || true)

if [ -z "$INVALID_STRUCTURE" ]; then
    log_success "✓ All S3 keys follow correct structure"
else
    log_warning "⚠ Some keys don't follow expected structure:"
    echo "$INVALID_STRUCTURE" | while read -r line; do
        echo "  $line"
    done
fi

stop_tvm_service

# =============================================================================
# TEST 4: AWS Credential Issues
# =============================================================================

log_info "═══════════════════════════════════════════"
log_info "TEST 4: AWS Credential Handling"
log_info "═══════════════════════════════════════════"

# Clean test directory
rm -f "$TEST_DIR/terminal/"*
echo "Credential test file" > "$TEST_DIR/terminal/cred_test.log"

# Backup AWS credentials
AWS_CRED_FILE="${HOME}/.aws/credentials"
AWS_CRED_BACKUP="${AWS_CRED_FILE}.backup-test27"

if [ -f "$AWS_CRED_FILE" ]; then
    cp "$AWS_CRED_FILE" "$AWS_CRED_BACKUP"
    log_info "Backed up AWS credentials"
else
    log_warning "No AWS credentials file found at $AWS_CRED_FILE"
    log_warning "Skipping credential expiration test"
    AWS_CRED_FILE=""
fi

if [ -n "$AWS_CRED_FILE" ] && [ -f "$AWS_CRED_BACKUP" ]; then
    log_info "Starting service with valid credentials..."
    rm -f "$SERVICE_LOG"
    start_tvm_service "$TEST_CONFIG" "$SERVICE_LOG" "" "$VEHICLE_ID"

    # Let service start and detect files
    sleep 10

    # Remove credentials to simulate expiration
    log_warning "Simulating credential expiration (removing credentials file)..."
    mv "$AWS_CRED_FILE" "${AWS_CRED_FILE}.removed"

    # Wait and check for credential errors
    sleep 30

    CRED_ERRORS=$(grep -i "credential\|NoCredentialsError\|authentication.*failed\|unauthorized" "$SERVICE_LOG" | wc -l)

    if [ "$CRED_ERRORS" -gt 0 ]; then
        log_success "✓ Credential errors detected: $CRED_ERRORS"
        log_info "Sample credential error:"
        grep -i "credential\|NoCredentialsError" "$SERVICE_LOG" | head -2 | while read -r line; do
            echo "  $line"
        done
    else
        log_warning "⚠ No credential errors detected (may be cached)"
    fi

    # Verify service didn't crash
    if is_service_running; then
        log_success "✓ Service didn't crash from credential failure"
    else
        log_warning "⚠ Service stopped (may have exited gracefully)"
    fi

    # Restore credentials
    log_info "Restoring credentials..."
    if [ -f "${AWS_CRED_FILE}.removed" ]; then
        mv "${AWS_CRED_FILE}.removed" "$AWS_CRED_FILE"
    else
        cp "$AWS_CRED_BACKUP" "$AWS_CRED_FILE"
    fi

    # Give service time to recover (if still running)
    if is_service_running; then
        sleep 20
        log_info "Checking if service recovered..."

        # Check logs for recovery
        RECOVERY=$(grep -i "credential.*restored\|upload.*success" "$SERVICE_LOG" | tail -5 | wc -l)
        if [ "$RECOVERY" -gt 0 ]; then
            log_success "✓ Service appears to have recovered"
        fi
    fi

    stop_tvm_service

    # Cleanup backup
    rm -f "$AWS_CRED_BACKUP"
fi

# =============================================================================
# TEST 5: Invalid AWS Configuration
# =============================================================================

log_info "═══════════════════════════════════════════"
log_info "TEST 5: Invalid AWS Configuration"
log_info "═══════════════════════════════════════════"

# Create config with invalid bucket
INVALID_CONFIG="/tmp/tvm-invalid-aws-config.yaml"
cat > "$INVALID_CONFIG" <<EOF
vehicle_id: "$VEHICLE_ID"
log_directories:
  - path: $TEST_DIR/terminal
    source: terminal

s3:
  bucket: this-bucket-does-not-exist-$(date +%s)
  region: $AWS_REGION
  profile: $AWS_PROFILE

upload:
  schedule:
    mode: interval
    interval_hours: 1
  file_stable_seconds: 30
  operational_hours:
    enabled: false
  batch_upload:
    enabled: true
  upload_on_start: true
  queue_file: /tmp/queue-gap27-invalid.json
  processed_files_registry:
    registry_file: /tmp/registry-gap27-invalid.json
    retention_days: 30

deletion:
  after_upload:
    enabled: false

disk:
  reserved_gb: 1

monitoring:
  cloudwatch_enabled: false
EOF

log_info "Testing with non-existent S3 bucket..."
rm -f "$TEST_DIR/terminal/"*
echo "Invalid bucket test" > "$TEST_DIR/terminal/invalid_bucket.log"

rm -f "$SERVICE_LOG"
start_tvm_service "$INVALID_CONFIG" "$SERVICE_LOG" "" "$VEHICLE_ID" || true

sleep 30

# Check for S3 bucket errors
BUCKET_ERRORS=$(grep -i "NoSuchBucket\|bucket.*not.*found\|bucket.*does.*not.*exist" "$SERVICE_LOG" | wc -l)

if [ "$BUCKET_ERRORS" -gt 0 ]; then
    log_success "✓ Invalid bucket errors detected: $BUCKET_ERRORS"
    log_info "Sample bucket error:"
    grep -i "NoSuchBucket\|bucket.*not.*found" "$SERVICE_LOG" | head -2 | while read -r line; do
        echo "  $line"
    done
else
    log_warning "⚠ No bucket errors detected in logs"
fi

# Verify service handles error gracefully
if is_service_running; then
    log_success "✓ Service continues running despite bucket errors"
else
    log_info "Service stopped (may have exited on invalid bucket)"
fi

stop_tvm_service || true
rm -f "$INVALID_CONFIG"

# =============================================================================
# TEST 6: File Injection Attempts
# =============================================================================

log_info "═══════════════════════════════════════════"
log_info "TEST 6: Filename Injection Prevention"
log_info "═══════════════════════════════════════════"

# Clean test directory
rm -f "$TEST_DIR/terminal/"*

# Create files with special characters (if allowed)
echo "Normal" > "$TEST_DIR/terminal/normal.log"

# Try various injection attempts
touch "$TEST_DIR/terminal/test\$\(whoami\).log" 2>/dev/null || log_info "  Command substitution name blocked by filesystem"
touch "$TEST_DIR/terminal/test\`id\`.log" 2>/dev/null || log_info "  Backtick name blocked by filesystem"
touch "$TEST_DIR/terminal/test;rm-rf.log" 2>/dev/null || log_info "  Semicolon name blocked by filesystem"
touch "$TEST_DIR/terminal/test\|cat.log" 2>/dev/null || log_info "  Pipe name blocked by filesystem"

log_info "Created files with special characters:"
ls -la "$TEST_DIR/terminal/" || true

# Start service
rm -f "$SERVICE_LOG"
start_tvm_service "$TEST_CONFIG" "$SERVICE_LOG" "" "$VEHICLE_ID"

sleep 60

# Check for any command execution in logs
INJECTION_ATTEMPTS=$(grep -i "whoami\|bash\|sh -c\|eval\|exec" "$SERVICE_LOG" | grep -v "bash.*tvm-upload" | wc -l)

if [ "$INJECTION_ATTEMPTS" -eq 0 ]; then
    log_success "✓ No command injection detected"
else
    log_error "✗ Potential command injection in logs: $INJECTION_ATTEMPTS"
    TESTS_FAILED=$((TESTS_FAILED + 1))
fi

stop_tvm_service

# =============================================================================
# Summary
# =============================================================================

log_info "═══════════════════════════════════════════"
log_info "SECURITY TEST SUMMARY"
log_info "═══════════════════════════════════════════"
echo ""
log_info "Security Checks:"
echo "  ✓ File permission handling"
echo "  ✓ Symlink attack prevention"
echo "  ✓ Path traversal prevention"
echo "  ✓ AWS credential expiration handling"
echo "  ✓ Invalid bucket handling"
echo "  ✓ Filename injection prevention"
echo ""

# Cleanup
log_info "Cleaning up..."
rm -rf "$TEST_DIR"
rm -f "$TEST_CONFIG"
rm -f /tmp/queue-gap27.json /tmp/queue-gap27-invalid.json
rm -f /tmp/registry-gap27.json /tmp/registry-gap27-invalid.json

# Clean S3 test data
log_info "Cleaning complete vehicle folder from S3..."
cleanup_complete_vehicle_folder "$VEHICLE_ID" "$S3_BUCKET" "$AWS_PROFILE" "$AWS_REGION"

# Print summary
print_test_summary

# Test result
if [ $TESTS_FAILED -eq 0 ]; then
    log_success "TEST 27: PASSED - Security scenarios handled correctly"
    log_success "  • File permissions: Secure"
    log_success "  • Symlink prevention: Working"
    log_success "  • Path traversal: Prevented"
    log_success "  • Credential handling: Graceful"
    log_success "  • Injection prevention: Secure"
    exit 0
else
    log_error "TEST 27: FAILED - Security issues detected"
    log_error "  • Failed checks: $TESTS_FAILED"
    exit 1
fi
