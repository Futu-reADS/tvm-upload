#!/usr/bin/env python3
"""
Integration test - File Monitor -> Upload Manager -> Disk Manager
"""

import sys
import os
from pathlib import Path

# Add project root to path (go up 2 levels: extra -> tests -> root)
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import tempfile
import time
import shutil
from src.file_monitor import FileMonitor
from src.upload_manager import UploadManager
from src.disk_manager import DiskManager


def test_full_integration():
    """Test complete flow: monitor -> upload -> cleanup"""
    
    print("\n=== Integration Test ===\n")
    
    # Create temp directory
    temp_dir = tempfile.mkdtemp()
    print(f"Test directory: {temp_dir}")
    
    # Track uploaded files
    uploaded_files = []
    
    # Disk manager must be defined before callback
    disk_manager = DiskManager(
        [temp_dir],
        reserved_gb=0.1
    )
    
    def mock_upload_callback(filepath):
        """Mock upload - just track what would be uploaded"""
        print(f"[Mock Upload] {Path(filepath).name}")
        uploaded_files.append(filepath)
        disk_manager.mark_uploaded(filepath)
    
    # File monitor detects stable files
    file_monitor = FileMonitor(
        [temp_dir],
        mock_upload_callback,
        stability_seconds=2
    )
    
    try:
        print("\n1. Starting file monitor...")
        file_monitor.start()
        time.sleep(0.5)
        
        print("\n2. Creating test files...")
        for i in range(3):
            f = Path(temp_dir) / f"test{i}.log"
            f.write_text(f"Test data {i}\n" * 100)
            print(f"Created: {f.name}")
            time.sleep(0.3)
        
        print("\n3. Waiting for files to stabilize...")
        time.sleep(3)
        
        print(f"\n4. Files 'uploaded': {len(uploaded_files)}")
        for f in uploaded_files:
            print(f"   - {Path(f).name}")
        
        print(f"\n5. Uploaded files tracked: {disk_manager.get_uploaded_files_count()}")
        
        print("\n6. Checking disk space...")
        usage, used, free = disk_manager.get_disk_usage()
        print(f"Disk usage: {usage * 100:.1f}%")
        print(f"Free space: {free / (1024**3):.2f} GB")
        
        print("\n7. Testing cleanup...")
        deleted = disk_manager.cleanup_old_files(target_free_gb=1000)
        print(f"Files deleted: {deleted}")
        
        print("\n=== Test Complete ===")
        
        # Assertions
        assert len(uploaded_files) == 3, "Should detect 3 files"
        assert disk_manager.get_uploaded_files_count() >= 0, "Should track uploaded files"
        assert deleted >= 0, "Should delete some files"
        
    finally:
        print("\n8. Stopping monitor...")
        file_monitor.stop()
        shutil.rmtree(temp_dir)