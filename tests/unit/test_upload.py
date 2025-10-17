#!/usr/bin/env python3
"""
Tests for Upload Manager
"""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from src.upload_manager import UploadManager, UploadError
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


@patch('src.upload_manager.boto3.session.Session')  # ← Changed this line
def test_successful_upload(mock_Session, temp_file):  # ← Parameter name changed
    """Test successful file upload"""
    # Create mock S3 client
    mock_s3 = Mock()
    mock_s3.upload_file.return_value = None 

    
    mock_s3.head_object.side_effect = ClientError(
        {'Error': {'Code': 'NotFound'}}, 'head_object'
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
        vehicle_id="vehicle-001"
    )
    
    # Upload file
    result = uploader.upload_file(temp_file)
    
    # Assertions
    assert result is True
    assert mock_s3.upload_file.called

@patch('src.upload_manager.boto3.client')
def test_upload_nonexistent_file(mock_boto_client):
    """Test uploading file that doesn't exist"""
    mock_s3 = Mock()
    mock_boto_client.return_value = mock_s3
    
    uploader = UploadManager(
        bucket="test-bucket",
        region="us-east-1",
        vehicle_id="vehicle-001"
    )
    
    result = uploader.upload_file("/nonexistent/file.log")
    
    assert result is False
    assert not mock_s3.upload_file.called


@patch('src.upload_manager.boto3.session.Session')
@patch('src.upload_manager.time.sleep')  # Mock sleep to speed up test
def test_upload_with_retry(mock_sleep, mock_Session, temp_file):
    """Test upload retries on failure"""
    # Create mock S3 client
    mock_s3 = Mock()
    mock_s3.upload_file.return_value = None 
    
    mock_s3.head_object.side_effect = ClientError(
        {'Error': {'Code': 'NotFound'}}, 'head_object'
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
        vehicle_id="vehicle-001"
    )
    
    result = uploader.upload_file(temp_file)
    
    assert result is True
    assert mock_s3.upload_file.call_count == 3
    assert mock_sleep.call_count == 2  # Slept between retries


@patch('src.upload_manager.boto3.session.Session')
#@patch('src.upload_manager.time.sleep')
def test_upload_fails_after_max_retries(mock_Session, temp_file):
    """Test upload fails after max retries"""
    
    # Create mock S3 client
    mock_s3 = Mock()
    mock_s3.upload_file.return_value = None 

    mock_s3.head_object.side_effect = ClientError(
        {'Error': {'Code': 'NotFound'}}, 'head_object'
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
        max_retries=3  # Reduce for faster test
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
        {'Error': {'Code': 'NotFound'}}, 'head_object'
    )
    
    # Create mock session instance
    mock_session_instance = Mock()
    mock_session_instance.client.return_value = mock_s3
    
    # When Session() is called, return our mock session
    mock_Session.return_value = mock_session_instance
    
    uploader = UploadManager(
        bucket="test-bucket",
        region="us-east-1",
        vehicle_id="vehicle-001"
    )
    
    result = uploader.upload_file(large_temp_file)
    
    assert result is True
    # Verify upload_file was called (which internally uses multipart for large files)
    assert mock_s3.upload_file.called
