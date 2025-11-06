#!/bin/bash
# Standalone S3 Test Data Cleanup Script
# Removes leftover test data from S3 bucket
#
# This script is useful for:
# - Cleaning up after interrupted test runs
# - Manual cleanup without running full test suite
# - Checking what test folders exist on S3
# - Emergency cleanup before deployment
#
# Usage:
#   ./scripts/cleanup_test_s3_data.sh [options]
#
# Options:
#   --dry-run           Preview what would be deleted (no actual deletion)
#   --config FILE       Use specific config file (default: config/config.yaml)
#   --pattern PATTERN   Custom vehicle pattern to search for (default: auto-detected from config)
#   --all-tests         Clean ALL test folders (vehicle-TEST-*), not just this vehicle
#   --help              Show this help message
#
# Examples:
#   # Preview what would be deleted
#   ./scripts/cleanup_test_s3_data.sh --dry-run
#
#   # Clean up test data for vehicle from config
#   ./scripts/cleanup_test_s3_data.sh
#
#   # Clean up with custom pattern
#   ./scripts/cleanup_test_s3_data.sh --pattern "vehicle-TEST-CN-001"
#
#   # Clean ALL test folders (any vehicle)
#   ./scripts/cleanup_test_s3_data.sh --all-tests
#
# Safety Features:
#   - Only deletes folders containing "TEST" in the name
#   - Protected production vehicle IDs (hard-coded list)
#   - Interactive confirmation before deletion
#   - Shows what will be deleted with file counts

set -e

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Change to project root
cd "$PROJECT_ROOT"

# Load helper functions
source "${SCRIPT_DIR}/lib/test_helpers.sh"

# Default values
DRY_RUN=false
CONFIG_FILE="config/config.yaml"
CUSTOM_PATTERN=""
ALL_TESTS=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --config)
            CONFIG_FILE="$2"
            shift 2
            ;;
        --pattern)
            CUSTOM_PATTERN="$2"
            shift 2
            ;;
        --all-tests)
            ALL_TESTS=true
            shift
            ;;
        --help|-h)
            # Show help (already in header comments)
            head -n 40 "$0" | grep "^#" | sed 's/^# \?//'
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Banner
echo ""
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║     S3 Test Data Cleanup Script                               ║"
echo "╔════════════════════════════════════════════════════════════════╗"
echo ""

# Verify config file exists
if [ ! -f "$CONFIG_FILE" ]; then
    log_error "Configuration file not found: $CONFIG_FILE"
    exit 1
fi

# Parse S3 configuration
log_info "Loading configuration from: $CONFIG_FILE"
S3_BUCKET=$(grep "bucket:" "$CONFIG_FILE" | head -1 | awk '{print $2}' | tr -d '"')
AWS_REGION=$(grep "region:" "$CONFIG_FILE" | head -1 | awk '{print $2}' | tr -d '"')
AWS_PROFILE=$(grep "profile:" "$CONFIG_FILE" | head -1 | awk '{print $2}' | tr -d '"')

if [ -z "$S3_BUCKET" ] || [ -z "$AWS_REGION" ]; then
    log_error "Failed to parse S3 configuration from $CONFIG_FILE"
    exit 1
fi

log_success "Configuration loaded"
echo "  S3 Bucket:   $S3_BUCKET"
echo "  AWS Region:  $AWS_REGION"
echo "  AWS Profile: ${AWS_PROFILE:-default}"
echo ""

# Determine cleanup pattern
if [ -n "$CUSTOM_PATTERN" ]; then
    # User provided custom pattern
    CLEANUP_PATTERN="$CUSTOM_PATTERN"
    log_info "Using custom pattern: $CLEANUP_PATTERN"
elif [ "$ALL_TESTS" = true ]; then
    # Clean all test folders
    CLEANUP_PATTERN="vehicle-TEST"
    log_warning "Cleaning ALL test folders (all vehicles)"
else
    # Auto-detect from config vehicle_id
    ORIGINAL_VEHICLE_ID=$(grep "^vehicle_id:" "$CONFIG_FILE" | awk '{print $2}' | tr -d '"')

    if [ -n "$ORIGINAL_VEHICLE_ID" ]; then
        VEHICLE_NAME=$(echo "$ORIGINAL_VEHICLE_ID" | sed 's/^vehicle-//')
        CLEANUP_PATTERN="vehicle-TEST-${VEHICLE_NAME}-MANUAL"
        log_info "Auto-detected pattern from config: $CLEANUP_PATTERN"
    else
        CLEANUP_PATTERN="vehicle-TEST-MANUAL"
        log_warning "Could not detect vehicle_id from config, using generic pattern: $CLEANUP_PATTERN"
    fi
fi

echo ""

# Dry run mode indicator
if [ "$DRY_RUN" = true ]; then
    log_warning "🔍 DRY RUN MODE - No deletions will be performed"
    echo ""
fi

# ============================================================================
# Execute Cleanup
# ============================================================================

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║     Searching for Test Folders                                 ║"
echo "╔════════════════════════════════════════════════════════════════╗"
echo ""

# Call cleanup function
if cleanup_all_test_folders "$CLEANUP_PATTERN" "$S3_BUCKET" "$AWS_PROFILE" "$AWS_REGION" "$DRY_RUN"; then
    echo ""
    log_success "✓ Cleanup completed successfully"
    exit 0
else
    echo ""
    log_error "✗ Cleanup completed with errors"
    exit 1
fi
