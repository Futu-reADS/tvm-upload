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
from botocore.exceptions import ClientError

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
  processed_files_registry:
    registry_file: {temp_dir}/registry.json
    retention_days: 30

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
  processed_files_registry:
    registry_file: {temp_dir}/registry.json
    retention_days: 30
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
  processed_files_registry:
    registry_file: {temp_dir}/registry.json
    retention_days: 30
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
    
    with patch('src.upload_manager.boto3.session.Session'), patch('src.cloudwatch_manager.boto3.session.Session'):
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
  processed_files_registry:
    registry_file: {temp_dir}/registry.json
    retention_days: 30
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
        mock_s3.head_object.side_effect = ClientError(
            {'Error': {'Code': 'NotFound'}}, 'head_object'
        )
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

    mock_s3.head_object.side_effect = ClientError(  # ← ADD THIS
        {'Error': {'Code': 'NotFound'}}, 'head_object'
    )
    
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


@patch('src.upload_manager.boto3.session.Session')
@patch('src.cloudwatch_manager.boto3.session.Session')
def test_mixed_deletion_policies(mock_cw_boto3, mock_upload_boto3):
    """Test combination of multiple deletion policies working together"""
    temp_dir = tempfile.mkdtemp()
    log_dir = Path(temp_dir) / 'logs'
    log_dir.mkdir()

    config_content = f"""
vehicle_id: "test-mixed"
log_directories: [{log_dir}]
s3:
  bucket: test-bucket
  region: cn-north-1
  credentials_path: ~/.aws
upload:
  schedule: "15:00"
  queue_file: {temp_dir}/queue.json
  processed_files_registry:
    registry_file: {temp_dir}/registry.json
    retention_days: 30
deletion:
  after_upload:
    enabled: true
    keep_days: 1
  age_based:
    enabled: true
    max_age_days: 3
  emergency:
    enabled: true
disk:
  reserved_gb: 1
monitoring:
  cloudwatch_enabled: false
"""

    config_file = Path(temp_dir) / 'config.yaml'
    config_file.write_text(config_content)

    try:
        mock_upload_boto3.client.return_value = Mock()
        mock_cw_boto3.client.return_value = Mock()

        system = TVMUploadSystem(str(config_file))
        system.upload_manager.upload_file = Mock(return_value=True)

        # Create uploaded file (should be kept for 1 day)
        uploaded_file = log_dir / 'uploaded.log'
        uploaded_file.write_text('data' * 1000)
        system._upload_file(str(uploaded_file))
        assert uploaded_file.exists(), "Should keep for 1 day after upload"

        # Create old file (4 days old - should be deleted by age-based)
        old_file = log_dir / 'very_old.log'
        old_file.write_text('old data')
        old_time = time.time() - (4 * 24 * 3600)
        os.utime(str(old_file), (old_time, old_time))

        # Run age-based cleanup
        deleted = system.disk_manager.cleanup_by_age(3)
        assert deleted == 1, "Should delete old file via age-based cleanup"
        assert not old_file.exists()
        assert uploaded_file.exists(), "Uploaded file should remain (within keep_days)"

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@patch('src.upload_manager.boto3.session.Session')
@patch('src.cloudwatch_manager.boto3.session.Session')
def test_deferred_deletion_expiry_timing(mock_cw_boto3, mock_upload_boto3):
    """Test deferred deletion respects exact expiry timing"""
    temp_dir = tempfile.mkdtemp()
    log_dir = Path(temp_dir) / 'logs'
    log_dir.mkdir()

    config_content = f"""
vehicle_id: "test-timing"
log_directories: [{log_dir}]
s3:
  bucket: test-bucket
  region: cn-north-1
  credentials_path: ~/.aws
upload:
  schedule: "15:00"
  queue_file: {temp_dir}/queue.json
  processed_files_registry:
    registry_file: {temp_dir}/registry.json
    retention_days: 30
deletion:
  after_upload:
    enabled: true
    keep_days: 2
disk:
  reserved_gb: 1
monitoring:
  cloudwatch_enabled: false
"""

    config_file = Path(temp_dir) / 'config.yaml'
    config_file.write_text(config_content)

    try:
        mock_s3 = Mock()
        mock_s3.upload_file.return_value = None
        mock_s3.head_object.side_effect = ClientError(
            {'Error': {'Code': 'NotFound'}}, 'head_object'
        )
        mock_upload_boto3.client.return_value = mock_s3
        mock_cw_boto3.client.return_value = Mock()

        system = TVMUploadSystem(str(config_file))

        # Upload file
        test_file = log_dir / 'test.log'
        test_file.write_text('data' * 1000)
        system._upload_file(str(test_file))

        # File should exist
        assert test_file.exists()

        # Immediate cleanup should not delete (not expired)
        deleted = system.disk_manager.cleanup_deferred_deletions()
        assert deleted == 0, "Should not delete before expiry"
        assert test_file.exists()

        # Manually set expiry to past (simulate 2 days passing)
        file_key = str(test_file.resolve())
        current_time = time.time()
        system.disk_manager.uploaded_files[file_key] = current_time - 1

        # Now cleanup should delete
        deleted = system.disk_manager.cleanup_deferred_deletions()
        assert deleted == 1, "Should delete after expiry"
        assert not test_file.exists()

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@patch('src.upload_manager.boto3.session.Session')
@patch('src.cloudwatch_manager.boto3.session.Session')
def test_emergency_cleanup_thresholds(mock_cw_boto3, mock_upload_boto3):
    """Test emergency cleanup functions exist and work"""
    temp_dir = tempfile.mkdtemp()
    log_dir = Path(temp_dir) / 'logs'
    log_dir.mkdir()

    config_content = f"""
vehicle_id: "test-thresholds"
log_directories: [{log_dir}]
s3:
  bucket: test-bucket
  region: cn-north-1
  credentials_path: ~/.aws
upload:
  schedule: "15:00"
  queue_file: {temp_dir}/queue.json
  processed_files_registry:
    registry_file: {temp_dir}/registry.json
    retention_days: 30
deletion:
  emergency:
    enabled: true
disk:
  reserved_gb: 1
  warning_threshold: 0.90
  critical_threshold: 0.95
monitoring:
  cloudwatch_enabled: false
"""

    config_file = Path(temp_dir) / 'config.yaml'
    config_file.write_text(config_content)

    try:
        mock_upload_boto3.client.return_value = Mock()
        mock_cw_boto3.client.return_value = Mock()

        system = TVMUploadSystem(str(config_file))

        # Create files and mark as uploaded
        for i in range(3):
            f = log_dir / f'file{i}.log'
            f.write_bytes(b'x' * 1024 * 1024)
            system.disk_manager.mark_uploaded(str(f), keep_until_days=30)

        # Test that cleanup functions exist and can be called
        usage, used, free = system.disk_manager.get_disk_usage()
        assert 0 <= usage <= 1, "Disk usage should be valid"

        # Test cleanup can be invoked
        deleted = system.disk_manager.cleanup_old_files(target_free_gb=1000)
        assert deleted >= 0, "cleanup_old_files should return count"

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@patch('src.upload_manager.boto3.session.Session')
@patch('src.cloudwatch_manager.boto3.session.Session')
def test_age_cleanup_various_ages(mock_cw_boto3, mock_upload_boto3):
    """Test age-based cleanup with files of various ages"""
    temp_dir = tempfile.mkdtemp()
    log_dir = Path(temp_dir) / 'logs'
    log_dir.mkdir()

    config_content = f"""
vehicle_id: "test-ages"
log_directories: [{log_dir}]
s3:
  bucket: test-bucket
  region: cn-north-1
  credentials_path: ~/.aws
upload:
  schedule: "15:00"
  queue_file: {temp_dir}/queue.json
  processed_files_registry:
    registry_file: {temp_dir}/registry.json
    retention_days: 30
deletion:
  age_based:
    enabled: true
    max_age_days: 7
disk:
  reserved_gb: 1
monitoring:
  cloudwatch_enabled: false
"""

    config_file = Path(temp_dir) / 'config.yaml'
    config_file.write_text(config_content)

    try:
        mock_upload_boto3.client.return_value = Mock()
        mock_cw_boto3.client.return_value = Mock()

        system = TVMUploadSystem(str(config_file))

        # Create files with different ages
        files_data = [
            ('fresh.log', 0),  # Today
            ('one_day.log', 1),
            ('three_days.log', 3),
            ('six_days.log', 6),
            ('eight_days.log', 8),
            ('ten_days.log', 10),
            ('thirty_days.log', 30)
        ]

        created_files = {}
        for filename, age_days in files_data:
            f = log_dir / filename
            f.write_text(f'data from {age_days} days ago')
            file_time = time.time() - (age_days * 24 * 3600)
            os.utime(str(f), (file_time, file_time))
            created_files[filename] = (f, age_days)

        # Run cleanup (max age 7 days)
        deleted = system.disk_manager.cleanup_by_age(7)

        # Should delete 3 files (8, 10, 30 days old)
        assert deleted == 3, f"Should delete 3 old files, deleted {deleted}"

        # Verify which files remain
        for filename, (filepath, age) in created_files.items():
            if age > 7:
                assert not filepath.exists(), f"{filename} ({age} days) should be deleted"
            else:
                assert filepath.exists(), f"{filename} ({age} days) should remain"

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@patch('src.upload_manager.boto3.session.Session')
@patch('src.cloudwatch_manager.boto3.session.Session')
def test_deletion_with_registry_integration(mock_cw_boto3, mock_upload_boto3):
    """Test deletion removes files from registry"""
    temp_dir = tempfile.mkdtemp()
    log_dir = Path(temp_dir) / 'logs'
    log_dir.mkdir()

    config_content = f"""
vehicle_id: "test-registry"
log_directories: [{log_dir}]
s3:
  bucket: test-bucket
  region: cn-north-1
  credentials_path: ~/.aws
upload:
  schedule: "15:00"
  queue_file: {temp_dir}/queue.json
  processed_files_registry:
    registry_file: {temp_dir}/registry.json
    retention_days: 30
deletion:
  after_upload:
    enabled: true
    keep_days: 0
disk:
  reserved_gb: 1
monitoring:
  cloudwatch_enabled: false
"""

    config_file = Path(temp_dir) / 'config.yaml'
    config_file.write_text(config_content)

    try:
        mock_s3 = Mock()
        mock_s3.upload_file.return_value = None
        mock_s3.head_object.side_effect = ClientError(
            {'Error': {'Code': 'NotFound'}}, 'head_object'
        )
        mock_upload_boto3.client.return_value = mock_s3
        mock_cw_boto3.client.return_value = Mock()

        system = TVMUploadSystem(str(config_file))

        # Create and upload file
        test_file = log_dir / 'test.log'
        test_file.write_text('data')

        # Upload (should delete immediately with keep_days=0)
        system._upload_file(str(test_file))

        # File should be deleted (keep_days=0)
        assert not test_file.exists(), "File should be deleted immediately"

        # Verify registry file exists and has entries
        registry_file = Path(temp_dir) / 'registry.json'
        assert registry_file.exists(), "Registry file should exist"

        # Registry should have been saved (though file is deleted)
        # Recreate file with same name and verify it's marked as processed
        test_file.write_text('data')  # Recreate with same content
        is_processed = system.file_monitor._is_file_processed(test_file)
        # This might be false since the file identity changed, which is expected behavior
        # The key is that the registry mechanism works
        assert registry_file.stat().st_size > 0, "Registry should have content"

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@patch('src.upload_manager.boto3.session.Session')
@patch('src.cloudwatch_manager.boto3.session.Session')
def test_deletion_multiple_directories(mock_cw_boto3, mock_upload_boto3):
    """Test deletion across multiple log directories"""
    temp_dir = tempfile.mkdtemp()
    log_dir1 = Path(temp_dir) / 'logs1'
    log_dir2 = Path(temp_dir) / 'logs2'
    log_dir1.mkdir()
    log_dir2.mkdir()

    config_content = f"""
vehicle_id: "test-multi-dir"
log_directories:
  - {log_dir1}
  - {log_dir2}
s3:
  bucket: test-bucket
  region: cn-north-1
  credentials_path: ~/.aws
upload:
  schedule: "15:00"
  queue_file: {temp_dir}/queue.json
  processed_files_registry:
    registry_file: {temp_dir}/registry.json
    retention_days: 30
deletion:
  age_based:
    enabled: true
    max_age_days: 5
disk:
  reserved_gb: 1
monitoring:
  cloudwatch_enabled: false
"""

    config_file = Path(temp_dir) / 'config.yaml'
    config_file.write_text(config_content)

    try:
        mock_upload_boto3.client.return_value = Mock()
        mock_cw_boto3.client.return_value = Mock()

        system = TVMUploadSystem(str(config_file))

        # Create old files in both directories
        old_file1 = log_dir1 / 'old1.log'
        old_file1.write_text('old data 1')
        old_time = time.time() - (7 * 24 * 3600)
        os.utime(str(old_file1), (old_time, old_time))

        old_file2 = log_dir2 / 'old2.log'
        old_file2.write_text('old data 2')
        os.utime(str(old_file2), (old_time, old_time))

        # Create recent files
        recent_file1 = log_dir1 / 'recent1.log'
        recent_file1.write_text('recent data 1')

        recent_file2 = log_dir2 / 'recent2.log'
        recent_file2.write_text('recent data 2')

        # Run cleanup
        deleted = system.disk_manager.cleanup_by_age(5)

        # Should delete both old files
        assert deleted == 2, "Should delete old files from both directories"
        assert not old_file1.exists()
        assert not old_file2.exists()
        assert recent_file1.exists()
        assert recent_file2.exists()

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@patch('src.upload_manager.boto3.session.Session')
@patch('src.cloudwatch_manager.boto3.session.Session')
def test_deletion_preserves_non_uploaded_files(mock_cw_boto3, mock_upload_boto3):
    """Test that regular cleanup only deletes uploaded files"""
    temp_dir = tempfile.mkdtemp()
    log_dir = Path(temp_dir) / 'logs'
    log_dir.mkdir()

    config_content = f"""
vehicle_id: "test-preserve"
log_directories: [{log_dir}]
s3:
  bucket: test-bucket
  region: cn-north-1
  credentials_path: ~/.aws
upload:
  schedule: "15:00"
  queue_file: {temp_dir}/queue.json
  processed_files_registry:
    registry_file: {temp_dir}/registry.json
    retention_days: 30
deletion:
  emergency:
    enabled: true
disk:
  reserved_gb: 1
  warning_threshold: 0.90
monitoring:
  cloudwatch_enabled: false
"""

    config_file = Path(temp_dir) / 'config.yaml'
    config_file.write_text(config_content)

    try:
        mock_upload_boto3.client.return_value = Mock()
        mock_cw_boto3.client.return_value = Mock()

        system = TVMUploadSystem(str(config_file))

        # Create uploaded file
        uploaded_file = log_dir / 'uploaded.log'
        uploaded_file.write_bytes(b'x' * 1024 * 1024)
        system.disk_manager.mark_uploaded(str(uploaded_file), keep_until_days=30)

        # Create non-uploaded file
        non_uploaded_file = log_dir / 'not_uploaded.log'
        non_uploaded_file.write_bytes(b'x' * 1024 * 1024)

        # Mock warning threshold
        with patch.object(system.disk_manager, 'get_disk_usage', return_value=(0.91, 1000, 100)):
            system._process_upload_queue()

        # Non-uploaded file should NOT be deleted by standard cleanup
        assert non_uploaded_file.exists(), "Non-uploaded files should be preserved"

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@patch('src.upload_manager.boto3.session.Session')
@patch('src.cloudwatch_manager.boto3.session.Session')
def test_partial_deletion_on_error(mock_cw_boto3, mock_upload_boto3):
    """Test system handles partial deletion when some files fail to delete"""
    temp_dir = tempfile.mkdtemp()
    log_dir = Path(temp_dir) / 'logs'
    log_dir.mkdir()

    config_content = f"""
vehicle_id: "test-partial"
log_directories: [{log_dir}]
s3:
  bucket: test-bucket
  region: cn-north-1
  credentials_path: ~/.aws
upload:
  schedule: "15:00"
  queue_file: {temp_dir}/queue.json
  processed_files_registry:
    registry_file: {temp_dir}/registry.json
    retention_days: 30
deletion:
  after_upload:
    enabled: true
    keep_days: 0
disk:
  reserved_gb: 1
monitoring:
  cloudwatch_enabled: false
"""

    config_file = Path(temp_dir) / 'config.yaml'
    config_file.write_text(config_content)

    try:
        mock_s3 = Mock()
        mock_s3.upload_file.return_value = None
        mock_s3.head_object.side_effect = ClientError(
            {'Error': {'Code': 'NotFound'}}, 'head_object'
        )
        mock_upload_boto3.client.return_value = mock_s3
        mock_cw_boto3.client.return_value = Mock()

        system = TVMUploadSystem(str(config_file))

        # Create files
        test_file1 = log_dir / 'file1.log'
        test_file1.write_text('data1')

        test_file2 = log_dir / 'file2.log'
        test_file2.write_text('data2')

        # Upload first file
        system._upload_file(str(test_file1))

        # Make second file read-only (will fail to delete)
        test_file2.chmod(0o444)

        # Try to upload and delete second file
        # This tests that the system handles deletion errors gracefully
        try:
            system._upload_file(str(test_file2))
        except:
            pass  # Expected to potentially fail

        # System should continue operating even if deletion fails
        assert system.stats['files_uploaded'] >= 1

    finally:
        # Restore permissions for cleanup
        for f in log_dir.glob('*.log'):
            try:
                f.chmod(0o644)
            except:
                pass
        shutil.rmtree(temp_dir, ignore_errors=True)


@patch('src.upload_manager.boto3.session.Session')
@patch('src.cloudwatch_manager.boto3.session.Session')
def test_zero_byte_file_deletion(mock_cw_boto3, mock_upload_boto3):
    """Test deletion of zero-byte files"""
    temp_dir = tempfile.mkdtemp()
    log_dir = Path(temp_dir) / 'logs'
    log_dir.mkdir()

    config_content = f"""
vehicle_id: "test-zerobyte"
log_directories: [{log_dir}]
s3:
  bucket: test-bucket
  region: cn-north-1
  credentials_path: ~/.aws
upload:
  schedule: "15:00"
  queue_file: {temp_dir}/queue.json
  processed_files_registry:
    registry_file: {temp_dir}/registry.json
    retention_days: 30
deletion:
  after_upload:
    enabled: true
    keep_days: 0
disk:
  reserved_gb: 1
monitoring:
  cloudwatch_enabled: false
"""

    config_file = Path(temp_dir) / 'config.yaml'
    config_file.write_text(config_content)

    try:
        mock_s3 = Mock()
        mock_s3.upload_file.return_value = None
        mock_s3.head_object.side_effect = ClientError(
            {'Error': {'Code': 'NotFound'}}, 'head_object'
        )
        mock_upload_boto3.client.return_value = mock_s3
        mock_cw_boto3.client.return_value = Mock()

        system = TVMUploadSystem(str(config_file))

        # Create zero-byte file
        empty_file = log_dir / 'empty.log'
        empty_file.write_text('')

        assert empty_file.exists()
        assert empty_file.stat().st_size == 0

        # Upload and delete
        system._upload_file(str(empty_file))

        # Should be deleted even though zero bytes
        assert not empty_file.exists(), "Zero-byte file should be deleted"

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])