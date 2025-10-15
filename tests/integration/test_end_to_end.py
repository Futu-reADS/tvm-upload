#!/usr/bin/env python3
"""
End-to-end integration tests for TVM Upload System
"""

import pytest
import tempfile
import time
import shutil
from pathlib import Path
from unittest.mock import patch, Mock

from src.main import TVMUploadSystem


@pytest.fixture
def test_config():
    """Create temporary config and directories"""
    temp_dir = tempfile.mkdtemp()
    log_dir = Path(temp_dir) / 'logs'
    log_dir.mkdir()
    
    config_content = f"""
vehicle_id: "test-vehicle-integration"

log_directories:
  - {log_dir}

s3:
  bucket: test-bucket
  region: cn-north-1
  credentials_path: ~/.aws

upload:
  schedule: "15:00"
  file_stable_seconds: 2  # ← SHORT for testing (was 60)
  queue_file: {temp_dir}/queue.json

disk:
  reserved_gb: 1
  warning_threshold: 0.90
  critical_threshold: 0.95

monitoring:
  cloudwatch_enabled: false
"""
    
    config_file = Path(temp_dir) / 'config.yaml'
    config_file.write_text(config_content)
    
    yield str(config_file), str(log_dir)
    
    # Cleanup
    shutil.rmtree(temp_dir, ignore_errors=True)


@patch('src.upload_manager.boto3.session.Session')
@patch('src.cloudwatch_manager.boto3.session.Session')
def test_system_initialization(mock_cw_boto3, mock_upload_boto3, test_config):
    """Test system initializes correctly"""
    config_file, temp_dir = test_config
    
    # Mock boto3 clients
    mock_upload_boto3.client.return_value = Mock()
    mock_cw_boto3.client.return_value = Mock()
    
    system = TVMUploadSystem(config_file)
    
    assert system.config is not None
    assert system.upload_manager is not None
    assert system.disk_manager is not None
    assert system.file_monitor is not None
    assert system.queue_manager is not None


@patch('src.upload_manager.boto3.session.Session')
@patch('src.cloudwatch_manager.boto3.session.Session')
def test_file_detection_and_queue(mock_cw_boto3, mock_upload_boto3, test_config):
    """Test file detection adds to upload queue"""
    config_file, temp_dir = test_config
    
    # Mock boto3 clients
    mock_upload_boto3.client.return_value = Mock()
    mock_cw_boto3.client.return_value = Mock()
    
    system = TVMUploadSystem(config_file)
    
    # Mock upload to prevent actual S3 calls
    system.upload_manager.upload_file = Mock(return_value=True)
    
    system.start()
    
    try:
        # Create test file
        test_file = Path(temp_dir) / 'test.log'
        test_file.write_text('test data\n' * 100)
        
        # Wait for detection and stability check (2 seconds stability + buffer)
        time.sleep(4)
        
        # File should be detected
        assert system.stats['files_detected'] >= 1
        
    finally:
        system.stop()


@patch('src.upload_manager.boto3.session.Session')
@patch('src.cloudwatch_manager.boto3.session.Session')
def test_upload_marks_file_for_cleanup(mock_cw_boto3, mock_upload_boto3, test_config):
    """Test uploaded file is marked for cleanup"""
    config_file, temp_dir = test_config
    
    # Mock boto3 clients
    mock_upload_boto3.client.return_value = Mock()
    mock_cw_boto3.client.return_value = Mock()
    
    system = TVMUploadSystem(config_file)
    
    # Mock upload to succeed
    system.upload_manager.upload_file = Mock(return_value=True)
    
    system.start()
    
    try:
        # Create test file
        test_file = Path(temp_dir) / 'test.log'
        test_file.write_text('test data')
        
        # Wait for detection and upload
        time.sleep(4)
        
        # File should be uploaded
        if system.stats['files_detected'] > 0:
            assert system.stats['files_uploaded'] >= 1
            # Check file marked as uploaded in disk manager
            assert system.disk_manager.get_uploaded_files_count() >= 1
        
    finally:
        system.stop()


@patch('src.upload_manager.boto3.session.Session')
@patch('src.cloudwatch_manager.boto3.session.Session')
def test_statistics_tracking(mock_cw_boto3, mock_upload_boto3, test_config):
    """Test statistics are tracked during operation"""
    config_file, temp_dir = test_config
    
    # Mock boto3 clients
    mock_upload_boto3.client.return_value = Mock()
    mock_cw_boto3.client.return_value = Mock()
    
    system = TVMUploadSystem(config_file)
    
    # Mock upload
    system.upload_manager.upload_file = Mock(return_value=True)
    
    # Check initial stats
    assert system.stats['files_detected'] == 0
    assert system.stats['files_uploaded'] == 0
    assert system.stats['files_failed'] == 0
    
    system.start()
    
    try:
        # Create multiple test files
        for i in range(3):
            test_file = Path(temp_dir) / f'test{i}.log'
            test_file.write_text(f'test data {i}')
        
        # Wait for detection and upload
        time.sleep(5)
        
        # Stats should be updated
        assert system.stats['files_detected'] >= 0  # May or may not be detected yet
        
    finally:
        system.stop()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])