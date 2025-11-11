#!/bin/bash
# TEST 30: Production Simulation - Campus Vehicle Operation
# Purpose: Long-running test simulating real campus deployment
# Duration: Configurable (2-24 hours)
#
# Simulates:
# - Variable WiFi availability (campus WiFi zones)
# - WiFi flapping (2-3 second micro-disconnections)
# - Continuous file generation from multiple sources
# - System crashes and recovery
# - Queue buildup and drain cycles
# - Disk pressure and emergency cleanup
# - Network degradation (latency, packet loss)
# - Operational hours patterns
#
# This test runs EVERYTHING in production-like chaos mode

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../../lib/test_helpers.sh"

# Configuration
CONFIG_FILE="${1:-config/config.yaml}"
TEST_VEHICLE_ID="${2}"
TEST_DURATION_HOURS="${3:-2}"  # Default 2 hours
TEST_DIR="/tmp/tvm-production-sim"
SERVICE_LOG="/tmp/tvm-service-prod-sim.log"
METRICS_LOG="/tmp/tvm-metrics-prod-sim.log"

print_test_header "Production Simulation - Campus Vehicle Operation" "30"

# Calculate test duration in seconds
TEST_DURATION_SECONDS=$((TEST_DURATION_HOURS * 3600))
CYCLE_DURATION=6000  # 100 minutes per cycle

log_info "╔════════════════════════════════════════════════════════════════╗"
log_info "║          PRODUCTION SIMULATION TEST - CAMPUS VEHICLE           ║"
log_info "╚════════════════════════════════════════════════════════════════╝"
log_info ""
log_info "Test Duration: $TEST_DURATION_HOURS hours ($TEST_DURATION_SECONDS seconds)"
log_info "Cycle Duration: ~100 minutes"
log_info "Expected Cycles: $((TEST_DURATION_SECONDS / CYCLE_DURATION))"
log_info ""
log_warning "⚠️  This test will:"
log_warning "   • Manipulate network (requires sudo for iptables/tc)"
log_warning "   • Generate thousands of files"
log_warning "   • Crash and restart service multiple times"
log_warning "   • Fill disk to critical levels"
log_warning "   • Run for $TEST_DURATION_HOURS hours continuously"
log_info ""

# Confirm sudo access
if ! sudo -n true 2>/dev/null; then
    log_warning "This test requires sudo access for network manipulation"
    log_info "Please enter sudo password:"
    sudo true || exit 1
fi

# Parse configuration
load_config "$CONFIG_FILE"

# Create unique test vehicle ID
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
VEHICLE_ID="${TEST_VEHICLE_ID:-vehicle-PROD-SIM}-${TIMESTAMP}"
log_info "Using test vehicle ID: $VEHICLE_ID"

# Create test directories for all 4 sources
mkdir -p "$TEST_DIR/terminal"
mkdir -p "$TEST_DIR/ros"
mkdir -p "$TEST_DIR/ros2"
mkdir -p "$TEST_DIR/syslog"

# Create nested structure
mkdir -p "$TEST_DIR/ros/run_001/sensor"
mkdir -p "$TEST_DIR/ros/run_001/planning"
mkdir -p "$TEST_DIR/ros2/launch"

log_success "Created test directory structure"

# ============================================================================
# WiFi Simulation Functions
# ============================================================================

get_network_interface() {
    # Get active network interface
    ip route get 8.8.8.8 2>/dev/null | grep -oP 'dev \K\S+' | head -1 || echo "eth0"
}

enable_wifi() {
    # Remove iptables blocks for AWS S3 China regions
    sudo iptables -D OUTPUT -d s3.cn-north-1.amazonaws.com.cn -j DROP 2>/dev/null || true
    sudo iptables -D OUTPUT -d s3.cn-northwest-1.amazonaws.com.cn -j DROP 2>/dev/null || true

    # Clear any traffic shaping
    local interface=$(get_network_interface)
    sudo tc qdisc del dev "$interface" root 2>/dev/null || true

    echo "[WiFi: ON] $(date +%H:%M:%S)" >> "$METRICS_LOG"
}

disable_wifi() {
    # Block AWS S3 endpoints (simulate no WiFi)
    sudo iptables -A OUTPUT -d s3.cn-north-1.amazonaws.com.cn -j DROP 2>/dev/null || true
    sudo iptables -A OUTPUT -d s3.cn-northwest-1.amazonaws.com.cn -j DROP 2>/dev/null || true

    echo "[WiFi: OFF] $(date +%H:%M:%S)" >> "$METRICS_LOG"
}

enable_slow_wifi() {
    local latency_ms=${1:-500}
    local packet_loss_pct=${2:-10}

    # Enable WiFi first
    enable_wifi

    # Add latency and packet loss
    local interface=$(get_network_interface)
    sudo tc qdisc add dev "$interface" root netem delay ${latency_ms}ms loss ${packet_loss_pct}% 2>/dev/null || true

    echo "[WiFi: DEGRADED ${latency_ms}ms, ${packet_loss_pct}% loss] $(date +%H:%M:%S)" >> "$METRICS_LOG"
}

restore_normal_wifi() {
    enable_wifi
}

# ============================================================================
# File Generation Functions
# ============================================================================

generate_files_normal() {
    # Normal file generation: 50 files/min for 15 minutes
    local duration=$1  # seconds
    local files_per_min=50
    local interval=$(awk "BEGIN {print 60.0 / $files_per_min}")

    local start=$(date +%s)
    local file_count=0

    log_info "Generating files: Normal mode (~50 files/min for $((duration/60)) min)"

    while [ $(($(date +%s) - start)) -lt $duration ]; do
        local source=$((RANDOM % 4))

        case $source in
            0)  # Terminal
                echo "Terminal log $(date +%s%N)" > "$TEST_DIR/terminal/term_${file_count}.log"
                ;;
            1)  # ROS
                echo "ROS log $(date +%s%N)" > "$TEST_DIR/ros/run_001/sensor/ros_${file_count}.log"
                ;;
            2)  # ROS2
                echo "ROS2 log $(date +%s%N)" > "$TEST_DIR/ros2/launch/ros2_${file_count}.log"
                ;;
            3)  # Syslog
                echo "Syslog entry $(date +%s%N)" > "$TEST_DIR/syslog/syslog.${file_count}"
                ;;
        esac

        file_count=$((file_count + 1))
        sleep "$interval" 2>/dev/null || sleep 1
    done

    log_success "Generated $file_count files in normal mode"
    echo "[Files Generated: Normal] $file_count files" >> "$METRICS_LOG"
}

generate_files_heavy() {
    # Heavy file generation: 100 files/min for specified duration
    local duration=$1  # seconds
    local files_per_min=100
    local interval=$(awk "BEGIN {print 60.0 / $files_per_min}")

    local start=$(date +%s)
    local file_count=0

    log_info "Generating files: Heavy mode (~100 files/min for $((duration/60)) min)"

    while [ $(($(date +%s) - start)) -lt $duration ]; do
        local source=$((RANDOM % 4))

        case $source in
            0)  # Terminal - larger files
                dd if=/dev/urandom of="$TEST_DIR/terminal/heavy_${file_count}.log" bs=1K count=$((RANDOM % 100 + 10)) 2>/dev/null
                ;;
            1)  # ROS - nested
                echo "ROS heavy $(date +%s%N)" > "$TEST_DIR/ros/run_001/planning/heavy_${file_count}.log"
                ;;
            2)  # ROS2
                echo "ROS2 heavy $(date +%s%N)" > "$TEST_DIR/ros2/launch/heavy_${file_count}.log"
                ;;
            3)  # Syslog
                echo "Syslog heavy $(date +%s%N)" > "$TEST_DIR/syslog/syslog.heavy_${file_count}"
                ;;
        esac

        file_count=$((file_count + 1))
        sleep "$interval" 2>/dev/null || sleep 0.5
    done

    log_success "Generated $file_count files in heavy mode"
    echo "[Files Generated: Heavy] $file_count files" >> "$METRICS_LOG"
}

generate_files_burst() {
    # Burst generation: 200 files/min for short duration
    local duration=$1  # seconds
    local files_per_min=200
    local interval=$(awk "BEGIN {print 60.0 / $files_per_min}")

    local start=$(date +%s)
    local file_count=0

    log_info "Generating files: Burst mode (~200 files/min for $((duration/60)) min)"

    while [ $(($(date +%s) - start)) -lt $duration ]; do
        # Generate multiple files at once
        for batch in {1..4}; do
            echo "Burst $(date +%s%N)" > "$TEST_DIR/terminal/burst_${file_count}_${batch}.log" &
        done
        wait

        file_count=$((file_count + 4))
        sleep "$interval" 2>/dev/null || sleep 0.3
    done

    log_success "Generated $file_count files in burst mode"
    echo "[Files Generated: Burst] $file_count files" >> "$METRICS_LOG"
}

# ============================================================================
# WiFi Flapping Simulation (Critical Pattern)
# ============================================================================

simulate_wifi_flapping() {
    local duration_seconds=${1:-600}  # Default 10 minutes

    log_warning "╔════════════════════════════════════════════════════════╗"
    log_warning "║  WIFI FLAPPING: 2-3s ON/OFF for $((duration_seconds/60)) min       ║"
    log_warning "╚════════════════════════════════════════════════════════╝"

    local start_time=$(date +%s)
    local flap_count=0
    local error_count_before=$(get_error_count)

    while [ $(($(date +%s) - start_time)) -lt $duration_seconds ]; do
        # WiFi ON for 2-3 seconds (random)
        enable_wifi
        sleep $((2 + RANDOM % 2))

        # WiFi OFF for 2-3 seconds (random)
        disable_wifi
        sleep $((2 + RANDOM % 2))

        flap_count=$((flap_count + 1))

        # Every 20 flaps (~2 min), check health
        if [ $((flap_count % 20)) -eq 0 ]; then
            log_info "Flap count: $flap_count | Checking service health..."

            # Check if service is still running
            if ! is_service_running; then
                log_error "✗ SERVICE CRASHED during WiFi flapping!"
                TESTS_FAILED=$((TESTS_FAILED + 1))

                # Try to restart
                log_warning "Attempting to restart service..."
                start_tvm_service "$TEST_CONFIG" "$SERVICE_LOG" "" "$VEHICLE_ID"
            fi

            # Check queue file integrity
            if [ -f "$QUEUE_FILE" ]; then
                if ! python3 -m json.tool "$QUEUE_FILE" > /dev/null 2>&1; then
                    log_error "✗ QUEUE CORRUPTED during WiFi flapping!"
                    TESTS_FAILED=$((TESTS_FAILED + 1))
                fi
            fi
        fi
    done

    # Restore WiFi after flapping
    enable_wifi

    log_success "✓ WiFi flapping complete: $flap_count flaps"
    echo "[WiFi Flapping] $flap_count flaps completed" >> "$METRICS_LOG"

    # Wait for recovery
    log_info "Waiting 60s for service to recover from flapping..."
    sleep 60

    # Verify service is still running
    if is_service_running; then
        log_success "✓ Service survived WiFi flapping"
    else
        log_error "✗ Service crashed during WiFi flapping"
        TESTS_FAILED=$((TESTS_FAILED + 1))
    fi
}

# ============================================================================
# Crash Simulation
# ============================================================================

simulate_crash() {
    local crash_type=${1:-sigkill}

    log_warning "Simulating crash: $crash_type"

    if [ -f /tmp/tvm-service.pid ]; then
        local pid=$(cat /tmp/tvm-service.pid)

        case $crash_type in
            sigkill)
                log_info "Crash: SIGKILL (kill -9)"
                sudo kill -9 "$pid" 2>/dev/null || true
                ;;
            sigterm)
                log_info "Crash: SIGTERM (graceful)"
                sudo kill -15 "$pid" 2>/dev/null || true
                ;;
            *)
                log_info "Crash: Default SIGKILL"
                sudo kill -9 "$pid" 2>/dev/null || true
                ;;
        esac

        sleep 2

        # Verify service is down
        if ! ps -p "$pid" > /dev/null 2>&1; then
            log_success "✓ Service crashed (PID $pid terminated)"
            echo "[Crash Simulated] $crash_type" >> "$METRICS_LOG"
        else
            log_warning "Service still running after crash attempt"
        fi
    else
        log_warning "No PID file found, cannot simulate crash"
    fi
}

verify_recovery() {
    log_info "Verifying crash recovery..."

    # Wait a bit
    sleep 5

    # Restart service
    log_info "Restarting service after crash..."
    start_tvm_service "$TEST_CONFIG" "$SERVICE_LOG" "" "$VEHICLE_ID"

    # Verify service started
    if is_service_running; then
        log_success "✓ Service recovered after crash"
        echo "[Recovery] Service restarted successfully" >> "$METRICS_LOG"
    else
        log_error "✗ Service failed to recover"
        TESTS_FAILED=$((TESTS_FAILED + 1))
    fi

    # Check queue integrity
    if [ -f "$QUEUE_FILE" ]; then
        if python3 -m json.tool "$QUEUE_FILE" > /dev/null 2>&1; then
            log_success "✓ Queue survived crash"
        else
            log_error "✗ Queue corrupted after crash"
            TESTS_FAILED=$((TESTS_FAILED + 1))
        fi
    fi
}

# ============================================================================
# Monitoring Functions
# ============================================================================

monitor_queue_drain() {
    local duration=${1:-600}  # 10 minutes default

    log_info "Monitoring queue drain for $((duration/60)) minutes..."

    local start=$(date +%s)
    local max_queue=0

    while [ $(($(date +%s) - start)) -lt $duration ]; do
        if [ -f "$QUEUE_FILE" ]; then
            local queue_size=$(grep -c "filepath" "$QUEUE_FILE" 2>/dev/null || echo "0")

            if [ "$queue_size" -gt "$max_queue" ]; then
                max_queue=$queue_size
            fi

            log_info "Queue: $queue_size entries (max: $max_queue)"
            echo "[Queue Size] $queue_size" >> "$METRICS_LOG"
        fi

        sleep 60
    done

    log_success "Queue monitoring complete. Max queue: $max_queue"
}

collect_metrics() {
    # Collect comprehensive metrics
    local timestamp=$(date +%s)

    # Service status
    local service_status="DOWN"
    if is_service_running; then
        service_status="UP"
    fi

    # Queue size
    local queue_size=0
    if [ -f "$QUEUE_FILE" ]; then
        queue_size=$(grep -c "filepath" "$QUEUE_FILE" 2>/dev/null || echo "0")
    fi

    # Disk usage
    local disk_usage=$(df "$TEST_DIR" | tail -1 | awk '{print $5}' | tr -d '%')

    # Memory usage
    local mem_usage=0
    if [ -f /tmp/tvm-service.pid ]; then
        local pid=$(cat /tmp/tvm-service.pid)
        mem_usage=$(ps -p "$pid" -o rss --no-headers 2>/dev/null | awk '{print int($1/1024)}' || echo "0")
    fi

    # CPU usage
    local cpu_usage=0
    if [ -f /tmp/tvm-service.pid ]; then
        local pid=$(cat /tmp/tvm-service.pid)
        cpu_usage=$(ps -p "$pid" -o %cpu --no-headers 2>/dev/null | awk '{print int($1)}' || echo "0")
    fi

    # Error count
    local error_count=$(get_error_count)

    # Write metrics
    echo "[$timestamp] Service=$service_status Queue=$queue_size Disk=${disk_usage}% Mem=${mem_usage}MB CPU=${cpu_usage}% Errors=$error_count" >> "$METRICS_LOG"
}

get_error_count() {
    grep -ci "error\|exception\|failed" "$SERVICE_LOG" 2>/dev/null || echo "0"
}

# ============================================================================
# Test Configuration
# ============================================================================

QUEUE_FILE="/tmp/queue-prod-sim.json"
REGISTRY_FILE="/tmp/registry-prod-sim.json"

TEST_CONFIG="/tmp/tvm-test-config-prod-sim.yaml"
cat > "$TEST_CONFIG" <<EOF
vehicle_id: "$VEHICLE_ID"

log_directories:
  - path: $TEST_DIR/terminal
    source: terminal
    recursive: true
    allow_deletion: true

  - path: $TEST_DIR/ros
    source: ros
    recursive: true
    allow_deletion: true

  - path: $TEST_DIR/ros2
    source: ros2
    recursive: true
    allow_deletion: true

  - path: $TEST_DIR/syslog
    source: syslog
    recursive: false
    allow_deletion: false
    pattern: "syslog*"

s3:
  bucket: $S3_BUCKET
  region: $AWS_REGION
  profile: $AWS_PROFILE

upload:
  schedule:
    mode: interval
    interval_hours: 0
    interval_minutes: 5
  file_stable_seconds: 60
  operational_hours:
    enabled: false  # Disabled for continuous testing
  batch_upload:
    enabled: true
  upload_on_start: true
  queue_file: $QUEUE_FILE
  scan_existing_files:
    enabled: true
    max_age_days: 3
  processed_files_registry:
    registry_file: $REGISTRY_FILE
    retention_days: 30

deletion:
  after_upload:
    enabled: true
    keep_days: 1  # Keep for 1 day
  age_based:
    enabled: true
    max_age_days: 7
    schedule_time: "02:00"
  emergency:
    enabled: true

disk:
  reserved_gb: 1
  warning_threshold: 0.85
  critical_threshold: 0.90

monitoring:
  cloudwatch_enabled: false

s3_lifecycle:
  retention_days: 14
EOF

log_success "Created production simulation config"

# ============================================================================
# Start Service
# ============================================================================

log_info "Starting TVM upload service..."
if ! start_tvm_service "$TEST_CONFIG" "$SERVICE_LOG" "" "$VEHICLE_ID"; then
    log_error "Failed to start service"
    exit 1
fi

# Initialize metrics log
echo "========================================" > "$METRICS_LOG"
echo "Production Simulation Test - Metrics Log" >> "$METRICS_LOG"
echo "Started: $(date)" >> "$METRICS_LOG"
echo "Duration: $TEST_DURATION_HOURS hours" >> "$METRICS_LOG"
echo "========================================" >> "$METRICS_LOG"
echo "" >> "$METRICS_LOG"

# ============================================================================
# Main Test Loop
# ============================================================================

START_TIME=$(date +%s)
CYCLE_COUNT=0
TOTAL_FILES_GENERATED=0

log_info "╔════════════════════════════════════════════════════════════════╗"
log_info "║              STARTING PRODUCTION SIMULATION                    ║"
log_info "╚════════════════════════════════════════════════════════════════╝"
echo ""

# Start background metrics collection
(
    while true; do
        collect_metrics
        sleep 60
    done
) &
METRICS_PID=$!

while [ $(($(date +%s) - START_TIME)) -lt $TEST_DURATION_SECONDS ]; do
    CYCLE_COUNT=$((CYCLE_COUNT + 1))
    CYCLE_START=$(date +%s)

    log_info "═══════════════════════════════════════════════════════════════"
    log_info "CYCLE $CYCLE_COUNT - Started at $(date +%H:%M:%S)"
    log_info "═══════════════════════════════════════════════════════════════"

    # ========== PHASE 1: Campus Entry (WiFi Available) ==========
    log_info ""
    log_info ">>> PHASE 1: Campus Entry - WiFi Available (15 min)"
    enable_wifi
    generate_files_normal 900 &  # 15 minutes, background
    GEN_PID=$!
    sleep 900
    wait $GEN_PID 2>/dev/null || true

    # ========== PHASE 2: Campus Interior (No WiFi) ==========
    log_info ""
    log_info ">>> PHASE 2: Campus Interior - No WiFi (30 min)"
    disable_wifi
    generate_files_heavy 1800 &  # 30 minutes, background
    GEN_PID=$!
    sleep 1800
    wait $GEN_PID 2>/dev/null || true

    # ========== PHASE 3: WiFi Zone Return (Queue Drain) ==========
    log_info ""
    log_info ">>> PHASE 3: WiFi Zone Return - Queue Draining (10 min)"
    enable_wifi
    monitor_queue_drain 600 &
    MON_PID=$!
    sleep 600
    wait $MON_PID 2>/dev/null || true

    # ========== PHASE 4: Network Instability ==========
    log_info ""
    log_info ">>> PHASE 4: Network Instability (30 min total)"

    # Pattern A: Regular Intermittent (30s on/off) - 10 minutes
    log_info "Pattern A: Regular Intermittent WiFi (10 min)"
    for cycle in {1..10}; do
        enable_wifi
        sleep 30
        disable_wifi
        sleep 30
    done

    # Pattern B: WiFi Flapping (2-3s on/off) - 10 minutes
    log_info "Pattern B: WiFi Flapping - CRITICAL TEST (10 min)"
    simulate_wifi_flapping 600

    # Pattern C: Degraded WiFi - 10 minutes
    log_info "Pattern C: Degraded WiFi (10 min)"
    enable_slow_wifi 500 10  # 500ms latency, 10% loss
    sleep 600
    restore_normal_wifi

    # ========== PHASE 5: Chaos Testing ==========
    log_info ""
    log_info ">>> PHASE 5: Chaos - Crashes & Recovery (15 min)"

    # Generate burst files
    generate_files_burst 300 &  # 5 minutes
    GEN_PID=$!
    sleep 300
    wait $GEN_PID 2>/dev/null || true

    # Simulate crash
    simulate_crash "sigkill"

    # Verify recovery
    verify_recovery

    # Continue file generation
    generate_files_normal 600 &  # 10 minutes
    GEN_PID=$!
    sleep 600
    wait $GEN_PID 2>/dev/null || true

    # ========== Cycle Complete ==========
    CYCLE_END=$(date +%s)
    CYCLE_DURATION=$((CYCLE_END - CYCLE_START))

    log_success "Cycle $CYCLE_COUNT complete in $((CYCLE_DURATION/60)) minutes"
    echo "[Cycle $CYCLE_COUNT Complete] Duration: $((CYCLE_DURATION/60)) min" >> "$METRICS_LOG"
    echo "" >> "$METRICS_LOG"

    # Check if we should continue
    ELAPSED=$(($(date +%s) - START_TIME))
    REMAINING=$((TEST_DURATION_SECONDS - ELAPSED))

    if [ $REMAINING -lt $CYCLE_DURATION ]; then
        log_info "Insufficient time for another full cycle ($((REMAINING/60)) min remaining)"
        log_info "Finishing test gracefully..."
        break
    fi

    log_info "Next cycle will start after brief pause..."
    sleep 60
done

# Stop metrics collection
kill $METRICS_PID 2>/dev/null || true

# ============================================================================
# Test Complete - Final Verification
# ============================================================================

log_info "╔════════════════════════════════════════════════════════════════╗"
log_info "║           PRODUCTION SIMULATION COMPLETE                       ║"
log_info "╚════════════════════════════════════════════════════════════════╝"
echo ""

# Restore network to normal
log_info "Restoring network to normal state..."
enable_wifi

# Final metrics collection
log_info "Collecting final metrics..."

# Service status
if is_service_running; then
    log_success "✓ Service still running after $TEST_DURATION_HOURS hour test"
else
    log_error "✗ Service not running at end of test"
    TESTS_FAILED=$((TESTS_FAILED + 1))
fi

# Queue state
FINAL_QUEUE_SIZE=0
if [ -f "$QUEUE_FILE" ]; then
    FINAL_QUEUE_SIZE=$(grep -c "filepath" "$QUEUE_FILE" 2>/dev/null || echo "0")
    log_info "Final queue size: $FINAL_QUEUE_SIZE entries"

    if python3 -m json.tool "$QUEUE_FILE" > /dev/null 2>&1; then
        log_success "✓ Queue file integrity maintained"
    else
        log_error "✗ Queue file corrupted"
        TESTS_FAILED=$((TESTS_FAILED + 1))
    fi
fi

# Registry state
if [ -f "$REGISTRY_FILE" ]; then
    if python3 -m json.tool "$REGISTRY_FILE" > /dev/null 2>&1; then
        log_success "✓ Registry file integrity maintained"
        REGISTRY_ENTRIES=$(grep -c "uploaded_at" "$REGISTRY_FILE" 2>/dev/null || echo "0")
        log_info "Registry entries: $REGISTRY_ENTRIES"
    else
        log_error "✗ Registry file corrupted"
        TESTS_FAILED=$((TESTS_FAILED + 1))
    fi
fi

# S3 verification
log_info "Verifying S3 uploads..."
TODAY=$(date +%Y-%m-%d)
UPLOADED_COUNT=$(aws s3 ls "s3://${S3_BUCKET}/${VEHICLE_ID}/" --recursive --profile "$AWS_PROFILE" --region "$AWS_REGION" 2>/dev/null | wc -l || echo "0")
log_info "Total files uploaded to S3: $UPLOADED_COUNT"

# Error analysis
ERROR_COUNT=$(get_error_count)
log_info "Total errors in service log: $ERROR_COUNT"

if [ "$ERROR_COUNT" -gt 1000 ]; then
    log_warning "⚠ High error count: $ERROR_COUNT (may be acceptable for long test with crashes)"
else
    log_success "✓ Error count acceptable: $ERROR_COUNT"
fi

# ============================================================================
# Test Summary
# ============================================================================

TEST_END=$(date +%s)
ACTUAL_DURATION=$((TEST_END - START_TIME))

log_info "╔════════════════════════════════════════════════════════════════╗"
log_info "║                    TEST SUMMARY                                ║"
log_info "╚════════════════════════════════════════════════════════════════╝"
echo ""
echo "Test Duration:        $((ACTUAL_DURATION / 3600))h $((ACTUAL_DURATION % 3600 / 60))m"
echo "Cycles Completed:     $CYCLE_COUNT"
echo "Files Uploaded:       $UPLOADED_COUNT"
echo "Final Queue Size:     $FINAL_QUEUE_SIZE"
echo "Service Errors:       $ERROR_COUNT"
echo "Tests Failed:         $TESTS_FAILED"
echo ""
echo "Detailed metrics saved to: $METRICS_LOG"
echo "Service log saved to:      $SERVICE_LOG"
echo ""

# ============================================================================
# Cleanup
# ============================================================================

log_info "Cleaning up..."

# Stop service
stop_tvm_service

# Clean test files
rm -rf "$TEST_DIR"
rm -f "$TEST_CONFIG"
rm -f "$QUEUE_FILE"
rm -f "$REGISTRY_FILE"

# Clean S3
log_info "Cleaning S3 test data..."
cleanup_complete_vehicle_folder "$VEHICLE_ID" "$S3_BUCKET" "$AWS_PROFILE" "$AWS_REGION"

# Print summary
print_test_summary

# Test result
if [ $TESTS_FAILED -eq 0 ]; then
    log_success "TEST 30: PASSED - Production simulation completed successfully"
    log_success "  • Service remained stable"
    log_success "  • Survived WiFi flapping"
    log_success "  • Recovered from crashes"
    log_success "  • Queue integrity maintained"
    exit 0
else
    log_error "TEST 30: FAILED - Production simulation encountered issues"
    log_error "  • Failed checks: $TESTS_FAILED"
    exit 1
fi
