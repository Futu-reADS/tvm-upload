# TVM Log Upload System

Automated log upload daemon for Autoware vehicles in China. Monitors log directories, queues files, uploads them to AWS S3 China region on a schedule, and manages disk space through configurable deletion policies.

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![AWS China](https://img.shields.io/badge/AWS-China%20Region-orange.svg)](https://www.amazonaws.cn/)

## Features

- **Automatic file detection** with 60s stability check
- **Flexible scheduling** - Daily uploads or interval-based (every N hours)
- **Dual upload modes** - Immediate uploads during operational hours + scheduled batch uploads
- **Source-based organization** - Files organized by type (terminal/ros/syslog/ros2)
- **ROS folder preservation** - Maintains complete ROS log folder structure in S3
- **Retry logic** with exponential backoff (up to 10 attempts)
- **Queue persistence** - Survives daemon restarts and system reboots
- **Duplicate prevention** - Processed files registry prevents re-uploading
- **Smart disk management** - Three-tier deletion policies (deferred, age-based, emergency)
- **CloudWatch integration** - Metrics and alarms for monitoring
- **SIGHUP reload** - Update configuration without restart

## Quick Start

```bash
# Clone and setup
git clone git@github.com:Futu-reADS/tvm-upload.git
cd tvm-upload

# Install dependencies
pip install -e ".[test]"

# Configure
cp config/config.yaml.example config/config.yaml
nano config/config.yaml  # Edit: vehicle_id, S3 bucket, AWS profile

# Test configuration
python3 src/main.py --config config/config.yaml --test-config

# Run
python3 src/main.py --config config/config.yaml --log-level INFO
```

## Installation

### Requirements

- **OS:** Linux (Ubuntu 20.04+, Debian 11+)
- **Python:** 3.10 or higher
- **AWS:** Credentials for China region (cn-north-1 or cn-northwest-1)
- **Disk:** Minimum 100GB recommended for log storage

### Development Setup

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install in editable mode with test dependencies
pip install -e ".[test]"

# Verify installation
python -c "import src.config_manager; print('✓ Package installed')"

# Run tests
pytest tests/unit/ -v
pytest tests/integration/ -v
pytest tests/e2e/ -v
```

### Production Setup

**Automated Installation (Recommended)**

```bash
# 1. Configure
cp config/config.yaml.example config/config.yaml
nano config/config.yaml  # Edit: vehicle_id, S3 bucket, AWS profile

# 2. Validate environment
./scripts/deployment/verify_deployment.sh

# 3. Install (creates directories, installs service, starts daemon)
sudo ./scripts/deployment/install.sh
```

The install script automatically:
- Creates `/opt/tvm-upload` (runtime code), `/var/lib/tvm-upload` (data), `/var/log/tvm-upload` (logs)
- Installs systemd service and enables auto-start on boot
- Validates AWS credentials and configuration

**Manual Installation**

```bash
# Install from requirements
pip install -r requirements.txt

# Create required directories
sudo mkdir -p /var/lib/tvm-upload /etc/tvm-upload /var/log/tvm-upload

# Copy and configure
sudo cp config/config.yaml /etc/tvm-upload/config.yaml
sudo nano /etc/tvm-upload/config.yaml

# Install systemd service
sudo cp systemd/tvm-upload.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable tvm-upload
sudo systemctl start tvm-upload
```

### Uninstall

To completely remove the service:

```bash
sudo ./scripts/deployment/uninstall.sh
```

This removes service, runtime directories, and optionally cleans data/logs.

## Configuration

### Essential Settings

Edit `config/config.yaml`:

```yaml
# Unique identifier for this vehicle
vehicle_id: "vehicle-CN-001"

# Directories to monitor
log_directories:
  - /home/autoware/.parcel/log/terminal   # Terminal logs
  - /home/autoware/.ros/log                # ROS logs
  - /var/log                               # System logs
  - /home/autoware/ros2_ws/log             # ROS2 logs

# AWS S3 Configuration
s3:
  bucket: t01logs
  region: cn-north-1
  credentials_path: /home/autoware/.aws
  profile: china

# Upload Configuration
upload:
  schedule:
    mode: "interval"          # "daily" or "interval"
    interval_hours: 2         # Upload every 2 hours
    interval_minutes: 0

  operational_hours:
    enabled: true
    start: "09:00"            # Immediate uploads 09:00-16:00
    end: "16:00"

  batch_upload:
    enabled: true             # Upload entire queue when file ready

  upload_on_start: true       # Upload immediately on service start

# Deletion Policies
deletion:
  after_upload:
    enabled: true
    keep_days: 14             # Keep files 14 days after upload

  age_based:
    enabled: true
    max_age_days: 7           # Delete files older than 7 days
    schedule_time: "02:00"

  emergency:
    enabled: true             # Delete when disk >95% full
```

See [config/config.yaml.example](config/config.yaml.example) for comprehensive documentation with all options.

### Upload Modes Explained

**Mode 1: Daily Upload**
```yaml
schedule:
  mode: "daily"
  daily_time: "15:00"  # Upload once per day at 3 PM
```
- Best for: Depot vehicles with stable WiFi at specific times
- All files queue throughout the day, bulk upload at scheduled time

**Mode 2: Interval Upload (Recommended for Mobile Vehicles)**
```yaml
schedule:
  mode: "interval"
  interval_hours: 2    # Upload every 2 hours
  interval_minutes: 0
```
- Best for: Mobile vehicles with intermittent WiFi
- Multiple upload opportunities throughout the day
- Balances upload frequency with network usage

### Operational Hours

Controls **immediate uploads** only (not scheduled uploads):

- **Within operational hours (09:00-16:00):** Files upload immediately when ready
- **Outside operational hours:** Files queue for next scheduled upload
- **Scheduled uploads:** Always run regardless of operational hours

Set `enabled: false` to allow immediate uploads 24/7.

## Usage

### Running as Foreground Process

```bash
# Standard operation
python3 src/main.py --config config/config.yaml --log-level INFO

# Debug mode (verbose logging)
python3 src/main.py --config config/config.yaml --log-level DEBUG

# Quiet mode (warnings and errors only)
python3 src/main.py --config config/config.yaml --log-level WARNING

# Test configuration without running
python3 src/main.py --config config/config.yaml --test-config
```

### Managing systemd Service

```bash
# Start/stop/restart
sudo systemctl start tvm-upload
sudo systemctl stop tvm-upload
sudo systemctl restart tvm-upload

# Check status
sudo systemctl status tvm-upload

# Enable/disable autostart
sudo systemctl enable tvm-upload
sudo systemctl disable tvm-upload

# Reload configuration (no restart required)
sudo systemctl reload tvm-upload
```

### Viewing Logs

```bash
# Follow logs in real-time
sudo journalctl -u tvm-upload -f

# Last 100 lines
sudo journalctl -u tvm-upload -n 100

# Logs from today
sudo journalctl -u tvm-upload --since today

# Logs with specific log level
sudo journalctl -u tvm-upload | grep ERROR
```

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    TVM Upload Daemon                    │
│                     (src/main.py)                       │
│                                                         │
│  ┌────────────┐      ┌──────────────┐                 │
│  │   Config   │─────>│ File Monitor │                 │
│  │  Manager   │      │  (watchdog)  │                 │
│  └────────────┘      └──────┬───────┘                 │
│                             │ file stable (60s)        │
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
└─────────────────────────────────────────────────────────┘
           │                            │
           │ monitor                    │ upload
           ↓                            ↓
    ┌─────────────┐            ┌──────────────┐
    │  Autoware   │            │  AWS China   │
    │   Logs      │            │     S3       │
    └─────────────┘            └──────────────┘
```

### Component Overview

| Component | Purpose | File |
|-----------|---------|------|
| **TVMUploadSystem** | Main coordinator, signal handling | `src/main.py` |
| **ConfigManager** | YAML config loading and validation | `src/config_manager.py` |
| **FileMonitor** | Watchdog-based file detection | `src/file_monitor.py` |
| **QueueManager** | Persistent upload queue (JSON) | `src/queue_manager.py` |
| **UploadManager** | S3 uploads with retry logic | `src/upload_manager.py` |
| **DiskManager** | Three-tier deletion policies | `src/disk_manager.py` |
| **CloudWatchManager** | Metrics publishing | `src/cloudwatch_manager.py` |

### Upload Workflow

```
1. SERVICE STARTS (9:30 AM)
   ├─ Load processed_files_registry
   ├─ Scan directories for files < 3 days old
   ├─ Filter out already-uploaded files
   ├─ Add to queue
   └─ If upload_on_start: true → Upload immediately

2. FILE BECOMES READY (after 60s stability)
   ├─ Check operational_hours
   ├─ WITHIN hours (09:00-16:00)
   │  ├─ batch_upload=true → Upload entire queue
   │  └─ batch_upload=false → Upload only this file
   └─ OUTSIDE hours → Queue for scheduled upload

3. SCHEDULED UPLOAD (every 2 hours: 09:00, 11:00, 13:00...)
   └─ Upload entire queue (includes failed files)

4. AFTER SUCCESSFUL UPLOAD
   ├─ Add to processed_files_registry
   ├─ If keep_days=0 → Delete immediately
   ├─ If keep_days=14 → Mark for deletion in 14 days
   └─ Remove from queue

5. AGE-BASED CLEANUP (daily at 02:00)
   └─ Delete files older than max_age_days (7 days)

6. EMERGENCY CLEANUP (disk >95% full)
   └─ Delete oldest uploaded files to free space
```

## S3 Folder Structure

Files are organized by vehicle, date (file modification time), and source type:

```
s3://t01logs/
└── vehicle-CN-001/
    ├── 2025-10-20/
    │   ├── terminal/
    │   │   ├── terminal_2025-10-20_10-30-15.log
    │   │   └── terminal_2025-10-20_14-22-03.log
    │   ├── ros/
    │   │   ├── 2025-10-20-15-30-00-123456-mini01-NucBox/
    │   │   │   ├── launch.log
    │   │   │   └── rosout.log
    │   │   └── some-loose-file.log
    │   ├── syslog/
    │   │   └── syslog_2025-10-20
    │   └── ros2/
    │       └── ros2_node_2025-10-20.log
    │
    └── 2025-10-21/
        ├── terminal/...
        ├── ros/...
        ├── syslog/...
        └── ros2/...
```

**Benefits:**
- Clear organization by source type
- ROS folder structure completely preserved
- Files grouped by creation date (handles delayed uploads correctly)
- Easy to download specific log types or dates

**Example Downloads:**
```bash
# All logs from Oct 20
aws s3 sync s3://t01logs/vehicle-CN-001/2025-10-20/ ./logs/

# Only ROS logs from Oct 20
aws s3 sync s3://t01logs/vehicle-CN-001/2025-10-20/ros/ ./ros-logs/

# Only terminal logs from Oct 20
aws s3 sync s3://t01logs/vehicle-CN-001/2025-10-20/terminal/ ./terminal-logs/
```

## Monitoring

### CloudWatch Metrics

**Namespace:** `TVM/Upload`

| Metric | Type | Description |
|--------|------|-------------|
| `BytesUploaded` | Sum | Total bytes uploaded |
| `FileCount` | Count | Number of files uploaded |
| `FailureCount` | Count | Number of failed uploads |
| `DiskUsagePercent` | Gauge | Current disk usage (0-100) |

**Dimension:** `VehicleId=vehicle-CN-001`

**Viewing in AWS Console:**
```
CloudWatch → Metrics → TVM/Upload → VehicleId → Select metrics
```

### Queue Status

Check pending uploads:
```bash
# Default location
cat /var/lib/tvm-upload/queue.json

# Format:
# {
#   "files": [
#     {
#       "filepath": "/path/to/file.log",
#       "size": 1024,
#       "detected_at": "2025-10-20T10:30:00",
#       "attempts": 0
#     }
#   ]
# }
```

### Processed Files Registry

Check uploaded files:
```bash
cat /var/lib/tvm-upload/processed_files.json

# Shows files already uploaded (prevents duplicates)
```

## Testing

### Test Levels

Three test levels with different purposes:

```bash
# Unit tests (fast, fully mocked, no AWS required)
pytest tests/unit/ -v

# Integration tests (mocked AWS, real file operations)
pytest tests/integration/ -v

# E2E tests (real AWS - only in CI/CD)
pytest tests/e2e/ -m e2e -v
```

### Common Test Commands

```bash
# Run all tests (excludes e2e by default)
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=src --cov-report=term-missing

# Run specific test file
pytest tests/unit/test_upload.py -v

# Run specific test
pytest tests/integration/test_main.py::TestTVMUploadSystem::test_init -v

# Run with debug output
pytest tests/unit/test_upload.py -v -s
```

### Test Markers

Defined in `pytest.ini`:

- `unit` - Fast unit tests with full mocking
- `integration` - Integration tests with mocked AWS
- `e2e` - End-to-end tests requiring real AWS credentials

### Test Runner Script

For convenience, use `scripts/testing/run_tests.sh` - a professional test runner with automatic venv setup, coverage reporting, and colored output.

**Basic Usage:**

```bash
# Run all tests (unit + integration + e2e)
./scripts/testing/run_tests.sh

# Or specify a test mode
./scripts/testing/run_tests.sh unit          # Unit tests only (~5s)
./scripts/testing/run_tests.sh integration   # Integration tests only (~15s)
./scripts/testing/run_tests.sh e2e           # E2E tests only (~60s, requires AWS)
./scripts/testing/run_tests.sh fast          # Unit + integration (skip E2E)
```

**Options:**

```bash
# Generate coverage report (HTML output in htmlcov/)
./scripts/testing/run_tests.sh all --coverage

# Verbose output for debugging
./scripts/testing/run_tests.sh unit --verbose

# Combine options
./scripts/testing/run_tests.sh fast --coverage --verbose
```

**Environment Variables:**

```bash
# Use different AWS profile for E2E tests
AWS_PROFILE=prod ./scripts/testing/run_tests.sh e2e

# Enable coverage via environment variable
COVERAGE=true ./scripts/testing/run_tests.sh all
```

**Test Modes:**

| Mode | Tests Run | Duration | AWS Required |
|------|-----------|----------|--------------|
| `unit` | Unit tests only | ~5s | No |
| `integration` | Integration tests only | ~15s | No |
| `e2e` | E2E tests only | ~60s | Yes |
| `all` | All tests (default) | ~80s | Yes (for E2E) |
| `fast` | Unit + integration | ~20s | No |

**Examples:**

```bash
# Quick local testing (no AWS needed)
./scripts/testing/run_tests.sh fast

# Full test suite with coverage report
./scripts/testing/run_tests.sh all --coverage
# Then open: htmlcov/index.html

# E2E tests with production AWS profile
AWS_PROFILE=prod ./scripts/testing/run_tests.sh e2e

# Debug failing unit tests
./scripts/testing/run_tests.sh unit --verbose

# Help
./scripts/testing/run_tests.sh help
```

**Features:**

- Automatic virtual environment setup
- Colored output for better readability
- Coverage reporting with HTML output
- Time tracking for test execution
- Supports all pytest options via pass-through

### Manual Testing

For end-to-end validation, use the manual test suite (16 scenarios covering all features):

```bash
# Run all manual tests
./scripts/testing/run_manual_tests.sh

# Run specific tests
./scripts/testing/run_manual_tests.sh config/config.yaml "1 2 3"

# Individual test
./scripts/testing/manual-tests/01_basic_upload.sh
```

**Test Scenarios:** Basic upload, source detection, date preservation, CloudWatch metrics/alarms, duplicate prevention, disk management, batch upload, large files, error handling, operational hours, service restart, pattern matching, recursive monitoring, startup scan, emergency cleanup.

See `scripts/testing/manual-tests/README.md` for detailed test descriptions.

## Troubleshooting

### Files Not Uploading

**1. Check Operational Hours**
```bash
# View current config
grep -A 5 "operational_hours" config/config.yaml

# Check current time
date +"%H:%M"

# Immediate uploads only happen within operational hours
# Scheduled uploads always run regardless of hours
```

**2. Check Queue Status**
```bash
# View pending files
cat /var/lib/tvm-upload/queue.json

# If empty, files haven't been detected yet
# Wait 60 seconds after file creation for stability check
```

**3. Check Service Status**
```bash
sudo systemctl status tvm-upload
sudo journalctl -u tvm-upload -n 50
```

**4. Check Processed Files Registry**
```bash
# File might already be uploaded
cat /var/lib/tvm-upload/processed_files.json | grep filename.log
```

### Disk Full

**Automatic Cleanup:**
- **90% usage:** Delete oldest uploaded files (warning)
- **95% usage:** Emergency cleanup (may delete non-uploaded files)

**Check Disk Usage:**
```bash
df -h /
```

**Check Deletion Configuration:**
```bash
grep -A 10 "deletion:" config/config.yaml

# Ensure emergency.enabled: true for production!
```

**Manual Cleanup:**
```bash
# Trigger age-based cleanup manually
python3 -c "
from src.disk_manager import DiskManager
from src.config_manager import ConfigManager
config = ConfigManager('config/config.yaml')
dm = DiskManager(config)
deleted = dm.age_based_cleanup()
print(f'Deleted {deleted} files')
"
```

### AWS Credentials Issues

**Verify Credentials:**
```bash
# Check credentials file
cat ~/.aws/credentials

# Should contain:
# [china]
# aws_access_key_id = YOUR_KEY
# aws_secret_access_key = YOUR_SECRET

# Test S3 access
aws s3 ls s3://t01logs \
  --region cn-north-1 \
  --endpoint-url https://s3.cn-north-1.amazonaws.com.cn \
  --profile china
```

**Common Issues:**
- **Wrong region:** Must use `cn-north-1` or `cn-northwest-1` for China
- **Wrong endpoint:** Must use `.amazonaws.com.cn` suffix
- **Wrong profile:** Ensure `profile: china` matches your AWS credentials file
- **No permissions:** IAM role needs `s3:PutObject` and `s3:GetObject` permissions
- **Network:** Check connectivity to China region endpoints

### Upload Failures

**View Retry Attempts:**
```bash
sudo journalctl -u tvm-upload | grep "Upload failed"

# Should see exponential backoff: 1s, 2s, 4s, 8s, 16s...
# Max 10 retries before giving up
```

**Test S3 Connectivity:**
```bash
curl -I https://s3.cn-north-1.amazonaws.com.cn
nslookup s3.cn-north-1.amazonaws.com.cn
```

### Configuration Errors

**Validate Configuration:**
```bash
python3 src/main.py --config config/config.yaml --test-config

# Should output:
# ✓ Configuration valid!
# Vehicle ID: vehicle-CN-001
# S3 Bucket: t01logs
# ...
```

**Common Config Issues:**
- Missing required fields (vehicle_id, s3.bucket, s3.region)
- Invalid time format (must be "HH:MM")
- Invalid interval (minimum 5 minutes, maximum 24 hours)
- Invalid paths (directories don't exist)

### Duplicate Uploads

If files are being uploaded multiple times:

```bash
# Check processed files registry is enabled
grep -A 3 "processed_files_registry" config/config.yaml

# Check registry file exists and is readable
ls -l /var/lib/tvm-upload/processed_files.json

# If corrupted, delete and restart service
sudo rm /var/lib/tvm-upload/processed_files.json
sudo systemctl restart tvm-upload
```

## Development

### Project Structure

```
tvm-upload/
├── src/                        # Application source code
│   ├── main.py                 # Main coordinator and entry point
│   ├── config_manager.py       # YAML configuration management
│   ├── file_monitor.py         # Watchdog file detection
│   ├── upload_manager.py       # S3 uploads with retry logic
│   ├── disk_manager.py         # Three-tier deletion policies
│   ├── queue_manager.py        # Persistent JSON queue
│   └── cloudwatch_manager.py   # CloudWatch metrics publishing
├── tests/                      # Test suite (235+ tests)
│   ├── unit/                   # Fast unit tests (mocked)
│   ├── integration/            # Integration tests (mocked AWS)
│   └── e2e/                    # End-to-end tests (real AWS)
├── scripts/                    # Operations and testing scripts
│   ├── deployment/             # Production deployment
│   │   ├── install.sh          # Automated installation
│   │   ├── uninstall.sh        # Clean removal
│   │   ├── verify_deployment.sh # Pre-install validation
│   │   └── health_check.sh     # System health check
│   ├── testing/                # Test execution
│   │   ├── run_tests.sh        # Test runner with coverage
│   │   ├── run_manual_tests.sh # Manual test orchestrator
│   │   └── manual-tests/       # 16 manual test scenarios
│   ├── diagnostics/            # Troubleshooting tools
│   │   └── verify_aws_credentials.sh
│   └── lib/                    # Shared libraries
│       └── test_helpers.sh
├── docs/                       # Documentation
│   ├── README.md               # Documentation index
│   ├── deployment_guide.md     # Production deployment
│   ├── quick_start.md          # Getting started
│   ├── testing_strategy_overview.md
│   ├── autonomous_testing_guide.md
│   └── github_actions_oidc_setup.md
├── .github/                    # CI/CD workflows
│   └── workflows/
│       └── run-tests.yml       # Automated testing
├── config/
│   └── config.yaml.example     # Comprehensive config documentation
├── systemd/
│   └── tvm-upload.service      # systemd service definition
├── requirements.txt            # Python dependencies
├── setup.py                    # Package setup
├── pytest.ini                  # Test configuration
├── CLAUDE.md                   # Claude Code guidance
└── README.md                   # This file
```

### Adding New Features

1. **Write tests first** (TDD approach)
2. **Unit test** in `tests/unit/` with full mocking
3. **Integration test** in `tests/integration/` if component interaction needed
4. **Update config schema** in `config_manager.py` if adding config options
5. **Update config.yaml.example** with documentation
6. **Run tests:** `pytest tests/ -v`
7. **Check coverage:** `pytest --cov=src --cov-report=term-missing`

### Code Style Guidelines

- Use **type hints** for all function parameters and return values
- Add **docstrings** to all functions (Google style)
- Follow **PEP 8** style guide
- Keep functions **under 50 lines**
- Use **descriptive variable names**
- Use **pathlib.Path** for file operations
- Convert to `str` only when required by external APIs

### Dependencies

- **watchdog** - File system monitoring
- **boto3** - AWS S3 client
- **pyyaml** - Configuration parsing
- **pytest**, **pytest-cov**, **pytest-mock** - Testing framework

## AWS China Specifics

### Key Differences from Standard AWS

1. **Endpoints:** Must use `.amazonaws.com.cn` suffix
   ```python
   # Correct for China
   endpoint_url = "https://s3.cn-north-1.amazonaws.com.cn"

   # Incorrect (standard AWS)
   endpoint_url = "https://s3.cn-north-1.amazonaws.com"
   ```

2. **Regions:** Only `cn-north-1` (Beijing) or `cn-northwest-1` (Ningxia)

3. **Credentials:** Use AWS profile configuration
   ```yaml
   s3:
     profile: china  # Matches [china] section in ~/.aws/credentials
   ```

4. **IAM Policies:** Require separate China AWS account

### LocalStack Support

For local testing with LocalStack:

```bash
# Set environment variable
export AWS_ENDPOINT_URL=http://localhost:4566

# Run tests
pytest tests/integration/ -v
```

See `upload_manager.py:99-103` for endpoint configuration logic.

## Signal Handling

The daemon responds to the following signals:

| Signal | Behavior |
|--------|----------|
| `SIGTERM` / `SIGINT` | Graceful shutdown (upload remaining queue, stop monitoring) |
| `SIGHUP` | Reload configuration without restart |

**Reload configuration:**
```bash
# Via systemd
sudo systemctl reload tvm-upload

# Or send signal directly
sudo kill -HUP $(pgrep -f 'src/main.py')
```

## Performance Notes

### Resource Usage

- **CPU:** Low (~1-2% on idle, 5-10% during uploads)
- **Memory:** ~50-100MB depending on queue size
- **Disk I/O:** Minimal (only during file detection and upload)
- **Network:** Depends on upload frequency and file sizes

### Optimization Tips

**Reduce CPU usage:**
- Use `log_level: WARNING` instead of `DEBUG`
- Increase `file_stable_seconds` to reduce stability checks
- Reduce number of monitored directories

**Reduce memory usage:**
- Upload more frequently (smaller queue)
- Enable `deletion.after_upload` with `keep_days: 0`

**Reduce network usage:**
- Use `mode: daily` instead of `mode: interval`
- Disable `batch_upload` for on-demand uploads only

## License

Copyright (c) 2025 Futu-reADS. All rights reserved.

## Support

For issues and questions:

- **GitHub Issues:** https://github.com/Futu-reADS/tvm-upload/issues
- **Documentation:** See [CLAUDE.md](CLAUDE.md) for Claude Code guidance
- **Configuration Help:** See [config.yaml.example](config/config.yaml.example)

---

**Version:** 2.1
**Last Updated:** 2025-10-24
**Maintained by:** Futu-reADS Team
