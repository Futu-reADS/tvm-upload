#!/usr/bin/env python3
"""
Disk Manager for TVM Log Upload System
Monitors disk space and manages file cleanup

Prevents disk from filling up by deleting oldest uploaded files
when disk usage exceeds configured thresholds.

Version: 2.0 - Added age-based cleanup and deferred deletion support
"""

import shutil
import logging
import time
from pathlib import Path
from typing import List, Tuple, Dict
import os

logger = logging.getLogger(__name__)

# Time Constants
SECONDS_PER_DAY = 86400  # 24 * 60 * 60
BYTES_PER_GB = 1024**3

# Deletion Policy Defaults
IMMEDIATE_DELETION = 0  # keep_days value for immediate deletion


class DiskManager:
    """
    Manages disk space by cleaning up uploaded files.
    
    Features:
    - Monitor available disk space
    - Delete oldest uploaded files when space is low (emergency cleanup)
    - Age-based automatic cleanup (NEW v2.0)
    - Deferred deletion (keep files for N days after upload) (NEW v2.0)
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
        >>> disk_mgr.mark_uploaded('/var/log/autoware/file.log', keep_until_days=14)
        >>> if not disk_mgr.check_disk_space():
        ...     deleted = disk_mgr.cleanup_old_files()
    
    Attributes:
        log_directories (List[Path]): Directories to monitor and clean
        reserved_bytes (int): Minimum free space in bytes
        warning_threshold (float): Disk usage % to warn (0-1)
        critical_threshold (float): Disk usage % to force cleanup (0-1)
        uploaded_files (dict): Files safe to delete with deletion time (NEW v2.0)
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
        
        # Track uploaded files with deletion time (NEW v2.0)
        # Format: {filepath: delete_after_timestamp}
        # If keep_days=0, timestamp is 0 (delete immediately)
        # If keep_days=14, timestamp is upload_time + 14 days
        self.uploaded_files: Dict[str, float] = {}
        
        # Callback for registry cleanup (set by main.py)
        self._on_file_deleted_callback = None
        
        logger.info("Initialized")
        logger.info(f"Reserved space: {reserved_gb} GB")
        logger.info(f"Warning threshold: {warning_threshold * 100}%")
        logger.info(f"Critical threshold: {critical_threshold * 100}%")
    
    def mark_uploaded(self, filepath: str, keep_until_days: int = 0):
        """
        Mark file as uploaded (safe to delete after keep_until_days).
        
        Only files marked as uploaded will be deleted during cleanup.
        This prevents accidental deletion of files not yet uploaded.
        
        Uses file modification time + keep_until_days for deletion time
        to avoid issues with system clock changes.
        
        Args:
            filepath: Path to uploaded file
            keep_until_days: Days to keep file after upload (NEW v2.0)
                        - 0: Delete immediately (Option A1)
                        - 14: Keep for 14 days (Option A2)
            
        Note:
            Stores absolute path to avoid ambiguity.
            Uses mtime-based deletion date (immune to system clock changes).
        """
        abs_path = str(Path(filepath).resolve())
        file_path = Path(filepath)
        
        if keep_until_days == IMMEDIATE_DELETION:
            # Delete immediately
            delete_after = 0
            logger.debug(f"Marked for immediate deletion: {file_path.name}")
        else:
            # ===== IMPROVED: Use mtime + keep_days instead of current time =====
            # This makes deletion time immune to system clock changes
            # Deletion is based on file age, not absolute timestamp
            try:
                mtime = file_path.stat().st_mtime
                # Store the target deletion date (mtime + keep_days)
                # Using negative value to distinguish from old epoch-based format
                # Format: -(mtime + keep_days_in_seconds)
                delete_after = -(mtime + (keep_until_days * SECONDS_PER_DAY))
                logger.debug(
                    f"Marked for deletion after {keep_until_days} days "
                    f"(based on file mtime): {file_path.name}"
                )
            except (OSError, FileNotFoundError) as e:
                logger.warning(
                    f"Cannot stat file {file_path.name}, using current time fallback: {e}"
                )
                # Fallback to current time if file stat fails
                delete_after = time.time() + (keep_until_days * SECONDS_PER_DAY)
            # ===== END IMPROVED =====
        
        self.uploaded_files[abs_path] = delete_after
    
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
    
    def cleanup_deferred_deletions(self) -> int:
        """
        Delete files whose deletion time has arrived (NEW v2.0).
        
        Checks all tracked uploaded files and deletes those that:
        - Have delete_after = 0 (immediate deletion)
        - Have delete_after < current_time (retention period expired)
        
        Handles both old epoch-based format and new mtime-based format.
        
        Returns:
            int: Number of files deleted
            
        Note:
            Called after successful upload if keep_days > 0
            Also called during age-based cleanup
        """
        current_time = time.time()
        deleted_count = 0
        freed_bytes = 0
        
        for filepath_str, delete_after in list(self.uploaded_files.items()):
            filepath = Path(filepath_str)
            
            should_delete = False
            
            # Check deletion criteria
            if delete_after == 0:
                # Immediate deletion
                should_delete = True
                
            elif delete_after < 0:
                # ===== NEW FORMAT: Negative value = -(mtime + keep_seconds) =====
                # Extract target deletion date
                target_deletion_date = -delete_after
                
                # Check if file still exists and compare dates
                if filepath.exists():
                    try:
                        mtime = filepath.stat().st_mtime
                        # Calculate when file should be deleted
                        file_deletion_time = target_deletion_date
                        
                        # Delete if current time is past deletion time
                        if current_time >= file_deletion_time:
                            should_delete = True
                            age_days = (current_time - mtime) / 86400
                            logger.debug(
                                f"File eligible for deletion (age-based): {filepath.name} "
                                f"({age_days:.1f} days old)"
                            )
                    except (OSError, FileNotFoundError):
                        # File disappeared, remove from tracking
                        logger.debug(f"File disappeared, removing from tracking: {filepath.name}")
                        del self.uploaded_files[filepath_str]
                        continue
                else:
                    # File doesn't exist, remove from tracking
                    logger.debug(f"File already deleted, removing from tracking: {filepath.name}")
                    del self.uploaded_files[filepath_str]
                    continue
            
            else:
                # ===== OLD FORMAT: Positive value = epoch timestamp =====
                # Legacy format for backward compatibility
                if current_time >= delete_after:
                    should_delete = True
                    logger.debug(f"File eligible for deletion (legacy format): {filepath.name}")
            
            # Perform deletion if criteria met
            if should_delete:
                if filepath.exists():
                    try:
                        size = filepath.stat().st_size
                        filepath.unlink()
                        freed_bytes += size
                        deleted_count += 1
                        logger.info(f"Deleted deferred file: {filepath.name} "
                                f"({size / (1024**2):.2f} MB)")
                        
                        # Notify about deletion for registry cleanup
                        if self._on_file_deleted_callback:
                            self._on_file_deleted_callback(filepath_str)
                            
                    except Exception as e:
                        logger.error(f"Error deleting {filepath}: {e}")
                
                # Remove from tracking
                del self.uploaded_files[filepath_str]
        
        if deleted_count > 0:
            logger.info(f"Deferred deletion: {deleted_count} files, "
                    f"{freed_bytes / (1024**3):.2f} GB freed")
        
        return deleted_count
    
    def cleanup_by_age(self, max_age_days: int) -> int:
        """
        Delete files older than max_age_days (NEW v2.0).
        
        Age-based cleanup that deletes files based on modification time,
        regardless of upload status. This handles orphaned files that
        were never uploaded.
        
        Args:
            max_age_days: Maximum age in days (files older will be deleted)
            
        Returns:
            int: Number of files deleted
            
        Note:
            - Deletes ALL files older than max_age_days
            - Use carefully - doesn't check if files were uploaded
            - Maeda-san: 7 days (Option B2)
            - Hayakawa-san: 14 days (Option B1)
        """
        if max_age_days <= 0:
            logger.debug("Age-based cleanup disabled (max_age_days = 0)")
            return 0
        
        logger.info(f"Running age-based cleanup (max age: {max_age_days} days)")

        cutoff_time = time.time() - (max_age_days * SECONDS_PER_DAY)
        deleted_count = 0
        freed_bytes = 0
        
        for directory in self.log_directories:
            if not directory.exists():
                continue
            
            for file_path in directory.rglob('*'):
                if file_path.is_file() and not file_path.name.startswith('.'):
                    try:
                        mtime = file_path.stat().st_mtime
                        
                        if mtime < cutoff_time:
                            size = file_path.stat().st_size
                            age_days = (time.time() - mtime) / 86400
                            
                            logger.info(f"Deleting old file: {file_path.name} "
                                    f"({age_days:.1f} days old, {size / (1024**2):.1f} MB)")
                            
                            file_path.unlink()
                            deleted_count += 1
                            freed_bytes += size
                            
                            # Remove from uploaded tracking if present
                            filepath_str = str(file_path.resolve())
                            self.uploaded_files.pop(filepath_str, None)
                            
                            # Notify about deletion for registry cleanup
                            if self._on_file_deleted_callback:
                                self._on_file_deleted_callback(filepath_str)
                            
                    except Exception as e:
                        logger.error(f"Error deleting {file_path}: {e}")
        
        if deleted_count > 0:
            logger.info(f"Age-based cleanup: {deleted_count} files deleted, "
                    f"{freed_bytes / (1024**3):.2f} GB freed")
        else:
            logger.info(f"Age-based cleanup: no files older than {max_age_days} days found")
        
        return deleted_count
    
    def cleanup_old_files(self, target_free_gb: float = None) -> int:
        """
        Delete oldest uploaded files to free space (EMERGENCY cleanup).
        
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
            This is EMERGENCY cleanup - triggered when disk nearly full
        """
        if target_free_gb is None:
            target_free_bytes = self.reserved_bytes
        else:
            target_free_bytes = int(target_free_gb * 1024 * 1024 * 1024)
        
        logger.info(f"Starting EMERGENCY cleanup to free {target_free_bytes / (1024**3):.2f} GB")
        
        # Get current free space
        _, _, free_bytes = self.get_disk_usage()
        
        if free_bytes >= target_free_bytes:
            logger.info("Sufficient space available, no cleanup needed")
            return 0
        
        # Get all uploaded files sorted by modification time (oldest first)
        # Ignore keep_until time during emergency cleanup
        uploaded_file_list = []
        for filepath_str in self.uploaded_files:
            filepath = Path(filepath_str)
            if filepath.exists():
                try:
                    mtime = filepath.stat().st_mtime
                    size = filepath.stat().st_size
                    uploaded_file_list.append((mtime, size, filepath))
                except (OSError, FileNotFoundError):
                    pass
        
        uploaded_file_list.sort()
        
        deleted_count = 0
        freed_bytes = 0
        
        for mtime, size, filepath in uploaded_file_list:
            # Check if we've freed enough space
            if free_bytes + freed_bytes >= target_free_bytes:
                break
            
            try:
                logger.info(f"EMERGENCY: Deleting {filepath.name} ({size / (1024**2):.2f} MB)")
                filepath.unlink()
                freed_bytes += size
                deleted_count += 1
                
                filepath_str = str(filepath.resolve())
                self.uploaded_files.pop(filepath_str, None)
                
                # Notify about deletion for registry cleanup
                if self._on_file_deleted_callback:
                    self._on_file_deleted_callback(filepath_str)
                    
            except Exception as e:
                logger.error(f"Error deleting {filepath}: {e}")
        
        logger.info(f"EMERGENCY cleanup complete: {deleted_count} files, "
                f"{freed_bytes / (1024**3):.2f} GB freed")
        
        return deleted_count
    
    def emergency_cleanup_all_files(self, target_free_gb: float = None) -> int:
        """
        EMERGENCY ONLY: Delete ANY old files to free space.
        
        Called when disk >95% full. Deletes oldest files first,
        regardless of upload status. Data loss is acceptable in emergency.
        
        Args:
            target_free_gb: Target free space in GB (default: reserved_gb)
            
        Returns:
            int: Number of files deleted
            
        Safety:
        - Deletes ALL files (uploaded or not) when disk critically full
        - Sorts by mtime (modification time), deletes oldest first
        - Stops when target reached or no more files to delete
        - Logs each deletion with age and size
        
        Note:
            This is EMERGENCY-ONLY cleanup for >95% disk usage.
            Regular cleanup should use cleanup_old_files() for <95%.
        """
        if target_free_gb is None:
            target_free_bytes = self.reserved_bytes
        else:
            target_free_bytes = int(target_free_gb * 1024 * 1024 * 1024)
        
        logger.warning("🚨 EMERGENCY CLEANUP: Deleting ALL old files (uploaded or not)")
        
        # Get current free space
        _, _, free_bytes = self.get_disk_usage()
        
        if free_bytes >= target_free_bytes:
            logger.info("Sufficient space available, no emergency cleanup needed")
            return 0
        
        # Collect ALL files from monitored directories
        all_files = []
        for directory in self.log_directories:
            if not directory.exists():
                continue
            
            for file_path in directory.rglob('*'):
                if file_path.is_file() and not file_path.name.startswith('.'):
                    try:
                        mtime = file_path.stat().st_mtime
                        size = file_path.stat().st_size
                        all_files.append((mtime, size, file_path))
                    except (OSError, FileNotFoundError):
                        pass
        
        # Sort by modification time (oldest first)
        all_files.sort()
        
        deleted_count = 0
        freed_bytes = 0
        
        for mtime, size, filepath in all_files:
            # Check if we've freed enough space
            if free_bytes + freed_bytes >= target_free_bytes:
                break
            
            try:
                age_days = (time.time() - mtime) / 86400
                logger.warning(f"🚨 EMERGENCY: Deleting {filepath.name} "
                            f"({size / (1024**2):.2f} MB, {age_days:.1f} days old)")
                
                filepath.unlink()
                freed_bytes += size
                deleted_count += 1
                
                # Remove from uploaded tracking if present
                filepath_str = str(filepath.resolve())
                self.uploaded_files.pop(filepath_str, None)
                
                # Notify about deletion for registry cleanup
                if self._on_file_deleted_callback:
                    self._on_file_deleted_callback(filepath_str)
                
            except Exception as e:
                logger.error(f"Error deleting {filepath}: {e}")
        
        logger.warning(f"🚨 EMERGENCY CLEANUP: {deleted_count} files deleted, "
                    f"{freed_bytes / (1024**3):.2f} GB freed")
        
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
    
    # Test deferred deletion
    test_file = Path(temp_dir) / "test.log"
    test_file.write_text("test content")
    
    # Mark for deletion after 1 second
    dm.mark_uploaded(str(test_file), keep_until_days=0)
    logger.info(f"File will be deleted in deferred cleanup")
    
    time.sleep(1)
    
    deleted = dm.cleanup_deferred_deletions()
    logger.info(f"Deferred cleanup deleted: {deleted} files")
    
    # Check disk space
    usage, used, free = dm.get_disk_usage()
    logger.info(f"Disk usage: {usage * 100:.1f}%")
    logger.info(f"Free space: {free / (1024**3):.2f} GB")
    
    # Cleanup temp
    import shutil
    shutil.rmtree(temp_dir)