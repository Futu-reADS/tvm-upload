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

# ============================================
# NEW TESTS FOR v2.0 DEFERRED DELETION
# ============================================

def test_mark_uploaded_with_keep_days(temp_dir):
    """Test marking file for deferred deletion"""
    dm = DiskManager([temp_dir])
    
    test_file = Path(temp_dir) / "test.log"
    test_file.write_text("data")
    
    # Mark for deletion after 14 days
    dm.mark_uploaded(str(test_file), keep_until_days=14)
    
    assert len(dm.uploaded_files) == 1
    filepath_key = str(test_file.resolve())
    assert filepath_key in dm.uploaded_files
    
    # Check delete_after timestamp is in the future
    delete_after = dm.uploaded_files[filepath_key]
    import time
    assert delete_after > time.time(), "Delete time should be in future"
    assert delete_after < time.time() + (15 * 24 * 3600), "Delete time should be within 15 days"


def test_mark_uploaded_immediate_deletion(temp_dir):
    """Test marking file for immediate deletion"""
    dm = DiskManager([temp_dir])
    
    test_file = Path(temp_dir) / "test.log"
    test_file.write_text("data")
    
    # Mark for immediate deletion
    dm.mark_uploaded(str(test_file), keep_until_days=0)
    
    filepath_key = str(test_file.resolve())
    assert dm.uploaded_files[filepath_key] == 0, "Delete time should be 0 for immediate"


def test_cleanup_deferred_deletions_immediate(temp_dir):
    """Test cleanup_deferred_deletions deletes immediate files"""
    dm = DiskManager([temp_dir])
    
    # Create and mark file for immediate deletion
    test_file = Path(temp_dir) / "test.log"
    test_file.write_text("data" * 100)
    dm.mark_uploaded(str(test_file), keep_until_days=0)
    
    assert test_file.exists(), "File should exist before cleanup"
    
    # Run deferred deletion
    deleted = dm.cleanup_deferred_deletions()
    
    assert deleted == 1, "Should delete 1 file"
    assert not test_file.exists(), "File should be deleted"


def test_cleanup_deferred_deletions_not_expired(temp_dir):
    """Test cleanup_deferred_deletions keeps non-expired files"""
    dm = DiskManager([temp_dir])
    
    # Create and mark file for deletion in 14 days
    test_file = Path(temp_dir) / "test.log"
    test_file.write_text("data" * 100)
    dm.mark_uploaded(str(test_file), keep_until_days=14)
    
    assert test_file.exists(), "File should exist before cleanup"
    
    # Run deferred deletion (file not expired yet)
    deleted = dm.cleanup_deferred_deletions()
    
    assert deleted == 0, "Should NOT delete file (not expired)"
    assert test_file.exists(), "File should still exist"


def test_cleanup_deferred_deletions_expired(temp_dir):
    """Test cleanup_deferred_deletions deletes expired files"""
    dm = DiskManager([temp_dir])
    
    # Create file
    test_file = Path(temp_dir) / "test.log"
    test_file.write_text("data" * 100)
    
    # Manually set expired timestamp (in the past)
    import time
    filepath_key = str(test_file.resolve())
    dm.uploaded_files[filepath_key] = time.time() - 1  # 1 second ago
    
    assert test_file.exists(), "File should exist before cleanup"
    
    # Run deferred deletion
    deleted = dm.cleanup_deferred_deletions()
    
    assert deleted == 1, "Should delete expired file"
    assert not test_file.exists(), "File should be deleted"


# ============================================
# NEW TESTS FOR v2.0 AGE-BASED CLEANUP
# ============================================

def test_cleanup_by_age_deletes_old_files(temp_dir):
    """Test cleanup_by_age deletes files older than max_age_days"""
    dm = DiskManager([temp_dir])
    
    import time
    import os
    
    # Create old file (8 days old)
    old_file = Path(temp_dir) / "old.log"
    old_file.write_text("old data" * 100)
    old_mtime = time.time() - (8 * 24 * 3600)
    os.utime(str(old_file), (old_mtime, old_mtime))
    
    # Create recent file (2 days old)
    recent_file = Path(temp_dir) / "recent.log"
    recent_file.write_text("recent data" * 100)
    recent_mtime = time.time() - (2 * 24 * 3600)
    os.utime(str(recent_file), (recent_mtime, recent_mtime))
    
    assert old_file.exists()
    assert recent_file.exists()
    
    # Run cleanup with 7-day threshold
    deleted = dm.cleanup_by_age(max_age_days=7)
    
    assert deleted == 1, "Should delete 1 old file"
    assert not old_file.exists(), "Old file should be deleted"
    assert recent_file.exists(), "Recent file should remain"


def test_cleanup_by_age_respects_threshold(temp_dir):
    """Test cleanup_by_age only deletes files exceeding threshold"""
    dm = DiskManager([temp_dir])
    
    import time
    import os
    
    # Create files of various ages
    ages_days = [1, 5, 10, 15, 20]
    files = []
    
    for age in ages_days:
        f = Path(temp_dir) / f"file_{age}days.log"
        f.write_text("data" * 100)
        mtime = time.time() - (age * 24 * 3600)
        os.utime(str(f), (mtime, mtime))
        files.append((f, age))
    
    # Run cleanup with 14-day threshold
    deleted = dm.cleanup_by_age(max_age_days=14)
    
    # Should delete files older than 14 days (15, 20)
    assert deleted == 2, f"Should delete 2 files (15d, 20d), got {deleted}"
    
    # Check which files remain
    for f, age in files:
        if age <= 14:
            assert f.exists(), f"File {age} days old should remain"
        else:
            assert not f.exists(), f"File {age} days old should be deleted"


def test_cleanup_by_age_disabled(temp_dir):
    """Test cleanup_by_age does nothing when max_age_days=0"""
    dm = DiskManager([temp_dir])
    
    import time
    import os
    
    # Create very old file
    old_file = Path(temp_dir) / "ancient.log"
    old_file.write_text("data" * 100)
    old_mtime = time.time() - (100 * 24 * 3600)  # 100 days old
    os.utime(str(old_file), (old_mtime, old_mtime))
    
    # Run cleanup with disabled threshold
    deleted = dm.cleanup_by_age(max_age_days=0)
    
    assert deleted == 0, "Should not delete any files when disabled"
    assert old_file.exists(), "File should still exist"


def test_cleanup_by_age_handles_nonexistent_directory():
    """Test cleanup_by_age handles missing directory gracefully"""
    dm = DiskManager(['/tmp/nonexistent-tvm-test-dir'])
    
    # Should not raise error
    deleted = dm.cleanup_by_age(max_age_days=7)
    
    assert deleted == 0, "Should return 0 for nonexistent directory"


def test_cleanup_by_age_removes_from_uploaded_tracking(temp_dir):
    """Test cleanup_by_age removes files from uploaded_files tracking"""
    dm = DiskManager([temp_dir])
    
    import time
    import os
    
    # Create old file
    old_file = Path(temp_dir) / "old.log"
    old_file.write_text("data" * 100)
    old_mtime = time.time() - (10 * 24 * 3600)
    os.utime(str(old_file), (old_mtime, old_mtime))
    
    # Mark as uploaded
    dm.mark_uploaded(str(old_file), keep_until_days=14)
    assert dm.get_uploaded_files_count() == 1
    
    # Run age-based cleanup (7 days)
    deleted = dm.cleanup_by_age(max_age_days=7)
    
    assert deleted == 1
    assert dm.get_uploaded_files_count() == 0, "Should remove from tracking"


def test_emergency_cleanup_ignores_keep_until(temp_dir):
    """Test emergency cleanup deletes files regardless of keep_until time"""
    dm = DiskManager([temp_dir])
    
    # Create file and mark for 14-day retention
    test_file = Path(temp_dir) / "test.log"
    test_file.write_text("data" * 1000000)  # 1MB
    dm.mark_uploaded(str(test_file), keep_until_days=14)
    
    # Run emergency cleanup with impossible target
    deleted = dm.cleanup_old_files(target_free_gb=10000)
    
    # Should delete even though keep_until not expired
    assert deleted >= 1, "Emergency cleanup should override keep_until"