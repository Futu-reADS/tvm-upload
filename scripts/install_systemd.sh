#!/bin/bash
# Install TVM Upload System as systemd service
# Usage: sudo ./install_systemd.sh

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo ""
echo "======================================"
echo "  TVM Upload System - Installation"
echo "======================================"
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}❌ ERROR: Please run as root${NC}"
    echo "Usage: sudo $0"
    exit 1
fi

# Check if service file exists
if [ ! -f "systemd/tvm-upload.service" ]; then
    echo -e "${RED}❌ ERROR: systemd/tvm-upload.service not found${NC}"
    echo "Please run this script from the tvm-upload repository root"
    exit 1
fi

echo -e "${BLUE}1. Copying service file...${NC}"
cp systemd/tvm-upload.service /etc/systemd/system/
chmod 644 /etc/systemd/system/tvm-upload.service
echo -e "${GREEN}   ✅ Service file copied${NC}"

echo ""
echo -e "${BLUE}2. Creating directories...${NC}"
mkdir -p /etc/tvm-upload
mkdir -p /var/lib/tvm-upload
mkdir -p /opt/tvm-upload
echo -e "${GREEN}   ✅ Directories created${NC}"

echo ""
echo -e "${BLUE}3. Checking configuration file...${NC}"
if [ ! -f /etc/tvm-upload/config.yaml ]; then
    if [ -f config/config.yaml.example ]; then
        echo -e "${YELLOW}   ⚠️  Creating default config from example...${NC}"
        cp config/config.yaml.example /etc/tvm-upload/config.yaml
        echo -e "${GREEN}   ✅ Config created${NC}"
        echo -e "${YELLOW}   ⚠️  IMPORTANT: Edit /etc/tvm-upload/config.yaml before starting!${NC}"
    else
        echo -e "${YELLOW}   ⚠️  No example config found${NC}"
        echo -e "${YELLOW}   ⚠️  You must create /etc/tvm-upload/config.yaml manually${NC}"
    fi
else
    echo -e "${GREEN}   ✅ Config already exists${NC}"
fi

echo ""
echo -e "${BLUE}4. Setting permissions...${NC}"
if id "autoware" &>/dev/null; then
    chown -R autoware:autoware /var/lib/tvm-upload
    echo -e "${GREEN}   ✅ Set ownership to autoware user${NC}"
else
    echo -e "${YELLOW}   ⚠️  User 'autoware' not found${NC}"
    echo -e "${YELLOW}   ⚠️  Please create user or edit service file${NC}"
fi

echo ""
echo -e "${BLUE}5. Reloading systemd...${NC}"
systemctl daemon-reload
echo -e "${GREEN}   ✅ Systemd reloaded${NC}"

echo ""
echo -e "${GREEN}======================================"
echo "  ✅ Installation complete!"
echo "======================================${NC}"
echo ""
echo -e "${YELLOW}Next Steps:${NC}"
echo ""
echo "1. Edit configuration:"
echo "   sudo nano /etc/tvm-upload/config.yaml"
echo ""
echo "2. Enable service (start on boot):"
echo "   sudo systemctl enable tvm-upload"
echo ""
echo "3. Start service:"
echo "   sudo systemctl start tvm-upload"
echo ""
echo "4. Check status:"
echo "   sudo systemctl status tvm-upload"
echo ""
echo "5. View logs:"
echo "   sudo journalctl -u tvm-upload -f"
echo ""
echo "6. Reload config (send SIGHUP):"
echo "   sudo systemctl reload tvm-upload"
echo ""
echo "======================================="
echo ""
