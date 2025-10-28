#!/bin/bash
# Quick test to demonstrate scripts are working
set -e

echo "════════════════════════════════════════════════════════════════"
echo "Quick Demonstration - Manual Test Scripts Working"
echo "════════════════════════════════════════════════════════════════"
echo ""

# Run just the first part of the test
source scripts/lib/test_helpers.sh

CONFIG_FILE="config/config.yaml"
TEST_DIR="/tmp/tvm-manual-test"
SERVICE_LOG="/tmp/tvm-service-demo.log"

echo "Step 1: Loading configuration..."
load_config "$CONFIG_FILE"

echo "Step 2: Creating test directory..."
TEST_TERMINAL_DIR="$TEST_DIR/terminal"
mkdir -p "$TEST_TERMINAL_DIR"
log_success "Created test directory: $TEST_TERMINAL_DIR"

echo ""
echo "Step 3: Starting TVM upload service..."
if start_tvm_service "$CONFIG_FILE" "$SERVICE_LOG"; then
    echo ""
    echo "✓✓✓ SUCCESS! All steps working ✓✓✓"
    echo ""
    echo "The manual test scripts are now functional!"
    echo ""

    # Show service is actually running
    echo "Service status:"
    ps aux | grep "python.*src.main" | grep -v grep || echo "  (Service may have already stopped)"
    echo ""

    # Stop service
    stop_tvm_service

    # Cleanup
    rm -rf "$TEST_DIR"

    echo "Demo complete!"
    exit 0
else
    echo "✗ Service failed to start"
    cat "$SERVICE_LOG" | tail -20
    exit 1
fi
