#!/bin/bash
# TVM Upload - Production Installer
# One-command installation for vehicle deployment
# Usage: sudo ./scripts/install.sh

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'
BOLD='\033[1m'

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# Installation paths
INSTALL_ROOT="/opt/tvm-upload"
DATA_DIR="/var/lib/tvm-upload"
LOG_DIR="/var/log/tvm-upload"
CONFIG_DIR="/etc/tvm-upload"
SYSTEMD_DIR="/etc/systemd/system"

# Track progress
STEP=0
TOTAL_STEPS=9

# Helper functions
print_header() {
    echo ""
    echo -e "${CYAN}╔════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║${NC}  ${BOLD}TVM Log Upload - Production Installation${NC}                ${CYAN}║${NC}"
    echo -e "${CYAN}╔════════════════════════════════════════════════════════════════╗${NC}"
    echo ""
}

step() {
    STEP=$((STEP + 1))
    echo ""
    echo -e "${CYAN}[${STEP}/${TOTAL_STEPS}]${NC} ${BOLD}$1${NC}"
}

success() {
    echo -e "      ${GREEN}✓${NC} $1"
}

error() {
    echo -e "      ${RED}✗${NC} $1"
}

info() {
    echo -e "      ${BLUE}ℹ${NC} $1"
}

warn() {
    echo -e "      ${YELLOW}⚠${NC} $1"
}

fatal_error() {
    echo ""
    echo -e "${RED}${BOLD}[ERROR]${NC} ${RED}$1${NC}"
    echo ""
    echo "Installation failed. Cleaning up..."
    # Rollback not implemented here - user should run uninstall.sh
    exit 1
}

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}Error:${NC} This script must be run as root"
    echo "Usage: sudo ./scripts/install.sh"
    exit 1
fi

# Get actual user (not root)
if [ -n "$SUDO_USER" ]; then
    ACTUAL_USER="$SUDO_USER"
    ACTUAL_HOME="/home/$SUDO_USER"
else
    ACTUAL_USER="$USER"
    ACTUAL_HOME="$HOME"
fi

print_header

# Step 1: Pre-deployment validation
step "Running pre-deployment validation"

info "Checking system requirements..."

# Run validation as actual user (not root)
su - "$ACTUAL_USER" -c "cd $PROJECT_ROOT && bash $SCRIPT_DIR/verify_deployment.sh" || fatal_error "Pre-deployment validation failed"

success "Environment validated"

# Step 2: Install Python dependencies
step "Installing Python dependencies"

info "Installing from pyproject.toml..."

cd "$PROJECT_ROOT"

if pip3 install -e . &> /tmp/tvm-install-pip.log; then
    success "Python dependencies installed (production mode)"
else
    error "Failed to install Python dependencies"
    cat /tmp/tvm-install-pip.log
    fatal_error "pip install failed"
fi

# Step 3: Create system directories
step "Creating system directories"

mkdir -p "$INSTALL_ROOT"
mkdir -p "$DATA_DIR"
mkdir -p "$LOG_DIR"
mkdir -p "$CONFIG_DIR"

success "Created: $INSTALL_ROOT"
success "Created: $DATA_DIR"
success "Created: $LOG_DIR"
success "Created: $CONFIG_DIR"

# Set ownership
chown -R "$ACTUAL_USER:$ACTUAL_USER" "$INSTALL_ROOT"
chown -R "$ACTUAL_USER:$ACTUAL_USER" "$DATA_DIR"
chown -R "$ACTUAL_USER:$ACTUAL_USER" "$LOG_DIR"
chown -R "$ACTUAL_USER:$ACTUAL_USER" "$CONFIG_DIR"

success "Set ownership to $ACTUAL_USER"

# Step 4: Create user log directories
step "Creating user log directories"

info "Creating log directories in user home..."

mkdir -p "$ACTUAL_HOME/.parcel/log/terminal"
mkdir -p "$ACTUAL_HOME/.ros/log"
mkdir -p "$ACTUAL_HOME/ros2_ws/log"

success "Created: $ACTUAL_HOME/.parcel/log/terminal"
success "Created: $ACTUAL_HOME/.ros/log"
success "Created: $ACTUAL_HOME/ros2_ws/log"

# Set ownership on user directories
chown -R "$ACTUAL_USER:$ACTUAL_USER" "$ACTUAL_HOME/.parcel" 2>/dev/null || true
chown -R "$ACTUAL_USER:$ACTUAL_USER" "$ACTUAL_HOME/.ros" 2>/dev/null || true
chown -R "$ACTUAL_USER:$ACTUAL_USER" "$ACTUAL_HOME/ros2_ws" 2>/dev/null || true

success "Set ownership on user directories"

# Step 5: Copy application files
step "Copying application files"

info "Copying source code..."

cp -r "$PROJECT_ROOT/src" "$INSTALL_ROOT/"
cp -r "$PROJECT_ROOT/config" "$INSTALL_ROOT/"
cp "$PROJECT_ROOT/pyproject.toml" "$INSTALL_ROOT/"
cp "$PROJECT_ROOT/setup.py" "$INSTALL_ROOT/" 2>/dev/null || true  # Optional, for setuptools

success "Application files copied"

# Step 6: Configure settings
step "Configuring system settings"

info "Preparing configuration..."

# Backup existing config if it exists
if [ -f "$CONFIG_DIR/config.yaml" ]; then
    BACKUP_FILE="$CONFIG_DIR/config.yaml.backup.$(date +%Y%m%d_%H%M%S)"
    cp "$CONFIG_DIR/config.yaml" "$BACKUP_FILE"
    warn "Backed up existing config to: $BACKUP_FILE"
fi

# Copy config to /etc
if [ -f "$PROJECT_ROOT/config/config.yaml" ]; then
    cp "$PROJECT_ROOT/config/config.yaml" "$CONFIG_DIR/config.yaml"
    success "Config copied to $CONFIG_DIR/config.yaml"
else
    fatal_error "Config file not found: $PROJECT_ROOT/config/config.yaml"
fi

# Replace USER placeholder with actual username
sed -i "s|/home/USER|$ACTUAL_HOME|g" "$CONFIG_DIR/config.yaml"
sed -i "s|USER|$ACTUAL_USER|g" "$CONFIG_DIR/config.yaml"

# Update paths in config
sed -i "s|queue_file:.*|queue_file: $DATA_DIR/queue.json|g" "$CONFIG_DIR/config.yaml"
sed -i "s|registry_file:.*|registry_file: $DATA_DIR/processed_files.json|g" "$CONFIG_DIR/config.yaml"

success "Replaced USER with $ACTUAL_USER"
success "Updated data paths"

# Step 7: Install systemd service
step "Installing systemd service"

info "Creating systemd service file..."

cat > "$SYSTEMD_DIR/tvm-upload.service" <<EOF
[Unit]
Description=TVM Log Upload Service
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$ACTUAL_USER
Group=$ACTUAL_USER
WorkingDirectory=$INSTALL_ROOT
ExecStart=/usr/bin/python3 -m src.main --config $CONFIG_DIR/config.yaml --log-level INFO
ExecReload=/bin/kill -HUP \$MAINPID
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=tvm-upload

# Security
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths=$DATA_DIR $LOG_DIR $ACTUAL_HOME/.ros/log $ACTUAL_HOME/.parcel/log $ACTUAL_HOME/ros2_ws/log

[Install]
WantedBy=multi-user.target
EOF

success "Service file created"

# Reload systemd
systemctl daemon-reload
success "systemd reloaded"

# Enable service (auto-start on boot)
systemctl enable tvm-upload.service
success "Service enabled (auto-start on boot)"

# Step 8: Start service
step "Starting tvm-upload service"

info "Starting service..."

if systemctl start tvm-upload.service; then
    success "Service started"
else
    fatal_error "Failed to start service. Check: journalctl -u tvm-upload -n 50"
fi

# Wait for service to stabilize
info "Waiting for service to stabilize (30 seconds)..."
sleep 30

# Step 9: Verify installation
step "Verifying installation"

info "Checking service status..."

if systemctl is-active --quiet tvm-upload.service; then
    success "Service is running"
else
    error "Service is not running"
    fatal_error "Service failed to start. Check: journalctl -u tvm-upload -n 50"
fi

# Check for errors in logs
ERROR_COUNT=$(journalctl -u tvm-upload --since "1 minute ago" | grep -i "error" | wc -l)
if [ "$ERROR_COUNT" -eq 0 ]; then
    success "No errors in recent logs"
else
    warn "$ERROR_COUNT errors found in recent logs"
    info "Check logs: journalctl -u tvm-upload -f"
fi

# Get vehicle ID from config
VEHICLE_ID=$(grep "^vehicle_id:" "$CONFIG_DIR/config.yaml" | awk '{print $2}' | tr -d '"')

# Print success message
echo ""
echo -e "${CYAN}════════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}${BOLD}✓ Installation Successful!${NC}"
echo -e "${CYAN}════════════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "${BOLD}Vehicle Information:${NC}"
echo -e "  Vehicle ID:      ${CYAN}$VEHICLE_ID${NC}"
echo -e "  Service Status:  ${GREEN}Active (running)${NC}"
echo -e "  Installation:    $INSTALL_ROOT"
echo -e "  Configuration:   $CONFIG_DIR/config.yaml"
echo -e "  Data Directory:  $DATA_DIR"
echo ""
echo -e "${BOLD}Next Steps:${NC}"
echo -e "  ${GREEN}1.${NC} Monitor logs:       ${CYAN}journalctl -u tvm-upload -f${NC}"
echo -e "  ${GREEN}2.${NC} Check health:       ${CYAN}sudo $SCRIPT_DIR/health_check.sh${NC}"
echo -e "  ${GREEN}3.${NC} View S3 uploads:    ${CYAN}aws s3 ls s3://[bucket]/$VEHICLE_ID/${NC}"
echo ""
echo -e "${BOLD}Useful Commands:${NC}"
echo -e "  Start service:   ${CYAN}sudo systemctl start tvm-upload${NC}"
echo -e "  Stop service:    ${CYAN}sudo systemctl stop tvm-upload${NC}"
echo -e "  Restart service: ${CYAN}sudo systemctl restart tvm-upload${NC}"
echo -e "  View status:     ${CYAN}sudo systemctl status tvm-upload${NC}"
echo -e "  Edit config:     ${CYAN}sudo nano $CONFIG_DIR/config.yaml${NC}"
echo -e "  Reload config:   ${CYAN}sudo systemctl reload tvm-upload${NC}"
echo ""
echo -e "${CYAN}════════════════════════════════════════════════════════════════${NC}"
echo ""

# Create convenience scripts
info "Creating convenience scripts..."

cat > "$INSTALL_ROOT/health_check.sh" <<'EOF'
#!/bin/bash
sudo /opt/tvm-upload/scripts/deployment/health_check.sh
EOF
chmod +x "$INSTALL_ROOT/health_check.sh"

success "Installation complete!"
echo ""

exit 0
