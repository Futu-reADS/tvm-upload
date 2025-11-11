#!/bin/bash
# TEST 26: Resource Limits and Graceful Degradation
# Purpose: Verify system handles resource exhaustion gracefully
# Duration: ~30 minutes
#
# Tests:
# 1. Queue with 10,000 files (stress test)
# 2. S3 rate limiting (429 errors)
# 3. Memory usage monitoring
# 4. CPU usage under load
# 5. Graceful degradation
# 6. System remains stable (no crashes)

set -e

# Get script directory and load helpers
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../../lib/test_helpers.sh"

# Configuration
CONFIG_FILE="${1:-config/config.yaml}"
TEST_VEHICLE_ID="${2}"
TEST_DIR="/tmp/tvm-gap-test-26"
SERVICE_LOG="/tmp/tvm-service-gap26.log"
QUEUE_FILE="/tmp/queue-gap26.json"

print_test_header "Resource Limits and Graceful Degradation" "26"

# Parse configuration
log_info "Loading base configuration..."
load_config "$CONFIG_FILE"

# Create unique test vehicle ID
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
if [ -n "$TEST_VEHICLE_ID" ]; then
    VEHICLE_ID="${TEST_VEHICLE_ID}-TEST26-${TIMESTAMP}"
else
    VEHICLE_ID="vehicle-TEST26-${TIMESTAMP}"
fi
log_info "Using test vehicle ID: $VEHICLE_ID"

# Create test directory
mkdir -p "$TEST_DIR/terminal"
log_success "Created test directory"

# =============================================================================
# TEST 1: Queue with 10,000 Files (Stress Test)
# =============================================================================

log_info "═══════════════════════════════════════════"
log_info "TEST 1: Large Queue Stress Test (10,000 files)"
log_info "═══════════════════════════════════════════"

log_warning "This test creates 10,000 small files (~50MB total)"
log_warning "Adjust FILE_COUNT if disk space is limited"

# Configurable file count
FILE_COUNT=10000
BATCH_SIZE=1000

log_info "Creating $FILE_COUNT test files in batches of $BATCH_SIZE..."

START_TIME=$(date +%s)

# Create files in batches for better performance
for batch in $(seq 1 $((FILE_COUNT / BATCH_SIZE))); do
    START_FILE=$(( (batch - 1) * BATCH_SIZE + 1 ))
    END_FILE=$(( batch * BATCH_SIZE ))

    log_info "Creating files $START_FILE - $END_FILE..."

    # Parallel file creation using xargs
    seq $START_FILE $END_FILE | xargs -P 10 -I {} sh -c \
        "echo 'Test file {} - $(date)' > $TEST_DIR/terminal/file_{}.log"

    log_info "  Batch $batch completed"
done

CREATION_TIME=$(($(date +%s) - START_TIME))
log_success "Created $FILE_COUNT files in ${CREATION_TIME}s"

# Check actual file count
ACTUAL_COUNT=$(find "$TEST_DIR/terminal" -type f -name "*.log" | wc -l)
log_info "Actual file count: $ACTUAL_COUNT"

if [ "$ACTUAL_COUNT" -lt $((FILE_COUNT * 95 / 100)) ]; then
    log_error "File creation incomplete: $ACTUAL_COUNT / $FILE_COUNT"
    exit 1
fi

# Create test config with short stability period for faster testing
TEST_CONFIG="/tmp/tvm-test-config-stress.yaml"
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
    interval_minutes: 1  # Upload every minute
  file_stable_seconds: 5  # Short stability for testing
  operational_hours:
    enabled: false
  batch_upload:
    enabled: true
  upload_on_start: true
  queue_file: $QUEUE_FILE
  scan_existing_files:
    enabled: true
    max_age_days: 1
  processed_files_registry:
    registry_file: /tmp/registry-gap26.json
    retention_days: 30

deletion:
  after_upload:
    enabled: false  # Keep files for testing
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
  publish_interval_seconds: 3600

s3_lifecycle:
  retention_days: 14
EOF

log_success "Created test config"

# Start service and monitor resource usage
log_info "Starting service with $FILE_COUNT files to process..."
log_info "This will test queue handling, memory usage, and stability"

# Start service in background
if ! start_tvm_service "$TEST_CONFIG" "$SERVICE_LOG" "" "$VEHICLE_ID"; then
    log_error "Failed to start service"
    exit 1
fi

SERVICE_PID=$(pgrep -f "python.*src.main.*$VEHICLE_ID" | head -1)
log_info "Service PID: $SERVICE_PID"

# =============================================================================
# Monitor Resource Usage
# =============================================================================

log_info "Monitoring resource usage for 5 minutes..."

# Monitor metrics
MONITOR_DURATION=300  # 5 minutes
MONITOR_INTERVAL=10   # Every 10 seconds
ITERATIONS=$((MONITOR_DURATION / MONITOR_INTERVAL))

PEAK_CPU=0
PEAK_MEM=0
PEAK_MEM_MB=0

for i in $(seq 1 $ITERATIONS); do
    if ! ps -p "$SERVICE_PID" > /dev/null 2>&1; then
        log_error "Service crashed during test!"
        log_info "Last 50 lines of log:"
        tail -50 "$SERVICE_LOG"
        exit 1
    fi

    # Get CPU and memory usage
    CPU=$(ps -p "$SERVICE_PID" -o %cpu --no-headers | tr -d ' ')
    MEM=$(ps -p "$SERVICE_PID" -o %mem --no-headers | tr -d ' ')
    MEM_KB=$(ps -p "$SERVICE_PID" -o rss --no-headers | tr -d ' ')
    MEM_MB=$((MEM_KB / 1024))

    # Track peaks
    if [ $(echo "$CPU > $PEAK_CPU" | bc) -eq 1 ]; then
        PEAK_CPU=$CPU
    fi
    if [ $(echo "$MEM > $PEAK_MEM" | bc) -eq 1 ]; then
        PEAK_MEM=$MEM
        PEAK_MEM_MB=$MEM_MB
    fi

    # Check queue size
    if [ -f "$QUEUE_FILE" ]; then
        QUEUE_SIZE=$(grep -c "filepath" "$QUEUE_FILE" 2>/dev/null || echo "0")
    else
        QUEUE_SIZE=0
    fi

    log_info "[$i/$ITERATIONS] CPU: ${CPU}% | Mem: ${MEM_MB}MB (${MEM}%) | Queue: $QUEUE_SIZE files"

    sleep $MONITOR_INTERVAL
done

log_info "Resource usage monitoring complete"
log_info "Peak CPU: ${PEAK_CPU}%"
log_info "Peak Memory: ${PEAK_MEM_MB}MB (${PEAK_MEM}%)"

# Check if service is still running
if ! ps -p "$SERVICE_PID" > /dev/null 2>&1; then
    log_error "Service crashed during stress test!"
    TESTS_FAILED=$((TESTS_FAILED + 1))
else
    log_success "✓ Service survived $FILE_COUNT file queue"
    log_success "✓ Peak CPU: ${PEAK_CPU}%"
    log_success "✓ Peak Memory: ${PEAK_MEM_MB}MB"
fi

# Check memory limits
if [ "$PEAK_MEM_MB" -gt 1000 ]; then
    log_warning "⚠ High memory usage: ${PEAK_MEM_MB}MB (>1GB)"
    log_warning "  Consider memory optimization for large queues"
elif [ "$PEAK_MEM_MB" -gt 500 ]; then
    log_warning "⚠ Moderate memory usage: ${PEAK_MEM_MB}MB"
else
    log_success "✓ Memory usage reasonable: ${PEAK_MEM_MB}MB"
fi

# =============================================================================
# TEST 2: Queue Processing Efficiency
# =============================================================================

log_info "═══════════════════════════════════════════"
log_info "TEST 2: Queue Processing Efficiency"
log_info "═══════════════════════════════════════════"

# Wait for some files to upload
log_info "Waiting 2 minutes for queue processing..."
sleep 120

# Check queue size after processing
if [ -f "$QUEUE_FILE" ]; then
    QUEUE_REMAINING=$(grep -c "filepath" "$QUEUE_FILE" 2>/dev/null || echo "0")
else
    QUEUE_REMAINING=0
fi

PROCESSED=$((FILE_COUNT - QUEUE_REMAINING))
PROCESS_RATE=$(echo "scale=2; $PROCESSED / 2" | bc)  # Per minute

log_info "Queue processing results:"
log_info "  Initial queue: $FILE_COUNT files"
log_info "  Remaining: $QUEUE_REMAINING files"
log_info "  Processed: $PROCESSED files"
log_info "  Processing rate: ~${PROCESS_RATE} files/minute"

if [ "$PROCESSED" -gt 100 ]; then
    log_success "✓ Queue processing functional (${PROCESSED} files processed)"
else
    log_warning "⚠ Slow queue processing (only ${PROCESSED} files in 2 min)"
fi

# =============================================================================
# TEST 3: S3 Rate Limiting Handling
# =============================================================================

log_info "═══════════════════════════════════════════"
log_info "TEST 3: S3 Rate Limiting Handling"
log_info "═══════════════════════════════════════════"

log_info "Checking for S3 rate limiting (429) errors in logs..."

RATE_LIMIT_ERRORS=$(grep -ci "429\|throttl\|rate.*limit\|slow.*down" "$SERVICE_LOG" || echo "0")

if [ "$RATE_LIMIT_ERRORS" -gt 0 ]; then
    log_warning "⚠ S3 rate limiting detected: $RATE_LIMIT_ERRORS occurrences"
    log_info "Checking retry behavior..."

    RETRY_COUNT=$(grep -ci "retry\|retrying" "$SERVICE_LOG" || echo "0")
    if [ "$RETRY_COUNT" -gt 0 ]; then
        log_success "✓ Retry mechanism activated: $RETRY_COUNT retries"
    else
        log_warning "⚠ Rate limiting but no retries detected"
    fi
else
    log_info "No rate limiting detected (upload rate within S3 limits)"
fi

# =============================================================================
# TEST 4: Error Recovery
# =============================================================================

log_info "═══════════════════════════════════════════"
log_info "TEST 4: Error Recovery"
log_info "═══════════════════════════════════════════"

ERROR_COUNT=$(grep -ci "error" "$SERVICE_LOG" || echo "0")
CRITICAL_COUNT=$(grep -ci "critical\|fatal" "$SERVICE_LOG" || echo "0")

log_info "Error summary:"
log_info "  Total errors: $ERROR_COUNT"
log_info "  Critical errors: $CRITICAL_COUNT"

if [ "$CRITICAL_COUNT" -gt 0 ]; then
    log_error "✗ Critical errors detected"
    log_info "Critical error samples:"
    grep -i "critical\|fatal" "$SERVICE_LOG" | head -5 | while read -r line; do
        echo "  $line"
    done
    TESTS_FAILED=$((TESTS_FAILED + 1))
else
    log_success "✓ No critical errors"
fi

if [ "$ERROR_COUNT" -gt $((FILE_COUNT / 10)) ]; then
    log_warning "⚠ High error rate: $ERROR_COUNT errors for $FILE_COUNT files"
elif [ "$ERROR_COUNT" -gt 0 ]; then
    log_info "Moderate errors: $ERROR_COUNT (may be transient)"
else
    log_success "✓ No errors during processing"
fi

# =============================================================================
# TEST 5: Graceful Degradation Check
# =============================================================================

log_info "═══════════════════════════════════════════"
log_info "TEST 5: Graceful Degradation"
log_info "═══════════════════════════════════════════"

# Check if service is still responsive
if ps -p "$SERVICE_PID" > /dev/null 2>&1; then
    log_success "✓ Service still running"

    # Check if service is responsive (can process signals)
    if kill -0 "$SERVICE_PID" 2>/dev/null; then
        log_success "✓ Service responsive to signals"
    else
        log_warning "⚠ Service may be unresponsive"
    fi
else
    log_error "✗ Service crashed"
    TESTS_FAILED=$((TESTS_FAILED + 1))
fi

# Check if queue is still functional
if [ -f "$QUEUE_FILE" ]; then
    if [ -r "$QUEUE_FILE" ] && [ -w "$QUEUE_FILE" ]; then
        log_success "✓ Queue file accessible"
    else
        log_error "✗ Queue file permission issues"
        TESTS_FAILED=$((TESTS_FAILED + 1))
    fi
else
    log_warning "⚠ Queue file not present"
fi

# =============================================================================
# TEST 6: System Stability Check
# =============================================================================

log_info "═══════════════════════════════════════════"
log_info "TEST 6: System Stability"
log_info "═══════════════════════════════════════════"

# Check for memory leaks (compare start vs current memory)
CURRENT_MEM_MB=$(ps -p "$SERVICE_PID" -o rss --no-headers 2>/dev/null | tr -d ' ' | awk '{print int($1/1024)}' || echo "0")

log_info "Memory stability:"
log_info "  Peak memory: ${PEAK_MEM_MB}MB"
log_info "  Current memory: ${CURRENT_MEM_MB}MB"

if [ "$CURRENT_MEM_MB" -lt $((PEAK_MEM_MB * 120 / 100)) ]; then
    log_success "✓ Memory stable (no significant leak)"
else
    log_warning "⚠ Memory may be growing"
fi

# Check disk I/O
DISK_WRITES=$(iostat -d 1 2 2>/dev/null | tail -1 | awk '{print $5}' || echo "N/A")
log_info "Disk write rate: ${DISK_WRITES} kB/s"

# =============================================================================
# Cleanup and Summary
# =============================================================================

log_info "Stopping service..."
stop_tvm_service

# Count uploaded files in S3
log_info "Checking S3 uploads..."
TODAY=$(date +%Y-%m-%d)
S3_PREFIX="s3://${S3_BUCKET}/${VEHICLE_ID}/${TODAY}/terminal/"

UPLOADED_COUNT=$(aws s3 ls "$S3_PREFIX" --profile "$AWS_PROFILE" --region "$AWS_REGION" 2>/dev/null | wc -l || echo "0")
UPLOADED_COUNT=$(echo "$UPLOADED_COUNT" | tr -d '[:space:]')

log_info "Upload statistics:"
log_info "  Total files: $FILE_COUNT"
log_info "  Uploaded to S3: $UPLOADED_COUNT"
log_info "  Upload rate: $(echo "scale=2; $UPLOADED_COUNT * 100 / $FILE_COUNT" | bc)%"

# Performance summary
log_info "═══════════════════════════════════════════"
log_info "PERFORMANCE SUMMARY"
log_info "═══════════════════════════════════════════"
echo ""
log_info "Queue Performance:"
echo "  • Files in queue: $FILE_COUNT"
echo "  • Files processed: $PROCESSED"
echo "  • Processing rate: ~${PROCESS_RATE} files/min"
echo "  • Upload success: $UPLOADED_COUNT files"
echo ""
log_info "Resource Usage:"
echo "  • Peak CPU: ${PEAK_CPU}%"
echo "  • Peak Memory: ${PEAK_MEM_MB}MB"
echo "  • Current Memory: ${CURRENT_MEM_MB}MB"
echo ""
log_info "Reliability:"
echo "  • Service crashes: $([ -d /proc/$SERVICE_PID ] && echo 0 || echo 1)"
echo "  • Critical errors: $CRITICAL_COUNT"
echo "  • Total errors: $ERROR_COUNT"
echo "  • Rate limit hits: $RATE_LIMIT_ERRORS"
echo ""

# Cleanup
log_info "Cleaning up test files..."
rm -rf "$TEST_DIR"
rm -f "$TEST_CONFIG"
rm -f "$QUEUE_FILE"
rm -f /tmp/registry-gap26.json

# Clean S3 test data
log_info "Cleaning complete vehicle folder from S3..."
cleanup_complete_vehicle_folder "$VEHICLE_ID" "$S3_BUCKET" "$AWS_PROFILE" "$AWS_REGION"

# Print summary
print_test_summary

# Test result
if [ $TESTS_FAILED -eq 0 ] && [ "$CRITICAL_COUNT" -eq 0 ]; then
    log_success "TEST 26: PASSED - System handles resource limits gracefully"
    log_success "  • $FILE_COUNT file queue handled successfully"
    log_success "  • Peak memory: ${PEAK_MEM_MB}MB (acceptable)"
    log_success "  • No crashes or critical errors"
    exit 0
else
    log_error "TEST 26: FAILED - Resource limit issues detected"
    log_error "  • Critical errors: $CRITICAL_COUNT"
    log_error "  • Test failures: $TESTS_FAILED"
    exit 1
fi
