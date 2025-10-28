#!/bin/bash
# TVM Upload - Health Check
# Verifies system is working correctly
# Usage: ./scripts/health_check.sh

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'
BOLD='\033[1m'

# Paths
CONFIG_FILE="/etc/tvm-upload/config.yaml"
DATA_DIR="/var/lib/tvm-upload"
QUEUE_FILE="$DATA_DIR/queue.json"
REGISTRY_FILE="$DATA_DIR/processed_files.json"

# If config not in /etc, try local
if [ ! -f "$CONFIG_FILE" ]; then
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
    CONFIG_FILE="$PROJECT_ROOT/config/config.yaml"
    DATA_DIR="$PROJECT_ROOT/data"
    QUEUE_FILE="$DATA_DIR/queue.json"
    REGISTRY_FILE="$DATA_DIR/processed_files.json"
fi

# Parse config
VEHICLE_ID=$(grep "^vehicle_id:" "$CONFIG_FILE" 2>/dev/null | awk '{print $2}' | tr -d '"')
S3_BUCKET=$(grep "bucket:" "$CONFIG_FILE" 2>/dev/null | head -1 | awk '{print $2}' | tr -d '"')
AWS_REGION=$(grep "region:" "$CONFIG_FILE" 2>/dev/null | head -1 | awk '{print $2}' | tr -d '"')
AWS_PROFILE=$(grep "profile:" "$CONFIG_FILE" 2>/dev/null | head -1 | awk '{print $2}' | tr -d '"')

# Status tracking
CHECKS_PASSED=0
CHECKS_FAILED=0
CHECKS_WARNING=0

# Helper functions
print_header() {
    echo ""
    echo -e "${CYAN}╔════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║${NC}  ${BOLD}TVM Upload Health Check - $VEHICLE_ID${NC}"
    # Pad to align
    PADDING=$((47 - ${#VEHICLE_ID}))
    printf "${CYAN}║${NC}"
    printf "%${PADDING}s" ""
    echo -e "${CYAN}║${NC}"
    echo -e "${CYAN}╔════════════════════════════════════════════════════════════════╗${NC}"
    echo ""
}

check_pass() {
    echo -e "${GREEN}✓${NC} $1"
    CHECKS_PASSED=$((CHECKS_PASSED + 1))
}

check_fail() {
    echo -e "${RED}✗${NC} $1"
    CHECKS_FAILED=$((CHECKS_FAILED + 1))
}

check_warn() {
    echo -e "${YELLOW}⚠${NC} $1"
    CHECKS_WARNING=$((CHECKS_WARNING + 1))
}

info() {
    echo -e "${BLUE}ℹ${NC} $1"
}

print_section() {
    echo ""
    echo -e "${BOLD}$1${NC}"
}

# Start health check
print_header

# Check 1: Service Status
print_section "Service Status"

if systemctl is-active --quiet tvm-upload.service 2>/dev/null; then
    UPTIME=$(systemctl show tvm-upload.service --property=ActiveEnterTimestamp --value)
    UPTIME_FRIENDLY=$(systemctl show tvm-upload.service --property=ActiveEnterTimestamp --value | xargs -I {} date -d {} '+%Y-%m-%d %H:%M:%S' 2>/dev/null || echo "Unknown")
    check_pass "Service is running (started: $UPTIME_FRIENDLY)"
elif pgrep -f "tvm.*upload" > /dev/null; then
    check_warn "Service running but not via systemd"
else
    check_fail "Service is not running"
    info "Start with: sudo systemctl start tvm-upload"
fi

# Check 2: Recent Logs
print_section "Recent Activity"

if command -v journalctl &> /dev/null && systemctl list-unit-files | grep -q "tvm-upload.service"; then
    # Check for errors in last 24 hours
    ERROR_COUNT=$(journalctl -u tvm-upload --since "24 hours ago" 2>/dev/null | grep -i "error" | wc -l)

    if [ "$ERROR_COUNT" -eq 0 ]; then
        check_pass "No errors in last 24 hours"
    elif [ "$ERROR_COUNT" -lt 5 ]; then
        check_warn "$ERROR_COUNT errors in last 24 hours"
    else
        check_fail "$ERROR_COUNT errors in last 24 hours"
        info "Check logs: journalctl -u tvm-upload -n 100"
    fi

    # Check for recent uploads
    UPLOAD_COUNT=$(journalctl -u tvm-upload --since "24 hours ago" 2>/dev/null | grep -i "upload.*success" | wc -l)

    if [ "$UPLOAD_COUNT" -gt 0 ]; then
        check_pass "$UPLOAD_COUNT successful uploads in last 24 hours"
    else
        check_warn "No uploads in last 24 hours"
        info "This may be normal if no new files were created"
    fi

    # Get last upload time
    LAST_UPLOAD=$(journalctl -u tvm-upload --since "7 days ago" 2>/dev/null | grep -i "upload.*success" | tail -1 | awk '{print $1, $2, $3}')

    if [ -n "$LAST_UPLOAD" ]; then
        info "Last upload: $LAST_UPLOAD"
    fi
else
    info "Service logs not available (systemd not configured)"
fi

# Check 3: Queue Status
print_section "Upload Queue"

if [ -f "$QUEUE_FILE" ]; then
    check_pass "Queue file exists: $QUEUE_FILE"

    QUEUE_SIZE=$(cat "$QUEUE_FILE" 2>/dev/null | python3 -c "import sys, json; data=json.load(sys.stdin); print(len(data.get('files', [])))" 2>/dev/null || echo "0")

    if [ "$QUEUE_SIZE" -eq 0 ]; then
        check_pass "Queue is empty (all files uploaded)"
    elif [ "$QUEUE_SIZE" -lt 10 ]; then
        check_warn "$QUEUE_SIZE files pending upload"
    else
        check_warn "$QUEUE_SIZE files pending upload"
        info "Large queue may indicate upload issues"
    fi
else
    check_warn "Queue file not found (may not be created yet)"
fi

# Check 4: Registry Status
print_section "Upload Registry"

if [ -f "$REGISTRY_FILE" ]; then
    check_pass "Registry file exists: $REGISTRY_FILE"

    REGISTRY_COUNT=$(cat "$REGISTRY_FILE" 2>/dev/null | python3 -c "import sys, json; data=json.load(sys.stdin); print(len(data))" 2>/dev/null || echo "0")

    if [ "$REGISTRY_COUNT" -gt 0 ]; then
        check_pass "$REGISTRY_COUNT files tracked in registry"
    else
        check_warn "Registry is empty (no files uploaded yet)"
    fi
else
    check_warn "Registry file not found (will be created on first upload)"
fi

# Check 5: Disk Usage
print_section "Disk Space"

DISK_USAGE=$(df -h / | tail -1 | awk '{print $5}' | tr -d '%')
DISK_AVAIL=$(df -h / | tail -1 | awk '{print $4}')

if [ "$DISK_USAGE" -lt 80 ]; then
    check_pass "Disk usage: ${DISK_USAGE}% (${DISK_AVAIL} available)"
elif [ "$DISK_USAGE" -lt 90 ]; then
    check_warn "Disk usage: ${DISK_USAGE}% (${DISK_AVAIL} available)"
else
    check_fail "Disk usage: ${DISK_USAGE}% (${DISK_AVAIL} available)"
    info "Critical disk space - cleanup may be triggered"
fi

# Check 6: S3 Connectivity
print_section "S3 Connectivity"

if command -v aws &> /dev/null; then
    if [ -n "$AWS_PROFILE" ]; then
        AWS_CMD="aws --profile $AWS_PROFILE --region $AWS_REGION"
    else
        AWS_CMD="aws --region $AWS_REGION"
    fi

    # Check recent uploads
    info "Checking recent uploads..."

    RECENT_UPLOADS=$($AWS_CMD s3 ls "s3://$S3_BUCKET/$VEHICLE_ID/" --recursive 2>/dev/null | tail -10)

    if [ -n "$RECENT_UPLOADS" ]; then
        check_pass "S3 bucket accessible"

        TOTAL_FILES=$($AWS_CMD s3 ls "s3://$S3_BUCKET/$VEHICLE_ID/" --recursive 2>/dev/null | wc -l)
        check_pass "Total files in S3: $TOTAL_FILES"

        echo ""
        echo -e "${BOLD}Latest Uploads:${NC}"
        echo "$RECENT_UPLOADS" | tail -5 | while read -r line; do
            FILE_DATE=$(echo "$line" | awk '{print $1, $2}')
            FILE_SIZE=$(echo "$line" | awk '{print $3}')
            FILE_NAME=$(echo "$line" | awk '{print $4}' | rev | cut -d'/' -f1 | rev)

            # Convert size to human readable
            if [ "$FILE_SIZE" -gt 1048576 ]; then
                FILE_SIZE_H="$(echo "scale=1; $FILE_SIZE / 1048576" | bc) MB"
            elif [ "$FILE_SIZE" -gt 1024 ]; then
                FILE_SIZE_H="$(echo "scale=1; $FILE_SIZE / 1024" | bc) KB"
            else
                FILE_SIZE_H="${FILE_SIZE} B"
            fi

            echo -e "  ${CYAN}$FILE_DATE${NC} - $FILE_NAME (${FILE_SIZE_H})"
        done
    else
        check_warn "No files found in S3 yet"
        info "Files will appear after first upload"
    fi
else
    check_warn "AWS CLI not available for S3 verification"
fi

# Check 7: Configuration
print_section "Configuration"

if [ -f "$CONFIG_FILE" ]; then
    check_pass "Config file exists: $CONFIG_FILE"

    # Check critical settings
    UPLOAD_SCHEDULE=$(grep -A 15 "schedule:" "$CONFIG_FILE" | grep "mode:" | awk '{print $2}' | tr -d '"')
    if [ -n "$UPLOAD_SCHEDULE" ]; then
        check_pass "Upload schedule: $UPLOAD_SCHEDULE"
    fi

    DELETION_ENABLED=$(grep -A 10 "after_upload:" "$CONFIG_FILE" | grep "enabled:" | head -1 | awk '{print $2}')
    if [ "$DELETION_ENABLED" = "true" ]; then
        KEEP_DAYS=$(grep -A 10 "after_upload:" "$CONFIG_FILE" | grep "keep_days:" | awk '{print $2}')
        check_pass "Deletion policy: enabled (keep $KEEP_DAYS days)"
    else
        check_warn "Deletion policy: disabled"
    fi
else
    check_fail "Config file not found: $CONFIG_FILE"
fi

# Print Summary
echo ""
echo -e "${CYAN}════════════════════════════════════════════════════════════════${NC}"
echo -e "${BOLD}Health Check Summary${NC}"
echo -e "${CYAN}════════════════════════════════════════════════════════════════${NC}"
echo -e "  ${GREEN}Passed:${NC}   $CHECKS_PASSED"
echo -e "  ${RED}Failed:${NC}   $CHECKS_FAILED"
echo -e "  ${YELLOW}Warnings:${NC} $CHECKS_WARNING"
echo ""

if [ $CHECKS_FAILED -eq 0 ]; then
    if [ $CHECKS_WARNING -eq 0 ]; then
        echo -e "${GREEN}${BOLD}[PASS]${NC} ${GREEN}System is healthy${NC} ✓"
    else
        echo -e "${YELLOW}${BOLD}[WARN]${NC} ${YELLOW}System is working with minor issues${NC}"
    fi
    echo -e "       ${BLUE}No action required${NC}"
else
    echo -e "${RED}${BOLD}[FAIL]${NC} ${RED}System has issues${NC}"
    echo -e "       ${RED}Review failed checks above${NC}"
fi

echo ""
echo -e "${CYAN}════════════════════════════════════════════════════════════════${NC}"
echo ""

exit $CHECKS_FAILED
