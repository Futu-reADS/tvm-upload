# TVM Log Upload System - Deployment Guide

**Version:** 2.2
**Last Updated:** 2025-10-31
**Target Audience:** Vehicle deployment technicians

---

## 📋 Overview

This guide provides **step-by-step instructions** for deploying the TVM log upload system to production vehicles. The deployment is **largely automated** using validation and installation scripts. Total time: approximately **5-10 minutes** per vehicle.

**Automation Scripts:**
- Pre-deployment validation automatically checks all prerequisites
- Installation script handles all system setup
- Health check script verifies successful deployment
- Diagnostic scripts troubleshoot issues

---

## ⚠️ Prerequisites

### Before Visiting Vehicle

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

---

## 🚗 Per-Vehicle Deployment

**Deployment Overview:**
1. Prepare vehicle information (vehicle ID)
2. Clone repository and install dependencies
3. Configure AWS credentials (manual + verification script)
4. Configure system (config.yaml)
5. **Run pre-deployment validation script**
6. Install system (automated script)
7. **Run health check script**
8. Verify first upload

**Key Scripts:**
- `./scripts/diagnostics/verify_aws_credentials.sh` - Comprehensive AWS verification
- `./scripts/deployment/verify_deployment.sh` - Pre-deployment validation
- `./scripts/deployment/install.sh` - Automated installation
- `./scripts/deployment/health_check.sh` - Post-deployment health check
- `./scripts/deployment/uninstall.sh` - Complete removal

---

### Step 1: Prepare Vehicle Information

Before installation, decide:

1. **Vehicle ID** - Unique identifier for this vehicle
   - Format: `vehicle-CN-XXX` (e.g., `vehicle-CN-001`, `vehicle-CN-002`)
   - **IMPORTANT:** Must be unique across all vehicles!

2. **Network** - Ensure vehicle has WiFi connectivity to AWS China

---

### Step 2: Clone Repository

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

### Step 3: Install Dependencies

Install Python dependencies using requirements.txt:

```bash
cd ~/tvm-upload

# Install dependencies
pip3 install -r requirements.txt

# Verify installation
python3 -c "import boto3, yaml, watchdog; print('✓ Dependencies installed')"
```

**Expected output:** `✓ Dependencies installed`

**If installation fails:**
```bash
# Use virtual environment
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

---

### Step 4: Configure AWS Credentials

**Recommended: Interactive setup + S3 configuration**

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

**Alternative: All-in-one commands (for scripting/automation):**
```bash
aws configure set aws_access_key_id YOUR_ACCESS_KEY_ID_HERE --profile china
aws configure set aws_secret_access_key YOUR_SECRET_ACCESS_KEY_HERE --profile china
aws configure set region cn-north-1 --profile china
aws configure set output json --profile china
aws configure set s3.endpoint_url https://s3.cn-north-1.amazonaws.com.cn --profile china
aws configure set s3.signature_version s3v4 --profile china
aws configure set s3.addressing_style path --profile china
```

---

**Alternative: Manual file editing:**

Create `~/.aws/credentials`:
```bash
mkdir -p ~/.aws
nano ~/.aws/credentials
```
```ini
[china]
aws_access_key_id = YOUR_ACCESS_KEY_ID_HERE
aws_secret_access_key = YOUR_SECRET_ACCESS_KEY_HERE
```

Create `~/.aws/config`:
```bash
nano ~/.aws/config
```
```ini
[profile china]
region = cn-north-1
output = json
s3 =
    endpoint_url = https://s3.cn-north-1.amazonaws.com.cn
    signature_version = s3v4
    addressing_style = path
```

---

**Verify AWS credentials:**
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

### Step 5: Configure System

#### 5.1 Copy Configuration Template

```bash
cp config/config.yaml.example config/config.yaml
```

#### 5.2 Edit Configuration

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

---

### Step 6: Pre-Deployment Validation

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

### Step 7: Install System

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

### Step 8: Verify Deployment

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

### Step 9: Verify First Upload

**Create a test file:**

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

**Last Updated:** 2025-10-31
**Version:** 2.2
