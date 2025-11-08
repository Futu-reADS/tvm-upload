# Changelog

All notable changes to the TVM Log Upload System will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Project structure improvements (CHANGELOG.md, LICENSE, .editorconfig, Makefile)

## [2.1.0] - 2025-11-08

### Added
- Interval-based upload scheduling (every N hours/minutes) as alternative to daily schedule
- Batch upload optimization with registry checkpointing for large upload batches
- Permanent upload error handling with queue management (prevents retry of unrecoverable errors)
- MD5 caching for performance optimization during upload verification
- Source-based S3 organization (terminal/ros/syslog/ros2) for better file categorization
- 17 comprehensive manual test scenarios for production validation
- Upload verification with date range search (±5 days for non-syslog files)
- Startup upload option (`upload_on_start`) for immediate queue processing on service start
- Pattern matching support for selective file uploads (wildcard support)
- Recursive directory monitoring with configurable depth

### Changed
- Modernized to `pyproject.toml` (PEP 518/621), removed `setup.py` and `requirements.txt`
- Standardized version to v2.1.0 across all files (pyproject.toml, src/main.py)
- Updated test counts: 416 total tests (249 unit + 90 integration + 60 E2E + 17 manual)
- Improved test pyramid distribution (60% unit tests, approaching ideal 70% ratio)

### Added
- `pyproject.toml` - Modern Python project configuration (single source of truth)
- `Makefile` - 25+ development automation commands
- `CONTRIBUTING.md` - Comprehensive contribution guidelines
- `.editorconfig` - Consistent code style across editors
- `.pre-commit-config.yaml` - Automated code quality checks
- `LICENSE` - Proprietary software license
- GitHub issue and PR templates for better collaboration
- Enhanced documentation with accurate test counts and version numbers
- Refactored upload manager to use source-based S3 key generation
- Improved file identity tracking with mtime-based verification

### Fixed
- Startup scan edge case: files modified within 2 minutes before service start
- Double registry marking in batch upload mode (prevented duplicate entries)
- File stability checks during upload process
- Queue cleanup on startup (removes entries for missing files)
- Configuration validation for interval scheduling mode

## [2.0.0] - 2025-10-15

### Added
- Three-tier deletion policies:
  - Deferred deletion: Keep uploaded files for N days (configurable)
  - Age-based cleanup: Delete all files older than N days (scheduled daily)
  - Emergency cleanup: Delete oldest uploaded files when disk >90% full
- Processed files registry for duplicate prevention (SHA256-based tracking)
- Pattern matching for selective file uploads using glob patterns
- Recursive directory monitoring with configurable enable/disable
- CloudWatch metrics integration for monitoring upload success/failures
- Configuration validation with SIGHUP signal (validates config without restart)
- Disk usage monitoring with warning/critical thresholds
- Upload verification to prevent duplicate uploads to S3

### Changed
- Refactored disk management system with pattern-aware deletion
- Enhanced error handling with permanent vs temporary error classification
- Improved logging with structured output and severity levels
- Optimized queue management with batch retrieval and filtering
- Updated configuration schema to support deletion policies

### Fixed
- Memory leak in file monitor startup scan
- Race condition in queue persistence during high file volume
- Incorrect S3 key generation for files with special characters
- AWS China endpoint configuration issues

### Security
- Added system directory protection (hard-coded safeguard for /var, /etc, /usr)
- Implemented 4-layer deletion safety system to prevent accidental file deletion

## [1.0.0] - 2025-09-01

### Added
- Initial release of TVM Log Upload System
- Basic log file upload functionality to AWS S3 China region
- S3 integration with support for cn-north-1 and cn-northwest-1 regions
- Queue persistence with JSON storage (survives daemon restarts)
- systemd service integration for automatic startup on boot
- File monitoring with watchdog library
- Exponential backoff retry logic (up to 10 attempts)
- Multipart upload support for large files (>5MB)
- AWS profile-based authentication support
- Configuration management with YAML format
- Basic logging with configurable log levels
- Health check scripts for deployment validation

### Documentation
- README.md with quick start guide
- Deployment guide for production vehicles
- Configuration reference with all available options
- Testing guide for unit and integration tests

---

## Version History Summary

- **v2.1.0** (2025-11-08): Interval scheduling, performance optimizations, expanded test coverage
- **v2.0.0** (2025-10-15): Deletion policies, duplicate prevention, pattern matching
- **v1.0.0** (2025-09-01): Initial release with core upload functionality

---

## Upgrade Notes

### Upgrading to 2.1.0 from 2.0.0

**Breaking Changes:** None

**New Features:**
- Can now use interval-based scheduling instead of daily uploads
- Upload on service start is now configurable
- Better performance with MD5 caching

**Configuration Changes:**
```yaml
# New optional configuration in upload.schedule
upload:
  schedule:
    mode: "interval"  # NEW: Can be "daily" or "interval"
    interval_hours: 2
    interval_minutes: 0

  # NEW: Control upload behavior on service start
  upload_on_start: true  # Default: true
```

**Migration Steps:**
1. Update code: `git pull origin main`
2. Review new config options in `config/config.yaml.example`
3. Update your `config.yaml` if using interval scheduling
4. Restart service: `sudo systemctl restart tvm-upload`

### Upgrading to 2.0.0 from 1.0.0

**Breaking Changes:**
- Configuration schema changed (added deletion policies)
- Queue file format updated (automatic migration on first run)

**New Features:**
- Three-tier deletion policies
- Duplicate prevention with processed files registry
- Pattern matching for file selection

**Configuration Changes:**
```yaml
# NEW sections in config.yaml
deletion:
  after_upload:
    enabled: true
    keep_days: 14
  age_based:
    enabled: true
    max_age_days: 7
    schedule_time: "02:00"
  emergency:
    enabled: true

upload:
  processed_files_registry:
    registry_file: /var/lib/tvm-upload/processed_files.json
    retention_days: 30
```

**Migration Steps:**
1. Backup existing config: `cp /etc/tvm-upload/config.yaml /etc/tvm-upload/config.yaml.backup`
2. Update code: `git pull origin main`
3. Merge new config sections from `config/config.yaml.example`
4. Test config: `python3 src/main.py --config /etc/tvm-upload/config.yaml --test-config`
5. Restart service: `sudo systemctl restart tvm-upload`

---

## Links

- [GitHub Repository](https://github.com/Futu-reADS/tvm-upload)
- [Documentation](docs/)
- [Issue Tracker](https://github.com/Futu-reADS/tvm-upload/issues)
