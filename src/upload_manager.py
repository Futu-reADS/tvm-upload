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

# S3 Upload Limits and Configuration
MAX_S3_FILE_SIZE = 5 * 1024**4  # 5 TB (AWS S3 maximum file size)
MULTIPART_THRESHOLD = 5 * 1024**2  # 5 MB (use multipart for files larger than this)
MULTIPART_CHUNK_SIZE = 5 * 1024**2  # 5 MB per chunk for multipart uploads
MD5_READ_CHUNK_SIZE = 8 * 1024**2  # 8 MB chunks for efficient MD5 hash calculation

# S3 Verification Configuration
DATE_SEARCH_RANGE_DAYS = 5  # Check ±5 days around file mtime for delayed uploads (non-syslog)

# MD5 Caching Configuration
MD5_CACHE_TTL_SECONDS = 300  # 5 minutes - cache MD5 hashes to avoid recalculation

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
         log_directories: List = None):
        """
        Initialize upload manager.
        
        Args:
            bucket: S3 bucket name
            region: AWS region (e.g., 'cn-north-1', 'us-east-1')
            vehicle_id: Vehicle identifier for S3 prefix
            max_retries: Maximum retry attempts (default: 10)
            profile_name: AWS profile name (default: None uses default profile)
            log_directories: List of directory configs (dict) or paths (str, legacy)
        
        Raises:
            ValueError: If no valid log directories configured
        """
        self.bucket = bucket
        self.region = region
        self.vehicle_id = vehicle_id
        self.max_retries = max_retries

        # MD5 cache for performance optimization
        # Format: {filepath_str: (md5_hash, mtime, cache_timestamp)}
        self._md5_cache = {}

        # Parse log directories configuration
        # Support both legacy (string list) and new (dict list) formats
        self.log_directory_configs = []
        
        if log_directories:
            for item in log_directories:
                if isinstance(item, str):
                    # Legacy format: ["/path/to/log"]
                    # Auto-detect source from path
                    self.log_directory_configs.append({
                        'path': item,
                        'source': self._guess_source_from_path(item)
                    })
                    logger.warning(
                        f"Using legacy log_directories format for {item}. "
                        f"Auto-detected source: {self._guess_source_from_path(item)}"
                    )
                elif isinstance(item, dict):
                    # New format: [{path: "/path", source: "ros"}]
                    if 'path' not in item or 'source' not in item:
                        logger.error(f"Invalid log directory config: {item}")
                        continue
                    self.log_directory_configs.append(item)
                else:
                    logger.error(f"Unknown log directory format: {item}")
        
        if not self.log_directory_configs:
            error_msg = (
                "No valid log directories configured. "
                "Cannot organize files by source. "
                "Check 'log_directories' in config.yaml - ensure it has valid entries "
                "with both 'path' and 'source' fields."
            )
            logger.error(error_msg)
            raise ValueError(error_msg)  # Fail fast!

        self._validate_directory_paths()
        
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
        logger.info(f"Configured sources: {[c['source'] for c in self.log_directory_configs]}")

    
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
            if file_size > MAX_S3_FILE_SIZE:
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
        
        
        for attempt in range(1, self.max_retries + 1):
            try:
                logger.info(f"Uploading {file_path.name} (attempt {attempt}/{self.max_retries})")

                if file_size > MULTIPART_THRESHOLD:
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
                
                
                # Permanent Errors (Credentials/Permissions)
                if error_code in ['InvalidAccessKeyId', 'SignatureDoesNotMatch']:
                    logger.error(f"PERMANENT ERROR: Invalid AWS credentials ({error_code})")
                    raise PermanentUploadError(f"Invalid AWS credentials: {error_code}")
                
                elif error_code == 'NoSuchBucket':
                    logger.error(f"PERMANENT ERROR: Bucket '{self.bucket}' does not exist")
                    raise PermanentUploadError(f"Bucket does not exist: {self.bucket}")
                
                elif error_code == 'AccessDenied':
                    # Parse error message to detect bucket policy denials
                    policy_keywords = [
                        'bucket policy',
                        'policy does not allow',
                        'policy denies',
                        'explicit deny',
                        'not authorized by bucket policy'
                    ]
                    
                    is_bucket_policy_error = any(
                        keyword in error_message.lower() 
                        for keyword in policy_keywords
                    )
                    
                    if is_bucket_policy_error:
                        logger.error(
                            f"PERMANENT ERROR: Bucket policy denies access - {error_message}"
                        )
                        logger.error(
                            f"This vehicle's credentials are blocked by bucket policy. "
                            f"Check bucket policy rules for bucket '{self.bucket}'"
                        )
                        raise PermanentUploadError(
                            f"Bucket policy denies access: {error_message}"
                        )
                    else:
                        # Generic IAM permission error
                        logger.error(
                            f"PERMANENT ERROR: Access denied - check IAM permissions - {error_message}"
                        )
                        raise PermanentUploadError(
                            f"IAM permissions denied for bucket {self.bucket}: {error_message}"
                        )
                
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
    

    def _guess_source_from_path(self, path: str) -> str:
        """
        Guess source name from path (for legacy format).
        
        Args:
            path: Directory path
            
        Returns:
            str: Guessed source name
            
        Note:
            This is a fallback for legacy config format.
            New format should explicitly specify source.
        """
        from pathlib import Path
        path_obj = Path(path)
        
        # Smart detection based on path patterns
        path_str = str(path_obj).lower()
        
        if 'terminal' in path_str:
            return 'terminal'
        elif '.ros/log' in path_str or 'ros_log' in path_str:
            return 'ros'
        elif 'ros2' in path_str or 'ros2_ws' in path_str:
            return 'ros2'
        elif path_str.startswith('/var/log'):
            return 'syslog'
        else:
            # Fallback to last directory name
            return path_obj.name

    def _build_s3_key(self, file_path: Path) -> str:
        """
        Build S3 key with source-based organization.
        
        Format: {vehicle-id}/{date}/{source}/{relative-path}
        
        Source Detection:
        - Matches file path against configured log_directories
        - Uses explicit 'source' from config
        
        Date Logic:
        - All files: Use file modification time (st_mtime)
        - This ensures files are grouped by when they were actually written
        
        Folder Structure:
        - Preserves full folder structure relative to monitored directory
        
        Args:
            file_path: Local file path
            
        Returns:
            str: S3 object key
            
        Examples:
            Config: [{path: "/home/autoware/.parcel/log/terminal", source: "terminal"}]
            File: /home/autoware/.parcel/log/terminal/session.log
            Result: vehicle-001/2025-10-20/terminal/session.log
            
            Config: [{path: "/home/autoware/.ros/log", source: "ros"}]
            File: /home/autoware/.ros/log/run-123/launch.log
            Result: vehicle-001/2025-10-20/ros/run-123/launch.log
            
            Config: [{path: "/var/log", source: "syslog"}]
            File: /var/log/syslog (modified Oct 18)
            Result: vehicle-001/2025-10-18/syslog/syslog
        """
        file_str = str(file_path.resolve())
        
        # Get file modification time
        try:
            stat = file_path.stat()
            mtime = stat.st_mtime  # Modification time - when file content was last written
        except (OSError, FileNotFoundError):
            # Fallback to current date if file stat fails
            logger.warning(f"Cannot stat file {file_path}, using current date")
            date_str = datetime.now().strftime("%Y-%m-%d")
            source = 'other'
            relative_path = file_path.name

            s3_key = f"{self.vehicle_id}/{date_str}/{source}/{relative_path}"
            logger.debug(f"Built S3 key (stat failed): {file_path.name} → {s3_key}")
            return s3_key

        # Match file against configured directories
        source = None
        relative_path = None

        for dir_config in self.log_directory_configs:
            log_dir = dir_config['path']
            log_dir_resolved = str(Path(log_dir).resolve())

            # Check if file is under this directory
            if file_str.startswith(log_dir_resolved):
                # Use explicit source from config
                source = dir_config['source']

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

        # Use modification time for date grouping (all files)
        # This ensures files are organized by when they were actually written
        timestamp = mtime
        date_str = datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d")
        
        # Build final S3 key
        s3_key = f"{self.vehicle_id}/{date_str}/{source}/{relative_path}"
        
        logger.debug(f"Built S3 key: {file_path.name} → {s3_key}")
        
        return s3_key
    
    def _validate_directory_paths(self):
        """
        Validate that configured directories exist.
        
        Logs warnings for missing directories but doesn't fail startup.
        This allows pre-configuration while still catching typos.
        
        Called during initialization.
        """
        for config in self.log_directory_configs:
            path = config['path']
            if not Path(path).exists():
                logger.warning(
                    f"Directory does not exist: {path} (source: {config['source']}). "
                    f"Will be created on first file event. "
                    f"If this is unexpected, check for typos in config.yaml"
                )
            else:
                logger.debug(f"Directory exists: {path} (source: {config['source']})")
    
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
                multipart_threshold=MULTIPART_THRESHOLD,
                multipart_chunksize=MULTIPART_CHUNK_SIZE
            )
        )
    
    def verify_upload(self, local_path: str) -> bool:
        """
        Verify that THIS specific file (same content) exists in S3.
        
        Checks by comparing BOTH file size AND content hash (ETag/MD5).
        This prevents false positives when different files have the same size.
        
        Date checking strategy:
        - Syslog files: Only check expected date (mtime), no date range check
        - Other files: Check ±5 days around mtime (handles delayed uploads)
        
        Args:
            local_path: Local file path
            
        Returns:
            bool: True if this exact file already exists in S3, False otherwise
            
        Note:
            Uses MD5 hash for content verification. For multipart uploads,
            ETag format is different (MD5-of-MD5s), so we fall back to
            size-only comparison for those cases.
        """
        file_path = Path(local_path)
        
        try:
            local_size = file_path.stat().st_size
            local_mtime = file_path.stat().st_mtime
        except (OSError, FileNotFoundError):
            return False
        
        # Calculate local file MD5 hash for verification (with caching)
        local_md5 = self._get_cached_md5(file_path)
        if local_md5 is None:
            logger.warning(f"Cannot calculate MD5 for {file_path.name}, skipping verification")
            return False
        
        # Check using file's actual modification date first (most likely match)
        s3_key = self._build_s3_key(file_path)  # Uses mtime internally for syslog
        
        if self._verify_s3_object(s3_key, local_size, local_md5, file_path.name):
            return True
        
        # Determine if this is a syslog file
        file_str = str(file_path.resolve())
        is_syslog = any(
            file_str.startswith(str(Path(cfg['path']).resolve())) and cfg['source'] == 'syslog'
            for cfg in self.log_directory_configs
        )
        
        if is_syslog:
            # Syslog: Only check expected date (no date range check)
            logger.debug(f"Syslog file not found in S3 for expected date: {file_path.name}")
            return False
        
        # For non-syslog files, check ±N days around file mtime
        # (handles cases where upload was delayed or file date was wrong)
        base_date = datetime.fromtimestamp(local_mtime)

        for days_offset in range(-DATE_SEARCH_RANGE_DAYS, DATE_SEARCH_RANGE_DAYS + 1):
            if days_offset == 0:
                continue  # Already checked above
            
            check_date = base_date + timedelta(days=days_offset)
            date_str = check_date.strftime("%Y-%m-%d")
            
            # Rebuild S3 key with different date
            original_parts = s3_key.split('/', 3)  # [vehicle_id, date, source, relative_path]
            if len(original_parts) >= 4:
                vehicle_id, _, source, relative_path = original_parts
                alternate_key = f"{vehicle_id}/{date_str}/{source}/{relative_path}"
                
                if self._verify_s3_object(alternate_key, local_size, local_md5, file_path.name, days_offset):
                    return True
        
        # File not found in S3 (or all found files have different content)
        logger.debug(f"File not found in S3 or different content: {file_path.name}")
        return False
    
    def _get_cached_md5(self, file_path: Path) -> str:
        """
        Get MD5 hash with caching for performance optimization.

        Caches MD5 hashes for up to MD5_CACHE_TTL_SECONDS to avoid recalculating
        for the same file. Validates file hasn't changed since cache by comparing
        modification time.

        Args:
            file_path: Path to file

        Returns:
            str: Hex MD5 hash, or None if calculation fails

        Performance Impact:
            - For large files (GB), saves seconds per verification
            - For startup scans, can reduce scan time by 10-100x
            - Minimal memory overhead (~100 bytes per cached file)
        """
        filepath_str = str(file_path.resolve())

        try:
            current_mtime = file_path.stat().st_mtime
        except (OSError, FileNotFoundError):
            # File doesn't exist or can't be accessed
            return None

        # Check cache
        if filepath_str in self._md5_cache:
            cached_md5, cached_mtime, cache_time = self._md5_cache[filepath_str]

            # Validate cache is still valid
            cache_age = time.time() - cache_time
            mtime_matches = abs(current_mtime - cached_mtime) < 0.001  # Within 1ms

            if cache_age < MD5_CACHE_TTL_SECONDS and mtime_matches:
                logger.debug(f"Using cached MD5 for {file_path.name} (cache age: {cache_age:.1f}s)")
                return cached_md5
            else:
                # Cache expired or file modified
                if not mtime_matches:
                    logger.debug(f"File modified since cache, recalculating MD5: {file_path.name}")
                else:
                    logger.debug(f"Cache expired, recalculating MD5: {file_path.name}")

        # Calculate fresh MD5
        md5_hash = self._calculate_md5(file_path)

        if md5_hash:
            # Store in cache
            self._md5_cache[filepath_str] = (md5_hash, current_mtime, time.time())
            logger.debug(f"Cached MD5 for {file_path.name}")

        return md5_hash

    def _calculate_md5(self, file_path: Path) -> str:
        """
        Calculate MD5 hash of file for content verification.

        Reads file in chunks to handle large files efficiently.

        Args:
            file_path: Path to file

        Returns:
            str: Hex MD5 hash, or None if calculation fails

        Note:
            Prefer using _get_cached_md5() instead for better performance.
        """
        import hashlib

        try:
            md5_hash = hashlib.md5()

            with open(file_path, 'rb') as f:
                # Read in 8MB chunks for efficiency
                for chunk in iter(lambda: f.read(MD5_READ_CHUNK_SIZE), b''):
                    md5_hash.update(chunk)

            return md5_hash.hexdigest()

        except Exception as e:
            logger.error(f"Failed to calculate MD5 for {file_path.name}: {e}")
            return None
    
    def _verify_s3_object(self, s3_key: str, local_size: int, local_md5: str, 
                         filename: str, days_offset: int = 0) -> bool:
        """
        Verify S3 object matches local file by size and content hash.
        
        Args:
            s3_key: S3 object key
            local_size: Local file size in bytes
            local_md5: Local file MD5 hash (hex)
            filename: Filename for logging
            days_offset: Days offset from expected date (for logging)
            
        Returns:
            bool: True if S3 object matches local file
        """
        try:
            response = self.s3_client.head_object(Bucket=self.bucket, Key=s3_key)
            s3_size = response['ContentLength']
            s3_etag = response['ETag'].strip('"')
            
            # Check size first (fast check)
            if s3_size != local_size:
                logger.debug(
                    f"S3 object size mismatch: {filename} "
                    f"(local: {local_size}, S3: {s3_size})"
                )
                return False
            
            # Check content hash (ETag)
            # Note: For multipart uploads, ETag format is "MD5-of-MD5s-partcount"
            # For single-part uploads, ETag is just the MD5 hash
            
            if '-' in s3_etag:
                # Multipart upload - ETag is not simple MD5
                # Fall back to size-only comparison (already checked above)
                logger.debug(
                    f"S3 object is multipart upload (ETag: {s3_etag}), "
                    f"using size-only verification: {filename}"
                )
                
                offset_msg = f" ({days_offset:+d} days offset)" if days_offset else ""
                logger.info(
                    f"File already in S3{offset_msg} (same size: {local_size} bytes, "
                    f"multipart upload), skipping: {filename}"
                )
                return True
            
            # Single-part upload - ETag is MD5 hash
            if s3_etag.lower() == local_md5.lower():
                offset_msg = f" ({days_offset:+d} days offset)" if days_offset else ""
                logger.info(
                    f"File already in S3{offset_msg} (size: {local_size} bytes, "
                    f"MD5 match), skipping: {filename}"
                )
                return True
            else:
                logger.debug(
                    f"S3 object content mismatch: {filename} "
                    f"(local MD5: {local_md5}, S3 ETag: {s3_etag})"
                )
                return False
                
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                logger.debug(f"S3 object not found: {s3_key}")
            else:
                logger.debug(f"S3 check error for {s3_key}: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error verifying S3 object {s3_key}: {e}")
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