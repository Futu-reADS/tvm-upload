# TVM Log Upload - Quick Start Guide

**5-Minute Vehicle Deployment** 🚗⚡

---

## Prerequisites (One-Time Setup)

✅ AWS China account with S3 bucket: `t01logs`
✅ AWS credentials (Access Key + Secret Key)
✅ Vehicle has network access to AWS China

---

## Deployment Steps

### 1️⃣ Clone Repository

```bash
cd ~
git clone https://github.com/your-org/tvm-upload.git
cd tvm-upload
```

### 2️⃣ Configure AWS

```bash
aws configure --profile china
# Enter: Access Key ID, Secret Key, cn-north-1, json
```

### 3️⃣ Edit Configuration

```bash
cp config/config.yaml.example config/config.yaml
nano config/config.yaml
```

**REQUIRED: Change vehicle_id (line 18):**
```yaml
vehicle_id: "vehicle-CN-001"  # ← MUST BE UNIQUE!
```

### 4️⃣ Validate Environment

```bash
./scripts/deployment/verify_deployment.sh
```

✅ Should show: **[PASS] Environment ready for deployment**

### 5️⃣ Install

```bash
sudo ./scripts/deployment/install.sh
```

⏱️ Takes ~2-3 minutes

✅ Should show: **✓ Installation Successful!**

### 6️⃣ Verify

```bash
sudo ./scripts/deployment/health_check.sh
```

✅ Should show: **[PASS] System is healthy**

### 7️⃣ Test Upload

```bash
echo "test" > ~/.parcel/log/terminal/test.log
sleep 90
aws s3 ls s3://t01logs/vehicle-CN-001/ --recursive --profile china
```

✅ Should see: `vehicle-CN-001/2025-XX-XX/terminal/test.log`

---

## Common Commands

```bash
# Monitor logs
journalctl -u tvm-upload -f

# Check health
sudo ./scripts/deployment/health_check.sh

# Restart service
sudo systemctl restart tvm-upload

# View S3 files
aws s3 ls s3://t01logs/vehicle-CN-001/ --recursive --profile china --region cn-north-1
```

---

## Troubleshooting

**Service not starting?**
```bash
journalctl -u tvm-upload -n 50
```

**No uploads?**
```bash
# Check operational hours (may only upload 09:00-18:00)
grep -A 10 "operational_hours:" /etc/tvm-upload/config.yaml
```

**Need to reinstall?**
```bash
sudo ./scripts/deployment/uninstall.sh
sudo ./scripts/deployment/install.sh
```

---

## Next Steps

📖 **Full Guide:** `docs/DEPLOYMENT_GUIDE.md`
🔧 **Configuration:** `config/config.yaml`
🏥 **Health Check:** `sudo ./scripts/deployment/health_check.sh`

---

**Questions?** Check `docs/DEPLOYMENT_GUIDE.md` or logs: `journalctl -u tvm-upload -f`
