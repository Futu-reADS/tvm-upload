# tests/e2e/test_cloudwatch_real.py
"""
Real CloudWatch integration tests
"""

import pytest
from src.cloudwatch_manager import CloudWatchManager


@pytest.mark.e2e
@pytest.mark.real_aws
def test_publish_metrics_to_real_cloudwatch(real_cloudwatch_client, aws_config):
    """Test publishing metrics to real CloudWatch"""
    cw = CloudWatchManager(
        region=aws_config['region'],
        vehicle_id='e2e-test-vehicle',
        enabled=True
    )
    
    # Replace with real client
    cw.cw_client = real_cloudwatch_client
    
    # Record some metrics
    cw.record_upload_success(1024 * 1024)  # 1MB
    cw.record_upload_success(2 * 1024 * 1024)  # 2MB
    
    # Publish to real CloudWatch
    try:
        cw.publish_metrics(disk_usage_percent=75.0)
        print("✓ Metrics published to CloudWatch")
    except Exception as e:
        pytest.fail(f"Failed to publish to CloudWatch: {e}")


@pytest.mark.e2e
@pytest.mark.real_aws
def test_cloudwatch_alarm_creation(real_cloudwatch_client, aws_config):
    """Test creating CloudWatch alarm"""
    cw = CloudWatchManager(
        region=aws_config['region'],
        vehicle_id='e2e-test-vehicle',
        enabled=True
    )
    cw.cw_client = real_cloudwatch_client
    
    try:
        cw.create_low_upload_alarm(threshold_mb=100)
        print("✓ CloudWatch alarm created")
        
        # Cleanup: delete alarm
        real_cloudwatch_client.delete_alarms(
            AlarmNames=[f"TVM-LowUpload-e2e-test-vehicle"]
        )
        print("✓ Alarm cleaned up")
        
    except Exception as e:
        pytest.fail(f"Alarm creation failed: {e}")