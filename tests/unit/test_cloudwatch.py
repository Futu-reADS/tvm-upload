#!/usr/bin/env python3
"""Tests for CloudWatch manager"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from src.cloudwatch_manager import CloudWatchManager


class TestCloudWatchManager:
    """Test CloudWatch metric recording and publishing"""
    
    def test_init_disabled(self):
        """Test CloudWatch manager with disabled mode"""
        cw = CloudWatchManager('cn-north-1', 'test-vehicle', enabled=False)
        assert cw.enabled is False
        assert cw.vehicle_id == 'test-vehicle'
    
    def test_record_upload_success(self):
        """Test recording successful upload"""
        cw = CloudWatchManager('cn-north-1', 'test-vehicle', enabled=False)
        
        cw.record_upload_success(1024 * 1024)  # 1 MB
        assert cw.bytes_uploaded == 1024 * 1024
        assert cw.files_uploaded == 1
        
        cw.record_upload_success(2 * 1024 * 1024)  # 2 MB
        assert cw.bytes_uploaded == 3 * 1024 * 1024
        assert cw.files_uploaded == 2
    
    def test_record_upload_failure(self):
        """Test recording upload failure"""
        cw = CloudWatchManager('cn-north-1', 'test-vehicle', enabled=False)
        
        cw.record_upload_failure()
        assert cw.files_failed == 1
        
        cw.record_upload_failure()
        assert cw.files_failed == 2
    
    @patch('boto3.client')
    def test_publish_metrics(self, mock_boto_client):
        """Test publishing metrics to CloudWatch"""
        mock_cw = Mock()
        mock_boto_client.return_value = mock_cw
        
        cw = CloudWatchManager('cn-north-1', 'test-vehicle', enabled=True)
        cw.record_upload_success(1024 * 1024 * 50)  # 50 MB
        cw.record_upload_success(1024 * 1024 * 100)  # 100 MB
        cw.record_upload_failure()
        
        cw.publish_metrics(disk_usage_percent=75.5)
        
        # Verify put_metric_data was called
        mock_cw.put_metric_data.assert_called_once()
        call_args = mock_cw.put_metric_data.call_args
        
        assert call_args[1]['Namespace'] == 'TVM/Upload'
        metrics = call_args[1]['MetricData']
        assert len(metrics) == 4  # Bytes, Count, Failures, Disk
        
        # Check metrics reset after publish
        assert cw.bytes_uploaded == 0
        assert cw.files_uploaded == 0
        assert cw.files_failed == 0
    
    def test_publish_metrics_disabled(self):
        """Test publish does nothing when disabled"""
        cw = CloudWatchManager('cn-north-1', 'test-vehicle', enabled=False)
        cw.record_upload_success(1024)
        
        # Should not raise error
        cw.publish_metrics()
        
        # Metrics should not reset
        assert cw.bytes_uploaded == 1024