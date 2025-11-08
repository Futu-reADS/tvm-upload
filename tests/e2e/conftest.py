# tests/e2e/conftest.py
"""
Fixtures for E2E tests (REAL AWS)
These tests use actual AWS services and run in CI/CD only
"""

import os
from pathlib import Path

import boto3
import pytest


@pytest.fixture(scope="session")
def aws_config():
    """
    Real AWS configuration
    Uses environment variables or defaults for CI/CD
    """
    return {
        "profile": os.getenv("AWS_PROFILE", None),  # ✅ None instead of 'china'
        "bucket": os.getenv("TEST_BUCKET", "t01logs"),
        "region": os.getenv("AWS_REGION", "cn-north-1"),
        "vehicle_id": "e2e-test-vehicle",
    }


@pytest.fixture
def real_s3_client(aws_config):
    """
    REAL S3 client - connects to actual AWS
    NO MOCKING - this makes real API calls
    """
    # CRITICAL: Check if profile exists before using it
    if aws_config["profile"]:
        # Local: Use profile
        session = boto3.Session(
            profile_name=aws_config["profile"], region_name=aws_config["region"]
        )
    else:
        # CI/CD: Use OIDC credentials (no profile)
        session = boto3.Session(region_name=aws_config["region"])

    return session.client("s3", endpoint_url=f"https://s3.{aws_config['region']}.amazonaws.com.cn")


@pytest.fixture
def real_cloudwatch_client(aws_config):
    """
    REAL CloudWatch client
    """
    # CRITICAL: Check if profile exists before using it
    if aws_config["profile"]:
        # Local: Use profile
        session = boto3.Session(
            profile_name=aws_config["profile"], region_name=aws_config["region"]
        )
    else:
        # CI/CD: Use OIDC credentials (no profile)
        session = boto3.Session(region_name=aws_config["region"])

    return session.client("cloudwatch")


@pytest.fixture
def real_upload_manager(aws_config):
    """
    Upload manager connected to REAL AWS S3 - Enhanced with log_directories

    Now includes log_directories for proper source-based path testing (v2.1)
    """
    from src.upload_manager import UploadManager

    # Define log directories for source detection (matches production config)
    log_directories = [
        "/home/autoware/.parcel/log/terminal",
        "/home/autoware/.ros/log",
        "/var/log",
        "/home/autoware/ros2_ws/log",
    ]

    return UploadManager(
        bucket=aws_config["bucket"],
        region=aws_config["region"],
        vehicle_id=aws_config["vehicle_id"],
        profile_name=aws_config["profile"],  # Will be None in CI
        log_directories=log_directories,  # NEW: Enable source detection
    )


@pytest.fixture
def s3_cleanup(real_s3_client, aws_config):
    """
    Auto-cleanup S3 objects after test completes
    Usage: s3_cleanup('path/to/object.log')
    """
    objects_to_delete = []

    def track(key):
        """Track S3 key for deletion"""
        objects_to_delete.append(key)
        return key

    yield track

    # Cleanup after test finishes
    for key in objects_to_delete:
        try:
            real_s3_client.delete_object(Bucket=aws_config["bucket"], Key=key)
            print(f"✓ Cleaned up s3://{aws_config['bucket']}/{key}")
        except Exception as e:
            print(f"✗ Cleanup failed for {key}: {e}")


@pytest.fixture
def e2e_config_with_deletion(aws_config):
    """
    Config dict for E2E tests with v2.0 deletion policies enabled

    Use this fixture when testing deletion behavior
    """
    return {
        **aws_config,
        "deletion": {
            "after_upload": {"enabled": True, "keep_days": 0},  # Immediate deletion for testing
            "age_based": {"enabled": True, "max_age_days": 7, "schedule_time": "02:00"},
            "emergency": {"enabled": True},
        },
        "upload": {
            "scan_existing_files": {"enabled": True, "max_age_days": 3},
            "batch_upload": {"enabled": True},
            "processed_files_registry": {
                "registry_file": "/tmp/e2e-test-registry.json",
                "retention_days": 30,
            },
        },
    }


@pytest.fixture
def e2e_config_without_deletion(aws_config):
    """
    Config dict for E2E tests with deletion DISABLED

    Use this to test that files persist after upload
    """
    return {
        **aws_config,
        "deletion": {
            "after_upload": {"enabled": False},  # Files kept indefinitely
            "age_based": {"enabled": False},
            "emergency": {"enabled": False},
        },
        "upload": {"scan_existing_files": {"enabled": True, "max_age_days": 3}},
    }


@pytest.fixture
def create_test_file():
    """
    Factory fixture for creating test files with custom metadata

    Returns a function that creates files and tracks them for cleanup

    Usage:
        def test_example(create_test_file):
            test_file = create_test_file(
                content='test data',
                suffix='.log',
                mtime_days_ago=5
            )
    """
    created_files = []

    def _create_file(content="test data\n", suffix=".log", mtime_days_ago=0):
        """
        Create a test file with optional custom mtime

        Args:
            content: File content (string)
            suffix: File extension
            mtime_days_ago: Set mtime to N days ago (0 = current time)

        Returns:
            str: Path to created file
        """
        import os
        import tempfile
        import time

        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=suffix) as f:
            f.write(content)
            filepath = f.name

        # Set custom mtime if requested
        if mtime_days_ago > 0:
            old_time = time.time() - (mtime_days_ago * 24 * 3600)
            os.utime(filepath, (old_time, old_time))

        created_files.append(filepath)
        return filepath

    yield _create_file

    # Cleanup all created files
    from pathlib import Path

    for filepath in created_files:
        Path(filepath).unlink(missing_ok=True)


@pytest.fixture
def verify_s3_key_structure():
    """
    Utility fixture for verifying S3 key structure (v2.1)

    Returns a function that validates S3 key format

    Usage:
        def test_example(verify_s3_key_structure, aws_config):
            verify_s3_key_structure(
                s3_key='vehicle-001/2025-10-20/terminal/session.log',
                vehicle_id=aws_config['vehicle_id']
            )
    """

    def _verify(s3_key, vehicle_id, expected_source=None):
        """
        Verify S3 key follows expected structure

        Args:
            s3_key: S3 object key to verify
            vehicle_id: Expected vehicle ID
            expected_source: Expected source type (optional)

        Returns:
            dict: Parsed components {vehicle_id, date, source, filename}

        Raises:
            AssertionError: If structure is invalid
        """
        from datetime import datetime

        parts = s3_key.split("/")
        assert len(parts) >= 4, f"S3 key should have at least 4 parts: {s3_key}"

        parsed_vehicle_id = parts[0]
        date_str = parts[1]
        source = parts[2]
        filename = parts[-1]

        # Verify vehicle ID
        assert (
            parsed_vehicle_id == vehicle_id
        ), f"Vehicle ID mismatch: expected {vehicle_id}, got {parsed_vehicle_id}"

        # Verify date format (YYYY-MM-DD)
        try:
            datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            raise AssertionError(f"Invalid date format in S3 key: {date_str}")

        # Verify source is not empty
        assert source, f"Source should not be empty in {s3_key}"

        # Verify expected source if provided
        if expected_source:
            assert (
                source == expected_source
            ), f"Source mismatch: expected {expected_source}, got {source}"

        return {
            "vehicle_id": parsed_vehicle_id,
            "date": date_str,
            "source": source,
            "filename": filename,
        }

    return _verify


@pytest.fixture
def cloudwatch_metrics_helper(real_cloudwatch_client, aws_config):
    """
    Helper fixture for verifying CloudWatch metrics

    Provides utilities for querying and verifying metrics

    Usage:
        def test_example(cloudwatch_metrics_helper):
            metrics = cloudwatch_metrics_helper.get_recent_metrics(
                metric_name='BytesUploaded',
                minutes=5
            )
    """

    class CloudWatchHelper:
        def __init__(self, client, config):
            self.client = client
            self.config = config

        def get_recent_metrics(self, metric_name, minutes=5, vehicle_id="e2e-test-vehicle"):
            """
            Get recent metric datapoints

            Args:
                metric_name: Name of metric (e.g., 'BytesUploaded')
                minutes: How many minutes back to query
                vehicle_id: Vehicle ID dimension

            Returns:
                list: Datapoints from CloudWatch
            """
            from datetime import datetime, timedelta

            end_time = datetime.utcnow()
            start_time = end_time - timedelta(minutes=minutes)

            try:
                response = self.client.get_metric_statistics(
                    Namespace="TVM/Upload",
                    MetricName=metric_name,
                    Dimensions=[{"Name": "VehicleId", "Value": vehicle_id}],
                    StartTime=start_time,
                    EndTime=end_time,
                    Period=60,  # 1 minute
                    Statistics=["Sum", "Average", "Maximum"],
                )
                return response.get("Datapoints", [])
            except Exception as e:
                print(f"⚠ Could not query metrics: {e}")
                return []

        def verify_alarm_exists(self, alarm_name):
            """
            Verify alarm exists in CloudWatch

            Args:
                alarm_name: Name of alarm

            Returns:
                dict: Alarm configuration or None
            """
            try:
                response = self.client.describe_alarms(AlarmNames=[alarm_name])
                alarms = response.get("MetricAlarms", [])
                return alarms[0] if alarms else None
            except Exception as e:
                print(f"⚠ Could not verify alarm: {e}")
                return None

        def cleanup_test_alarms(self, prefix="TVM-LowUpload-e2e"):
            """
            Cleanup all test alarms matching prefix

            Args:
                prefix: Alarm name prefix to match
            """
            try:
                response = self.client.describe_alarms(AlarmNamePrefix=prefix)
                alarm_names = [alarm["AlarmName"] for alarm in response.get("MetricAlarms", [])]

                if alarm_names:
                    self.client.delete_alarms(AlarmNames=alarm_names)
                    print(f"✓ Cleaned up {len(alarm_names)} test alarms")
            except Exception as e:
                print(f"⚠ Alarm cleanup failed: {e}")

    return CloudWatchHelper(real_cloudwatch_client, aws_config)


@pytest.fixture
def s3_batch_cleanup(real_s3_client, aws_config):
    """
    Enhanced S3 cleanup that can delete multiple objects efficiently

    Useful for batch upload tests that create many files

    Usage:
        def test_example(s3_batch_cleanup):
            # ... create and upload files ...
            s3_batch_cleanup(['key1', 'key2', 'key3'])
    """
    tracked_keys = []

    def _track(key_or_keys):
        """
        Track S3 key(s) for deletion

        Args:
            key_or_keys: Single key (str) or list of keys

        Returns:
            Same as input (for chaining)
        """
        if isinstance(key_or_keys, str):
            tracked_keys.append(key_or_keys)
            return key_or_keys
        else:
            tracked_keys.extend(key_or_keys)
            return key_or_keys

    yield _track

    # Cleanup after test finishes
    if tracked_keys:
        try:
            # Batch delete (up to 1000 objects at once)
            for i in range(0, len(tracked_keys), 1000):
                batch = tracked_keys[i : i + 1000]

                delete_objects = [{"Key": key} for key in batch]

                real_s3_client.delete_objects(
                    Bucket=aws_config["bucket"], Delete={"Objects": delete_objects}
                )

            print(f"✓ Cleaned up {len(tracked_keys)} S3 objects")
        except Exception as e:
            print(f"✗ Batch cleanup failed: {e}")


@pytest.fixture(scope="session")
def e2e_test_environment():
    """
    Session-scoped fixture providing E2E test environment information

    Useful for logging and debugging test runs
    """
    import os
    from datetime import datetime

    env_info = {
        "test_run_id": datetime.now().strftime("%Y%m%d-%H%M%S"),
        "ci_environment": os.getenv("CI", "false") == "true",
        "aws_region": os.getenv("AWS_REGION", "cn-north-1"),
        "test_bucket": os.getenv("TEST_BUCKET", "t01logs"),
        "python_version": f"{os.sys.version_info.major}.{os.sys.version_info.minor}",
    }

    print("\n" + "=" * 60)
    print("E2E Test Environment")
    print("=" * 60)
    for key, value in env_info.items():
        print(f"  {key}: {value}")
    print("=" * 60 + "\n")

    return env_info
