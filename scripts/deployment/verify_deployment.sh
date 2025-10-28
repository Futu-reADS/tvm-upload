#!/bin/bash
# TVM Upload - Pre-Deployment Validator
# Validates environment before installation
# Usage: ./scripts/verify_deployment.sh [config_file]

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color
BOLD='\033[1m'

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# Configuration
CONFIG_FILE="${1:-$PROJECT_ROOT/config/config.yaml}"
CHECKS_PASSED=0
CHECKS_FAILED=0
CHECKS_WARNING=0

# Helper functions
print_header() {
    echo ""
    echo -e "${CYAN}╔════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║${NC}  ${BOLD}TVM Log Upload - Pre-Deployment Validation${NC}              ${CYAN}║${NC}"
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

check_info() {
    echo -e "${BLUE}ℹ${NC} $1"
}

print_section() {
    echo ""
    echo -e "${BOLD}$1${NC}"
    echo "────────────────────────────────────────────────────────────────"
}

print_summary() {
    echo ""
    echo -e "${CYAN}════════════════════════════════════════════════════════════════${NC}"
    echo -e "${BOLD}Validation Summary${NC}"
    echo -e "${CYAN}════════════════════════════════════════════════════════════════${NC}"
    echo -e "  ${GREEN}Passed:${NC}   $CHECKS_PASSED"
    echo -e "  ${RED}Failed:${NC}   $CHECKS_FAILED"
    echo -e "  ${YELLOW}Warnings:${NC} $CHECKS_WARNING"
    echo ""

    if [ $CHECKS_FAILED -eq 0 ]; then
        echo -e "${GREEN}${BOLD}[PASS]${NC} ${GREEN}Environment ready for deployment${NC} ✓"
        echo ""
        return 0
    else
        echo -e "${RED}${BOLD}[FAIL]${NC} ${RED}Cannot proceed with deployment${NC}"
        echo -e "       ${RED}Fix the errors above before installing${NC}"
        echo ""
        return 1
    fi
}

# Start validation
print_header

# Check 1: Configuration file
print_section "Configuration File"

if [ ! -f "$CONFIG_FILE" ]; then
    check_fail "Config file not found: $CONFIG_FILE"
    echo "       Create config.yaml from template:"
    echo "       cp config/config.yaml.example config/config.yaml"
    print_summary
    exit 1
else
    check_pass "Config file exists: $CONFIG_FILE"
fi

# Parse configuration
VEHICLE_ID=$(grep "^vehicle_id:" "$CONFIG_FILE" | awk '{print $2}' | tr -d '"')
S3_BUCKET=$(grep "bucket:" "$CONFIG_FILE" | head -1 | awk '{print $2}' | tr -d '"')
AWS_REGION=$(grep "region:" "$CONFIG_FILE" | head -1 | awk '{print $2}' | tr -d '"')
AWS_PROFILE=$(grep "profile:" "$CONFIG_FILE" | head -1 | awk '{print $2}' | tr -d '"')

if [ -z "$VEHICLE_ID" ]; then
    check_fail "vehicle_id not configured"
else
    check_pass "Vehicle ID: $VEHICLE_ID"
fi

if [ -z "$S3_BUCKET" ]; then
    check_fail "S3 bucket not configured"
else
    check_pass "S3 Bucket: $S3_BUCKET"
fi

if [ -z "$AWS_REGION" ]; then
    check_fail "AWS region not configured"
else
    check_pass "AWS Region: $AWS_REGION"
fi

# Check 2: AWS Credentials
print_section "AWS Credentials"

AWS_CREDS_PATH="$HOME/.aws/credentials"
AWS_CONFIG_PATH="$HOME/.aws/config"

if [ ! -f "$AWS_CREDS_PATH" ]; then
    check_fail "AWS credentials not found: $AWS_CREDS_PATH"
    echo "       Run: aws configure --profile ${AWS_PROFILE:-default}"
else
    check_pass "AWS credentials file exists"

    # Check if profile exists
    if [ -n "$AWS_PROFILE" ]; then
        if grep -q "\\[$AWS_PROFILE\\]" "$AWS_CREDS_PATH"; then
            check_pass "AWS profile configured: $AWS_PROFILE"
        else
            check_fail "AWS profile not found: $AWS_PROFILE"
            echo "       Run: aws configure --profile $AWS_PROFILE"
        fi
    fi
fi

if [ ! -f "$AWS_CONFIG_PATH" ]; then
    check_warn "AWS config file not found (optional)"
else
    check_pass "AWS config file exists"
fi

# Check 3: AWS Connectivity & Permissions
print_section "AWS Connectivity & Permissions"

if command -v aws &> /dev/null; then
    check_pass "AWS CLI installed"

    # Test AWS connectivity
    check_info "Testing AWS connectivity..."

    if [ -n "$AWS_PROFILE" ]; then
        AWS_CMD="aws --profile $AWS_PROFILE --region $AWS_REGION"
    else
        AWS_CMD="aws --region $AWS_REGION"
    fi

    # Test S3 bucket access
    if $AWS_CMD s3 ls "s3://$S3_BUCKET" &> /dev/null; then
        check_pass "S3 bucket accessible: s3://$S3_BUCKET"
    else
        check_fail "Cannot access S3 bucket: s3://$S3_BUCKET"
        echo "       Verify bucket exists and IAM permissions are correct"
    fi

    # Test S3 write permission
    TEST_KEY="${VEHICLE_ID}/test/deployment_test_$(date +%s).txt"
    if echo "test" | $AWS_CMD s3 cp - "s3://$S3_BUCKET/$TEST_KEY" &> /dev/null; then
        check_pass "S3 write permission verified"
        # Cleanup test file
        $AWS_CMD s3 rm "s3://$S3_BUCKET/$TEST_KEY" &> /dev/null || true
    else
        check_fail "S3 write permission denied"
        echo "       IAM policy must allow s3:PutObject"
    fi

    # Test CloudWatch permissions (optional)
    if $AWS_CMD cloudwatch list-metrics --namespace TVM/Upload &> /dev/null; then
        check_pass "CloudWatch permissions verified"
    else
        check_warn "CloudWatch permissions not verified (may not be required)"
    fi

else
    check_fail "AWS CLI not installed"
    echo "       Install: pip install awscli"
fi

# Check 4: System Requirements
print_section "System Requirements"

# Python version
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version | awk '{print $2}')
    PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d. -f1)
    PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d. -f2)

    if [ "$PYTHON_MAJOR" -ge 3 ] && [ "$PYTHON_MINOR" -ge 8 ]; then
        check_pass "Python $PYTHON_VERSION (>= 3.8 required)"
    else
        check_fail "Python $PYTHON_VERSION (>= 3.8 required)"
    fi
else
    check_fail "Python 3 not installed"
fi

# pip
if command -v pip3 &> /dev/null; then
    check_pass "pip3 installed"
else
    check_warn "pip3 not found (may be named 'pip')"
fi

# Disk space
DISK_FREE_GB=$(df -BG "$HOME" | tail -1 | awk '{print $4}' | tr -d 'G')
if [ "$DISK_FREE_GB" -ge 100 ]; then
    check_pass "Disk space: ${DISK_FREE_GB}GB free (>= 100GB required)"
elif [ "$DISK_FREE_GB" -ge 50 ]; then
    check_warn "Disk space: ${DISK_FREE_GB}GB free (recommend >= 100GB)"
else
    check_fail "Disk space: ${DISK_FREE_GB}GB free (>= 50GB required)"
fi

# Check 5: Log Directories
print_section "Log Directories"

# Extract log directories from config (correct awk field)
LOG_DIRS=$(grep -A 100 "^log_directories:" "$CONFIG_FILE" | grep "^\s*-\s*path:" | awk '{print $3}' | head -10)

if [ -z "$LOG_DIRS" ]; then
    check_warn "No log directories configured"
else
    for dir in $LOG_DIRS; do
        # Replace USER placeholder
        dir="${dir//USER/$USER}"

        if [ -d "$dir" ]; then
            check_pass "Log directory exists: $dir"
        else
            check_warn "Log directory not found: $dir (will be created on first use)"
        fi
    done
fi

# Check 6: Network Connectivity
print_section "Network Connectivity"

check_info "Testing AWS China endpoint connectivity..."

if curl -s --connect-timeout 5 "https://s3.${AWS_REGION}.amazonaws.com.cn" &> /dev/null; then
    check_pass "AWS China endpoint reachable"
else
    check_fail "Cannot reach AWS China endpoint"
    echo "       Check network connection and firewall"
fi

# Check 7: Duplicate Vehicle ID
print_section "Vehicle ID Uniqueness"

check_info "Checking for duplicate vehicle ID in S3..."

EXISTING_FILES=$($AWS_CMD s3 ls "s3://$S3_BUCKET/$VEHICLE_ID/" --recursive 2>/dev/null | wc -l)

if [ "$EXISTING_FILES" -gt 0 ]; then
    check_warn "Vehicle ID already exists in S3 ($EXISTING_FILES files)"
    echo "       This vehicle may have been previously deployed"
    echo "       Ensure this is the correct vehicle_id"
else
    check_pass "Vehicle ID is unique (no existing files)"
fi

# Check 8: Required Packages
print_section "Python Dependencies"

MISSING_DEPS=""

# Check for key dependencies (note: PyYAML imports as 'yaml')
for pkg in boto3 watchdog; do
    if python3 -c "import $pkg" &> /dev/null; then
        check_pass "Python package: $pkg"
    else
        check_warn "Python package missing: $pkg (will be installed)"
        MISSING_DEPS="$MISSING_DEPS $pkg"
    fi
done

# Check PyYAML separately (imports as 'yaml')
if python3 -c "import yaml" &> /dev/null; then
    check_pass "Python package: PyYAML"
else
    check_warn "Python package missing: PyYAML (will be installed)"
    MISSING_DEPS="$MISSING_DEPS PyYAML"
fi

if [ -n "$MISSING_DEPS" ]; then
    check_info "Run: pip install -r requirements.txt"
fi

# Check 9: Systemd
print_section "System Integration"

if command -v systemctl &> /dev/null; then
    check_pass "systemd available"
else
    check_fail "systemd not available (required for auto-start)"
fi

# Check if service already installed
if systemctl list-unit-files | grep -q "tvm-upload.service"; then
    check_warn "tvm-upload service already installed"
    echo "       Run uninstall.sh first if reinstalling"
fi

# Print final summary
print_summary
EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}Ready to install:${NC}"
    echo -e "  ${CYAN}sudo ./scripts/install.sh${NC}"
    echo ""
fi

exit $EXIT_CODE
