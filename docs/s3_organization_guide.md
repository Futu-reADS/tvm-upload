# TVM Upload System - S3 Organization Guide

**Version:** 1.0
**Last Updated:** 2025-11-06
**Target Audience:** System administrators, Data analysts

---

## Overview

This guide explains how the TVM Upload System organizes files in S3, including date handling, folder structure, and search behavior.

---

## S3 Folder Structure

### Basic Structure

```
s3://t01logs/
└── {vehicle_id}/
    └── {date}/
        └── {source}/
            └── {filename}
```

### Real Example

```
s3://t01logs/
└── vehicle-CN-001/
    ├── 2025-11-05/
    │   ├── terminal/
    │   │   ├── session_20251105_093000.log
    │   │   └── session_20251105_140000.log
    │   ├── ros/
    │   │   └── run_001/
    │   │       ├── rosout.log
    │   │       └── roscore.log
    │   └── syslog/
    │       ├── syslog.1
    │       └── syslog.2.gz
    └── 2025-11-06/
        ├── terminal/
        │   └── session_20251106_090000.log
        └── ros/
            └── run_002/
                └── rosout.log
```

---

## Date Handling

### Primary Date Source: File Modification Time

**The date folder comes from the file's modification time (mtime), NOT:**
- Upload time
- Current date
- Filename date
- Folder name date

**Example:**
```bash
# File created on Nov 5, uploaded on Nov 7
-rw-r--r-- 1 user user 1024 Nov  5 14:30 test.log

# S3 location:
s3://t01logs/vehicle-CN-001/2025-11-05/terminal/test.log
#                            ^^^^^^^^^^^
#                            From file mtime
```

### Why Modification Time?

**Advantages:**
- Preserves original log timing
- Handles delayed uploads correctly
- Works even if vehicle offline for days
- Organizes logs by when events occurred, not when uploaded

**Example Scenario:**
1. Vehicle records logs on Monday (Nov 5)
2. Vehicle offline Tuesday-Thursday (no WiFi)
3. Vehicle uploads Friday (Nov 9)
4. **Result:** Logs stored in Monday's folder (2025-11-05), reflecting actual event time

---

## Search Range for Duplicate Detection

### ±5 Day Search Window

When checking if a file already exists in S3, the system searches **±5 days** around the file's modification time.

**Example:**
- File mtime: November 6, 2025
- Search range: November 1 through November 11

**Why This Matters:**

### Scenario 1: Clock Drift

```
# Vehicle clock slightly wrong
File mtime: Nov 6 (incorrect clock)
Upload date: Nov 7 (correct clock after sync)

# System searches: Nov 1 - Nov 11
# Finds existing file even if date differs by 1 day
```

### Scenario 2: Delayed Upload

```
# File created, WiFi unavailable for a week
File created: Nov 1 (mtime preserved)
Upload attempt 1: Nov 8 (fails, queued)
Upload attempt 2: Nov 9 (succeeds)

# System searches: Oct 27 - Nov 6
# Avoids duplicate if file was uploaded during first attempt
```

### Scenario 3: Timezone Issues

```
# File created in different timezone
File mtime: Nov 6 23:00 (UTC)
Local time: Nov 7 01:00 (UTC+2)

# Search range handles timezone differences
```

---

## Source Organization

### What is a Source?

A "source" is a log category defined in configuration. Each source becomes a folder in S3.

**Configuration:**
```yaml
log_directories:
  - path: ~/.parcel/log/terminal
    source: terminal          # ← Source name

  - path: ~/.ros/log
    source: ros               # ← Source name

  - path: /var/log
    source: syslog            # ← Source name
```

**S3 Result:**
```
vehicle-CN-001/
└── 2025-11-06/
    ├── terminal/         # ← From source: terminal
    ├── ros/              # ← From source: ros
    └── syslog/           # ← From source: syslog
```

---

## ROS Folder Structure Preservation

### Special Handling for ROS Logs

ROS logs often have nested folder structures. The system preserves this structure in S3.

**Local Structure:**
```
~/.ros/log/
└── run_20251106_090000_abc123/
    ├── rosout.log
    ├── roscore.log
    └── node_manager.log
```

**S3 Structure:**
```
vehicle-CN-001/
└── 2025-11-06/
    └── ros/
        └── run_20251106_090000_abc123/   # ← Folder preserved!
            ├── rosout.log
            ├── roscore.log
            └── node_manager.log
```

**Configuration:**
```yaml
log_directories:
  - path: ~/.ros/log
    source: ros
    recursive: true           # ← Crucial for preserving structure!
```

### Without Recursive: True

If `recursive: false`, only top-level files are uploaded:

**Local:**
```
~/.ros/log/
├── toplevel.log              # ← Uploaded
└── run_001/
    └── rosout.log            # ← Ignored!
```

**S3:**
```
vehicle-CN-001/
└── 2025-11-06/
    └── ros/
        └── toplevel.log      # Only this file
```

**⚠️ Always use `recursive: true` for ROS logs!**

---

## File Naming in S3

### Filename Preservation

Filenames are preserved exactly as they appear locally.

**Local:**
```
/var/log/syslog.1
~/.parcel/log/terminal/session_20251106.log
~/.ros/log/run_001/rosout.log
```

**S3:**
```
s3://t01logs/vehicle-CN-001/2025-11-06/syslog/syslog.1
s3://t01logs/vehicle-CN-001/2025-11-06/terminal/session_20251106.log
s3://t01logs/vehicle-CN-001/2025-11-06/ros/run_001/rosout.log
```

### No Timestamp Added

The system does NOT add timestamps or UUID to filenames. Original names preserved.

**Why?**
- Easier to find specific files
- Matches local filename
- Duplicate prevention by registry (not filename mangling)

---

## Downloading Files from S3

### Download All Logs for a Vehicle

```bash
# Download everything
aws s3 sync s3://t01logs/vehicle-CN-001/ ./vehicle-CN-001-logs/ \
  --profile china --region cn-north-1

# Result:
./vehicle-CN-001-logs/
├── 2025-11-05/
│   ├── terminal/
│   ├── ros/
│   └── syslog/
└── 2025-11-06/
    ├── terminal/
    └── ros/
```

---

### Download Specific Date

```bash
# Download one day
aws s3 sync s3://t01logs/vehicle-CN-001/2025-11-06/ ./logs-nov-6/ \
  --profile china --region cn-north-1

# Result:
./logs-nov-6/
├── terminal/
├── ros/
└── syslog/
```

---

### Download Specific Source

```bash
# Download only ROS logs for all dates
aws s3 sync s3://t01logs/vehicle-CN-001/ ./ros-logs/ \
  --exclude "*" --include "*/ros/*" \
  --profile china --region cn-north-1

# Result:
./ros-logs/
├── 2025-11-05/
│   └── ros/
│       └── run_001/
└── 2025-11-06/
    └── ros/
        └── run_002/
```

---

### Download Date Range

```bash
# Download November 1-7
for day in {01..07}; do
  aws s3 sync s3://t01logs/vehicle-CN-001/2025-11-$day/ \
    ./logs-nov-$day/ \
    --profile china --region cn-north-1
done
```

---

### List Files Without Downloading

```bash
# List all files
aws s3 ls s3://t01logs/vehicle-CN-001/ --recursive \
  --profile china --region cn-north-1

# List specific date
aws s3 ls s3://t01logs/vehicle-CN-001/2025-11-06/ --recursive \
  --profile china --region cn-north-1

# List specific source
aws s3 ls s3://t01logs/vehicle-CN-001/ --recursive \
  --profile china --region cn-north-1 | grep "/ros/"
```

---

## Storage Cost Optimization

### Understanding Costs

**S3 China Pricing (approximate):**
- Storage: ¥0.148/GB/month
- PUT requests: ¥0.01/1000 requests
- GET requests: ¥0.01/10000 requests

**Example Monthly Cost:**
- 100 GB stored: ¥14.80
- 10,000 files uploaded: ¥0.10
- **Total: ~¥15/month**

---

### Optimization Strategies

#### 1. Compress Files Before Upload

**Not implemented by default**, but can be done manually:

```bash
# Compress logs before system monitors them
gzip /path/to/logs/*.log

# System will upload compressed files
# Savings: ~70-90% storage reduction
```

**Trade-offs:**
- **Pro:** Lower storage costs
- **Con:** Must decompress to view
- **Con:** Loses random access to file contents

---

#### 2. Adjust Retention Policies

```yaml
deletion:
  after_upload:
    enabled: true
    keep_days: 7            # Reduce from 14 to 7
```

**Savings:** Reduces local disk usage, doesn't affect S3 costs

---

#### 3. Use S3 Lifecycle Policies

**Move old logs to cheaper storage tiers:**

```json
{
  "Rules": [{
    "Id": "Move-to-IA-after-30-days",
    "Status": "Enabled",
    "Transitions": [{
      "Days": 30,
      "StorageClass": "STANDARD_IA"  // Infrequent Access (~40% cheaper)
    }, {
      "Days": 90,
      "StorageClass": "GLACIER"      // Archive (~80% cheaper)
    }],
    "NoncurrentVersionExpiration": {
      "NoncurrentDays": 30
    }
  }]
}
```

**Apply via AWS CLI:**
```bash
aws s3api put-bucket-lifecycle-configuration \
  --bucket t01logs \
  --lifecycle-configuration file://lifecycle.json \
  --profile china --region cn-north-1
```

---

#### 4. Delete Old Logs (Policy-Based)

```json
{
  "Rules": [{
    "Id": "Delete-after-1-year",
    "Status": "Enabled",
    "Expiration": {
      "Days": 365          // Delete after 1 year
    }
  }]
}
```

---

## Troubleshooting

### Files in Wrong Date Folder

**Symptom:** Files appear in unexpected date folders

**Cause:** File modification time not what you expect

**Diagnosis:**
```bash
# Check local file mtime
ls -l /path/to/file.log
stat /path/to/file.log

# Check S3 file location
aws s3 ls s3://t01logs/vehicle-CN-001/ --recursive | grep filename
```

**Solution:**
- Files organized by mtime, not upload time
- If mtime wrong, fix source (system clock, file creation process)

---

### Duplicate Files in Multiple Date Folders

**Symptom:** Same filename in multiple dates

**Cause:** File was modified and re-uploaded

**Explanation:**
```
Nov 5: test.log (mtime: Nov 5) → s3://.../2025-11-05/test.log
Nov 7: test.log modified → s3://.../2025-11-07/test.log
```

**This is correct behavior** - different versions of file on different dates.

---

### Missing Files

**Symptom:** File uploaded locally but not in expected S3 location

**Diagnosis:**
```bash
# Search ±5 days
for day in {01..11}; do
  echo "Checking 2025-11-$day:"
  aws s3 ls s3://t01logs/vehicle-CN-001/2025-11-$day/terminal/ \
    --profile china --region cn-north-1 | grep filename
done
```

**Common Causes:**
1. File in different date due to mtime
2. File in different source folder
3. Upload failed (check logs: `journalctl -u tvm-upload | grep filename`)

---

## Best Practices

### 1. Consistent Source Naming

**Use standardized source names across all vehicles:**

✅ **Good:**
```yaml
source: terminal
source: ros
source: syslog
source: ros2
```

❌ **Bad:**
```yaml
source: term              # Vehicle 1
source: terminal          # Vehicle 2 (inconsistent!)
```

**Why:** Makes cross-vehicle analysis easier.

---

### 2. Document Source Meanings

Create a source reference document for your team:

```
terminal → Shell session logs
ros → ROS 1 system logs
ros2 → ROS 2 system logs
syslog → System logs (Linux)
application → Custom app logs
```

---

### 3. Regular Archiving

**Set up periodic archiving to Glacier:**

```bash
# Monthly archive script
aws s3 sync s3://t01logs/vehicle-CN-001/2025-10-*/ \
  s3://t01logs-archive/vehicle-CN-001/2025-10/ \
  --storage-class GLACIER \
  --profile china --region cn-north-1

# Delete from main bucket after archiving
aws s3 rm s3://t01logs/vehicle-CN-001/2025-10-*/ --recursive \
  --profile china --region cn-north-1
```

---

### 4. Monitor S3 Costs

```bash
# Check bucket size
aws s3 ls s3://t01logs --recursive --human-readable --summarize \
  --profile china --region cn-north-1

# Output:
# Total Objects: 15234
# Total Size: 42.3 GB
```

**Set up billing alerts** in AWS Console → Billing → Budgets

---

## Related Documentation

- [Configuration Reference](./configuration_reference.md) - Source configuration
- [Deployment Guide](./deployment_guide.md) - Initial setup
- [Error Handling Guide](./error_handling_guide.md) - Upload troubleshooting

---

**Document Version:** 1.0
**Last Updated:** 2025-11-06
**Maintained By:** TVM Upload Team

### Changelog
- **v1.0** (2025-11-06): Initial S3 organization guide with date handling, structure, and download strategies
