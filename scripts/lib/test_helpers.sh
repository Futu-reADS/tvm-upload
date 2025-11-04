#!/bin/bash
# Common helper functions for manual testing automation

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Test result tracking
TESTS_PASSED=0
TESTS_FAILED=0
TESTS_SKIPPED=0

# Safety: Production vehicle IDs that should NEVER be auto-cleaned
PRODUCTION_VEHICLE_IDS=(
    "vehicle-CN-001"
    "vehicle-CN-002"
    "vehicle-JP-001"
    # Add more production IDs here
)

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[✓]${NC} $1"
    TESTS_PASSED=$((TESTS_PASSED + 1))
}

log_error() {
    echo -e "${RED}[✗]${NC} $1"
    TESTS_FAILED=$((TESTS_FAILED + 1))
}

log_warning() {
    echo -e "${YELLOW}[⚠]${NC} $1"
}

log_skip() {
    echo -e "${YELLOW}[SKIP]${NC} $1"
    TESTS_SKIPPED=$((TESTS_SKIPPED + 1))
}

# Print test header
print_test_header() {
    local test_name=$1
    local test_num=$2
    echo ""
    echo "================================================================"
    echo "TEST ${test_num}: ${test_name}"
    echo "================================================================"
}

# Print test summary with color-coded borders
print_test_summary() {
    local total=$((TESTS_PASSED + TESTS_FAILED + TESTS_SKIPPED))
    local summary_color="${NC}"
    local status_icon=""
    local status_text=""

    # Determine color based on test results
    if [ $TESTS_FAILED -gt 0 ]; then
        # Red if any failures
        summary_color="${RED}"
        status_icon="✗"
        status_text="FAILED"
    elif [ $TESTS_SKIPPED -gt 0 ]; then
        # Yellow if warnings/skipped but no failures
        summary_color="${YELLOW}"
        status_icon="⚠"
        status_text="WARNING"
    else
        # Green if all passed
        summary_color="${GREEN}"
        status_icon="✓"
        status_text="PASSED"
    fi

    echo ""
    echo -e "${summary_color}================================================================${NC}"
    echo -e "${summary_color}TEST SUMMARY${NC} [${summary_color}${status_icon} ${status_text}${NC}]"
    echo -e "${summary_color}================================================================${NC}"
    echo -e "Passed:  ${GREEN}${TESTS_PASSED}${NC}"
    echo -e "Failed:  ${RED}${TESTS_FAILED}${NC}"
    echo -e "Skipped: ${YELLOW}${TESTS_SKIPPED}${NC}"
    echo "Total:   ${total}"
    echo -e "${summary_color}================================================================${NC}"
}

# Wait with progress indicator
wait_with_progress() {
    local duration=$1
    local message=${2:-"Waiting"}

    log_info "$message for ${duration} seconds..."
    for ((i=duration; i>0; i--)); do
        printf "\r${BLUE}[⏳]${NC} Time remaining: ${i}s  "
        sleep 1
    done
    printf "\r${GREEN}[✓]${NC} Wait complete!           \n"
}

# Create test directory
create_test_dir() {
    local base_dir=${1:-/tmp/tvm-manual-test}

    if [ -d "$base_dir" ]; then
        log_info "Cleaning existing test directory..."
        rm -rf "$base_dir"
    fi

    mkdir -p "$base_dir"/{terminal,ros,syslog,other}
    log_success "Test directory created: $base_dir"
    echo "$base_dir"
}

# Generate test file with content
generate_test_file() {
    local filepath=$1
    local size_kb=${2:-1}
    local content=${3:-"Test data"}

    mkdir -p "$(dirname "$filepath")"

    if [ "$size_kb" -eq 0 ]; then
        # Empty file
        touch "$filepath"
    elif [ "$size_kb" -lt 10 ]; then
        # Small text file
        for ((i=0; i<size_kb*10; i++)); do
            echo "$content line $i $(date +%s)" >> "$filepath"
        done
    else
        # Binary file for larger sizes
        dd if=/dev/urandom of="$filepath" bs=1024 count="$size_kb" 2>/dev/null
    fi

    log_success "Created file: $filepath (${size_kb}KB)"
}

# Set file modification time
set_file_mtime() {
    local filepath=$1
    local days_ago=$2

    local timestamp=$(date -d "$days_ago days ago" +%Y%m%d0000)
    touch -t "$timestamp" "$filepath" 2>/dev/null

    if [ $? -eq 0 ]; then
        log_success "Set mtime to $days_ago days ago: $filepath"
    else
        log_error "Failed to set mtime: $filepath"
    fi
}

# Check if file exists
assert_file_exists() {
    local filepath=$1
    local message=${2:-"File should exist"}

    if [ -f "$filepath" ]; then
        log_success "$message: $filepath"
        return 0
    else
        log_error "$message: $filepath (NOT FOUND)"
        return 1
    fi
}

# Check if file does NOT exist
assert_file_not_exists() {
    local filepath=$1
    local message=${2:-"File should not exist"}

    if [ ! -f "$filepath" ]; then
        log_success "$message: $filepath"
        return 0
    else
        log_error "$message: $filepath (STILL EXISTS)"
        return 1
    fi
}

# Compare strings
assert_equals() {
    local expected=$1
    local actual=$2
    local message=${3:-"Values should match"}

    if [ "$expected" == "$actual" ]; then
        log_success "$message"
        return 0
    else
        log_error "$message (Expected: '$expected', Got: '$actual')"
        return 1
    fi
}

# Check if string contains substring
assert_contains() {
    local haystack=$1
    local needle=$2
    local message=${3:-"String should contain"}

    if [[ "$haystack" == *"$needle"* ]]; then
        log_success "$message: '$needle'"
        return 0
    else
        log_error "$message: '$needle' (Not found in: '$haystack')"
        return 1
    fi
}

# Assert greater than
assert_greater_than() {
    local value=$1
    local threshold=$2
    local message=${3:-"Value should be greater than threshold"}

    if [ "$value" -gt "$threshold" ]; then
        log_success "$message ($value > $threshold)"
        return 0
    else
        log_error "$message ($value <= $threshold)"
        return 1
    fi
}

# Load configuration
load_config() {
    local config_file=${1:-config/config.yaml}

    if [ ! -f "$config_file" ]; then
        log_error "Config file not found: $config_file"
        return 1
    fi

    # Export config values (simplified - assumes YAML format)
    export VEHICLE_ID=$(grep "^vehicle_id:" "$config_file" | awk '{print $2}' | tr -d '"')
    export S3_BUCKET=$(grep "bucket:" "$config_file" | head -1 | awk '{print $2}' | tr -d '"')
    export AWS_REGION=$(grep "region:" "$config_file" | head -1 | awk '{print $2}' | tr -d '"')
    export AWS_PROFILE=$(grep "profile:" "$config_file" | head -1 | awk '{print $2}' | tr -d '"')

    log_info "Configuration loaded:"
    log_info "  Vehicle ID: $VEHICLE_ID"
    log_info "  S3 Bucket: $S3_BUCKET"
    log_info "  AWS Region: $AWS_REGION"
    log_info "  AWS Profile: $AWS_PROFILE"
}

# Start TVM service in background
start_tvm_service() {
    local config_file=${1:-config/config.yaml}
    local log_file=${2:-/tmp/tvm-service.log}
    local test_dir=${3:-}  # Optional: if provided, creates test config
    local test_vehicle_id=${4:-}  # Optional: override vehicle_id for testing

    log_info "Starting TVM upload service..."

    # Kill existing process if running (using killall instead of pkill to avoid hang)
    killall -9 python3 2>/dev/null || true
    sleep 2

    # Find project root (where src/ directory is located)
    if [ -d "src" ]; then
        PROJECT_ROOT="$(pwd)"
    elif [ -d "../src" ]; then
        PROJECT_ROOT="$(cd .. && pwd)"
    elif [ -d "../../src" ]; then
        PROJECT_ROOT="$(cd ../.. && pwd)"
    else
        log_error "Cannot find project root (src/ directory not found)"
        return 1
    fi

    # Create test config if test_dir provided
    local actual_config="$config_file"
    if [ -n "$test_dir" ]; then
        actual_config="/tmp/tvm-test-config.yaml"

        # Create test config by replacing log_directories section using Python
        python3 - "$config_file" "$actual_config" "$test_dir" <<'EOPY'
import re
import sys

config_file = sys.argv[1]
output_file = sys.argv[2]
test_dir = sys.argv[3]

with open(config_file, 'r') as f:
    content = f.read()

# Replace log_directories section with test directories
# Match from "log_directories:" to the next section divider (comment line starting with # =)
# This preserves everything else including s3:, upload:, etc.
pattern = r'(log_directories:).*?(?=\n# =+)'
replacement = f'''log_directories:
  - path: {test_dir}/terminal
    source: terminal
  - path: {test_dir}/ros
    source: ros
  - path: {test_dir}/syslog
    source: syslog
  - path: {test_dir}/other
    source: other

'''

new_content = re.sub(pattern, replacement, content, flags=re.DOTALL | re.MULTILINE)

with open(output_file, 'w') as f:
    f.write(new_content)
EOPY

        log_info "Created test config monitoring: $test_dir"
    fi

    # Override queue/registry paths when test_dir is provided (safety: avoid production contamination)
    if [ -n "$test_dir" ]; then
        # Generate unique test identifier from test_dir or vehicle_id
        local test_id=$(basename "$test_dir" | tr '/' '-')
        if [ -n "$test_vehicle_id" ]; then
            test_id=$(echo "$test_vehicle_id" | sed 's/[^a-zA-Z0-9-]/-/g')
        fi

        # Use test-specific queue and registry files
        local test_queue="/tmp/queue-${test_id}.json"
        local test_registry="/tmp/registry-${test_id}.json"

        sed -i "s|queue_file:.*|queue_file: $test_queue|" "$actual_config"
        sed -i "s|registry_file:.*|registry_file: $test_registry|" "$actual_config"

        log_info "Using test-specific state files:"
        log_info "  Queue: $test_queue"
        log_info "  Registry: $test_registry"
    fi

    # Override vehicle_id if test_vehicle_id provided
    if [ -n "$test_vehicle_id" ]; then
        # Create temp config if not already created
        if [ "$actual_config" = "$config_file" ]; then
            actual_config="/tmp/tvm-test-config.yaml"
            cp "$config_file" "$actual_config"
        fi

        # Replace vehicle_id in config
        sed -i "s/^vehicle_id:.*/vehicle_id: \"$test_vehicle_id\"/" "$actual_config"
        log_info "Overriding vehicle_id in config: $test_vehicle_id"
    fi

    # Start service from project root
    cd "$PROJECT_ROOT" || exit 1
    python3 -m src.main --config "$actual_config" > "$log_file" 2>&1 &

    local pid=$!
    echo "$pid" > /tmp/tvm-service.pid

    sleep 3

    if ps -p "$pid" > /dev/null 2>&1; then
        log_success "TVM service started (PID: $pid)"
        return 0
    else
        log_error "Failed to start TVM service"
        cat "$log_file"
        return 1
    fi
}

# Stop TVM service
stop_tvm_service() {
    log_info "Stopping TVM service..."

    if [ -f /tmp/tvm-service.pid ]; then
        local pid=$(cat /tmp/tvm-service.pid)
        kill "$pid" 2>/dev/null || true
        sleep 2

        if ! ps -p "$pid" > /dev/null 2>&1; then
            log_success "TVM service stopped"
        else
            kill -9 "$pid" 2>/dev/null || true
            log_warning "TVM service force killed"
        fi

        rm -f /tmp/tvm-service.pid
    else
        pkill -f "python.*src.main" 2>/dev/null || true
        log_info "TVM service stopped (no PID file)"
    fi
}

# Get service logs
get_service_logs() {
    local log_file=${1:-/tmp/tvm-service.log}
    local lines=${2:-50}

    if [ -f "$log_file" ]; then
        tail -n "$lines" "$log_file"
    else
        log_warning "Log file not found: $log_file"
    fi
}

# Check service health
check_service_health() {
    if [ -f /tmp/tvm-service.pid ]; then
        local pid=$(cat /tmp/tvm-service.pid)
        if ps -p "$pid" > /dev/null 2>&1; then
            log_success "Service is running (PID: $pid)"
            return 0
        fi
    fi

    log_error "Service is not running"
    return 1
}

# Check if service is running (silent - no logging, no test counter increment)
is_service_running() {
    if [ -f /tmp/tvm-service.pid ]; then
        local pid=$(cat /tmp/tvm-service.pid)
        if ps -p "$pid" > /dev/null 2>&1; then
            return 0  # Running
        fi
    fi
    return 1  # Not running
}

# Cleanup test environment
cleanup_test_env() {
    local test_dir=${1:-/tmp/tvm-manual-test}

    log_info "Cleaning up test environment..."

    # Stop service
    stop_tvm_service

    # Remove test directories
    if [ -d "$test_dir" ]; then
        rm -rf "$test_dir"
        log_success "Removed test directory: $test_dir"
    fi

    # Remove temp files (including root-owned files from previous sudo runs)
    rm -f /tmp/tvm-service.log 2>/dev/null || true
    rm -f /tmp/tvm-service.pid 2>/dev/null || true
    rm -f /tmp/test-*.log 2>/dev/null || true

    # Try to remove test config files; if root-owned, try with sudo
    if ! rm -f /tmp/tvm-test-config*.yaml 2>/dev/null; then
        # Check if any root-owned test configs exist
        if ls -l /tmp/tvm-test-config*.yaml 2>/dev/null | grep -q "^-.*root"; then
            log_warning "Found root-owned test configs, attempting sudo cleanup..."
            sudo rm -f /tmp/tvm-test-config*.yaml 2>/dev/null || log_warning "Could not remove root-owned configs"
        fi
    fi

    # Clean up persistent state files to avoid cross-test contamination
    # These files accumulate processed/uploaded file tracking across test runs
    if [ -d "/var/lib/tvm-upload" ]; then
        rm -f /var/lib/tvm-upload/queue.json 2>/dev/null || true
        rm -f /var/lib/tvm-upload/queue.json.bak 2>/dev/null || true
        rm -f /var/lib/tvm-upload/processed_files.json 2>/dev/null || true
    fi

    # Clean up test-specific state files (used by Tests 13, 14, 15, 16)
    rm -f /tmp/queue-*.json 2>/dev/null || true
    rm -f /tmp/registry-*.json 2>/dev/null || true

    log_success "Cleanup complete"
}

# Save test results to file
save_test_result() {
    local test_name=$1
    local result=$2
    local duration=$3
    local notes=${4:-""}

    local result_file="/tmp/manual-test-results.txt"

    if [ ! -f "$result_file" ]; then
        echo "# TVM Manual Test Results - $(date)" > "$result_file"
        echo "# ======================================" >> "$result_file"
        echo "" >> "$result_file"
    fi

    echo "Test: $test_name" >> "$result_file"
    echo "Result: $result" >> "$result_file"
    echo "Duration: ${duration}s" >> "$result_file"
    if [ -n "$notes" ]; then
        echo "Notes: $notes" >> "$result_file"
    fi
    echo "" >> "$result_file"
}

# Safe S3 cleanup with production protection
cleanup_test_s3_data() {
    local vehicle_id=$1
    local s3_bucket=$2
    local aws_profile=$3
    local aws_region=$4
    local date_filter=${5:-$(date +%Y-%m-%d)}  # Default to today

    # SAFETY CHECK: Prevent cleaning production vehicle IDs
    for prod_id in "${PRODUCTION_VEHICLE_IDS[@]}"; do
        if [ "$vehicle_id" = "$prod_id" ]; then
            log_error "SAFETY BLOCK: Cannot auto-clean production vehicle ID: $vehicle_id"
            log_warning "To clean manually, run:"
            log_warning "  aws s3 rm s3://${s3_bucket}/${vehicle_id}/${date_filter}/ --recursive --profile ${aws_profile} --region ${aws_region}"
            return 1
        fi
    done

    # Only clean test vehicle IDs (must contain "TEST" or "test")
    if [[ ! "$vehicle_id" =~ (TEST|test) ]]; then
        log_warning "Vehicle ID doesn't contain 'TEST': $vehicle_id"
        log_warning "For safety, only test vehicle IDs can be auto-cleaned"
        log_info "Add 'TEST' to vehicle ID or clean manually"
        return 1
    fi

    # Safe to clean test data
    local s3_path="s3://${s3_bucket}/${vehicle_id}/${date_filter}/"
    log_info "Cleaning test data: $s3_path"

    if aws s3 rm "$s3_path" --recursive --profile "$aws_profile" --region "$aws_region" 2>/dev/null; then
        log_success "Cleaned test data from S3"
    else
        log_warning "No test data found to clean (or AWS error)"
    fi
}

# Generate test-specific vehicle ID
generate_test_vehicle_id() {
    local base_name=${1:-"vehicle-TEST"}
    local timestamp=$(date +%s)
    echo "${base_name}-${timestamp}"
}

# Complete vehicle folder cleanup (all dates) - for end of test suite
# Deletes the EXACT vehicle ID folder that was created for this test run
cleanup_complete_vehicle_folder() {
    local vehicle_id=$1
    local s3_bucket=$2
    local aws_profile=$3
    local aws_region=$4

    # Simple check: just verify vehicle_id is not empty
    if [ -z "$vehicle_id" ]; then
        log_error "Vehicle ID is empty, cannot clean"
        return 1
    fi

    # Clean the EXACT vehicle folder (e.g., s3://bucket/vehicle-TEST-MANUAL-1730123456/)
    local s3_path="s3://${s3_bucket}/${vehicle_id}/"
    log_info "Cleaning test vehicle folder: $s3_path"

    if aws s3 rm "$s3_path" --recursive --profile "$aws_profile" --region "$aws_region" 2>/dev/null; then
        log_success "Cleaned vehicle folder from S3: ${vehicle_id}/"
    else
        log_warning "No vehicle data found to clean (or AWS error)"
    fi
}

# Export functions
export -f log_info log_success log_error log_warning log_skip
export -f print_test_header print_test_summary
export -f wait_with_progress create_test_dir generate_test_file set_file_mtime
export -f cleanup_test_s3_data cleanup_complete_vehicle_folder generate_test_vehicle_id
export -f assert_file_exists assert_file_not_exists assert_equals assert_contains assert_greater_than
export -f load_config start_tvm_service stop_tvm_service get_service_logs check_service_health
export -f cleanup_test_env save_test_result
