#!/bin/bash
# Run Production Simulation Test (Test 30)
# This is a long-running test separate from the main test suite

set -e

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Configuration
CONFIG_FILE="${1:-config/config.yaml}"
TEST_VEHICLE_ID="${2:-vehicle-CN-PRODSIM}"
TEST_DURATION_HOURS="${3:-2}"  # Default 2 hours

echo -e "${BLUE}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║     TVM Upload System - Production Simulation Test            ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${YELLOW}Configuration:${NC} $CONFIG_FILE"
echo -e "${YELLOW}Base Vehicle ID:${NC} $TEST_VEHICLE_ID"
echo -e "${YELLOW}Test Duration:${NC} $TEST_DURATION_HOURS hours"
echo ""
echo -e "${YELLOW}⚠️  WARNING:${NC} This test will run for ${BLUE}$TEST_DURATION_HOURS hours${NC}"
echo -e "${YELLOW}   It will simulate real campus vehicle operation with:${NC}"
echo "   • Continuous file generation"
echo "   • WiFi availability changes"
echo "   • WiFi flapping (2-3 second micro-disconnections)"
echo "   • System crashes and recovery"
echo "   • Network degradation"
echo "   • Disk pressure scenarios"
echo ""
echo -e "${YELLOW}   This test requires:${NC}"
echo "   • Sudo access (for network manipulation)"
echo "   • AWS credentials configured"
echo "   • $((TEST_DURATION_HOURS * 2))GB+ free disk space"
echo "   • Stable system for entire duration"
echo ""

# Confirm
read -p "Do you want to continue? (y/N) " -n 1 -r
echo
echo ""

if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo -e "${YELLOW}Test cancelled by user${NC}"
    exit 0
fi

# Check for running TVM services
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
            echo -e "${RED}Test cancelled - please stop services manually${NC}"
            exit 1
        fi
    else
        echo -e "${RED}Test cancelled by user${NC}"
        exit 0
    fi
else
    echo -e "${GREEN}✓ No running TVM services detected${NC}"
    echo ""
fi

# Run the test
echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}Starting Production Simulation Test${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
echo ""

if bash "$SCRIPT_DIR/30_production_simulation.sh" "$CONFIG_FILE" "$TEST_VEHICLE_ID" "$TEST_DURATION_HOURS"; then
    echo ""
    echo -e "${GREEN}╔════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║      PRODUCTION SIMULATION TEST PASSED! ✓                      ║${NC}"
    echo -e "${GREEN}╚════════════════════════════════════════════════════════════════╝${NC}"
    exit 0
else
    echo ""
    echo -e "${RED}╔════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${RED}║         PRODUCTION SIMULATION TEST FAILED ✗                    ║${NC}"
    echo -e "${RED}╚════════════════════════════════════════════════════════════════╝${NC}"
    exit 1
fi
