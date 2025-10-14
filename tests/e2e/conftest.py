# tests/e2e/conftest.py
"""
Fixtures for E2E tests (REAL AWS)
These tests use actual AWS services and run in CI/CD only
"""

import pytest
import boto3
import os
from pathlib import Path


@pytest.fixture(scope='session')
def aws_config():
    """
    Real AWS configuration
    Uses environment variables or defaults for CI/CD
    """
    return {
        'profile': os.getenv('AWS_PROFILE', 'china'),
        'bucket': os.getenv('TEST_BUCKET', 't01logs'),
        'region': os.getenv('AWS_REGION', 'cn-north-1'),
        'vehicle_id': 'e2e-test-vehicle'
    }


@pytest.fixture
def real_s3_client(aws_config):
    """
    REAL S3 client - connects to actual AWS
    NO MOCKING - this makes real API calls
    """
    session = boto3.Session(profile_name=aws_config['profile'])
    return session.client(
        's3',
        region_name=aws_config['region'],
        endpoint_url=f"https://s3.{aws_config['region']}.amazonaws.com.cn"
    )


@pytest.fixture
def real_cloudwatch_client(aws_config):
    """
    REAL CloudWatch client
    """
    session = boto3.Session(profile_name=aws_config['profile'])
    return session.client(
        'cloudwatch',
        region_name=aws_config['region']
    )


@pytest.fixture
def real_upload_manager(aws_config):
    """
    Upload manager connected to REAL AWS S3
    """
    from src.upload_manager import UploadManager
    return UploadManager(
        bucket=aws_config['bucket'],
        region=aws_config['region'],
        vehicle_id=aws_config['vehicle_id'],
        profile_name=aws_config['profile']
    )


@pytest.fixture
def s3_cleanup(real_s3_client, aws_config):
    """
    Auto-cleanup S3 objects after test completes
    Usage: s3_cleanup('path/to/object.log')
    """
    objects_to_delete = []
    
    def track(key):
        """Track S3 key for deletion"""
        objects_to_delete.append(key)
        return key
    
    yield track
    
    # Cleanup after test finishes
    for key in objects_to_delete:
        try:
            real_s3_client.delete_object(
                Bucket=aws_config['bucket'],
                Key=key
            )
            print(f"✓ Cleaned up s3://{aws_config['bucket']}/{key}")
        except Exception as e:
            print(f"✗ Cleanup failed for {key}: {e}")
