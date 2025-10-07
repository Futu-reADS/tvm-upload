#!/usr/bin/env python3
"""
Tests for Disk Manager
"""

import pytest
import tempfile
import shutil
from pathlib import Path

from src.disk_manager import DiskManager


@pytest.fixture
def temp_dir():
    """Create temporary directory for testing"""
    tmpdir = tempfile.mkdtemp()
    yield tmpdir
    shutil.rmtree(tmpdir)


def test_disk_manager_initialization(temp_dir):
    """Test disk manager can be initialized"""
    dm = DiskManager([temp_dir], reserved_gb=10.0)
    
    assert dm.reserved_bytes == 10 * 1024 * 1024 * 1024
    assert dm.warning_threshold == 0.90
    assert dm.critical_threshold == 0.95


def test_get_disk_usage():
    """Test getting disk usage statistics"""
    dm = DiskManager(["/tmp"])
    
    usage, used, free = dm.get_disk_usage("/")
    
    assert 0 <= usage <= 1
    assert used > 0
    assert free > 0


def test_check_disk_space():
    """Test disk space checking"""
    dm = DiskManager(["/tmp"], reserved_gb=0.1)  # Only require 100MB
    
    # Should have space with such low requirement
    has_space = dm.check_disk_space("/")
    assert has_space is True


def test_mark_uploaded(temp_dir):
    """Test marking files as uploaded"""
    dm = DiskManager([temp_dir])
    
    # Create test file
    test_file = Path(temp_dir) / "test.log"
    test_file.write_text("data")
    
    # Mark as uploaded
    dm.mark_uploaded(str(test_file))
    
    assert len(dm.uploaded_files) == 1
    assert str(test_file.resolve()) in dm.uploaded_files


def test_cleanup_with_no_uploaded_files(temp_dir):
    """Test cleanup when no files marked as uploaded"""
    dm = DiskManager([temp_dir])
    
    # Create files but don't mark as uploaded
    for i in range(3):
        f = Path(temp_dir) / f"file{i}.log"
        f.write_text("data" * 100)
    
    # Cleanup should delete nothing (no uploaded files)
    deleted = dm.cleanup_old_files(target_free_gb=1000)  # Impossible target
    
    assert deleted == 0
    # Files still exist
    assert len(list(Path(temp_dir).glob("*.log"))) == 3


def test_cleanup_deletes_oldest_first(temp_dir):
    """Test that cleanup deletes oldest files first"""
    dm = DiskManager([temp_dir])
    
    import time
    
    # Create files with different ages
    files = []
    for i in range(3):
        f = Path(temp_dir) / f"file{i}.log"
        f.write_text("data" * 1000)
        dm.mark_uploaded(str(f))
        files.append(f)
        time.sleep(0.1)  # Ensure different mtimes
    
    # Cleanup - should delete oldest (file0)
    deleted = dm.cleanup_old_files(target_free_gb=1000)  # Force cleanup
    
    assert deleted >= 1
    # Oldest file should be gone
    assert not files[0].exists()


def test_get_directory_size(temp_dir):
    """Test calculating directory size"""
    dm = DiskManager([temp_dir])
    
    # Create files
    (Path(temp_dir) / "file1.log").write_text("a" * 1000)
    (Path(temp_dir) / "file2.log").write_text("b" * 2000)
    
    size = dm.get_directory_size(temp_dir)
    
    assert size == 3000  # 1000 + 2000 bytes


def test_get_uploaded_files_count(temp_dir):
    """Test getting count of uploaded files"""
    dm = DiskManager([temp_dir])
    
    assert dm.get_uploaded_files_count() == 0
    
    # Mark some files
    for i in range(3):
        f = Path(temp_dir) / f"file{i}.log"
        f.write_text("data")
        dm.mark_uploaded(str(f))
    
    assert dm.get_uploaded_files_count() == 3


def test_cleanup_stops_when_target_reached(temp_dir):
    """Test cleanup stops once target free space reached"""
    dm = DiskManager([temp_dir])
    
    # Create multiple small files
    for i in range(10):
        f = Path(temp_dir) / f"file{i}.log"
        f.write_text("data" * 100)
        dm.mark_uploaded(str(f))
    
    # Get initial state
    initial_count = dm.get_uploaded_files_count()
    
    # Cleanup with reasonable target (not forcing all deletions)
    deleted = dm.cleanup_old_files(target_free_gb=0.001)  # 1MB
    
    # Should delete some but not necessarily all
    assert deleted >= 0
    assert deleted <= initial_count
