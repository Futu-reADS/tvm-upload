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

Located in `deployment/`

| Script | Purpose | Usage |
|--------|---------|-------|
| **install.sh** | Install TVM Upload system | `sudo ./scripts/deployment/install.sh` |
| **uninstall.sh** | Remove TVM Upload system | `sudo ./scripts/deployment/uninstall.sh` |
| **verify_deployment.sh** | Pre-installation validation | `./scripts/deployment/verify_deployment.sh` |
| **health_check.sh** | Post-installation health check | `sudo ./scripts/deployment/health_check.sh` |

### Typical Deployment Workflow

```bash
# 1. Verify environment
./scripts/deployment/verify_deployment.sh

# 2. Install system
sudo ./scripts/deployment/install.sh

# 3. Verify installation
sudo ./scripts/deployment/health_check.sh
```

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

- **[DEPLOYMENT_GUIDE.md](../docs/DEPLOYMENT_GUIDE.md)** - Complete deployment guide
- **[MANUAL_TESTING_GUIDE.md](../docs/MANUAL_TESTING_GUIDE.md)** - Manual testing procedures
- **[AUTONOMOUS_TESTING_GUIDE.md](../docs/AUTONOMOUS_TESTING_GUIDE.md)** - Automated testing guide

---

**Last Updated:** January 2025
**Maintained By:** TVM Upload Team
