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
        'profile': os.getenv('AWS_PROFILE', None),  # ✅ None instead of 'china'
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
    # ✅ CRITICAL: Check if profile exists before using it
    if aws_config['profile']:
        # Local: Use profile
        session = boto3.Session(
            profile_name=aws_config['profile'],
            region_name=aws_config['region']
        )
    else:
        # CI/CD: Use OIDC credentials (no profile)
        session = boto3.Session(region_name=aws_config['region'])
    
    return session.client(
        's3',
        endpoint_url=f"https://s3.{aws_config['region']}.amazonaws.com.cn"
    )


@pytest.fixture
def real_cloudwatch_client(aws_config):
    """
    REAL CloudWatch client
    """
    # ✅ CRITICAL: Check if profile exists before using it
    if aws_config['profile']:
        # Local: Use profile
        session = boto3.Session(
            profile_name=aws_config['profile'],
            region_name=aws_config['region']
        )
    else:
        # CI/CD: Use OIDC credentials (no profile)
        session = boto3.Session(region_name=aws_config['region'])
    
    return session.client('cloudwatch')


@pytest.fixture
def real_upload_manager(aws_config):
    """
    Upload manager connected to REAL AWS S3
    """
    from src.upload_manager import UploadManager
    
    # ✅ This is OK - UploadManager already handles None profile
    return UploadManager(
        bucket=aws_config['bucket'],
        region=aws_config['region'],
        vehicle_id=aws_config['vehicle_id'],
        profile_name=aws_config['profile']  # Will be None in CI - handled by UploadManager
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