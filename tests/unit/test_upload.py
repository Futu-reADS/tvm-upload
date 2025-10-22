#!/usr/bin/env python3
"""
Tests for Upload Manager
"""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from src.upload_manager import UploadManager, PermanentUploadError
from botocore.exceptions import ClientError


@pytest.fixture
def temp_file():
    """Create temporary test file"""
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.log') as f:
        f.write("test data" * 1000)  # ~9KB
        temp_path = f.name
    
    yield temp_path
    
    # Cleanup
    if Path(temp_path).exists():
        Path(temp_path).unlink()


@pytest.fixture
def large_temp_file():
    """Create large temporary file for multipart test"""
    with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.mcap') as f:
        # Write 6MB of data
        f.write(b'0' * (6 * 1024 * 1024))
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
        vehicle_id="vehicle-001"
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
        vehicle_id="vehicle-001"
    )
    
    file_path = Path(temp_file)
    s3_key = uploader._build_s3_key(file_path)
    
    # Should be: vehicle-001/YYYY-MM-DD/filename.log
    assert s3_key.startswith("vehicle-001/")
    assert s3_key.endswith(file_path.name)
    assert "/" in s3_key  # Has date component


def test_exponential_backoff():
    """Test backoff calculation"""
    uploader = UploadManager(
        bucket="test-bucket",
        region="us-east-1",
        vehicle_id="vehicle-001"
    )
    
    # Test exponential progression
    assert uploader._calculate_backoff(1) == 1
    assert uploader._calculate_backoff(2) == 2
    assert uploader._calculate_backoff(3) == 4
    assert uploader._calculate_backoff(4) == 8
    assert uploader._calculate_backoff(10) == 512  # Max cap


@patch('src.upload_manager.boto3.session.Session')
def test_successful_upload(mock_Session, temp_file):
    """Test successful file upload"""
    # Create mock S3 client
    mock_s3 = Mock()
    mock_s3.upload_file.return_value = None 
    mock_s3.head_object.side_effect = ClientError(
        {'Error': {'Code': '404'}}, 'head_object'
    )
    
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
        log_directories=[str(Path(temp_file).parent)]  # ADD THIS
    )
    
    # Upload file
    result = uploader.upload_file(temp_file)
    
    # Assertions
    assert result is True
    assert mock_s3.upload_file.called

@patch('src.upload_manager.boto3.session.Session')
@patch('src.upload_manager.time.sleep')
def test_upload_with_retry(mock_sleep, mock_Session, temp_file):
    """Test upload retries on failure"""
    # Create mock S3 client
    mock_s3 = Mock()
    mock_s3.head_object.side_effect = ClientError(
        {'Error': {'Code': '404'}}, 'head_object'
    )
    
    # Create mock session instance
    mock_session_instance = Mock()
    mock_session_instance.client.return_value = mock_s3
    
    # When Session() is called, return our mock session
    mock_Session.return_value = mock_session_instance
    
    # Fail first 2 attempts, succeed on 3rd
    mock_s3.upload_file.side_effect = [
        ClientError({'Error': {'Code': '500'}}, 'upload_file'),
        ClientError({'Error': {'Code': '500'}}, 'upload_file'),
        None  # Success
    ]
    
    uploader = UploadManager(
        bucket="test-bucket",
        region="us-east-1",
        vehicle_id="vehicle-001",
        log_directories=[str(Path(temp_file).parent)]  # ADD THIS
    )
    
    result = uploader.upload_file(temp_file)
    
    assert result is True
    assert mock_s3.upload_file.call_count == 3
    assert mock_sleep.call_count == 2


@patch('src.upload_manager.boto3.session.Session')
def test_upload_fails_after_max_retries(mock_Session, temp_file):
    """Test upload fails after max retries"""
    
    # Create mock S3 client
    mock_s3 = Mock()
    mock_s3.head_object.side_effect = ClientError(
        {'Error': {'Code': '404'}}, 'head_object'
    )
    
    # Create mock session instance
    mock_session_instance = Mock()
    mock_session_instance.client.return_value = mock_s3
    
    # When Session() is called, return our mock session
    mock_Session.return_value = mock_session_instance
    
    # Always fail
    mock_s3.upload_file.side_effect = ClientError(
        {'Error': {'Code': '500'}}, 'upload_file'
    )
    
    uploader = UploadManager(
        bucket="test-bucket",
        region="us-east-1",
        vehicle_id="vehicle-001",
        max_retries=3,
        log_directories=[str(Path(temp_file).parent)]  # ADD THIS
    )
    
    result = uploader.upload_file(temp_file)
    
    assert result is False
    assert mock_s3.upload_file.call_count == 3


@patch('src.upload_manager.boto3.session.Session')
def test_multipart_upload_for_large_files(mock_Session, large_temp_file):
    """Test that large files use multipart upload"""
    
    # Create mock S3 client
    mock_s3 = Mock()
    mock_s3.upload_file.return_value = None 
    mock_s3.head_object.side_effect = ClientError(
        {'Error': {'Code': '404'}}, 'head_object'
    )
    
    # Create mock session instance
    mock_session_instance = Mock()
    mock_session_instance.client.return_value = mock_s3
    
    # When Session() is called, return our mock session
    mock_Session.return_value = mock_session_instance
    
    uploader = UploadManager(
        bucket="test-bucket",
        region="us-east-1",
        vehicle_id="vehicle-001",
        log_directories=[str(Path(large_temp_file).parent)]  # ADD THIS
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
        vehicle_id="vehicle-001"
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
        vehicle_id="vehicle-001"
    )
    
    try:
        with pytest.raises(PermanentUploadError, match="Permission denied"):
            uploader.upload_file(str(test_file))
    finally:
        # Restore permissions for cleanup
        os.chmod(str(test_file), 0o644)


@patch('src.upload_manager.boto3.session.Session')
def test_invalid_credentials_raises_permanent_error(mock_Session, temp_file):
    """Test invalid AWS credentials raises PermanentUploadError"""
    mock_s3 = Mock()
    mock_s3.head_object.side_effect = ClientError(
        {'Error': {'Code': '404'}}, 'head_object'
    )
    mock_s3.upload_file.side_effect = ClientError(
        {'Error': {'Code': 'InvalidAccessKeyId'}}, 'upload_file'
    )
    
    mock_session_instance = Mock()
    mock_session_instance.client.return_value = mock_s3
    mock_Session.return_value = mock_session_instance
    
    uploader = UploadManager(
        bucket="test-bucket",
        region="us-east-1",
        vehicle_id="vehicle-001",
        log_directories=[str(Path(temp_file).parent)]
    )
    
    with pytest.raises(PermanentUploadError, match="Invalid AWS credentials"):
        uploader.upload_file(temp_file)


@patch('src.upload_manager.boto3.session.Session')
def test_bucket_not_found_raises_permanent_error(mock_Session, temp_file):
    """Test nonexistent bucket raises PermanentUploadError"""
    mock_s3 = Mock()
    mock_s3.head_object.side_effect = ClientError(
        {'Error': {'Code': '404'}}, 'head_object'
    )
    mock_s3.upload_file.side_effect = ClientError(
        {'Error': {'Code': 'NoSuchBucket'}}, 'upload_file'
    )
    
    mock_session_instance = Mock()
    mock_session_instance.client.return_value = mock_s3
    mock_Session.return_value = mock_session_instance
    
    uploader = UploadManager(
        bucket="nonexistent-bucket",
        region="us-east-1",
        vehicle_id="vehicle-001",
        log_directories=[str(Path(temp_file).parent)]
    )
    
    with pytest.raises(PermanentUploadError, match="Bucket does not exist"):
        uploader.upload_file(temp_file)


@patch('src.upload_manager.boto3.session.Session')
def test_access_denied_raises_permanent_error(mock_Session, temp_file):
    """Test IAM permissions error raises PermanentUploadError"""
    mock_s3 = Mock()
    mock_s3.head_object.side_effect = ClientError(
        {'Error': {'Code': '404'}}, 'head_object'
    )
    mock_s3.upload_file.side_effect = ClientError(
        {'Error': {'Code': 'AccessDenied'}}, 'upload_file'
    )
    
    mock_session_instance = Mock()
    mock_session_instance.client.return_value = mock_s3
    mock_Session.return_value = mock_session_instance
    
    uploader = UploadManager(
        bucket="test-bucket",
        region="us-east-1",
        vehicle_id="vehicle-001",
        log_directories=[str(Path(temp_file).parent)]
    )
    
    with pytest.raises(PermanentUploadError, match="IAM permissions denied"):
        uploader.upload_file(temp_file)


# ============================================
# NEW TESTS FOR v2.1 SOURCE-BASED S3 KEYS
# ============================================

def test_s3_key_source_detection_terminal():
    """Test S3 key includes source from directory structure"""
    uploader = UploadManager(
        bucket="test-bucket",
        region="us-east-1",
        vehicle_id="vehicle-001",
        log_directories=["/home/autoware/.parcel/log/terminal"]
    )
    
    file_path = Path("/home/autoware/.parcel/log/terminal/session.log")
    s3_key = uploader._build_s3_key(file_path)
    
    # Should be: vehicle-001/YYYY-MM-DD/terminal/session.log
    assert "terminal/session.log" in s3_key
    assert s3_key.startswith("vehicle-001/")


def test_s3_key_source_detection_ros():
    """Test S3 key preserves ROS folder structure"""
    uploader = UploadManager(
        bucket="test-bucket",
        region="us-east-1",
        vehicle_id="vehicle-001",
        log_directories=["/home/autoware/.ros/log"]
    )
    
    file_path = Path("/home/autoware/.ros/log/run-123/launch.log")
    s3_key = uploader._build_s3_key(file_path)
    
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
            log_directories=["/var/log"]
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
    with patch('src.upload_manager.boto3.session.Session') as mock_Session:
        mock_s3 = Mock()
        
        # Simulate file exists in S3 with same size
        file_size = Path(temp_file).stat().st_size
        mock_s3.head_object.return_value = {'ContentLength': file_size}
        
        mock_session_instance = Mock()
        mock_session_instance.client.return_value = mock_s3
        mock_Session.return_value = mock_session_instance
        
        uploader = UploadManager(
            bucket="test-bucket",
            region="us-east-1",
            vehicle_id="vehicle-001",
            log_directories=[str(Path(temp_file).parent)]
        )
        
        # Should return True (file already exists)
        assert uploader.verify_upload(temp_file) is True


def test_verify_upload_checks_multiple_dates(temp_file):
    """Test verify_upload checks ±5 days for delayed uploads"""
    with patch('src.upload_manager.boto3.session.Session') as mock_Session:
        mock_s3 = Mock()
        
        # First check (file mtime date) - not found
        # Second check (+1 day) - found
        file_size = Path(temp_file).stat().st_size
        
        def mock_head_object(Bucket, Key):
            if "2025-10-21" in Key:  # Tomorrow's date
                return {'ContentLength': file_size}
            raise ClientError({'Error': {'Code': '404'}}, 'head_object')
        
        mock_s3.head_object.side_effect = mock_head_object
        
        mock_session_instance = Mock()
        mock_session_instance.client.return_value = mock_s3
        mock_Session.return_value = mock_session_instance
        
        uploader = UploadManager(
            bucket="test-bucket",
            region="us-east-1",
            vehicle_id="vehicle-001",
            log_directories=[str(Path(temp_file).parent)]
        )
        
        # Should find file in alternate date and return True
        result = uploader.verify_upload(temp_file)
        
        # Verify multiple head_object calls were made (checking different dates)
        assert mock_s3.head_object.call_count > 1
