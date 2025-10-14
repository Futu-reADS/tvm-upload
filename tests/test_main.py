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
        with patch('src.upload_manager.boto3') as mock_boto3_upload, \
             patch('src.cloudwatch_manager.boto3') as mock_boto3_cw:
            
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
    
    def test_should_upload_now_no_operational_hours(self):
        """Test upload always allowed when operational hours disabled"""
        test_dir = Path('/tmp/test-no-op-hours')
        test_dir.mkdir(exist_ok=True)
        
        config_content = """
vehicle_id: "test-vehicle"
log_directories: [/tmp/test-no-op-hours]
s3:
  bucket: test-bucket
  region: cn-north-1
  credentials_path: ~/.aws
upload:
  schedule: "15:00"
  file_stable_seconds: 60
  queue_file: /tmp/test-queue-no-op.json
disk:
  reserved_gb: 1
  warning_threshold: 0.90
  critical_threshold: 0.95
monitoring:
  cloudwatch_enabled: false
"""
        
        config_file = Path('/tmp/test-config-no-op.yaml')
        config_file.write_text(config_content)
        
        with patch('src.upload_manager.boto3'), \
             patch('src.cloudwatch_manager.boto3'):
            
            try:
                system = TVMUploadSystem(str(config_file))
                result = system._should_upload_now()
                assert result is True
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


class TestSignalHandlers:
    """Test signal handling"""
    
    def test_signal_handler_exists(self):
        """Test that signal handler function exists"""
        from src.main import signal_handler
        assert signal_handler is not None
        assert callable(signal_handler)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])