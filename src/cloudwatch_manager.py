#!/usr/bin/env python3
"""
CloudWatch Manager for TVM Log Upload System
Publishes metrics and creates alarms
"""

import boto3
import logging
from datetime import datetime
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class CloudWatchManager:
    """
    Manages CloudWatch metrics for upload monitoring.
    
    Metrics Published:
    - TVM/Upload/BytesUploaded (daily aggregate)
    - TVM/Upload/FileCount (daily count)
    - TVM/Upload/FailureCount (daily failures)
    - TVM/Disk/UsagePercent (current disk usage)
    
    Example:
        >>> cw = CloudWatchManager('cn-north-1', 'vehicle-001')
        >>> cw.record_upload_success(file_size=1024*1024*50)  # 50MB
        >>> cw.record_upload_failure()
        >>> cw.publish_metrics()
    """
    
    def __init__(self, region: str, vehicle_id: str, enabled: bool = True):
        """
        Initialize CloudWatch manager.
        
        Args:
            region: AWS region (e.g., 'cn-north-1')
            vehicle_id: Vehicle identifier for dimensions
            enabled: Enable/disable CloudWatch (False for testing)
        """
        self.region = region
        self.vehicle_id = vehicle_id
        self.enabled = enabled
        
        # Metric accumulators (reset after publish)
        self.bytes_uploaded = 0
        self.files_uploaded = 0
        self.files_failed = 0
        
        # Initialize CloudWatch client
        if self.enabled:
            try:
                self.cw_client = boto3.client('cloudwatch', region_name=region)
                logger.info(f"CloudWatch initialized for region: {region}")
            except Exception as e:
                logger.warning(f"CloudWatch client creation failed: {e}")
                self.enabled = False
        else:
            logger.info("CloudWatch disabled")
    
    def record_upload_success(self, file_size: int):
        """
        Record successful file upload.
        
        Args:
            file_size: Size of uploaded file in bytes
        """
        self.bytes_uploaded += file_size
        self.files_uploaded += 1
        logger.debug(f"Recorded upload: {file_size} bytes")
    
    def record_upload_failure(self):
        """Record failed file upload."""
        self.files_failed += 1
        logger.debug("Recorded upload failure")
    
    def publish_metrics(self, disk_usage_percent: Optional[float] = None):
        """
        Publish accumulated metrics to CloudWatch.
        
        Publishes all metrics and resets accumulators.
        Call this periodically (e.g., hourly or daily).
        
        Args:
            disk_usage_percent: Current disk usage (0-100)
        """
        if not self.enabled:
            logger.debug("CloudWatch disabled, skipping publish")
            return
        
        try:
            metrics = []
            timestamp = datetime.utcnow()
            
            # Bytes uploaded metric
            if self.bytes_uploaded > 0:
                metrics.append({
                    'MetricName': 'BytesUploaded',
                    'Value': self.bytes_uploaded,
                    'Unit': 'Bytes',
                    'Timestamp': timestamp,
                    'Dimensions': [
                        {'Name': 'VehicleId', 'Value': self.vehicle_id}
                    ]
                })
            
            # File count metric
            if self.files_uploaded > 0:
                metrics.append({
                    'MetricName': 'FileCount',
                    'Value': self.files_uploaded,
                    'Unit': 'Count',
                    'Timestamp': timestamp,
                    'Dimensions': [
                        {'Name': 'VehicleId', 'Value': self.vehicle_id}
                    ]
                })
            
            # Failure count metric
            if self.files_failed > 0:
                metrics.append({
                    'MetricName': 'FailureCount',
                    'Value': self.files_failed,
                    'Unit': 'Count',
                    'Timestamp': timestamp,
                    'Dimensions': [
                        {'Name': 'VehicleId', 'Value': self.vehicle_id}
                    ]
                })
            
            # Disk usage metric
            if disk_usage_percent is not None:
                metrics.append({
                    'MetricName': 'DiskUsagePercent',
                    'Value': disk_usage_percent,
                    'Unit': 'Percent',
                    'Timestamp': timestamp,
                    'Dimensions': [
                        {'Name': 'VehicleId', 'Value': self.vehicle_id}
                    ]
                })
            
            # Publish to CloudWatch
            if metrics:
                self.cw_client.put_metric_data(
                    Namespace='TVM/Upload',
                    MetricData=metrics
                )
                logger.info(f"Published {len(metrics)} metrics to CloudWatch")
                
                # Reset accumulators
                self.bytes_uploaded = 0
                self.files_uploaded = 0
                self.files_failed = 0
            
        except Exception as e:
            logger.error(f"Failed to publish CloudWatch metrics: {e}")
    
    def create_low_upload_alarm(self, threshold_mb: int = 100):
        """
        Create CloudWatch alarm for low upload volume.
        
        Triggers if <threshold_mb uploaded for 3 consecutive days.
        
        Args:
            threshold_mb: Minimum MB per day threshold
        """
        if not self.enabled:
            return
        
        try:
            alarm_name = f"TVM-LowUpload-{self.vehicle_id}"
            
            self.cw_client.put_metric_alarm(
                AlarmName=alarm_name,
                ComparisonOperator='LessThanThreshold',
                EvaluationPeriods=3,
                MetricName='BytesUploaded',
                Namespace='TVM/Upload',
                Period=86400,  # 1 day
                Statistic='Sum',
                Threshold=threshold_mb * 1024 * 1024,  # Convert to bytes
                ActionsEnabled=False,  # Add SNS later if needed
                AlarmDescription=f'Upload volume for {self.vehicle_id} below {threshold_mb}MB for 3 days',
                Dimensions=[
                    {'Name': 'VehicleId', 'Value': self.vehicle_id}
                ]
            )
            logger.info(f"Created CloudWatch alarm: {alarm_name}")
            
        except Exception as e:
            logger.error(f"Failed to create CloudWatch alarm: {e}")


if __name__ == '__main__':
    import sys
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Test CloudWatch manager (dry run mode)
    cw = CloudWatchManager('cn-north-1', 'test-vehicle', enabled=False)
    
    # Simulate uploads
    cw.record_upload_success(1024 * 1024 * 50)  # 50 MB
    cw.record_upload_success(1024 * 1024 * 100)  # 100 MB
    cw.record_upload_failure()
    
    # Publish metrics
    cw.publish_metrics(disk_usage_percent=75.5)
    
    logger.info(f"Bytes: {cw.bytes_uploaded}, Files: {cw.files_uploaded}, Failures: {cw.files_failed}")