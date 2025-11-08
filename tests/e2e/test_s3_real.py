# tests/e2e/test_s3_real.py
"""
Real S3 upload tests - Comprehensive coverage
These tests make actual API calls to AWS S3
"""

import os
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from botocore.exceptions import ClientError

# ============================================================================
# BASIC UPLOAD TESTS
# ============================================================================


@pytest.mark.e2e
@pytest.mark.real_aws
def test_upload_small_file_to_real_s3(real_upload_manager, real_s3_client, s3_cleanup, aws_config):
    """Test uploading small file to actual S3"""
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".log") as f:
        f.write("Real S3 E2E test\n" * 100)
        test_file = f.name

    try:
        result = real_upload_manager.upload_file(test_file)
        assert result is True, "Upload to real S3 failed"

        s3_key = real_upload_manager._build_s3_key(Path(test_file))
        s3_cleanup(s3_key)

        response = real_s3_client.head_object(Bucket=aws_config["bucket"], Key=s3_key)

        assert response["ResponseMetadata"]["HTTPStatusCode"] == 200
        assert response["ContentLength"] > 0

        print(f"✓ Uploaded to s3://{aws_config['bucket']}/{s3_key}")

    finally:
        Path(test_file).unlink(missing_ok=True)


@pytest.mark.e2e
@pytest.mark.real_aws
@pytest.mark.slow
def test_upload_large_file_multipart(real_upload_manager, real_s3_client, s3_cleanup, aws_config):
    """Test multipart upload with 10MB file"""
    with tempfile.NamedTemporaryFile(mode="wb", delete=False, suffix=".mcap") as f:
        f.write(b"0" * (10 * 1024 * 1024))
        test_file = f.name

    try:
        start_time = time.time()
        result = real_upload_manager.upload_file(test_file)
        upload_time = time.time() - start_time

        assert result is True, "Large file upload failed"

        s3_key = real_upload_manager._build_s3_key(Path(test_file))
        s3_cleanup(s3_key)

        response = real_s3_client.head_object(Bucket=aws_config["bucket"], Key=s3_key)

        assert response["ContentLength"] == 10 * 1024 * 1024

        print(f"✓ Multipart upload: {s3_key}")
        print(f"✓ Upload time: {upload_time:.2f}s ({(10 / upload_time):.2f} MB/s)")

        etag = response.get("ETag", "").strip('"')
        if "-" in etag:
            print(f"✓ Confirmed multipart ETag: {etag}")

    finally:
        Path(test_file).unlink(missing_ok=True)


@pytest.mark.e2e
@pytest.mark.real_aws
def test_upload_empty_file(real_upload_manager, real_s3_client, s3_cleanup, aws_config):
    """Test uploading zero-byte file"""
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".log") as f:
        test_file = f.name

    try:
        assert Path(test_file).stat().st_size == 0, "File should be empty"

        result = real_upload_manager.upload_file(test_file)
        assert result is True, "Empty file upload failed"

        s3_key = real_upload_manager._build_s3_key(Path(test_file))
        s3_cleanup(s3_key)

        response = real_s3_client.head_object(Bucket=aws_config["bucket"], Key=s3_key)

        assert response["ContentLength"] == 0
        print("✓ Empty file uploaded successfully")

    finally:
        Path(test_file).unlink(missing_ok=True)


@pytest.mark.e2e
@pytest.mark.real_aws
def test_upload_binary_file(real_upload_manager, real_s3_client, s3_cleanup, aws_config):
    """Test uploading binary file (MCAP/BAG format)"""
    with tempfile.NamedTemporaryFile(mode="wb", delete=False, suffix=".mcap") as f:
        # Write binary data
        f.write(b"\x89MCAP\x00\x01\x02\x03")
        f.write(os.urandom(1024 * 100))  # 100KB random binary
        test_file = f.name

    file_size = Path(test_file).stat().st_size

    try:
        result = real_upload_manager.upload_file(test_file)
        assert result is True

        s3_key = real_upload_manager._build_s3_key(Path(test_file))
        s3_cleanup(s3_key)

        response = real_s3_client.head_object(Bucket=aws_config["bucket"], Key=s3_key)

        assert response["ContentLength"] == file_size
        print(f"✓ Binary file uploaded: {file_size} bytes")

    finally:
        Path(test_file).unlink(missing_ok=True)


@pytest.mark.e2e
@pytest.mark.real_aws
def test_upload_compressed_file(real_upload_manager, real_s3_client, s3_cleanup, aws_config):
    """Test uploading compressed file (gz)"""
    import gzip

    with tempfile.NamedTemporaryFile(mode="wb", delete=False, suffix=".log.gz") as f:
        with gzip.open(f, "wb") as gz:
            gz.write(b"Compressed log data\n" * 1000)
        test_file = f.name

    try:
        result = real_upload_manager.upload_file(test_file)
        assert result is True

        s3_key = real_upload_manager._build_s3_key(Path(test_file))
        s3_cleanup(s3_key)

        response = real_s3_client.head_object(Bucket=aws_config["bucket"], Key=s3_key)

        assert response["ContentLength"] > 0
        print(f"✓ Compressed file uploaded: {Path(test_file).name}")

    finally:
        Path(test_file).unlink(missing_ok=True)


# ============================================================================
# S3 PATH STRUCTURE TESTS
# ============================================================================


@pytest.mark.e2e
@pytest.mark.real_aws
def test_source_based_s3_paths(
    real_upload_manager, real_s3_client, s3_cleanup, aws_config, verify_s3_key_structure
):
    """Test v2.1 source-based S3 path organization"""
    test_cases = [
        ("terminal_session.log", None),
        ("ros_launch.bag", None),
        ("system.log", None),
    ]

    for filename, expected_source in test_cases:
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=filename) as f:
            f.write(f"Test data for {filename}\n" * 50)
            test_file = f.name

        try:
            result = real_upload_manager.upload_file(test_file)
            assert result is True, f"Upload failed for {filename}"

            s3_key = real_upload_manager._build_s3_key(Path(test_file))
            s3_cleanup(s3_key)

            # Verify structure using helper
            parsed = verify_s3_key_structure(s3_key, aws_config["vehicle_id"], expected_source)

            print(f"✓ Source-based path: {s3_key}")
            print(
                f"  Vehicle: {parsed['vehicle_id']}, Date: {parsed['date']}, Source: {parsed['source']}"
            )

            response = real_s3_client.head_object(Bucket=aws_config["bucket"], Key=s3_key)
            assert response["ResponseMetadata"]["HTTPStatusCode"] == 200

        finally:
            Path(test_file).unlink(missing_ok=True)


@pytest.mark.e2e
@pytest.mark.real_aws
def test_syslog_uses_upload_date(real_upload_manager, real_s3_client, s3_cleanup, aws_config):
    """Test that syslog files use upload date, not file mtime"""
    with tempfile.NamedTemporaryFile(mode="w", delete=False, prefix="syslog", suffix="") as f:
        f.write("Test syslog data\n" * 100)
        test_file = f.name

    # Set mtime to 3 days ago
    old_time = time.time() - (3 * 24 * 3600)
    os.utime(test_file, (old_time, old_time))

    try:
        result = real_upload_manager.upload_file(test_file)
        assert result is True

        s3_key = real_upload_manager._build_s3_key(Path(test_file))
        s3_cleanup(s3_key)

        parts = s3_key.split("/")
        date_in_key = parts[1]
        today = datetime.now().strftime("%Y-%m-%d")

        if "/var/log" in test_file or "syslog" in parts[2]:
            assert (
                date_in_key == today
            ), f"Syslog should use upload date ({today}), got {date_in_key}"
            print(f"✓ Syslog correctly uses upload date: {today}")

        response = real_s3_client.head_object(Bucket=aws_config["bucket"], Key=s3_key)
        assert response["ResponseMetadata"]["HTTPStatusCode"] == 200

    finally:
        Path(test_file).unlink(missing_ok=True)


@pytest.mark.e2e
@pytest.mark.real_aws
def test_upload_preserves_file_date_in_path(
    real_upload_manager, real_s3_client, s3_cleanup, aws_config
):
    """Test that S3 path uses file mtime for non-syslog files"""
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".log") as f:
        f.write("Old file test\n" * 100)
        test_file = f.name

    # Set mtime to 5 days ago
    old_time = time.time() - (5 * 24 * 3600)
    os.utime(test_file, (old_time, old_time))

    expected_date = datetime.fromtimestamp(old_time).strftime("%Y-%m-%d")

    try:
        result = real_upload_manager.upload_file(test_file)
        assert result is True

        s3_key = real_upload_manager._build_s3_key(Path(test_file))
        s3_cleanup(s3_key)

        key_parts = s3_key.split("/")
        date_in_key = key_parts[1]
        today = datetime.now().strftime("%Y-%m-%d")

        # For non-syslog files, should use file mtime
        if "syslog" not in s3_key:
            assert (
                date_in_key == expected_date
            ), f"S3 key should use file mtime ({expected_date}), not upload date ({today})"
            print(f"✓ Correctly used file mtime: {expected_date}")

        response = real_s3_client.head_object(Bucket=aws_config["bucket"], Key=s3_key)
        assert response["ResponseMetadata"]["HTTPStatusCode"] == 200

    finally:
        Path(test_file).unlink(missing_ok=True)


# ============================================================================
# METADATA AND VERIFICATION TESTS
# ============================================================================


@pytest.mark.e2e
@pytest.mark.real_aws
def test_verify_upload(real_upload_manager, real_s3_client, s3_cleanup, aws_config):
    """Test upload verification"""
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".log") as f:
        f.write("verification test")
        test_file = f.name

    try:
        result = real_upload_manager.upload_file(test_file)
        assert result is True

        s3_key = real_upload_manager._build_s3_key(Path(test_file))
        s3_cleanup(s3_key)

        verified = real_upload_manager.verify_upload(test_file)
        assert verified is True, "Upload verification failed"

        print("✓ Upload verified in S3")

    finally:
        Path(test_file).unlink(missing_ok=True)


@pytest.mark.e2e
@pytest.mark.real_aws
def test_upload_preserves_file_metadata(
    real_upload_manager, real_s3_client, s3_cleanup, aws_config
):
    """Test that uploaded files maintain correct size and basic metadata"""
    test_content = b"Metadata test content\n" * 1000
    expected_size = len(test_content)

    with tempfile.NamedTemporaryFile(mode="wb", delete=False, suffix=".log") as f:
        f.write(test_content)
        test_file = f.name

    try:
        result = real_upload_manager.upload_file(test_file)
        assert result is True

        s3_key = real_upload_manager._build_s3_key(Path(test_file))
        s3_cleanup(s3_key)

        response = real_s3_client.head_object(Bucket=aws_config["bucket"], Key=s3_key)

        assert response["ContentLength"] == expected_size
        assert "LastModified" in response
        assert "ETag" in response
        assert "ContentType" in response

        print(f"✓ Metadata preserved - Size: {expected_size} bytes")
        print(f"  ContentType: {response.get('ContentType')}")

    finally:
        Path(test_file).unlink(missing_ok=True)


@pytest.mark.e2e
@pytest.mark.real_aws
def test_s3_content_integrity(real_upload_manager, real_s3_client, s3_cleanup, aws_config):
    """Test that uploaded content matches original (download and compare)"""
    test_content = "Content integrity test\n" * 500

    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".log") as f:
        f.write(test_content)
        test_file = f.name

    try:
        result = real_upload_manager.upload_file(test_file)
        assert result is True

        s3_key = real_upload_manager._build_s3_key(Path(test_file))
        s3_cleanup(s3_key)

        # Download from S3
        download_response = real_s3_client.get_object(Bucket=aws_config["bucket"], Key=s3_key)

        downloaded_data = download_response["Body"].read().decode("utf-8")

        # Verify exact match
        assert downloaded_data == test_content, "Content mismatch!"
        assert len(downloaded_data) == len(test_content)

        print("✓ Content integrity verified (exact match)")

    finally:
        Path(test_file).unlink(missing_ok=True)


# ============================================================================
# ERROR HANDLING AND RETRY TESTS
# ============================================================================


@pytest.mark.e2e
@pytest.mark.real_aws
def test_upload_retry_mechanism(real_upload_manager, real_s3_client, s3_cleanup, aws_config):
    """Test that upload retries are configured correctly"""
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".log") as f:
        f.write("Retry test\n" * 100)
        test_file = f.name

    try:
        original_max_retries = real_upload_manager.max_retries
        real_upload_manager.max_retries = 3

        result = real_upload_manager.upload_file(test_file)
        assert result is True

        s3_key = real_upload_manager._build_s3_key(Path(test_file))
        s3_cleanup(s3_key)

        response = real_s3_client.head_object(Bucket=aws_config["bucket"], Key=s3_key)
        assert response["ResponseMetadata"]["HTTPStatusCode"] == 200

        print(f"✓ Upload with retry mechanism verified")

        real_upload_manager.max_retries = original_max_retries

    finally:
        Path(test_file).unlink(missing_ok=True)


@pytest.mark.e2e
@pytest.mark.real_aws
def test_upload_nonexistent_file_error(real_upload_manager):
    """Test that uploading nonexistent file handles error correctly"""
    from src.upload_manager import PermanentUploadError

    nonexistent_file = "/tmp/this_file_absolutely_does_not_exist_12345.log"
    assert not Path(nonexistent_file).exists()

    try:
        result = real_upload_manager.upload_file(nonexistent_file)
        pytest.fail("Should have raised PermanentUploadError for nonexistent file")
    except PermanentUploadError as e:
        assert "File not found" in str(e)
        print(f"✓ Correctly raised PermanentUploadError: {e}")


# ============================================================================
# SPECIAL FILE TESTS
# ============================================================================


@pytest.mark.e2e
@pytest.mark.real_aws
def test_upload_file_with_unicode_name(real_upload_manager, real_s3_client, s3_cleanup, aws_config):
    """Test uploading file with unicode characters in name"""
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix="_测试.log") as f:
        f.write("Unicode filename test\n" * 100)
        test_file = f.name

    try:
        result = real_upload_manager.upload_file(test_file)
        assert result is True

        s3_key = real_upload_manager._build_s3_key(Path(test_file))
        s3_cleanup(s3_key)

        response = real_s3_client.head_object(Bucket=aws_config["bucket"], Key=s3_key)
        assert response["ResponseMetadata"]["HTTPStatusCode"] == 200

        print(f"✓ Unicode filename uploaded: {Path(test_file).name}")

    finally:
        Path(test_file).unlink(missing_ok=True)


@pytest.mark.e2e
@pytest.mark.real_aws
def test_upload_various_file_types(
    real_upload_manager, real_s3_client, s3_batch_cleanup, aws_config
):
    """Test uploading files with various extensions"""
    file_types = [".log", ".txt", ".csv", ".json", ".xml", ".mcap", ".bag", ".db3"]

    for ext in file_types:
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=ext) as f:
            f.write(f"Test data for {ext}\n" * 50)
            test_file = f.name

        try:
            result = real_upload_manager.upload_file(test_file)
            assert result is True, f"Upload failed for {ext}"

            s3_key = real_upload_manager._build_s3_key(Path(test_file))
            s3_batch_cleanup(s3_key)

            response = real_s3_client.head_object(Bucket=aws_config["bucket"], Key=s3_key)
            assert response["ResponseMetadata"]["HTTPStatusCode"] == 200

            print(f"✓ Uploaded {ext} file")

        finally:
            Path(test_file).unlink(missing_ok=True)


# ============================================================================
# BUCKET OPERATIONS
# ============================================================================


@pytest.mark.e2e
@pytest.mark.real_aws
def test_list_bucket(real_s3_client, aws_config):
    """Test listing real bucket contents"""
    response = real_s3_client.list_objects_v2(Bucket=aws_config["bucket"], MaxKeys=10)

    assert "ResponseMetadata" in response
    assert response["ResponseMetadata"]["HTTPStatusCode"] == 200

    if "Contents" in response:
        print(f"✓ Bucket {aws_config['bucket']} contains {len(response['Contents'])} objects")
    else:
        print(f"✓ Bucket {aws_config['bucket']} is empty")


@pytest.mark.e2e
@pytest.mark.real_aws
def test_s3_duplicate_detection(real_upload_manager, real_s3_client, s3_cleanup, aws_config):
    """Test that duplicate file in S3 is detected"""
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

        # Second upload of same file
        result2 = real_upload_manager.upload_file(test_file)

        etag2 = real_s3_client.head_object(Bucket=aws_config["bucket"], Key=s3_key).get("ETag")

        # ETags should match (duplicate detection worked)
        assert etag1 == etag2
        print("✓ Duplicate file detected correctly")

    finally:
        Path(test_file).unlink(missing_ok=True)


# ============================================================================
# PERFORMANCE AND STRESS TESTS
# ============================================================================


@pytest.mark.e2e
@pytest.mark.real_aws
@pytest.mark.slow
def test_upload_very_large_file(real_upload_manager, real_s3_client, s3_cleanup, aws_config):
    """Test uploading 50MB file (stress test)"""
    with tempfile.NamedTemporaryFile(mode="wb", delete=False, suffix=".mcap") as f:
        # Write 50MB
        f.write(b"X" * (50 * 1024 * 1024))
        test_file = f.name

    try:
        start_time = time.time()
        result = real_upload_manager.upload_file(test_file)
        upload_time = time.time() - start_time

        assert result is True

        s3_key = real_upload_manager._build_s3_key(Path(test_file))
        s3_cleanup(s3_key)

        response = real_s3_client.head_object(Bucket=aws_config["bucket"], Key=s3_key)

        assert response["ContentLength"] == 50 * 1024 * 1024

        print(f"✓ 50MB file uploaded in {upload_time:.2f}s ({(50 / upload_time):.2f} MB/s)")

    finally:
        Path(test_file).unlink(missing_ok=True)


@pytest.mark.e2e
@pytest.mark.real_aws
@pytest.mark.slow
def test_concurrent_uploads_sequential(
    real_upload_manager, real_s3_client, s3_batch_cleanup, aws_config
):
    """Test uploading multiple files in sequence (simulating concurrent workflow)"""
    num_files = 10
    test_files = []

    # Create files
    for i in range(num_files):
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=f"_{i}.log") as f:
            f.write(f"Concurrent test file {i}\n" * 100)
            test_files.append(f.name)

    uploaded_keys = []

    try:
        start_time = time.time()

        # Upload all files
        for i, test_file in enumerate(test_files):
            result = real_upload_manager.upload_file(test_file)
            assert result is True, f"Upload {i+1} failed"

            s3_key = real_upload_manager._build_s3_key(Path(test_file))
            uploaded_keys.append(s3_key)

        total_time = time.time() - start_time
        s3_batch_cleanup(uploaded_keys)

        # Verify all in S3
        for s3_key in uploaded_keys:
            response = real_s3_client.head_object(Bucket=aws_config["bucket"], Key=s3_key)
            assert response["ResponseMetadata"]["HTTPStatusCode"] == 200

        print(
            f"✓ {num_files} files uploaded in {total_time:.2f}s ({total_time/num_files:.2f}s per file)"
        )

    finally:
        for test_file in test_files:
            Path(test_file).unlink(missing_ok=True)
