# TVM Upload System - Configuration Reference

**Version:** 1.0
**Last Updated:** 2025-11-06
**Target Audience:** System administrators, DevOps engineers

---

## Overview

This document provides a complete reference for all configuration parameters in the TVM Upload System. For quick start, see [Deployment Guide](./deployment_guide.md).

**Configuration File Location:**
- Development: `config/config.yaml`
- Production: `/etc/tvm-upload/config.yaml`

---

## Table of Contents

1. [Vehicle Identification](#vehicle-identification)
2. [Log Directories](#log-directories)
3. [AWS S3 Configuration](#aws-s3-configuration)
4. [Upload Settings](#upload-settings)
5. [Deletion Policies](#deletion-policies)
6. [Disk Management](#disk-management)
7. [Monitoring](#monitoring)
8. [Complete Example](#complete-example)

---

## Vehicle Identification

### `vehicle_id`

**Type:** String
**Required:** Yes
**Default:** None
**Validation:** Must be non-empty string

**Description:** Unique identifier for this vehicle. Used as the root folder in S3.

**Format Recommendation:** `vehicle-{region}-{number}`

**Examples:**
```yaml
vehicle_id: "vehicle-CN-001"
vehicle_id: "vehicle-CN-002"
vehicle_id: "vehicle-JP-001"
```

**S3 Structure:**
```
s3://t01logs/
  └── vehicle-CN-001/
      └── 2025-11-06/
          ├── terminal/
          ├── ros/
          └── syslog/
```

**⚠️ Important:** Must be unique across all vehicles. Duplicate IDs will cause file conflicts in S3.

---

## Log Directories

### `log_directories`

**Type:** List of objects
**Required:** Yes
**Default:** None
**Validation:** Must have at least one directory

**Description:** List of directories to monitor for log files. Each directory becomes a "source" in S3 organization.

---

### Directory Object Structure

Each directory entry supports these fields:

#### `path`

**Type:** String
**Required:** Yes
**Environment Variables:** Supported (`${HOME}`, `${USER}`, `~`)

**Description:** Local filesystem path to monitor.

**Examples:**
```yaml
path: /var/log                      # Absolute path
path: ${HOME}/.ros/log              # Environment variable
path: ~/.parcel/log/terminal        # Tilde expansion
path: /home/${USER}/logs            # Variable in middle
```

**Validation:** Must be non-empty string. Directory doesn't need to exist at startup (can be created later).

---

#### `source`

**Type:** String
**Required:** Yes
**Validation:** Only letters, numbers, underscores (`a-zA-Z0-9_`)

**Description:** Source name for S3 folder organization. Each source must be unique.

**Examples:**
```yaml
source: terminal    # → s3://bucket/vehicle-id/date/terminal/
source: ros         # → s3://bucket/vehicle-id/date/ros/
source: syslog      # → s3://bucket/vehicle-id/date/syslog/
source: ros2        # → s3://bucket/vehicle-id/date/ros2/
```

**⚠️ Important:** Source names must be unique. Duplicate sources will cause validation error.

---

#### `pattern`

**Type:** String
**Required:** No
**Default:** `*` (all files)

**Description:** Glob pattern to filter which files to upload. If omitted, ALL files are uploaded.

**Wildcard Support:**
- `*` - Matches any characters (including none)
- `?` - Matches exactly one character
- `[...]` - Matches any character in brackets

**Examples:**
```yaml
# Upload only rotated syslog files (not active syslog)
pattern: "syslog.[1-9]*"  # Matches: syslog.1, syslog.2.gz, etc.

# Upload only log files
pattern: "*.log"          # Matches: error.log, debug.log, app.log

# Upload ROS bag files
pattern: "*.mcap"         # Matches: recording.mcap, data_001.mcap

# Upload files with specific prefix
pattern: "test_*"         # Matches: test_run1.log, test_data.txt

# Upload files with date pattern
pattern: "2024-*"         # Matches: 2024-11-06.log, 2024-data.txt

# Upload compressed files
pattern: "*.gz"           # Matches: log.gz, data.tar.gz
```

**Use Cases:**

1. **Avoid Active Files:**
```yaml
- path: /var/log
  source: syslog
  pattern: "syslog.[1-9]*"  # Skip active /var/log/syslog
```

2. **Specific File Types:**
```yaml
- path: ~/recordings
  source: bags
  pattern: "*.mcap"         # Only MCAP files
```

3. **Dated Files:**
```yaml
- path: ~/logs
  source: app
  pattern: "app-2024-*.log" # Only 2024 logs
```

---

#### `recursive`

**Type:** Boolean
**Required:** No
**Default:** `true`

**Description:** Whether to monitor subdirectories.

**Values:**
- `true` - Monitor subdirectories (default)
- `false` - Only monitor top-level directory

**Examples:**
```yaml
# ROS logs: Include subdirectories (important for ROS folder structure)
- path: ~/.ros/log
  source: ros
  recursive: true           # Monitors ~/.ros/log/run_001/, etc.

# System logs: Exclude subdirectories (avoid system folders)
- path: /var/log
  source: syslog
  recursive: false          # Only /var/log, not /var/log/apt/, etc.
```

**Use Cases:**

1. **ROS Logs (recursive: true):**
```
~/.ros/log/
  ├── run_001/
  │   ├── rosout.log
  │   └── roscore.log
  └── run_002/
      └── rosout.log
```
All files uploaded, structure preserved in S3.

2. **System Logs (recursive: false):**
```
/var/log/
  ├── syslog          ← Monitored
  ├── syslog.1        ← Monitored
  ├── apt/            ← Ignored (subdirectory)
  └── journal/        ← Ignored (subdirectory)
```
Only top-level files uploaded.

---

### Complete Directory Examples

```yaml
log_directories:
  # Terminal logs: Simple monitoring
  - path: ${HOME}/.parcel/log/terminal
    source: terminal
    recursive: true
    # No pattern → Upload all files

  # ROS logs: Preserve structure
  - path: ${HOME}/.ros/log
    source: ros
    recursive: true
    # No pattern → Upload all files, keep folder structure

  # System logs: Filtered and non-recursive
  - path: /var/log
    source: syslog
    pattern: "syslog.[1-9]*"
    recursive: false

  # ROS2 logs: Include subdirectories
  - path: ${HOME}/ros2_ws/log
    source: ros2
    recursive: true
    # No pattern → Upload all files

  # Custom application logs
  - path: /opt/myapp/logs
    source: application
    pattern: "*.log"
    recursive: false
```

---

## AWS S3 Configuration

### `s3`

**Type:** Object
**Required:** Yes

Container for AWS S3 settings.

---

### `s3.bucket`

**Type:** String
**Required:** Yes
**Validation:** Valid S3 bucket name

**Description:** S3 bucket name for log storage.

**Example:**
```yaml
s3:
  bucket: t01logs
```

**⚠️ Important:** Bucket must exist in specified region before deployment.

---

### `s3.region`

**Type:** String
**Required:** Yes
**Valid Values:** Any AWS region, typically AWS China regions

**Description:** AWS region where S3 bucket is located.

**AWS China Regions:**
- `cn-north-1` - Beijing
- `cn-northwest-1` - Ningxia

**Examples:**
```yaml
s3:
  region: cn-north-1        # Beijing
  region: cn-northwest-1    # Ningxia
```

---

### `s3.credentials_path`

**Type:** String
**Required:** No
**Default:** `${HOME}/.aws`
**Environment Variables:** Supported

**Description:** Path to AWS credentials directory.

**Directory Should Contain:**
- `credentials` - AWS access keys
- `config` - AWS configuration (region, endpoint)

**Examples:**
```yaml
s3:
  credentials_path: ${HOME}/.aws          # Default
  credentials_path: /etc/tvm-upload/aws   # Custom location
```

---

### `s3.profile`

**Type:** String
**Required:** Yes
**Default:** None

**Description:** AWS CLI profile name to use for authentication.

**Example:**
```yaml
s3:
  profile: china            # Uses [china] profile
```

**Credentials File Structure:**
```ini
# ~/.aws/credentials
[china]
aws_access_key_id = YOUR_ACCESS_KEY
aws_secret_access_key = YOUR_SECRET_KEY

# ~/.aws/config
[profile china]
region = cn-north-1
output = json
s3 =
    endpoint_url = https://s3.cn-north-1.amazonaws.com.cn
    signature_version = s3v4
    addressing_style = path
```

---

## Upload Settings

### `upload`

**Type:** Object
**Required:** Yes

Container for upload behavior settings.

---

### `upload.file_stable_seconds`

**Type:** Integer
**Required:** No
**Default:** 60
**Range:** 1-600

**Description:** How long (in seconds) to wait after last file modification before considering file "stable" and ready for upload.

**Purpose:** Prevents uploading incomplete files that are still being written.

**Examples:**
```yaml
upload:
  file_stable_seconds: 60    # Default (recommended)
  file_stable_seconds: 30    # Faster uploads, risk of incomplete files
  file_stable_seconds: 120   # Safer for slow writes
```

**Recommendations:**
- **Terminal logs:** 30-60 seconds (small files, written quickly)
- **ROS bags:** 120+ seconds (large files, written slowly)
- **System logs:** 60 seconds (standard)

---

### `upload.upload_on_start`

**Type:** Boolean
**Required:** No
**Default:** `true`

**Description:** Whether to upload queued files immediately when service starts.

**Behavior:**
- `true` - Upload queue immediately after service starts (within operational hours)
- `false` - Wait for next scheduled upload time

**Examples:**
```yaml
upload:
  upload_on_start: true      # Default (recommended)
  upload_on_start: false     # Wait for schedule
```

**Use Cases:**
- `true` - Production (upload ASAP after vehicle WiFi connects)
- `false` - Testing (controlled upload timing)

---

### `upload.queue_file`

**Type:** String
**Required:** No
**Default:** `/var/lib/tvm-upload/queue.json`

**Description:** Path to persistent upload queue file.

**Example:**
```yaml
upload:
  queue_file: /var/lib/tvm-upload/queue.json   # Default
  queue_file: /tmp/test_queue.json             # Testing
```

**File Format:**
```json
{
  "files": [
    {
      "filepath": "/var/log/syslog.1",
      "added_at": 1699200000,
      "retry_count": 0
    }
  ]
}
```

---

### `upload.schedule`

**Type:** Object
**Required:** Yes

Defines when and how often uploads occur.

---

### `upload.schedule.mode`

**Type:** String
**Required:** Yes
**Valid Values:** `interval`, `daily`

**Description:** Upload scheduling mode.

**Values:**

**`interval` Mode:**
Upload every N hours, starting from service start time.

```yaml
upload:
  schedule:
    mode: interval
    interval_hours: 2       # Upload every 2 hours
```

**Schedule Example** (service started at 10:00 AM):
- 10:00 AM - Service starts
- 12:00 PM - First upload
- 2:00 PM - Second upload
- 4:00 PM - Third upload
- Continues every 2 hours...

**`daily` Mode:**
Upload once per day at specific time.

```yaml
upload:
  schedule:
    mode: daily
    time: "02:00"          # Upload at 2:00 AM daily
```

**Recommendations:**
- **`interval`** - Production (ensures regular uploads regardless of start time)
- **`daily`** - Low-bandwidth scenarios (single daily upload)

---

### `upload.schedule.interval_hours`

**Type:** Integer/Float
**Required:** When `mode: interval`
**Range:** 0.25-24

**Description:** Hours between scheduled uploads (interval mode only).

**Examples:**
```yaml
upload:
  schedule:
    mode: interval
    interval_hours: 2      # Every 2 hours
    interval_hours: 0.5    # Every 30 minutes
    interval_hours: 24     # Once per day
```

---

### `upload.schedule.time`

**Type:** String (HH:MM)
**Required:** When `mode: daily`
**Format:** 24-hour time

**Description:** Daily upload time (daily mode only).

**Examples:**
```yaml
upload:
  schedule:
    mode: daily
    time: "02:00"          # 2:00 AM
    time: "14:30"          # 2:30 PM
```

---

### `upload.operational_hours`

**Type:** Object
**Required:** No

Restricts immediate uploads to specific time window.

**Purpose:** Avoid uploading during high-bandwidth activities (driving, recording).

---

### `upload.operational_hours.enabled`

**Type:** Boolean
**Required:** No
**Default:** `true`

**Description:** Whether to enforce operational hours.

**Behavior:**
- `true` - Immediate uploads only within hours
- `false` - Immediate uploads anytime

---

### `upload.operational_hours.start`

**Type:** String (HH:MM)
**Required:** When `enabled: true`

**Description:** Start of operational hours window.

---

### `upload.operational_hours.end`

**Type:** String (HH:MM)
**Required:** When `enabled: true`

**Description:** End of operational hours window.

**Complete Example:**
```yaml
upload:
  operational_hours:
    enabled: true
    start: "09:00"         # 9:00 AM
    end: "16:00"           # 4:00 PM
```

**Behavior:**
- **Within hours (9 AM - 4 PM):** Files upload immediately (if batch_upload enabled)
- **Outside hours:** Files queued, upload at next scheduled time
- **Scheduled uploads:** Run regardless of operational hours

---

### `upload.batch_upload`

**Type:** Object
**Required:** No

Controls whether entire queue uploads when one file is ready.

---

### `upload.batch_upload.enabled`

**Type:** Boolean
**Required:** No
**Default:** `true`

**Description:** When one file is ready, upload entire queue (within operational hours).

**Behavior:**
- `true` - Upload all queued files when one file ready
- `false` - Upload only the ready file

**Examples:**
```yaml
upload:
  batch_upload:
    enabled: true          # Default (recommended)
```

**Recommendation:** Keep `true` for efficiency (fewer S3 connections).

---

### `upload.scan_existing_files`

**Type:** Object
**Required:** No

Controls startup scan behavior (upload existing files when service starts).

---

### `upload.scan_existing_files.enabled`

**Type:** Boolean
**Required:** No
**Default:** `true`

**Description:** Whether to scan for existing files on service startup.

---

### `upload.scan_existing_files.max_age_days`

**Type:** Integer/Float
**Required:** When `enabled: true`
**Default:** 3
**Range:** 0-365

**Description:** Maximum age (in days) of files to upload during startup scan.

**Special Values:**
- `0` - Upload ALL files (no age limit)
- `> 0` - Only files modified within last N days

**Examples:**
```yaml
upload:
  scan_existing_files:
    enabled: true
    max_age_days: 3        # Last 3 days (default)
    max_age_days: 7        # Last week
    max_age_days: 0        # All files
```

**Use Cases:**
- `3` - Standard (avoid old logs)
- `7` - After long offline period
- `0` - Initial deployment (upload everything)

---

### `upload.processed_files_registry`

**Type:** Object
**Required:** No

Controls duplicate prevention registry.

---

### `upload.processed_files_registry.registry_file`

**Type:** String
**Required:** No
**Default:** `/var/lib/tvm-upload/processed_files.json`

**Description:** Path to registry file tracking uploaded files.

---

### `upload.processed_files_registry.retention_days`

**Type:** Integer
**Required:** No
**Default:** 30
**Range:** 1-365

**Description:** How long to keep entries in registry before cleanup.

**Example:**
```yaml
upload:
  processed_files_registry:
    registry_file: /var/lib/tvm-upload/processed_files.json
    retention_days: 30     # Keep 30 days of history
```

---

## Deletion Policies

### `deletion`

**Type:** Object
**Required:** No

Controls when and how to delete uploaded files locally.

---

### `deletion.after_upload`

**Type:** Object
**Required:** No

Delete files after successful upload.

---

### `deletion.after_upload.enabled`

**Type:** Boolean
**Required:** No
**Default:** `true`

---

### `deletion.after_upload.keep_days`

**Type:** Integer
**Required:** When `enabled: true`
**Default:** 14
**Range:** 0-365

**Description:** Days to keep files after upload before deletion.

**Special Values:**
- `0` - Delete immediately after upload
- `> 0` - Keep N days after upload

**Examples:**
```yaml
deletion:
  after_upload:
    enabled: true
    keep_days: 14          # Default (recommended)
    keep_days: 0           # Immediate deletion (saves space)
    keep_days: 30          # Extra safety margin
```

---

### `deletion.age_based`

**Type:** Object
**Required:** No

Delete old files regardless of upload status.

---

### `deletion.age_based.enabled`

**Type:** Boolean
**Required:** No
**Default:** `false`

---

### `deletion.age_based.max_age_days`

**Type:** Integer
**Required:** When `enabled: true`
**Range:** 1-365

**Description:** Delete files older than N days.

---

### `deletion.age_based.schedule_time`

**Type:** String (HH:MM)
**Required:** When `enabled: true`

**Description:** Daily time to run age-based cleanup.

**Example:**
```yaml
deletion:
  age_based:
    enabled: true
    max_age_days: 7
    schedule_time: "02:00"  # 2:00 AM daily
```

---

### `deletion.emergency`

**Type:** Object
**Required:** No

Emergency cleanup when disk space critical.

---

### `deletion.emergency.enabled`

**Type:** Boolean
**Required:** No
**Default:** `false`

---

### `deletion.emergency.threshold`

**Type:** Float
**Required:** When `enabled: true`
**Range:** 0.01-0.99

**Description:** Disk usage percentage that triggers emergency cleanup.

**Example:**
```yaml
deletion:
  emergency:
    enabled: true
    threshold: 0.95        # 95% full
```

---

## Disk Management

### `disk`

**Type:** Object
**Required:** Yes

Disk space monitoring settings.

---

### `disk.reserved_gb`

**Type:** Integer/Float
**Required:** Yes
**Range:** 1-1000

**Description:** Minimum GB to keep free. Triggers warnings/emergency cleanup.

**Example:**
```yaml
disk:
  reserved_gb: 5            # Keep 5 GB free
```

---

### `disk.warning_threshold`

**Type:** Float
**Required:** No
**Default:** 0.85
**Range:** 0.01-0.99

**Description:** Disk usage percentage that triggers warnings.

---

### `disk.critical_threshold`

**Type:** Float
**Required:** No
**Default:** 0.95
**Range:** 0.01-0.99

**Description:** Disk usage percentage considered critical.

**Example:**
```yaml
disk:
  reserved_gb: 5
  warning_threshold: 0.85   # Warn at 85%
  critical_threshold: 0.95  # Critical at 95%
```

---

## Monitoring

### `monitoring`

**Type:** Object
**Required:** No

CloudWatch monitoring settings.

---

### `monitoring.cloudwatch_enabled`

**Type:** Boolean
**Required:** No
**Default:** `true`

**Description:** Whether to publish metrics to CloudWatch.

---

### `monitoring.publish_interval_seconds`

**Type:** Integer
**Required:** No
**Default:** 3600 (1 hour)

**Description:** How often to publish metrics (seconds).

**Example:**
```yaml
monitoring:
  cloudwatch_enabled: true
  publish_interval_seconds: 3600  # Every hour
```

**Metrics Published:**
- `BytesUploaded`
- `FileCount`
- `FailureCount`
- `DiskUsagePercent`

---

## Complete Example

```yaml
# Vehicle Identification
vehicle_id: "vehicle-CN-001"

# Log Directories
log_directories:
  - path: ${HOME}/.parcel/log/terminal
    source: terminal
    recursive: true

  - path: ${HOME}/.ros/log
    source: ros
    recursive: true

  - path: /var/log
    source: syslog
    pattern: "syslog.[1-9]*"
    recursive: false

  - path: ${HOME}/ros2_ws/log
    source: ros2
    recursive: true

# AWS S3
s3:
  bucket: t01logs
  region: cn-north-1
  credentials_path: ${HOME}/.aws
  profile: china

# Upload Settings
upload:
  file_stable_seconds: 60
  upload_on_start: true
  queue_file: /var/lib/tvm-upload/queue.json

  schedule:
    mode: interval
    interval_hours: 2

  operational_hours:
    enabled: true
    start: "09:00"
    end: "16:00"

  batch_upload:
    enabled: true

  scan_existing_files:
    enabled: true
    max_age_days: 3

  processed_files_registry:
    registry_file: /var/lib/tvm-upload/processed_files.json
    retention_days: 30

# Deletion Policies
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
    threshold: 0.95

# Disk Management
disk:
  reserved_gb: 5
  warning_threshold: 0.85
  critical_threshold: 0.95

# Monitoring
monitoring:
  cloudwatch_enabled: true
  publish_interval_seconds: 3600
```

---

## Related Documentation

- [Deployment Guide](./deployment_guide.md) - Initial setup
- [Error Handling Guide](./error_handling_guide.md) - Troubleshooting
- [Complete Reference](./complete_reference.md) - Feature overview

---

**Document Version:** 1.0
**Last Updated:** 2025-11-06
**Maintained By:** TVM Upload Team

### Changelog
- **v1.0** (2025-11-06): Initial comprehensive configuration reference with all parameters documented
