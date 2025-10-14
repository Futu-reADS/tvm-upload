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
from typing import Optional, Tuple
from datetime import datetime
from botocore.exceptions import ClientError, BotoCoreError

logger = logging.getLogger(__name__)


class UploadError(Exception):
    """
    Raised when upload fails after all retries.
    
    This exception indicates that the file could not be uploaded
    even after the maximum number of retry attempts.
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
    
    # upload_manager.py
    def __init__(self, bucket: str, region: str, vehicle_id: str, 
                max_retries: int = 10, profile_name: str = None):  # ← Add profile parameter
        """
        Initialize upload manager.
        
        Args:
            bucket: S3 bucket name
            region: AWS region (e.g., 'cn-north-1', 'us-east-1')
            vehicle_id: Vehicle identifier for S3 prefix
            max_retries: Maximum retry attempts (default: 10)
            profile_name: AWS profile name (default: None uses default profile)
        """
        self.bucket = bucket
        self.region = region
        self.vehicle_id = vehicle_id
        self.max_retries = max_retries
        
        # Initialize S3 client with China endpoint support
        import os
        
        # Check for LocalStack (testing)
        endpoint_url = os.getenv('AWS_ENDPOINT_URL')
        
        # Prepare boto3 client kwargs
        client_kwargs = {'region_name': region}
        
        # Add profile if specified
        if profile_name:
            import boto3.session
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
        Upload file to S3 with retry logic.
        
        Attempts upload with exponential backoff on failure.
        Automatically uses multipart upload for files larger than 5MB.
        
        Args:
            local_path: Path to local file
            
        Returns:
            bool: True if upload succeeded, False if failed after all retries
            
        Note:
            Logs detailed progress including attempt number and errors
        """
        file_path = Path(local_path)
        
        if not file_path.exists():
            logger.error(f"File not found: {local_path}")
            return False
        
        # Build S3 key
        s3_key = self._build_s3_key(file_path)
        
        # Try upload with retries
        for attempt in range(1, self.max_retries + 1):
            try:
                logger.info(f"Uploading {file_path.name} (attempt {attempt}/{self.max_retries})")
                
                # Upload file
                file_size = file_path.stat().st_size
                
                if file_size > 5 * 1024 * 1024:
                    # Use multipart upload for large files
                    self._multipart_upload(str(file_path), s3_key)
                else:
                    # Simple upload for small files
                    self.s3_client.upload_file(str(file_path), self.bucket, s3_key)
                
                logger.info(f"SUCCESS: {file_path.name} -> s3://{self.bucket}/{s3_key}")
                return True
                
            except (ClientError, BotoCoreError) as e:
                logger.warning(f"Upload failed (attempt {attempt}): {e}")
                
                if attempt < self.max_retries:
                    # Calculate backoff delay
                    delay = self._calculate_backoff(attempt)
                    logger.info(f"Retrying in {delay} seconds...")
                    time.sleep(delay)
                else:
                    logger.error(f"Max retries exceeded for {file_path.name}")
                    return False
            
            except Exception as e:
                logger.error(f"Unexpected error: {e}")
                return False
        
        return False
    
    def _build_s3_key(self, file_path: Path) -> str:
        """
        Build S3 key from file path.
        
        Format: {vehicle-id}/{YYYY-MM-DD}/{filename}
        Example: vehicle-001/2025-10-12/autoware.log
        
        Args:
            file_path: Local file path
            
        Returns:
            str: S3 object key
            
        Note:
            Uses current date for the middle component
        """
        # Use current date
        date_str = datetime.now().strftime("%Y-%m-%d")
        
        # Build key
        s3_key = f"{self.vehicle_id}/{date_str}/{file_path.name}"
        
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
        Verify that file exists in S3.
        
        Checks if file was successfully uploaded by attempting to
        retrieve object metadata.
        
        Args:
            local_path: Local file path (used to build S3 key)
            
        Returns:
            bool: True if file exists in S3, False otherwise
            
        Note:
            Does not verify file content or size, only existence
        """
        file_path = Path(local_path)
        s3_key = self._build_s3_key(file_path)
        
        try:
            self.s3_client.head_object(Bucket=self.bucket, Key=s3_key)
            return True
        except ClientError:
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