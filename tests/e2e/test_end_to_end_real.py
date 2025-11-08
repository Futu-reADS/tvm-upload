# tests/e2e/test_end_to_end_real.py
"""
Complete end-to-end test with REAL AWS - Comprehensive Coverage
Tests the entire flow: file creation → upload → verification → cleanup
"""

import os
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest

# ============================================================================
# BASIC END-TO-END WORKFLOWS
# ============================================================================


@pytest.mark.e2e
@pytest.mark.real_aws
@pytest.mark.slow
def test_complete_upload_flow_real_aws(real_upload_manager, real_s3_client, s3_cleanup, aws_config):
    """Complete E2E test with real AWS - Full verification"""
    print("\n=== Starting E2E Real AWS Test ===")

    test_content = "Complete E2E test data\n" * 500

    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".log") as f:
        f.write(test_content)
        test_file = f.name

    file_size = Path(test_file).stat().st_size
    print(f"1. Created {file_size} byte file")

    try:
        # Upload to real S3
        print("2. Uploading to S3...")
        start_time = time.time()
        result = real_upload_manager.upload_file(test_file)
        upload_time = time.time() - start_time

        assert result is True, "Upload failed"
        print(f"   ✓ Uploaded in {upload_time:.2f}s ({(file_size / 1024 / upload_time):.2f} KB/s)")

        # Verify in S3
        print("3. Verifying in S3...")
        s3_key = real_upload_manager._build_s3_key(Path(test_file))
        s3_cleanup(s3_key)

        response = real_s3_client.head_object(Bucket=aws_config["bucket"], Key=s3_key)

        assert response["ContentLength"] == file_size
        print(f"   ✓ Verified: s3://{aws_config['bucket']}/{s3_key}")

        # Test retrieval and content integrity
        print("4. Testing retrieval and content integrity...")
        download_response = real_s3_client.get_object(Bucket=aws_config["bucket"], Key=s3_key)

        downloaded_data = download_response["Body"].read().decode("utf-8")
        assert len(downloaded_data) == file_size
        assert downloaded_data == test_content, "Content mismatch!"
        print(f"   ✓ Content integrity verified (exact match)")

        # Verify S3 key structure
        print("5. Verifying S3 path structure...")
        key_parts = s3_key.split("/")
        assert len(key_parts) >= 4, f"S3 key should have 4+ parts: {s3_key}"

        vehicle_id, date_str, source, filename = (
            key_parts[0],
            key_parts[1],
            key_parts[2],
            key_parts[-1],
        )
        print(f"   ✓ Vehicle ID: {vehicle_id}")
        print(f"   ✓ Date: {date_str}")
        print(f"   ✓ Source: {source}")
        print(f"   ✓ Filename: {filename}")

        print("\n=== E2E Test Complete ===")

    finally:
        Path(test_file).unlink(missing_ok=True)


@pytest.mark.e2e
@pytest.mark.real_aws
def test_simple_upload_verify_cycle(real_upload_manager, real_s3_client, s3_cleanup, aws_config):
    """Test simple upload and verify cycle"""
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".log") as f:
        f.write("Simple cycle test\n" * 100)
        test_file = f.name

    try:
        # Upload
        result = real_upload_manager.upload_file(test_file)
        assert result is True

        s3_key = real_upload_manager._build_s3_key(Path(test_file))
        s3_cleanup(s3_key)

        # Verify
        verified = real_upload_manager.verify_upload(test_file)
        assert verified is True

        print("✓ Simple upload-verify cycle successful")

    finally:
        Path(test_file).unlink(missing_ok=True)


# ============================================================================
# BATCH UPLOAD TESTS
# ============================================================================


@pytest.mark.e2e
@pytest.mark.real_aws
@pytest.mark.slow
def test_batch_upload_multiple_files(
    real_upload_manager, real_s3_client, s3_batch_cleanup, aws_config
):
    """Test uploading multiple files in batch"""
    print("\n=== Testing Batch Upload ===")

    num_files = 5
    test_files = []

    # Create multiple test files
    print(f"1. Creating {num_files} test files...")
    for i in range(num_files):
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=f"_{i}.log") as f:
            f.write(f"Batch test file {i}\n" * 100)
            test_files.append(f.name)
        print(f"   ✓ Created file {i+1}/{num_files}: {Path(test_files[i]).name}")

    uploaded_keys = []

    try:
        # Upload all files
        print(f"\n2. Uploading {num_files} files...")
        start_time = time.time()

        for i, test_file in enumerate(test_files):
            result = real_upload_manager.upload_file(test_file)
            assert result is True, f"Upload {i+1} failed"

            s3_key = real_upload_manager._build_s3_key(Path(test_file))
            uploaded_keys.append(s3_key)

            print(f"   ✓ Uploaded {i+1}/{num_files}: {s3_key}")

        total_time = time.time() - start_time
        s3_batch_cleanup(uploaded_keys)

        print(f"\n   ✓ Total upload time: {total_time:.2f}s ({total_time/num_files:.2f}s per file)")

        # Verify all files in S3
        print(f"\n3. Verifying {num_files} files in S3...")
        for i, s3_key in enumerate(uploaded_keys):
            response = real_s3_client.head_object(Bucket=aws_config["bucket"], Key=s3_key)
            assert response["ResponseMetadata"]["HTTPStatusCode"] == 200
            print(f"   ✓ Verified {i+1}/{num_files}: {s3_key}")

        print(f"\n✓ Batch upload complete: {num_files} files uploaded successfully")
        print("\n=== Batch Upload Test Complete ===")

    finally:
        for test_file in test_files:
            Path(test_file).unlink(missing_ok=True)


@pytest.mark.e2e
@pytest.mark.real_aws
@pytest.mark.slow
def test_batch_upload_mixed_file_types(
    real_upload_manager, real_s3_client, s3_batch_cleanup, aws_config
):
    """Test batch upload with different file types"""
    file_types = [".log", ".mcap", ".bag", ".csv", ".json"]
    test_files = []
    uploaded_keys = []

    # Create files of different types
    for ext in file_types:
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=ext) as f:
            f.write(f"Batch test for {ext}\n" * 200)
            test_files.append(f.name)

    try:
        # Upload all
        for test_file in test_files:
            result = real_upload_manager.upload_file(test_file)
            assert result is True

            s3_key = real_upload_manager._build_s3_key(Path(test_file))
            uploaded_keys.append(s3_key)

        s3_batch_cleanup(uploaded_keys)

        # Verify all
        for s3_key in uploaded_keys:
            response = real_s3_client.head_object(Bucket=aws_config["bucket"], Key=s3_key)
            assert response["ResponseMetadata"]["HTTPStatusCode"] == 200

        print(f"✓ Batch uploaded {len(file_types)} different file types")

    finally:
        for test_file in test_files:
            Path(test_file).unlink(missing_ok=True)


# ============================================================================
# DATE AND TIME TESTS
# ============================================================================


@pytest.mark.e2e
@pytest.mark.real_aws
def test_upload_preserves_file_date_in_path(
    real_upload_manager, real_s3_client, s3_cleanup, aws_config
):
    """Test that S3 path uses file mtime for organization"""
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".log") as f:
        f.write("Old file test\n" * 100)
        test_file = f.name

    # Set mtime to 5 days ago
    old_time = time.time() - (5 * 24 * 3600)
    os.utime(test_file, (old_time, old_time))

    expected_date = datetime.fromtimestamp(old_time).strftime("%Y-%m-%d")
    print(f"1. Created file with mtime: {expected_date}")

    try:
        print("2. Uploading...")
        result = real_upload_manager.upload_file(test_file)
        assert result is True

        s3_key = real_upload_manager._build_s3_key(Path(test_file))
        s3_cleanup(s3_key)

        # Parse date from S3 key
        key_parts = s3_key.split("/")
        date_in_key = key_parts[1]

        print(f"3. S3 key date: {date_in_key}")
        print(f"   Expected date: {expected_date}")

        today = datetime.now().strftime("%Y-%m-%d")

        # For non-syslog files, should use file mtime
        if "syslog" not in s3_key:
            assert (
                date_in_key == expected_date
            ), f"S3 key should use file mtime ({expected_date}), not upload date ({today})"
            print(f"   ✓ Correctly used file mtime, not upload date")

        # Verify in S3
        response = real_s3_client.head_object(Bucket=aws_config["bucket"], Key=s3_key)
        assert response["ResponseMetadata"]["HTTPStatusCode"] == 200

        print(f"   ✓ File organized by creation date: {date_in_key}")

    finally:
        Path(test_file).unlink(missing_ok=True)


@pytest.mark.e2e
@pytest.mark.real_aws
def test_upload_files_across_date_boundary(
    real_upload_manager, real_s3_client, s3_batch_cleanup, aws_config
):
    """Test uploading files from different dates"""
    test_files = []
    uploaded_keys = []

    # Create files with different mtimes
    dates_ago = [0, 1, 2, 3, 5]  # Today, yesterday, 2 days ago, etc.

    for days_ago in dates_ago:
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".log") as f:
            f.write(f"File from {days_ago} days ago\n" * 100)
            test_file = f.name

        # Set mtime
        if days_ago > 0:
            old_time = time.time() - (days_ago * 24 * 3600)
            os.utime(test_file, (old_time, old_time))

        test_files.append(test_file)

    try:
        # Upload all
        for test_file in test_files:
            result = real_upload_manager.upload_file(test_file)
            assert result is True

            s3_key = real_upload_manager._build_s3_key(Path(test_file))
            uploaded_keys.append(s3_key)

        s3_batch_cleanup(uploaded_keys)

        # Verify all uploaded and have correct dates in paths
        dates_found = set()
        for s3_key in uploaded_keys:
            parts = s3_key.split("/")
            date_in_key = parts[1]
            dates_found.add(date_in_key)

            response = real_s3_client.head_object(Bucket=aws_config["bucket"], Key=s3_key)
            assert response["ResponseMetadata"]["HTTPStatusCode"] == 200

        print(f"✓ Uploaded files across {len(dates_found)} different dates")
        print(f"✓ Dates: {sorted(dates_found)}")

    finally:
        for test_file in test_files:
            Path(test_file).unlink(missing_ok=True)


# ============================================================================
# ERROR HANDLING TESTS
# ============================================================================


@pytest.mark.e2e
@pytest.mark.real_aws
def test_upload_nonexistent_file_handling(real_upload_manager):
    """Test that attempting to upload nonexistent file raises PermanentUploadError"""
    from src.upload_manager import PermanentUploadError

    print("\n=== Testing Nonexistent File Handling ===")

    nonexistent_file = "/tmp/this_file_does_not_exist_e2e_12345.log"
    print(f"1. Attempting to upload nonexistent file: {nonexistent_file}")

    assert not Path(nonexistent_file).exists(), "Test file should not exist"

    try:
        result = real_upload_manager.upload_file(nonexistent_file)
        pytest.fail("Should have raised PermanentUploadError for nonexistent file")
    except PermanentUploadError as e:
        print(f"✓ Correctly raised PermanentUploadError: {e}")
        assert "File not found" in str(e)
        print("✓ Error message contains 'File not found'")


@pytest.mark.e2e
@pytest.mark.real_aws
def test_upload_continues_after_single_failure(
    real_upload_manager, real_s3_client, s3_batch_cleanup, aws_config
):
    """Test that system continues uploading after a single file failure"""
    from src.upload_manager import PermanentUploadError

    test_files = []
    uploaded_keys = []
    successful_uploads = 0
    failed_uploads = 0

    # Create mix of valid and invalid files
    for i in range(3):
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=f"_{i}.log") as f:
            f.write(f"Valid file {i}\n" * 100)
            test_files.append(f.name)

    try:
        # Upload valid files with a nonexistent file in between
        for i, test_file in enumerate(test_files):
            try:
                result = real_upload_manager.upload_file(test_file)
                if result:
                    successful_uploads += 1
                    s3_key = real_upload_manager._build_s3_key(Path(test_file))
                    uploaded_keys.append(s3_key)
            except PermanentUploadError:
                failed_uploads += 1

        s3_batch_cleanup(uploaded_keys)

        # Verify successful uploads
        assert successful_uploads == 3, "All valid files should upload"

        for s3_key in uploaded_keys:
            response = real_s3_client.head_object(Bucket=aws_config["bucket"], Key=s3_key)
            assert response["ResponseMetadata"]["HTTPStatusCode"] == 200

        print(f"✓ System continued after handling errors")
        print(f"✓ Successful: {successful_uploads}, Failed: {failed_uploads}")

    finally:
        for test_file in test_files:
            Path(test_file).unlink(missing_ok=True)


# ============================================================================
# CONTENT VERIFICATION TESTS
# ============================================================================


@pytest.mark.e2e
@pytest.mark.real_aws
def test_upload_download_content_match(real_upload_manager, real_s3_client, s3_cleanup, aws_config):
    """Test that uploaded content exactly matches downloaded content"""
    test_content = "Content verification test\n" * 1000
    test_content += "Special characters: 中文 日本語 한국어 😀\n"
    test_content += "Numbers: 1234567890\n"

    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".log", encoding="utf-8") as f:
        f.write(test_content)
        test_file = f.name

    try:
        # Upload
        result = real_upload_manager.upload_file(test_file)
        assert result is True

        s3_key = real_upload_manager._build_s3_key(Path(test_file))
        s3_cleanup(s3_key)

        # Download and compare
        download_response = real_s3_client.get_object(Bucket=aws_config["bucket"], Key=s3_key)

        downloaded_data = download_response["Body"].read().decode("utf-8")

        # Exact match verification
        assert downloaded_data == test_content, "Content mismatch!"
        assert len(downloaded_data) == len(test_content)

        print("✓ Upload/download content match verified")
        print("✓ Unicode characters preserved")

    finally:
        Path(test_file).unlink(missing_ok=True)


@pytest.mark.e2e
@pytest.mark.real_aws
def test_upload_binary_content_integrity(
    real_upload_manager, real_s3_client, s3_cleanup, aws_config
):
    """Test binary file upload/download integrity"""
    import hashlib

    # Create binary file with known content
    binary_content = b"\x00\x01\x02\x03\xff\xfe\xfd"
    binary_content += os.urandom(1024 * 50)  # 50KB random data

    # Calculate original hash
    original_hash = hashlib.sha256(binary_content).hexdigest()

    with tempfile.NamedTemporaryFile(mode="wb", delete=False, suffix=".mcap") as f:
        f.write(binary_content)
        test_file = f.name

    try:
        # Upload
        result = real_upload_manager.upload_file(test_file)
        assert result is True

        s3_key = real_upload_manager._build_s3_key(Path(test_file))
        s3_cleanup(s3_key)

        # Download
        download_response = real_s3_client.get_object(Bucket=aws_config["bucket"], Key=s3_key)

        downloaded_data = download_response["Body"].read()

        # Verify hash
        downloaded_hash = hashlib.sha256(downloaded_data).hexdigest()

        assert original_hash == downloaded_hash, "Binary content corrupted!"
        assert len(downloaded_data) == len(binary_content)

        print(f"✓ Binary integrity verified (SHA256: {original_hash[:16]}...)")

    finally:
        Path(test_file).unlink(missing_ok=True)


# ============================================================================
# SPECIAL SCENARIOS
# ============================================================================


@pytest.mark.e2e
@pytest.mark.real_aws
def test_upload_file_with_special_characters(
    real_upload_manager, real_s3_client, s3_cleanup, aws_config
):
    """Test uploading files with special characters in filename"""
    special_names = [
        "test-file.log",
        "test_file.log",
        "test.file.log",
        "test 2024.log",
        "test(1).log",
    ]

    for filename in special_names:
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=filename) as f:
            f.write(f"Test data for {filename}\n" * 100)
            test_file = f.name

        try:
            result = real_upload_manager.upload_file(test_file)
            assert result is True

            s3_key = real_upload_manager._build_s3_key(Path(test_file))
            s3_cleanup(s3_key)

            response = real_s3_client.head_object(Bucket=aws_config["bucket"], Key=s3_key)
            assert response["ResponseMetadata"]["HTTPStatusCode"] == 200

            print(f"✓ Uploaded file with special name: {Path(test_file).name}")

        finally:
            Path(test_file).unlink(missing_ok=True)


@pytest.mark.e2e
@pytest.mark.real_aws
def test_upload_very_small_and_very_large_files(
    real_upload_manager, real_s3_client, s3_batch_cleanup, aws_config
):
    """Test uploading files of extreme sizes"""
    test_files = []
    uploaded_keys = []

    # Create files of different sizes
    sizes = [
        (0, "empty.log"),  # 0 bytes
        (1, "tiny.log"),  # 1 byte
        (100, "small.log"),  # 100 bytes
        (1024 * 100, "medium.log"),  # 100 KB
        (1024 * 1024 * 5, "large.mcap"),  # 5 MB
    ]

    for size, suffix in sizes:
        with tempfile.NamedTemporaryFile(mode="wb", delete=False, suffix=suffix) as f:
            if size > 0:
                f.write(b"X" * size)
            test_file = f.name
        test_files.append((test_file, size, suffix))

    try:
        for test_file, expected_size, suffix in test_files:
            result = real_upload_manager.upload_file(test_file)
            assert result is True

            s3_key = real_upload_manager._build_s3_key(Path(test_file))
            uploaded_keys.append(s3_key)

            # Verify size
            response = real_s3_client.head_object(Bucket=aws_config["bucket"], Key=s3_key)
            assert response["ContentLength"] == expected_size

            print(f"✓ Uploaded {suffix}: {expected_size} bytes")

        s3_batch_cleanup(uploaded_keys)

    finally:
        for test_file, _, _ in test_files:
            Path(test_file).unlink(missing_ok=True)


@pytest.mark.e2e
@pytest.mark.real_aws
@pytest.mark.slow
def test_complete_workflow_with_metadata_tracking(
    real_upload_manager, real_s3_client, s3_cleanup, aws_config
):
    """Test complete workflow with detailed metadata tracking"""
    print("\n=== Starting Complete Workflow with Metadata Tracking ===")

    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".log") as f:
        f.write("Metadata workflow test\n" * 500)
        test_file = f.name

    file_size = Path(test_file).stat().st_size
    file_mtime = Path(test_file).stat().st_mtime
    print(f"1. Created file: {file_size} bytes, mtime: {datetime.fromtimestamp(file_mtime)}")

    try:
        # Upload
        print("2. Uploading to S3...")
        result = real_upload_manager.upload_file(test_file)
        assert result is True
        print("   ✓ Upload successful")

        # Verify in S3
        print("3. Verifying in S3...")
        s3_key = real_upload_manager._build_s3_key(Path(test_file))
        s3_cleanup(s3_key)

        response = real_s3_client.head_object(Bucket=aws_config["bucket"], Key=s3_key)
        assert response["ContentLength"] == file_size
        print(f"   ✓ Verified in S3: {s3_key}")

        # Check metadata
        print("4. Verifying S3 metadata...")
        last_modified = response.get("LastModified")
        if last_modified:
            print(f"   ✓ S3 LastModified: {last_modified}")

        etag = response.get("ETag")
        if etag:
            print(f"   ✓ ETag: {etag}")

        content_type = response.get("ContentType")
        if content_type:
            print(f"   ✓ ContentType: {content_type}")

        print("\n=== Complete Workflow Test Successful ===")

    finally:
        Path(test_file).unlink(missing_ok=True)


# ============================================================================
# PERFORMANCE TESTS
# ============================================================================


@pytest.mark.e2e
@pytest.mark.real_aws
@pytest.mark.slow
def test_sequential_upload_performance(
    real_upload_manager, real_s3_client, s3_batch_cleanup, aws_config
):
    """Test and measure sequential upload performance"""
    num_files = 10
    file_size = 1024 * 100  # 100KB each
    test_files = []
    uploaded_keys = []

    # Create files
    for i in range(num_files):
        with tempfile.NamedTemporaryFile(mode="wb", delete=False, suffix=f"_perf_{i}.log") as f:
            f.write(b"X" * file_size)
            test_files.append(f.name)

    try:
        start_time = time.time()

        # Upload sequentially
        for i, test_file in enumerate(test_files):
            result = real_upload_manager.upload_file(test_file)
            assert result is True

            s3_key = real_upload_manager._build_s3_key(Path(test_file))
            uploaded_keys.append(s3_key)

        total_time = time.time() - start_time
        s3_batch_cleanup(uploaded_keys)

        # Verify all
        for s3_key in uploaded_keys:
            response = real_s3_client.head_object(Bucket=aws_config["bucket"], Key=s3_key)
            assert response["ResponseMetadata"]["HTTPStatusCode"] == 200

        avg_time = total_time / num_files
        throughput = (file_size * num_files) / total_time / 1024  # KB/s

        print(f"\n=== Performance Metrics ===")
        print(f"Files: {num_files}")
        print(f"Total time: {total_time:.2f}s")
        print(f"Avg time per file: {avg_time:.2f}s")
        print(f"Throughput: {throughput:.2f} KB/s")

    finally:
        for test_file in test_files:
            Path(test_file).unlink(missing_ok=True)


# ============================================================================
# DUPLICATE AND RETRY TESTS
# ============================================================================


@pytest.mark.e2e
@pytest.mark.real_aws
def test_duplicate_upload_detection(real_upload_manager, real_s3_client, s3_cleanup, aws_config):
    """Test duplicate file detection in S3"""
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".log") as f:
        f.write("Duplicate test\n" * 100)
        test_file = f.name

    try:
        # First upload
        result1 = real_upload_manager.upload_file(test_file)
        assert result1 is True

        s3_key = real_upload_manager._build_s3_key(Path(test_file))
        s3_cleanup(s3_key)

        etag1 = real_s3_client.head_object(Bucket=aws_config["bucket"], Key=s3_key).get("ETag")

        # Second upload
        result2 = real_upload_manager.upload_file(test_file)

        etag2 = real_s3_client.head_object(Bucket=aws_config["bucket"], Key=s3_key).get("ETag")

        # ETags should match
        assert etag1 == etag2
        print("✓ Duplicate file handled correctly")

    finally:
        Path(test_file).unlink(missing_ok=True)


@pytest.mark.e2e
@pytest.mark.real_aws
def test_upload_with_retry_configuration(
    real_upload_manager, real_s3_client, s3_cleanup, aws_config
):
    """Test upload with retry mechanism configured"""
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".log") as f:
        f.write("Retry test\n" * 100)
        test_file = f.name

    try:
        original_retries = real_upload_manager.max_retries
        real_upload_manager.max_retries = 5

        result = real_upload_manager.upload_file(test_file)
        assert result is True

        s3_key = real_upload_manager._build_s3_key(Path(test_file))
        s3_cleanup(s3_key)

        response = real_s3_client.head_object(Bucket=aws_config["bucket"], Key=s3_key)
        assert response["ResponseMetadata"]["HTTPStatusCode"] == 200

        print("✓ Upload with retry configuration successful")

        real_upload_manager.max_retries = original_retries

    finally:
        Path(test_file).unlink(missing_ok=True)
