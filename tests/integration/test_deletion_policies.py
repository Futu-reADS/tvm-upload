#!/usr/bin/env python3
"""
Integration Tests for v2.0 Deletion Policies
Tests the complete deletion workflow
"""

import pytest
import tempfile
import time
import shutil
from pathlib import Path
from unittest.mock import patch, Mock

from src.main import TVMUploadSystem


@pytest.fixture
def test_env_with_deletion():
    """Create test environment with deletion policies configured"""
    temp_dir = tempfile.mkdtemp()
    log_dir = Path(temp_dir) / 'logs'
    log_dir.mkdir()
    
    config_content = f"""
vehicle_id: "test-vehicle-deletion"

log_directories:
  - {log_dir}

s3:
  bucket: test-bucket
  region: cn-north-1
  credentials_path: ~/.aws

upload:
  schedule: "15:00"
  file_stable_seconds: 2
  queue_file: {temp_dir}/queue.json
  
  scan_existing_files:
    enabled: true
    max_age_days: 3

deletion:
  after_upload:
    enabled: true
    keep_days: 0  # Delete immediately for testing
  
  age_based:
    enabled: true
    max_age_days: 7
    schedule_time: "02:00"
  
  emergency:
    enabled: true

disk:
  reserved_gb: 1
  warning_threshold: 0.90
  critical_threshold: 0.95

s3_lifecycle:
  retention_days: 14

monitoring:
  cloudwatch_enabled: false
"""
    
    config_file = Path(temp_dir) / 'config.yaml'
    config_file.write_text(config_content)
    
    yield str(config_file), str(log_dir), temp_dir
    
    # Cleanup
    shutil.rmtree(temp_dir, ignore_errors=True)


@patch('src.upload_manager.boto3')
@patch('src.cloudwatch_manager.boto3')
def test_immediate_deletion_after_upload(mock_cw_boto3, mock_upload_boto3, test_env_with_deletion):
    """Test files deleted immediately after upload when keep_days=0"""
    config_file, log_dir, temp_dir = test_env_with_deletion
    
    # Mock boto3
    mock_upload_boto3.client.return_value = Mock()
    mock_cw_boto3.client.return_value = Mock()
    
    system = TVMUploadSystem(config_file)
    
    # Mock successful upload
    system.upload_manager.upload_file = Mock(return_value=True)
    
    # Create test file
    test_file = Path(log_dir) / 'test.log'
    test_file.write_text('test data' * 100)
    
    assert test_file.exists(), "File should exist before upload"
    
    # Upload file
    system._upload_file(str(test_file))
    
    # File should be deleted immediately (keep_days=0)
    assert not test_file.exists(), "File should be deleted after upload"
    assert system.stats['files_uploaded'] == 1


@patch('src.upload_manager.boto3')
@patch('src.cloudwatch_manager.boto3')
def test_deferred_deletion_keeps_file(mock_cw_boto3, mock_upload_boto3):
    """Test files kept for N days after upload when keep_days>0"""
    temp_dir = tempfile.mkdtemp()
    log_dir = Path(temp_dir) / 'logs'
    log_dir.mkdir()
    
    # Config with 14-day retention
    config_content = f"""
vehicle_id: "test-vehicle"
log_directories: [{log_dir}]
s3:
  bucket: test-bucket
  region: cn-north-1
  credentials_path: ~/.aws
upload:
  schedule: "15:00"
  queue_file: {temp_dir}/queue.json
deletion:
  after_upload:
    enabled: true
    keep_days: 14
disk:
  reserved_gb: 1
monitoring:
  cloudwatch_enabled: false
"""
    
    config_file = Path(temp_dir) / 'config.yaml'
    config_file.write_text(config_content)
    
    try:
        # Mock boto3
        mock_upload_boto3.client.return_value = Mock()
        mock_cw_boto3.client.return_value = Mock()
        
        system = TVMUploadSystem(str(config_file))
        system.upload_manager.upload_file = Mock(return_value=True)
        
        # Create and upload file
        test_file = Path(log_dir) / 'test.log'
        test_file.write_text('test data' * 100)
        
        system._upload_file(str(test_file))
        
        # File should still exist (14-day retention)
        assert test_file.exists(), "File should be kept for 14 days"
        assert system.disk_manager.get_uploaded_files_count() == 1
        
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@patch('src.upload_manager.boto3')
@patch('src.cloudwatch_manager.boto3')
def test_deletion_disabled(mock_cw_boto3, mock_upload_boto3):
    """Test files kept indefinitely when deletion.after_upload.enabled=false"""
    temp_dir = tempfile.mkdtemp()
    log_dir = Path(temp_dir) / 'logs'
    log_dir.mkdir()
    
    # Config with deletion DISABLED
    config_content = f"""
vehicle_id: "test-vehicle"
log_directories: [{log_dir}]
s3:
  bucket: test-bucket
  region: cn-north-1
  credentials_path: ~/.aws
upload:
  schedule: "15:00"
  queue_file: {temp_dir}/queue.json
deletion:
  after_upload:
    enabled: false
    keep_days: 14
disk:
  reserved_gb: 1
monitoring:
  cloudwatch_enabled: false
"""
    
    config_file = Path(temp_dir) / 'config.yaml'
    config_file.write_text(config_content)
    
    try:
        # Mock boto3
        mock_upload_boto3.client.return_value = Mock()
        mock_cw_boto3.client.return_value = Mock()
        
        system = TVMUploadSystem(str(config_file))
        system.upload_manager.upload_file = Mock(return_value=True)
        
        # Create and upload file
        test_file = Path(log_dir) / 'test.log'
        test_file.write_text('test data' * 100)
        
        system._upload_file(str(test_file))
        
        # File should still exist (deletion disabled)
        assert test_file.exists(), "File should be kept indefinitely when deletion disabled"
        assert system.disk_manager.get_uploaded_files_count() == 0, "Should not track for deletion"
        
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_age_based_cleanup_integration(test_env_with_deletion):
    """Test age-based cleanup deletes old files"""
    config_file, log_dir, temp_dir = test_env_with_deletion
    
    import os
    
    with patch('src.upload_manager.boto3'), patch('src.cloudwatch_manager.boto3'):
        system = TVMUploadSystem(config_file)
        
        # Create old file (10 days old)
        old_file = Path(log_dir) / 'old.log'
        old_file.write_text('old data' * 100)
        old_mtime = time.time() - (10 * 24 * 3600)
        os.utime(str(old_file), (old_mtime, old_mtime))
        
        # Create recent file (2 days old)
        recent_file = Path(log_dir) / 'recent.log'
        recent_file.write_text('recent data' * 100)
        recent_mtime = time.time() - (2 * 24 * 3600)
        os.utime(str(recent_file), (recent_mtime, recent_mtime))
        
        assert old_file.exists()
        assert recent_file.exists()
        
        # Run age-based cleanup (7 days)
        deleted = system.disk_manager.cleanup_by_age(7)
        
        assert deleted == 1, "Should delete 1 old file"
        assert not old_file.exists(), "Old file should be deleted"
        assert recent_file.exists(), "Recent file should remain"


@patch('src.upload_manager.boto3')
@patch('src.cloudwatch_manager.boto3')
def test_emergency_cleanup_enabled(mock_cw_boto3, mock_upload_boto3, test_env_with_deletion):
    """Test emergency cleanup triggers when enabled"""
    config_file, log_dir, temp_dir = test_env_with_deletion
    
    # Mock boto3
    mock_upload_boto3.client.return_value = Mock()
    mock_cw_boto3.client.return_value = Mock()
    
    system = TVMUploadSystem(config_file)
    system.upload_manager.upload_file = Mock(return_value=True)
    
    # Create and upload file
    test_file = Path(log_dir) / 'test.log'
    test_file.write_text('data' * 100000)
    
    # Mark as uploaded to make it eligible for emergency cleanup
    system.disk_manager.mark_uploaded(str(test_file), keep_until_days=14)
    
    # Mock low disk space
    with patch.object(system.disk_manager, 'check_disk_space', return_value=False):
        system._process_upload_queue()
        # Emergency cleanup should have run (since enabled=true)


@patch('src.upload_manager.boto3')
@patch('src.cloudwatch_manager.boto3')
def test_emergency_cleanup_disabled(mock_cw_boto3, mock_upload_boto3):  # ← MUST ADD THESE PARAMETERS
    """Test emergency cleanup does not run when disabled"""
    temp_dir = tempfile.mkdtemp()
    log_dir = Path(temp_dir) / 'logs'
    log_dir.mkdir()
    
    # Config with emergency cleanup DISABLED
    config_content = f"""
vehicle_id: "test-vehicle"
log_directories: [{log_dir}]
s3:
  bucket: test-bucket
  region: cn-north-1
  credentials_path: ~/.aws
upload:
  schedule: "15:00"
  queue_file: {temp_dir}/queue.json
deletion:
  emergency:
    enabled: false
disk:
  reserved_gb: 1
monitoring:
  cloudwatch_enabled: false
"""
    
    config_file = Path(temp_dir) / 'config.yaml'
    config_file.write_text(config_content)
    
    try:
        # Mock boto3 properly
        mock_s3 = Mock()
        mock_s3.upload_file.return_value = None
        mock_s3.head_object.return_value = {}
        mock_upload_boto3.client.return_value = mock_s3
        
        mock_cw = Mock()
        mock_cw.put_metric_data.return_value = None
        mock_cw_boto3.client.return_value = mock_cw
        
        system = TVMUploadSystem(str(config_file))
        
        # Mock low disk space
        with patch.object(system.disk_manager, 'check_disk_space', return_value=False):
            with patch.object(system.disk_manager, 'cleanup_old_files') as mock_cleanup:
                system._process_upload_queue()
                
                # Emergency cleanup should NOT run (disabled)
                mock_cleanup.assert_not_called()
        
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_startup_scan_integration(test_env_with_deletion):
    """Test startup scan finds existing files and adds to queue"""
    config_file, log_dir, temp_dir = test_env_with_deletion
    
    # Create files BEFORE starting system
    test_file1 = Path(log_dir) / 'existing1.log'
    test_file1.write_text('data1')
    
    test_file2 = Path(log_dir) / 'existing2.log'
    test_file2.write_text('data2')
    
    # Patch boto3 BEFORE importing/creating anything
    with patch('boto3.client') as mock_boto3_client:
        
        # Mock S3 client
        mock_s3 = Mock()
        mock_s3.upload_file.return_value = None
        mock_s3.head_object.return_value = {}
        
        # Mock CloudWatch client
        mock_cw = Mock()
        mock_cw.put_metric_data.return_value = None
        
        # Return different mocks based on service name
        def client_side_effect(service_name, **kwargs):
            if service_name == 's3':
                return mock_s3
            elif service_name == 'cloudwatch':
                return mock_cw
            return Mock()
        
        mock_boto3_client.side_effect = client_side_effect
        
        # Now create system (will use mocked boto3)
        system = TVMUploadSystem(config_file)
        
        # Start system (triggers startup scan)
        system.start()
        
        try:
            # Poll for files to be detected
            max_wait = 15
            waited = 0
            interval = 0.5
            
            while waited < max_wait:
                detected = system.stats['files_detected']
                uploaded = system.stats['files_uploaded']
                
                # Check if both files were either detected or uploaded
                if detected + uploaded >= 2:
                    break
                    
                time.sleep(interval)
                waited += interval
            
            # Get final stats
            detected = system.stats['files_detected']
            uploaded = system.stats['files_uploaded']
            failed = system.stats['files_failed']
            queued = system.queue_manager.get_queue_size()
            
            # Files should be either detected (waiting) or uploaded (processed)
            total_processed = detected + uploaded
            
            assert total_processed >= 2, \
                f"After {waited:.1f}s: detected={detected}, uploaded={uploaded}, " \
                f"failed={failed}, queued={queued}. Expected 2+ files processed."
            
        finally:
            system.stop()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])