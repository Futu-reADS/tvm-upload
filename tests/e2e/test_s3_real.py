# tests/e2e/test_s3_real.py
"""
Real S3 upload tests
These tests make actual API calls to AWS S3
"""

import pytest
import tempfile
from pathlib import Path


@pytest.mark.e2e
@pytest.mark.real_aws
def test_upload_small_file_to_real_s3(real_upload_manager, real_s3_client, s3_cleanup, aws_config):
    """Test uploading small file to actual S3"""
    # Create test file
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.log') as f:
        f.write('Real S3 E2E test\n' * 100)
        test_file = f.name
    
    try:
        # Upload to REAL S3
        result = real_upload_manager.upload_file(test_file)
        assert result is True, "Upload to real S3 failed"
        
        # Build S3 key
        s3_key = real_upload_manager._build_s3_key(Path(test_file))
        s3_cleanup(s3_key)  # Mark for cleanup
        
        # Verify file exists in S3
        response = real_s3_client.head_object(
            Bucket=aws_config['bucket'],
            Key=s3_key
        )
        
        assert response['ResponseMetadata']['HTTPStatusCode'] == 200
        assert response['ContentLength'] > 0
        
        print(f"✓ Uploaded to s3://{aws_config['bucket']}/{s3_key}")
        
    finally:
        Path(test_file).unlink(missing_ok=True)


@pytest.mark.e2e
@pytest.mark.real_aws
@pytest.mark.slow
def test_upload_large_file_multipart(real_upload_manager, real_s3_client, s3_cleanup, aws_config):
    """Test multipart upload with 10MB file"""
    # Create 10MB file
    with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.mcap') as f:
        f.write(b'0' * (10 * 1024 * 1024))
        test_file = f.name
    
    try:
        result = real_upload_manager.upload_file(test_file)
        assert result is True, "Large file upload failed"
        
        s3_key = real_upload_manager._build_s3_key(Path(test_file))
        s3_cleanup(s3_key)
        
        # Verify in S3
        response = real_s3_client.head_object(
            Bucket=aws_config['bucket'],
            Key=s3_key
        )
        
        assert response['ContentLength'] == 10 * 1024 * 1024
        print(f"✓ Multipart upload successful: {s3_key}")
        
    finally:
        Path(test_file).unlink(missing_ok=True)


@pytest.mark.e2e
@pytest.mark.real_aws
def test_list_bucket(real_s3_client, aws_config):
    """Test listing real bucket contents"""
    response = real_s3_client.list_objects_v2(
        Bucket=aws_config['bucket'],
        MaxKeys=10
    )
    
    assert 'ResponseMetadata' in response
    assert response['ResponseMetadata']['HTTPStatusCode'] == 200
    
    if 'Contents' in response:
        print(f"✓ Bucket {aws_config['bucket']} contains {len(response['Contents'])} objects")
    else:
        print(f"✓ Bucket {aws_config['bucket']} is empty")


@pytest.mark.e2e
@pytest.mark.real_aws
def test_verify_upload(real_upload_manager, real_s3_client, s3_cleanup, aws_config):
    """Test upload verification"""
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.log') as f:
        f.write('verification test')
        test_file = f.name
    
    try:
        # Upload
        result = real_upload_manager.upload_file(test_file)
        assert result is True
        
        # Verify using manager's method
        s3_key = real_upload_manager._build_s3_key(Path(test_file))
        s3_cleanup(s3_key)
        
        verified = real_upload_manager.verify_upload(test_file)
        assert verified is True, "Upload verification failed"
        
        print(f"✓ Upload verified in S3")
        
    finally:
        Path(test_file).unlink(missing_ok=True)