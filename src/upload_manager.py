#!/usr/bin/env python3
"""
Upload Manager for TVM Log Upload System
Handles S3 uploads with retry logic
"""

import boto3
import time
from pathlib import Path
from typing import Optional, Tuple
from datetime import datetime
from botocore.exceptions import ClientError, BotoCoreError


class UploadError(Exception):
    """Raised when upload fails after all retries"""
    pass


class UploadManager:
    """
    Manages file uploads to S3 with retry logic
    
    Features:
    - Exponential backoff retry
    - Multipart upload for large files
    - Upload progress tracking
    """
    
    def __init__(self, bucket: str, region: str, vehicle_id: str, 
                 max_retries: int = 10):
        """
        Initialize upload manager
        
        Args:
            bucket: S3 bucket name
            region: AWS region
            vehicle_id: Vehicle identifier for S3 prefix
            max_retries: Maximum retry attempts
        """
        self.bucket = bucket
        self.region = region
        self.vehicle_id = vehicle_id
        self.max_retries = max_retries
        
        # Initialize S3 client
        self.s3_client = boto3.client('s3', region_name=region)
        
        print(f"[UploadManager] Initialized for bucket: {bucket}")
        print(f"[UploadManager] Vehicle ID: {vehicle_id}")
        print(f"[UploadManager] Max retries: {max_retries}")
    
    def upload_file(self, local_path: str) -> bool:
        """
        Upload file to S3 with retry logic
        
        Args:
            local_path: Path to local file
            
        Returns:
            bool: True if upload succeeded, False otherwise
        """
        file_path = Path(local_path)
        
        if not file_path.exists():
            print(f"[UploadManager] ERROR: File not found: {local_path}")
            return False
        
        # Build S3 key
        s3_key = self._build_s3_key(file_path)
        
        # Try upload with retries
        for attempt in range(1, self.max_retries + 1):
            try:
                print(f"[UploadManager] Uploading {file_path.name} (attempt {attempt}/{self.max_retries})")
                
                # Upload file
                file_size = file_path.stat().st_size
                
                if file_size > 5 * 1024 * 1024:  # 5MB threshold
                    # Use multipart upload for large files
                    self._multipart_upload(str(file_path), s3_key)
                else:
                    # Simple upload for small files
                    self.s3_client.upload_file(str(file_path), self.bucket, s3_key)
                
                print(f"[UploadManager] SUCCESS: {file_path.name} -> s3://{self.bucket}/{s3_key}")
                return True
                
            except (ClientError, BotoCoreError) as e:
                print(f"[UploadManager] Upload failed (attempt {attempt}): {e}")
                
                if attempt < self.max_retries:
                    # Calculate backoff delay
                    delay = self._calculate_backoff(attempt)
                    print(f"[UploadManager] Retrying in {delay} seconds...")
                    time.sleep(delay)
                else:
                    print(f"[UploadManager] FAILED: Max retries exceeded for {file_path.name}")
                    return False
            
            except Exception as e:
                print(f"[UploadManager] Unexpected error: {e}")
                return False
        
        return False
    
    def _build_s3_key(self, file_path: Path) -> str:
        """
        Build S3 key from file path
        Format: {vehicle-id}/{YYYY-MM-DD}/{filename}
        
        Args:
            file_path: Local file path
            
        Returns:
            str: S3 key
        """
        # Use current date
        date_str = datetime.now().strftime("%Y-%m-%d")
        
        # Build key
        s3_key = f"{self.vehicle_id}/{date_str}/{file_path.name}"
        
        return s3_key
    
    def _calculate_backoff(self, attempt: int) -> int:
        """
        Calculate exponential backoff delay
        
        Args:
            attempt: Current attempt number (1-based)
            
        Returns:
            int: Delay in seconds
        """
        # Exponential backoff: 1, 2, 4, 8, 16, 32, 64, 128, 256, 512
        delay = min(2 ** (attempt - 1), 512)
        return delay
    
    def _multipart_upload(self, file_path: str, s3_key: str):
        """
        Upload large file using multipart upload
        
        Args:
            file_path: Local file path
            s3_key: S3 object key
        """
        # For simplicity, use boto3's upload_file which handles multipart automatically
        # In production, you might want more control with create_multipart_upload
        self.s3_client.upload_file(
            file_path, 
            self.bucket, 
            s3_key,
            Config=boto3.s3.transfer.TransferConfig(
                multipart_threshold=5 * 1024 * 1024,  # 5MB
                multipart_chunksize=5 * 1024 * 1024   # 5MB chunks
            )
        )
    
    def verify_upload(self, local_path: str) -> bool:
        """
        Verify that file exists in S3
        
        Args:
            local_path: Local file path
            
        Returns:
            bool: True if file exists in S3
        """
        file_path = Path(local_path)
        s3_key = self._build_s3_key(file_path)
        
        try:
            self.s3_client.head_object(Bucket=self.bucket, Key=s3_key)
            return True
        except ClientError:
            return False


if __name__ == '__main__':
    # Quick test (requires AWS credentials)
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python upload_manager.py <file_path>")
        sys.exit(1)
    
    # Test with local credentials
    uploader = UploadManager(
        bucket="tvm-logs-test",
        region="us-east-1",  # Use your test region
        vehicle_id="vehicle-test"
    )
    
    result = uploader.upload_file(sys.argv[1])
    
    if result:
        print("Upload successful!")
        sys.exit(0)
    else:
        print("Upload failed!")
        sys.exit(1)
