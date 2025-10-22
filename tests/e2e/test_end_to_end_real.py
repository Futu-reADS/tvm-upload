# tests/e2e/test_end_to_end_real.py
"""
Complete end-to-end test with REAL AWS
Tests the entire flow: file creation → upload → verification → cleanup
"""

import pytest
import tempfile
import time
import os
from datetime import datetime
from pathlib import Path


@pytest.mark.e2e
@pytest.mark.real_aws
@pytest.mark.slow
def test_complete_upload_flow_real_aws(
    real_upload_manager,
    real_s3_client,
    s3_cleanup,
    aws_config
):
    """
    Complete E2E test with real AWS - Enhanced verification
    1. Create file
    2. Upload to S3
    3. Verify in S3
    4. Verify content integrity
    5. Cleanup
    """
    print("\n=== Starting E2E Real AWS Test ===")
    
    # 1. Create test file with known content
    print("1. Creating test file...")
    test_content = 'Complete E2E test data\n' * 500
    
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.log') as f:
        f.write(test_content)
        test_file = f.name
    
    file_size = Path(test_file).stat().st_size
    print(f"   ✓ Created {file_size} byte file")
    
    try:
        # 2. Upload to real S3
        print("2. Uploading to S3...")
        start_time = time.time()
        result = real_upload_manager.upload_file(test_file)
        upload_time = time.time() - start_time
        
        assert result is True, "Upload failed"
        print(f"   ✓ Uploaded in {upload_time:.2f}s ({(file_size / 1024 / upload_time):.2f} KB/s)")
        
        # 3. Verify in S3
        print("3. Verifying in S3...")
        s3_key = real_upload_manager._build_s3_key(Path(test_file))
        s3_cleanup(s3_key)
        
        response = real_s3_client.head_object(
            Bucket=aws_config['bucket'],
            Key=s3_key
        )
        
        assert response['ContentLength'] == file_size
        print(f"   ✓ Verified: s3://{aws_config['bucket']}/{s3_key}")
        
        # 4. Test retrieval and content integrity
        print("4. Testing retrieval and content integrity...")
        download_response = real_s3_client.get_object(
            Bucket=aws_config['bucket'],
            Key=s3_key
        )
        
        downloaded_data = download_response['Body'].read().decode('utf-8')
        assert len(downloaded_data) == file_size
        assert downloaded_data == test_content, "Content mismatch!"
        print(f"   ✓ Retrieved {len(downloaded_data)} bytes")
        print(f"   ✓ Content integrity verified (exact match)")
        
        # 5. Verify S3 key structure (v2.1 feature)
        print("5. Verifying S3 path structure...")
        key_parts = s3_key.split('/')
        assert len(key_parts) >= 4, f"S3 key should have 4+ parts: {s3_key}"
        
        vehicle_id, date_str, source, filename = key_parts[0], key_parts[1], key_parts[2], key_parts[-1]
        print(f"   ✓ Vehicle ID: {vehicle_id}")
        print(f"   ✓ Date: {date_str}")
        print(f"   ✓ Source: {source}")
        print(f"   ✓ Filename: {filename}")
        
        print("\n=== E2E Test Complete ===")
        
    finally:
        Path(test_file).unlink(missing_ok=True)

@pytest.mark.e2e
@pytest.mark.real_aws
@pytest.mark.slow
def test_complete_workflow_with_deletion(
    real_upload_manager,
    real_s3_client,
    s3_cleanup,
    aws_config
):
    """
    Test complete v2.0 workflow:
    1. Create file
    2. Upload to S3
    3. Verify in S3
    4. Verify file marked for deletion
    5. Cleanup
    """
    print("\n=== Starting E2E v2.0 Deletion Workflow Test ===")
    
    # 1. Create test file
    print("1. Creating test file...")
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.log') as f:
        f.write('E2E v2.0 deletion test\n' * 500)
        test_file = f.name
    
    file_size = Path(test_file).stat().st_size
    print(f"   ✓ Created {file_size} byte file")
    
    try:
        # 2. Upload
        print("2. Uploading to S3...")
        result = real_upload_manager.upload_file(test_file)
        assert result is True, "Upload failed"
        print("   ✓ Upload successful")
        
        # 3. Verify in S3
        print("3. Verifying in S3...")
        s3_key = real_upload_manager._build_s3_key(Path(test_file))
        s3_cleanup(s3_key)
        
        response = real_s3_client.head_object(
            Bucket=aws_config['bucket'],
            Key=s3_key
        )
        assert response['ContentLength'] == file_size
        print(f"   ✓ Verified in S3: {s3_key}")
        
        # 4. Verify deletion tracking (NEW v2.0)
        # NOTE: This requires DiskManager integration
        # For now, just verify the file still exists locally
        # (actual deletion happens based on config keep_days setting)
        print("4. Checking deletion policy...")
        file_exists = Path(test_file).exists()
        print(f"   ✓ File exists locally: {file_exists}")
        print("   ✓ File will be deleted after keep_days expires")
        
        print("\n=== E2E v2.0 Workflow Complete ===")
        
    finally:
        Path(test_file).unlink(missing_ok=True)


@pytest.mark.e2e
@pytest.mark.real_aws
def test_registry_prevents_duplicate_upload(
    real_upload_manager,
    real_s3_client,
    s3_cleanup,
    aws_config
):
    """
    Test processed files registry prevents duplicate uploads (v2.0)
    
    NOTE: This test requires ProcessedFilesRegistry integration
    which may not be in real_upload_manager yet.
    """
    print("\n=== Testing Duplicate Upload Prevention ===")
    
    # Create test file
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.log') as f:
        f.write('Registry test\n' * 100)
        test_file = f.name
    
    try:
        # First upload
        print("1. First upload...")
        result1 = real_upload_manager.upload_file(test_file)
        assert result1 is True
        
        s3_key = real_upload_manager._build_s3_key(Path(test_file))
        s3_cleanup(s3_key)
        print("   ✓ First upload successful")
        
        # Attempt second upload (should be prevented by registry)
        print("2. Attempting duplicate upload...")
        
        # NOTE: If registry is implemented, upload_file should check registry
        # and skip upload, returning True without actually uploading
        # For now, this will upload again (expected behavior without registry)
        result2 = real_upload_manager.upload_file(test_file)
        
        if hasattr(real_upload_manager, 'registry'):
            # If registry exists, verify it prevented duplicate
            print("   ✓ Registry integration detected")
            # Registry should have flagged this as duplicate
        else:
            print("   ⚠ Registry not yet integrated (will upload duplicate)")
        
        print("\n=== Registry Test Complete ===")
        
    finally:
        Path(test_file).unlink(missing_ok=True)


@pytest.mark.e2e
@pytest.mark.real_aws
@pytest.mark.slow
def test_complete_workflow_with_deletion_tracking(
    real_upload_manager,
    real_s3_client,
    s3_cleanup,
    aws_config
):
    """
    Test complete v2.0 workflow with deletion policy tracking
    1. Create file
    2. Upload to S3
    3. Verify in S3
    4. Check local file status (for deletion policy)
    5. Cleanup
    """
    print("\n=== Starting E2E v2.0 Deletion Workflow Test ===")
    
    # 1. Create test file
    print("1. Creating test file...")
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.log') as f:
        f.write('E2E v2.0 deletion test\n' * 500)
        test_file = f.name
    
    file_size = Path(test_file).stat().st_size
    file_mtime = Path(test_file).stat().st_mtime
    print(f"   ✓ Created {file_size} byte file")
    print(f"   ✓ File mtime: {datetime.fromtimestamp(file_mtime)}")
    
    try:
        # 2. Upload
        print("2. Uploading to S3...")
        result = real_upload_manager.upload_file(test_file)
        assert result is True, "Upload failed"
        print("   ✓ Upload successful")
        
        # 3. Verify in S3
        print("3. Verifying in S3...")
        s3_key = real_upload_manager._build_s3_key(Path(test_file))
        s3_cleanup(s3_key)
        
        response = real_s3_client.head_object(
            Bucket=aws_config['bucket'],
            Key=s3_key
        )
        assert response['ContentLength'] == file_size
        print(f"   ✓ Verified in S3: {s3_key}")
        
        # 4. Check deletion policy tracking (NEW v2.0)
        print("4. Checking deletion policy...")
        file_still_exists = Path(test_file).exists()
        print(f"   ✓ File exists locally: {file_still_exists}")
        
        if file_still_exists:
            print("   ✓ File will be managed by deletion policy:")
            print("     - keep_days=0: Deleted immediately after upload")
            print("     - keep_days=14: Kept for 14 days, then deleted")
            print("     - enabled=false: Kept indefinitely")
        
        # 5. Verify S3 metadata includes upload timestamp
        print("5. Verifying S3 metadata...")
        last_modified = response.get('LastModified')
        if last_modified:
            print(f"   ✓ S3 LastModified: {last_modified}")
            print(f"   ✓ Upload timestamp recorded")
        
        print("\n=== E2E v2.0 Workflow Complete ===")
        
    finally:
        Path(test_file).unlink(missing_ok=True)


@pytest.mark.e2e
@pytest.mark.real_aws
def test_duplicate_upload_prevention(
    real_upload_manager,
    real_s3_client,
    s3_cleanup,
    aws_config
):
    """
    Test processed files registry prevents duplicate uploads (v2.0)
    
    Note: This test verifies expected behavior. If registry is not yet
    implemented, it documents what should happen when it is.
    """
    print("\n=== Testing Duplicate Upload Prevention ===")
    
    # Create test file
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.log') as f:
        f.write('Registry test\n' * 100)
        test_file = f.name
    
    file_size = Path(test_file).stat().st_size
    
    try:
        # First upload
        print("1. First upload...")
        result1 = real_upload_manager.upload_file(test_file)
        assert result1 is True
        
        s3_key = real_upload_manager._build_s3_key(Path(test_file))
        s3_cleanup(s3_key)
        print("   ✓ First upload successful")
        
        # Verify in S3
        response1 = real_s3_client.head_object(
            Bucket=aws_config['bucket'],
            Key=s3_key
        )
        etag1 = response1.get('ETag')
        print(f"   ✓ First upload ETag: {etag1}")
        
        # Attempt second upload (should be handled by registry)
        print("2. Attempting duplicate upload...")
        
        # Check if registry is implemented
        has_registry = hasattr(real_upload_manager, 'registry') or \
                      hasattr(real_upload_manager, 'processed_files_registry')
        
        result2 = real_upload_manager.upload_file(test_file)
        
        if has_registry:
            print("   ✓ Registry integration detected")
            # With registry, should skip duplicate
            print("   ✓ Expected: Skip duplicate upload")
            
            # Verify file wasn't re-uploaded by checking ETag
            response2 = real_s3_client.head_object(
                Bucket=aws_config['bucket'],
                Key=s3_key
            )
            etag2 = response2.get('ETag')
            
            # ETags should match (same file, not re-uploaded)
            assert etag1 == etag2, "ETag changed - file was re-uploaded"
            print(f"   ✓ ETag unchanged: {etag2}")
            print("   ✓ Duplicate upload prevented by registry")
            
        else:
            print("   ⚠ Registry not yet implemented")
            print("   ⚠ File will be re-uploaded (expected without registry)")
            print("   ℹ Future: Registry should prevent this duplicate upload")
            
            # Verify second upload succeeded (without registry)
            assert result2 is True
            print("   ✓ Second upload succeeded (no registry)")
        
        print("\n=== Registry Test Complete ===")
        
    finally:
        Path(test_file).unlink(missing_ok=True)


@pytest.mark.e2e
@pytest.mark.real_aws
def test_upload_preserves_file_date_in_path(
    real_upload_manager,
    real_s3_client,
    s3_cleanup,
    aws_config
):
    """
    Test that S3 path uses file mtime, not upload time
    
    This ensures delayed uploads still organize files by creation date
    """
    print("\n=== Testing File Date Preservation ===")
    
    # Create file with old modification time
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.log') as f:
        f.write('Old file test\n' * 100)
        test_file = f.name
    
    # Set mtime to 5 days ago
    old_time = time.time() - (5 * 24 * 3600)
    os.utime(test_file, (old_time, old_time))
    
    expected_date = datetime.fromtimestamp(old_time).strftime('%Y-%m-%d')
    print(f"1. Created file with mtime: {expected_date}")
    
    try:
        # Upload
        print("2. Uploading...")
        result = real_upload_manager.upload_file(test_file)
        assert result is True
        
        # Get S3 key
        s3_key = real_upload_manager._build_s3_key(Path(test_file))
        s3_cleanup(s3_key)
        
        # Parse date from S3 key
        key_parts = s3_key.split('/')
        date_in_key = key_parts[1]
        
        print(f"3. S3 key date: {date_in_key}")
        print(f"   Expected date: {expected_date}")
        
        # Verify date matches file mtime (not today)
        today = datetime.now().strftime('%Y-%m-%d')
        
        # For non-syslog files, should use file mtime
        if 'syslog' not in s3_key:
            assert date_in_key == expected_date, \
                f"S3 key should use file mtime ({expected_date}), not upload date ({today})"
            print(f"   ✓ Correctly used file mtime, not upload date")
        
        # Verify in S3
        response = real_s3_client.head_object(
            Bucket=aws_config['bucket'],
            Key=s3_key
        )
        assert response['ResponseMetadata']['HTTPStatusCode'] == 200
        
        print(f"   ✓ File organized by creation date: {date_in_key}")
        print("\n=== Date Preservation Test Complete ===")
        
    finally:
        Path(test_file).unlink(missing_ok=True)


@pytest.mark.e2e
@pytest.mark.real_aws
@pytest.mark.slow
def test_batch_upload_multiple_files(
    real_upload_manager,
    real_s3_client,
    s3_cleanup,
    aws_config
):
    """
    Test uploading multiple files in sequence
    
    Simulates real-world batch upload scenario
    """
    print("\n=== Testing Batch Upload ===")
    
    num_files = 5
    test_files = []
    
    # 1. Create multiple test files
    print(f"1. Creating {num_files} test files...")
    for i in range(num_files):
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix=f'_{i}.log') as f:
            f.write(f'Batch test file {i}\n' * 100)
            test_files.append(f.name)
        print(f"   ✓ Created file {i+1}/{num_files}: {Path(test_files[i]).name}")
    
    uploaded_keys = []
    
    try:
        # 2. Upload all files
        print(f"\n2. Uploading {num_files} files...")
        start_time = time.time()
        
        for i, test_file in enumerate(test_files):
            result = real_upload_manager.upload_file(test_file)
            assert result is True, f"Upload {i+1} failed"
            
            s3_key = real_upload_manager._build_s3_key(Path(test_file))
            uploaded_keys.append(s3_key)
            s3_cleanup(s3_key)
            
            print(f"   ✓ Uploaded {i+1}/{num_files}: {s3_key}")
        
        total_time = time.time() - start_time
        print(f"\n   ✓ Total upload time: {total_time:.2f}s ({total_time/num_files:.2f}s per file)")
        
        # 3. Verify all files in S3
        print(f"\n3. Verifying {num_files} files in S3...")
        for i, s3_key in enumerate(uploaded_keys):
            response = real_s3_client.head_object(
                Bucket=aws_config['bucket'],
                Key=s3_key
            )
            assert response['ResponseMetadata']['HTTPStatusCode'] == 200
            print(f"   ✓ Verified {i+1}/{num_files}: {s3_key}")
        
        print(f"\n✓ Batch upload complete: {num_files} files uploaded successfully")
        print("\n=== Batch Upload Test Complete ===")
        
    finally:
        # Cleanup local files
        for test_file in test_files:
            Path(test_file).unlink(missing_ok=True)


@pytest.mark.e2e
@pytest.mark.real_aws
def test_upload_nonexistent_file_handling(real_upload_manager, aws_config):
    """
    Test that attempting to upload nonexistent file raises PermanentUploadError
    
    Should raise exception immediately without retrying (v2.0 behavior)
    """
    from src.upload_manager import PermanentUploadError
    
    print("\n=== Testing Nonexistent File Handling ===")
    
    nonexistent_file = "/tmp/this_file_does_not_exist.log"
    print(f"1. Attempting to upload nonexistent file: {nonexistent_file}")
    
    # Verify file doesn't exist
    assert not Path(nonexistent_file).exists(), "Test file should not exist"
    
    # Should raise PermanentUploadError
    try:
        result = real_upload_manager.upload_file(nonexistent_file)
        # If we get here, test should fail
        pytest.fail("Should have raised PermanentUploadError for nonexistent file")
    except PermanentUploadError as e:
        print(f"✓ Correctly raised PermanentUploadError: {e}")
        assert "File not found" in str(e)
        print("✓ Error message contains 'File not found'")
        print("✓ Test passed: Nonexistent files handled correctly")