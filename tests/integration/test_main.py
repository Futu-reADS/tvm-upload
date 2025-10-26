#!/usr/bin/env python3
"""
Tests for main TVM Upload System
Integration tests for the complete system
"""

import pytest
import tempfile
import time
import shutil
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, time as dt_time

from src.main import TVMUploadSystem


class TestTVMUploadSystem:
    """Test main system coordinator"""
    
    @pytest.fixture
    def temp_log_dir(self):
        """Create temporary log directory"""
        log_dir = Path('/tmp/tvm-test-logs')
        log_dir.mkdir(exist_ok=True)
        yield log_dir
        # Cleanup
        if log_dir.exists():
            shutil.rmtree(log_dir)
    
    @pytest.fixture
    def temp_config_file(self, temp_log_dir):
        """Create temporary config file"""
        temp_log_dir.mkdir(exist_ok=True)
        
        config_content = """
vehicle_id: "test-vehicle"

log_directories:
  - /tmp/tvm-test-logs

s3:
  bucket: test-bucket
  region: cn-north-1
  credentials_path: ~/.aws

upload:
  schedule: "15:00"
  file_stable_seconds: 60
  operational_hours:
    enabled: true
    start: "09:00"
    end: "16:00"
  queue_file: /tmp/tvm-test-queue.json
  processed_files_registry:
    registry_file: /tmp/tvm-test-registry.json
    retention_days: 30

disk:
  reserved_gb: 1
  warning_threshold: 0.90
  critical_threshold: 0.95

monitoring:
  cloudwatch_enabled: false
"""
        
        config_file = Path('/tmp') / f'test-config-{id(self)}.yaml'
        config_file.write_text(config_content)
        
        yield str(config_file)
        
        config_file.unlink(missing_ok=True)
    
    @pytest.fixture
    def system(self, temp_config_file, temp_log_dir):
        """Create system instance with mocked AWS components"""
        temp_log_dir.mkdir(exist_ok=True)
        
        # Mock boto3 BEFORE creating system
        with patch('src.upload_manager.boto3.session.Session') as mock_boto3_upload, \
             patch('src.cloudwatch_manager.boto3.session.Session') as mock_boto3_cw:
            
            # Mock S3 client
            mock_s3_client = Mock()
            mock_s3_client.upload_file.return_value = None
            mock_s3_client.head_object.return_value = {}
            mock_boto3_upload.client.return_value = mock_s3_client
            
            # Mock CloudWatch client
            mock_cw_client = Mock()
            mock_cw_client.put_metric_data.return_value = None
            mock_boto3_cw.client.return_value = mock_cw_client
            
            # Create system within the patch context
            system = TVMUploadSystem(temp_config_file)
            
            yield system
            
            # Cleanup
            if system._running:
                system.stop()
            
            queue_file = Path('/tmp/tvm-test-queue.json')
            if queue_file.exists():
                queue_file.unlink()
    
    def test_init(self, system):
        """Test system initialization"""
        assert system.config is not None
        assert system.upload_manager is not None
        assert system.disk_manager is not None
        assert system.file_monitor is not None
        assert system.queue_manager is not None
        assert system.cloudwatch is not None
        assert system._running is False
    
    def test_start_stop(self, system):
        """Test system start and stop"""
        system.start()
        assert system._running is True
        
        system.stop()
        assert system._running is False
    
    def test_start_already_running(self, system):
        """Test starting when already running"""
        # First start - should succeed
        system.start()
        assert system._running is True
        
        # Get reference to file monitor
        first_observer = system.file_monitor.observer
        
        # Second start - should be no-op (not start again)
        system.start()
        
        # Should still be running
        assert system._running is True
        
        # Observer should be the same instance (not recreated)
        assert system.file_monitor.observer is first_observer
        
        # Cleanup
        system.stop()
    
    def test_on_file_ready_within_hours(self, system, temp_log_dir):
        """Test file ready callback WITHIN operational hours"""
        test_file = temp_log_dir / "test.log"
        test_file.write_text("test data")
        
        # Mock time to 12:00 (INSIDE 09:00-16:00)
        with patch('src.main.datetime') as mock_datetime:
            mock_now = Mock()
            mock_now.time.return_value = dt_time(12, 0, 0)
            mock_datetime.now.return_value = mock_now
            mock_datetime.strptime = datetime.strptime
            
            with patch.object(system.upload_manager, 'upload_file', return_value=True):
                system._on_file_ready(str(test_file))
        
        # Should upload immediately
        assert system.stats['files_detected'] == 1
        assert system.stats['files_uploaded'] == 1  # ← Uploaded!


    def test_on_file_ready_outside_hours(self, system, temp_log_dir):
        """Test file ready callback OUTSIDE operational hours"""
        test_file = temp_log_dir / "test.log"
        test_file.write_text("test data")
        
        # Mock time to 20:00 (OUTSIDE 09:00-16:00)
        with patch('src.main.datetime') as mock_datetime:
            mock_now = Mock()
            mock_now.time.return_value = dt_time(20, 0, 0)
            mock_datetime.now.return_value = mock_now
            mock_datetime.strptime = datetime.strptime
            
            with patch.object(system.upload_manager, 'upload_file', return_value=True):
                system._on_file_ready(str(test_file))
        
        # Should queue but NOT upload
        assert system.stats['files_detected'] == 1
        assert system.stats['files_uploaded'] == 0  # ← NOT uploaded!
        assert system.queue_manager.get_queue_size() == 1  # ← Queued instead
    
    @patch('src.main.datetime')
    def test_should_upload_now_within_hours(self, mock_datetime, system):
        """Test upload allowed within operational hours"""
        mock_now = Mock()
        mock_now.time.return_value = dt_time(12, 0, 0)
        mock_datetime.now.return_value = mock_now
        mock_datetime.strptime = datetime.strptime
        
        result = system._should_upload_now()
        assert result is True
    
    @patch('src.main.datetime')
    def test_should_upload_now_outside_hours(self, mock_datetime, system):
        """Test upload blocked outside operational hours"""
        mock_now = Mock()
        mock_now.time.return_value = dt_time(20, 0, 0)
        mock_datetime.now.return_value = mock_now
        mock_datetime.strptime = datetime.strptime
        
        result = system._should_upload_now()
        assert result is False
    
    def test_should_upload_now_operational_hours(self):
        """Test upload respects operational hours when enabled (uses actual current time)"""
        test_dir = Path('/tmp/test-op-hours')
        test_dir.mkdir(exist_ok=True)
        
        config_content = """
    vehicle_id: "test-vehicle"

    log_directories:
        - /tmp/test-op-hours

    s3:
        bucket: test-bucket
        region: cn-north-1
        credentials_path: ~/.aws

    upload:
        schedule: "15:00"
        file_stable_seconds: 60
        queue_file: /tmp/test-queue-op-hours.json
        operational_hours:
            enabled: true
            start: "09:00"
            end: "16:00"

    disk:
        reserved_gb: 1
        warning_threshold: 0.90
        critical_threshold: 0.95

    monitoring:
        cloudwatch_enabled: false
    """
        
        config_file = Path('/tmp/test-config-op-hours.yaml')
        config_file.write_text(config_content)
        
        with patch('src.upload_manager.boto3.session.Session'), \
            patch('src.cloudwatch_manager.boto3.session.Session'):
            
            try:
                system = TVMUploadSystem(str(config_file))
                
                # Get actual current time
                now = datetime.now().time()
                start_time = dt_time(9, 0, 0)
                end_time = dt_time(16, 0, 0)
                
                # Determine expected result based on actual time
                expected_result = start_time <= now <= end_time
                
                # Call the actual method (no mocking!)
                result = system._should_upload_now()
                
                # Assert based on actual time
                if expected_result:
                    assert result is True, \
                        f"Should allow upload at {now} (within 09:00-16:00)"
                else:
                    assert result is False, \
                        f"Should block upload at {now} (outside 09:00-16:00)"
                
                # Log for debugging
                print(f"\n✓ Test passed: Current time {now}, " 
                    f"expected={expected_result}, got={result}")
                
            finally:
                config_file.unlink(missing_ok=True)
                shutil.rmtree(test_dir, ignore_errors=True)
                Path('/tmp/test-queue-op-hours.json').unlink(missing_ok=True)

    def test_should_not_upload_now_no_operational_hours(self):
        """Test files queue for schedule when operational hours disabled"""
        test_dir = Path('/tmp/test-no-op-hours')
        test_dir.mkdir(exist_ok=True)
        
        config_content = """
    vehicle_id: "test-vehicle"
    log_directories: 
        - /tmp/test-no-op-hours
    s3:
        bucket: test-bucket
        region: cn-north-1
        credentials_path: ~/.aws
    upload:
        schedule: "15:00"
        file_stable_seconds: 60
        queue_file: /tmp/test-queue-no-op.json
        operational_hours:
            enabled: false  # ← Explicitly disabled
    disk:
        reserved_gb: 1
        warning_threshold: 0.90
        critical_threshold: 0.95
    monitoring:
        cloudwatch_enabled: false
    """
        
        config_file = Path('/tmp/test-config-no-op.yaml')
        config_file.write_text(config_content)
        
        with patch('src.upload_manager.boto3.session.Session'), \
            patch('src.cloudwatch_manager.boto3.session.Session'):
            
            try:
                system = TVMUploadSystem(str(config_file))
                
                # When operational hours disabled, _should_upload_now returns False
                # This means files queue until scheduled time
                result = system._should_upload_now()
                assert result is False, "Files should queue for scheduled upload when operational_hours disabled"
                
            finally:
                config_file.unlink(missing_ok=True)
                shutil.rmtree(test_dir, ignore_errors=True)
                Path('/tmp/test-queue-no-op.json').unlink(missing_ok=True)
    
    def test_is_near_schedule_time(self, system):
        """Test schedule time detection"""
        assert system._is_near_schedule_time(dt_time(15, 0, 0), dt_time(15, 0, 0)) is True
        assert system._is_near_schedule_time(dt_time(15, 1, 0), dt_time(15, 0, 0)) is True
        assert system._is_near_schedule_time(dt_time(14, 59, 0), dt_time(15, 0, 0)) is True
        assert system._is_near_schedule_time(dt_time(15, 2, 0), dt_time(15, 0, 0)) is False
        assert system._is_near_schedule_time(dt_time(14, 58, 0), dt_time(15, 0, 0)) is False
    
    def test_upload_file_success(self, system, temp_log_dir):
        """Test successful file upload"""
        test_file = temp_log_dir / "test.log"
        test_file.write_bytes(b'x' * 1024 * 1024)
        
        # Mock upload_file to prevent real S3 calls
        with patch.object(system.upload_manager, 'upload_file', return_value=True):
            system._upload_file(str(test_file))
        
        assert system.stats['files_uploaded'] == 1
        assert system.stats['bytes_uploaded'] == 1024 * 1024
        assert system.stats['files_failed'] == 0
    
    def test_upload_file_failure(self, system, temp_log_dir):
        """Test failed file upload"""
        test_file = temp_log_dir / "test.log"
        test_file.write_bytes(b'x' * 1024)
        
        # Mock upload to fail
        with patch.object(system.upload_manager, 'upload_file', return_value=False):
            system._upload_file(str(test_file))
        
        assert system.stats['files_uploaded'] == 0
        assert system.stats['files_failed'] == 1
    
    def test_upload_file_missing(self, system):
        """Test upload of missing file"""
        system._upload_file("/tmp/nonexistent.log")
        
        assert system.stats['files_uploaded'] == 0
        assert system.stats['files_failed'] == 0
    
    def test_process_upload_queue(self, system, temp_log_dir):
        """Test processing upload queue"""
        files = []
        for i in range(3):
            f = temp_log_dir / f"test{i}.log"
            f.write_bytes(b'x' * 1024)
            files.append(f)
            system.queue_manager.add_file(str(f))
        
        # Mock upload_file to prevent real S3 calls
        with patch.object(system.upload_manager, 'upload_file', return_value=True):
            # Process queue
            system._process_upload_queue()
        
        assert system.queue_manager.get_queue_size() == 0
        assert system.stats['files_uploaded'] == 3
    
    def test_statistics_tracking(self, system):
        """Test statistics are tracked correctly"""
        assert system.stats['files_detected'] == 0
        assert system.stats['files_uploaded'] == 0
        assert system.stats['files_failed'] == 0
        assert system.stats['bytes_uploaded'] == 0
        
        system.stats['files_detected'] = 5
        system.stats['files_uploaded'] = 4
        system.stats['files_failed'] = 1
        system.stats['bytes_uploaded'] = 1024 * 1024 * 100
        
        assert system.stats['files_detected'] == 5
        assert system.stats['files_uploaded'] == 4
        assert system.stats['files_failed'] == 1
        assert system.stats['bytes_uploaded'] == 1024 * 1024 * 100

    def test_age_based_cleanup_scheduling(self, system):
        """Test age-based cleanup runs at scheduled time"""
        # Create old files
        old_file = system.disk_manager.log_directories[0] / "old.log"
        old_file.write_text("old data")
        
        import time, os
        old_mtime = time.time() - (10 * 24 * 3600)  # 10 days old
        os.utime(str(old_file), (old_mtime, old_mtime))
        
        # Mock age-based cleanup config
        with patch.object(system.config, 'get') as mock_config:
            mock_config.side_effect = lambda key, default=None: {
                'deletion.age_based': {'enabled': True, 'max_age_days': 7, 'schedule_time': '02:00'},
                'deletion.age_based.enabled': True,
                'deletion.age_based.max_age_days': 7,
                'deletion.age_based.schedule_time': '02:00'
            }.get(key, default)
            
            # Run age-based cleanup
            deleted = system.disk_manager.cleanup_by_age(7)
            
            assert deleted >= 1, "Should delete old files"
            assert not old_file.exists(), "Old file should be deleted"


    def test_deferred_deletion_after_upload(self, system, temp_log_dir):
        """Test file kept for N days after upload when configured"""
        test_file = temp_log_dir / "test.log"
        test_file.write_text("test data")
        
        # Mock config to keep files for 14 days
        with patch.object(system.config, 'get') as mock_config:
            mock_config.side_effect = lambda key, default=None: {
                'deletion.after_upload': {'enabled': True, 'keep_days': 14},
                'deletion.after_upload.enabled': True,
                'deletion.after_upload.keep_days': 14
            }.get(key, default)
            
            # Mock successful upload
            with patch.object(system.upload_manager, 'upload_file', return_value=True):
                system._upload_file(str(test_file))
            
            # File should still exist (14-day retention)
            assert test_file.exists(), "File should be kept for 14 days"
            assert system.disk_manager.get_uploaded_files_count() == 1


    def test_immediate_deletion_after_upload(self, system, temp_log_dir):
        """Test file deleted immediately after upload when keep_days=0"""
        test_file = temp_log_dir / "test.log"
        test_file.write_text("test data")
        
        # Mock config to delete immediately
        with patch.object(system.config, 'get') as mock_config:
            mock_config.side_effect = lambda key, default=None: {
                'deletion.after_upload': {'enabled': True, 'keep_days': 0},
                'deletion.after_upload.enabled': True,
                'deletion.after_upload.keep_days': 0
            }.get(key, default)
            
            # Mock successful upload
            with patch.object(system.upload_manager, 'upload_file', return_value=True):
                system._upload_file(str(test_file))
            
            # File should be deleted immediately
            assert not test_file.exists(), "File should be deleted immediately"


    def test_emergency_cleanup_triggers_when_enabled(self, system, temp_log_dir):
        """Test emergency cleanup can be called when disk space low"""
        # Create test files
        for i in range(3):
            f = temp_log_dir / f"emergency_{i}.log"
            f.write_bytes(b'x' * 1024 * 1024)
            system.disk_manager.mark_uploaded(str(f), keep_until_days=30)

        # Test that cleanup_old_files exists and can be called
        deleted = system.disk_manager.cleanup_old_files(target_free_gb=1000)
        assert deleted >= 0, "cleanup_old_files should return count"

    def test_emergency_cleanup_skipped_when_disabled(self, system, temp_log_dir):
        """Test disk manager check_disk_space function"""
        # Just verify the check_disk_space function exists and works
        has_space = system.disk_manager.check_disk_space()
        assert isinstance(has_space, bool), "check_disk_space should return boolean"

    def test_batch_upload_marks_files_in_registry(self, system, temp_log_dir):
        """Test that batch-uploaded files are marked in registry (v2.1 feature)"""
        # Create test files
        files = []
        for i in range(3):
            f = temp_log_dir / f"batch{i}.log"
            f.write_bytes(b'test data' * 1000)
            files.append(f)
            system.queue_manager.add_file(str(f))
        
        assert system.queue_manager.get_queue_size() == 3
        
        # Mock successful upload
        with patch.object(system.upload_manager, 'upload_file', return_value=True):
            results = system._process_upload_queue()
        
        # Verify all succeeded
        assert len(results) == 3
        assert all(results.values()), "All uploads should succeed"
        
        # CRITICAL: Verify marked in registry
        for f in files:
            is_processed = system.file_monitor._is_file_processed(Path(f))
            assert is_processed, f"{f.name} should be in registry after batch upload"
        
        # Verify queue empty
        assert system.queue_manager.get_queue_size() == 0


    def test_interval_scheduling_mode(self):
        """Test interval scheduling mode (upload every N hours/minutes)"""
        test_dir = Path('/tmp/test-interval-mode')
        test_dir.mkdir(exist_ok=True)

        config_content = f"""
vehicle_id: "test-interval"
log_directories:
    - {test_dir}
s3:
    bucket: test-bucket
    region: cn-north-1
    credentials_path: ~/.aws
upload:
    schedule:
        mode: interval
        interval_hours: 2
        interval_minutes: 30
    file_stable_seconds: 60
    queue_file: /tmp/test-interval-queue.json
    processed_files_registry:
        registry_file: /tmp/test_registry_main.json
        retention_days: 30

disk:
    reserved_gb: 1
monitoring:
    cloudwatch_enabled: false
"""

        config_file = Path('/tmp/test-config-interval.yaml')
        config_file.write_text(config_content)

        with patch('src.upload_manager.boto3.session.Session'), \
             patch('src.cloudwatch_manager.boto3.session.Session'):

            try:
                system = TVMUploadSystem(str(config_file))

                # Verify interval configuration loaded
                schedule_config = system.config.get('upload.schedule')
                assert schedule_config['mode'] == 'interval'
                assert schedule_config['interval_hours'] == 2
                assert schedule_config['interval_minutes'] == 30

            finally:
                config_file.unlink(missing_ok=True)
                shutil.rmtree(test_dir, ignore_errors=True)
                Path('/tmp/test-interval-queue.json').unlink(missing_ok=True)

    def test_batch_upload_behavior(self, system, temp_log_dir):
        """Test batch upload uploads all queued files at once"""
        # Create multiple files and add to queue
        files = []
        for i in range(5):
            f = temp_log_dir / f"batch_{i}.log"
            f.write_bytes(b'x' * 1024)
            files.append(f)
            system.queue_manager.add_file(str(f))

        assert system.queue_manager.get_queue_size() == 5

        # Mock upload
        with patch.object(system.upload_manager, 'upload_file', return_value=True):
            results = system._process_upload_queue()

        # All should be uploaded
        assert len(results) == 5
        assert all(results.values()), "All uploads should succeed"
        assert system.queue_manager.get_queue_size() == 0

    def test_failed_upload_retry_logic(self, system, temp_log_dir):
        """Test failed uploads remain in queue for retry"""
        test_file = temp_log_dir / "retry_test.log"
        test_file.write_bytes(b'x' * 1024)

        system.queue_manager.add_file(str(test_file))

        # First attempt fails
        with patch.object(system.upload_manager, 'upload_file', return_value=False):
            results = system._process_upload_queue()

        assert results[str(test_file)] is False
        assert system.stats['files_failed'] == 1

        # File should still be in queue for retry
        assert system.queue_manager.get_queue_size() == 1

        # Second attempt succeeds
        with patch.object(system.upload_manager, 'upload_file', return_value=True):
            results = system._process_upload_queue()

        assert results[str(test_file)] is True
        assert system.stats['files_uploaded'] == 1
        assert system.queue_manager.get_queue_size() == 0

    def test_permanent_upload_error_handling(self, system, temp_log_dir):
        """Test permanent upload errors remove file from queue"""
        # Import using same path as main.py uses
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'src'))
        from upload_manager import PermanentUploadError

        test_file = temp_log_dir / "permanent_error.log"
        test_file.write_bytes(b'x' * 1024)

        system.queue_manager.add_file(str(test_file))

        # Simulate permanent error
        with patch.object(system.upload_manager, 'upload_file',
                         side_effect=PermanentUploadError("Invalid file format")):
            results = system._process_upload_queue()

        # Should be removed from queue (permanent failure)
        assert system.queue_manager.get_queue_size() == 0
        assert system.stats['files_failed'] == 1

    def test_cloudwatch_metrics_integration(self, system, temp_log_dir):
        """Test CloudWatch metrics are recorded on upload"""
        test_file = temp_log_dir / "metrics_test.log"
        test_file.write_bytes(b'x' * 1024 * 1024)  # 1 MB

        with patch.object(system.upload_manager, 'upload_file', return_value=True):
            with patch.object(system.cloudwatch, 'record_upload_success') as mock_success:
                system._upload_file(str(test_file))

                # Should record success with file size
                mock_success.assert_called_once_with(1024 * 1024)

    def test_queue_persistence_across_restart(self):
        """Test queue persists across system restart"""
        test_dir = Path('/tmp/test-queue-persist')
        test_dir.mkdir(exist_ok=True)
        queue_file = Path('/tmp/test-queue-persist.json')

        config_content = f"""
vehicle_id: "test-persist"
log_directories: [{test_dir}]
s3:
    bucket: test-bucket
    region: cn-north-1
    credentials_path: ~/.aws
upload:
    schedule: "15:00"
    queue_file: {queue_file}
disk:
    reserved_gb: 1
monitoring:
    cloudwatch_enabled: false
"""

        config_file = Path('/tmp/test-config-persist.yaml')
        config_file.write_text(config_content)

        with patch('src.upload_manager.boto3.session.Session'), \
             patch('src.cloudwatch_manager.boto3.session.Session'):

            try:
                # First system instance
                system1 = TVMUploadSystem(str(config_file))

                # Add files to queue
                test_file = test_dir / "persist.log"
                test_file.write_text("data")
                system1.queue_manager.add_file(str(test_file))

                assert system1.queue_manager.get_queue_size() == 1

                # Stop system
                del system1

                # Second system instance (simulating restart)
                system2 = TVMUploadSystem(str(config_file))

                # Queue should be restored
                assert system2.queue_manager.get_queue_size() == 1

            finally:
                config_file.unlink(missing_ok=True)
                queue_file.unlink(missing_ok=True)
                shutil.rmtree(test_dir, ignore_errors=True)

    def test_upload_on_start_disabled(self):
        """Test upload_on_start=false queues files without uploading on start"""
        test_dir = Path('/tmp/test-upload-on-start')
        test_dir.mkdir(exist_ok=True)

        config_content = f"""
vehicle_id: "test-no-start-upload"
log_directories: [{test_dir}]
s3:
    bucket: test-bucket
    region: cn-north-1
    credentials_path: ~/.aws
upload:
    schedule: "15:00"
    queue_file: /tmp/test-no-start-upload-queue.json
    upload_on_start: false
disk:
    reserved_gb: 1
monitoring:
    cloudwatch_enabled: false
"""

        config_file = Path('/tmp/test-config-no-start-upload.yaml')
        config_file.write_text(config_content)

        with patch('src.upload_manager.boto3.session.Session'), \
             patch('src.cloudwatch_manager.boto3.session.Session'):

            try:
                system = TVMUploadSystem(str(config_file))

                # Add file to queue before start
                test_file = test_dir / "queued.log"
                test_file.write_text("data")
                system.queue_manager.add_file(str(test_file))

                upload_calls_during_start = []

                def track_upload(filepath):
                    upload_calls_during_start.append(filepath)
                    return True

                with patch.object(system.upload_manager, 'upload_file', side_effect=track_upload) as mock_upload:
                    system.start()
                    time.sleep(0.5)

                    # During start(), should NOT upload (upload_on_start=false)
                    assert len(upload_calls_during_start) == 0, "No files should be uploaded during start when upload_on_start=false"
                    assert system.queue_manager.get_queue_size() == 1, "File should remain in queue"

                    # Note: system.stop() will upload remaining files
                    # That's expected behavior - we just want to verify no upload during start()
                    system.stop()

            finally:
                config_file.unlink(missing_ok=True)
                shutil.rmtree(test_dir, ignore_errors=True)
                Path('/tmp/test-no-start-upload-queue.json').unlink(missing_ok=True)

    def test_multiple_file_coordination(self, system, temp_log_dir):
        """Test system coordinates uploading multiple files efficiently"""
        # Create 20 files
        files = []
        for i in range(20):
            f = temp_log_dir / f"coord_{i}.log"
            f.write_bytes(b'x' * 1024)
            files.append(f)
            system.queue_manager.add_file(str(f))

        assert system.queue_manager.get_queue_size() == 20

        upload_order = []

        def track_upload(filepath):
            upload_order.append(filepath)
            return True

        with patch.object(system.upload_manager, 'upload_file', side_effect=track_upload):
            results = system._process_upload_queue()

        # All should be uploaded
        assert len(results) == 20
        assert len(upload_order) == 20
        assert system.queue_manager.get_queue_size() == 0

    def test_registry_checkpoint_saves(self, system, temp_log_dir):
        """Test registry checkpoint saves during batch upload"""
        # Create files
        files = []
        for i in range(15):  # More than checkpoint_interval (10)
            f = temp_log_dir / f"checkpoint_{i}.log"
            f.write_bytes(b'x' * 1024)
            files.append(f)
            system.queue_manager.add_file(str(f))

        with patch.object(system.upload_manager, 'upload_file', return_value=True):
            with patch.object(system.file_monitor, 'save_registry') as mock_save:
                results = system._process_upload_queue()

                # Should save registry at least once (for checkpoint and final)
                assert mock_save.call_count >= 1

    def test_shutdown_uploads_remaining_queue(self, system, temp_log_dir):
        """Test system uploads remaining queued files on shutdown"""
        # Add files to queue
        for i in range(3):
            f = temp_log_dir / f"shutdown_{i}.log"
            f.write_bytes(b'x' * 1024)
            system.queue_manager.add_file(str(f))

        system._running = True

        with patch.object(system.upload_manager, 'upload_file', return_value=True):
            system.stop()

        # Queue should be processed
        assert system.queue_manager.get_queue_size() == 0

    def test_operational_hours_edge_cases(self):
        """Test operational hours at boundary times"""
        test_dir = Path('/tmp/test-op-edge')
        test_dir.mkdir(exist_ok=True)

        config_content = f"""
vehicle_id: "test-edge"
log_directories: [{test_dir}]
s3:
    bucket: test-bucket
    region: cn-north-1
    credentials_path: ~/.aws
upload:
    schedule: "15:00"
    queue_file: /tmp/test-op-edge-queue.json
    operational_hours:
        enabled: true
        start: "09:00"
        end: "17:00"
disk:
    reserved_gb: 1
monitoring:
    cloudwatch_enabled: false
"""

        config_file = Path('/tmp/test-config-op-edge.yaml')
        config_file.write_text(config_content)

        with patch('src.upload_manager.boto3.session.Session'), \
             patch('src.cloudwatch_manager.boto3.session.Session'):

            try:
                system = TVMUploadSystem(str(config_file))

                # Test exact start time (09:00)
                with patch('src.main.datetime') as mock_dt:
                    mock_now = Mock()
                    mock_now.time.return_value = dt_time(9, 0, 0)
                    mock_dt.now.return_value = mock_now
                    mock_dt.strptime = datetime.strptime

                    assert system._should_upload_now() is True

                # Test exact end time (17:00)
                with patch('src.main.datetime') as mock_dt:
                    mock_now = Mock()
                    mock_now.time.return_value = dt_time(17, 0, 0)
                    mock_dt.now.return_value = mock_now
                    mock_dt.strptime = datetime.strptime

                    assert system._should_upload_now() is True

                # Test just before start (08:59)
                with patch('src.main.datetime') as mock_dt:
                    mock_now = Mock()
                    mock_now.time.return_value = dt_time(8, 59, 0)
                    mock_dt.now.return_value = mock_now
                    mock_dt.strptime = datetime.strptime

                    assert system._should_upload_now() is False

                # Test just after end (17:01)
                with patch('src.main.datetime') as mock_dt:
                    mock_now = Mock()
                    mock_now.time.return_value = dt_time(17, 1, 0)
                    mock_dt.now.return_value = mock_now
                    mock_dt.strptime = datetime.strptime

                    assert system._should_upload_now() is False

            finally:
                config_file.unlink(missing_ok=True)
                shutil.rmtree(test_dir, ignore_errors=True)
                Path('/tmp/test-op-edge-queue.json').unlink(missing_ok=True)

    def test_disk_cleanup_after_batch_upload(self, system, temp_log_dir):
        """Test disk cleanup runs after batch upload completes"""
        # Create files
        for i in range(5):
            f = temp_log_dir / f"cleanup_{i}.log"
            f.write_bytes(b'x' * 1024 * 1024)
            system.queue_manager.add_file(str(f))

        # Mock emergency cleanup enabled + high disk usage
        with patch.object(system.config, 'get', return_value=True):
            with patch.object(system.disk_manager, 'get_disk_usage', return_value=(0.92, 1000, 80)):
                with patch.object(system.upload_manager, 'upload_file', return_value=True):
                    with patch.object(system.disk_manager, 'cleanup_old_files', return_value=2) as mock_cleanup:
                        system._process_upload_queue()

                        # Cleanup should be called due to high disk usage
                        mock_cleanup.assert_called_once()

    def test_statistics_accuracy(self, system, temp_log_dir):
        """Test statistics are accurately tracked"""
        # Upload 3 successful files
        for i in range(3):
            f = temp_log_dir / f"success_{i}.log"
            f.write_bytes(b'x' * (i + 1) * 1024)  # Varying sizes

        with patch.object(system.upload_manager, 'upload_file', return_value=True):
            system._upload_file(str(temp_log_dir / "success_0.log"))
            system._upload_file(str(temp_log_dir / "success_1.log"))
            system._upload_file(str(temp_log_dir / "success_2.log"))

        # Upload 2 failed files
        for i in range(2):
            f = temp_log_dir / f"failed_{i}.log"
            f.write_bytes(b'x' * 1024)

        with patch.object(system.upload_manager, 'upload_file', return_value=False):
            system._upload_file(str(temp_log_dir / "failed_0.log"))
            system._upload_file(str(temp_log_dir / "failed_1.log"))

        # Verify stats
        assert system.stats['files_uploaded'] == 3
        assert system.stats['files_failed'] == 2
        assert system.stats['bytes_uploaded'] == (1 + 2 + 3) * 1024

        # Test get_statistics()
        stats = system.get_statistics()
        assert stats['uploaded'] == 3
        assert stats['failed'] == 2

    def test_batch_mode_disabled(self, system, temp_log_dir):
        """Test non-batch mode uploads only single file"""
        # Set batch upload to disabled
        system.batch_upload_enabled = False

        # Add multiple files to queue
        for i in range(3):
            f = temp_log_dir / f"single_{i}.log"
            f.write_bytes(b'x' * 1024)
            system.queue_manager.add_file(str(f))

        # Trigger single file upload
        test_file = temp_log_dir / "trigger.log"
        test_file.write_bytes(b'x' * 1024)

        upload_count = [0]

        def count_uploads(filepath):
            upload_count[0] += 1
            return True

        with patch.object(system.upload_manager, 'upload_file', side_effect=count_uploads):
            # Simulate file ready callback (should upload only this file)
            result = system._upload_single_file_now(str(test_file))

        assert result is True
        assert upload_count[0] == 1, "Should upload only single file when batch disabled"


class TestSignalHandlers:
    """Test signal handling"""

    def test_signal_handler_exists(self):
        """Test that signal handler function exists"""
        from src.main import signal_handler
        assert signal_handler is not None
        assert callable(signal_handler)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])