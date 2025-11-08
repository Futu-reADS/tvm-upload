# Contributing to TVM Log Upload System

Thank you for contributing to the TVM Upload System! This document provides guidelines for development and contribution.

---

## 📋 Table of Contents

1. [Development Setup](#development-setup)
2. [Development Workflow](#development-workflow)
3. [Code Style Guidelines](#code-style-guidelines)
4. [Testing Requirements](#testing-requirements)
5. [Pull Request Process](#pull-request-process)
6. [Commit Message Guidelines](#commit-message-guidelines)
7. [Bug Reports](#bug-reports)
8. [Security](#security)

---

## 🚀 Development Setup

### Prerequisites
- Python 3.10+
- Git
- AWS China account with credentials (for E2E tests)

### Quick Setup

```bash
# Clone repository
git clone git@github.com:Futu-reADS/tvm-upload.git
cd tvm-upload

# Setup development environment (one command!)
make dev-setup

# Verify setup
make test-fast
```

### Manual Setup

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install in development mode with test dependencies
pip3 install -e ".[test]"

# Verify installation
pytest tests/unit/ -v
```

---

## 🔄 Development Workflow

### 1. Create Feature Branch

```bash
# Update main branch
git checkout main
git pull origin main

# Create feature branch
git checkout -b feature/your-feature-name
```

### 2. Make Changes

- Write code following style guidelines
- Add tests for new functionality
- Update documentation if needed

### 3. Run Tests Locally

```bash
# Fast feedback loop
make test-fast           # Unit tests (~5 sec)

# Before committing
make test                # Unit + Integration (~30 sec)

# Full validation (optional)
make test-coverage       # With coverage report
```

### 4. Commit Changes

Follow [commit message guidelines](#commit-message-guidelines).

```bash
git add .
git commit -m "feat(upload): add MD5 caching for performance"
```

### 5. Push and Create PR

```bash
git push origin feature/your-feature-name
```

Then create Pull Request on GitHub.

---

## 📝 Code Style Guidelines

### Python Style

**Follow PEP 8 with these specifics:**

- **Line Length:** 100 characters max
- **Indentation:** 4 spaces (no tabs)
- **Imports:** Organized (standard lib, third-party, local)
- **Type Hints:** Required for all function parameters and return values
- **Docstrings:** Required for all public functions and classes

### Example

```python
from pathlib import Path
from typing import Optional

def upload_file(local_path: str, retry_count: int = 3) -> bool:
    """
    Upload file to S3 with retry logic.

    Args:
        local_path: Path to local file
        retry_count: Number of retry attempts (default: 3)

    Returns:
        bool: True if upload succeeded, False otherwise

    Raises:
        PermanentUploadError: For unrecoverable errors

    Example:
        >>> success = upload_file('/var/log/test.log')
        >>> if success:
        ...     print("Upload complete")
    """
    file_path = Path(local_path)
    # Implementation...
    return True
```

### Code Quality Tools

```bash
# Auto-format code
make format              # Uses black with 100-char line length

# Run linters
make lint                # Runs flake8 and pylint

# Run all checks
make check               # Format + lint
```

### File Operations

- **Always use `pathlib.Path`** for file operations
- Only convert to `str` when required by external APIs

```python
# ✅ Good
from pathlib import Path
file_path = Path(local_path)
if file_path.exists():
    with open(file_path, 'rb') as f:
        data = f.read()

# ❌ Bad
import os
if os.path.exists(local_path):
    with open(local_path, 'rb') as f:
        data = f.read()
```

---

## 🧪 Testing Requirements

### Test Coverage Requirements

- **Unit Tests:** 90%+ code coverage required
- **Integration Tests:** Required for all component interactions
- **E2E Tests:** Required for critical user workflows

### Writing Tests

**1. Test Structure:**

```python
import pytest
from pathlib import Path
from src.upload_manager import UploadManager

class TestUploadManager:
    """Tests for UploadManager class."""

    def test_upload_file_success(self, mocker):
        """Test successful file upload."""
        # Arrange
        mock_s3 = mocker.patch('boto3.client')
        uploader = UploadManager('bucket', 'region', 'vehicle-001')

        # Act
        result = uploader.upload_file('/tmp/test.log')

        # Assert
        assert result is True
        mock_s3.return_value.upload_file.assert_called_once()
```

**2. Test Naming Convention:**

- `test_<function_name>_<scenario>_<expected_result>`
- Examples:
  - `test_upload_file_success`
  - `test_upload_file_missing_file_raises_error`
  - `test_queue_add_duplicate_file_skips`

**3. Test Markers:**

```python
@pytest.mark.unit
def test_fast_unit_test():
    """Fast unit test with no external dependencies."""
    pass

@pytest.mark.integration
def test_component_interaction():
    """Integration test with mocked AWS."""
    pass

@pytest.mark.e2e
def test_real_aws_upload():
    """E2E test requiring real AWS credentials."""
    pass
```

### Running Tests

```bash
# Development (fast feedback)
make test-fast           # Unit only (~5 sec)

# Pre-commit (recommended)
make test                # Unit + Integration (~30 sec)

# Full suite
make test-all            # All tests including E2E
make test-coverage       # With HTML coverage report
```

---

## 🔀 Pull Request Process

### Before Submitting PR

**Checklist:**

- [ ] Code follows style guidelines
- [ ] All tests pass (`make test`)
- [ ] Added tests for new functionality
- [ ] Updated documentation (if applicable)
- [ ] Updated CHANGELOG.md under "Unreleased"
- [ ] No secrets or credentials committed

### PR Title Format

Use [Conventional Commits](https://www.conventionalcommits.org/) format:

```
<type>(<scope>): <description>

Examples:
feat(upload): add MD5 caching for performance
fix(queue): prevent duplicate registry marking
docs(readme): update test count to 416 tests
test(e2e): add permanent error handling tests
```

**Types:**
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation only
- `style`: Code style (formatting, no logic change)
- `refactor`: Code refactoring
- `test`: Adding/updating tests
- `chore`: Build process, dependencies

### PR Description Template

GitHub will auto-populate this template when you create a PR. Fill in all sections.

```markdown
## Description
Brief description of changes

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Documentation update

## Testing
- [ ] Unit tests pass
- [ ] Integration tests pass
- [ ] E2E tests pass (if applicable)

## Checklist
- [ ] Code follows style guidelines
- [ ] Documentation updated
- [ ] Tests added/updated
- [ ] CHANGELOG.md updated
```

### Review Process

1. **Automated Checks:** CI/CD runs unit + integration tests
2. **Code Review:** At least one approval required
3. **Address Feedback:** Respond to all review comments
4. **Merge:** Squash and merge after approval

---

## 💬 Commit Message Guidelines

### Format

```
<type>(<scope>): <subject>

[optional body]

[optional footer]
```

### Examples

```bash
# Simple commit
git commit -m "feat(upload): add retry logic with exponential backoff"

# With body
git commit -m "fix(queue): prevent duplicate entries

- Check queue before adding file
- Add integration test for duplicate detection
- Update documentation"

# Breaking change
git commit -m "feat(config)!: change schedule format to support intervals

BREAKING CHANGE: upload.schedule is now an object instead of string.
Migration: Change 'schedule: "15:00"' to 'schedule: {mode: daily, daily_time: "15:00"}'
```

### Type Descriptions

| Type | Description | Example |
|------|-------------|---------|
| `feat` | New feature | `feat(upload): add pattern matching` |
| `fix` | Bug fix | `fix(disk): correct cleanup logic` |
| `docs` | Documentation | `docs(faq): add CloudWatch setup` |
| `style` | Formatting | `style: fix indentation in main.py` |
| `refactor` | Code refactoring | `refactor(queue): simplify add logic` |
| `test` | Tests | `test(upload): add edge case tests` |
| `chore` | Maintenance | `chore: update dependencies` |

---

## 🐛 Bug Reports

### Before Reporting

1. **Search existing issues** - Check if already reported
2. **Verify latest version** - Update to latest `main` branch
3. **Collect logs and config** - Gather debugging information

### Bug Report Template

Create issue with this information:

```markdown
**Environment:**
- OS: Ubuntu 22.04
- Python: 3.10.12
- TVM Upload Version: 2.1.0
- AWS Region: cn-north-1

**Description:**
Clear description of the bug

**Steps to Reproduce:**
1. Configure upload schedule to interval mode
2. Start service
3. Observe error in logs

**Expected Behavior:**
Service should start successfully

**Actual Behavior:**
Service crashes with KeyError

**Logs:**
```bash
# Paste relevant logs from journalctl
sudo journalctl -u tvm-upload -n 50
```

**Configuration:**
```yaml
# Paste relevant config (REDACT SENSITIVE DATA)
upload:
  schedule:
    mode: interval
    interval_hours: 2
```

**Additional Context:**
Any other relevant information
```

---

## 🔐 Security

### Do NOT Commit

**Never commit sensitive data:**

- ❌ AWS credentials (access keys, secret keys)
- ❌ API keys
- ❌ Passwords
- ❌ Private keys (`.pem`, `.key` files)
- ❌ Real vehicle IDs
- ❌ Production configuration files

### If Sensitive Data Committed

**Immediate Action:**

1. **Rotate credentials immediately** - Generate new AWS keys
2. **Contact team lead** - Report the incident
3. **Remove from history:**
   ```bash
   # Use BFG Repo-Cleaner or git filter-branch
   # Contact DevOps team for help
   ```

### Secure Development

```bash
# Use environment variables for credentials
export AWS_PROFILE=china

# Use git-secrets to prevent commits
git secrets --install
git secrets --register-aws
```

---

## 📞 Questions?

- **Documentation:** Check [docs/](docs/) folder
- **FAQ:** See [docs/faq.md](docs/faq.md)
- **Issues:** [GitHub Issues](https://github.com/Futu-reADS/tvm-upload/issues)
- **Team Chat:** Internal Slack/Teams channel

---

## 🎯 Quick Reference

### Common Commands

```bash
# Development
make dev-setup          # Setup environment
make test-fast          # Quick test
make test               # Full test suite
make lint               # Check code quality
make format             # Auto-format code

# Running
make run                # Run application
make run-test-config    # Validate config

# Deployment
make deploy-verify      # Pre-deployment check
make deploy-install     # Install to production
make deploy-health      # Health check

# Cleanup
make clean              # Remove cache
make clean-test         # Remove test artifacts
```

### File Organization

```
src/                    # Source code
├── main.py            # Entry point
├── config_manager.py  # Configuration
├── upload_manager.py  # S3 uploads
├── queue_manager.py   # Queue management
└── ...

tests/                 # Test suite
├── unit/             # Fast, mocked tests
├── integration/      # Component interaction tests
└── e2e/              # Real AWS tests

docs/                  # Documentation
└── ...
```

---

**Thank you for contributing! 🚀**

For detailed guidelines, see:
- [Complete Reference](docs/complete_reference.md)
- [Testing Guide](docs/autonomous_testing_guide.md)
- [Deployment Guide](docs/deployment_guide.md)
