# tests/integration/conftest.py
"""
Fixtures for integration tests (mocked AWS)
These tests verify components work together with mocked external services
"""

import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import yaml


@pytest.fixture
def temp_log_dir():
    """Create temporary log directory"""
    log_dir = Path("/tmp/tvm-test-logs")
    log_dir.mkdir(exist_ok=True)
    yield log_dir
    # Cleanup
    if log_dir.exists():
        import shutil

        shutil.rmtree(log_dir)


@pytest.fixture
def temp_config_file(temp_log_dir):
    """Create temporary config file for system tests"""
    temp_log_dir.mkdir(exist_ok=True)

    config_content = f"""
vehicle_id: "test-vehicle"

log_directories:
  - {temp_log_dir}

s3:
  bucket: test-bucket
  region: cn-north-1
  credentials_path: ~/.aws

upload:
  schedule: "15:00"
  file_stable_seconds: 2
  operational_hours:
    enabled: true
    start: "09:00"
    end: "16:00"
  queue_file: /tmp/tvm-test-queue.json
  processed_files_registry:
    registry_file: /tmp/tvm-test-registry-conftest.json
    retention_days: 30

disk:
  reserved_gb: 1
  warning_threshold: 0.90
  critical_threshold: 0.95

deletion:
  after_upload:
    enabled: true
    keep_days: 0
  age_based:
    enabled: true
    max_age_days: 7
    schedule_time: "02:00"
  emergency:
    enabled: true

monitoring:
  cloudwatch_enabled: false
"""

    config_file = Path("/tmp") / "test-config-integration.yaml"
    config_file.write_text(config_content)

    yield str(config_file)

    config_file.unlink(missing_ok=True)


@pytest.fixture
def mock_s3_client():
    """Mock S3 client for integration tests"""
    from botocore.exceptions import ClientError

    mock = Mock()
    mock.upload_file.return_value = None

    # Simulate file NOT in S3 (new upload)
    mock.head_object.side_effect = ClientError({"Error": {"Code": "NotFound"}}, "head_object")

    mock.delete_object.return_value = {}
    return mock


@pytest.fixture
def mock_cloudwatch_client():
    """Mock CloudWatch client for integration tests"""
    mock = Mock()
    mock.put_metric_data.return_value = None
    return mock
