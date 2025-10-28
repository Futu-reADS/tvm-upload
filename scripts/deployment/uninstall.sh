#!/bin/bash
# TVM Upload - Uninstaller
# Clean removal of TVM upload system
# Usage: sudo ./scripts/uninstall.sh [--keep-data]

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'
BOLD='\033[1m'

# Installation paths
INSTALL_ROOT="/opt/tvm-upload"
DATA_DIR="/var/lib/tvm-upload"
LOG_DIR="/var/log/tvm-upload"
CONFIG_DIR="/etc/tvm-upload"
SYSTEMD_SERVICE="/etc/systemd/system/tvm-upload.service"

# Options
KEEP_DATA=false

# Parse arguments
for arg in "$@"; do
    case $arg in
        --keep-data)
            KEEP_DATA=true
            ;;
    esac
done

# Helper functions
print_header() {
    echo ""
    echo -e "${CYAN}╔════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║${NC}  ${BOLD}TVM Log Upload - Uninstallation${NC}                         ${CYAN}║${NC}"
    echo -e "${CYAN}╔════════════════════════════════════════════════════════════════╗${NC}"
    echo ""
}

success() {
    echo -e "${GREEN}✓${NC} $1"
}

info() {
    echo -e "${BLUE}ℹ${NC} $1"
}

warn() {
    echo -e "${YELLOW}⚠${NC} $1"
}

error() {
    echo -e "${RED}✗${NC} $1"
}

step() {
    echo ""
    echo -e "${BOLD}$1${NC}"
}

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}Error:${NC} This script must be run as root"
    echo "Usage: sudo ./scripts/uninstall.sh [--keep-data]"
    exit 1
fi

print_header

# Warning
if [ "$KEEP_DATA" = false ]; then
    echo -e "${YELLOW}${BOLD}WARNING:${NC} ${YELLOW}This will completely remove TVM Upload system${NC}"
    echo -e "${YELLOW}         All data (queue, registry, logs) will be deleted!${NC}"
    echo ""
    echo -e "To keep data, run: ${CYAN}sudo ./scripts/uninstall.sh --keep-data${NC}"
    echo ""
    read -p "Are you sure you want to continue? (yes/no): " -r
    echo
    if [[ ! $REPLY =~ ^[Yy]es$ ]]; then
        echo "Uninstall cancelled."
        exit 0
    fi
else
    echo -e "${BLUE}Data will be preserved (queue, registry, logs)${NC}"
    echo ""
fi

# Step 1: Stop service
step "Stopping service"

if systemctl is-active --quiet tvm-upload.service 2>/dev/null; then
    info "Stopping tvm-upload service..."
    systemctl stop tvm-upload.service
    success "Service stopped"
else
    info "Service is not running"
fi

# Step 2: Disable service
step "Disabling service"

if systemctl is-enabled --quiet tvm-upload.service 2>/dev/null; then
    info "Disabling auto-start..."
    systemctl disable tvm-upload.service
    success "Service disabled"
else
    info "Service is not enabled"
fi

# Step 3: Remove systemd service
step "Removing systemd service"

if [ -f "$SYSTEMD_SERVICE" ]; then
    rm -f "$SYSTEMD_SERVICE"
    success "Service file removed"
    systemctl daemon-reload
    success "systemd reloaded"
else
    info "Service file not found"
fi

# Step 4: Remove installation directory
step "Removing installation files"

if [ -d "$INSTALL_ROOT" ]; then
    rm -rf "$INSTALL_ROOT"
    success "Removed: $INSTALL_ROOT"
else
    info "Installation directory not found"
fi

# Step 5: Remove configuration
step "Removing configuration"

if [ -d "$CONFIG_DIR" ]; then
    if [ "$KEEP_DATA" = true ]; then
        info "Keeping configuration (--keep-data)"
    else
        rm -rf "$CONFIG_DIR"
        success "Removed: $CONFIG_DIR"
    fi
else
    info "Configuration directory not found"
fi

# Step 6: Remove data directory
step "Removing data directory"

if [ -d "$DATA_DIR" ]; then
    if [ "$KEEP_DATA" = true ]; then
        info "Keeping data directory: $DATA_DIR"
        warn "Contains: queue.json, processed_files.json"
    else
        rm -rf "$DATA_DIR"
        success "Removed: $DATA_DIR"
    fi
else
    info "Data directory not found"
fi

# Step 7: Remove logs
step "Removing logs"

if [ -d "$LOG_DIR" ]; then
    if [ "$KEEP_DATA" = true ]; then
        info "Keeping logs: $LOG_DIR"
    else
        rm -rf "$LOG_DIR"
        success "Removed: $LOG_DIR"
    fi
else
    info "Log directory not found"
fi

# Step 8: Check for orphaned processes
step "Checking for orphaned processes"

ORPHANED=$(pgrep -f "tvm.*upload" | wc -l)

if [ "$ORPHANED" -gt 0 ]; then
    warn "Found $ORPHANED orphaned process(es)"
    info "Killing orphaned processes..."
    pkill -f "tvm.*upload" || true
    success "Orphaned processes terminated"
else
    success "No orphaned processes found"
fi

# Print summary
echo ""
echo -e "${CYAN}════════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}${BOLD}✓ Uninstallation Complete${NC}"
echo -e "${CYAN}════════════════════════════════════════════════════════════════${NC}"
echo ""

if [ "$KEEP_DATA" = true ]; then
    echo -e "${BOLD}Preserved Data:${NC}"
    if [ -d "$CONFIG_DIR" ]; then
        echo -e "  ${CYAN}Config:${NC}   $CONFIG_DIR"
    fi
    if [ -d "$DATA_DIR" ]; then
        echo -e "  ${CYAN}Data:${NC}     $DATA_DIR"
    fi
    if [ -d "$LOG_DIR" ]; then
        echo -e "  ${CYAN}Logs:${NC}     $LOG_DIR"
    fi
    echo ""
    echo -e "${BLUE}To completely remove data:${NC}"
    echo -e "  ${CYAN}sudo rm -rf $CONFIG_DIR $DATA_DIR $LOG_DIR${NC}"
    echo ""
else
    echo -e "${BOLD}Removed:${NC}"
    echo -e "  ${GREEN}✓${NC} Installation files"
    echo -e "  ${GREEN}✓${NC} Configuration"
    echo -e "  ${GREEN}✓${NC} Data directory"
    echo -e "  ${GREEN}✓${NC} Logs"
    echo -e "  ${GREEN}✓${NC} systemd service"
    echo ""
fi

echo -e "${CYAN}════════════════════════════════════════════════════════════════${NC}"
echo ""

exit 0
