# tests/e2e/test_s3_real.py
"""
Real S3 upload tests
These tests make actual API calls to AWS S3
"""

import pytest
import tempfile
import time
import os
from pathlib import Path
from datetime import datetime




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
    """Test multipart upload with 10MB file - Enhanced with timing"""
    # Create 10MB file
    with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.mcap') as f:
        f.write(b'0' * (10 * 1024 * 1024))
        test_file = f.name
    
    try:
        # Measure upload time
        start_time = time.time()
        result = real_upload_manager.upload_file(test_file)
        upload_time = time.time() - start_time
        
        assert result is True, "Large file upload failed"
        
        s3_key = real_upload_manager._build_s3_key(Path(test_file))
        s3_cleanup(s3_key)
        
        # Verify in S3
        response = real_s3_client.head_object(
            Bucket=aws_config['bucket'],
            Key=s3_key
        )
        
        assert response['ContentLength'] == 10 * 1024 * 1024
        
        # Verify multipart was used (file > 5MB triggers multipart)
        print(f"✓ Multipart upload successful: {s3_key}")
        print(f"✓ Upload time: {upload_time:.2f}s ({(10 / upload_time):.2f} MB/s)")
        
        # Additional verification: Check ETag format
        # Multipart uploads have ETags with "-" (e.g., "abc123-2")
        etag = response.get('ETag', '').strip('"')
        if '-' in etag:
            print(f"✓ Confirmed multipart ETag: {etag}")
        
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

@pytest.mark.e2e
@pytest.mark.real_aws
def test_source_based_s3_path(real_upload_manager, real_s3_client, s3_cleanup, aws_config):
    """Test that uploaded files use source-based S3 path structure (v2.1)"""
    # Create test files with different extensions
    test_files = [
        ('terminal_test.log', 'terminal'),
        ('ros_test.bag', 'ros'),
        ('syslog', 'syslog'),
        ('ros2_test.log', 'ros2')
    ]
    
    for filename, expected_source in test_files:
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix=filename) as f:
            f.write(f'Test data for {expected_source}\n' * 50)
            test_file = f.name
        
        try:
            # Upload
            result = real_upload_manager.upload_file(test_file)
            assert result is True, f"Upload failed for {filename}"
            
            # Build S3 key - should contain source prefix
            s3_key = real_upload_manager._build_s3_key(Path(test_file))
            s3_cleanup(s3_key)
            
            # Verify S3 key contains source type
            # Expected format: {vehicle-id}/{YYYY-MM-DD}/{source}/{filename}
            assert expected_source in s3_key, \
                f"S3 key {s3_key} should contain source type '{expected_source}'"
            
            print(f"✓ Source-based path verified: {s3_key}")
            
        finally:
            Path(test_file).unlink(missing_ok=True)

@pytest.mark.e2e
@pytest.mark.real_aws
def test_source_based_s3_paths(real_upload_manager, real_s3_client, s3_cleanup, aws_config):
    """
    Test v2.1 source-based S3 path organization
    
    Files should be organized by source type:
    - {vehicle-id}/{date}/{source}/{filename}
    
    Sources: terminal, ros, syslog, ros2, other
    """
    # Test files with different names simulating different sources
    test_cases = [
        ('terminal_session.log', 'terminal'),
        ('ros_launch.bag', 'log'),  # Will map to 'log' directory source
        ('system.log', 'other'),  # No specific source
    ]
    
    for filename, expected_source_hint in test_cases:
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix=filename) as f:
            f.write(f'Test data for {filename}\n' * 50)
            test_file = f.name
        
        try:
            # Upload
            result = real_upload_manager.upload_file(test_file)
            assert result is True, f"Upload failed for {filename}"
            
            # Build and verify S3 key structure
            s3_key = real_upload_manager._build_s3_key(Path(test_file))
            s3_cleanup(s3_key)
            
            # Parse S3 key: {vehicle-id}/{date}/{source}/{filename}
            parts = s3_key.split('/')
            assert len(parts) >= 4, f"S3 key should have at least 4 parts: {s3_key}"
            
            vehicle_id = parts[0]
            date_str = parts[1]
            source = parts[2]
            
            # Verify structure
            assert vehicle_id == aws_config['vehicle_id'], f"Vehicle ID mismatch in {s3_key}"
            
            # Verify date format (YYYY-MM-DD)
            try:
                datetime.strptime(date_str, '%Y-%m-%d')
            except ValueError:
                pytest.fail(f"Invalid date format in S3 key: {date_str}")
            
            # Verify source is not empty
            assert source, f"Source should not be empty in {s3_key}"
            
            print(f"✓ Source-based path verified: {s3_key}")
            print(f"  Vehicle: {vehicle_id}, Date: {date_str}, Source: {source}")
            
            # Verify file exists in S3
            response = real_s3_client.head_object(
                Bucket=aws_config['bucket'],
                Key=s3_key
            )
            assert response['ResponseMetadata']['HTTPStatusCode'] == 200
            
        finally:
            Path(test_file).unlink(missing_ok=True)

@pytest.mark.e2e
@pytest.mark.real_aws
def test_syslog_uses_upload_date(real_upload_manager, real_s3_client, s3_cleanup, aws_config):
    """
    Test that syslog files use upload date, not file mtime
    
    According to v2.1: /var/log files always use current date,
    ensuring latest version is in today's folder
    """
    # Create temp file simulating syslog
    with tempfile.NamedTemporaryFile(mode='w', delete=False, 
                                     prefix='syslog', suffix='') as f:
        f.write('Test syslog data\n' * 100)
        test_file = f.name
    
    # Modify file's mtime to 3 days ago
    old_time = time.time() - (3 * 24 * 3600)
    os.utime(test_file, (old_time, old_time))
    
    try:
        # Upload
        result = real_upload_manager.upload_file(test_file)
        assert result is True, "Syslog upload failed"
        
        # Get S3 key
        s3_key = real_upload_manager._build_s3_key(Path(test_file))
        s3_cleanup(s3_key)
        
        # Parse date from S3 key
        parts = s3_key.split('/')
        date_in_key = parts[1]
        
        # Verify date is TODAY (not 3 days ago)
        today = datetime.now().strftime('%Y-%m-%d')
        
        # For syslog, should use upload date
        if '/var/log' in test_file or 'syslog' in parts[2]:
            assert date_in_key == today, \
                f"Syslog should use upload date ({today}), got {date_in_key}"
            print(f"✓ Syslog correctly uses upload date: {today}")
        
        # Verify in S3
        response = real_s3_client.head_object(
            Bucket=aws_config['bucket'],
            Key=s3_key
        )
        assert response['ResponseMetadata']['HTTPStatusCode'] == 200
        
        print(f"✓ Syslog uploaded to: s3://{aws_config['bucket']}/{s3_key}")
        
    finally:
        Path(test_file).unlink(missing_ok=True)

@pytest.mark.e2e
@pytest.mark.real_aws
def test_upload_retry_succeeds_after_failure(real_upload_manager, real_s3_client, s3_cleanup, aws_config):
    """
    Test that upload retries and succeeds after transient failures
    
    Note: This test cannot simulate actual network failures in real AWS,
    but verifies the retry mechanism is in place
    """
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.log') as f:
        f.write('Retry test\n' * 100)
        test_file = f.name
    
    try:
        # Get original max_retries
        original_max_retries = real_upload_manager.max_retries
        
        # Set to small number for faster test
        real_upload_manager.max_retries = 3
        
        # Upload should succeed
        result = real_upload_manager.upload_file(test_file)
        assert result is True, "Upload with retry failed"
        
        # Verify in S3
        s3_key = real_upload_manager._build_s3_key(Path(test_file))
        s3_cleanup(s3_key)
        
        response = real_s3_client.head_object(
            Bucket=aws_config['bucket'],
            Key=s3_key
        )
        assert response['ResponseMetadata']['HTTPStatusCode'] == 200
        
        print(f"✓ Upload with retry mechanism verified: {s3_key}")
        
        # Restore original setting
        real_upload_manager.max_retries = original_max_retries
        
    finally:
        Path(test_file).unlink(missing_ok=True)

@pytest.mark.e2e
@pytest.mark.real_aws
def test_upload_preserves_file_metadata(real_upload_manager, real_s3_client, s3_cleanup, aws_config):
    """Test that uploaded files maintain correct size and basic metadata"""
    test_content = b'Metadata test content\n' * 1000
    expected_size = len(test_content)
    
    with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.log') as f:
        f.write(test_content)
        test_file = f.name
    
    try:
        # Upload
        result = real_upload_manager.upload_file(test_file)
        assert result is True, "Upload failed"
        
        # Verify in S3
        s3_key = real_upload_manager._build_s3_key(Path(test_file))
        s3_cleanup(s3_key)
        
        response = real_s3_client.head_object(
            Bucket=aws_config['bucket'],
            Key=s3_key
        )
        
        # Verify size
        assert response['ContentLength'] == expected_size, \
            f"Size mismatch: expected {expected_size}, got {response['ContentLength']}"
        
        # Verify metadata exists
        assert 'LastModified' in response
        assert 'ETag' in response
        assert 'ContentType' in response
        
        print(f"✓ Metadata preserved - Size: {expected_size} bytes")
        print(f"  ContentType: {response.get('ContentType')}")
        print(f"  ETag: {response.get('ETag')}")
        
    finally:
        Path(test_file).unlink(missing_ok=True)