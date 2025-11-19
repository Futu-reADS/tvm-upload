# Passwordless Sudo Setup for Production Simulation Test

## Problem
The production simulation test (Test 9) asks for sudo password multiple times during execution because it needs to:
- Manipulate network with `iptables` (simulate WiFi on/off)
- Add network latency with `tc` (simulate poor connectivity)
- Kill processes with `kill` (simulate crashes)

## Solution: One-Time Setup

Run this **ONCE** to enable passwordless sudo for test commands:

```bash
sudo ./scripts/deployment/setup_test_sudo.sh
```

This creates `/etc/sudoers.d/tvm-test` with rules allowing your user to run specific commands without password.

## What Commands Are Allowed

Only these specific commands will be passwordless:
- `/usr/sbin/iptables` and `/sbin/iptables`
- `/usr/sbin/tc` and `/sbin/tc`
- `/usr/bin/kill` and `/bin/kill`
- `/usr/bin/systemctl stop tvm-upload`

**No other sudo commands are affected** - this is safe and targeted.

## Usage After Setup

### Run Production Simulation Without Prompts

```bash
# 2-hour test (no password prompts)
make test-prod-sim-2h

# 8-hour test (no password prompts)
make test-prod-sim-8h

# 24-hour test (no password prompts)
make test-prod-sim-24h

# Or directly with skip prompts flag
./scripts/testing/gap-tests/run_production_simulation.sh config/config.yaml vehicle-TEST 2 true
#                                                                                    ^
#                                                                                    skip prompts
```

### Manual Usage (With Prompts)

If you don't run the setup, you can still run the test but will be prompted for password:

```bash
# Will ask for password when needed
./scripts/testing/gap-tests/run_production_simulation.sh config/config.yaml vehicle-TEST 2
```

## Verify Setup

Check if passwordless sudo is working:

```bash
# This should work without password after setup
sudo -n iptables -L > /dev/null 2>&1 && echo "✓ Passwordless sudo working" || echo "✗ Setup needed"
```

## Remove Passwordless Sudo

If you want to remove this configuration later:

```bash
sudo rm /etc/sudoers.d/tvm-test
```

## Security Notes

- ✅ Only allows specific commands needed for testing
- ✅ Only allows for your user account
- ✅ Uses `/etc/sudoers.d/` which is the recommended approach
- ✅ Validated with `visudo -c` before installation
- ✅ No shell access or arbitrary command execution

This is **safe for development/test environments** where you need to run network simulation tests frequently.

**⚠️ NOT recommended for production servers** - only use on development machines or dedicated test systems.

## Troubleshooting

### "Invalid sudoers syntax" error
The setup script validates syntax before applying. If you see this error:
1. Check you're running on Linux (not macOS/BSD)
2. Ensure `visudo` is installed
3. Report the issue

### Still asking for password
1. Verify the file exists: `ls -l /etc/sudoers.d/tvm-test`
2. Check permissions: should be `0440`
3. Check ownership: should be `root:root`
4. Verify your username matches: `grep $USER /etc/sudoers.d/tvm-test`

### "This test requires passwordless sudo" error
This means you ran with `SKIP_PROMPTS=true` but haven't set up passwordless sudo yet:
```bash
sudo ./scripts/deployment/setup_test_sudo.sh
```

---

**Created**: 2025-11-14
**Last Updated**: 2025-11-14
