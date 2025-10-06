#!/usr/bin/env python3
"""
Disk Manager for TVM Log Upload System
Monitors disk space and manages file cleanup
"""

import shutil
from pathlib import Path
from typing import List, Tuple
import os


class DiskManager:
    """
    Manages disk space by cleaning up uploaded files
    
    Features:
    - Check available disk space
    - Delete oldest files when space low
    - Never delete files that haven't been uploaded
    """
    
    def __init__(self, 
                 log_directories: List[str],
                 reserved_gb: float = 70.0,
                 warning_threshold: float = 0.90,
                 critical_threshold: float = 0.95):
        """
        Initialize disk manager
        
        Args:
            log_directories: Directories to monitor and clean
            reserved_gb: Minimum free space to maintain (GB)
            warning_threshold: Disk usage % to warn at (0-1)
            critical_threshold: Disk usage % to force cleanup (0-1)
        """
        self.log_directories = [Path(d) for d in log_directories]
        self.reserved_bytes = int(reserved_gb * 1024 * 1024 * 1024)
        self.warning_threshold = warning_threshold
        self.critical_threshold = critical_threshold
        
        # Track uploaded files (files safe to delete)
        self.uploaded_files = set()
        
        print(f"[DiskManager] Initialized")
        print(f"[DiskManager] Reserved space: {reserved_gb} GB")
        print(f"[DiskManager] Warning threshold: {warning_threshold * 100}%")
        print(f"[DiskManager] Critical threshold: {critical_threshold * 100}%")
    
    def mark_uploaded(self, filepath: str):
        """
        Mark file as uploaded (safe to delete)
        
        Args:
            filepath: Path to uploaded file
        """
        self.uploaded_files.add(str(Path(filepath).resolve()))
        print(f"[DiskManager] Marked as uploaded: {Path(filepath).name}")
    
    def get_disk_usage(self, path: str = "/") -> Tuple[float, int, int]:
        """
        Get disk usage statistics
        
        Args:
            path: Path to check (default: root)
            
        Returns:
            Tuple of (usage_percent, used_bytes, free_bytes)
        """
        stat = shutil.disk_usage(path)
        usage_percent = stat.used / stat.total
        return (usage_percent, stat.used, stat.free)
    
    def check_disk_space(self, path: str = "/") -> bool:
        """
        Check if disk has enough free space
        
        Args:
            path: Path to check
            
        Returns:
            bool: True if enough space available
        """
        usage_percent, used, free = self.get_disk_usage(path)
        
        if free < self.reserved_bytes:
            print(f"[DiskManager] WARNING: Low disk space")
            print(f"[DiskManager] Free: {free / (1024**3):.2f} GB")
            print(f"[DiskManager] Reserved: {self.reserved_bytes / (1024**3):.2f} GB")
            return False
        
        if usage_percent >= self.critical_threshold:
            print(f"[DiskManager] CRITICAL: Disk usage at {usage_percent * 100:.1f}%")
            return False
        
        if usage_percent >= self.warning_threshold:
            print(f"[DiskManager] WARNING: Disk usage at {usage_percent * 100:.1f}%")
        
        return True
    
    def cleanup_old_files(self, target_free_gb: float = None) -> int:
        """
        Delete oldest uploaded files to free space
        
        Args:
            target_free_gb: Target free space in GB (default: reserved_gb)
            
        Returns:
            int: Number of files deleted
        """
        if target_free_gb is None:
            target_free_bytes = self.reserved_bytes
        else:
            target_free_bytes = int(target_free_gb * 1024 * 1024 * 1024)
        
        print(f"[DiskManager] Starting cleanup to free {target_free_bytes / (1024**3):.2f} GB")
        
        # Get current free space
        _, _, free_bytes = self.get_disk_usage()
        
        if free_bytes >= target_free_bytes:
            print(f"[DiskManager] Sufficient space available, no cleanup needed")
            return 0
        
        # Get all uploaded files sorted by modification time (oldest first)
        uploaded_file_list = []
        for filepath_str in self.uploaded_files:
            filepath = Path(filepath_str)
            if filepath.exists():
                mtime = filepath.stat().st_mtime
                size = filepath.stat().st_size
                uploaded_file_list.append((mtime, size, filepath))
        
        uploaded_file_list.sort()  # Sort by mtime (oldest first)
        
        deleted_count = 0
        freed_bytes = 0
        
        for mtime, size, filepath in uploaded_file_list:
            # Check if we've freed enough space
            if free_bytes + freed_bytes >= target_free_bytes:
                break
            
            try:
                print(f"[DiskManager] Deleting: {filepath.name} ({size / (1024**2):.2f} MB)")
                filepath.unlink()
                freed_bytes += size
                deleted_count += 1
                self.uploaded_files.discard(str(filepath))
            except Exception as e:
                print(f"[DiskManager] ERROR deleting {filepath}: {e}")
        
        print(f"[DiskManager] Cleanup complete: {deleted_count} files deleted, {freed_bytes / (1024**3):.2f} GB freed")
        
        return deleted_count
    
    def get_directory_size(self, directory: str) -> int:
        """
        Calculate total size of directory
        
        Args:
            directory: Directory path
            
        Returns:
            int: Total size in bytes
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
        Get count of files marked as uploaded
        
        Returns:
            int: Number of uploaded files
        """
        return len(self.uploaded_files)


if __name__ == '__main__':
    # Quick test
    import tempfile
    
    # Create temp directory
    temp_dir = tempfile.mkdtemp()
    print(f"Test directory: {temp_dir}")
    
    # Create disk manager
    dm = DiskManager([temp_dir], reserved_gb=1.0)
    
    # Check disk space
    usage, used, free = dm.get_disk_usage()
    print(f"\nDisk usage: {usage * 100:.1f}%")
    print(f"Free space: {free / (1024**3):.2f} GB")
    
    has_space = dm.check_disk_space()
    print(f"Has sufficient space: {has_space}")
    
    # Cleanup temp
    import shutil
    shutil.rmtree(temp_dir)
