# TVM Log Upload System - Deployment Guide

**Version:** 2.7
**Last Updated:** 2025-11-10
**Target Audience:** Vehicle deployment technicians

---

## 📋 Overview

This guide provides **step-by-step instructions** for deploying the TVM log upload system to production vehicles. The deployment is **largely automated** using validation and installation scripts. Total time: approximately **5-10 minutes** per vehicle.

**Automation Scripts:**
- Pre-deployment validation automatically checks all prerequisites
- Installation script handles all system setup
- Health check script verifies successful deployment
- Diagnostic scripts troubleshoot issues.

---

##  Prerequisites


Complete these one-time setup tasks:

#### 1. AWS Account Setup (Organization-wide, ONE TIME)

✅ Create AWS China account
✅ Create S3 bucket: `t01logs` (or your chosen name)
✅ Create IAM user: `tvm-upload-service`
✅ Attach IAM policy (see below)
✅ Generate access keys (Access Key ID + Secret Access Key)

**Required IAM Policy:**
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:PutObject",
        "s3:GetObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws-cn:s3:::t01logs",
        "arn:aws-cn:s3:::t01logs/*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": [
        "cloudwatch:PutMetricData",
        "cloudwatch:PutMetricAlarm",
        "cloudwatch:DescribeAlarms"
      ],
      "Resource": "*"
    }
  ]
}
```

#### 2. S3 Bucket Setup

**One-time AWS S3 bucket creation:**

1. Log into AWS China Console: https://console.amazonaws.cn
2. Navigate to S3 service
3. Create bucket:
   - Name: `t01logs`
   - Region: `cn-north-1` (Beijing) or `cn-northwest-1` (Ningxia)
   - Block Public Access: **Enabled** (keep private)
   - Versioning: Optional
   - Encryption: Recommended (SSE-S3)

**Verify bucket access from laptop:**
```bash
aws s3 ls s3://t01logs --profile china --region cn-north-1
```



#### 3. Vehicle System Requirements

Before deploying to any vehicle, ensure the following prerequisites are met:

**System Requirements**

✅ **Operating System:** Ubuntu 22.04+ or Debian 11+
✅ **Python:** Python 3.10 or higher
✅ **Package Manager:** pip3 (Python package installer)
✅ **Network:** WiFi connectivity with access to AWS China regions
✅ **Disk Space:** Minimum 10GB free space
✅ **Permissions:** sudo/root access for systemd service installation

**Verify system prerequisites:**
```bash
# Check OS version
lsb_release -a

# Check Python version (must be 3.10+)
python3 --version

# Check pip3 is installed
pip3 --version

# Check network connectivity to AWS China
ping -c 3 s3.cn-north-1.amazonaws.com.cn

# Check available disk space
df -h /
```

**Expected outputs:**
- Ubuntu: 22.04 or higher
- Python: 3.10.x or higher
- pip3: any recent version (e.g., 22.0+)
- Network: Successful ping response
- Disk: At least 10GB available

#### Vehicle Information

Before installation, prepare:

1. **Vehicle ID** - Unique identifier for this vehicle
   - Format: `vehicle-CN-XXX` (e.g., `vehicle-CN-001`, `vehicle-CN-002`)
   - **IMPORTANT:** Must be unique across all vehicles!

2. **AWS Credentials** - Access Key ID and Secret Access Key (from AWS setup above)

---

## ⚡ Quick Deployment (Commands Only)

**Complete deployment in 8 steps - just copy and run:**

### Step 0: Environment Setup & Verification (REQUIRED - Run First!)

**This step prevents common deployment issues** including AWS CLI conflicts, Python version mismatches, and dependency problems.

```bash
# ============================================================
# STEP 0: ENVIRONMENT SETUP & VERIFICATION
# ============================================================
# Run these commands FIRST before proceeding with installation
# This prevents 90% of common deployment issues!
# ============================================================

# Check Python version (must be 3.10+)
python3 --version
# Expected: Python 3.10.x or higher

# Check pip3 is installed
pip3 --version
# Expected: pip 22.x or higher

# Check disk space (need at least 10GB free)
df -h / | grep -E '^/|Avail'
# Expected: At least 10GB available

# Check network connectivity to AWS China
ping -c 3 s3.cn-north-1.amazonaws.com.cn
# Expected: Successful ping responses

# ============================================================
# CRITICAL: AWS CLI CONFLICT DETECTION & RESOLUTION
# ============================================================
# This is the MOST COMMON issue - version conflicts between
# system AWS CLI and user-installed boto3/botocore packages
# ============================================================

# Step 0a: Check for AWS CLI version conflicts
echo "Checking AWS CLI installation..."
which -a aws 2>/dev/null || echo "AWS CLI not found (will be installed)"

# Step 0b: Check for conflicting package installations
echo ""
echo "Checking for package conflicts..."
pip3 list | grep -E "(awscli|boto)" 2>/dev/null || echo "No user boto packages found"
dpkg -l 2>/dev/null | grep -E "awscli|python3-boto" || echo "No system AWS packages found"

# Step 0c: RESOLVE CONFLICTS (if any were found above)
# If you see BOTH system packages (dpkg) AND user packages (pip3 list),
# you have a conflict that MUST be resolved:

# Option 1: Remove system AWS CLI and use user installation (RECOMMENDED)
# Uncomment these lines if you have sudo access:
# sudo apt remove -y awscli python3-botocore
# pip3 install --user --upgrade awscli

# Option 2: Use local AWS CLI only (if no sudo access)
# This upgrades your local installation to match boto3:
pip3 install --user --upgrade awscli

# Step 0d: Verify AWS CLI works after conflict resolution
echo ""
echo "Verifying AWS CLI installation..."
aws --version
# Expected: aws-cli/1.40+ with matching botocore version
# Example: aws-cli/1.42.69 Python/3.10.12 Linux/6.8.0-87-generic botocore/1.40.69

# Step 0e: Ensure local AWS CLI takes precedence
echo ""
echo "AWS CLI location:"
which aws
# Expected: /home/YOUR_USERNAME/.local/bin/aws (user installation)
# If you see /usr/bin/aws, your PATH may need adjustment

# ============================================================
# VERIFICATION SUMMARY
# ============================================================
echo ""
echo "Environment Setup Summary:"
echo "-------------------------"
echo "Python version: $(python3 --version)"
echo "pip3 version: $(pip3 --version | cut -d' ' -f2)"
echo "AWS CLI version: $(aws --version 2>&1 | cut -d' ' -f1)"
echo "Disk space: $(df -h / | awk 'NR==2 {print $4}')"
echo ""
echo "If all checks above passed, proceed to Step 1!"
echo "If any check failed, fix the issue before continuing."
echo "-------------------------"
```

**Common Issues & Solutions:**

| Issue | Symptom | Solution |
|-------|---------|----------|
| AWS CLI conflict | `KeyError: 'opsworkscm'` when running `aws configure` | Run Step 0c to upgrade local AWS CLI |
| Old Python | `Python 3.8` or lower | Upgrade to Python 3.10+ or use different system |
| Missing pip3 | `pip3: command not found` | Install: `sudo apt install python3-pip` |
| Network issues | Cannot ping AWS China | Check WiFi/firewall settings |
| Disk space low | Less than 10GB free | Clean up disk space or use different partition |

**Why This Step Matters:**

The most common deployment failure is the AWS CLI conflict you just experienced:
- System package managers (apt) install older AWS CLI versions
- Python pip installs newer boto3/botocore for your project
- These versions clash, causing cryptic errors like `KeyError: 'opsworkscm'`
- Step 0c resolves this by ensuring compatible versions

**Expected Time:** 2-3 minutes

---

```bash
# Step 1: Clone repository
cd ~ && git clone git@github.com:Futu-reADS/tvm-upload.git && cd tvm-upload

# Step 2: Install dependencies
make install
# OR: pip3 install -e .

# Step 3: Configure AWS credentials
aws configure --profile china
# Enter: Access Key ID, Secret Key, region: cn-north-1, output: json
aws configure set s3.endpoint_url https://s3.cn-north-1.amazonaws.com.cn --profile china
aws configure set s3.signature_version s3v4 --profile china
aws configure set s3.addressing_style path --profile china

# Step 4: Configure system
cp config/config.yaml.example config/config.yaml
nano config/config.yaml  # Edit vehicle_id and verify settings

# Step 5: Verify deployment prerequisites
make deploy-verify
# OR: ./scripts/deployment/verify_deployment.sh

# Step 6: Install to production
make deploy-install
# OR: sudo ./scripts/deployment/install.sh

# Step 7: Verify installation
make deploy-health
# OR: sudo ./scripts/deployment/health_check.sh
```

**Done! System is running as systemd service.**

Check status: `sudo systemctl status tvm-upload`

---

## 🚗 Per-Vehicle Deployment (Detailed)

**Deployment Overview:**

**Required Steps (System Setup):**
1. Clone repository to vehicle
2. Install Python dependencies
3. Configure AWS credentials
4. Configure system (config.yaml)
5. Run pre-deployment validation script
6. **Install system (automated script)** ← System is now running!

**Optional Steps (Verification - Recommended but not mandatory):**
7. Run health check script (verify installation)
8. Verify first upload (confirm S3 connectivity)

**Key Scripts:**
- `./scripts/diagnostics/verify_aws_credentials.sh` - Comprehensive AWS verification
- `./scripts/deployment/verify_deployment.sh` - Pre-deployment validation
- `./scripts/deployment/install.sh` - Automated installation
- `./scripts/deployment/health_check.sh` - Post-deployment health check
- `./scripts/deployment/uninstall.sh` - Complete removal

---

### Step 0: Environment Setup & Verification (REQUIRED)

**⚠️ CRITICAL: Run this step FIRST before any installation!**

This step detects and resolves common environment issues that cause 90% of deployment failures, including the AWS CLI version conflict issue.

#### 0.1 Basic System Verification

```bash
# Check Python version (must be 3.10+)
python3 --version
```
**Expected:** `Python 3.10.x` or higher

```bash
# Check pip3 is installed
pip3 --version
```
**Expected:** `pip 22.x` or higher

```bash
# Check disk space
df -h /
```
**Expected:** At least 10GB available

```bash
# Check network connectivity to AWS China
ping -c 3 s3.cn-north-1.amazonaws.com.cn
```
**Expected:** Successful ping responses

**If any check fails:**
- Python too old: Upgrade to Python 3.10+ or use different system
- pip3 missing: Install with `sudo apt install python3-pip`
- Disk space low: Clean up disk or use different partition
- Network issues: Check WiFi/firewall settings

---

#### 0.2 AWS CLI Conflict Detection & Resolution

**⚠️ MOST COMMON ISSUE:** This is the error you likely encountered - version conflicts between system AWS CLI and user boto3 packages.

**Step 1: Check for conflicts**

```bash
# Check AWS CLI installations
which -a aws
```

**Step 2: Check package versions**

```bash
# Check user-installed packages (pip3)
pip3 list | grep -E "(awscli|boto)"

# Check system-installed packages (apt)
dpkg -l | grep -E "awscli|python3-boto"
```

**Step 3: Identify the conflict**

**You have a conflict if:**
- `which -a aws` shows multiple locations (e.g., `/usr/bin/aws` AND `/home/user/.local/bin/aws`)
- `pip3 list` shows boto/awscli packages (e.g., `botocore 1.40.69`)
- `dpkg -l` shows system AWS packages (e.g., `awscli 1.22.34`)

**Example conflict output:**
```
# pip3 list shows:
awscli       1.22.34
boto3        1.40.69
botocore     1.40.69

# dpkg -l shows:
ii  awscli           1.22.34-1
ii  python3-botocore 1.23.34+repack-1
```

This mismatch causes errors like: `KeyError: 'opsworkscm'`

**Step 4: Resolve the conflict**

**Option A: Remove system packages (RECOMMENDED - requires sudo):**

```bash
sudo apt remove -y awscli python3-botocore
pip3 install --user --upgrade awscli
```

**Option B: Upgrade local installation (no sudo required):**

```bash
pip3 install --user --upgrade awscli
```

This ensures your local AWS CLI matches your boto3 version.

**Step 5: Verify the fix**

```bash
# Check AWS CLI version
aws --version
```
**Expected:** `aws-cli/1.40+` with matching botocore
**Example:** `aws-cli/1.42.69 Python/3.10.12 Linux/6.8.0-87-generic botocore/1.40.69`

```bash
# Check AWS CLI location
which aws
```
**Expected:** `/home/YOUR_USERNAME/.local/bin/aws` (user installation)

**Step 6: Test AWS CLI works**

```bash
aws help
```
**Expected:** No errors, shows help text

**If you still see errors:**
1. Restart your terminal session (to reload PATH)
2. Run `hash -r` to clear bash command cache
3. Verify PATH includes `~/.local/bin`: `echo $PATH`

---

#### 0.3 Environment Summary

Run this to see a complete summary:

```bash
echo "Environment Setup Summary:"
echo "-------------------------"
echo "Python: $(python3 --version)"
echo "pip3: $(pip3 --version | cut -d' ' -f2)"
echo "AWS CLI: $(aws --version 2>&1)"
echo "AWS location: $(which aws)"
echo "Disk free: $(df -h / | awk 'NR==2 {print $4}')"
echo "-------------------------"
```

**All checks passed?** ✅ Proceed to Step 1!

**Any check failed?** ❌ Fix the issue before continuing - deployment will fail otherwise.

---

### Step 1: Clone Repository

On the vehicle:

```bash
# Navigate to home directory
cd ~

# Clone repository (if not already present)
git clone git@github.com:Futu-reADS/tvm-upload.git

# Enter project directory
cd tvm-upload

# Switch to deployment branch
git checkout main
```

If repository already exists:
```bash
cd ~/tvm-upload
git pull origin main
```

---

### Step 2: Install Dependencies

**Main Method - Direct Installation:**

```bash
cd ~/tvm-upload

# Install dependencies (reads from pyproject.toml)
pip3 install -e .

# Verify installation
python3 -c "import boto3, yaml, watchdog; print('✓ Dependencies installed')"
```

**Expected output:** `✓ Dependencies installed`

---

<details>
<summary><b>📌 Alternative Method: Virtual Environment (click to expand)</b></summary>

<br>

**Use this if the main installation fails or you prefer isolated dependencies:**

```bash
cd ~/tvm-upload

# Create virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate

# Install dependencies (reads from pyproject.toml)
pip3 install -e .

# Verify installation
python3 -c "import boto3, yaml, watchdog; print('✓ Dependencies installed')"
```

**Note:** If using virtual environment, you'll need to activate it before running any commands:
```bash
source ~/tvm-upload/venv/bin/activate
```

</details>

---

### Step 3: Configure AWS Credentials

**✅ Recommended Method - Interactive Setup:**

**Step 1: Configure basic credentials (interactive):**
```bash
aws configure --profile china
```

Enter when prompted:
- **AWS Access Key ID:** `YOUR_ACCESS_KEY_ID_HERE`
- **AWS Secret Access Key:** `YOUR_SECRET_ACCESS_KEY_HERE`
- **Default region:** `cn-north-1`
- **Default output format:** `json`

**Step 2: Add S3-specific settings for AWS China (required):**
```bash
aws configure set s3.endpoint_url https://s3.cn-north-1.amazonaws.com.cn --profile china
aws configure set s3.signature_version s3v4 --profile china
aws configure set s3.addressing_style path --profile china
```

---

<details>
<summary><b>📌 Alternative Method 1: All-in-One Commands (for scripting/automation - click to expand)</b></summary>

<br>

**Use this for automated deployments or scripting:**

```bash
aws configure set aws_access_key_id YOUR_ACCESS_KEY_ID_HERE --profile china
aws configure set aws_secret_access_key YOUR_SECRET_ACCESS_KEY_HERE --profile china
aws configure set region cn-north-1 --profile china
aws configure set output json --profile china
aws configure set s3.endpoint_url https://s3.cn-north-1.amazonaws.com.cn --profile china
aws configure set s3.signature_version s3v4 --profile china
aws configure set s3.addressing_style path --profile china
```

**Advantage:** Single block of commands, easier to automate.

</details>

---

<details>
<summary><b>📌 Alternative Method 2: Manual File Editing (for advanced users - click to expand)</b></summary>

<br>

**Use this if you prefer direct file editing or AWS CLI is not available:**

**Step 1: Create credentials file:**
```bash
mkdir -p ~/.aws
nano ~/.aws/credentials
```

Add the following content:
```ini
[china]
aws_access_key_id = YOUR_ACCESS_KEY_ID_HERE
aws_secret_access_key = YOUR_SECRET_ACCESS_KEY_HERE
```

Save and exit: `Ctrl+X`, `Y`, `Enter`

**Step 2: Create config file:**
```bash
nano ~/.aws/config
```

Add the following content:
```ini
[profile china]
region = cn-north-1
output = json
s3 =
    endpoint_url = https://s3.cn-north-1.amazonaws.com.cn
    signature_version = s3v4
    addressing_style = path
```

Save and exit: `Ctrl+X`, `Y`, `Enter`

**Advantage:** Direct control over configuration files, works without AWS CLI.

</details>

---

**Verify AWS Credentials (required for all methods):**
```bash
./scripts/diagnostics/verify_aws_credentials.sh
```

This script verifies:
- AWS CLI installation
- Credentials file and profile configuration
- AWS identity (STS check)
- S3 bucket access and write permissions
- CloudWatch permissions

**Expected output:** All tests pass with ✓ marks. If any test fails, fix the issue before proceeding.

---

### Step 4: Configure System

#### 4.1 Copy Configuration Template

```bash
cp config/config.yaml.example config/config.yaml
```

#### 4.2 Edit Configuration

```bash
nano config/config.yaml
```

**Minimum required changes:**

1. **Set vehicle_id** (Line ~18):
   ```yaml
   vehicle_id: "vehicle-CN-001"  # ← CHANGE THIS!
   ```

2. **Verify S3 bucket** (Line ~79):
   ```yaml
   s3:
     bucket: t01logs  # ← Verify this matches your bucket
     region: cn-north-1
     profile: china
   ```

**Optional changes** (advanced):
- Upload schedule (line ~106): Change from `interval` mode to `daily` if needed
- Deletion policy (line ~278): Adjust `keep_days` (default: 14)
- Operational hours (line ~153): Adjust upload time window

Save and exit: `Ctrl+X`, `Y`, `Enter`

#### 4.3 Configure System Logrotate (Required ONLY if monitoring /var/log/syslog)

**⚠️ Skip this step if you are NOT monitoring system logs (/var/log/syslog)**

**Why this is needed:** System logs rotate weekly by default, but TVM scans files < 3 days old. Weekly rotation means you lose 4+ days of logs.

**Solution:** Change logrotate to daily rotation:

```bash
sudo nano /etc/logrotate.d/rsyslog
```

Find the `/var/log/syslog` section and change `weekly` to `daily`:

```
/var/log/syslog {
    daily           # ← Change from 'weekly' to 'daily'
    rotate 7        # Keep 7 days of logs
    missingok
    notifempty
    delaycompress
    compress
    postrotate
        /usr/lib/rsyslog/rsyslog-rotate
    endscript
}
```

Save and exit: `Ctrl+X`, `Y`, `Enter`

**Note:** The new rotation schedule will take effect on the next scheduled rotation (typically daily at 6:25 AM). For testing purposes, see Appendix A for how to trigger immediate rotation.

---

### Step 5: Pre-Deployment Validation

**IMPORTANT:** Run comprehensive validation before installing:

```bash
./scripts/deployment/verify_deployment.sh
```

**This script checks:**
- ✓ Configuration file exists and is valid
- ✓ Vehicle ID, S3 bucket, AWS region configured
- ✓ AWS credentials file and profile exist
- ✓ AWS connectivity and permissions (S3 + CloudWatch)
- ✓ Python version (>= 3.8), pip3, disk space (>= 100GB)
- ✓ Log directories exist or will be created
- ✓ Network connectivity to AWS China endpoints
- ✓ Vehicle ID uniqueness check in S3
- ✓ Python dependencies (boto3, watchdog, PyYAML)
- ✓ systemd availability

**Expected result:** `[PASS] Environment ready for deployment ✓`

**If validation fails:**
- ✗ Red errors: MUST be fixed before proceeding
- ⚠ Yellow warnings: Review but may proceed

---

### Step 6: Install System

**One-command installation:**

```bash
sudo ./scripts/deployment/install.sh
```

This will:
1. ✓ Validate pre-requisites
2. ✓ Install Python dependencies
3. ✓ Create system directories
4. ✓ Copy application files
5. ✓ Configure systemd service
6. ✓ Start service
7. ✓ Verify installation

**Expected output:**
```
╔════════════════════════════════════════════════════════════════╗
║  TVM Log Upload - Production Installation                     ║
╔════════════════════════════════════════════════════════════════╗

[1/8] Running pre-deployment validation
      ✓ Environment validated

[2/8] Installing Python dependencies
      ✓ Python dependencies installed

[3/8] Creating system directories
      ✓ Created: /opt/tvm-upload
      ✓ Created: /var/lib/tvm-upload
      ✓ Created: /var/log/tvm-upload
      ✓ Created: /etc/tvm-upload

[4/8] Copying application files
      ✓ Application files copied

[5/8] Configuring system settings
      ✓ Config copied to /etc/tvm-upload/config.yaml
      ✓ Replaced USER with actual username
      ✓ Updated data paths

[6/8] Installing systemd service
      ✓ Service file created
      ✓ systemd reloaded
      ✓ Service enabled (auto-start on boot)

[7/8] Starting tvm-upload service
      ✓ Service started
      ℹ Waiting for service to stabilize (30 seconds)...

[8/8] Verifying installation
      ✓ Service is running
      ✓ No errors in recent logs

════════════════════════════════════════════════════════════════
✓ Installation Successful!
════════════════════════════════════════════════════════════════

Vehicle Information:
  Vehicle ID:      vehicle-CN-001
  Service Status:  Active (running)
  Installation:    /opt/tvm-upload
  Configuration:   /etc/tvm-upload/config.yaml
  Data Directory:  /var/lib/tvm-upload

Next Steps:
  1. Monitor logs:       journalctl -u tvm-upload -f
  2. Check health:       sudo ./scripts/deployment/health_check.sh
  3. View S3 uploads:    aws s3 ls s3://t01logs/vehicle-CN-001/

Useful Commands:
  Start service:   sudo systemctl start tvm-upload
  Stop service:    sudo systemctl stop tvm-upload
  Restart service: sudo systemctl restart tvm-upload
  View status:     sudo systemctl status tvm-upload
  Edit config:     sudo nano /etc/tvm-upload/config.yaml
  Reload config:   sudo systemctl reload tvm-upload

════════════════════════════════════════════════════════════════
```

**Installation takes:** ~2-3 minutes

**What happens after installation:**
- Service starts monitoring log directories immediately
- Existing logs (created within last 3 days) are scanned and queued
- Files upload immediately if within operational hours (09:00-16:00)
- Files upload at next scheduled interval (default: every 2 hours) if outside operational hours
- File stability period (60 seconds) must elapse before any upload

---

### Step 7: Verify Deployment (Optional - Recommended)

> **✅ System Setup Complete!** After Step 6, the TVM upload system is installed and running.
>
> **This step is optional but recommended** to verify the installation was successful. You can skip this and proceed to production, or run this health check for peace of mind.

**Run health check script:**

```bash
sudo ./scripts/deployment/health_check.sh
```

**This script checks:**
- ✓ Service status and uptime
- ✓ Recent errors in logs (last 24 hours)
- ✓ Recent uploads count and last upload time
- ✓ Queue file status and pending files count
- ✓ Registry file status and tracked files count
- ✓ Disk usage percentage and available space
- ✓ S3 connectivity and recent uploads
- ✓ Configuration file and critical settings

**Expected result:** `[PASS] System is healthy ✓` or `[WARN] System is working with minor issues`

**Note:** Warnings are normal for fresh installation (no files uploaded yet).

---

### Step 8: Verify First Upload (Optional - For Testing Only)

> **This step is optional** and intended for testing/verification purposes only.
>
> **Skip this in production** - The system will automatically upload real log files when they're created. You don't need to manually test unless troubleshooting.

**If you want to test, create a test file:**

```bash
echo "Test upload $(date)" > ~/.parcel/log/terminal/test.log
```

**Wait 2-3 minutes**, then check S3:

```bash
aws s3 ls s3://t01logs/vehicle-CN-001/ --recursive --profile china --region cn-north-1
```

**Expected output:**
```
2025-01-27 14:35:22    25 vehicle-CN-001/2025-01-27/terminal/test.log
```

**If file appears:** ✅ Deployment successful!

**If file doesn't appear:**
1. Check service logs: `journalctl -u tvm-upload -n 100`
2. Verify file stability period (60 seconds by default)
3. Check operational hours configuration

---

## 🔧 Post-Deployment

### Monitor Service

**Check system health (recommended):**
```bash
sudo ./scripts/deployment/health_check.sh
```

**View real-time logs:**
```bash
journalctl -u tvm-upload -f
```

**View recent logs:**
```bash
journalctl -u tvm-upload -n 100
```

**Check service status:**
```bash
sudo systemctl status tvm-upload
```

### Useful Commands

| Task | Command |
|------|---------|
| Start service | `sudo systemctl start tvm-upload` |
| Stop service | `sudo systemctl stop tvm-upload` |
| Restart service | `sudo systemctl restart tvm-upload` |
| View status | `sudo systemctl status tvm-upload` |
| View logs | `journalctl -u tvm-upload -f` |
| Health check | `sudo ./scripts/deployment/health_check.sh` |
| Edit config | `sudo nano /etc/tvm-upload/config.yaml` |
| Reload config | `sudo systemctl reload tvm-upload` |

### View Uploaded Files

**List all files for this vehicle:**
```bash
aws s3 ls s3://t01logs/vehicle-CN-001/ --recursive --profile china --region cn-north-1
```

**List files from specific date:**
```bash
aws s3 ls s3://t01logs/vehicle-CN-001/2025-01-27/ --recursive --profile china --region cn-north-1
```

**Download all logs:**
```bash
aws s3 sync s3://t01logs/vehicle-CN-001/ ./downloaded-logs/ --profile china --region cn-north-1
```

---

## 🚨 Troubleshooting

**First step for any issue:**
```bash
sudo ./scripts/deployment/health_check.sh
```
This will identify most common problems automatically.

---

### Problem: AWS CLI errors (KeyError: 'opsworkscm' or similar)

**Symptoms:**
- `aws configure` command fails with `KeyError: 'opsworkscm'`
- Traceback showing `/usr/bin/aws` and `/home/user/.local/lib/python3.10/site-packages/botocore`
- Version mismatch between AWS CLI and botocore

**Root cause:** Conflict between system-installed AWS CLI (old version) and user-installed botocore (new version).

**Diagnose:**
```bash
# Check for multiple AWS CLI installations
which -a aws

# Check versions
pip3 list | grep -E "(awscli|boto)"
dpkg -l | grep -E "awscli|python3-boto"
```

**Solution:**
```bash
# Upgrade local AWS CLI to match boto3
pip3 install --user --upgrade awscli

# Verify fix
aws --version
which aws  # Should show ~/.local/bin/aws

# Test it works
aws help
```

**If still failing:**
```bash
# Restart terminal to reload PATH
# Or clear bash command cache
hash -r

# If you have sudo access, remove system packages entirely:
sudo apt remove -y awscli python3-botocore
pip3 install --user --upgrade awscli
```

**Prevention:** Always run Step 0 (Environment Setup & Verification) before deployment!

---

### Problem: Service won't start

**Diagnose:**
```bash
sudo ./scripts/deployment/health_check.sh
journalctl -u tvm-upload -n 50
```

**Common causes:**
- Missing AWS credentials
- Invalid configuration
- Python dependencies not installed

**Solution:**
```bash
# Re-run validation
./scripts/deployment/verify_deployment.sh

# If validation fails, fix issues then reinstall
sudo ./scripts/deployment/uninstall.sh
sudo ./scripts/deployment/install.sh
```

---

### Problem: No files uploading to S3

**Diagnose:**
```bash
sudo ./scripts/deployment/health_check.sh
```

**Common causes:**
- Operational hours restriction (default: 09:00-16:00)
- File stability period not elapsed (60 seconds)
- No new files in monitored directories

**Solution:**
```bash
# Check operational hours
grep -A 5 "operational_hours:" /etc/tvm-upload/config.yaml

# Create test file and wait 90 seconds
echo "test" > ~/.parcel/log/terminal/test-$(date +%s).log
sleep 90
journalctl -u tvm-upload -n 20
```

---

### Problem: AWS credentials issues

**Diagnose:**
```bash
./scripts/diagnostics/verify_aws_credentials.sh
```

This script tests all AWS permissions comprehensively. Fix any ✗ errors shown.

---

### Problem: Syslog uploading in infinite loop

**Symptoms:**
- Logs show syslog uploading every 60 seconds repeatedly
- Upload succeeds but immediately retries
- Other directories (terminal, ros) not uploading
- Warning: `✗ Upload failed, NOT marking as processed: syslog`

**Root cause:** Active syslog file is constantly being written to by the system, triggering re-uploads.

**Solution:**
```bash
# Edit config to only monitor rotated syslogs
sudo nano /etc/tvm-upload/config.yaml
```

Change syslog configuration:
```yaml
log_directories:
  - path: /var/log
    source: syslog
    pattern: "syslog.[1-9]*"  # Only rotated files, NOT active syslog
    recursive: false
```

Then reload:
```bash
sudo systemctl reload tvm-upload
```

**Verify fix:**
```bash
# Should show other directories uploading now
journalctl -u tvm-upload -f
```

**Additional step:** Ensure daily logrotate (see Step 4.3) so rotated files are captured within 3-day scan window.

---

### Problem: Disk full

**Diagnose:**
```bash
sudo ./scripts/deployment/health_check.sh
df -h /
```

**Solution:**
```bash
# Enable aggressive deletion
sudo nano /etc/tvm-upload/config.yaml
# Set: deletion.after_upload.keep_days: 0
# Set: deletion.emergency.enabled: true
sudo systemctl reload tvm-upload
```

---

## 🔄 Updating Configuration

After changing configuration:

```bash
# Edit config
sudo nano /etc/tvm-upload/config.yaml

# Reload service (doesn't restart, just reloads config)
sudo systemctl reload tvm-upload

# Or restart service (stops and starts)
sudo systemctl restart tvm-upload
```

**Note:** SIGHUP signal (`reload`) reloads config without interrupting uploads.

---

## 🗑️ Uninstallation

### Keep Data (Preserve Queue and Registry)

```bash
sudo ./scripts/deployment/uninstall.sh --keep-data
```

This removes:
- ✓ Service
- ✓ Installation files

But preserves:
- ✓ Configuration
- ✓ Queue
- ✓ Registry
- ✓ Logs

### Complete Removal

```bash
sudo ./scripts/deployment/uninstall.sh
```

This removes **everything** including data.

---

## 📊 Monitoring & Maintenance

### CloudWatch Metrics

Enable CloudWatch metrics in configuration:

```yaml
monitoring:
  cloudwatch_enabled: true
  publish_interval_seconds: 3600
```

**Available metrics:**
- `BytesUploaded` - Total bytes uploaded
- `FileCount` - Number of files uploaded
- `FailureCount` - Number of failed uploads
- `DiskUsagePercent` - Current disk usage

**View metrics:**
```bash
aws cloudwatch get-metric-statistics \
  --namespace TVM/Upload \
  --metric-name BytesUploaded \
  --dimensions Name=VehicleId,Value=vehicle-CN-001 \
  --start-time 2025-01-27T00:00:00Z \
  --end-time 2025-01-27T23:59:59Z \
  --period 3600 \
  --statistics Sum \
  --profile china --region cn-north-1
```

---

## 📝 Deployment Checklist

Use this checklist when deploying to a vehicle:

- [ ] **Step 0: Environment verified** (Python 3.10+, pip3, disk space, network)
- [ ] **Step 0: AWS CLI conflicts resolved** (no version mismatches)
- [ ] AWS credentials configured (`~/.aws/credentials` + `~/.aws/config`)
- [ ] AWS credentials verified (`./scripts/diagnostics/verify_aws_credentials.sh`)
- [ ] Repository cloned and dependencies installed
- [ ] Configuration file created with unique vehicle ID
- [ ] Pre-deployment validation passed (`./scripts/deployment/verify_deployment.sh`)
- [ ] Installation completed (`./scripts/deployment/install.sh`)
- [ ] Health check passed (`./scripts/deployment/health_check.sh`)
- [ ] Test file uploaded to S3
- [ ] Documented vehicle ID in inventory

---

## 📞 Support

**Common Issues:**
- Check logs: `journalctl -u tvm-upload -f`
- Run health check: `sudo ./scripts/deployment/health_check.sh`
- Review configuration: `/etc/tvm-upload/config.yaml`

**For Help:**
- GitHub Issues: https://github.com/Futu-reADS/tvm-upload/issues
- Documentation: `/docs` directory

---

## 📚 Appendix

### Appendix A: Force Immediate Logrotate (Testing Only)

> **⚠️ This is for testing purposes only** - Not required for production deployment.
>
> By default, logrotate runs on its scheduled time (typically daily at 6:25 AM). The configuration changes in Step 4.3 will take effect on the next scheduled run.

**If you need to test logrotate immediately** (e.g., during deployment testing):

```bash
# Force immediate rotation of rsyslog
sudo logrotate -f /etc/logrotate.d/rsyslog

# Verify rotation occurred
ls -lh /var/log/syslog*
```

**Expected output:**
```
-rw-r----- 1 syslog adm    0 Nov  5 14:30 /var/log/syslog
-rw-r----- 1 syslog adm  15K Nov  5 14:29 /var/log/syslog.1
-rw-r----- 1 syslog adm  12K Nov  4 06:25 /var/log/syslog.2.gz
-rw-r----- 1 syslog adm  10K Nov  3 06:25 /var/log/syslog.3.gz
```

**When to use this:**
- During initial deployment testing to verify syslog upload works
- When troubleshooting syslog upload issues
- When you want to test the system immediately without waiting for scheduled rotation

**When NOT to use this:**
- In production (let rotation happen naturally)
- For regular operations (automatic rotation is sufficient)

---

**Version:** 2.7
**Last Updated:** 2025-11-10

### Changelog
- **v2.7** (2025-11-10): **CRITICAL UPDATE** - Added comprehensive Step 0: Environment Setup & Verification to prevent AWS CLI conflicts (KeyError: 'opsworkscm'), Python version issues, and dependency conflicts. Added detailed troubleshooting for AWS CLI version mismatches. Updated deployment checklist and quick deployment guide.
- **v2.6** (2025-11-05): Clarified Steps 7 & 8 as optional verification (not mandatory setup), moved immediate logrotate command to Appendix A (testing only), improved deployment overview
- **v2.5** (2025-11-05): Improved formatting - alternate methods now use collapsible sections for clearer main vs. alternative paths
- **v2.4** (2025-11-05): Added detailed system prerequisites (Python 3.10+, pip3, Ubuntu 22.04+, WiFi), moved vehicle info to prerequisites, renumbered all steps
- **v2.3** (2025-11-05): Added scan_existing_files documentation, 2-minute threshold startup scan fix
- **v2.2** (2025-10-31): Previous version
