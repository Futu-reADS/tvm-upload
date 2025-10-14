# tests/e2e/test_end_to_end_real.py
"""
Complete end-to-end test with REAL AWS
Tests the entire flow: file creation → upload → verification → cleanup
"""

import pytest
import tempfile
import time
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
    Complete E2E test with real AWS:
    1. Create file
    2. Upload to S3
    3. Verify in S3
    4. Cleanup
    """
    print("\n=== Starting E2E Real AWS Test ===")
    
    # 1. Create test file
    print("1. Creating test file...")
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.log') as f:
        f.write('Complete E2E test data\n' * 500)
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
        print(f"   ✓ Uploaded in {upload_time:.2f}s")
        
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
        
        # 4. Test retrieval
        print("4. Testing retrieval...")
        download_response = real_s3_client.get_object(
            Bucket=aws_config['bucket'],
            Key=s3_key
        )
        
        downloaded_data = download_response['Body'].read()
        assert len(downloaded_data) == file_size
        print(f"   ✓ Retrieved {len(downloaded_data)} bytes")
        
        print("\n=== E2E Test Complete ===")
        
    finally:
        Path(test_file).unlink(missing_ok=True)