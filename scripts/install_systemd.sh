#!/bin/bash
# Install/Update TVM Upload System as systemd service
# This script ALWAYS updates config and service files on every run
# Usage: sudo ./install_systemd.sh

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
MAGENTA='\033[0;35m'
NC='\033[0m' # No Color

echo ""
echo "=========================================="
echo "  TVM Upload System - Install/Update"
echo "=========================================="
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}✗ ERROR: Please run as root${NC}"
    echo "Usage: sudo $0"
    exit 1
fi

# Detect the user who ran sudo
INSTALL_USER="${SUDO_USER:-$USER}"

if [ -z "$INSTALL_USER" ] || [ "$INSTALL_USER" = "root" ]; then
    echo -e "${RED}✗ ERROR: Could not detect user${NC}"
    echo "Please run with: sudo -u YOUR_USER $0"
    exit 1
fi

echo -e "${GREEN}✓ Detected user: $INSTALL_USER${NC}"

# Check if running from correct directory
if [ ! -f "systemd/tvm-upload.service" ]; then
    echo -e "${RED}✗ ERROR: systemd/tvm-upload.service not found${NC}"
    echo "Please run this script from the tvm-upload repository root:"
    echo "  cd ~/tvm-upload"
    echo "  sudo ./scripts/install_systemd.sh"
    exit 1
fi

if [ ! -f "config/config.yaml.example" ]; then
    echo -e "${RED}✗ ERROR: config.yaml.example not found${NC}"
    echo "Please ensure config.yaml.example exists in the repository root"
    exit 1
fi

echo ""
echo -e "${MAGENTA}[1/7] Creating directories...${NC}"
mkdir -p /etc/tvm-upload
mkdir -p /var/lib/tvm-upload
mkdir -p /opt/tvm-upload
echo -e "${GREEN}✓ Directories created${NC}"

echo ""
echo -e "${MAGENTA}[2/7] Creating log directories...${NC}"
mkdir -p /home/$INSTALL_USER/.parcel/log/terminal
mkdir -p /home/$INSTALL_USER/.ros/log
mkdir -p /home/$INSTALL_USER/ros2_ws/log
echo -e "${GREEN}✓ Log directories created${NC}"

echo ""
echo -e "${MAGENTA}[3/7] Updating configuration file...${NC}"

# Check if service is running
SERVICE_WAS_RUNNING=0
if systemctl is-active --quiet tvm-upload; then
    SERVICE_WAS_RUNNING=1
    echo -e "${YELLOW}  ⚠ Service is running - stopping for config update...${NC}"
    systemctl stop tvm-upload
fi

# Backup existing config if it exists
if [ -f /etc/tvm-upload/config.yaml ]; then
    BACKUP_FILE="/etc/tvm-upload/config.yaml.backup.$(date +%Y%m%d_%H%M%S)"
    cp /etc/tvm-upload/config.yaml "$BACKUP_FILE"
    echo -e "${YELLOW}  ⚠ Backed up existing config to: $BACKUP_FILE${NC}"
fi

# Always copy the new config
cp config/config.yaml.example /etc/tvm-upload/config.yaml

# Replace USER placeholder with actual username
sed -i "s/USER/$INSTALL_USER/g" /etc/tvm-upload/config.yaml

chmod 644 /etc/tvm-upload/config.yaml
echo -e "${GREEN}✓ Config file updated from repository (USER → $INSTALL_USER)${NC}"

echo ""
echo -e "${MAGENTA}[4/7] Updating systemd service file...${NC}"

# Backup existing service file if it exists
if [ -f /etc/systemd/system/tvm-upload.service ]; then
    BACKUP_SERVICE="/etc/systemd/system/tvm-upload.service.backup.$(date +%Y%m%d_%H%M%S)"
    cp /etc/systemd/system/tvm-upload.service "$BACKUP_SERVICE"
    echo -e "${YELLOW}  ⚠ Backed up existing service to: $BACKUP_SERVICE${NC}"
fi

# Copy and update service file with correct user
cp systemd/tvm-upload.service /etc/systemd/system/tvm-upload.service

# Replace INSTALL_USER placeholder with actual username (all occurrences)
sed -i "s/INSTALL_USER/$INSTALL_USER/g" /etc/systemd/system/tvm-upload.service

chmod 644 /etc/systemd/system/tvm-upload.service
echo -e "${GREEN}✓ Service file updated (INSTALL_USER → $INSTALL_USER)${NC}"

echo ""
echo -e "${MAGENTA}[5/7] Setting permissions...${NC}"
chown -R $INSTALL_USER:$INSTALL_USER /var/lib/tvm-upload
chown -R $INSTALL_USER:$INSTALL_USER /home/$INSTALL_USER/.parcel
chown -R $INSTALL_USER:$INSTALL_USER /home/$INSTALL_USER/.ros
chown -R $INSTALL_USER:$INSTALL_USER /home/$INSTALL_USER/ros2_ws
chown root:root /etc/tvm-upload/config.yaml
chmod 644 /etc/tvm-upload/config.yaml
echo -e "${GREEN}✓ Permissions set${NC}"

echo ""
echo -e "${MAGENTA}[6/7] Reloading systemd...${NC}"
systemctl daemon-reload
echo -e "${GREEN}✓ Systemd reloaded${NC}"

echo ""
echo -e "${MAGENTA}[7/7] Post-installation steps...${NC}"

# Enable service if not already enabled
if ! systemctl is-enabled --quiet tvm-upload; then
    systemctl enable tvm-upload
    echo -e "${GREEN}✓ Service enabled (will start on boot)${NC}"
else
    echo -e "${GREEN}✓ Service already enabled${NC}"
fi

# Restart service if it was running
if [ $SERVICE_WAS_RUNNING -eq 1 ]; then
    echo -e "${YELLOW}  ⚠ Restarting service...${NC}"
    systemctl restart tvm-upload
    sleep 2
    if systemctl is-active --quiet tvm-upload; then
        echo -e "${GREEN}✓ Service restarted successfully${NC}"
    else
        echo -e "${RED}✗ Service failed to start - check logs${NC}"
    fi
fi

echo ""
echo -e "${GREEN}=========================================="
echo "  Installation/Update Complete!"
echo -e "==========================================${NC}"
echo ""
echo -e "${YELLOW}Configuration Updated:${NC}"
echo "  Config: /etc/tvm-upload/config.yaml"
echo "  Service: /etc/systemd/system/tvm-upload.service"
echo "  User: $INSTALL_USER"
echo ""

if [ $SERVICE_WAS_RUNNING -eq 0 ]; then
    echo -e "${YELLOW}Service Management:${NC}"
    echo ""
    echo "Start service:"
    echo -e "  ${MAGENTA}sudo systemctl start tvm-upload${NC}"
    echo ""
    echo "Check status:"
    echo -e "  ${MAGENTA}sudo systemctl status tvm-upload${NC}"
    echo ""
    echo "View logs:"
    echo -e "  ${MAGENTA}sudo journalctl -u tvm-upload -f${NC}"
    echo ""
else
    echo -e "${GREEN}Service is running!${NC}"
    echo ""
    echo "Check status:"
    echo -e "  ${MAGENTA}sudo systemctl status tvm-upload${NC}"
    echo ""
    echo "View logs:"
    echo -e "  ${MAGENTA}sudo journalctl -u tvm-upload -f${NC}"
    echo ""
fi

echo "Stop service:"
echo -e "  ${MAGENTA}sudo systemctl stop tvm-upload${NC}"
echo ""
echo "Restart service:"
echo -e "  ${MAGENTA}sudo systemctl restart tvm-upload${NC}"
echo ""
echo "Disable service (prevent auto-start):"
echo -e "  ${MAGENTA}sudo systemctl disable tvm-upload${NC}"
echo ""
echo "==========================================="
echo ""