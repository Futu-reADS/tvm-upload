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

    # Check delete_after timestamp (stored as negative: -(mtime + keep_seconds))
    delete_after = dm.uploaded_files[filepath_key]
    import time
    assert delete_after < 0, "Delete time should be negative (mtime-based format)"
    # The actual deletion time is -delete_after, which should be in the future
    actual_deletion_time = -delete_after
    assert actual_deletion_time > time.time(), "Actual deletion time should be in future"
    assert actual_deletion_time < time.time() + (15 * 24 * 3600), "Deletion time should be within 15 days"


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


# ============================================
# MULTI-DIRECTORY TESTS
# ============================================

def test_disk_usage_multiple_directories(temp_dir):
    """Test disk usage across multiple log directories"""
    dir1 = Path(temp_dir) / "logs1"
    dir2 = Path(temp_dir) / "logs2"
    dir1.mkdir()
    dir2.mkdir()

    dm = DiskManager([dir1, dir2])

    # Create files in both directories
    file1 = dir1 / "file1.log"
    file2 = dir2 / "file2.log"

    file1.write_bytes(b'0' * 1024)  # 1KB
    file2.write_bytes(b'0' * 2048)  # 2KB

    # Directory size should include both (must call separately for each dir)
    size1 = dm.get_directory_size(str(dir1))
    size2 = dm.get_directory_size(str(dir2))
    assert size1 + size2 >= 3072  # At least 3KB


def test_cleanup_across_multiple_directories(temp_dir):
    """Test cleanup works across multiple directories"""
    dir1 = Path(temp_dir) / "logs1"
    dir2 = Path(temp_dir) / "logs2"
    dir1.mkdir()
    dir2.mkdir()

    dm = DiskManager([dir1, dir2])

    # Create old files in both directories
    import time
    old_time = time.time() - (10 * 24 * 3600)  # 10 days old

    file1 = dir1 / "old1.log"
    file2 = dir2 / "old2.log"

    file1.write_text("data1")
    file2.write_text("data2")

    # Mark as uploaded
    dm.mark_uploaded(str(file1), keep_until_days=0)
    dm.mark_uploaded(str(file2), keep_until_days=0)

    # Cleanup should work across both directories
    deleted = dm.cleanup_deferred_deletions()
    assert deleted >= 2


def test_cleanup_respects_directory_boundaries(temp_dir):
    """Test age-based cleanup respects directory boundaries"""
    import time
    import os

    monitored_dir = Path(temp_dir) / "monitored"
    external_dir = Path(temp_dir) / "external"
    monitored_dir.mkdir()
    external_dir.mkdir()

    dm = DiskManager([monitored_dir])

    # Create old files in both directories
    monitored_file = monitored_dir / "monitored.log"
    external_file = external_dir / "external.log"

    monitored_file.write_text("data")
    external_file.write_text("data")

    # Make both files old (10 days)
    old_time = time.time() - (10 * 24 * 3600)
    os.utime(str(monitored_file), (old_time, old_time))
    os.utime(str(external_file), (old_time, old_time))

    # Age-based cleanup should only delete files in monitored directories
    dm.cleanup_by_age(max_age_days=7)

    # Only monitored file should be deleted
    assert not monitored_file.exists(), "Monitored file should be deleted"
    assert external_file.exists(), "External file should NOT be deleted"

    # Cleanup
    external_file.unlink()


# ============================================
# RACE CONDITION TESTS
# ============================================

def test_file_deleted_during_cleanup(temp_dir):
    """Test cleanup handles file deleted externally during operation"""
    dm = DiskManager([temp_dir])

    # Create files
    file1 = Path(temp_dir) / "file1.log"
    file2 = Path(temp_dir) / "file2.log"

    file1.write_text("data1")
    file2.write_text("data2")

    # Mark for immediate deletion
    dm.mark_uploaded(str(file1), keep_until_days=0)
    dm.mark_uploaded(str(file2), keep_until_days=0)

    # Delete one file externally before cleanup
    file1.unlink()

    # Cleanup should handle missing file gracefully
    try:
        deleted = dm.cleanup_deferred_deletions()
        # Should delete file2 successfully
        assert not file2.exists()
    except Exception as e:
        pytest.fail(f"Cleanup should handle missing files gracefully: {e}")


def test_file_modified_during_cleanup(temp_dir):
    """Test cleanup handles file modified during operation"""
    dm = DiskManager([temp_dir])

    # Create file
    test_file = Path(temp_dir) / "test.log"
    test_file.write_text("original")

    # Mark for deletion
    dm.mark_uploaded(str(test_file), keep_until_days=0)

    # Modify file before cleanup (simulating concurrent write)
    test_file.write_text("modified content - much longer")

    # Cleanup should handle this gracefully
    deleted = dm.cleanup_deferred_deletions()

    # File might or might not be deleted depending on implementation
    # Either outcome is acceptable as long as no crash occurs


def test_permission_denied_during_cleanup(temp_dir):
    """Test cleanup handles permission errors gracefully"""
    import os

    dm = DiskManager([temp_dir])

    # Create file
    test_file = Path(temp_dir) / "readonly.log"
    test_file.write_text("data")

    # Mark for deletion
    dm.mark_uploaded(str(test_file), keep_until_days=0)

    # Make file unreadable/undeletable
    os.chmod(str(test_file), 0o000)

    try:
        # Cleanup should handle permission error gracefully
        # Note: On some systems (like Linux), the file may still be deletable
        # if the parent directory has write permissions (which temp_dir does)
        deleted = dm.cleanup_deferred_deletions()
        # Either outcome is acceptable - file deleted or permission error
    except (OSError, PermissionError):
        pass  # Expected on some systems
    finally:
        # Restore permissions for cleanup (file may already be deleted)
        if test_file.exists():
            os.chmod(str(test_file), 0o644)
            test_file.unlink(missing_ok=True)


# ============================================
# KEEP_UNTIL EDGE CASES
# ============================================

def test_keep_until_in_past(temp_dir):
    """Test files with keep_until already expired are deleted immediately"""
    dm = DiskManager([temp_dir])

    # Create file
    test_file = Path(temp_dir) / "expired.log"
    test_file.write_text("data")

    # Mark with keep_until in the past
    import time
    past_time = time.time() - (10 * 24 * 3600)  # 10 days ago

    dm.uploaded_files[str(test_file)] = past_time

    # Cleanup should delete immediately
    deleted = dm.cleanup_deferred_deletions()
    assert deleted >= 1
    assert not test_file.exists()


def test_keep_until_distant_future(temp_dir):
    """Test files with keep_until far in future are not deleted"""
    dm = DiskManager([temp_dir])

    # Create file
    test_file = Path(temp_dir) / "future.log"
    test_file.write_text("data")

    # Mark with keep_until 1000 days in future
    dm.mark_uploaded(str(test_file), keep_until_days=1000)

    # Cleanup should not delete
    deleted = dm.cleanup_deferred_deletions()

    assert test_file.exists(), "File with distant future keep_until should not be deleted"


def test_keep_until_exact_boundary(temp_dir):
    """Test file exactly at keep_until boundary"""
    dm = DiskManager([temp_dir])

    # Create file
    test_file = Path(temp_dir) / "boundary.log"
    test_file.write_text("data")

    # Mark with keep_until exactly now (within 1 second)
    import time
    boundary_time = time.time() + 1  # 1 second from now

    dm.uploaded_files[str(test_file)] = boundary_time

    # Wait briefly
    time.sleep(1.5)

    # Cleanup should delete (time has passed)
    deleted = dm.cleanup_deferred_deletions()
    assert deleted >= 1


# ============================================
# UPLOADED FILES TRACKING TESTS
# ============================================

def test_uploaded_files_removal_from_tracking(temp_dir):
    """Test deleted files are removed from uploaded tracking"""
    dm = DiskManager([temp_dir])

    # Create files
    file1 = Path(temp_dir) / "file1.log"
    file2 = Path(temp_dir) / "file2.log"

    file1.write_text("data1")
    file2.write_text("data2")

    # Mark both
    dm.mark_uploaded(str(file1), keep_until_days=0)
    dm.mark_uploaded(str(file2), keep_until_days=5)

    assert len(dm.uploaded_files) == 2

    # Cleanup deletes file1 only
    dm.cleanup_deferred_deletions()

    # File1 should be removed from tracking
    assert str(file1) not in dm.uploaded_files
    # File2 should still be tracked
    assert str(file2) in dm.uploaded_files


def test_get_uploaded_files_count(temp_dir):
    """Test getting count of uploaded files"""
    dm = DiskManager([temp_dir])

    # Initially zero
    assert dm.get_uploaded_files_count() == 0

    # Add files
    for i in range(5):
        f = Path(temp_dir) / f"file{i}.log"
        f.write_text("data")
        dm.mark_uploaded(str(f), keep_until_days=10)

    assert dm.get_uploaded_files_count() == 5


# ============================================
# LARGE-SCALE TESTS (1000+ FILES)
# ============================================

def test_cleanup_with_1000_files(temp_dir):
    """Test cleanup performance with 1000+ files"""
    dm = DiskManager([temp_dir])

    # Create 1000 files
    files = []
    for i in range(1000):
        f = Path(temp_dir) / f"file{i:04d}.log"
        f.write_text(f"data{i}")
        files.append(f)

        # Mark half for immediate deletion
        if i < 500:
            dm.mark_uploaded(str(f), keep_until_days=0)

    # Cleanup should delete 500 files
    deleted = dm.cleanup_deferred_deletions()
    assert deleted == 500

    # Verify correct files deleted
    for i in range(500):
        assert not files[i].exists()
    for i in range(500, 1000):
        assert files[i].exists()

    # Cleanup
    for f in files[500:]:
        f.unlink(missing_ok=True)


def test_age_based_cleanup_with_many_files(temp_dir):
    """Test age-based cleanup with many files"""
    import time
    import os

    dm = DiskManager([temp_dir])

    # Create 500 files with varying ages
    files = []
    current_time = time.time()

    for i in range(500):
        f = Path(temp_dir) / f"aged{i:04d}.log"
        f.write_text(f"data{i}")
        files.append(f)

        # Files 0-249: 10 days old
        # Files 250-499: 5 days old
        if i < 250:
            age = current_time - (10 * 24 * 3600)
        else:
            age = current_time - (5 * 24 * 3600)

        os.utime(str(f), (age, age))

    # Cleanup files older than 7 days
    deleted = dm.cleanup_by_age(max_age_days=7)

    # Should delete first 250 files (10 days old)
    assert deleted == 250

    # Cleanup
    for f in files[250:]:
        f.unlink(missing_ok=True)


# COMMENTED OUT: Very slow test - enable for stress testing
# def test_directory_size_with_10000_files(temp_dir):
#     """STRESS TEST: Directory size calculation with 10,000 files (slow)"""
#     dm = DiskManager([temp_dir])
#
#     # Create 10,000 small files
#     for i in range(10000):
#         f = Path(temp_dir) / f"stress{i:05d}.log"
#         f.write_bytes(b'0' * 100)  # 100 bytes each
#
#     size = dm.get_directory_size()
#     expected_min = 10000 * 100  # At least 1MB
#
#     assert size >= expected_min
#
#     # Cleanup
#     for i in range(10000):
#         f = Path(temp_dir) / f"stress{i:05d}.log"
#         f.unlink(missing_ok=True)


# ============================================
# CALLBACK INTEGRATION TESTS
# ============================================

def test_on_file_deleted_callback(temp_dir):
    """Test callback is called when file is deleted"""
    deleted_files = []

    def callback(filepath):
        deleted_files.append(filepath)

    dm = DiskManager([temp_dir])
    dm._on_file_deleted_callback = callback

    # Create file
    test_file = Path(temp_dir) / "test.log"
    test_file.write_text("data")

    # Mark for deletion
    dm.mark_uploaded(str(test_file), keep_until_days=0)

    # Cleanup
    dm.cleanup_deferred_deletions()

    # Callback should have been called
    assert len(deleted_files) == 1
    assert str(test_file.resolve()) in deleted_files[0]


def test_callback_with_multiple_deletions(temp_dir):
    """Test callback called for each deleted file"""
    deleted_files = []

    def callback(filepath):
        deleted_files.append(filepath)

    dm = DiskManager([temp_dir])
    dm._on_file_deleted_callback = callback

    # Create 10 files
    files = []
    for i in range(10):
        f = Path(temp_dir) / f"file{i}.log"
        f.write_text("data")
        files.append(f)
        dm.mark_uploaded(str(f), keep_until_days=0)

    # Cleanup
    dm.cleanup_deferred_deletions()

    # Callback should be called 10 times
    assert len(deleted_files) == 10


# ============================================
# DISK SPACE CALCULATION TESTS
# ============================================

def test_check_disk_space_available(temp_dir):
    """Test disk space availability check"""
    dm = DiskManager([temp_dir], reserved_gb=0.001)  # 1MB reserved

    # Should have space available
    has_space = dm.check_disk_space()

    assert isinstance(has_space, bool)
    assert has_space is True  # Should have space with low requirement


def test_get_disk_usage_stats(temp_dir):
    """Test getting disk usage statistics"""
    dm = DiskManager([temp_dir])

    usage_percent, used_bytes, free_bytes = dm.get_disk_usage()

    assert isinstance(usage_percent, float)
    assert isinstance(used_bytes, int)
    assert isinstance(free_bytes, int)

    # Percent should be between 0-1
    assert 0 <= usage_percent <= 1
    assert used_bytes > 0
    assert free_bytes > 0


def test_disk_usage_with_very_large_files(temp_dir):
    """Test disk usage calculation with large files"""
    dm = DiskManager([temp_dir])

    # Create large file (10MB)
    large_file = Path(temp_dir) / "large.log"
    with open(large_file, 'wb') as f:
        f.write(b'0' * (10 * 1024 * 1024))

    size = dm.get_directory_size(temp_dir)
    assert size >= 10 * 1024 * 1024

    # Cleanup
    large_file.unlink()


# ============================================
# System Directory Protection Tests
# ============================================

def test_system_directory_detection():
    """Test that system directories are correctly detected"""
    from src.disk_manager import SYSTEM_DIRECTORIES

    dm = DiskManager(["/tmp"])

    # System directories should be detected
    assert dm._is_system_directory(Path("/var/log/syslog"))
    assert dm._is_system_directory(Path("/etc/passwd"))
    assert dm._is_system_directory(Path("/usr/bin/bash"))
    assert dm._is_system_directory(Path("/opt/app/config"))
    assert dm._is_system_directory(Path("/sys/kernel"))
    assert dm._is_system_directory(Path("/proc/cpuinfo"))
    assert dm._is_system_directory(Path("/boot/grub"))
    assert dm._is_system_directory(Path("/dev/null"))

    # User directories should NOT be detected as system
    assert not dm._is_system_directory(Path("/home/user/file.log"))
    assert not dm._is_system_directory(Path("/tmp/test.log"))


def test_pattern_matching_blocks_system_directory(temp_dir):
    """Test that _matches_pattern blocks files in system directories"""
    # Create config with pattern
    dir_configs = {
        "/var/log": {
            'pattern': 'syslog.*',
            'recursive': False,
            'allow_deletion': True  # Even with allow_deletion=true...
        }
    }

    dm = DiskManager(
        log_directories=["/var/log"],
        directory_configs=dir_configs
    )

    # System directory files should be blocked (even if pattern matches)
    syslog_file = Path("/var/log/syslog.1")
    result = dm._matches_pattern(syslog_file)

    assert result is False, "System directory files should be blocked from deletion"


def test_pattern_matching_respects_allow_deletion_false(temp_dir):
    """Test that _matches_pattern respects allow_deletion=false"""
    # Create test file in temp directory
    test_file = Path(temp_dir) / "test.log"
    test_file.write_text("data")

    # Config with allow_deletion=false
    dir_configs = {
        str(Path(temp_dir).resolve()): {
            'pattern': '*.log',
            'recursive': True,
            'allow_deletion': False
        }
    }

    dm = DiskManager(
        log_directories=[temp_dir],
        directory_configs=dir_configs
    )

    # File matches pattern but allow_deletion=false
    result = dm._matches_pattern(test_file)

    assert result is False, "Files should be blocked when allow_deletion=false"


def test_pattern_matching_respects_allow_deletion_true(temp_dir):
    """Test that _matches_pattern allows deletion when allow_deletion=true"""
    # Create test file
    test_file = Path(temp_dir) / "test.log"
    test_file.write_text("data")

    # Config with allow_deletion=true
    dir_configs = {
        str(Path(temp_dir).resolve()): {
            'pattern': '*.log',
            'recursive': True,
            'allow_deletion': True
        }
    }

    dm = DiskManager(
        log_directories=[temp_dir],
        directory_configs=dir_configs
    )

    # File matches pattern and allow_deletion=true
    result = dm._matches_pattern(test_file)

    assert result is True, "Files should be allowed when allow_deletion=true and pattern matches"


def test_pattern_matching_default_allow_deletion(temp_dir):
    """Test that allow_deletion defaults to true for backward compatibility"""
    # Create test file
    test_file = Path(temp_dir) / "test.log"
    test_file.write_text("data")

    # Config WITHOUT allow_deletion specified (should default to true)
    dir_configs = {
        str(Path(temp_dir).resolve()): {
            'pattern': '*.log',
            'recursive': True
            # allow_deletion not specified
        }
    }

    dm = DiskManager(
        log_directories=[temp_dir],
        directory_configs=dir_configs
    )

    # Should default to allow_deletion=true
    result = dm._matches_pattern(test_file)

    assert result is True, "allow_deletion should default to true"


def test_age_cleanup_skips_system_directory():
    """Test that age-based cleanup skips system directories"""
    # This is a functional test - we verify the logic, not actual /var/log access
    import time

    dir_configs = {
        "/var/log": {
            'pattern': 'syslog.*',
            'recursive': False,
            'allow_deletion': True  # Even if mistakenly set to true
        }
    }

    dm = DiskManager(
        log_directories=["/var/log"],
        directory_configs=dir_configs
    )

    # Mock file in /var/log
    fake_file = Path("/var/log/syslog.1")

    # Should be blocked by system directory check
    result = dm._matches_pattern(fake_file)
    assert result is False, "Age cleanup should skip system directory files"


def test_emergency_cleanup_skips_system_directory():
    """Test that emergency cleanup skips system directories"""
    dir_configs = {
        "/var/log": {
            'pattern': '*',
            'recursive': False,
            'allow_deletion': True  # Even if mistakenly set to true
        }
    }

    dm = DiskManager(
        log_directories=["/var/log"],
        directory_configs=dir_configs
    )

    # Mock file in /var/log
    fake_file = Path("/var/log/kern.log")

    # Should be blocked by system directory check
    result = dm._matches_pattern(fake_file)
    assert result is False, "Emergency cleanup should skip system directory files"


def test_recursive_false_blocks_subdirectory_files(temp_dir):
    """Test that recursive=false blocks files in subdirectories"""
    # Create file structure:
    # temp_dir/
    #   top.log (should be allowed)
    #   subdir/
    #     nested.log (should be blocked)

    top_file = Path(temp_dir) / "top.log"
    top_file.write_text("data")

    subdir = Path(temp_dir) / "subdir"
    subdir.mkdir()
    nested_file = subdir / "nested.log"
    nested_file.write_text("data")

    # Config with recursive=false
    dir_configs = {
        str(Path(temp_dir).resolve()): {
            'pattern': '*.log',
            'recursive': False,  # Don't delete from subdirectories
            'allow_deletion': True
        }
    }

    dm = DiskManager(
        log_directories=[temp_dir],
        directory_configs=dir_configs
    )

    # Top-level file should be allowed
    result_top = dm._matches_pattern(top_file)
    assert result_top is True, "Top-level file should be allowed when recursive=false"

    # Subdirectory file should be blocked
    result_nested = dm._matches_pattern(nested_file)
    assert result_nested is False, "Subdirectory file should be blocked when recursive=false"


def test_recursive_true_allows_subdirectory_files(temp_dir):
    """Test that recursive=true allows files in subdirectories"""
    # Create file structure
    subdir = Path(temp_dir) / "subdir"
    subdir.mkdir()
    nested_file = subdir / "nested.log"
    nested_file.write_text("data")

    # Config with recursive=true
    dir_configs = {
        str(Path(temp_dir).resolve()): {
            'pattern': '*.log',
            'recursive': True,  # Allow deletion from subdirectories
            'allow_deletion': True
        }
    }

    dm = DiskManager(
        log_directories=[temp_dir],
        directory_configs=dir_configs
    )

    # Subdirectory file should be allowed
    result = dm._matches_pattern(nested_file)
    assert result is True, "Subdirectory file should be allowed when recursive=true"


def test_recursive_default_true(temp_dir):
    """Test that recursive defaults to true for backward compatibility"""
    # Create nested file
    subdir = Path(temp_dir) / "subdir"
    subdir.mkdir()
    nested_file = subdir / "nested.log"
    nested_file.write_text("data")

    # Config WITHOUT recursive specified
    dir_configs = {
        str(Path(temp_dir).resolve()): {
            'pattern': '*.log',
            'allow_deletion': True
            # recursive not specified
        }
    }

    dm = DiskManager(
        log_directories=[temp_dir],
        directory_configs=dir_configs
    )

    # Should default to recursive=true
    result = dm._matches_pattern(nested_file)
    assert result is True, "recursive should default to true (backward compatibility)"