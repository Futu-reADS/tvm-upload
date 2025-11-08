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

    # FIX P0-6: Safe process cleanup - only kill TVM service, not all python3 processes
    # This prevents killing IDE processes, user scripts, and other Python applications
    log_info "Ensuring no previous TVM service is running..."

    # Method 1: Check PID file and kill that specific process
    if [ -f /tmp/tvm-service.pid ]; then
        OLD_PID=$(cat /tmp/tvm-service.pid 2>/dev/null)
        if [ -n "$OLD_PID" ] && ps -p "$OLD_PID" > /dev/null 2>&1; then
            # Verify it's actually a TVM process before killing
            if ps -p "$OLD_PID" -o cmd= 2>/dev/null | grep -q "src.main\|tvm"; then
                log_info "Found previous TVM service (PID: $OLD_PID), stopping it..."
                kill "$OLD_PID" 2>/dev/null || true
                sleep 2
                # Force kill if still running
                if ps -p "$OLD_PID" > /dev/null 2>&1; then
                    kill -9 "$OLD_PID" 2>/dev/null || true
                    sleep 1
                fi
            fi
        fi
        rm -f /tmp/tvm-service.pid
    fi

    # Method 2: Find TVM processes by exact command pattern and kill only those
    # Use pkill with exact pattern match to avoid killing other Python processes
    pkill -f "python.*src.main" 2>/dev/null || true
    sleep 1

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
# DEPRECATED: cleanup_test_s3_data()
# This function only cleans a single date folder, which is insufficient for tests
# that create data across multiple dates (like Test 15: Startup Scan).
#
# RECOMMENDED: Use cleanup_complete_vehicle_folder() instead, which:
# - Cleans entire vehicle folder (all dates)
# - Has triple safety checks (empty ID, production protection, TEST pattern validation)
# - Provides better logging and verification
# - Is the standard used by the master test runner's batch cleanup
#
# This function is kept for backward compatibility only.
cleanup_test_s3_data() {
    local vehicle_id=$1
    local s3_bucket=$2
    local aws_profile=$3
    local aws_region=$4
    local date_filter=${5:-$(date +%Y-%m-%d)}  # Default to today

    # DEPRECATION WARNING
    log_warning "⚠️  DEPRECATION: cleanup_test_s3_data() is deprecated"
    log_warning "   Use cleanup_complete_vehicle_folder() instead for complete cleanup"
    log_warning "   This function only cleans one date folder: $date_filter"
    echo ""

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
# Features: Triple safety checks to prevent accidental production data deletion
cleanup_complete_vehicle_folder() {
    local vehicle_id=$1
    local s3_bucket=$2
    local aws_profile=$3
    local aws_region=$4

    # ========================================================================
    # SAFETY CHECK 1: Vehicle ID not empty
    # ========================================================================
    if [ -z "$vehicle_id" ]; then
        log_error "SAFETY BLOCK: Vehicle ID is empty, cannot clean"
        return 1
    fi

    # ========================================================================
    # SAFETY CHECK 2: Production vehicle ID protection
    # ========================================================================
    for prod_id in "${PRODUCTION_VEHICLE_IDS[@]}"; do
        if [[ "$vehicle_id" == "$prod_id"* ]]; then
            log_error "SAFETY BLOCK: Cannot auto-clean production vehicle ID: $vehicle_id"
            log_warning "This matches production vehicle ID pattern: $prod_id"
            log_warning "To clean manually, run:"
            log_warning "  aws s3 rm s3://${s3_bucket}/${vehicle_id}/ --recursive --profile ${aws_profile} --region ${aws_region}"
            return 1
        fi
    done

    # ========================================================================
    # SAFETY CHECK 3: Vehicle ID must contain "TEST"
    # ========================================================================
    if [[ ! "$vehicle_id" =~ TEST ]]; then
        log_error "SAFETY BLOCK: Vehicle ID does not contain 'TEST': $vehicle_id"
        log_warning "This doesn't look like a test vehicle ID. Refusing to delete."
        log_warning "Test vehicle IDs should follow pattern: vehicle-TEST-*"
        return 1
    fi

    # ========================================================================
    # All safety checks passed - proceed with cleanup
    # ========================================================================
    local s3_path="s3://${s3_bucket}/${vehicle_id}/"

    # Check if folder exists before attempting deletion
    if aws s3 ls "$s3_path" --profile "$aws_profile" --region "$aws_region" &>/dev/null; then
        local file_count=$(aws s3 ls "$s3_path" --recursive --profile "$aws_profile" --region "$aws_region" 2>/dev/null | wc -l)

        # Perform deletion
        if aws s3 rm "$s3_path" --recursive --profile "$aws_profile" --region "$aws_region" 2>/dev/null; then
            log_success "Cleaned vehicle folder from S3: ${vehicle_id}/ ($file_count files)"
            return 0
        else
            log_error "Failed to clean vehicle folder (AWS error): ${vehicle_id}/"
            return 1
        fi
    else
        # No data found - this is OK (test may not have uploaded anything)
        log_info "No S3 data found for: ${vehicle_id}/ (test may not have uploaded files)"
        return 0
    fi
}

# Cleanup all test folders matching a pattern (pre-flight cleanup)
# Finds and removes all old test data from S3 for a specific vehicle pattern
# Used to clean up leftover data from interrupted test runs
cleanup_all_test_folders() {
    local vehicle_pattern=$1  # e.g., "vehicle-TEST-CN-001-MANUAL"
    local s3_bucket=$2
    local aws_profile=$3
    local aws_region=$4
    local dry_run=${5:-false}  # Optional: set to 'true' for preview only

    # ========================================================================
    # SAFETY CHECK 1: Pattern must contain "TEST"
    # ========================================================================
    if [[ ! "$vehicle_pattern" =~ TEST ]]; then
        log_error "SAFETY BLOCK: Pattern does not contain 'TEST': $vehicle_pattern"
        log_warning "Refusing to search for non-test vehicles"
        return 1
    fi

    # ========================================================================
    # SAFETY CHECK 2: Production vehicle ID protection
    # ========================================================================
    for prod_id in "${PRODUCTION_VEHICLE_IDS[@]}"; do
        if [[ "$vehicle_pattern" == "$prod_id"* ]]; then
            log_error "SAFETY BLOCK: Pattern matches production vehicle ID: $vehicle_pattern"
            return 1
        fi
    done

    log_info "Searching for test folders matching pattern: ${vehicle_pattern}*"

    # Build AWS command
    if [ -n "$aws_profile" ]; then
        AWS_CMD="aws --profile $aws_profile --region $aws_region"
    else
        AWS_CMD="aws --region $aws_region"
    fi

    # List all folders in bucket and filter for matching pattern
    local matching_folders=$($AWS_CMD s3 ls "s3://${s3_bucket}/" 2>/dev/null | \
        grep "PRE ${vehicle_pattern}" | \
        awk '{print $2}' | \
        sed 's|/$||' || true)

    if [ -z "$matching_folders" ]; then
        log_info "No matching test folders found"
        return 0
    fi

    # Count folders
    local folder_count=$(echo "$matching_folders" | wc -l)
    log_info "Found $folder_count test folder(s) to clean:"
    echo ""

    # Display folders with file counts
    local total_files=0
    while IFS= read -r folder; do
        local file_count=$($AWS_CMD s3 ls "s3://${s3_bucket}/${folder}/" --recursive 2>/dev/null | wc -l || echo "0")
        total_files=$((total_files + file_count))
        echo "  - $folder ($file_count files)"
    done <<< "$matching_folders"

    echo ""
    log_info "Total: $folder_count folders, $total_files files"

    if [ "$dry_run" = "true" ]; then
        log_warning "DRY RUN MODE - No deletions performed"
        return 0
    fi

    # Confirm deletion (only if interactive)
    if [ -t 0 ]; then
        echo ""
        read -p "Delete these test folders? (y/N): " confirm
        if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
            log_info "Cleanup cancelled by user"
            return 0
        fi
    fi

    echo ""
    log_info "Cleaning up test folders..."

    # Delete each folder
    local success_count=0
    local fail_count=0

    while IFS= read -r folder; do
        # Use the existing cleanup_complete_vehicle_folder function with safety checks
        if cleanup_complete_vehicle_folder "$folder" "$s3_bucket" "$aws_profile" "$aws_region"; then
            success_count=$((success_count + 1))
        else
            fail_count=$((fail_count + 1))
        fi
    done <<< "$matching_folders"

    echo ""
    log_info "Cleanup complete: $success_count cleaned, $fail_count failed"

    if [ $fail_count -gt 0 ]; then
        return 1
    fi

    return 0
}

# Check if current time is within operational hours and warn if not
# This helps identify potential test failures due to operational hours restrictions
check_operational_hours() {
    local config_file=${1:-config/config.yaml}

    # Parse operational hours from config (exclude comments with grep -v)
    local op_hours_enabled=$(grep -A 10 "operational_hours:" "$config_file" | grep -v "^[[:space:]]*#" | grep "enabled:" | head -1 | awk '{print $2}' | tr -d '"')
    local op_start=$(grep -A 10 "operational_hours:" "$config_file" | grep -v "^[[:space:]]*#" | grep "start:" | grep -v "upload_on_start" | head -1 | awk '{print $2}' | tr -d '"')
    local op_end=$(grep -A 10 "operational_hours:" "$config_file" | grep -v "^[[:space:]]*#" | grep "end:" | head -1 | awk '{print $2}' | tr -d '"')

    # If operational hours not enabled, no warning needed
    if [ "$op_hours_enabled" != "true" ]; then
        log_info "Operational hours: DISABLED (24/7 uploads enabled)"
        return 0
    fi

    # Get current time in HH:MM format
    local current_time=$(date +%H:%M)
    local current_hour=$(date +%H | sed 's/^0//')
    local current_minute=$(date +%M | sed 's/^0//')

    # Parse start/end hours
    local start_hour=$(echo "$op_start" | cut -d: -f1 | sed 's/^0//')
    local start_minute=$(echo "$op_start" | cut -d: -f2 | sed 's/^0//')
    local end_hour=$(echo "$op_end" | cut -d: -f1 | sed 's/^0//')
    local end_minute=$(echo "$op_end" | cut -d: -f2 | sed 's/^0//')

    # Convert to minutes since midnight for easier comparison
    local current_minutes=$((current_hour * 60 + current_minute))
    local start_minutes=$((start_hour * 60 + start_minute))
    local end_minutes=$((end_hour * 60 + end_minute))

    # Check if within operational hours
    if [ $current_minutes -ge $start_minutes ] && [ $current_minutes -lt $end_minutes ]; then
        log_info "Operational hours: WITHIN window ($op_start - $op_end, current: $current_time)"
        return 0
    else
        # Outside operational hours - issue warning
        echo ""
        log_error "⚠️  WARNING: OUTSIDE OPERATIONAL HOURS ⚠️"
        log_error "⚠️  Current time: $current_time"
        log_error "⚠️  Operational hours: $op_start - $op_end (enabled: $op_hours_enabled)"
        log_error "⚠️  FILES WILL BE QUEUED BUT NOT UPLOADED UNTIL $op_start"
        log_error "⚠️  This test may FAIL if it expects immediate uploads"
        log_error "⚠️  Solution: Run test during operational hours OR disable operational_hours in config"
        echo ""
        return 1
    fi
}

# Export functions
export -f log_info log_success log_error log_warning log_skip
export -f print_test_header print_test_summary
export -f wait_with_progress create_test_dir generate_test_file set_file_mtime
export -f cleanup_test_s3_data cleanup_complete_vehicle_folder generate_test_vehicle_id cleanup_all_test_folders
export -f assert_file_exists assert_file_not_exists assert_equals assert_contains assert_greater_than
export -f load_config start_tvm_service stop_tvm_service get_service_logs check_service_health
export -f cleanup_test_env save_test_result check_operational_hours
