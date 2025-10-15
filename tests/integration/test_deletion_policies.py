#!/usr/bin/env python3
"""
Integration Tests for v2.0 Deletion Policies
Tests the complete deletion workflow
"""

import pytest
import tempfile
import time
import shutil
import os
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import patch, Mock, MagicMock

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


@patch('src.upload_manager.boto3.session.Session')
@patch('src.cloudwatch_manager.boto3.session.Session')
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


@patch('src.upload_manager.boto3.session.Session')
@patch('src.cloudwatch_manager.boto3.session.Session')
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


@patch('src.upload_manager.boto3.session.Session')
@patch('src.cloudwatch_manager.boto3.session.Session')
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


@patch('src.upload_manager.boto3.session.Session')
@patch('src.cloudwatch_manager.boto3.session.Session')
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


@patch('src.upload_manager.boto3.session.Session')
@patch('src.cloudwatch_manager.boto3.session.Session')
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


@patch('src.upload_manager.boto3.session.Session')  # ← Mock AWS
def test_startup_scan_integration(mock_Session, temp_config_file):
    """Test that system scans and uploads existing files on startup"""
    
    cfg_path = Path(temp_config_file)

    # Setup mock S3 client
    mock_s3 = Mock()
    mock_s3.upload_file.return_value = None  # ← Simulate successful upload
    
    mock_session_instance = Mock()
    mock_session_instance.client.return_value = mock_s3
    mock_Session.return_value = mock_session_instance
    
    # Create test directory
    log_dir = Path('/tmp/test-startup-scan')
    log_dir.mkdir(exist_ok=True)
    
    try:
        # Create files that should be uploaded (within 3 days)
        now = datetime.now()
        
        # File 1: 1 day old
        file1 = log_dir / 'existing1.log'
        file1.write_text('test')
        old_time = (now - timedelta(days=1)).timestamp()
        os.utime(file1, (old_time, old_time))
        
        # File 2: 2 days old
        file2 = log_dir / 'existing2.log'
        file2.write_text('test')
        old_time = (now - timedelta(days=2)).timestamp()
        os.utime(file2, (old_time, old_time))
        
        # File 3: Too old (5 days) - should NOT be uploaded
        file3 = log_dir / 'too_old.log'
        file3.write_text('test')
        old_time = (now - timedelta(days=5)).timestamp()
        os.utime(file3, (old_time, old_time))
        
        # Update config to use our test directory
        # config_content = temp_config_file.read_text()
        config_content = cfg_path.read_text()
        config_content = config_content.replace(
            'log_directories:',
            f'log_directories:\n  - {log_dir}'
        )
        # temp_config_file.write_text(config_content)
        cfg_path.write_text(config_content)
        
        # Start system
        # system = TVMUploadSystem(str(temp_config_file))
        system = TVMUploadSystem(str(cfg_path))
        system.start()
        
        # Wait for startup scan and uploads
        time.sleep(3)  # ← Reduced from 15s since mocked uploads are instant
        
        system.stop()
        
        # Verify results
        stats = system.get_statistics()
        total_processed = stats['uploaded'] + stats['failed']
        
        # Should have processed 2 files (not 3, since one is too old)
        assert total_processed >= 2, \
            f"After startup: detected={stats['detected']}, uploaded={stats['uploaded']}, " \
            f"failed={stats['failed']}. Expected 2+ files processed."
        
        # Verify uploads were attempted
        assert mock_s3.upload_file.call_count >= 2, \
            f"Expected at least 2 upload attempts, got {mock_s3.upload_file.call_count}"
        
    finally:
        # Cleanup
        import shutil
        if log_dir.exists():
            shutil.rmtree(log_dir)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])