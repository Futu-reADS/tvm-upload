#!/bin/bash
# Test if passwordless sudo is working for TVM production simulation

echo "Testing passwordless sudo configuration..."
echo ""

PASS=0
FAIL=0

# Test iptables
echo -n "Testing iptables... "
if sudo -n iptables -L > /dev/null 2>&1; then
    echo "✓ PASS"
    PASS=$((PASS + 1))
else
    echo "✗ FAIL"
    FAIL=$((FAIL + 1))
fi

# Test tc
echo -n "Testing tc... "
if sudo -n tc qdisc show > /dev/null 2>&1; then
    echo "✓ PASS"
    PASS=$((PASS + 1))
else
    echo "✗ FAIL"
    FAIL=$((FAIL + 1))
fi

# Test kill
echo -n "Testing kill... "
if sudo -n kill -0 $$ > /dev/null 2>&1; then
    echo "✓ PASS"
    PASS=$((PASS + 1))
else
    echo "✗ FAIL"
    FAIL=$((FAIL + 1))
fi

# Test systemctl
echo -n "Testing systemctl... "
if sudo -n systemctl is-active --quiet ssh 2>&1 | grep -q "" || sudo -n systemctl is-active ssh > /dev/null 2>&1; then
    echo "✓ PASS"
    PASS=$((PASS + 1))
else
    echo "✗ FAIL"
    FAIL=$((FAIL + 1))
fi

echo ""
echo "Results: $PASS passed, $FAIL failed"
echo ""

if [ $FAIL -eq 0 ]; then
    echo "✓ All tests passed! Production simulation will run without password prompts."
    exit 0
else
    echo "✗ Some tests failed. You may need to:"
    echo "  1. Run: sudo ./scripts/deployment/setup_test_sudo.sh"
    echo "  2. Clear sudo cache: sudo -k"
    echo "  3. Log out and back in"
    exit 1
fi
