# Installation Script Updates

**Date:** 2025-10-28
**Updated:** scripts/install.sh

---

## Changes Made

### ✅ Feature 1: User Log Directory Creation (HIGH PRIORITY)

**Added New Step 4:** "Creating user log directories"

```bash
mkdir -p "$ACTUAL_HOME/.parcel/log/terminal"
mkdir -p "$ACTUAL_HOME/.ros/log"
mkdir -p "$ACTUAL_HOME/ros2_ws/log"
```

**Why needed:**
- These directories might not exist on fresh vehicles
- Without them, watchdog cannot monitor for log files
- System would fail silently with no uploads

**Impact:** Ensures all monitored directories exist before service starts

---

### ✅ Feature 2: Permissions on User Directories (MEDIUM PRIORITY)

**Added to Step 4:**

```bash
chown -R "$ACTUAL_USER:$ACTUAL_USER" "$ACTUAL_HOME/.parcel" 2>/dev/null || true
chown -R "$ACTUAL_USER:$ACTUAL_USER" "$ACTUAL_HOME/.ros" 2>/dev/null || true
chown -R "$ACTUAL_USER:$ACTUAL_USER" "$ACTUAL_HOME/ros2_ws" 2>/dev/null || true
```

**Why needed:**
- If directories are created by root, user might not have write access
- Prevents permission denied errors when writing logs
- Ensures service running as user can access all directories

**Note:** Uses `2>/dev/null || true` to silently ignore errors if directories already exist with correct ownership

---

### ✅ Feature 3: Config Backup on Reinstall (MEDIUM PRIORITY)

**Added to Step 6 (before overwriting config):**

```bash
# Backup existing config if it exists
if [ -f "$CONFIG_DIR/config.yaml" ]; then
    BACKUP_FILE="$CONFIG_DIR/config.yaml.backup.$(date +%Y%m%d_%H%M%S)"
    cp "$CONFIG_DIR/config.yaml" "$BACKUP_FILE"
    warn "Backed up existing config to: $BACKUP_FILE"
fi
```

**Why needed:**
- Prevents losing custom configuration on reinstall
- Provides rollback capability if new config has issues
- Timestamps ensure multiple backups don't conflict

**Example backup filename:** `/etc/tvm-upload/config.yaml.backup.20251028_143052`

---

### ✅ Bonus: Updated systemd Service ReadWritePaths

**Updated in Step 7:**

```bash
ReadWritePaths=$DATA_DIR $LOG_DIR $ACTUAL_HOME/.ros/log $ACTUAL_HOME/.parcel/log $ACTUAL_HOME/ros2_ws/log
```

**Why needed:**
- Added `ros2_ws/log` path (was missing)
- Ensures systemd allows service to write to all user log directories
- Prevents permission errors from systemd security hardening

---

## Updated Step Flow

**Before:** 8 steps
**After:** 9 steps

1. Pre-deployment validation
2. Installing Python dependencies
3. Creating system directories
4. **Creating user log directories** ← NEW
5. Copying application files
6. Configuring system settings (now with backup)
7. Installing systemd service (now with ros2_ws path)
8. Starting tvm-upload service
9. Verifying installation

---

## Comparison: Before vs After

| Feature | Before | After |
|---------|--------|-------|
| User log directories | ❌ Not created | ✅ Created with ownership |
| User directory permissions | ❌ Not set | ✅ Set for .parcel, .ros, ros2_ws |
| Config backup | ❌ None | ✅ Timestamped backup |
| Systemd ReadWritePaths | ⚠️ Missing ros2_ws | ✅ All paths included |
| Total steps | 8 | 9 |

---

## Testing the Updates

### Test 1: Fresh Installation

```bash
# Should create all user directories
sudo ./scripts/install.sh

# Verify directories exist
ls -la ~/.parcel/log/terminal
ls -la ~/.ros/log
ls -la ~/ros2_ws/log

# Check ownership
ls -ld ~/.parcel ~/.ros ~/ros2_ws
```

### Test 2: Reinstallation (Config Backup)

```bash
# First installation
sudo ./scripts/install.sh

# Modify config
sudo nano /etc/tvm-upload/config.yaml
# (make some changes)

# Reinstall
sudo ./scripts/install.sh

# Check backup was created
ls -la /etc/tvm-upload/config.yaml.backup.*
```

### Test 3: Service Permissions

```bash
# After installation, check service can write to directories
sudo systemctl status tvm-upload

# Create test file
echo "test" > ~/.parcel/log/terminal/test.log

# Check service logs for upload
sudo journalctl -u tvm-upload -f
```

---

## Lines Added

**Total lines added:** ~20 lines
- Step 4 (user directories): 12 lines
- Config backup: 5 lines
- Systemd path update: 1 line (modified existing)
- Step number updates: 4 lines (renumbering)

---

## Compatibility

**Backward compatible:** Yes
- Existing installations can be updated
- Script checks if directories already exist before creating
- Config backup only happens if file exists
- Permissions setting uses `|| true` to ignore errors

**No breaking changes:** Old behavior preserved where applicable

---

## Migration from Old Script

Users of `install_systemd.sh` can now switch to `install.sh` because:

✅ All critical features from old script are now included
✅ Plus new features: pre-validation, post-verification
✅ Better user experience with progress indicators
✅ Self-contained installation in /opt

**Recommended migration path:**

```bash
# 1. Uninstall using old script or new uninstall.sh
sudo ./scripts/uninstall.sh --keep-data

# 2. Install using new script
sudo ./scripts/install.sh

# Note: Your existing config will be backed up automatically
```

---

## Future Improvements (Optional)

Not implemented yet, but could be added:

1. **Update mode**: `--update` flag to gracefully update existing installation without uninstalling
2. **Service file backup**: Backup systemd service before overwriting (like config backup)
3. **Resource limits**: Add MemoryMax and CPUQuota to systemd service
4. **Environment variables**: Add AWS_PROFILE to service environment

These are nice-to-have but not critical for production deployment.

---

**Status:** ✅ Production Ready
**All critical features from old script are now included in new script**
