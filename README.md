The README is **mostly good** but has a few issues with the latest code. Here's the **updated version**:

---

# TVM Log Upload System

Automated log upload system for Autoware vehicles in China.

## Features

- ✅ Automatic file detection with 60s stability check
- ✅ Scheduled daily uploads (configurable time)
- ✅ Retry logic with exponential backoff (up to 10 attempts)
- ✅ Queue persistence (survives daemon restarts)
- ✅ Disk management (automatic cleanup at thresholds)
- ✅ CloudWatch metrics and alarms
- ✅ Operational hours control (9:00-16:00 configurable)

## Installation

### Requirements

- Linux (Ubuntu 20.04+ recommended)
- Python 3.10+
- AWS credentials for China region (cn-north-1 or cn-northwest-1)

### Setup

```bash
# Clone repository
git clone git@github.com:Futu-reADS/tvm-upload.git
cd tvm-upload

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install in editable mode (recommended for development)
pip install -e ".[test]"

# OR install from requirements.txt
pip install -r requirements.txt

# Create configuration
cp config/config.yaml.example config/config.yaml
nano config/config.yaml

# Test configuration
python3 src/main.py --config config/config.yaml --test-config
```

## Configuration

Edit `config/config.yaml`:

```yaml
vehicle_id: "vehicle-001"

log_directories:
  - /var/log/autoware/bags
  - /var/log/autoware/system

s3:
  bucket: tvm-logs
  region: cn-north-1
  credentials_path: ~/.aws

upload:
  schedule: "15:00"  # Daily upload time (HH:MM)
  file_stable_seconds: 60
  operational_hours:
    enabled: true
    start: "09:00"  # Start upload window
    end: "16:00"    # End upload window
  queue_file: /var/lib/tvm-upload/queue.json

disk:
  reserved_gb: 70  # Minimum free space to maintain
  warning_threshold: 0.90  # Warn at 90% usage
  critical_threshold: 0.95  # Force cleanup at 95%

monitoring:
  cloudwatch_enabled: true
```

See `config/config.yaml.example` for full documentation.

## Usage

### Run as Foreground Process

```bash
# Run with INFO logging
python3 src/main.py --config config/config.yaml --log-level INFO

# Run with DEBUG logging (verbose)
python3 src/main.py --config config/config.yaml --log-level DEBUG

# Run with WARNING logging (quiet)
python3 src/main.py --config config/config.yaml --log-level WARNING
```

### Install as systemd Service

```bash
# Copy service file
sudo cp systemd/tvm-upload.service /etc/systemd/system/

# Edit service file to set correct paths
sudo nano /etc/systemd/system/tvm-upload.service

# Enable and start service
sudo systemctl daemon-reload
sudo systemctl enable tvm-upload
sudo systemctl start tvm-upload
sudo systemctl status tvm-upload
```

### View Logs

```bash
# Follow logs in real-time
sudo journalctl -u tvm-upload -f

# View last 100 lines
sudo journalctl -u tvm-upload -n 100

# View logs from today
sudo journalctl -u tvm-upload --since today
```

### Reload Configuration

```bash
# Reload without restarting (SIGHUP)
sudo systemctl reload tvm-upload

# OR send signal directly
sudo kill -HUP $(pgrep -f 'src/main.py')

# OR restart service
sudo systemctl restart tvm-upload
```

## Testing

```bash
# Run all tests
pytest tests/ -v

# Run with coverage report
pytest tests/ --cov=src --cov-report=term-missing

# Run specific test file
pytest tests/test_upload.py -v

# Run specific test
pytest tests/test_main.py::TestTVMUploadSystem::test_init -v

# Run with debug output
pytest tests/test_main.py -v -s
```

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    TVM Upload Daemon                    │
│                                                         │
│  ┌────────────┐      ┌──────────────┐                 │
│  │   Config   │─────>│ File Monitor │                 │
│  │  Manager   │      │  (watchdog)  │                 │
│  └────────────┘      └──────┬───────┘                 │
│                             │ file stable              │
│                             ↓                          │
│                      ┌──────────────┐                 │
│                      │    Queue     │                 │
│                      │   Manager    │                 │
│                      └──────┬───────┘                 │
│                             │ scheduled upload         │
│                             ↓                          │
│  ┌────────────┐      ┌──────────────┐                 │
│  │   Disk     │<─────│   Upload     │                 │
│  │  Manager   │      │   Manager    │                 │
│  └────────────┘      │   (boto3)    │                 │
│       │              └──────┬───────┘                 │
│       │ cleanup             │ metrics                  │
│       ↓                     ↓                          │
│  ┌─────────────────────────────────┐                  │
│  │      CloudWatch Manager         │                  │
│  └─────────────────────────────────┘                  │
│                                                         │
└─────────────────────────────────────────────────────────┘
           │                            │
           │ monitor                    │ upload
           ↓                            ↓
    ┌─────────────┐            ┌──────────────┐
    │  Autoware   │            │  AWS China   │
    │   Logs      │            │     S3       │
    └─────────────┘            └──────────────┘
```

## Monitoring

### CloudWatch Metrics

Namespace: `TVM/Upload`

- `BytesUploaded` - Total bytes uploaded (Sum)
- `FileCount` - Number of files uploaded (Count)
- `FailureCount` - Number of failed uploads (Count)
- `DiskUsagePercent` - Current disk usage (Gauge)

Dimension: `VehicleId=vehicle-001`

### Queue Status

Check pending uploads:
```bash
cat /var/lib/tvm-upload/queue.json
# OR (if configured differently)
cat /tmp/tvm-test-queue.json
```

### System Logs

Logs are written to:
- **systemd journal** (when running as service)
- **stdout/stderr** (when running in foreground)

Log format:
```
2025-10-12 15:30:45 [main] [INFO] File ready: autoware.log
2025-10-12 15:30:46 [upload_manager] [INFO] Uploading autoware.log (attempt 1/10)
2025-10-12 15:30:50 [upload_manager] [INFO] SUCCESS: autoware.log -> s3://tvm-logs/vehicle-001/2025-10-12/autoware.log
```

## Troubleshooting

### Uploads Not Happening

**Check 1: Operational Hours**
```bash
# View current config
grep -A 5 "operational_hours" config/config.yaml

# Check current time
date +"%H:%M"

# Uploads only happen between start and end times
```

**Check 2: Queue Status**
```bash
# View pending files
cat /var/lib/tvm-upload/queue.json

# If queue is empty, files haven't been detected yet
# Wait 60 seconds after file creation for stability check
```

**Check 3: Service Status**
```bash
# Check if service is running
sudo systemctl status tvm-upload

# View recent logs
sudo journalctl -u tvm-upload -n 50
```

**Check 4: File Detection**
```bash
# Verify log directories exist
ls -la /var/log/autoware/bags

# Check file permissions
ls -l /var/log/autoware/bags/*.mcap

# Files must be stable (unchanged) for 60 seconds
```

### Disk Full

**Automatic Cleanup:**
- System automatically deletes oldest uploaded files at **90% disk usage**
- Force cleanup at **95% usage** (may delete non-uploaded files)

**Manual Cleanup:**
```bash
# Check current disk usage
df -h /

# Manual cleanup (Python)
python3 << EOF
from src.disk_manager import DiskManager
dm = DiskManager(['/var/log/autoware'], reserved_gb=70)
deleted = dm.cleanup_old_files()
print(f"Deleted {deleted} files")
EOF
```

### AWS Credentials Issues

**Verify Credentials:**
```bash
# Check credentials file exists
cat ~/.aws/credentials

# Should contain:
# [default]
# aws_access_key_id = YOUR_KEY
# aws_secret_access_key = YOUR_SECRET

# Test S3 access
#aws s3 ls s3://tvm-logs --region cn-north-1
aws s3 ls s3://t01logs   --region cn-north-1   --endpoint-url https://s3.cn-north-1.amazonaws.com.cn   --profile china

# Test with boto3
python3 -c "import boto3; print(boto3.client('s3', region_name='cn-north-1').list_buckets())"
```

**Common Issues:**
- **Wrong region:** Use `cn-north-1` or `cn-northwest-1` for China
- **Credentials expired:** Refresh IAM credentials
- **No permissions:** Ensure IAM role has `s3:PutObject` permission
- **Network issues:** Check connectivity to China region

### Upload Failures

**Check Retry Logic:**
```bash
# View logs for retry attempts
sudo journalctl -u tvm-upload | grep "Upload failed"

# Should see exponential backoff: 1s, 2s, 4s, 8s, 16s...
# Max 10 retries before giving up
```

**Network Issues:**
```bash
# Test S3 connectivity
curl -I https://s3.cn-north-1.amazonaws.com.cn

# Check DNS resolution
nslookup s3.cn-north-1.amazonaws.com.cn
```

### Configuration Errors

**Validate Config:**
```bash
# Test configuration syntax
python3 src/main.py --config config/config.yaml --test-config

# Should output:
# Configuration valid!
# Vehicle ID: vehicle-001
# S3 Bucket: tvm-logs
# ...
```

### Performance Issues

**High CPU Usage:**
- Check log level (DEBUG is verbose)
- Reduce number of monitored directories
- Increase `file_stable_seconds` to reduce checks

**High Memory Usage:**
- Reduce queue size (upload more frequently)
- Check for large files (>1GB)
- Monitor with: `ps aux | grep main.py`

## Project Structure

```
tvm-upload/
├── src/
│   ├── main.py              # Main coordinator
│   ├── config_manager.py    # YAML configuration
│   ├── file_monitor.py      # Watchdog file detection
│   ├── upload_manager.py    # S3 uploads with retry
│   ├── disk_manager.py      # Disk space management
│   ├── queue_manager.py     # Persistent queue
│   └── cloudwatch_manager.py # CloudWatch metrics
├── tests/
│   ├── test_config.py
│   ├── test_monitor.py
│   ├── test_upload.py
│   ├── test_disk.py
│   ├── test_queue.py
│   ├── test_cloudwatch.py
│   └── test_main.py
├── config/
│   └── config.yaml.example
├── systemd/
│   └── tvm-upload.service
├── requirements.txt
├── setup.py
└── README.md
```

## Development

### Running Tests Locally

```bash
# All tests use mocks - no AWS credentials needed!
pytest tests/ -v

# Tests will pass even without AWS access
```

### Adding New Features

1. Create feature branch
2. Write tests first (TDD)
3. Implement feature
4. Ensure tests pass: `pytest tests/ -v`
5. Check coverage: `pytest --cov=src --cov-report=term-missing`
6. Submit PR

### Code Style

- Use type hints
- Add docstrings to all functions
- Follow PEP 8
- Keep functions under 50 lines
- Use descriptive variable names

## License

[Your License]

## Support

For issues and questions:
- **Email:** support@yourcompany.com
- **Slack:** #tvm-upload-support
- **Documentation:** https://wiki.yourcompany.com/tvm-upload

---

## Key Changes Made

1. ✅ **Changed installation:** Use `pip install -e ".[test]"` (editable install with setup.py)
2. ✅ **Added log-level option:** `--log-level DEBUG/INFO/WARNING/ERROR`
3. ✅ **Clarified log location:** Logs go to systemd journal or stdout (not a file by default)
4. ✅ **Added operational hours explanation:** 9:00-16:00 upload window
5. ✅ **Expanded troubleshooting:** More specific solutions
6. ✅ **Added architecture diagram:** Visual system overview
7. ✅ **CloudWatch metrics details:** Actual metric names from code
8. ✅ **Queue file path:** Mentioned both default and configurable paths
9. ✅ **Project structure:** Shows all modules
10. ✅ **Development section:** For contributors

**This README now matches your actual code implementation!**