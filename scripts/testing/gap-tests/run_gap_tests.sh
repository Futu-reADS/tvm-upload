#!/bin/bash
# Run Gap Coverage Tests
# These tests cover features not fully tested in the original 16 manual tests

set -e

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Default configuration
CONFIG_FILE="${1:-config/config.yaml}"
TEST_VEHICLE_ID="${2:-vehicle-CN-GAP}"

# Results tracking
TESTS_PASSED=0
TESTS_FAILED=0
TESTS_TOTAL=11

# Print header
echo -e "${BLUE}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║    TVM Upload System - Gap & Advanced Test Suite              ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${YELLOW}Configuration:${NC} $CONFIG_FILE"
echo -e "${YELLOW}Base Vehicle ID:${NC} $TEST_VEHICLE_ID"
echo -e "${YELLOW}Total Tests:${NC} $TESTS_TOTAL"
echo ""
echo -e "${YELLOW}NOTE:${NC} Each test creates isolated S3 folders with timestamps"
echo -e "${YELLOW}      Folders are automatically cleaned after each test${NC}"
echo ""

# Check for running TVM services (production or previous test runs)
echo -e "${YELLOW}Checking for running TVM services...${NC}"
RUNNING_SERVICES=$(pgrep -f "python.*src.main" || echo "")

if [ -n "$RUNNING_SERVICES" ]; then
    echo -e "${RED}⚠  Found running TVM services that must be stopped:${NC}"
    ps -p $RUNNING_SERVICES -o pid,cmd || true
    echo ""
    echo -e "${YELLOW}To continue, I will stop all running TVM services.${NC}"
    echo ""
    read -p "Do you want to continue? (y/N) " -n 1 -r
    echo
    echo ""

    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo -e "${GREEN}Stopping services...${NC}"

        # Check if systemd service is running
        if systemctl is-active --quiet tvm-upload 2>/dev/null; then
            echo -e "${YELLOW}Stopping systemd service (requires sudo)...${NC}"
            if sudo systemctl stop tvm-upload; then
                echo -e "${GREEN}✓ Systemd service stopped${NC}"
            else
                echo -e "${RED}✗ Failed to stop systemd service${NC}"
            fi
            sleep 1
        fi

        # Kill any remaining processes
        STILL_RUNNING=$(pgrep -f "python.*src.main" || echo "")
        if [ -n "$STILL_RUNNING" ]; then
            echo -e "${YELLOW}Stopping remaining processes...${NC}"
            for pid in $STILL_RUNNING; do
                if kill $pid 2>/dev/null; then
                    echo -e "${GREEN}✓ Stopped PID $pid${NC}"
                fi
            done
            sleep 1
        fi

        # Final verification
        STILL_RUNNING=$(pgrep -f "python.*src.main" || echo "")
        if [ -z "$STILL_RUNNING" ]; then
            echo -e "${GREEN}✓ All TVM services stopped successfully${NC}"
            echo ""
        else
            echo -e "${RED}✗ Some services still running (PIDs: $STILL_RUNNING)${NC}"
            echo -e "${RED}Tests cancelled - please stop services manually${NC}"
            exit 1
        fi
    else
        echo -e "${RED}Tests cancelled by user${NC}"
        exit 1
    fi
else
    echo -e "${GREEN}✓ No running TVM services detected${NC}"
    echo ""
fi

# Test list (Gap tests 18-22, Advanced tests 23,25-29)
TESTS=(
    "18_all_sources_complete.sh|All 4 Log Sources Simultaneously"
    "19_deferred_deletion.sh|Deferred Deletion (keep_days > 0)"
    "20_queue_crash_recovery.sh|Queue Recovery After Crash"
    "21_registry_cleanup.sh|Registry Cleanup After Retention Days"
    "22_env_var_expansion.sh|Environment Variable Path Expansion"
    "23_config_validation.sh|Configuration Validation"
    "25_concurrent_operations.sh|Concurrent Operations & Race Conditions"
    "26_resource_limits.sh|Resource Limits & Stress Testing"
    "27_security_scenarios.sh|Security Scenarios & Attack Vectors"
    "28_performance_benchmarks.sh|Performance Benchmarks"
    "29_full_system_integration.sh|Full System Integration"
)

# Run each test
for test_entry in "${TESTS[@]}"; do
    IFS='|' read -r test_file test_name <<< "$test_entry"
    test_path="$SCRIPT_DIR/$test_file"

    if [ ! -f "$test_path" ]; then
        echo -e "${RED}✗ Test not found: $test_file${NC}"
        TESTS_FAILED=$((TESTS_FAILED + 1))
        continue
    fi

    echo ""
    echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}Running: $test_name${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"

    # Run test
    if bash "$test_path" "$CONFIG_FILE" "$TEST_VEHICLE_ID"; then
        echo -e "${GREEN}✓ PASSED: $test_name${NC}"
        TESTS_PASSED=$((TESTS_PASSED + 1))
    else
        echo -e "${RED}✗ FAILED: $test_name${NC}"
        TESTS_FAILED=$((TESTS_FAILED + 1))
    fi
done

# Print summary
echo ""
echo -e "${BLUE}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║                        Test Summary                            ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${GREEN}Passed:${NC} $TESTS_PASSED / $TESTS_TOTAL"
echo -e "${RED}Failed:${NC} $TESTS_FAILED / $TESTS_TOTAL"
echo ""

# Success rate
SUCCESS_RATE=$(awk "BEGIN {printf \"%.1f\", ($TESTS_PASSED / $TESTS_TOTAL) * 100}")
echo -e "${YELLOW}Success Rate:${NC} $SUCCESS_RATE%"

# Overall result
echo ""
if [ $TESTS_FAILED -eq 0 ]; then
    echo -e "${GREEN}╔════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║      ALL GAP & ADVANCED TESTS PASSED! ✓                       ║${NC}"
    echo -e "${GREEN}╚════════════════════════════════════════════════════════════════╝${NC}"
    exit 0
else
    echo -e "${RED}╔════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${RED}║         SOME GAP/ADVANCED TESTS FAILED ✗                       ║${NC}"
    echo -e "${RED}╚════════════════════════════════════════════════════════════════╝${NC}"
    exit 1
fi
