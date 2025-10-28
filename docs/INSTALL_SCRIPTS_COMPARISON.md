# Installation Scripts Comparison

## Overview

Comparison between the OLD `install_systemd.sh` and NEW `install.sh` scripts.

---

## Feature Comparison

| Feature | OLD (install_systemd.sh) | NEW (install.sh) | Status |
|---------|--------------------------|------------------|--------|
| **Pre-deployment validation** | ❌ None | ✅ Comprehensive (verify_deployment.sh) | ✅ Better |
| **Python dependencies** | ❌ Manual (assumes installed) | ✅ Auto-installs from requirements.txt | ✅ Better |
| **System directories** | ✅ Creates 3 dirs | ✅ Creates 4 dirs (added /var/log) | ✅ Better |
| **User log directories** | ✅ Creates explicitly | ❌ **MISSING** | ⚠️ **NEEDS FIX** |
| **Config source** | config.yaml.example | config/config.yaml | ✅ Better (pre-edited) |
| **Config backup** | ✅ With timestamp | ❌ **MISSING** | ⚠️ **NEEDS FIX** |
| **Service file source** | Template (systemd/tvm-upload.service) | Inline generation | ≈ Similar |
| **Service backup** | ✅ With timestamp | ❌ **MISSING** | ⚠️ Consider adding |
| **Update/reinstall** | ✅ Graceful (stops, backs up, restarts) | ❌ **MISSING** | ⚠️ **NEEDS FIX** |
| **Permissions on user dirs** | ✅ Sets ownership on ~/.parcel, ~/.ros, etc. | ❌ **MISSING** | ⚠️ **NEEDS FIX** |
| **Application files** | Runs from git repo | Copies to /opt/tvm-upload | ✅ Better (self-contained) |
| **Service start** | Only if was running | Always starts | ≈ Different approach |
| **Post-install verification** | ❌ None | ✅ Checks status and logs | ✅ Better |
| **Security hardening** | Basic | ✅ Enhanced (NoNewPrivileges, PrivateTmp) | ✅ Better |

---

## Detailed Analysis

### ✅ NEW Script Improvements

1. **Pre-deployment validation**: Catches issues BEFORE installation
2. **Automatic dependency installation**: No manual pip install needed
3. **Self-contained installation**: Copies everything to /opt (not run from git)
4. **Post-install verification**: Confirms service is running correctly
5. **Enhanced security**: Systemd hardening features

### ⚠️ MISSING Features in NEW Script

#### 1. **User Log Directory Creation** ⚠️ HIGH PRIORITY
**OLD behavior:**
```bash
mkdir -p /home/$INSTALL_USER/.parcel/log/terminal
mkdir -p /home/$INSTALL_USER/.ros/log
mkdir -p /home/$INSTALL_USER/ros2_ws/log
```

**NEW behavior:** Does NOT create these directories

**Impact:** If these directories don't exist, watchdog may fail to monitor them

**Fix needed:** Add log directory creation to new script

---

#### 2. **Permissions on User Directories** ⚠️ MEDIUM PRIORITY
**OLD behavior:**
```bash
chown -R $INSTALL_USER:$INSTALL_USER /home/$INSTALL_USER/.parcel
chown -R $INSTALL_USER:$INSTALL_USER /home/$INSTALL_USER/.ros
chown -R $INSTALL_USER:$INSTALL_USER /home/$INSTALL_USER/ros2_ws
```

**NEW behavior:** Only sets permissions on /opt, /var/lib, /var/log, /etc

**Impact:** May cause permission issues if directories created by root

**Fix needed:** Add user directory permission setting

---

#### 3. **Config Backup on Reinstall** ⚠️ MEDIUM PRIORITY
**OLD behavior:**
```bash
BACKUP_FILE="/etc/tvm-upload/config.yaml.backup.$(date +%Y%m%d_%H%M%S)"
cp /etc/tvm-upload/config.yaml "$BACKUP_FILE"
```

**NEW behavior:** No backup (assumes fresh install)

**Impact:** Lose custom configuration on reinstall

**Fix needed:** Add backup before overwriting

---

#### 4. **Graceful Update/Reinstall** ⚠️ MEDIUM PRIORITY
**OLD behavior:**
- Checks if service is running
- Stops service before updating config
- Backs up existing config and service files
- Restarts service if it was running
- Doesn't fail if service already exists

**NEW behavior:**
- Assumes fresh install
- Warns if service already exists (in verify script)
- User must manually run uninstall.sh first

**Impact:** More manual steps for updates

**Fix needed:** Add update mode or handle existing installation gracefully

---

### Systemd Service File Differences

#### OLD Template (systemd/tvm-upload.service)
```systemd
WorkingDirectory=/home/INSTALL_USER/tvm-upload
ExecStart=/home/INSTALL_USER/tvm-upload/venv/bin/python3 src/main.py
Environment="AWS_PROFILE=china"
Environment="AWS_SHARED_CREDENTIALS_FILE=/home/INSTALL_USER/.aws/credentials"
MemoryMax=512M
CPUQuota=20%
```

#### NEW Inline (install.sh)
```systemd
WorkingDirectory=/opt/tvm-upload
ExecStart=/usr/bin/python3 -m src.main
ReadWritePaths=/var/lib/tvm-upload /var/log/tvm-upload ~/.ros/log ~/.parcel/log
ProtectSystem=strict
ProtectHome=read-only
```

**Differences:**
1. **Working directory**: OLD uses ~/tvm-upload, NEW uses /opt/tvm-upload
2. **Python path**: OLD uses venv, NEW uses system python3
3. **Environment variables**: OLD sets AWS_PROFILE, NEW doesn't (relies on config.yaml)
4. **Resource limits**: OLD has memory/CPU limits, NEW doesn't
5. **Security**: NEW has stricter protections (ProtectHome=read-only)

---

## Recommendations

### Critical Fixes Needed

1. **Add user log directory creation** to new install.sh:
```bash
# After Step 3 (Creating system directories)
step "Creating user log directories"

mkdir -p "$ACTUAL_HOME/.parcel/log/terminal"
mkdir -p "$ACTUAL_HOME/.ros/log"
mkdir -p "$ACTUAL_HOME/ros2_ws/log"

success "Created user log directories"
```

2. **Add permissions on user directories**:
```bash
# After creating user directories
chown -R "$ACTUAL_USER:$ACTUAL_USER" "$ACTUAL_HOME/.parcel"
chown -R "$ACTUAL_USER:$ACTUAL_USER" "$ACTUAL_HOME/.ros"
chown -R "$ACTUAL_USER:$ACTUAL_USER" "$ACTUAL_HOME/ros2_ws"

success "Set ownership on user directories"
```

3. **Add config backup** (before Step 5):
```bash
# Backup existing config if it exists
if [ -f "$CONFIG_DIR/config.yaml" ]; then
    BACKUP_FILE="$CONFIG_DIR/config.yaml.backup.$(date +%Y%m%d_%H%M%S)"
    cp "$CONFIG_DIR/config.yaml" "$BACKUP_FILE"
    warn "Backed up existing config to: $BACKUP_FILE"
fi
```

### Optional Improvements

1. **Add update mode**: Support `--update` flag to gracefully handle existing installations
2. **Add resource limits** to systemd service (MemoryMax, CPUQuota)
3. **Add environment variables** for AWS_PROFILE in service file
4. **Add service backup** before overwriting

---

## Which Script to Use?

### Use **OLD (install_systemd.sh)** if:
- You need to update an existing installation
- You run from git repository (not self-contained)
- You need config/service backups
- You use virtualenv

### Use **NEW (install.sh)** if:
- Fresh vehicle deployment
- You want pre-deployment validation
- You want self-contained installation in /opt
- You want enhanced security hardening
- You're okay with manually running uninstall.sh first for updates

### Recommended: Fix and use NEW script
The new script has better architecture (validation, verification, self-contained), but needs the missing features added.

---

**Generated:** 2025-10-28
