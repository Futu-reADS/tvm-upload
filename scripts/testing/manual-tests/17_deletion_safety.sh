#!/bin/bash
# Manual Test 17: Deletion Safety System (4-Layer Protection)
# Tests: System directory protection, allow_deletion flag, recursive flag, pattern matching
#
# This test verifies the complete 4-layer deletion safety system:
# - Layer 1: System directory protection (hard-coded)
# - Layer 2: allow_deletion flag
# - Layer 3: recursive flag
# - Layer 4: Pattern matching
#
# Test Categories:
# 1. System directory protection (files never deleted from /var, /etc, etc.)
# 2. allow_deletion flag (explicit user control)
# 3. recursive flag (subdirectory protection)
# 4. Pattern matching (only matching files deleted)
# 5. Combined safety layers

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../../lib/test_helpers.sh"

TEST_NAME="Deletion Safety System"
TEST_NUMBER="17"

print_test_header "$TEST_NAME" "$TEST_NUMBER"

# Cleanup function
cleanup() {
    log_info "Cleaning up test environment"

    if [ -n "$TEST_DIR" ] && [ -d "$TEST_DIR" ]; then
        rm -rf "$TEST_DIR"
    fi

    if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
        kill "$PID" 2>/dev/null || true
        wait "$PID" 2>/dev/null || true
    fi
}

trap cleanup EXIT

# Create test environment
log_info "Setting up test environment"
TEST_DIR=$(mktemp -d)
USER_LOG_DIR="$TEST_DIR/user_logs"
USER_SUBDIR="$USER_LOG_DIR/subdir"
CONFIG_FILE="$TEST_DIR/config.yaml"
QUEUE_FILE="$TEST_DIR/queue.json"
REGISTRY_FILE="$TEST_DIR/registry.json"

mkdir -p "$USER_LOG_DIR"
mkdir -p "$USER_SUBDIR"

log_info "Test directory: $TEST_DIR"
log_info "User log directory: $USER_LOG_DIR"

# ============================================================================
# TEST 1: System Directory Protection (Layer 1)
# ============================================================================
echo ""
log_info "=== TEST 1: System directory protection blocks deletion ==="

# Note: We can't actually test /var/log deletion (requires root and dangerous)
# Instead, we verify the behavior programmatically

python3 <<EOF
from pathlib import Path
from src.disk_manager import DiskManager

# Test system directory detection
dm = DiskManager(["/tmp"])

# System directories should be detected
system_files = [
    Path("/var/log/syslog.1"),
    Path("/etc/config.conf"),
    Path("/usr/bin/app"),
    Path("/opt/software/file"),
]

all_blocked = True
for file_path in system_files:
    is_system = dm._is_system_directory(file_path)
    if not is_system:
        print(f"❌ FAIL: {file_path} not detected as system directory")
        all_blocked = False

if all_blocked:
    print("✅ All system directories correctly detected")
    exit(0)
else:
    exit(1)
EOF

if [ $? -eq 0 ]; then
    log_success "System directory protection works"
else
    log_error "System directory detection failed"
    exit 1
fi

# ============================================================================
# TEST 2: allow_deletion=false Flag (Layer 2)
# ============================================================================
echo ""
log_info "=== TEST 2: allow_deletion=false blocks deletion ==="

# Create test config with allow_deletion=false
cat > "$CONFIG_FILE" <<EOF
vehicle_id: "test-deletion-safety"

log_directories:
  - path: $USER_LOG_DIR
    source: protected
    allow_deletion: false  # Should block deletion

s3:
  bucket: test-bucket
  region: cn-north-1
  credentials_path: ~/.aws
  profile: china

upload:
  schedule:
    mode: "interval"
    interval_hours: 24
  file_stable_seconds: 1
  upload_on_start: false
  queue_file: $QUEUE_FILE
  processed_files_registry:
    registry_file: $REGISTRY_FILE
    retention_days: 30
  scan_existing_files:
    enabled: false

deletion:
  after_upload:
    enabled: true
    keep_days: 0  # Delete immediately
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
EOF

# Create test file
TEST_FILE_1="$USER_LOG_DIR/protected.log"
echo "test data" > "$TEST_FILE_1"

# Test deletion blocking
python3 <<EOF
from pathlib import Path
from src.config_manager import ConfigManager
from src.disk_manager import DiskManager

config = ConfigManager("$CONFIG_FILE")
log_dir_configs = config.get('log_directories')

# Build directory_configs
directory_configs = {}
for item in log_dir_configs:
    resolved_path = str(Path(item['path']).expanduser().resolve())
    directory_configs[resolved_path] = {
        'pattern': item.get('pattern'),
        'recursive': item.get('recursive', True),
        'allow_deletion': item.get('allow_deletion', True)
    }

dm = DiskManager(
    log_directories=["$USER_LOG_DIR"],
    directory_configs=directory_configs
)

# Check if file is blocked by allow_deletion=false
test_file = Path("$TEST_FILE_1")
result = dm._matches_pattern(test_file)

if result is False:
    print("✅ File correctly blocked by allow_deletion=false")
    exit(0)
else:
    print("❌ File NOT blocked by allow_deletion=false")
    exit(1)
EOF

if [ $? -eq 0 ]; then
    log_success "allow_deletion=false blocks deletion"
else
    log_error "allow_deletion=false did not block deletion"
    exit 1
fi

# ============================================================================
# TEST 3: recursive=false Flag (Layer 3)
# ============================================================================
echo ""
log_info "=== TEST 3: recursive=false blocks subdirectory deletion ==="

# Update config with recursive=false
cat > "$CONFIG_FILE" <<EOF
vehicle_id: "test-deletion-safety"

log_directories:
  - path: $USER_LOG_DIR
    source: logs
    recursive: false  # Should block subdirectory deletion
    allow_deletion: true

s3:
  bucket: test-bucket
  region: cn-north-1
  credentials_path: ~/.aws
  profile: china

upload:
  schedule:
    mode: "interval"
    interval_hours: 24
  file_stable_seconds: 1
  upload_on_start: false
  queue_file: $QUEUE_FILE
  processed_files_registry:
    registry_file: $REGISTRY_FILE
    retention_days: 30
  scan_existing_files:
    enabled: false

deletion:
  after_upload:
    enabled: true
    keep_days: 0
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
EOF

# Create test files
TOP_LEVEL_FILE="$USER_LOG_DIR/top.log"
NESTED_FILE="$USER_SUBDIR/nested.log"
echo "top level" > "$TOP_LEVEL_FILE"
echo "nested" > "$NESTED_FILE"

# Test recursive=false blocking
python3 <<EOF
from pathlib import Path
from src.config_manager import ConfigManager
from src.disk_manager import DiskManager

config = ConfigManager("$CONFIG_FILE")
log_dir_configs = config.get('log_directories')

directory_configs = {}
for item in log_dir_configs:
    resolved_path = str(Path(item['path']).expanduser().resolve())
    directory_configs[resolved_path] = {
        'pattern': item.get('pattern'),
        'recursive': item.get('recursive', True),
        'allow_deletion': item.get('allow_deletion', True)
    }

dm = DiskManager(
    log_directories=["$USER_LOG_DIR"],
    directory_configs=directory_configs
)

# Top-level file should be allowed
top_file = Path("$TOP_LEVEL_FILE")
top_result = dm._matches_pattern(top_file)

# Nested file should be blocked
nested_file = Path("$NESTED_FILE")
nested_result = dm._matches_pattern(nested_file)

if top_result is True and nested_result is False:
    print("✅ Top-level allowed, subdirectory blocked (recursive=false works)")
    exit(0)
else:
    print(f"❌ FAIL: top_result={top_result}, nested_result={nested_result}")
    exit(1)
EOF

if [ $? -eq 0 ]; then
    log_success "recursive=false blocks subdirectory deletion"
else
    log_error "recursive=false did not work correctly"
    exit 1
fi

# ============================================================================
# TEST 4: Pattern Matching (Layer 4)
# ============================================================================
echo ""
log_info "=== TEST 4: Pattern matching only allows matching files ==="

# Update config with pattern
cat > "$CONFIG_FILE" <<EOF
vehicle_id: "test-deletion-safety"

log_directories:
  - path: $USER_LOG_DIR
    source: logs
    pattern: "*.log"  # Only .log files
    recursive: true
    allow_deletion: true

s3:
  bucket: test-bucket
  region: cn-north-1
  credentials_path: ~/.aws
  profile: china

upload:
  schedule:
    mode: "interval"
    interval_hours: 24
  file_stable_seconds: 1
  upload_on_start: false
  queue_file: $QUEUE_FILE
  processed_files_registry:
    registry_file: $REGISTRY_FILE
    retention_days: 30
  scan_existing_files:
    enabled: false

deletion:
  after_upload:
    enabled: true
    keep_days: 0
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
EOF

# Create test files
MATCHING_FILE="$USER_LOG_DIR/match.log"
NON_MATCHING_FILE="$USER_LOG_DIR/nomatch.txt"
echo "matches pattern" > "$MATCHING_FILE"
echo "does not match" > "$NON_MATCHING_FILE"

# Test pattern matching
python3 <<EOF
from pathlib import Path
from src.config_manager import ConfigManager
from src.disk_manager import DiskManager

config = ConfigManager("$CONFIG_FILE")
log_dir_configs = config.get('log_directories')

directory_configs = {}
for item in log_dir_configs:
    resolved_path = str(Path(item['path']).expanduser().resolve())
    directory_configs[resolved_path] = {
        'pattern': item.get('pattern'),
        'recursive': item.get('recursive', True),
        'allow_deletion': item.get('allow_deletion', True)
    }

dm = DiskManager(
    log_directories=["$USER_LOG_DIR"],
    directory_configs=directory_configs
)

# .log file should be allowed
log_file = Path("$MATCHING_FILE")
log_result = dm._matches_pattern(log_file)

# .txt file should be blocked
txt_file = Path("$NON_MATCHING_FILE")
txt_result = dm._matches_pattern(txt_file)

if log_result is True and txt_result is False:
    print("✅ Pattern matching works correctly")
    exit(0)
else:
    print(f"❌ FAIL: log_result={log_result}, txt_result={txt_result}")
    exit(1)
EOF

if [ $? -eq 0 ]; then
    log_success "Pattern matching filters deletion correctly"
else
    log_error "Pattern matching did not work"
    exit 1
fi

# ============================================================================
# TEST 5: Combined Layers (All 4 Layers Working Together)
# ============================================================================
echo ""
log_info "=== TEST 5: All 4 layers work together correctly ==="

# Update config for combined test
cat > "$CONFIG_FILE" <<EOF
vehicle_id: "test-deletion-safety"

log_directories:
  - path: $USER_LOG_DIR
    source: logs
    pattern: "*.log"
    recursive: false
    allow_deletion: true

s3:
  bucket: test-bucket
  region: cn-north-1
  credentials_path: ~/.aws
  profile: china

upload:
  schedule:
    mode: "interval"
    interval_hours: 24
  file_stable_seconds: 1
  upload_on_start: false
  queue_file: $QUEUE_FILE
  processed_files_registry:
    registry_file: $REGISTRY_FILE
    retention_days: 30
  scan_existing_files:
    enabled: false

deletion:
  after_upload:
    enabled: true
    keep_days: 0
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
EOF

# Create various test files
TOP_LOG="$USER_LOG_DIR/top.log"          # Should pass (top-level, .log)
TOP_TXT="$USER_LOG_DIR/top.txt"          # Should fail (pattern)
SUB_LOG="$USER_SUBDIR/sub.log"           # Should fail (subdirectory)
echo "data" > "$TOP_LOG"
echo "data" > "$TOP_TXT"
echo "data" > "$SUB_LOG"

# Test combined layers
python3 <<EOF
from pathlib import Path
from src.config_manager import ConfigManager
from src.disk_manager import DiskManager

config = ConfigManager("$CONFIG_FILE")
log_dir_configs = config.get('log_directories')

directory_configs = {}
for item in log_dir_configs:
    resolved_path = str(Path(item['path']).expanduser().resolve())
    directory_configs[resolved_path] = {
        'pattern': item.get('pattern'),
        'recursive': item.get('recursive', True),
        'allow_deletion': item.get('allow_deletion', True)
    }

dm = DiskManager(
    log_directories=["$USER_LOG_DIR"],
    directory_configs=directory_configs
)

# Test all scenarios
top_log = dm._matches_pattern(Path("$TOP_LOG"))     # Should be True
top_txt = dm._matches_pattern(Path("$TOP_TXT"))     # Should be False (pattern)
sub_log = dm._matches_pattern(Path("$SUB_LOG"))     # Should be False (recursive)

print(f"top.log (expect True):  {top_log}")
print(f"top.txt (expect False): {top_txt}")
print(f"sub.log (expect False): {sub_log}")

if top_log is True and top_txt is False and sub_log is False:
    print("✅ All 4 layers work together correctly")
    exit(0)
else:
    print("❌ FAIL: Combined layers not working correctly")
    exit(1)
EOF

if [ $? -eq 0 ]; then
    log_success "Combined 4-layer protection works correctly"
else
    log_error "Combined layers failed"
    exit 1
fi

# ============================================================================
# Summary
# ============================================================================
print_test_summary

echo ""
log_info "Test completed successfully"
echo ""
echo "✅ Deletion Safety System Verification:"
echo "   Layer 1: System directory protection ✓"
echo "   Layer 2: allow_deletion flag ✓"
echo "   Layer 3: recursive flag ✓"
echo "   Layer 4: Pattern matching ✓"
echo "   Combined: All layers working together ✓"
echo ""
