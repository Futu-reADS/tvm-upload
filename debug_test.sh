#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/scripts/lib/test_helpers.sh"

CONFIG_FILE="config/config.yaml"
SERVICE_LOG="/tmp/tvm-service.log"

echo "About to call start_tvm_service..."
start_tvm_service "$CONFIG_FILE" "$SERVICE_LOG"
echo "Service started successfully!"
