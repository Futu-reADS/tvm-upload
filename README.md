# TVM Log Upload System

**Automated log upload daemon for Autoware vehicles in China.** Monitors log directories, queues files, uploads to AWS S3 China region on schedule, and manages disk space through smart deletion policies.

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![AWS China](https://img.shields.io/badge/AWS-China%20Region-orange.svg)](https://www.amazonaws.cn/)
[![Tests](https://img.shields.io/badge/tests-400%2B%20passing-brightgreen.svg)]()

---

## 🚀 Quick Start

### Production Deployment

**For complete vehicle deployment instructions, see:**

📘 **[Deployment Guide](docs/deployment_guide.md)** - Complete step-by-step deployment process

The deployment guide includes:
- Prerequisites and S3 bucket setup
- AWS credentials configuration with S3-specific settings
- Automated validation scripts
- Installation with health checks
- Troubleshooting and maintenance

**Quick overview:**
```bash
# 1. Configure AWS credentials
aws configure --profile china
aws configure set s3.endpoint_url https://s3.cn-north-1.amazonaws.com.cn --profile china
# (+ 2 more S3 settings - see deployment guide)

# 2. Configure and validate
cp config/config.yaml.example config/config.yaml
nano config/config.yaml  # Set vehicle_id
./scripts/deployment/verify_deployment.sh

# 3. Install
sudo ./scripts/deployment/install.sh

# 4. Verify
sudo ./scripts/deployment/health_check.sh
```

### Develop & Test (Local)

```bash
# Setup
python3 -m venv venv && source venv/bin/activate
pip install -e ".[test]"

# Run tests
./scripts/testing/run_tests.sh fast        # Unit + integration (~30s)
./scripts/testing/run_tests.sh all         # All tests (~80s)

# Run locally
python3 src/main.py --config config/config.yaml --log-level DEBUG
```

---

## ✨ Key Features

- **Automated Detection** - File system monitoring with 60s stability check
- **Flexible Scheduling** - Daily uploads or interval-based (every N hours)
- **Smart Disk Management** - Three-tier deletion: deferred, age-based, emergency
- **Retry Logic** - Exponential backoff up to 10 attempts per file
- **Queue Persistence** - Survives daemon restarts and system reboots
- **Duplicate Prevention** - SHA256-based file registry prevents re-uploads
- **CloudWatch Integration** - Metrics and alarms for monitoring
- **Pattern Matching** - Wildcard support for selective file uploads
- **Recursive Monitoring** - Automatically watches subdirectories
- **Configuration Validation** - SIGHUP signal validates config (restart required to apply changes)

---

## 📖 Documentation

| Document | Description | Audience |
|----------|-------------|----------|
| **[Deployment Guide](docs/deployment_guide.md)** | **START HERE** - Complete vehicle deployment | Operators, DevOps |
| **[Complete Reference](docs/complete_reference.md)** | All features, configuration, examples | All Users |
| **[Testing Guide](docs/autonomous_testing_guide.md)** | Running 400+ automated tests | Developers |
| **[GitHub Actions OIDC](docs/github_actions_oidc_setup.md)** | CI/CD setup without stored credentials | DevOps |

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────┐
│                 TVM Upload Daemon                       │
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
```

**Core Components:**
- **File Monitor** - Detects new files with stability check
- **Queue Manager** - Persistent JSON queue survives restarts
- **Upload Manager** - S3 uploads with retry and multipart support
- **Disk Manager** - Smart deletion policies (deferred, age-based, emergency)
- **CloudWatch Manager** - Metrics publishing and alarms

See [Complete Reference](docs/complete_reference.md) for detailed architecture.

---

## ⚙️ Configuration Highlights

```yaml
# Unique identifier for this vehicle
vehicle_id: "vehicle-CN-001"

# Directories to monitor
log_directories:
  - path: ${HOME}/.parcel/log/terminal
    source: terminal
    recursive: true
    pattern: "*.log"

# S3 configuration
s3:
  bucket: t01logs
  region: cn-north-1
  profile: china

# Upload schedule
upload:
  schedule:
    mode: "interval"        # "daily" or "interval"
    interval_hours: 4       # Upload every 4 hours
  operational_hours:
    enabled: true
    start: "09:00"
    end: "16:00"

# Disk management
deletion:
  after_upload:
    enabled: true
    keep_days: 14          # Keep uploaded files for 14 days
  age_based:
    enabled: true
    max_age_days: 7        # Delete all files older than 7 days
  emergency:
    enabled: true
    threshold_percent: 90  # Emergency cleanup at 90% disk
```

See `config/config.yaml.example` for full configuration options.

---

## 🎯 Pattern Matching

Filter which files to upload using glob patterns. This is crucial for preventing infinite upload loops with active log files.

### Basic Usage

```yaml
log_directories:
  - path: /var/log
    source: syslog
    pattern: "syslog.[1-9]*"  # Only rotated files
    recursive: false
```

**Supported Wildcards:**
- `*` - Matches any characters (e.g., `*.log` matches `app.log`, `system.log`)
- `?` - Matches single character (e.g., `log.?` matches `log.1`, `log.2`)
- `[1-9]` - Matches character range (e.g., `syslog.[1-9]*` matches `syslog.1`, `syslog.2.gz`)

### Critical Use Case: Avoid Active Syslog File

**Problem:** Uploading `/var/log/syslog` creates an infinite loop:
1. Service uploads `/var/log/syslog`
2. Upload writes to syslog: "Uploaded file X"
3. Service detects change, uploads again
4. Repeat forever...

**Solution:** Use pattern to skip active file:

```yaml
log_directories:
  - path: /var/log
    source: syslog
    pattern: "syslog.[1-9]*"  # ✅ Uploads: syslog.1, syslog.2.gz
                               # ❌ Skips: /var/log/syslog (active)
```

### More Examples

```yaml
# Upload only .log files
log_directories:
  - path: ~/.parcel/log/terminal
    source: terminal
    pattern: "*.log"

# Upload compressed logs only
log_directories:
  - path: /var/log
    source: archived
    pattern: "*.gz"

# Upload specific date pattern
log_directories:
  - path: ~/logs
    source: daily
    pattern: "2025-11-*.log"
```

**Important:** If `pattern` is omitted, ALL files in the directory are uploaded.

See [Configuration Reference](./docs/configuration_reference.md#pattern) for detailed pattern syntax and examples.

---

## 🧪 Testing

**400+ automated tests** covering all functionality:

```bash
# Fast local tests (unit + integration)
./scripts/testing/run_tests.sh fast

# Full suite with coverage
./scripts/testing/run_tests.sh all --coverage

# E2E tests (requires AWS)
AWS_PROFILE=china ./scripts/testing/run_tests.sh e2e

# Manual test suite (17 scenarios, end-to-end validation)
./scripts/testing/run_manual_tests.sh
```

**Test Coverage:**
- ✅ 249 unit tests (fast, fully mocked)
- ✅ 90 integration tests (mocked AWS)
- ✅ 60 E2E tests (real AWS S3)
- ✅ 17 manual test scenarios
- ✅ 90%+ code coverage

See [Testing Guide](docs/autonomous_testing_guide.md) for details.

---

## 🔧 Common Operations

### Check Service Status

```bash
sudo systemctl status tvm-upload
sudo journalctl -u tvm-upload -f           # Follow logs
```

### View Queue

```bash
cat /var/lib/tvm-upload/queue.json         # Pending uploads
cat /var/lib/tvm-upload/processed_files.json  # Upload history
```

### Validate and Reload Configuration

```bash
# Edit config
sudo nano /etc/tvm-upload/config.yaml

# Validate configuration (sends SIGHUP)
sudo systemctl reload tvm-upload
# Note: This only validates the config. To apply changes, restart is required:
sudo systemctl restart tvm-upload
```

### Health Check

```bash
./scripts/deployment/health_check.sh       # Verify service health
./scripts/deployment/verify_deployment.sh  # Pre-install validation
```

### Uninstall

```bash
sudo ./scripts/deployment/uninstall.sh     # Clean removal
```

---

## 🐛 Troubleshooting

### Files Not Uploading

**Check operational hours:**
```bash
grep -A 5 "operational_hours" /etc/tvm-upload/config.yaml
date +"%H:%M"  # Current time
```
Immediate uploads only happen within operational hours. Scheduled uploads always run.

**Check queue:**
```bash
cat /var/lib/tvm-upload/queue.json
# Wait 60s after file creation for stability check
```

**Check service:**
```bash
sudo systemctl status tvm-upload
sudo journalctl -u tvm-upload -n 50  # Last 50 log lines
```

### AWS Credentials

```bash
# Verify credentials
./scripts/diagnostics/verify_aws_credentials.sh

# Check profile
aws sts get-caller-identity --profile china
aws s3 ls s3://your-bucket --profile china --region cn-north-1
```

See [Troubleshooting Guide](docs/complete_reference.md#troubleshooting) for more solutions.

---

## 📁 Project Structure

```
tvm-upload/
├── src/                    # Application source code
│   ├── main.py             # Main coordinator
│   ├── config_manager.py   # Configuration
│   ├── file_monitor.py     # File detection
│   ├── upload_manager.py   # S3 uploads
│   ├── disk_manager.py     # Disk management
│   ├── queue_manager.py    # Queue persistence
│   └── cloudwatch_manager.py
├── tests/                  # Test suite (400+ tests)
│   ├── unit/               # Fast unit tests
│   ├── integration/        # Integration tests
│   └── e2e/                # End-to-end tests
├── scripts/
│   ├── deployment/         # install.sh, uninstall.sh, verify_deployment.sh
│   ├── testing/            # run_tests.sh, run_manual_tests.sh
│   ├── diagnostics/        # Troubleshooting tools
│   └── lib/                # Shared libraries
├── docs/                   # Documentation
├── config/                 # Configuration templates
└── systemd/                # systemd service definition
```

---

## 🤝 Contributing

1. **Write tests first** (TDD approach)
2. **Run tests locally**: `./scripts/testing/run_tests.sh fast`
3. **Check coverage**: `./scripts/testing/run_tests.sh all --coverage`
4. **Follow code style**: Type hints, docstrings, `pathlib.Path`
5. **Update docs** if adding features

See [Complete Reference](docs/complete_reference.md) for development guidelines.

---

## 📋 Requirements

- **OS:** Linux (Ubuntu 20.04+, Debian 11+)
- **Python:** 3.10 or higher
- **AWS:** Credentials for China region (cn-north-1 or cn-northwest-1)
- **Disk:** Minimum 100GB recommended for log storage

---

## 📄 License

This project is proprietary software developed by Futu-reADS for internal use.

**Copyright © 2025 Futu-reADS. All rights reserved.**

---

## 🔗 Links

- **Documentation**: [docs/](docs/)
- **Issues**: [GitHub Issues](https://github.com/Futu-reADS/tvm-upload/issues)
- **CI/CD**: [GitHub Actions](https://github.com/Futu-reADS/tvm-upload/actions)

---

**For detailed feature documentation, configuration examples, and troubleshooting, see [Complete Reference](docs/complete_reference.md).**
