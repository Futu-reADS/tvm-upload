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

CLOUDWATCH_NAMESPACE = 'TVM/Upload'
METRIC_BYTES_UPLOADED = 'BytesUploaded'
METRIC_FILE_COUNT = 'FileCount'
METRIC_FAILURE_COUNT = 'FailureCount'
METRIC_DISK_USAGE = 'DiskUsagePercent'
METRIC_SERVICE_STARTUP = 'ServiceStartup'
DEFAULT_ALARM_EVALUATION_PERIODS = 3
ALARM_PERIOD_SECONDS = 86400


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
    
    def __init__(self, region: str, vehicle_id: str, enabled: bool = True, profile_name: str = None):
        """Initialize CloudWatch manager."""
        self.region = region
        self.vehicle_id = vehicle_id
        self.enabled = enabled
        self.profile_name = profile_name
        self.cw_client = None
        self.bytes_uploaded = 0
        self.files_uploaded = 0
        self.files_failed = 0

        if self.enabled:
            try:
                import os
                endpoint_url = os.getenv('AWS_ENDPOINT_URL')

                if endpoint_url:
                    logger.info(f"CloudWatch in TEST mode (endpoint: {endpoint_url})")
                    client_kwargs = {
                        'region_name': region,
                        'endpoint_url': endpoint_url,
                        'aws_access_key_id': os.getenv('AWS_ACCESS_KEY_ID', 'test'),
                        'aws_secret_access_key': os.getenv('AWS_SECRET_ACCESS_KEY', 'test')
                    }
                    self.cw_client = boto3.client('cloudwatch', **client_kwargs)
                    logger.info("CloudWatch client created (TEST mode)")
                else:
                    # Create session with profile if specified
                    if profile_name:
                        session = boto3.Session(profile_name=profile_name)
                        self.cw_client = session.client('cloudwatch', region_name=region)
                        logger.info(f"CloudWatch initialized with profile '{profile_name}' for region: {region}")
                    else:
                        self.cw_client = boto3.client('cloudwatch', region_name=region)
                        logger.info(f"CloudWatch initialized for region: {region}")

                    try:
                        self.cw_client.put_metric_data(
                            Namespace=CLOUDWATCH_NAMESPACE,
                            MetricData=[{
                                'MetricName': METRIC_SERVICE_STARTUP,
                                'Value': 1,
                                'Unit': 'Count',
                                'Timestamp': datetime.utcnow(),
                                'Dimensions': [
                                    {'Name': 'VehicleId', 'Value': self.vehicle_id}
                                ]
                            }]
                        )
                        logger.info("✓ CloudWatch permissions verified (test metric published)")
                    except Exception as perm_error:
                        logger.error(f"✗ CloudWatch permission test FAILED: {perm_error}")
                        logger.error("="*60)
                        logger.error("CRITICAL: CloudWatch is enabled but cannot publish metrics")
                        logger.error("This indicates IAM permission issues")
                        logger.error("")
                        logger.error("Required IAM permissions:")
                        logger.error("  - cloudwatch:PutMetricData")
                        logger.error("  - cloudwatch:PutMetricAlarm (for alarms)")
                        logger.error("")
                        logger.error("Action required:")
                        logger.error("  1. Fix IAM policy for this vehicle's credentials")
                        logger.error("  2. Or set monitoring.cloudwatch_enabled: false in config")
                        logger.error("="*60)
                        raise RuntimeError(f"CloudWatch enabled but cannot publish metrics: {perm_error}")

            except RuntimeError:
                raise

            except Exception as e:
                logger.error(f"CloudWatch client creation failed: {e}")
                logger.error("="*60)
                logger.error("CRITICAL: CloudWatch initialization failed")
                logger.error(f"Region: {region}")
                logger.error(f"Vehicle ID: {vehicle_id}")
                logger.error("")
                logger.error("Possible causes:")
                logger.error("  1. Invalid AWS credentials")
                logger.error("  2. Invalid region name")
                logger.error("  3. Network connectivity issues")
                logger.error("  4. Missing boto3 dependencies")
                logger.error("")
                logger.error("Action required:")
                logger.error("  - If CloudWatch monitoring is required, fix the issue above")
                logger.error("  - If monitoring is optional, set monitoring.cloudwatch_enabled: false")
                logger.error("="*60)
                raise RuntimeError(f"CloudWatch initialization failed: {e}")
        else:
            logger.info("CloudWatch disabled (enabled=False)")


    def record_upload_success(self, file_size: int):
        """Record successful file upload."""
        self.bytes_uploaded += file_size
        self.files_uploaded += 1
        logger.debug(f"Recorded upload: {file_size} bytes")

    def record_upload_failure(self):
        """Record failed file upload."""
        self.files_failed += 1
        logger.debug("Recorded upload failure")

    def publish_metrics(self, disk_usage_percent: Optional[float] = None):
        """Publish accumulated metrics to CloudWatch and reset accumulators."""
        if not self.enabled:
            logger.debug("CloudWatch disabled, skipping publish")
            return
        
        if self.cw_client is None:
            logger.error("CloudWatch client not initialized, cannot publish metrics")
            return
        
        try:
            metrics = []
            timestamp = datetime.utcnow()

            if self.bytes_uploaded > 0:
                metrics.append({
                    'MetricName': METRIC_BYTES_UPLOADED,
                    'Value': self.bytes_uploaded,
                    'Unit': 'Bytes',
                    'Timestamp': timestamp,
                    'Dimensions': [{'Name': 'VehicleId', 'Value': self.vehicle_id}]
                })

            if self.files_uploaded > 0:
                metrics.append({
                    'MetricName': METRIC_FILE_COUNT,
                    'Value': self.files_uploaded,
                    'Unit': 'Count',
                    'Timestamp': timestamp,
                    'Dimensions': [{'Name': 'VehicleId', 'Value': self.vehicle_id}]
                })

            if self.files_failed > 0:
                metrics.append({
                    'MetricName': METRIC_FAILURE_COUNT,
                    'Value': self.files_failed,
                    'Unit': 'Count',
                    'Timestamp': timestamp,
                    'Dimensions': [{'Name': 'VehicleId', 'Value': self.vehicle_id}]
                })

            if disk_usage_percent is not None:
                metrics.append({
                    'MetricName': METRIC_DISK_USAGE,
                    'Value': disk_usage_percent,
                    'Unit': 'Percent',
                    'Timestamp': timestamp,
                    'Dimensions': [{'Name': 'VehicleId', 'Value': self.vehicle_id}]
                })

            if metrics:
                self.cw_client.put_metric_data(
                    Namespace=CLOUDWATCH_NAMESPACE,
                    MetricData=metrics
                )
                logger.info(f"Published {len(metrics)} metrics to CloudWatch")
                self.bytes_uploaded = 0
                self.files_uploaded = 0
                self.files_failed = 0

        except Exception as e:
            logger.error(f"Failed to publish CloudWatch metrics: {e}")

    def create_low_upload_alarm(self, threshold_mb: int = 100):
        """Create CloudWatch alarm for low upload volume (triggers if <threshold_mb for 3 consecutive days)."""
        if not self.enabled:
            return
        
        try:
            alarm_name = f"TVM-LowUpload-{self.vehicle_id}"

            self.cw_client.put_metric_alarm(
                AlarmName=alarm_name,
                ComparisonOperator='LessThanThreshold',
                EvaluationPeriods=DEFAULT_ALARM_EVALUATION_PERIODS,
                MetricName=METRIC_BYTES_UPLOADED,
                Namespace=CLOUDWATCH_NAMESPACE,
                Period=ALARM_PERIOD_SECONDS,
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