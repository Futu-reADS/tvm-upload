#!/bin/bash
# Test runner for TVM Upload System

set -e  # Exit on any error

echo "======================================"
echo "TVM Upload System - Test Suite"
echo "======================================"

echo ""
echo "1. Running unit tests..."
echo "--------------------------------------"
pytest tests/test_*.py -v

echo ""
echo "2. Running integration tests..."
echo "--------------------------------------"
pytest tests/integration/ -v -s

echo ""
echo "======================================"
echo "All automated tests passed!"
echo "======================================"

echo ""
echo "Manual scripts available (run separately):"
echo "  - python3 scripts/test_watchdog_debug.py"
echo "  - python3 scripts/test_s3_upload.py (requires AWS credentials)"

python3 scripts/test_watchdog_debug.py
