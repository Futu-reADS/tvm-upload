---
name: Bug Report
about: Create a report to help us improve
title: '[BUG] '
labels: bug
assignees: ''
---

## 🐛 Bug Description

A clear and concise description of what the bug is.

---

## 🌍 Environment

- **OS:** [e.g., Ubuntu 22.04]
- **Python Version:** [e.g., 3.10.12]
- **TVM Upload Version:** [e.g., 2.1.0]
- **AWS Region:** [e.g., cn-north-1]
- **Installation Method:** [pip / make install-dev / systemd service]

---

## 📋 Steps to Reproduce

Steps to reproduce the behavior:

1. Configure '...'
2. Run '...'
3. Observe '...'
4. See error

---

## ✅ Expected Behavior

A clear description of what you expected to happen.

---

## ❌ Actual Behavior

A clear description of what actually happened.

---

## 📝 Logs

```bash
# Paste relevant logs here
# For systemd service:
sudo journalctl -u tvm-upload -n 100

# For manual runs:
# Paste stdout/stderr output
```

---

## ⚙️ Configuration

```yaml
# Paste relevant config.yaml sections
# IMPORTANT: REDACT SENSITIVE DATA (credentials, vehicle IDs, etc.)

vehicle_id: "REDACTED"
s3:
  bucket: "REDACTED"
  region: cn-north-1

upload:
  schedule:
    mode: daily
    daily_time: "15:00"
```

---

## 📸 Screenshots (if applicable)

Add screenshots to help explain the problem.

---

## 🔍 Additional Context

Add any other context about the problem here:
- Did this work before? When did it stop working?
- Does it happen consistently or intermittently?
- Any recent changes to configuration or environment?

---

## 🔧 Possible Solution (Optional)

If you have ideas on how to fix the bug, please share them here.
