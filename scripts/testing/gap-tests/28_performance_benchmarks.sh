#!/bin/bash
# TEST 28: Performance Benchmarks
# Purpose: Establish performance baselines for the TVM upload system
# Duration: ~15-20 minutes
#
# Performance Metrics:
# 1. File Processing Throughput (files/minute)
# 2. Upload Speed (MB/s)
# 3. Queue Processing Efficiency
# 4. Resource Usage (CPU%, Memory MB)
# 5. System Stability Under Load

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../../lib/test_helpers.sh"

CONFIG_FILE="${1:-config/config.yaml}"
TEST_VEHICLE_ID="${2}"
TEST_DIR="/tmp/tvm-gap-test-28"
SERVICE_LOG="/tmp/tvm-service-gap28.log"
QUEUE_FILE="/tmp/queue-gap28.json"
REGISTRY_FILE="/tmp/registry-gap28.json"

print_test_header "Performance Benchmarks" "28"

load_config "$CONFIG_FILE"

TIMESTAMP=$(date +%Y%m%d-%H%M%S)
if [ -n "$TEST_VEHICLE_ID" ]; then
    VEHICLE_ID="${TEST_VEHICLE_ID}-TEST28-${TIMESTAMP}"
else
    VEHICLE_ID="vehicle-CN-GAP-TEST28-${TIMESTAMP}"
fi
log_info "Using test vehicle ID: $VEHICLE_ID"

# Create test directory
mkdir -p "$TEST_DIR/terminal"
log_success "Created test directory"

# =============================================================================
# BENCHMARK 1: File Detection Performance
# =============================================================================

log_info "═══════════════════════════════════════════"
log_info "BENCHMARK 1: File Detection Performance"
log_info "═══════════════════════════════════════════"

# Create test config with short intervals for faster testing
TEST_CONFIG="/tmp/tvm-test-config-perf.yaml"
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
  file_stable_seconds: 5
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
    registry_file: $REGISTRY_FILE
    retention_days: 30

deletion:
  after_upload:
    enabled: false

disk:
  reserved_gb: 1
  warning_threshold: 0.90
  critical_threshold: 0.95

monitoring:
  cloudwatch_enabled: false
EOF

log_info "Creating 100 test files for detection benchmark..."
START_TIME=$(date +%s)

for i in $(seq 1 100); do
    echo "Performance test file $i - $(date +%s%N)" > "$TEST_DIR/terminal/perf_detect_$i.log"
done

CREATION_TIME=$(($(date +%s) - START_TIME))
log_info "Created 100 files in ${CREATION_TIME}s"

# Start service
log_info "Starting service..."
if ! start_tvm_service "$TEST_CONFIG" "$SERVICE_LOG" "" "$VEHICLE_ID"; then
    log_error "Failed to start service"
    exit 1
fi

SERVICE_PID=$(pgrep -f "python.*src.main.*$VEHICLE_ID" | head -1)
log_info "Service PID: $SERVICE_PID"

# Monitor file detection
log_info "Monitoring file detection for 30 seconds..."
sleep 30

DETECTED=$(grep -c "File ready:\|Added to queue:" "$SERVICE_LOG" 2>/dev/null || echo "0")
DETECTED=$(echo "$DETECTED" | tr -d '\n' | awk '{print $1}')  # Remove newlines and take first number
DETECTION_RATE=$(echo "scale=2; $DETECTED / 30 * 60" | bc 2>/dev/null || echo "0")  # Files per minute

log_info "Detection Performance:"
log_info "  • Files detected: $DETECTED / 100"
log_info "  • Detection rate: ~${DETECTION_RATE} files/minute"

if [ "$DETECTED" -ge 95 ]; then
    log_success "✓ Excellent detection performance (${DETECTED}/100 files)"
    BENCHMARK_1_SCORE=100
elif [ "$DETECTED" -ge 80 ]; then
    log_success "✓ Good detection performance (${DETECTED}/100 files)"
    BENCHMARK_1_SCORE=80
else
    log_warning "⚠ Slow detection performance (${DETECTED}/100 files)"
    BENCHMARK_1_SCORE=60
fi

# =============================================================================
# BENCHMARK 2: Upload Throughput and Speed
# =============================================================================

log_info "═══════════════════════════════════════════"
log_info "BENCHMARK 2: Upload Throughput and Speed"
log_info "═══════════════════════════════════════════"

# Clean directory and create test files of various sizes
rm -f "$TEST_DIR/terminal/"*

log_info "Creating 50 files (mix of small, medium sizes)..."
# 30 small files (10KB each)
for i in $(seq 1 30); do
    dd if=/dev/zero of="$TEST_DIR/terminal/small_$i.log" bs=1024 count=10 2>/dev/null
done
# 20 medium files (100KB each)
for i in $(seq 1 20); do
    dd if=/dev/zero of="$TEST_DIR/terminal/medium_$i.log" bs=1024 count=100 2>/dev/null
done

TOTAL_SIZE_KB=$(du -sk "$TEST_DIR/terminal" | awk '{print $1}')
TOTAL_SIZE_MB=$(echo "scale=2; $TOTAL_SIZE_KB / 1024" | bc)

log_info "Total data size: ${TOTAL_SIZE_MB}MB (50 files)"

# Wait for files to stabilize and start uploading
log_info "Waiting 10 seconds for file stability..."
sleep 10

UPLOAD_START=$(date +%s)

# Wait for uploads to complete (check every 10 seconds)
log_info "Monitoring upload progress..."
MAX_WAIT=300  # 5 minutes max
ELAPSED=0

while [ $ELAPSED -lt $MAX_WAIT ]; do
    UPLOADED=$(grep -c "Successfully uploaded\|Upload successful" "$SERVICE_LOG" 2>/dev/null || echo "0")
    UPLOADED=$(echo "$UPLOADED" | tr -d '\n' | awk '{print $1}')  # Clean newlines

    if [ "$UPLOADED" -ge 45 ]; then  # 90% uploaded
        log_info "Upload threshold reached: $UPLOADED files"
        break
    fi

    sleep 10
    ELAPSED=$((ELAPSED + 10))
    log_info "  Progress: $UPLOADED / 50 files uploaded (${ELAPSED}s elapsed)"
done

UPLOAD_END=$(date +%s)
UPLOAD_DURATION=$((UPLOAD_END - UPLOAD_START))
[ $UPLOAD_DURATION -eq 0 ] && UPLOAD_DURATION=1  # Avoid division by zero

UPLOADED=$(grep -c "Successfully uploaded\|Upload successful" "$SERVICE_LOG" 2>/dev/null || echo "0")
UPLOADED=$(echo "$UPLOADED" | tr -d '\n' | awk '{print $1}')  # Clean newlines
UPLOAD_RATE=$(echo "scale=2; $UPLOADED / $UPLOAD_DURATION * 60" | bc 2>/dev/null || echo "0")  # Files per minute
UPLOAD_SPEED_MBPS=$(echo "scale=2; $TOTAL_SIZE_MB / $UPLOAD_DURATION" | bc 2>/dev/null || echo "0")  # MB/s

log_info "Upload Performance:"
log_info "  • Files uploaded: $UPLOADED / 50"
log_info "  • Upload duration: ${UPLOAD_DURATION}s"
log_info "  • Upload rate: ~${UPLOAD_RATE} files/minute"
log_info "  • Upload speed: ~${UPLOAD_SPEED_MBPS} MB/s"

if [ "$UPLOADED" -ge 45 ]; then
    log_success "✓ Excellent upload performance (${UPLOADED}/50 files in ${UPLOAD_DURATION}s)"
    BENCHMARK_2_SCORE=100
elif [ "$UPLOADED" -ge 35 ]; then
    log_success "✓ Good upload performance (${UPLOADED}/50 files in ${UPLOAD_DURATION}s)"
    BENCHMARK_2_SCORE=80
else
    log_warning "⚠ Slow upload performance (${UPLOADED}/50 files in ${UPLOAD_DURATION}s)"
    BENCHMARK_2_SCORE=60
fi

# =============================================================================
# BENCHMARK 3: Queue Processing Efficiency
# =============================================================================

log_info "═══════════════════════════════════════════"
log_info "BENCHMARK 3: Queue Processing Efficiency"
log_info "═══════════════════════════════════════════"

# Clean and create many small files
rm -f "$TEST_DIR/terminal/"*

log_info "Creating 200 small files for queue test..."
for i in $(seq 1 200); do
    echo "Queue test $i - $(date +%s%N)" > "$TEST_DIR/terminal/queue_$i.log"
done

# Wait for files to be queued
log_info "Waiting 15 seconds for queueing..."
sleep 15

if [ -f "$QUEUE_FILE" ]; then
    QUEUE_SIZE=$(grep -c "filepath" "$QUEUE_FILE" 2>/dev/null || echo "0")
    QUEUE_SIZE=$(echo "$QUEUE_SIZE" | tr -d '\n' | awk '{print $1}')  # Clean newlines
else
    QUEUE_SIZE=0
fi

log_info "Initial queue size: $QUEUE_SIZE files"

# Monitor queue processing for 2 minutes
log_info "Monitoring queue processing for 120 seconds..."
QUEUE_START=$(date +%s)
sleep 120
QUEUE_END=$(date +%s)

if [ -f "$QUEUE_FILE" ]; then
    QUEUE_REMAINING=$(grep -c "filepath" "$QUEUE_FILE" 2>/dev/null || echo "0")
    QUEUE_REMAINING=$(echo "$QUEUE_REMAINING" | tr -d '\n' | awk '{print $1}')  # Clean newlines
else
    QUEUE_REMAINING=0
fi

QUEUE_PROCESSED=$((QUEUE_SIZE - QUEUE_REMAINING))
QUEUE_RATE=$(echo "scale=2; $QUEUE_PROCESSED / 2" | bc 2>/dev/null || echo "0")  # Per minute

log_info "Queue Processing Performance:"
log_info "  • Initial queue: $QUEUE_SIZE files"
log_info "  • Processed: $QUEUE_PROCESSED files"
log_info "  • Remaining: $QUEUE_REMAINING files"
log_info "  • Processing rate: ~${QUEUE_RATE} files/minute"

if [ "$QUEUE_PROCESSED" -ge 150 ]; then
    log_success "✓ Excellent queue processing (${QUEUE_PROCESSED}/200 files)"
    BENCHMARK_3_SCORE=100
elif [ "$QUEUE_PROCESSED" -ge 100 ]; then
    log_success "✓ Good queue processing (${QUEUE_PROCESSED}/200 files)"
    BENCHMARK_3_SCORE=80
else
    log_warning "⚠ Slow queue processing (${QUEUE_PROCESSED}/200 files)"
    BENCHMARK_3_SCORE=60
fi

# =============================================================================
# BENCHMARK 4: Resource Usage
# =============================================================================

log_info "═══════════════════════════════════════════"
log_info "BENCHMARK 4: Resource Usage"
log_info "═══════════════════════════════════════════"

if ! ps -p "$SERVICE_PID" > /dev/null 2>&1; then
    log_error "Service crashed during benchmarks!"
    TESTS_FAILED=$((TESTS_FAILED + 1))
    BENCHMARK_4_SCORE=0
else
    # Get resource usage
    CPU=$(ps -p "$SERVICE_PID" -o %cpu --no-headers | tr -d ' ')
    MEM=$(ps -p "$SERVICE_PID" -o %mem --no-headers | tr -d ' ')
    MEM_KB=$(ps -p "$SERVICE_PID" -o rss --no-headers | tr -d ' ')
    MEM_MB=$((MEM_KB / 1024))

    log_info "Current Resource Usage:"
    log_info "  • CPU: ${CPU}%"
    log_info "  • Memory: ${MEM_MB}MB (${MEM}%)"

    # Score based on memory usage
    if [ "$MEM_MB" -lt 200 ]; then
        log_success "✓ Excellent resource efficiency (<200MB)"
        BENCHMARK_4_SCORE=100
    elif [ "$MEM_MB" -lt 500 ]; then
        log_success "✓ Good resource efficiency (<500MB)"
        BENCHMARK_4_SCORE=80
    elif [ "$MEM_MB" -lt 1000 ]; then
        log_warning "⚠ Moderate resource usage (<1GB)"
        BENCHMARK_4_SCORE=60
    else
        log_warning "⚠ High resource usage (>1GB)"
        BENCHMARK_4_SCORE=40
    fi
fi

# =============================================================================
# BENCHMARK 5: System Stability
# =============================================================================

log_info "═══════════════════════════════════════════"
log_info "BENCHMARK 5: System Stability"
log_info "═══════════════════════════════════════════"

# Check for errors (look for [ERROR] level logs, not filenames containing "error")
ERROR_COUNT=$(grep -c "\[ERROR\]" "$SERVICE_LOG" 2>/dev/null || echo "0")
ERROR_COUNT=$(echo "$ERROR_COUNT" | tr -d '\n' | awk '{print $1}')  # Clean newlines
CRITICAL_COUNT=$(grep -ci "\[CRITICAL\]\|FATAL" "$SERVICE_LOG" 2>/dev/null || echo "0")
CRITICAL_COUNT=$(echo "$CRITICAL_COUNT" | tr -d '\n' | awk '{print $1}')  # Clean newlines

log_info "Stability Metrics:"
log_info "  • Total errors: $ERROR_COUNT"
log_info "  • Critical errors: $CRITICAL_COUNT"
log_info "  • Service running: $(ps -p "$SERVICE_PID" > /dev/null 2>&1 && echo "Yes" || echo "No")"

if [ "$CRITICAL_COUNT" -eq 0 ] && ps -p "$SERVICE_PID" > /dev/null 2>&1; then
    if [ "$ERROR_COUNT" -lt 10 ]; then
        log_success "✓ Excellent stability (no crashes, minimal errors)"
        BENCHMARK_5_SCORE=100
    elif [ "$ERROR_COUNT" -lt 50 ]; then
        log_success "✓ Good stability (no crashes, some errors)"
        BENCHMARK_5_SCORE=80
    else
        log_warning "⚠ Moderate stability (many errors)"
        BENCHMARK_5_SCORE=60
    fi
else
    log_error "✗ Poor stability (crashes or critical errors)"
    BENCHMARK_5_SCORE=40
    TESTS_FAILED=$((TESTS_FAILED + 1))
fi

# =============================================================================
# Performance Summary and Scoring
# =============================================================================

log_info "═══════════════════════════════════════════"
log_info "PERFORMANCE BENCHMARK SUMMARY"
log_info "═══════════════════════════════════════════"
echo ""

# Calculate overall score
OVERALL_SCORE=$(echo "scale=1; ($BENCHMARK_1_SCORE + $BENCHMARK_2_SCORE + $BENCHMARK_3_SCORE + $BENCHMARK_4_SCORE + $BENCHMARK_5_SCORE) / 5" | bc)

log_info "Individual Benchmark Scores (out of 100):"
echo "  1. File Detection:      $BENCHMARK_1_SCORE"
echo "  2. Upload Throughput:   $BENCHMARK_2_SCORE"
echo "  3. Queue Processing:    $BENCHMARK_3_SCORE"
echo "  4. Resource Usage:      $BENCHMARK_4_SCORE"
echo "  5. System Stability:    $BENCHMARK_5_SCORE"
echo ""
log_info "Overall Performance Score: ${OVERALL_SCORE}/100"
echo ""

if [ $(echo "$OVERALL_SCORE >= 90" | bc) -eq 1 ]; then
    log_success "Performance Grade: A (Excellent)"
elif [ $(echo "$OVERALL_SCORE >= 80" | bc) -eq 1 ]; then
    log_success "Performance Grade: B (Good)"
elif [ $(echo "$OVERALL_SCORE >= 70" | bc) -eq 1 ]; then
    log_warning "Performance Grade: C (Acceptable)"
else
    log_warning "Performance Grade: D (Needs Improvement)"
fi

echo ""
log_info "Performance Baselines Established:"
echo "  • Detection rate: ~${DETECTION_RATE} files/min"
echo "  • Upload rate: ~${UPLOAD_RATE} files/min"
echo "  • Upload speed: ~${UPLOAD_SPEED_MBPS} MB/s"
echo "  • Queue processing: ~${QUEUE_RATE} files/min"
echo "  • Memory usage: ${MEM_MB}MB"
echo "  • CPU usage: ${CPU}%"
echo ""

# Cleanup
log_info "Stopping service and cleaning up..."
stop_tvm_service || true
rm -rf "$TEST_DIR"
rm -f "$TEST_CONFIG"
rm -f "$QUEUE_FILE"
rm -f "$REGISTRY_FILE"

# Clean S3 test data
log_info "Cleaning complete vehicle folder from S3..."
cleanup_complete_vehicle_folder "$VEHICLE_ID" "$S3_BUCKET" "$AWS_PROFILE" "$AWS_REGION"

# Print summary
print_test_summary

# Test result
if [ $(echo "$OVERALL_SCORE >= 70" | bc) -eq 1 ] && [ $TESTS_FAILED -eq 0 ]; then
    log_success "TEST 28: PASSED - Performance benchmarks completed"
    log_success "  • Overall score: ${OVERALL_SCORE}/100"
    log_success "  • All stability checks passed"
    log_success "  • Performance baselines established"
    exit 0
else
    log_error "TEST 28: FAILED - Performance issues detected"
    log_error "  • Overall score: ${OVERALL_SCORE}/100"
    log_error "  • Some benchmarks below acceptable thresholds"
    exit 1
fi
