#!/bin/bash
# Setup passwordless sudo for production simulation test
# This allows the test to run without password prompts for network manipulation

set -e

echo "Setting up passwordless sudo for production simulation test..."
echo ""
echo "This will allow the following commands to run without password:"
echo "  - iptables (for WiFi simulation)"
echo "  - tc (for network degradation)"
echo "  - kill (for crash simulation)"
echo ""

# Get current user
CURRENT_USER="$USER"

# Create sudoers file for TVM test
SUDOERS_FILE="/etc/sudoers.d/tvm-test"

echo "Creating sudoers configuration..."

# Create temporary file
TMP_FILE=$(mktemp)

cat > "$TMP_FILE" << EOF
# TVM Production Simulation Test - Passwordless sudo
# Created: $(date)
# User: $CURRENT_USER

# Allow iptables commands (for WiFi simulation)
$CURRENT_USER ALL=(ALL) NOPASSWD: /usr/sbin/iptables *
$CURRENT_USER ALL=(ALL) NOPASSWD: /sbin/iptables *

# Allow tc commands (for network degradation)
$CURRENT_USER ALL=(ALL) NOPASSWD: /usr/sbin/tc *
$CURRENT_USER ALL=(ALL) NOPASSWD: /sbin/tc *

# Allow kill commands (for crash simulation)
$CURRENT_USER ALL=(ALL) NOPASSWD: /usr/bin/kill *
$CURRENT_USER ALL=(ALL) NOPASSWD: /bin/kill *

# Allow systemctl stop for tvm-upload service
$CURRENT_USER ALL=(ALL) NOPASSWD: /usr/bin/systemctl stop *
$CURRENT_USER ALL=(ALL) NOPASSWD: /bin/systemctl stop *
$CURRENT_USER ALL=(ALL) NOPASSWD: /usr/bin/systemctl is-active *
$CURRENT_USER ALL=(ALL) NOPASSWD: /bin/systemctl is-active *
EOF

# Validate syntax
if visudo -c -f "$TMP_FILE" > /dev/null 2>&1; then
    echo "✓ Sudoers syntax valid"
    sudo cp "$TMP_FILE" "$SUDOERS_FILE"
    sudo chmod 0440 "$SUDOERS_FILE"
    echo "✓ Sudoers file created: $SUDOERS_FILE"
else
    echo "✗ Error: Invalid sudoers syntax"
    rm -f "$TMP_FILE"
    exit 1
fi

rm -f "$TMP_FILE"

echo ""
echo "✓ Setup complete!"
echo ""

# Verify it works
echo "Verifying passwordless sudo..."
if sudo -n iptables -L > /dev/null 2>&1; then
    echo "✓ iptables: works without password"
else
    echo "✗ iptables: still requires password (may need to log out/in)"
fi

if sudo -n tc qdisc show > /dev/null 2>&1; then
    echo "✓ tc: works without password"
else
    echo "✗ tc: still requires password (may need to log out/in)"
fi

echo ""
echo "You can now run production simulation without password prompts:"
echo "  make test-prod-sim-2h"
echo "  ./scripts/testing/gap-tests/run_production_simulation.sh"
echo ""
echo "To remove this configuration:"
echo "  sudo rm $SUDOERS_FILE"
echo ""
echo "If verification failed, try logging out and back in, or run:"
echo "  sudo -k  # Clear sudo timestamp"
