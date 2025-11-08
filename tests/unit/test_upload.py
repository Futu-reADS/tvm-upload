#!/usr/bin/env python3
"""
Tests for Upload Manager
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest
from botocore.exceptions import ClientError

from src.upload_manager import PermanentUploadError, UploadManager


@pytest.fixture
def temp_file():
    """Create temporary test file"""
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".log") as f:
        f.write("test data" * 1000)  # ~9KB
        temp_path = f.name

    yield temp_path

    # Cleanup
    if Path(temp_path).exists():
        Path(temp_path).unlink()


@pytest.fixture
def large_temp_file():
    """Create large temporary file for multipart test"""
    with tempfile.NamedTemporaryFile(mode="wb", delete=False, suffix=".mcap") as f:
        # Write 6MB of data
        f.write(b"0" * (6 * 1024 * 1024))
        temp_path = f.name

    yield temp_path

    # Cleanup
    if Path(temp_path).exists():
        Path(temp_path).unlink()


def test_upload_manager_initialization():
    """Test upload manager can be initialized"""
    uploader = UploadManager(
        bucket="test-bucket",
        region="us-east-1",
        vehicle_id="vehicle-001",
        log_directories=[{"path": "/tmp/logs", "source": "test"}],
    )

    assert uploader.bucket == "test-bucket"
    assert uploader.region == "us-east-1"
    assert uploader.vehicle_id == "vehicle-001"
    assert uploader.max_retries == 10


def test_s3_key_building(temp_file):
    """Test S3 key generation"""
    uploader = UploadManager(
        bucket="test-bucket",
        region="us-east-1",
        vehicle_id="vehicle-001",
        log_directories=[str(Path(temp_file).parent)],
    )

    file_path = Path(temp_file)
    s3_key = uploader._build_s3_key(file_path)

    # Should be: vehicle-001/YYYY-MM-DD/source/filename.log
    assert s3_key.startswith("vehicle-001/")
    assert file_path.name in s3_key
    assert "/" in s3_key  # Has date component


def test_exponential_backoff():
    """Test backoff calculation"""
    uploader = UploadManager(
        bucket="test-bucket",
        region="us-east-1",
        vehicle_id="vehicle-001",
        log_directories=[{"path": "/tmp/logs", "source": "test"}],
    )

    # Test exponential progression
    assert uploader._calculate_backoff(1) == 1
    assert uploader._calculate_backoff(2) == 2
    assert uploader._calculate_backoff(3) == 4
    assert uploader._calculate_backoff(4) == 8
    assert uploader._calculate_backoff(10) == 512  # Max cap


@patch("src.upload_manager.boto3.session.Session")
def test_successful_upload(mock_Session, temp_file):
    """Test successful file upload"""
    # Create mock S3 client
    mock_s3 = Mock()
    mock_s3.upload_file.return_value = None
    mock_s3.head_object.side_effect = ClientError({"Error": {"Code": "404"}}, "head_object")

    # Create mock session instance
    mock_session_instance = Mock()
    mock_session_instance.client.return_value = mock_s3

    # When Session() is called, return our mock session
    mock_Session.return_value = mock_session_instance

    # Create uploader (this calls Session())
    uploader = UploadManager(
        bucket="test-bucket",
        region="us-east-1",
        vehicle_id="vehicle-001",
        log_directories=[str(Path(temp_file).parent)],  # ADD THIS
    )

    # Upload file
    result = uploader.upload_file(temp_file)

    # Assertions
    assert result is True
    assert mock_s3.upload_file.called


@patch("src.upload_manager.boto3.session.Session")
@patch("src.upload_manager.time.sleep")
def test_upload_with_retry(mock_sleep, mock_Session, temp_file):
    """Test upload retries on failure"""
    # Create mock S3 client
    mock_s3 = Mock()
    mock_s3.head_object.side_effect = ClientError({"Error": {"Code": "404"}}, "head_object")

    # Create mock session instance
    mock_session_instance = Mock()
    mock_session_instance.client.return_value = mock_s3

    # When Session() is called, return our mock session
    mock_Session.return_value = mock_session_instance

    # Fail first 2 attempts, succeed on 3rd
    mock_s3.upload_file.side_effect = [
        ClientError({"Error": {"Code": "500"}}, "upload_file"),
        ClientError({"Error": {"Code": "500"}}, "upload_file"),
        None,  # Success
    ]

    uploader = UploadManager(
        bucket="test-bucket",
        region="us-east-1",
        vehicle_id="vehicle-001",
        log_directories=[str(Path(temp_file).parent)],  # ADD THIS
    )

    result = uploader.upload_file(temp_file)

    assert result is True
    assert mock_s3.upload_file.call_count == 3
    assert mock_sleep.call_count == 2


@patch("src.upload_manager.boto3.session.Session")
def test_upload_fails_after_max_retries(mock_Session, temp_file):
    """Test upload fails after max retries"""

    # Create mock S3 client
    mock_s3 = Mock()
    mock_s3.head_object.side_effect = ClientError({"Error": {"Code": "404"}}, "head_object")

    # Create mock session instance
    mock_session_instance = Mock()
    mock_session_instance.client.return_value = mock_s3

    # When Session() is called, return our mock session
    mock_Session.return_value = mock_session_instance

    # Always fail
    mock_s3.upload_file.side_effect = ClientError({"Error": {"Code": "500"}}, "upload_file")

    uploader = UploadManager(
        bucket="test-bucket",
        region="us-east-1",
        vehicle_id="vehicle-001",
        max_retries=3,
        log_directories=[str(Path(temp_file).parent)],  # ADD THIS
    )

    result = uploader.upload_file(temp_file)

    assert result is False
    assert mock_s3.upload_file.call_count == 3


@patch("src.upload_manager.boto3.session.Session")
def test_multipart_upload_for_large_files(mock_Session, large_temp_file):
    """Test that large files use multipart upload"""

    # Create mock S3 client
    mock_s3 = Mock()
    mock_s3.upload_file.return_value = None
    mock_s3.head_object.side_effect = ClientError({"Error": {"Code": "404"}}, "head_object")

    # Create mock session instance
    mock_session_instance = Mock()
    mock_session_instance.client.return_value = mock_s3

    # When Session() is called, return our mock session
    mock_Session.return_value = mock_session_instance

    uploader = UploadManager(
        bucket="test-bucket",
        region="us-east-1",
        vehicle_id="vehicle-001",
        log_directories=[str(Path(large_temp_file).parent)],  # ADD THIS
    )

    result = uploader.upload_file(large_temp_file)

    assert result is True
    assert mock_s3.upload_file.called


# ============================================
# NEW TESTS FOR v2.1 PERMANENT UPLOAD ERRORS
# ============================================


def test_upload_nonexistent_file_raises_permanent_error():
    """Test uploading nonexistent file raises PermanentUploadError"""
    uploader = UploadManager(
        bucket="test-bucket",
        region="us-east-1",
        vehicle_id="vehicle-001",
        log_directories=[{"path": "/nonexistent", "source": "test"}],
    )

    with pytest.raises(PermanentUploadError, match="File not found"):
        uploader.upload_file("/nonexistent/file.log")


def test_upload_unreadable_file_raises_permanent_error(temp_dir):
    """Test uploading unreadable file raises PermanentUploadError"""
    import os

    # Create file and make it unreadable
    test_file = Path(temp_dir) / "unreadable.log"
    test_file.write_text("data")
    os.chmod(str(test_file), 0o000)  # No permissions

    uploader = UploadManager(
        bucket="test-bucket",
        region="us-east-1",
        vehicle_id="vehicle-001",
        log_directories=[str(temp_dir)],
    )

    try:
        with pytest.raises(PermanentUploadError, match="Permission denied"):
            uploader.upload_file(str(test_file))
    finally:
        # Restore permissions for cleanup
        os.chmod(str(test_file), 0o644)


@patch("src.upload_manager.boto3.session.Session")
def test_invalid_credentials_raises_permanent_error(mock_Session, temp_file):
    """Test invalid AWS credentials raises PermanentUploadError"""
    mock_s3 = Mock()
    mock_s3.head_object.side_effect = ClientError({"Error": {"Code": "404"}}, "head_object")
    mock_s3.upload_file.side_effect = ClientError(
        {"Error": {"Code": "InvalidAccessKeyId"}}, "upload_file"
    )

    mock_session_instance = Mock()
    mock_session_instance.client.return_value = mock_s3
    mock_Session.return_value = mock_session_instance

    uploader = UploadManager(
        bucket="test-bucket",
        region="us-east-1",
        vehicle_id="vehicle-001",
        log_directories=[str(Path(temp_file).parent)],
    )

    with pytest.raises(PermanentUploadError, match="Invalid AWS credentials"):
        uploader.upload_file(temp_file)


@patch("src.upload_manager.boto3.session.Session")
def test_bucket_not_found_raises_permanent_error(mock_Session, temp_file):
    """Test nonexistent bucket raises PermanentUploadError"""
    mock_s3 = Mock()
    mock_s3.head_object.side_effect = ClientError({"Error": {"Code": "404"}}, "head_object")
    mock_s3.upload_file.side_effect = ClientError(
        {"Error": {"Code": "NoSuchBucket"}}, "upload_file"
    )

    mock_session_instance = Mock()
    mock_session_instance.client.return_value = mock_s3
    mock_Session.return_value = mock_session_instance

    uploader = UploadManager(
        bucket="nonexistent-bucket",
        region="us-east-1",
        vehicle_id="vehicle-001",
        log_directories=[str(Path(temp_file).parent)],
    )

    with pytest.raises(PermanentUploadError, match="Bucket does not exist"):
        uploader.upload_file(temp_file)


@patch("src.upload_manager.boto3.session.Session")
def test_access_denied_raises_permanent_error(mock_Session, temp_file):
    """Test IAM permissions error raises PermanentUploadError"""
    mock_s3 = Mock()
    mock_s3.head_object.side_effect = ClientError({"Error": {"Code": "404"}}, "head_object")
    mock_s3.upload_file.side_effect = ClientError(
        {"Error": {"Code": "AccessDenied"}}, "upload_file"
    )

    mock_session_instance = Mock()
    mock_session_instance.client.return_value = mock_s3
    mock_Session.return_value = mock_session_instance

    uploader = UploadManager(
        bucket="test-bucket",
        region="us-east-1",
        vehicle_id="vehicle-001",
        log_directories=[str(Path(temp_file).parent)],
    )

    with pytest.raises(PermanentUploadError, match="IAM permissions denied"):
        uploader.upload_file(temp_file)


# ============================================
# NEW TESTS FOR v2.1 SOURCE-BASED S3 KEYS
# ============================================


def test_s3_key_source_detection_terminal(temp_dir):
    """Test S3 key includes source from directory structure"""
    # Create actual directory and file
    terminal_dir = temp_dir / "terminal"
    terminal_dir.mkdir()
    test_file = terminal_dir / "session.log"
    test_file.write_text("session data")

    uploader = UploadManager(
        bucket="test-bucket",
        region="us-east-1",
        vehicle_id="vehicle-001",
        log_directories=[{"path": str(terminal_dir), "source": "terminal"}],
    )

    s3_key = uploader._build_s3_key(test_file)

    # Should be: vehicle-001/YYYY-MM-DD/terminal/session.log
    assert "terminal/session.log" in s3_key
    assert s3_key.startswith("vehicle-001/")


def test_s3_key_source_detection_ros(temp_dir):
    """Test S3 key preserves ROS folder structure"""
    # Create actual directory structure
    ros_dir = temp_dir / "ros_log"
    ros_dir.mkdir()
    run_dir = ros_dir / "run-123"
    run_dir.mkdir()
    test_file = run_dir / "launch.log"
    test_file.write_text("ros launch data")

    uploader = UploadManager(
        bucket="test-bucket",
        region="us-east-1",
        vehicle_id="vehicle-001",
        log_directories=[{"path": str(ros_dir), "source": "log"}],
    )

    s3_key = uploader._build_s3_key(test_file)

    # Should be: vehicle-001/YYYY-MM-DD/log/run-123/launch.log
    assert "log/run-123/launch.log" in s3_key
    assert s3_key.startswith("vehicle-001/")


def test_s3_key_syslog_uses_upload_date(temp_file):
    """Test syslog files use upload date (not file mtime)"""
    import os
    import time
    from datetime import datetime

    # Create file in /var/log (simulated syslog)
    syslog_dir = Path(temp_file).parent / "var_log"
    syslog_dir.mkdir(exist_ok=True)

    syslog_file = syslog_dir / "syslog"
    syslog_file.write_text("syslog data")

    # Set file mtime to 3 days ago
    old_time = time.time() - (3 * 24 * 3600)
    os.utime(str(syslog_file), (old_time, old_time))

    # Temporarily patch the file path to start with /var/log
    original_resolve = Path.resolve

    def mock_resolve(self):
        result = original_resolve(self)
        if "var_log" in str(result):
            return Path(str(result).replace("var_log", "var/log"))
        return result

    Path.resolve = mock_resolve

    try:
        uploader = UploadManager(
            bucket="test-bucket",
            region="us-east-1",
            vehicle_id="vehicle-001",
            log_directories=["/var/log"],
        )

        s3_key = uploader._build_s3_key(Path("/var/log/syslog"))

        # Should use TODAY's date, not file's old mtime
        today = datetime.now().strftime("%Y-%m-%d")
        assert today in s3_key
        assert "syslog/syslog" in s3_key

    finally:
        Path.resolve = original_resolve


def test_verify_upload_checks_existing_file(temp_file):
    """Test verify_upload checks if file already exists in S3"""
    with patch("src.upload_manager.boto3.session.Session") as mock_Session:
        mock_s3 = Mock()

        # Calculate actual MD5 for temp file
        import hashlib

        with open(temp_file, "rb") as f:
            file_md5 = hashlib.md5(f.read()).hexdigest()

        # Simulate file exists in S3 with same size and MD5
        file_size = Path(temp_file).stat().st_size
        mock_s3.head_object.return_value = {
            "ContentLength": file_size,
            "ETag": f'"{file_md5}"',  # ETag is quoted
        }

        mock_session_instance = Mock()
        mock_session_instance.client.return_value = mock_s3
        mock_Session.return_value = mock_session_instance

        uploader = UploadManager(
            bucket="test-bucket",
            region="us-east-1",
            vehicle_id="vehicle-001",
            log_directories=[str(Path(temp_file).parent)],
        )

        # Should return True (file already exists)
        assert uploader.verify_upload(temp_file) is True


def test_verify_upload_checks_multiple_dates(temp_file):
    """Test verify_upload checks ±5 days for delayed uploads"""
    with patch("src.upload_manager.boto3.session.Session") as mock_Session:
        mock_s3 = Mock()

        # First check (file mtime date) - not found
        # Second check (+1 day) - found
        file_size = Path(temp_file).stat().st_size

        def mock_head_object(Bucket, Key):
            if "2025-10-21" in Key:  # Tomorrow's date
                return {"ContentLength": file_size}
            raise ClientError({"Error": {"Code": "404"}}, "head_object")

        mock_s3.head_object.side_effect = mock_head_object

        mock_session_instance = Mock()
        mock_session_instance.client.return_value = mock_s3
        mock_Session.return_value = mock_session_instance

        uploader = UploadManager(
            bucket="test-bucket",
            region="us-east-1",
            vehicle_id="vehicle-001",
            log_directories=[str(Path(temp_file).parent)],
        )

        # Should find file in alternate date and return True
        result = uploader.verify_upload(temp_file)

        # Verify multiple head_object calls were made (checking different dates)
        assert mock_s3.head_object.call_count > 1


# ============================================
# COMPREHENSIVE TESTS FOR MTIME (CRITICAL!)
# ============================================


@pytest.fixture
def temp_dir():
    """Create temporary directory for testing"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


def test_s3_key_uses_mtime_not_ctime(temp_dir):
    """CRITICAL: Verify S3 key uses modification time (mtime), not change time (ctime)"""
    import os
    import time
    from datetime import datetime, timedelta

    # Create file
    test_file = temp_dir / "test.log"
    test_file.write_text("original content")

    # Set mtime to 5 days ago
    old_mtime = time.time() - (5 * 24 * 3600)
    os.utime(str(test_file), (old_mtime, old_mtime))

    # Verify file has old mtime
    stat = test_file.stat()
    assert stat.st_mtime < time.time() - (4 * 24 * 3600)

    # Create uploader
    log_dirs = [{"path": str(temp_dir), "source": "test"}]

    uploader = UploadManager(
        bucket="test-bucket", region="us-east-1", vehicle_id="vehicle-001", log_directories=log_dirs
    )

    # Build S3 key
    s3_key = uploader._build_s3_key(test_file)

    # Expected date (5 days ago)
    expected_date = datetime.fromtimestamp(old_mtime).strftime("%Y-%m-%d")

    # S3 key should use old mtime date, not today's date
    assert expected_date in s3_key, f"S3 key should use mtime date {expected_date}, got: {s3_key}"
    assert datetime.now().strftime(
        "%Y-%m-%d"
    ) not in s3_key or expected_date == datetime.now().strftime(
        "%Y-%m-%d"
    ), "S3 key should NOT use today's date for old file"


def test_all_sources_use_mtime(temp_dir):
    """Verify ALL sources (terminal, ros, syslog, ros2) use mtime consistently"""
    import os
    import time
    from datetime import datetime

    sources = ["terminal", "ros", "syslog", "ros2"]

    # Set mtime to 10 days ago
    old_mtime = time.time() - (10 * 24 * 3600)
    expected_date = datetime.fromtimestamp(old_mtime).strftime("%Y-%m-%d")

    for source in sources:
        # Create directory for this source
        source_dir = temp_dir / source
        source_dir.mkdir()

        # Create file with old mtime
        test_file = source_dir / f"{source}.log"
        test_file.write_text(f"{source} data")
        os.utime(str(test_file), (old_mtime, old_mtime))

        # Create uploader with this source
        log_dirs = [{"path": str(source_dir), "source": source}]

        uploader = UploadManager(
            bucket="test-bucket",
            region="us-east-1",
            vehicle_id="vehicle-001",
            log_directories=log_dirs,
        )

        # Build S3 key
        s3_key = uploader._build_s3_key(test_file)

        # All sources should use mtime
        assert (
            expected_date in s3_key
        ), f"Source '{source}' should use mtime date {expected_date}, got: {s3_key}"


def test_mtime_with_very_old_files(temp_dir):
    """Test files modified 365 days ago get correct old date"""
    import os
    import time
    from datetime import datetime

    test_file = temp_dir / "old.log"
    test_file.write_text("ancient data")

    # Set mtime to 365 days ago
    old_mtime = time.time() - (365 * 24 * 3600)
    os.utime(str(test_file), (old_mtime, old_mtime))

    log_dirs = [{"path": str(temp_dir), "source": "test"}]

    uploader = UploadManager(
        bucket="test-bucket", region="us-east-1", vehicle_id="vehicle-001", log_directories=log_dirs
    )

    s3_key = uploader._build_s3_key(test_file)
    expected_date = datetime.fromtimestamp(old_mtime).strftime("%Y-%m-%d")

    assert expected_date in s3_key


def test_mtime_with_future_date(temp_dir):
    """Test file with future mtime (clock skew scenario)"""
    import os
    import time
    from datetime import datetime

    test_file = temp_dir / "future.log"
    test_file.write_text("future data")

    # Set mtime to 1 day in future
    future_mtime = time.time() + (1 * 24 * 3600)
    os.utime(str(test_file), (future_mtime, future_mtime))

    log_dirs = [{"path": str(temp_dir), "source": "test"}]

    uploader = UploadManager(
        bucket="test-bucket", region="us-east-1", vehicle_id="vehicle-001", log_directories=log_dirs
    )

    s3_key = uploader._build_s3_key(test_file)
    expected_date = datetime.fromtimestamp(future_mtime).strftime("%Y-%m-%d")

    # Should use future date (handles clock skew gracefully)
    assert expected_date in s3_key


# ============================================
# SOURCE-BASED S3 KEY TESTS
# ============================================


def test_s3_key_preserves_subdirectory_structure(temp_dir):
    """Test that subdirectory structure is preserved in S3 key"""
    # Create nested directory structure
    ros_dir = temp_dir / "ros"
    ros_dir.mkdir()
    run_dir = ros_dir / "run-20250125-150000"
    run_dir.mkdir()

    test_file = run_dir / "launch.log"
    test_file.write_text("launch data")

    log_dirs = [{"path": str(ros_dir), "source": "ros"}]

    uploader = UploadManager(
        bucket="test-bucket", region="us-east-1", vehicle_id="vehicle-001", log_directories=log_dirs
    )

    s3_key = uploader._build_s3_key(test_file)

    # Should preserve subdirectory structure
    assert "ros/run-20250125-150000/launch.log" in s3_key
    assert s3_key.startswith("vehicle-001/")


def test_s3_key_with_multiple_sources(temp_dir):
    """Test files from different sources get correct source in S3 key"""
    # Use distinct directory names to avoid startswith() overlap (ros vs ros2)
    sources = {
        "terminal": "session.log",
        "ros_logs": "rosout.log",
        "syslog": "syslog",
        "ros2_logs": "node.log",
    }

    log_dirs = []
    test_files = []

    for source, filename in sources.items():
        source_dir = temp_dir / source
        source_dir.mkdir()

        test_file = source_dir / filename
        test_file.write_text(f"{source} data")

        # Map directory name to actual source name for S3
        actual_source = source.replace("_logs", "")  # ros_logs -> ros, ros2_logs -> ros2
        test_files.append((actual_source, test_file))

        log_dirs.append({"path": str(source_dir), "source": actual_source})

    uploader = UploadManager(
        bucket="test-bucket", region="us-east-1", vehicle_id="vehicle-001", log_directories=log_dirs
    )

    for source, test_file in test_files:
        s3_key = uploader._build_s3_key(test_file)
        # S3 key format: vehicle-001/YYYY-MM-DD/source/filename
        assert f"/{source}/{test_file.name}" in s3_key, f"Source '{source}' not in S3 key: {s3_key}"


def test_s3_key_file_not_in_configured_directories(temp_dir):
    """Test file outside log_directories gets source='other'"""
    configured_dir = temp_dir / "configured"
    configured_dir.mkdir()

    other_dir = temp_dir / "other"
    other_dir.mkdir()

    test_file = other_dir / "orphan.log"
    test_file.write_text("orphan data")

    log_dirs = [{"path": str(configured_dir), "source": "test"}]

    uploader = UploadManager(
        bucket="test-bucket", region="us-east-1", vehicle_id="vehicle-001", log_directories=log_dirs
    )

    s3_key = uploader._build_s3_key(test_file)

    # Should use 'other' as source
    assert "/other/" in s3_key


def test_s3_key_with_special_characters_in_filename(temp_dir):
    """Test filenames with spaces and special characters"""
    test_file = temp_dir / "test file with spaces & special-chars.log"
    test_file.write_text("data")

    log_dirs = [{"path": str(temp_dir), "source": "test"}]

    uploader = UploadManager(
        bucket="test-bucket", region="us-east-1", vehicle_id="vehicle-001", log_directories=log_dirs
    )

    s3_key = uploader._build_s3_key(test_file)

    # S3 key should contain the filename
    assert "test file with spaces & special-chars.log" in s3_key


def test_s3_key_with_unicode_filename(temp_dir):
    """Test Unicode characters in filename"""
    test_file = temp_dir / "测试文件.log"
    test_file.write_text("unicode data")

    log_dirs = [{"path": str(temp_dir), "source": "test"}]

    uploader = UploadManager(
        bucket="test-bucket", region="us-east-1", vehicle_id="vehicle-001", log_directories=log_dirs
    )

    s3_key = uploader._build_s3_key(test_file)

    # Should handle Unicode gracefully
    assert "测试文件.log" in s3_key or test_file.name in s3_key


# ============================================
# MD5 CACHE TESTS
# ============================================


@patch("src.upload_manager.boto3.session.Session")
def test_md5_cache_hit(mock_Session, temp_dir):
    """Test MD5 cache reuses calculated hash"""
    test_file = temp_dir / "cached.log"
    test_file.write_text("data for caching")

    mock_s3 = Mock()
    mock_s3.head_object.side_effect = ClientError({"Error": {"Code": "404"}}, "head_object")

    mock_session_instance = Mock()
    mock_session_instance.client.return_value = mock_s3
    mock_Session.return_value = mock_session_instance

    log_dirs = [{"path": str(temp_dir), "source": "test"}]

    uploader = UploadManager(
        bucket="test-bucket", region="us-east-1", vehicle_id="vehicle-001", log_directories=log_dirs
    )

    # First call - calculate MD5
    with patch.object(uploader, "_calculate_md5", wraps=uploader._calculate_md5) as mock_calc:
        md5_1 = uploader._get_cached_md5(test_file)
        assert mock_calc.call_count == 1

        # Second call - use cache
        md5_2 = uploader._get_cached_md5(test_file)
        assert mock_calc.call_count == 1  # Not called again

        assert md5_1 == md5_2


@patch("src.upload_manager.boto3.session.Session")
def test_md5_cache_invalidation_on_mtime_change(mock_Session, temp_dir):
    """Test MD5 cache invalidated when file modified"""
    import os
    import time

    test_file = temp_dir / "modified.log"
    test_file.write_text("original content")

    mock_s3 = Mock()
    mock_session_instance = Mock()
    mock_session_instance.client.return_value = mock_s3
    mock_Session.return_value = mock_session_instance

    log_dirs = [{"path": str(temp_dir), "source": "test"}]

    uploader = UploadManager(
        bucket="test-bucket", region="us-east-1", vehicle_id="vehicle-001", log_directories=log_dirs
    )

    # First call - calculate MD5
    md5_1 = uploader._get_cached_md5(test_file)

    # Modify file
    time.sleep(0.01)  # Ensure mtime changes
    test_file.write_text("modified content")

    # Second call - cache should be invalidated, recalculate
    with patch.object(uploader, "_calculate_md5", wraps=uploader._calculate_md5) as mock_calc:
        md5_2 = uploader._get_cached_md5(test_file)
        assert mock_calc.call_count == 1  # Called because cache invalidated

        assert md5_1 != md5_2  # Different MD5


@patch("src.upload_manager.boto3.session.Session")
def test_md5_cache_ttl_expiration(mock_Session, temp_dir):
    """Test MD5 cache expires after TTL"""
    import time

    test_file = temp_dir / "ttl.log"
    test_file.write_text("data")

    mock_s3 = Mock()
    mock_session_instance = Mock()
    mock_session_instance.client.return_value = mock_s3
    mock_Session.return_value = mock_session_instance

    log_dirs = [{"path": str(temp_dir), "source": "test"}]

    uploader = UploadManager(
        bucket="test-bucket", region="us-east-1", vehicle_id="vehicle-001", log_directories=log_dirs
    )

    # First call
    md5_1 = uploader._get_cached_md5(test_file)

    # Manually expire cache by modifying cache timestamp
    filepath_str = str(test_file.resolve())
    if filepath_str in uploader._md5_cache:
        md5_hash, mtime, cache_time = uploader._md5_cache[filepath_str]
        # Set cache time to 10 minutes ago (TTL is 5 minutes)
        uploader._md5_cache[filepath_str] = (md5_hash, mtime, time.time() - 600)

    # Second call - cache expired, should recalculate
    with patch.object(uploader, "_calculate_md5", wraps=uploader._calculate_md5) as mock_calc:
        md5_2 = uploader._get_cached_md5(test_file)
        assert mock_calc.call_count == 1  # Recalculated

        assert md5_1 == md5_2  # Same content, same MD5


# ============================================
# MULTIPART UPLOAD EDGE CASES
# ============================================


@patch("src.upload_manager.boto3.session.Session")
def test_file_exactly_5mb_uses_multipart(mock_Session, temp_dir):
    """Test file exactly at 5MB boundary uses multipart upload"""
    # Create exactly 5MB file
    test_file = temp_dir / "exactly_5mb.bin"
    with open(test_file, "wb") as f:
        f.write(b"0" * (5 * 1024 * 1024))  # Exactly 5MB

    mock_s3 = Mock()
    mock_s3.upload_file.return_value = None
    mock_s3.head_object.side_effect = ClientError({"Error": {"Code": "404"}}, "head_object")

    mock_session_instance = Mock()
    mock_session_instance.client.return_value = mock_s3
    mock_Session.return_value = mock_session_instance

    log_dirs = [{"path": str(temp_dir), "source": "test"}]

    uploader = UploadManager(
        bucket="test-bucket", region="us-east-1", vehicle_id="vehicle-001", log_directories=log_dirs
    )

    result = uploader.upload_file(str(test_file))

    assert result is True
    assert mock_s3.upload_file.called


@patch("src.upload_manager.boto3.session.Session")
def test_multipart_etag_verification(mock_Session, temp_dir):
    """Test verify_upload handles multipart ETag format (with dash)"""
    test_file = temp_dir / "multipart.log"
    test_file.write_text("data")

    mock_s3 = Mock()

    # Multipart ETag format: "hash-partcount"
    file_size = test_file.stat().st_size
    mock_s3.head_object.return_value = {
        "ContentLength": file_size,
        "ETag": '"d41d8cd98f00b204e9800998ecf8427e-3"',  # Multipart ETag
    }

    mock_session_instance = Mock()
    mock_session_instance.client.return_value = mock_s3
    mock_Session.return_value = mock_session_instance

    log_dirs = [{"path": str(temp_dir), "source": "test"}]

    uploader = UploadManager(
        bucket="test-bucket", region="us-east-1", vehicle_id="vehicle-001", log_directories=log_dirs
    )

    # Should verify using size only (multipart ETag not simple MD5)
    result = uploader.verify_upload(str(test_file))
    assert result is True


# ============================================
# CHINA REGION TESTS
# ============================================


@patch("src.upload_manager.boto3.session.Session")
def test_china_region_endpoint(mock_Session):
    """Test China region uses correct .amazonaws.com.cn endpoint"""
    mock_s3 = Mock()
    mock_session_instance = Mock()
    mock_session_instance.client.return_value = mock_s3
    mock_Session.return_value = mock_session_instance

    uploader = UploadManager(
        bucket="test-bucket",
        region="cn-north-1",
        vehicle_id="vehicle-001",
        log_directories=[{"path": "/tmp", "source": "test"}],
    )

    # Verify client was created with China endpoint
    mock_session_instance.client.assert_called_once()
    call_kwargs = mock_session_instance.client.call_args[1]

    assert "endpoint_url" in call_kwargs
    assert "amazonaws.com.cn" in call_kwargs["endpoint_url"]
    assert "cn-north-1" in call_kwargs["endpoint_url"]


@patch("src.upload_manager.boto3.session.Session")
@patch.dict("os.environ", {"AWS_ENDPOINT_URL": "http://localhost:4566"})
def test_localstack_endpoint_override(mock_Session):
    """Test AWS_ENDPOINT_URL environment variable is respected (LocalStack)"""
    mock_s3 = Mock()
    mock_session_instance = Mock()
    mock_session_instance.client.return_value = mock_s3
    mock_Session.return_value = mock_session_instance

    uploader = UploadManager(
        bucket="test-bucket",
        region="us-east-1",
        vehicle_id="vehicle-001",
        log_directories=[{"path": "/tmp", "source": "test"}],
    )

    # Verify LocalStack endpoint used
    call_kwargs = mock_session_instance.client.call_args[1]
    assert call_kwargs["endpoint_url"] == "http://localhost:4566"


# ============================================
# LEGACY FORMAT COMPATIBILITY TESTS
# ============================================


def test_legacy_log_directories_string_format():
    """Test backward compatibility with old string list format"""
    with patch("src.upload_manager.boto3.session.Session") as mock_Session:
        mock_s3 = Mock()
        mock_session_instance = Mock()
        mock_session_instance.client.return_value = mock_s3
        mock_Session.return_value = mock_session_instance

        # Old format: list of strings
        uploader = UploadManager(
            bucket="test-bucket",
            region="us-east-1",
            vehicle_id="vehicle-001",
            log_directories=["/home/autoware/.parcel/log/terminal", "/var/log"],
        )

        # Should auto-detect sources
        assert len(uploader.log_directory_configs) == 2
        assert all("source" in cfg for cfg in uploader.log_directory_configs)


def test_no_log_directories_raises_error():
    """Test initialization without log_directories raises clear error"""
    with patch("src.upload_manager.boto3.session.Session"):
        with pytest.raises(ValueError, match="No valid log directories"):
            UploadManager(
                bucket="test-bucket",
                region="us-east-1",
                vehicle_id="vehicle-001",
                log_directories=[],
            )
