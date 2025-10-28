# TVM Upload - Scripts Directory

Organization of scripts by purpose and function.

---

## 📁 Directory Structure

```
scripts/
├── deployment/        # Deployment and installation scripts
├── testing/          # Test execution scripts
├── diagnostics/      # Troubleshooting and diagnostic tools
└── lib/             # Shared libraries and utilities
```

---

## 🚀 Deployment Scripts

Located in `deployment/` - Professional vehicle deployment toolkit

### 1. verify_deployment.sh

**Pre-installation validation** - Checks environment before installation

**Checks:**
- ✅ Configuration file exists and is valid
- ✅ AWS credentials configured
- ✅ AWS profile accessible
- ✅ S3 bucket exists and is writable
- ✅ Python 3.10+ installed
- ✅ Required packages available
- ✅ Log directories exist
- ✅ Sufficient disk space

**Usage:**
```bash
./scripts/deployment/verify_deployment.sh [config_file]
# Default: config/config.yaml
```

**Exit codes:**
- `0` - All checks passed (ready for installation)
- `1` - One or more checks failed

---

### 2. install.sh

**Master installer** - One-command system installation

**What it does:**
1. Runs pre-deployment validation
2. Creates system directories (`/opt/tvm-upload`, `/var/lib/tvm-upload`, `/var/log/tvm-upload`)
3. Installs Python dependencies
4. Copies application files
5. Configures systemd service
6. Enables and starts service

**Usage:**
```bash
sudo ./scripts/deployment/install.sh
```

**Duration:** 2-3 minutes

**Exit codes:**
- `0` - Installation successful
- `1` - Installation failed (see error messages)

**Installation creates:**
- `/opt/tvm-upload/` - Runtime code
- `/etc/tvm-upload/config.yaml` - Configuration
- `/var/lib/tvm-upload/` - Queue and registry data
- `/var/log/tvm-upload/` - Service logs
- `/etc/systemd/system/tvm-upload.service` - systemd service

---

### 3. health_check.sh

**Post-deployment verification** - Ensures system is working correctly

**Checks:**
- ✅ Service is running
- ✅ No recent errors (last 24 hours)
- ✅ Recent uploads succeeded
- ✅ Queue status (pending files)
- ✅ Registry status (uploaded files)
- ✅ Disk space below threshold
- ✅ S3 connectivity
- ✅ Recent uploads visible in S3
- ✅ Configuration valid

**Usage:**
```bash
sudo ./scripts/deployment/health_check.sh
```

**Duration:** ~10 seconds

**Exit codes:**
- `0` - All checks passed (system healthy)
- `>0` - Number of failed checks

**Example output:**
```
╔════════════════════════════════════════════════════════════════╗
║  TVM Upload Health Check - vehicle-CN-001                     ║
╔════════════════════════════════════════════════════════════════╗

Service Status
✓ Service is running (started: 2025-01-27 14:32:15)

Recent Activity
✓ No errors in last 24 hours
✓ 15 successful uploads in last 24 hours

Upload Queue
✓ Queue is empty (all files uploaded)

S3 Connectivity
✓ S3 bucket accessible
✓ Total files in S3: 47

[PASS] System is healthy ✓
```

---

### 4. uninstall.sh

**Clean removal** - Safely removes TVM Upload system

**Options:**
- `--keep-data` - Preserve queue, registry, and logs
- (default) - Remove everything

**Usage:**
```bash
# Complete removal
sudo ./scripts/deployment/uninstall.sh

# Keep data files
sudo ./scripts/deployment/uninstall.sh --keep-data
```

**What it removes:**
1. Stops and disables service
2. Removes systemd service file
3. Removes `/opt/tvm-upload/`
4. Removes `/etc/tvm-upload/` (unless --keep-data)
5. Removes `/var/lib/tvm-upload/` (unless --keep-data)
6. Removes `/var/log/tvm-upload/` (unless --keep-data)

**Duration:** ~30 seconds

**Exit codes:**
- `0` - Uninstallation successful

---

### Typical Deployment Workflow

```bash
# 1. Verify environment
./scripts/deployment/verify_deployment.sh

# 2. Install system
sudo ./scripts/deployment/install.sh

# 3. Verify installation
sudo ./scripts/deployment/health_check.sh
```

**See [docs/deployment_guide.md](../docs/deployment_guide.md) for complete deployment guide.**

---

## 🧪 Testing Scripts

Located in `testing/`

| Script | Purpose | Usage |
|--------|---------|-------|
| **run_tests.sh** | Unified test runner | `./scripts/testing/run_tests.sh [unit\|integration\|e2e\|all]` |
| **run_manual_tests.sh** | Manual test orchestrator | `./scripts/testing/run_manual_tests.sh` |
| **test_s3_upload.py** | S3 upload test utility | Used by test scripts |
| **test_watchdog_debug.py** | Watchdog debugging utility | Used for troubleshooting |
| **manual-tests/** | 16 individual test scenarios | See `manual-tests/README.md` |

### Testing Workflow

```bash
# Quick test (unit tests only)
./scripts/testing/run_tests.sh unit

# Full test suite
./scripts/testing/run_tests.sh all

# Run specific manual tests
./scripts/testing/run_manual_tests.sh config/config.yaml "1 2 3"
```

### Manual Test Scenarios

Located in `testing/manual-tests/`

| Test | Name | Duration |
|------|------|----------|
| 01 | Basic File Upload | 10 min |
| 02 | Source-Based Path Detection | 5 min |
| 03 | File Date Preservation | 5 min |
| 04 | CloudWatch Metrics | 10 min |
| 05 | CloudWatch Alarms | 5 min |
| 06 | Duplicate Prevention | 10 min |
| 07 | Disk Space Management | 15 min |
| 08 | Batch Upload Performance | 10 min |
| 09 | Large File Upload | 10 min |
| 10 | Error Handling & Retry | 15 min |
| 11 | Operational Hours | 10 min |
| 12 | Service Restart Resilience | 10 min |
| 13 | Pattern Matching | 5 min |
| 14 | Recursive Monitoring | 5 min |
| 15 | Startup Scan | 10 min |
| 16 | Emergency Cleanup | 10 min |

See `testing/manual-tests/README.md` for detailed information.

---

## 🔍 Diagnostic Scripts

Located in `diagnostics/`

| Script | Purpose | Usage |
|--------|---------|-------|
| **verify_aws_credentials.sh** | AWS permissions troubleshooting | `./scripts/diagnostics/verify_aws_credentials.sh` |

### When to Use Diagnostics

Use `verify_aws_credentials.sh` when:
- ❓ Uploads are failing with AWS errors
- ❓ Need to verify S3 permissions
- ❓ CloudWatch metrics not publishing
- ❓ Testing AWS connectivity
- ❓ Debugging IAM policy issues

**Output includes:**
- AWS CLI installation check
- Credentials file validation
- S3 bucket access test
- S3 write permission test
- CloudWatch metrics test
- CloudWatch alarms test

---

## 📚 Library Scripts

Located in `lib/`

| Script | Purpose | Usage |
|--------|---------|-------|
| **create_test_config.sh** | Generate test configuration | Used by test scripts |
| **test_helpers.sh** | Common test functions | Sourced by other scripts |

**Note:** These are utility libraries, not meant to be run directly.

---

## 💡 Quick Reference

### I want to...

| Task | Command |
|------|---------|
| Install the system | `sudo ./scripts/deployment/install.sh` |
| Check if environment is ready | `./scripts/deployment/verify_deployment.sh` |
| Remove the system | `sudo ./scripts/deployment/uninstall.sh` |
| Check system health | `sudo ./scripts/deployment/health_check.sh` |
| Run all tests | `./scripts/testing/run_tests.sh all` |
| Run only unit tests | `./scripts/testing/run_tests.sh unit` |
| Run manual tests | `./scripts/testing/run_manual_tests.sh` |
| Debug AWS issues | `./scripts/diagnostics/verify_aws_credentials.sh` |

---

## 🔧 Script Development Guidelines

### Adding New Scripts

1. **Choose the right directory:**
   - `deployment/` - Installation, setup, teardown
   - `testing/` - Test execution, validation
   - `diagnostics/` - Troubleshooting, debugging
   - `lib/` - Reusable functions

2. **Follow naming conventions:**
   - Use underscores: `my_script.sh`
   - Be descriptive: `verify_aws_permissions.sh` not `check.sh`
   - Add `.sh` extension for shell scripts
   - Add `.py` extension for Python scripts

3. **Make scripts executable:**
   ```bash
   chmod +x scripts/category/my_script.sh
   ```

4. **Add documentation:**
   - Update this README.md
   - Add comments in the script
   - Include usage examples

5. **Use absolute paths:**
   ```bash
   SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
   PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
   ```

---

## 📖 Related Documentation

- **[deployment_guide.md](../docs/deployment_guide.md)** - Complete deployment guide
- **[manual_testing_guide.md](../docs/manual_testing_guide.md)** - Manual testing procedures
- **[autonomous_testing_guide.md](../docs/autonomous_testing_guide.md)** - Automated testing guide

---

**Last Updated:** January 2025
**Maintained By:** TVM Upload Team
