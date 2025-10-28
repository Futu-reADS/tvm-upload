# TVM Log Upload System - Deployment Guide

**Version:** 2.1
**Last Updated:** 2025-01-27
**Target Audience:** Vehicle deployment technicians

---

## 📋 Overview

This guide provides **step-by-step instructions** for deploying the TVM log upload system to production vehicles. The installation takes approximately **5-10 minutes** per vehicle.

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

#### 2. AWS CLI Configuration

On your laptop (for verification):
```bash
aws configure --profile china
# Enter:
#   AWS Access Key ID: <your-key-id>
#   AWS Secret Access Key: <your-secret-key>
#   Default region: cn-north-1
#   Default output format: json
```

Verify access:
```bash
aws s3 ls s3://t01logs --profile china --region cn-north-1
```

---

## 🚗 Per-Vehicle Deployment

### Step 1: Prepare Vehicle Information

Before installation, decide:

1. **Vehicle ID** - Unique identifier for this vehicle
   - Format: `vehicle-CN-XXX` (e.g., `vehicle-CN-001`, `vehicle-CN-002`)
   - **IMPORTANT:** Must be unique across all vehicles!

2. **Log Directories** - Paths to monitor (check these exist):
   - Terminal logs: `/home/USER/.parcel/log/terminal`
   - ROS logs: `/home/USER/.ros/log`
   - System logs: `/var/log`
   - ROS2 logs: `/home/USER/ros2_ws/log`

3. **Network** - Ensure vehicle has:
   - WiFi connectivity
   - Access to AWS China endpoints (`.amazonaws.com.cn`)

---

### Step 2: Clone Repository

On the vehicle:

```bash
# Navigate to home directory
cd ~

# Clone repository (if not already present)
git clone https://github.com/your-org/tvm-upload.git

# Enter project directory
cd tvm-upload
```

If repository already exists:
```bash
cd ~/tvm-upload
git pull origin main
```

---

### Step 3: Configure AWS Credentials

Set up AWS credentials on the vehicle:

```bash
aws configure --profile china
```

Enter the shared credentials:
- **AWS Access Key ID:** `<your-access-key-id>`
- **AWS Secret Access Key:** `<your-secret-access-key>`
- **Default region:** `cn-north-1`
- **Default output format:** `json`

**Verify connectivity:**
```bash
aws s3 ls s3://t01logs --profile china --region cn-north-1
```

You should see bucket contents or an empty response (not an error).

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

3. **Verify log directories** (Lines ~54-73):
   ```yaml
   log_directories:
     - path: /home/USER/.parcel/log/terminal  # ← USER will be auto-replaced
       source: terminal
     # ... (other directories)
   ```

**Optional changes** (advanced):
- Upload schedule (line ~106): Change from `interval` mode to `daily` if needed
- Deletion policy (line ~278): Adjust `keep_days` (default: 14)
- Operational hours (line ~153): Adjust upload time window

Save and exit: `Ctrl+X`, `Y`, `Enter`

---

### Step 5: Pre-Deployment Validation

**IMPORTANT:** Run this before installing!

```bash
./scripts/verify_deployment.sh
```

**Expected output:**
```
╔════════════════════════════════════════════════════════════════╗
║  TVM Log Upload - Pre-Deployment Validation                   ║
╔════════════════════════════════════════════════════════════════╗

Configuration File
────────────────────────────────────────────────────────────────
✓ Config file exists: /home/user/tvm-upload/config/config.yaml
✓ Vehicle ID: vehicle-CN-001
✓ S3 Bucket: t01logs
✓ AWS Region: cn-north-1

AWS Credentials
────────────────────────────────────────────────────────────────
✓ AWS credentials file exists
✓ AWS profile configured: china

AWS Connectivity & Permissions
────────────────────────────────────────────────────────────────
ℹ Testing AWS connectivity...
✓ S3 bucket accessible: s3://t01logs
✓ S3 write permission verified
✓ CloudWatch permissions verified

... (more checks)

════════════════════════════════════════════════════════════════
[PASS] Environment ready for deployment ✓

Ready to install:
  sudo ./scripts/install.sh
```

**If validation fails:**
- ✗ Red errors: MUST be fixed before proceeding
- ⚠ Yellow warnings: Should be reviewed but may be acceptable

---

### Step 6: Install System

**One-command installation:**

```bash
sudo ./scripts/install.sh
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
  2. Check health:       sudo ./scripts/health_check.sh
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

---

### Step 7: Verify Deployment

**Run health check:**

```bash
sudo ./scripts/health_check.sh
```

**Expected output:**
```
╔════════════════════════════════════════════════════════════════╗
║  TVM Upload Health Check - vehicle-CN-001                     ║
╔════════════════════════════════════════════════════════════════╗

Service Status
✓ Service is running (started: 2025-01-27 14:32:15)

Recent Activity
✓ No errors in last 24 hours
⚠ No uploads in last 24 hours
ℹ This may be normal if no new files were created

Upload Queue
✓ Queue file exists: /var/lib/tvm-upload/queue.json
✓ Queue is empty (all files uploaded)

Upload Registry
⚠ Registry file not found (will be created on first upload)

Disk Space
✓ Disk usage: 45% (120GB available)

S3 Connectivity
✓ S3 bucket accessible
⚠ No files found in S3 yet
ℹ Files will appear after first upload

Configuration
✓ Config file exists: /etc/tvm-upload/config.yaml
✓ Upload schedule: interval
✓ Deletion policy: enabled (keep 14 days)

════════════════════════════════════════════════════════════════
Health Check Summary
════════════════════════════════════════════════════════════════
  Passed:   8
  Failed:   0
  Warnings: 3

[WARN] System is working with minor issues
       No action required
```

**Warnings are normal** for a fresh installation (no files uploaded yet).

---

### Step 8: Verify First Upload

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
| Health check | `sudo ./scripts/health_check.sh` |
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

### Problem: Service won't start

**Check logs:**
```bash
journalctl -u tvm-upload -n 50
```

**Common causes:**
- Missing AWS credentials
- Invalid configuration
- Python dependencies not installed
- File permission issues

**Solution:**
```bash
# Re-run pre-deployment validation
./scripts/verify_deployment.sh

# Reinstall
sudo ./scripts/uninstall.sh
sudo ./scripts/install.sh
```

---

### Problem: No files uploading to S3

**Check queue:**
```bash
cat /var/lib/tvm-upload/queue.json | python3 -m json.tool
```

**Check logs for errors:**
```bash
journalctl -u tvm-upload | grep -i error
```

**Common causes:**
- Operational hours restriction (uploads only 09:00-18:00)
- File stability period not elapsed (60 seconds)
- No new files created in monitored directories
- Network connectivity issues

**Solution:**
```bash
# Check operational hours in config
grep -A 10 "operational_hours:" /etc/tvm-upload/config.yaml

# Temporarily disable operational hours
sudo nano /etc/tvm-upload/config.yaml
# Set: operational_hours.enabled: false
sudo systemctl reload tvm-upload

# Create test file and wait
echo "test" > ~/.parcel/log/terminal/test-$(date +%s).log
sleep 90
journalctl -u tvm-upload -n 20
```

---

### Problem: Disk full

**Check disk usage:**
```bash
df -h /
```

**Check deletion settings:**
```bash
grep -A 15 "deletion:" /etc/tvm-upload/config.yaml
```

**Solution:**
```bash
# Enable deletion if disabled
sudo nano /etc/tvm-upload/config.yaml
# Set: deletion.after_upload.enabled: true
# Set: deletion.after_upload.keep_days: 0  # Immediate deletion
sudo systemctl reload tvm-upload

# Enable emergency cleanup
# Set: deletion.emergency.enabled: true
sudo systemctl reload tvm-upload
```

---

### Problem: Duplicate uploads

**Check registry:**
```bash
cat /var/lib/tvm-upload/processed_files.json | python3 -m json.tool | less
```

**Common causes:**
- Registry file corrupted
- File modified after upload (size/mtime changed)

**Solution:**
```bash
# Clear registry (will re-upload all files)
sudo systemctl stop tvm-upload
sudo rm /var/lib/tvm-upload/processed_files.json
sudo systemctl start tvm-upload
```

---

### Problem: Service crashes on reboot

**Check service status:**
```bash
sudo systemctl status tvm-upload
```

**Check if enabled:**
```bash
sudo systemctl is-enabled tvm-upload
```

**Solution:**
```bash
# Re-enable service
sudo systemctl enable tvm-upload
sudo systemctl start tvm-upload
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
sudo ./scripts/uninstall.sh --keep-data
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
sudo ./scripts/uninstall.sh
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

- [ ] AWS credentials configured on vehicle
- [ ] Repository cloned/updated
- [ ] Configuration file created and edited
- [ ] Vehicle ID is unique
- [ ] Pre-deployment validation passed
- [ ] Installation completed successfully
- [ ] Health check passed
- [ ] Test file uploaded to S3
- [ ] Service logs show no errors
- [ ] Documented vehicle ID in inventory

---

## 📞 Support

**Common Issues:**
- Check logs: `journalctl -u tvm-upload -f`
- Run health check: `sudo ./scripts/health_check.sh`
- Review configuration: `/etc/tvm-upload/config.yaml`

**For Help:**
- GitHub Issues: https://github.com/your-org/tvm-upload/issues
- Documentation: `/docs` directory

---

**Last Updated:** 2025-01-27
**Version:** 2.1
