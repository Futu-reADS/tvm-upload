#!/usr/bin/env python3
"""
Upload Manager for TVM Log Upload System
Handles S3 uploads with retry logic

Provides robust file upload to S3 with exponential backoff retry,
multipart upload support for large files, and upload verification.
"""

import boto3
import time
import logging
from pathlib import Path
from typing import List
from datetime import datetime, timedelta
from botocore.exceptions import ClientError, BotoCoreError

logger = logging.getLogger(__name__)

class UploadError(Exception):
    """
    Raised when upload fails after all retries.
    
    This exception indicates that the file could not be uploaded
    even after the maximum number of retry attempts.
    """
    pass

class PermanentUploadError(Exception):
    """
    Raised when upload fails due to permanent error (won't resolve by retrying).
    
    Examples:
    - File not found
    - File permission denied
    - File corrupted (disk read error)
    - Invalid AWS credentials
    - Bucket doesn't exist
    - IAM permissions denied
    
    These errors require manual intervention and won't be resolved by retrying.
    """
    pass


class UploadManager:
    """
    Manages file uploads to S3 with retry logic.
    
    Features:
    - Exponential backoff retry (1, 2, 4, 8... up to 512 seconds)
    - Automatic multipart upload for files >5MB
    - S3 key generation: {vehicle-id}/{YYYY-MM-DD}/{filename}
    - Upload verification
    
    Example:
        >>> uploader = UploadManager(
        ...     bucket='tvm-logs',
        ...     region='cn-north-1',
        ...     vehicle_id='vehicle-001'
        ... )
        >>> success = uploader.upload_file('/var/log/test.log')
        >>> if success:
        ...     print("Upload successful")
    
    Attributes:
        bucket (str): S3 bucket name
        region (str): AWS region
        vehicle_id (str): Vehicle identifier for S3 key prefix
        max_retries (int): Maximum retry attempts
        s3_client: Boto3 S3 client
    """
    
    def __init__(self, bucket: str, region: str, vehicle_id: str, 
             max_retries: int = 10, profile_name: str = None,
             log_directories: List[str] = None):
        """
        Initialize upload manager.
        
        Args:
            bucket: S3 bucket name
            region: AWS region (e.g., 'cn-north-1', 'us-east-1')
            vehicle_id: Vehicle identifier for S3 prefix
            max_retries: Maximum retry attempts (default: 10)
            profile_name: AWS profile name (default: None uses default profile)
            log_directories: List of monitored directories (for source detection)
        """
        self.bucket = bucket
        self.region = region
        self.vehicle_id = vehicle_id
        self.max_retries = max_retries
        self.log_directories = log_directories or []  # ← NEW LINE
        
        # Initialize S3 client with China endpoint support
        import os
        
        # Check for LocalStack (testing)
        endpoint_url = os.getenv('AWS_ENDPOINT_URL')
        
        # Prepare boto3 client kwargs
        client_kwargs = {'region_name': region}
        import boto3.session
        # Add profile if specified
        if profile_name:
            session = boto3.session.Session(profile_name=profile_name)
            logger.info(f"Using AWS profile: {profile_name}")
        else:
            session = boto3.session.Session()
        
        if endpoint_url:
            logger.info(f"Using custom endpoint: {endpoint_url}")
            client_kwargs['endpoint_url'] = endpoint_url
            client_kwargs['aws_access_key_id'] = os.getenv('AWS_ACCESS_KEY_ID', 'test')
            client_kwargs['aws_secret_access_key'] = os.getenv('AWS_SECRET_ACCESS_KEY', 'test')
            self.s3_client = session.client('s3', **client_kwargs)
        elif region.startswith('cn-'):
            # AWS China uses different endpoints
            logger.info(f"Using AWS China endpoint for region: {region}")
            client_kwargs['endpoint_url'] = f'https://s3.{region}.amazonaws.com.cn'
            self.s3_client = session.client('s3', **client_kwargs)
        else:
            # Standard AWS regions
            self.s3_client = session.client('s3', **client_kwargs)
        
        logger.info(f"Initialized for bucket: {bucket}")
        logger.info(f"Vehicle ID: {vehicle_id}")
        logger.info(f"Max retries: {max_retries}")
    
    def upload_file(self, local_path: str) -> bool:
        """
        Upload file to S3 with retry logic and error classification.
        
        Attempts upload with exponential backoff on temporary failures.
        Raises exception for permanent failures (file issues, credentials).
        Automatically uses multipart upload for files larger than 5MB.
        
        Args:
            local_path: Path to local file
            
        Returns:
            bool: True if upload succeeded, False if failed after all retries
            
        Raises:
            PermanentUploadError: For errors that won't resolve by retrying
                (file not found, permission denied, corrupted file, invalid credentials)
                
        Note:
            Logs detailed progress including attempt number and errors.
            Permanent errors should be caught by caller and file removed from queue.
        """
        file_path = Path(local_path)
        
        # ===== PRE-FLIGHT CHECKS (Permanent Errors) =====
        
        # Check 1: File exists
        if not file_path.exists():
            logger.error(f"File not found: {local_path}")
            raise PermanentUploadError(f"File not found: {local_path}")
        
        # Check 2: File is readable
        try:
            with open(file_path, 'rb') as f:
                # Try reading first byte to ensure file is readable
                f.read(1)
        except PermissionError as e:
            logger.error(f"Permission denied: {local_path}")
            raise PermanentUploadError(f"Permission denied: {local_path}")
        except OSError as e:
            # Disk read errors (bad sectors, I/O errors)
            logger.error(f"Disk read error for {file_path.name}: {e}")
            raise PermanentUploadError(f"Disk read error: {e}")
        
        # Check 3: File size (S3 limit is 5TB)
        try:
            file_size = file_path.stat().st_size
            if file_size > 5 * 1024 * 1024 * 1024 * 1024:  # 5TB
                logger.error(f"File too large: {file_size / (1024**4):.2f} TB (max 5TB)")
                raise PermanentUploadError(f"File exceeds S3 5TB limit")
        except OSError as e:
            logger.error(f"Cannot stat file: {e}")
            raise PermanentUploadError(f"Cannot access file: {e}")
        
        # Build S3 key
        s3_key = self._build_s3_key(file_path)

        # Check if file already exists in S3
        if self.verify_upload(local_path):
            logger.info(f"File already in S3, skipping: {file_path.name}")
            return True
        
        # ===== UPLOAD WITH RETRY (Temporary Errors) =====
        
        for attempt in range(1, self.max_retries + 1):
            try:
                logger.info(f"Uploading {file_path.name} (attempt {attempt}/{self.max_retries})")
                
                if file_size > 5 * 1024 * 1024:
                    # Use multipart upload for large files (>5MB)
                    self._multipart_upload(str(file_path), s3_key)
                else:
                    # Simple upload for small files
                    self.s3_client.upload_file(str(file_path), self.bucket, s3_key)
                
                logger.info(f"SUCCESS: {file_path.name} -> s3://{self.bucket}/{s3_key}")
                return True
                
            except ClientError as e:
                error_code = e.response.get('Error', {}).get('Code', '')
                error_message = e.response.get('Error', {}).get('Message', str(e))
                
                # ===== CLASSIFY AWS ERRORS =====
                
                # Permanent Errors (Credentials/Permissions)
                if error_code in ['InvalidAccessKeyId', 'SignatureDoesNotMatch']:
                    logger.error(f"PERMANENT ERROR: Invalid AWS credentials ({error_code})")
                    raise PermanentUploadError(f"Invalid AWS credentials: {error_code}")
                
                elif error_code == 'NoSuchBucket':
                    logger.error(f"PERMANENT ERROR: Bucket '{self.bucket}' does not exist")
                    raise PermanentUploadError(f"Bucket does not exist: {self.bucket}")
                
                elif error_code == 'AccessDenied':
                    logger.error(f"PERMANENT ERROR: Access denied - check IAM permissions")
                    raise PermanentUploadError(f"IAM permissions denied for bucket {self.bucket}")
                
                elif error_code == 'EntityTooLarge':
                    logger.error(f"PERMANENT ERROR: File too large for S3")
                    raise PermanentUploadError("File size exceeds S3 limits")
                
                # Temporary Errors (Network/Service) - RETRY
                else:
                    logger.warning(f"Upload failed (attempt {attempt}): {error_code} - {error_message}")
                    
                    if attempt < self.max_retries:
                        delay = self._calculate_backoff(attempt)
                        logger.info(f"Retrying in {delay} seconds...")
                        time.sleep(delay)
                    else:
                        logger.error(f"Max retries exceeded for {file_path.name}")
                        return False  # Temporary failure, caller should retry later
            
            except FileNotFoundError:
                # File deleted during upload
                logger.error(f"File disappeared during upload: {file_path.name}")
                raise PermanentUploadError(f"File deleted during upload: {local_path}")
            
            except BotoCoreError as e:
                # Network/connection errors (temporary)
                logger.warning(f"Network error (attempt {attempt}): {e}")
                
                if attempt < self.max_retries:
                    delay = self._calculate_backoff(attempt)
                    logger.info(f"Retrying in {delay} seconds...")
                    time.sleep(delay)
                else:
                    logger.error(f"Max retries exceeded (network error)")
                    return False  # Temporary failure
            
            except Exception as e:
                # Unexpected errors
                logger.error(f"Unexpected error during upload: {e}")
                import traceback
                logger.debug(traceback.format_exc())
                return False
        
        return False
    
    def _build_s3_key(self, file_path: Path) -> str:
        """
        Build S3 key with source-based organization.
        
        Format: {vehicle-id}/{date}/{source}/{relative-path}
        
        Source Detection:
        - Matches file path against configured log_directories
        - Uses directory name as source (e.g., 'terminal', 'log', 'rosLog')
        - Special case: /var/log → 'syslog' (always uses upload date, not file mtime)
        
        Date Logic:
        - Normal files: Use file modification time (handles delayed uploads)
        - Syslog files: Use current date (always latest version in today's folder)
        
        Folder Structure:
        - Preserves full folder structure relative to monitored directory
        - Example: /home/autoware/.ros/log/run-123/launch.log
        -       → vehicle-001/2025-10-20/log/run-123/launch.log
        
        Args:
            file_path: Local file path
            
        Returns:
            str: S3 object key
            
        Examples:
            Config: log_directories: ["/home/autoware/.parcel/log/terminal"]
            File: /home/autoware/.parcel/log/terminal/session.log
            Result: vehicle-001/2025-10-20/terminal/session.log
            
            Config: log_directories: ["/home/autoware/.ros/log"]
            File: /home/autoware/.ros/log/run-123/launch.log
            Result: vehicle-001/2025-10-20/log/run-123/launch.log
            
            Config: log_directories: ["/var/log"]
            File: /var/log/syslog (modified 3 days ago)
            Result: vehicle-001/2025-10-21/syslog/syslog (uses TODAY, not file mtime)
        """
        file_str = str(file_path.resolve())
        
        # Special case: /var/log (syslog) - ALWAYS use upload date, not file mtime
        if file_str.startswith('/var/log'):
            date_str = datetime.now().strftime("%Y-%m-%d")  # Current date
            source = 'syslog'
            relative_path = file_path.name  # Just filename
            
            logger.debug(
                f"Syslog file detected, using upload date: {file_path.name} "
                f"→ {date_str}/syslog/{relative_path}"
            )
        
        else:
            # Normal files: Use file modification time for date
            try:
                mtime = file_path.stat().st_mtime
                date_str = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")
            except (OSError, FileNotFoundError):
                # Fallback to current date if file stat fails
                date_str = datetime.now().strftime("%Y-%m-%d")
                logger.warning(f"Cannot get mtime for {file_path}, using current date")
            
            # Match file against configured directories
            source = None
            relative_path = None
            
            # Get configured directories from config
            for log_dir in self.log_directories:
                log_dir_resolved = str(Path(log_dir).resolve())
                
                # Check if file is under this directory
                if file_str.startswith(log_dir_resolved):
                    # Extract source name from directory path
                    # Use the last component of the directory path as source
                    # Example: /home/autoware/.ros/log → 'log'
                    #          /home/autoware/.parcel/log/terminal → 'terminal'
                    source = Path(log_dir).name
                    
                    # Get relative path from monitored directory
                    # Preserves full folder structure
                    try:
                        relative_path = str(file_path.relative_to(log_dir_resolved))
                    except ValueError:
                        # Shouldn't happen, but fallback to filename
                        relative_path = file_path.name
                    
                    logger.debug(
                        f"Matched directory: {log_dir} → source='{source}', "
                        f"relative='{relative_path}'"
                    )
                    break
            
            # Fallback if no match found
            if source is None:
                source = 'other'
                relative_path = file_path.name
                logger.warning(
                    f"File not under any configured log_directory: {file_path}"
                )
        
        # Build final S3 key
        s3_key = f"{self.vehicle_id}/{date_str}/{source}/{relative_path}"
        
        logger.debug(f"Built S3 key: {file_path.name} → {s3_key}")
        
        return s3_key
    
    def _calculate_backoff(self, attempt: int) -> int:
        """
        Calculate exponential backoff delay.
        
        Uses formula: min(2^(attempt-1), 512)
        Sequence: 1, 2, 4, 8, 16, 32, 64, 128, 256, 512, 512...
        
        Args:
            attempt: Current attempt number (1-based)
            
        Returns:
            int: Delay in seconds (max 512)
            
        Examples:
            >>> _calculate_backoff(1)  # 1 second
            >>> _calculate_backoff(5)  # 16 seconds
            >>> _calculate_backoff(10) # 512 seconds (capped)
        """
        # Exponential backoff: 1, 2, 4, 8, 16, 32, 64, 128, 256, 512
        delay = min(2 ** (attempt - 1), 512)
        return delay
    
    def _multipart_upload(self, file_path: str, s3_key: str):
        """
        Upload large file using multipart upload.
        
        Splits file into 5MB chunks and uploads them in parallel.
        Boto3 handles the multipart API calls automatically.
        
        Args:
            file_path: Local file path
            s3_key: S3 object key
            
        Note:
            Uses boto3's high-level transfer configuration
        """
        # For simplicity, use boto3's upload_file which handles multipart automatically
        self.s3_client.upload_file(
            file_path, 
            self.bucket, 
            s3_key,
            Config=boto3.s3.transfer.TransferConfig(
                multipart_threshold=5 * 1024 * 1024,
                multipart_chunksize=5 * 1024 * 1024
            )
        )
    
    def verify_upload(self, local_path: str) -> bool:
        """
        Verify that THIS specific file (same content) exists in S3.
        
        Checks by comparing file size across multiple date paths.
        Now uses source-based S3 structure.
        
        Args:
            local_path: Local file path
            
        Returns:
            bool: True if this exact file already exists in S3, False otherwise
        """
        file_path = Path(local_path)
        
        try:
            local_size = file_path.stat().st_size
            local_mtime = file_path.stat().st_mtime
        except (OSError, FileNotFoundError):
            return False
        
        # Check using file's actual modification date first (most likely match)
        s3_key = self._build_s3_key(file_path)  # Uses mtime internally
        try:
            response = self.s3_client.head_object(Bucket=self.bucket, Key=s3_key)
            s3_size = response['ContentLength']
            
            if s3_size == local_size:
                logger.info(f"File already in S3 (same size: {local_size} bytes), skipping: {file_path.name}")
                return True
            else:
                logger.debug(f"S3 key exists but different size (local: {local_size}, S3: {s3_size})")
                return False
                
        except ClientError as e:
            if e.response['Error']['Code'] != '404':
                logger.debug(f"S3 check error: {e}")
            pass
        
        # Check previous 30 days (file might have been uploaded with wrong date)
        # Special case: Skip date checking for syslog (always uses current date)
        file_str = str(file_path.resolve())
        if file_str.startswith('/var/log'):
            # Syslog uses upload date, so no need to check other dates
            logger.debug(f"Syslog file not found in S3 for today: {file_path.name}")
            return False
        
        # For non-syslog files, check ±5 days around file mtime
        base_date = datetime.fromtimestamp(local_mtime)
        
        for days_offset in range(-5, 6):  # Check ±5 days around file mtime
            if days_offset == 0:
                continue  # Already checked above
            
            check_date = base_date + timedelta(days=days_offset)
            date_str = check_date.strftime("%Y-%m-%d")
            
            # Rebuild S3 key with different date
            # Extract source and relative_path from original key
            original_parts = s3_key.split('/', 3)  # [vehicle_id, date, source, relative_path]
            if len(original_parts) >= 4:
                vehicle_id, _, source, relative_path = original_parts
                alternate_key = f"{vehicle_id}/{date_str}/{source}/{relative_path}"
                
                try:
                    response = self.s3_client.head_object(Bucket=self.bucket, Key=alternate_key)
                    s3_size = response['ContentLength']
                    
                    if s3_size == local_size:
                        logger.info(
                            f"File already in S3 ({days_offset:+d} days offset, same size), "
                            f"skipping: {file_path.name}"
                        )
                        return True
                        
                except ClientError:
                    continue
        
        # File not found in S3 (or all found files have different sizes)
        logger.debug(f"File not found in S3 or different content: {file_path.name}")
        return False


if __name__ == '__main__':
    import sys
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    if len(sys.argv) < 2:
        logger.error("Usage: python upload_manager.py <file_path>")
        sys.exit(1)
    
    # Test with local credentials
    uploader = UploadManager(
        bucket="tvm-logs-test",
        region="us-east-1",
        vehicle_id="vehicle-test"
    )
    
    result = uploader.upload_file(sys.argv[1])
    
    if result:
        logger.info("Upload successful!")
        sys.exit(0)
    else:
        logger.error("Upload failed!")
        sys.exit(1)