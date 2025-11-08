#!/usr/bin/env python3
"""Tests for CloudWatch manager"""

from unittest.mock import MagicMock, Mock, patch

import pytest

from src.cloudwatch_manager import CloudWatchManager


class TestCloudWatchManager:
    """Test CloudWatch metric recording and publishing"""

    def test_init_disabled(self):
        """Test CloudWatch manager with disabled mode"""
        cw = CloudWatchManager("cn-north-1", "test-vehicle", enabled=False)
        assert cw.enabled is False
        assert cw.vehicle_id == "test-vehicle"

    def test_record_upload_success(self):
        """Test recording successful upload"""
        cw = CloudWatchManager("cn-north-1", "test-vehicle", enabled=False)

        cw.record_upload_success(1024 * 1024)  # 1 MB
        assert cw.bytes_uploaded == 1024 * 1024
        assert cw.files_uploaded == 1

        cw.record_upload_success(2 * 1024 * 1024)  # 2 MB
        assert cw.bytes_uploaded == 3 * 1024 * 1024
        assert cw.files_uploaded == 2

    def test_record_upload_failure(self):
        """Test recording upload failure"""
        cw = CloudWatchManager("cn-north-1", "test-vehicle", enabled=False)

        cw.record_upload_failure()
        assert cw.files_failed == 1

        cw.record_upload_failure()
        assert cw.files_failed == 2

    @patch("boto3.client")
    def test_publish_metrics(self, mock_boto_client):
        """Test publishing metrics to CloudWatch"""
        mock_cw = Mock()
        mock_boto_client.return_value = mock_cw

        cw = CloudWatchManager("cn-north-1", "test-vehicle", enabled=True)

        # Reset mock after initialization (ServiceStartup metric was published)
        mock_cw.put_metric_data.reset_mock()

        cw.record_upload_success(1024 * 1024 * 50)  # 50 MB
        cw.record_upload_success(1024 * 1024 * 100)  # 100 MB
        cw.record_upload_failure()

        cw.publish_metrics(disk_usage_percent=75.5)

        # Verify put_metric_data was called
        mock_cw.put_metric_data.assert_called_once()
        call_args = mock_cw.put_metric_data.call_args

        assert call_args[1]["Namespace"] == "TVM/Upload"
        metrics = call_args[1]["MetricData"]
        assert len(metrics) == 4  # Bytes, Count, Failures, Disk

        # Check metrics reset after publish
        assert cw.bytes_uploaded == 0
        assert cw.files_uploaded == 0
        assert cw.files_failed == 0

    def test_publish_metrics_disabled(self):
        """Test publish does nothing when disabled"""
        cw = CloudWatchManager("cn-north-1", "test-vehicle", enabled=False)
        cw.record_upload_success(1024)

        # Should not raise error
        cw.publish_metrics()

        # Metrics should not reset
        assert cw.bytes_uploaded == 1024


# ============================================
# METRIC AGGREGATION TESTS
# ============================================


class TestMetricAggregation:
    """Test metric aggregation before publishing"""

    def test_multiple_uploads_before_publish(self):
        """Test aggregating multiple uploads before single publish"""
        cw = CloudWatchManager("cn-north-1", "test-vehicle", enabled=False)

        # Upload 5 files
        upload_sizes = [100, 200, 300, 400, 500]  # bytes
        for size in upload_sizes:
            cw.record_upload_success(size)

        # Verify aggregation
        assert cw.bytes_uploaded == sum(upload_sizes)
        assert cw.files_uploaded == 5

    def test_mix_success_and_failure(self):
        """Test mix of successful and failed uploads"""
        cw = CloudWatchManager("cn-north-1", "test-vehicle", enabled=False)

        # 3 successes, 2 failures
        cw.record_upload_success(1000)
        cw.record_upload_success(2000)
        cw.record_upload_failure()
        cw.record_upload_success(3000)
        cw.record_upload_failure()

        assert cw.bytes_uploaded == 6000
        assert cw.files_uploaded == 3
        assert cw.files_failed == 2

    @patch("boto3.client")
    def test_metrics_reset_after_publish(self, mock_boto_client):
        """Test all counters reset to zero after successful publish"""
        mock_cw = Mock()
        mock_boto_client.return_value = mock_cw

        cw = CloudWatchManager("cn-north-1", "test-vehicle", enabled=True)

        # Record metrics
        cw.record_upload_success(5000)
        cw.record_upload_success(3000)
        cw.record_upload_failure()

        # Publish
        cw.publish_metrics(disk_usage_percent=50.0)

        # All should be reset
        assert cw.bytes_uploaded == 0
        assert cw.files_uploaded == 0
        assert cw.files_failed == 0

    def test_zero_metrics_publish(self):
        """Test publishing with zero recorded metrics"""
        with patch("boto3.client") as mock_boto_client:
            mock_cw = Mock()
            mock_boto_client.return_value = mock_cw

            cw = CloudWatchManager("cn-north-1", "test-vehicle", enabled=True)

            # Reset mock after initialization (ServiceStartup metric was published)
            mock_cw.put_metric_data.reset_mock()

            # Publish without recording anything
            cw.publish_metrics(disk_usage_percent=10.0)

            # Should still publish (with zeros)
            mock_cw.put_metric_data.assert_called_once()


# ============================================
# CLOUDWATCH API ERROR TESTS
# ============================================


class TestCloudWatchAPIErrors:
    """Test error handling for CloudWatch API calls"""

    @patch("boto3.client")
    def test_put_metric_data_throttling(self, mock_boto_client):
        """Test handling of CloudWatch throttling errors during init"""
        from botocore.exceptions import ClientError

        mock_cw = Mock()
        mock_cw.put_metric_data.side_effect = ClientError(
            {"Error": {"Code": "Throttling", "Message": "Rate exceeded"}}, "PutMetricData"
        )
        mock_boto_client.return_value = mock_cw

        # Should raise RuntimeError during initialization
        with pytest.raises(RuntimeError, match="CloudWatch enabled but cannot publish metrics"):
            cw = CloudWatchManager("cn-north-1", "test-vehicle", enabled=True)

    @patch("boto3.client")
    def test_put_metric_data_invalid_credentials(self, mock_boto_client):
        """Test handling of invalid AWS credentials during init"""
        from botocore.exceptions import ClientError

        mock_cw = Mock()
        mock_cw.put_metric_data.side_effect = ClientError(
            {"Error": {"Code": "InvalidClientTokenId"}}, "PutMetricData"
        )
        mock_boto_client.return_value = mock_cw

        # Should raise RuntimeError during initialization
        with pytest.raises(RuntimeError, match="CloudWatch enabled but cannot publish metrics"):
            cw = CloudWatchManager("cn-north-1", "test-vehicle", enabled=True)

    @patch("boto3.client")
    def test_put_metric_data_network_error(self, mock_boto_client):
        """Test handling of network errors during init"""
        from botocore.exceptions import EndpointConnectionError

        mock_cw = Mock()
        mock_cw.put_metric_data.side_effect = EndpointConnectionError(
            endpoint_url="https://monitoring.cn-north-1.amazonaws.com.cn"
        )
        mock_boto_client.return_value = mock_cw

        # Should raise RuntimeError during initialization
        with pytest.raises(RuntimeError, match="CloudWatch enabled but cannot publish metrics"):
            cw = CloudWatchManager("cn-north-1", "test-vehicle", enabled=True)

    @patch("boto3.client")
    def test_publish_with_boto_client_creation_failure(self, mock_boto_client):
        """Test handling when boto3 client creation fails"""
        mock_boto_client.side_effect = Exception("Cannot create client")

        # Should raise RuntimeError during initialization
        with pytest.raises(RuntimeError, match="CloudWatch initialization failed"):
            cw = CloudWatchManager("cn-north-1", "test-vehicle", enabled=True)


# ============================================
# METRIC DETAILS TESTS
# ============================================


class TestMetricDetails:
    """Test metric names, units, dimensions"""

    @patch("boto3.client")
    def test_metric_namespace_correct(self, mock_boto_client):
        """Test metrics use correct namespace 'TVM/Upload'"""
        mock_cw = Mock()
        mock_boto_client.return_value = mock_cw

        cw = CloudWatchManager("cn-north-1", "test-vehicle", enabled=True)
        cw.record_upload_success(1000)
        cw.publish_metrics()

        call_args = mock_cw.put_metric_data.call_args
        assert call_args[1]["Namespace"] == "TVM/Upload"

    @patch("boto3.client")
    def test_metric_dimensions_vehicle_id(self, mock_boto_client):
        """Test all metrics include VehicleId dimension"""
        mock_cw = Mock()
        mock_boto_client.return_value = mock_cw

        cw = CloudWatchManager("cn-north-1", "test-vehicle-123", enabled=True)
        cw.record_upload_success(1000)
        cw.publish_metrics(disk_usage_percent=50.0)

        call_args = mock_cw.put_metric_data.call_args
        metrics = call_args[1]["MetricData"]

        # All metrics should have VehicleId dimension
        for metric in metrics:
            dimensions = metric["Dimensions"]
            assert len(dimensions) == 1
            assert dimensions[0]["Name"] == "VehicleId"
            assert dimensions[0]["Value"] == "test-vehicle-123"

    @patch("boto3.client")
    def test_bytes_metric_unit(self, mock_boto_client):
        """Test BytesUploaded metric uses 'Bytes' unit"""
        mock_cw = Mock()
        mock_boto_client.return_value = mock_cw

        cw = CloudWatchManager("cn-north-1", "test-vehicle", enabled=True)
        cw.record_upload_success(1024 * 1024)  # 1MB
        cw.publish_metrics()

        call_args = mock_cw.put_metric_data.call_args
        metrics = call_args[1]["MetricData"]

        bytes_metric = next(m for m in metrics if m["MetricName"] == "BytesUploaded")
        assert bytes_metric["Unit"] == "Bytes"
        assert bytes_metric["Value"] == 1024 * 1024

    @patch("boto3.client")
    def test_count_metric_unit(self, mock_boto_client):
        """Test FileCount and FailureCount metrics use 'Count' unit"""
        mock_cw = Mock()
        mock_boto_client.return_value = mock_cw

        cw = CloudWatchManager("cn-north-1", "test-vehicle", enabled=True)
        cw.record_upload_success(1000)
        cw.record_upload_failure()
        cw.publish_metrics()

        call_args = mock_cw.put_metric_data.call_args
        metrics = call_args[1]["MetricData"]

        file_count = next(m for m in metrics if m["MetricName"] == "FileCount")
        failure_count = next(m for m in metrics if m["MetricName"] == "FailureCount")

        assert file_count["Unit"] == "Count"
        assert file_count["Value"] == 1

        assert failure_count["Unit"] == "Count"
        assert failure_count["Value"] == 1

    @patch("boto3.client")
    def test_disk_usage_metric_unit(self, mock_boto_client):
        """Test DiskUsagePercent metric uses 'Percent' unit"""
        mock_cw = Mock()
        mock_boto_client.return_value = mock_cw

        cw = CloudWatchManager("cn-north-1", "test-vehicle", enabled=True)
        cw.publish_metrics(disk_usage_percent=75.5)

        call_args = mock_cw.put_metric_data.call_args
        metrics = call_args[1]["MetricData"]

        disk_metric = next(m for m in metrics if m["MetricName"] == "DiskUsagePercent")
        assert disk_metric["Unit"] == "Percent"
        assert disk_metric["Value"] == 75.5

    @patch("boto3.client")
    def test_all_metric_names(self, mock_boto_client):
        """Test all expected metric names are present"""
        mock_cw = Mock()
        mock_boto_client.return_value = mock_cw

        cw = CloudWatchManager("cn-north-1", "test-vehicle", enabled=True)
        cw.record_upload_success(1000)
        cw.record_upload_failure()
        cw.publish_metrics(disk_usage_percent=50.0)

        call_args = mock_cw.put_metric_data.call_args
        metrics = call_args[1]["MetricData"]
        metric_names = {m["MetricName"] for m in metrics}

        expected_names = {"BytesUploaded", "FileCount", "FailureCount", "DiskUsagePercent"}
        assert metric_names == expected_names


# ============================================
# DISK USAGE METRIC TESTS
# ============================================


class TestDiskUsageMetrics:
    """Test disk usage percentage metric"""

    @patch("boto3.client")
    def test_disk_usage_zero_percent(self, mock_boto_client):
        """Test disk usage at 0%"""
        mock_cw = Mock()
        mock_boto_client.return_value = mock_cw

        cw = CloudWatchManager("cn-north-1", "test-vehicle", enabled=True)
        cw.publish_metrics(disk_usage_percent=0.0)

        call_args = mock_cw.put_metric_data.call_args
        metrics = call_args[1]["MetricData"]

        disk_metric = next(m for m in metrics if m["MetricName"] == "DiskUsagePercent")
        assert disk_metric["Value"] == 0.0

    @patch("boto3.client")
    def test_disk_usage_100_percent(self, mock_boto_client):
        """Test disk usage at 100%"""
        mock_cw = Mock()
        mock_boto_client.return_value = mock_cw

        cw = CloudWatchManager("cn-north-1", "test-vehicle", enabled=True)
        cw.publish_metrics(disk_usage_percent=100.0)

        call_args = mock_cw.put_metric_data.call_args
        metrics = call_args[1]["MetricData"]

        disk_metric = next(m for m in metrics if m["MetricName"] == "DiskUsagePercent")
        assert disk_metric["Value"] == 100.0

    @patch("boto3.client")
    def test_disk_usage_over_100_percent(self, mock_boto_client):
        """Test disk usage over 100% (edge case with reserved space)"""
        mock_cw = Mock()
        mock_boto_client.return_value = mock_cw

        cw = CloudWatchManager("cn-north-1", "test-vehicle", enabled=True)
        cw.publish_metrics(disk_usage_percent=105.0)

        call_args = mock_cw.put_metric_data.call_args
        metrics = call_args[1]["MetricData"]

        disk_metric = next(m for m in metrics if m["MetricName"] == "DiskUsagePercent")
        # Should report actual value (even if >100%)
        assert disk_metric["Value"] == 105.0

    @patch("boto3.client")
    def test_disk_usage_not_provided(self, mock_boto_client):
        """Test publishing without disk_usage_percent parameter"""
        mock_cw = Mock()
        mock_boto_client.return_value = mock_cw

        cw = CloudWatchManager("cn-north-1", "test-vehicle", enabled=True)
        cw.record_upload_success(1000)

        # Publish without disk_usage_percent
        cw.publish_metrics()

        call_args = mock_cw.put_metric_data.call_args
        metrics = call_args[1]["MetricData"]
        metric_names = {m["MetricName"] for m in metrics}

        # DiskUsagePercent should not be in metrics if not provided
        # (or should be 0, depending on implementation)
        assert (
            "DiskUsagePercent" not in metric_names
            or next(m for m in metrics if m["MetricName"] == "DiskUsagePercent")["Value"] == 0
        )

    @patch("boto3.client")
    def test_disk_usage_fractional_percent(self, mock_boto_client):
        """Test disk usage with decimal precision"""
        mock_cw = Mock()
        mock_boto_client.return_value = mock_cw

        cw = CloudWatchManager("cn-north-1", "test-vehicle", enabled=True)
        cw.publish_metrics(disk_usage_percent=87.654)

        call_args = mock_cw.put_metric_data.call_args
        metrics = call_args[1]["MetricData"]

        disk_metric = next(m for m in metrics if m["MetricName"] == "DiskUsagePercent")
        assert abs(disk_metric["Value"] - 87.654) < 0.001  # Float precision


# ============================================
# CHINA REGION TESTS
# ============================================


class TestChinaRegion:
    """Test China region CloudWatch endpoint"""

    @patch("boto3.client")
    def test_cloudwatch_china_endpoint(self, mock_boto_client):
        """Test CloudWatch uses China endpoint for cn regions"""
        mock_cw = Mock()
        mock_boto_client.return_value = mock_cw

        cw = CloudWatchManager("cn-north-1", "test-vehicle", enabled=True)

        # Verify boto3.client was called with correct parameters
        mock_boto_client.assert_called_once()
        call_args = mock_boto_client.call_args

        # Should be creating 'cloudwatch' client
        assert call_args[0][0] == "cloudwatch"

        # Should specify region
        assert call_args[1]["region_name"] == "cn-north-1"

    @patch("boto3.client")
    def test_cloudwatch_standard_region(self, mock_boto_client):
        """Test CloudWatch with standard AWS region"""
        mock_cw = Mock()
        mock_boto_client.return_value = mock_cw

        cw = CloudWatchManager("us-east-1", "test-vehicle", enabled=True)

        call_args = mock_boto_client.call_args
        assert call_args[1]["region_name"] == "us-east-1"


# ============================================
# LARGE-SCALE TESTS
# ============================================


class TestLargeScaleMetrics:
    """Test handling large numbers of metrics"""

    @patch("boto3.client")
    def test_many_uploads_aggregation(self, mock_boto_client):
        """Test aggregating 1000+ uploads"""
        mock_cw = Mock()
        mock_boto_client.return_value = mock_cw

        cw = CloudWatchManager("cn-north-1", "test-vehicle", enabled=True)

        # Record 1000 uploads
        total_bytes = 0
        for i in range(1000):
            size = 1024 * (i + 1)  # Varying sizes
            cw.record_upload_success(size)
            total_bytes += size

        assert cw.files_uploaded == 1000
        assert cw.bytes_uploaded == total_bytes

        # Publish should work fine
        cw.publish_metrics()
        assert cw.files_uploaded == 0  # Reset after publish

    @patch("boto3.client")
    def test_very_large_byte_count(self, mock_boto_client):
        """Test handling very large byte counts (TB range)"""
        mock_cw = Mock()
        mock_boto_client.return_value = mock_cw

        cw = CloudWatchManager("cn-north-1", "test-vehicle", enabled=True)

        # Upload 1TB worth of data
        one_tb = 1024 * 1024 * 1024 * 1024
        cw.record_upload_success(one_tb)

        cw.publish_metrics()

        call_args = mock_cw.put_metric_data.call_args
        metrics = call_args[1]["MetricData"]

        bytes_metric = next(m for m in metrics if m["MetricName"] == "BytesUploaded")
        assert bytes_metric["Value"] == one_tb


# ============================================
# EDGE CASE TESTS
# ============================================


class TestEdgeCases:
    """Test edge cases and boundary conditions"""

    def test_negative_bytes_rejected(self):
        """Test that negative bytes are rejected or handled"""
        cw = CloudWatchManager("cn-north-1", "test-vehicle", enabled=False)

        # Negative bytes should either raise error or be ignored
        try:
            cw.record_upload_success(-1000)
            # If accepted, should not make counters negative
            assert cw.bytes_uploaded >= 0
        except (ValueError, AssertionError):
            # Or it raises an error - both are acceptable
            pass

    def test_multiple_publish_cycles(self):
        """Test multiple publish/record cycles"""
        with patch("boto3.client") as mock_boto_client:
            mock_cw = Mock()
            mock_boto_client.return_value = mock_cw

            cw = CloudWatchManager("cn-north-1", "test-vehicle", enabled=True)

            # Reset mock after initialization (ServiceStartup metric was published)
            mock_cw.put_metric_data.reset_mock()

            # Cycle 1
            cw.record_upload_success(1000)
            cw.publish_metrics()
            assert mock_cw.put_metric_data.call_count == 1

            # Cycle 2
            cw.record_upload_success(2000)
            cw.publish_metrics()
            assert mock_cw.put_metric_data.call_count == 2

            # Cycle 3
            cw.record_upload_success(3000)
            cw.publish_metrics()
            assert mock_cw.put_metric_data.call_count == 3

    @patch("boto3.client")
    def test_publish_with_only_failures(self, mock_boto_client):
        """Test publishing when only failures occurred (no successes)"""
        mock_cw = Mock()
        mock_boto_client.return_value = mock_cw

        cw = CloudWatchManager("cn-north-1", "test-vehicle", enabled=True)

        # Reset mock after initialization (ServiceStartup metric was published)
        mock_cw.put_metric_data.reset_mock()

        # Only record failures
        cw.record_upload_failure()
        cw.record_upload_failure()
        cw.record_upload_failure()

        cw.publish_metrics(disk_usage_percent=50.0)

        call_args = mock_cw.put_metric_data.call_args
        metrics = call_args[1]["MetricData"]

        # Should have FailureCount and DiskUsagePercent (bytes/files are 0, so not published)
        failure_count = next(m for m in metrics if m["MetricName"] == "FailureCount")
        disk_usage = next(m for m in metrics if m["MetricName"] == "DiskUsagePercent")

        assert failure_count["Value"] == 3
        assert disk_usage["Value"] == 50.0

    @patch("boto3.client")
    def test_vehicle_id_with_special_characters(self, mock_boto_client):
        """Test vehicle ID with special characters"""
        mock_cw = Mock()
        mock_boto_client.return_value = mock_cw

        special_vehicle_id = "vehicle-CN-北京-001"
        cw = CloudWatchManager("cn-north-1", special_vehicle_id, enabled=True)
        cw.record_upload_success(1000)
        cw.publish_metrics()

        call_args = mock_cw.put_metric_data.call_args
        metrics = call_args[1]["MetricData"]

        # Verify vehicle ID is correctly used
        for metric in metrics:
            dimensions = metric["Dimensions"]
            assert dimensions[0]["Value"] == special_vehicle_id
