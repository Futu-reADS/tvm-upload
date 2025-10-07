#!/usr/bin/env python3
"""
Disk Manager for TVM Log Upload System
Monitors disk space and manages file cleanup

Prevents disk from filling up by deleting oldest uploaded files
when disk usage exceeds configured thresholds.
"""

import shutil
import logging
from pathlib import Path
from typing import List, Tuple
import os

logger = logging.getLogger(__name__)


class DiskManager:
    """
    Manages disk space by cleaning up uploaded files.
    
    Features:
    - Monitor available disk space
    - Delete oldest uploaded files when space is low
    - Never delete files that haven't been uploaded
    - Configurable warning and critical thresholds
    
    Safety:
    - Only deletes files explicitly marked as uploaded
    - Deletes oldest files first (by modification time)
    - Respects minimum free space requirement
    
    Example:
        >>> disk_mgr = DiskManager(
        ...     log_directories=['/var/log/autoware'],
        ...     reserved_gb=70,
        ...     warning_threshold=0.90
        ... )
        >>> disk_mgr.mark_uploaded('/var/log/autoware/file.log')
        >>> if not disk_mgr.check_disk_space():
        ...     deleted = disk_mgr.cleanup_old_files()
    
    Attributes:
        log_directories (List[Path]): Directories to monitor and clean
        reserved_bytes (int): Minimum free space in bytes
        warning_threshold (float): Disk usage % to warn (0-1)
        critical_threshold (float): Disk usage % to force cleanup (0-1)
        uploaded_files (set): Files safe to delete
    """
    
    def __init__(self, 
                 log_directories: List[str],
                 reserved_gb: float = 70.0,
                 warning_threshold: float = 0.90,
                 critical_threshold: float = 0.95):
        """
        Initialize disk manager.
        
        Args:
            log_directories: Directories to monitor and clean
            reserved_gb: Minimum free space to maintain (GB)
            warning_threshold: Disk usage % to warn at (0-1, e.g. 0.90 = 90%)
            critical_threshold: Disk usage % to force cleanup (0-1, e.g. 0.95 = 95%)
            
        Note:
            Thresholds are disk usage percentages, not free space percentages
        """
        self.log_directories = [Path(d) for d in log_directories]
        self.reserved_bytes = int(reserved_gb * 1024 * 1024 * 1024)
        self.warning_threshold = warning_threshold
        self.critical_threshold = critical_threshold
        
        # Track uploaded files (files safe to delete)
        self.uploaded_files = set()
        
        logger.info("Initialized")
        logger.info(f"Reserved space: {reserved_gb} GB")
        logger.info(f"Warning threshold: {warning_threshold * 100}%")
        logger.info(f"Critical threshold: {critical_threshold * 100}%")
    
    def mark_uploaded(self, filepath: str):
        """
        Mark file as uploaded (safe to delete).
        
        Only files marked as uploaded will be deleted during cleanup.
        This prevents accidental deletion of files not yet uploaded.
        
        Args:
            filepath: Path to uploaded file
            
        Note:
            Stores absolute path to avoid ambiguity
        """
        self.uploaded_files.add(str(Path(filepath).resolve()))
        logger.info(f"Marked as uploaded: {Path(filepath).name}")
    
    def get_disk_usage(self, path: str = "/") -> Tuple[float, int, int]:
        """
        Get disk usage statistics.
        
        Args:
            path: Path to check (default: root filesystem)
            
        Returns:
            Tuple of:
            - usage_percent (float): Disk usage as fraction (0-1)
            - used_bytes (int): Bytes used
            - free_bytes (int): Bytes free
            
        Example:
            >>> usage, used, free = disk_mgr.get_disk_usage()
            >>> print(f"Disk {usage*100:.1f}% full, {free/1e9:.1f} GB free")
        """
        stat = shutil.disk_usage(path)
        usage_percent = stat.used / stat.total
        return (usage_percent, stat.used, stat.free)
    
    def check_disk_space(self, path: str = "/") -> bool:
        """
        Check if disk has enough free space.
        
        Checks against both reserved bytes and threshold percentages.
        Logs warnings at warning_threshold and errors at critical_threshold.
        
        Args:
            path: Path to check (default: root filesystem)
            
        Returns:
            bool: True if sufficient space available, False if space low
            
        Note:
            Returns False if either:
            - Free space < reserved_bytes
            - Usage >= critical_threshold
        """
        usage_percent, used, free = self.get_disk_usage(path)
        
        if free < self.reserved_bytes:
            logger.warning("Low disk space")
            logger.warning(f"Free: {free / (1024**3):.2f} GB")
            logger.warning(f"Reserved: {self.reserved_bytes / (1024**3):.2f} GB")
            return False
        
        if usage_percent >= self.critical_threshold:
            logger.error(f"CRITICAL: Disk usage at {usage_percent * 100:.1f}%")
            return False
        
        if usage_percent >= self.warning_threshold:
            logger.warning(f"Disk usage at {usage_percent * 100:.1f}%")
        
        return True
    
    def cleanup_old_files(self, target_free_gb: float = None) -> int:
        """
        Delete oldest uploaded files to free space.
        
        Deletes files in order of modification time (oldest first) until
        target free space is reached or no more uploaded files remain.
        
        Args:
            target_free_gb: Target free space in GB (default: reserved_gb)
            
        Returns:
            int: Number of files deleted
            
        Safety:
        - Only deletes files previously marked as uploaded
        - Sorts by mtime (modification time), deletes oldest first
        - Stops when target reached or no more files to delete
        - Logs each deletion with file size
        
        Note:
            If target is already met, returns 0 without deleting anything
        """
        if target_free_gb is None:
            target_free_bytes = self.reserved_bytes
        else:
            target_free_bytes = int(target_free_gb * 1024 * 1024 * 1024)
        
        logger.info(f"Starting cleanup to free {target_free_bytes / (1024**3):.2f} GB")
        
        # Get current free space
        _, _, free_bytes = self.get_disk_usage()
        
        if free_bytes >= target_free_bytes:
            logger.info("Sufficient space available, no cleanup needed")
            return 0
        
        # Get all uploaded files sorted by modification time (oldest first)
        uploaded_file_list = []
        for filepath_str in self.uploaded_files:
            filepath = Path(filepath_str)
            if filepath.exists():
                mtime = filepath.stat().st_mtime
                size = filepath.stat().st_size
                uploaded_file_list.append((mtime, size, filepath))
        
        uploaded_file_list.sort()
        
        deleted_count = 0
        freed_bytes = 0
        
        for mtime, size, filepath in uploaded_file_list:
            # Check if we've freed enough space
            if free_bytes + freed_bytes >= target_free_bytes:
                break
            
            try:
                logger.info(f"Deleting: {filepath.name} ({size / (1024**2):.2f} MB)")
                filepath.unlink()
                freed_bytes += size
                deleted_count += 1
                self.uploaded_files.discard(str(filepath))
            except Exception as e:
                logger.error(f"Error deleting {filepath}: {e}")
        
        logger.info(f"Cleanup complete: {deleted_count} files deleted, {freed_bytes / (1024**3):.2f} GB freed")
        
        return deleted_count
    
    def get_directory_size(self, directory: str) -> int:
        """
        Calculate total size of directory recursively.
        
        Args:
            directory: Directory path
            
        Returns:
            int: Total size in bytes (sum of all files)
            
        Note:
            Silently skips files that can't be accessed (permissions, etc.)
        """
        total = 0
        dir_path = Path(directory)
        
        if not dir_path.exists():
            return 0
        
        for item in dir_path.rglob('*'):
            if item.is_file():
                try:
                    total += item.stat().st_size
                except (OSError, PermissionError):
                    pass
        
        return total
    
    def get_uploaded_files_count(self) -> int:
        """
        Get count of files marked as uploaded.
        
        Returns:
            int: Number of files safe to delete
            
        Note:
            Useful for monitoring and debugging
        """
        return len(self.uploaded_files)


if __name__ == '__main__':
    import tempfile
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Create temp directory
    temp_dir = tempfile.mkdtemp()
    logger.info(f"Test directory: {temp_dir}")
    
    # Create disk manager
    dm = DiskManager([temp_dir], reserved_gb=1.0)
    
    # Check disk space
    usage, used, free = dm.get_disk_usage()
    logger.info(f"Disk usage: {usage * 100:.1f}%")
    logger.info(f"Free space: {free / (1024**3):.2f} GB")
    
    has_space = dm.check_disk_space()
    logger.info(f"Has sufficient space: {has_space}")
    
    # Cleanup temp
    import shutil
    shutil.rmtree(temp_dir)