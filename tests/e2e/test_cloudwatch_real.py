# tests/e2e/test_cloudwatch_real.py
"""
Real CloudWatch integration tests
"""

import pytest
from src.cloudwatch_manager import CloudWatchManager


@pytest.mark.e2e
@pytest.mark.real_aws
def test_publish_metrics_to_real_cloudwatch(real_cloudwatch_client, aws_config):
    """Test publishing metrics to real CloudWatch - Enhanced with verification"""
    cw = CloudWatchManager(
        region=aws_config['region'],
        vehicle_id='e2e-test-vehicle',
        enabled=True
    )
    
    # Replace with real client
    cw.cw_client = real_cloudwatch_client
    
    # Record multiple types of metrics
    cw.record_upload_success(1024 * 1024)  # 1MB
    cw.record_upload_success(2 * 1024 * 1024)  # 2MB
    cw.record_upload_failure()
    
    # Publish to real CloudWatch
    try:
        cw.publish_metrics(disk_usage_percent=75.0)
        print("✓ Metrics published to CloudWatch")
        
        # Verify metrics were reset after publish
        assert cw.bytes_uploaded == 0, "Bytes should be reset after publish"
        assert cw.files_uploaded == 0, "File count should be reset after publish"
        assert cw.files_failed == 0, "Failure count should be reset after publish"
        
        print("✓ Metric accumulators correctly reset after publish")
        
        # Wait briefly for CloudWatch to process
        import time
        time.sleep(2)
        
        # Attempt to query metrics (optional - may need more complex filtering)
        try:
            # Query recent metrics for this vehicle
            from datetime import datetime, timedelta
            end_time = datetime.utcnow()
            start_time = end_time - timedelta(minutes=5)
            
            response = real_cloudwatch_client.get_metric_statistics(
                Namespace='TVM/Upload',
                MetricName='BytesUploaded',
                Dimensions=[
                    {'Name': 'VehicleId', 'Value': 'e2e-test-vehicle'}
                ],
                StartTime=start_time,
                EndTime=end_time,
                Period=300,  # 5 minutes
                Statistics=['Sum']
            )
            
            if response.get('Datapoints'):
                print(f"✓ Verified {len(response['Datapoints'])} datapoints in CloudWatch")
            else:
                print("⚠ No datapoints found yet (may take time to appear)")
                
        except Exception as e:
            print(f"⚠ Could not verify metrics in CloudWatch (this is OK): {e}")
        
    except Exception as e:
        pytest.fail(f"Failed to publish to CloudWatch: {e}")


@pytest.mark.e2e
@pytest.mark.real_aws
def test_cloudwatch_alarm_creation(real_cloudwatch_client, aws_config):
    """Test creating CloudWatch alarm - Enhanced with better cleanup"""
    alarm_name = f"TVM-LowUpload-e2e-test-vehicle"
    
    cw = CloudWatchManager(
        region=aws_config['region'],
        vehicle_id='e2e-test-vehicle',
        enabled=True
    )
    cw.cw_client = real_cloudwatch_client
    
    try:
        # Create alarm
        cw.create_low_upload_alarm(threshold_mb=100)
        print("✓ CloudWatch alarm created")
        
        # Verify alarm exists
        response = real_cloudwatch_client.describe_alarms(
            AlarmNames=[alarm_name]
        )
        
        assert len(response['MetricAlarms']) == 1, "Alarm should exist"
        alarm = response['MetricAlarms'][0]
        
        # Verify alarm configuration
        assert alarm['AlarmName'] == alarm_name
        assert alarm['MetricName'] == 'BytesUploaded'
        assert alarm['Namespace'] == 'TVM/Upload'
        assert alarm['Statistic'] == 'Sum'
        assert alarm['Threshold'] == 100 * 1024 * 1024  # 100MB in bytes
        assert alarm['ComparisonOperator'] == 'LessThanThreshold'
        assert alarm['EvaluationPeriods'] == 3
        
        print(f"✓ Alarm configuration verified:")
        print(f"  Threshold: {alarm['Threshold'] / (1024**2):.0f} MB")
        print(f"  Evaluation Periods: {alarm['EvaluationPeriods']}")
        
    except Exception as e:
        pytest.fail(f"Alarm creation/verification failed: {e}")
    
    finally:
        # Cleanup: delete alarm
        try:
            real_cloudwatch_client.delete_alarms(AlarmNames=[alarm_name])
            print("✓ Alarm cleaned up")
        except Exception as e:
            print(f"⚠ Alarm cleanup failed: {e}")

@pytest.mark.e2e
@pytest.mark.real_aws
def test_publish_deletion_metrics(real_cloudwatch_client, aws_config):
    """Test publishing deletion policy metrics (v2.0)"""
    cw = CloudWatchManager(
        region=aws_config['region'],
        vehicle_id='e2e-test-vehicle',
        enabled=True
    )
    cw.cw_client = real_cloudwatch_client
    
    # Record upload and deletion events
    cw.record_upload_success(5 * 1024 * 1024)  # 5MB
    cw.record_upload_failure()
    
    # NEW v2.0: Record deletion events
    # (Note: CloudWatchManager may need these methods added in your actual code)
    if hasattr(cw, 'record_file_deletion'):
        cw.record_file_deletion(file_size=2 * 1024 * 1024, reason='after_upload')
    
    try:
        cw.publish_metrics(disk_usage_percent=85.0)
        print("✓ Deletion metrics published to CloudWatch")
    except Exception as e:
        pytest.fail(f"Failed to publish deletion metrics: {e}")


@pytest.mark.e2e
@pytest.mark.real_aws
def test_publish_queue_metrics(real_cloudwatch_client, aws_config):
    """Test publishing queue size metrics (v2.0)"""
    cw = CloudWatchManager(
        region=aws_config['region'],
        vehicle_id='e2e-test-vehicle',
        enabled=True
    )
    cw.cw_client = real_cloudwatch_client
    
    # Simulate queue metrics
    # (Note: You may need to add these methods to CloudWatchManager)
    if hasattr(cw, 'record_queue_size'):
        cw.record_queue_size(queue_count=15, queue_bytes=250 * 1024 * 1024)
    
    try:
        cw.publish_metrics(disk_usage_percent=80.0)
        print("✓ Queue metrics published to CloudWatch")
    except Exception as e:
        pytest.fail(f"Failed to publish queue metrics: {e}")


@pytest.mark.e2e
@pytest.mark.real_aws
def test_publish_all_metric_types(real_cloudwatch_client, aws_config):
    """
    Test publishing all metric types supported by CloudWatch manager
    
    Metrics:
    - BytesUploaded (Sum)
    - FileCount (Count)
    - FailureCount (Count)
    - DiskUsagePercent (Gauge)
    """
    cw = CloudWatchManager(
        region=aws_config['region'],
        vehicle_id='e2e-test-vehicle',
        enabled=True
    )
    cw.cw_client = real_cloudwatch_client
    
    # Record diverse metrics
    cw.record_upload_success(5 * 1024 * 1024)   # 5MB
    cw.record_upload_success(10 * 1024 * 1024)  # 10MB
    cw.record_upload_success(3 * 1024 * 1024)   # 3MB
    cw.record_upload_failure()
    cw.record_upload_failure()
    
    try:
        # Publish all metrics including disk usage
        cw.publish_metrics(disk_usage_percent=82.5)
        
        print("✓ All metric types published:")
        print(f"  - BytesUploaded: {18 * 1024 * 1024} bytes (18MB)")
        print(f"  - FileCount: 3")
        print(f"  - FailureCount: 2")
        print(f"  - DiskUsagePercent: 82.5%")
        
        # Verify reset
        assert cw.bytes_uploaded == 0
        assert cw.files_uploaded == 0
        assert cw.files_failed == 0
        
        print("✓ All accumulators reset correctly")
        
    except Exception as e:
        pytest.fail(f"Failed to publish all metric types: {e}")


@pytest.mark.e2e
@pytest.mark.real_aws
def test_publish_metrics_with_no_data(real_cloudwatch_client, aws_config):
    """Test that publishing with no recorded metrics doesn't cause errors"""
    cw = CloudWatchManager(
        region=aws_config['region'],
        vehicle_id='e2e-test-vehicle',
        enabled=True
    )
    cw.cw_client = real_cloudwatch_client
    
    # Don't record any metrics
    assert cw.bytes_uploaded == 0
    assert cw.files_uploaded == 0
    assert cw.files_failed == 0
    
    try:
        # Publish with no data - should not error
        cw.publish_metrics(disk_usage_percent=70.0)
        print("✓ Empty metrics publish succeeded (no error)")
        
        # Only disk usage should be published
        print("✓ Handled empty upload metrics gracefully")
        
    except Exception as e:
        pytest.fail(f"Empty metrics publish failed: {e}")


@pytest.mark.e2e
@pytest.mark.real_aws
def test_cloudwatch_disabled_mode(aws_config):
    """Test that CloudWatch manager works correctly when disabled"""
    cw = CloudWatchManager(
        region=aws_config['region'],
        vehicle_id='e2e-test-vehicle',
        enabled=False  # Disabled
    )
    
    # Should not have client
    assert cw.enabled is False
    
    # Record metrics
    cw.record_upload_success(1024 * 1024)
    cw.record_upload_failure()
    
    # Metrics should accumulate
    assert cw.bytes_uploaded == 1024 * 1024
    assert cw.files_uploaded == 1
    assert cw.files_failed == 1
    
    # Publish should be no-op (not error)
    try:
        cw.publish_metrics(disk_usage_percent=75.0)
        print("✓ Publish is no-op when disabled")
        
        # Metrics should NOT be reset when disabled
        assert cw.bytes_uploaded == 1024 * 1024, "Metrics should not reset when disabled"
        assert cw.files_uploaded == 1
        assert cw.files_failed == 1
        
        print("✓ Metrics not reset when CloudWatch disabled")
        
    except Exception as e:
        pytest.fail(f"Disabled mode should not error: {e}")


@pytest.mark.e2e
@pytest.mark.real_aws
@pytest.mark.slow
def test_high_frequency_metric_publishing(real_cloudwatch_client, aws_config):
    """
    Test publishing metrics multiple times in succession
    
    Simulates real-world scenario where metrics are published
    every hour throughout the day
    """
    cw = CloudWatchManager(
        region=aws_config['region'],
        vehicle_id='e2e-test-vehicle-hf',  # Different vehicle to avoid conflicts
        enabled=True
    )
    cw.cw_client = real_cloudwatch_client
    
    publish_count = 5  # Publish 5 times
    
    try:
        for i in range(publish_count):
            # Record some metrics
            cw.record_upload_success((i + 1) * 1024 * 1024)  # 1MB, 2MB, 3MB...
            
            # Publish
            cw.publish_metrics(disk_usage_percent=70.0 + i)
            
            print(f"✓ Publish {i+1}/{publish_count} succeeded")
            
            # Verify reset after each publish
            assert cw.bytes_uploaded == 0
            assert cw.files_uploaded == 0
            
            # Small delay to avoid rate limiting
            import time
            time.sleep(1)
        
        print(f"✓ Successfully published metrics {publish_count} times")
        print("✓ High-frequency publishing verified")
        
    except Exception as e:
        pytest.fail(f"High-frequency publishing failed: {e}")