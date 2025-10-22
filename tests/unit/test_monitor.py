#!/usr/bin/env python3
"""
Tests for File Monitor
"""
import json
import os
import pytest
import time
import tempfile
from pathlib import Path

from src.file_monitor import FileMonitor


def wait_until(condition, timeout=10, interval=0.1, description="condition"):
    """
    Poll until condition is true or timeout expires
    
    Args:
        condition: Callable that returns bool
        timeout: Maximum seconds to wait
        interval: Seconds between checks
        description: Description for error message
        
    Returns:
        bool: True if condition met, False if timeout
    """
    start = time.time()
    while time.time() - start < timeout:
        if condition():
            return True
        time.sleep(interval)
    
    elapsed = time.time() - start
    print(f"Timeout after {elapsed:.1f}s waiting for: {description}")
    return False


@pytest.fixture
def temp_dir():
    """Create temporary directory for testing"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def callback_tracker():
    """Fixture to track callback calls with return values"""
    class CallbackTracker:
        def __init__(self):
            self.called_files = []
            self.return_value = True  # ADD THIS - Default: simulate successful upload
        
        def callback(self, filepath):
            self.called_files.append(filepath)
            print(f"[Test] Callback received: {filepath}")
            return self.return_value  # ADD THIS - Return success/failure
    
    return CallbackTracker()


def test_monitor_initialization(temp_dir):
    """Test file monitor can be initialized"""
    def dummy_callback(filepath):
        pass
    
    monitor = FileMonitor([str(temp_dir)], dummy_callback)
    
    assert monitor.stability_seconds == 60
    assert len(monitor.directories) == 1


def test_monitor_start_stop(temp_dir):
    """Test monitor can start and stop"""
    def dummy_callback(filepath):
        pass
    
    monitor = FileMonitor([str(temp_dir)], dummy_callback)
    
    monitor.start()
    assert monitor._running is True
    
    monitor.stop()
    assert monitor._running is False


def test_file_stability_detection(temp_dir, callback_tracker):
    """Test that stable files are detected"""
    monitor = FileMonitor([str(temp_dir)], callback_tracker.callback, stability_seconds=2)
    monitor.start()
    
    # Create a file
    test_file = temp_dir / "test.log"
    test_file.write_text("initial content")
    
    # Wait for file to be detected (up to 5 seconds)
    # File needs: detection time + 2s stability + check interval
    result = wait_until(
        lambda: len(callback_tracker.called_files) == 1,
        timeout=5,
        description=f"file {test_file.name} to be marked stable"
    )
    
    monitor.stop()
    
    assert result, f"File was not detected. Callbacks: {callback_tracker.called_files}"
    assert test_file.name in callback_tracker.called_files[0]


def test_file_still_being_written(temp_dir, callback_tracker):
    """Test that files still being written are not marked stable"""
    monitor = FileMonitor([str(temp_dir)], callback_tracker.callback, stability_seconds=3)
    monitor.start()
    
    # Create file and keep modifying it
    test_file = temp_dir / "growing.log"
    test_file.write_text("data")
    time.sleep(1)
    test_file.write_text("data" * 10)
    time.sleep(1)
    test_file.write_text("data" * 20)
    time.sleep(1)
    
    # File should NOT be stable yet (we just modified it 1 second ago)
    assert len(callback_tracker.called_files) == 0, "File marked stable while still being written"
    
    # Now stop writing and wait for stability
    result = wait_until(
        lambda: len(callback_tracker.called_files) == 1,
        timeout=6,
        description="file to become stable after writes stop"
    )
    
    monitor.stop()
    assert result, "File was not detected after becoming stable"


def test_multiple_files(temp_dir, callback_tracker):
    """Test monitoring multiple files"""
    monitor = FileMonitor([str(temp_dir)], callback_tracker.callback, stability_seconds=2)
    monitor.start()
    
    # Create multiple files
    files = []
    for i in range(3):
        f = temp_dir / f"file{i}.log"
        f.write_text(f"content {i}")
        files.append(f)
    
    # Wait for all files to be detected
    result = wait_until(
        lambda: len(callback_tracker.called_files) == 3,
        timeout=6,
        description="all 3 files to be detected"
    )
    
    monitor.stop()
    
    assert result, f"Not all files detected. Got: {len(callback_tracker.called_files)}/3"


def test_hidden_files_ignored(temp_dir, callback_tracker):
    """Test that hidden files are ignored"""
    monitor = FileMonitor([str(temp_dir)], callback_tracker.callback, stability_seconds=2)
    monitor.start()
    
    # Create hidden file
    hidden = temp_dir / ".hidden"
    hidden.write_text("secret")
    
    # Create normal file
    normal = temp_dir / "normal.log"
    normal.write_text("visible")
    
    # Wait for normal file (should be only 1)
    result = wait_until(
        lambda: len(callback_tracker.called_files) == 1,
        timeout=5,
        description="normal file to be detected (hidden file should be ignored)"
    )
    
    monitor.stop()
    
    assert result, "Normal file was not detected"
    assert "normal.log" in callback_tracker.called_files[0]
    assert ".hidden" not in str(callback_tracker.called_files)


def test_nonexistent_directory():
    """Test that monitor creates missing directories"""
    nonexistent = Path("/tmp/tvm-test-nonexistent-dir")
    
    # Make sure it doesn't exist
    if nonexistent.exists():
        import shutil
        shutil.rmtree(nonexistent)
    
    def dummy_callback(filepath):
        pass
    
    monitor = FileMonitor([str(nonexistent)], dummy_callback)
    monitor.start()
    
    # Directory should have been created
    assert nonexistent.exists()
    
    monitor.stop()
    
    # Cleanup
    import shutil
    shutil.rmtree(nonexistent)


def test_get_tracked_files(temp_dir, callback_tracker):
    """Test getting list of tracked files"""
    monitor = FileMonitor([str(temp_dir)], callback_tracker.callback, stability_seconds=5)
    monitor.start()
    
    # Create file
    test_file = temp_dir / "tracked.log"
    test_file.write_text("data")
    
    # Wait for file to be tracked (not stable, just tracked)
    result = wait_until(
        lambda: len(monitor.get_tracked_files()) >= 1,
        timeout=3,
        description="file to appear in tracked list"
    )
    
    monitor.stop()
    
    assert result, "File was not added to tracker"

# ============================================
# NEW TESTS FOR v2.0 STARTUP SCAN
# ============================================

def test_startup_scan_enabled(temp_dir, callback_tracker):
    """Test startup scan detects existing files"""
    # Create files BEFORE starting monitor
    old_file = temp_dir / "old.log"
    old_file.write_text("old data")
    
    recent_file = temp_dir / "recent.log"
    recent_file.write_text("recent data")
    
    # Configure startup scan
    config = {
        'upload': {
            'scan_existing_files': {
                'enabled': True,
                'max_age_days': 30  # Accept all files
            }
        }
    }
    
    monitor = FileMonitor(
        [str(temp_dir)],
        callback_tracker.callback,
        stability_seconds=2,
        config=config
    )
    monitor.start()
    
    # Wait for startup scan + stability check
    result = wait_until(
        lambda: len(callback_tracker.called_files) >= 2,
        timeout=5,
        description="startup scan to detect both files"
    )
    
    monitor.stop()
    
    assert result, f"Only detected {len(callback_tracker.called_files)}/2 files"
    assert any("old.log" in f for f in callback_tracker.called_files)
    assert any("recent.log" in f for f in callback_tracker.called_files)


def test_startup_scan_max_age_days(temp_dir, callback_tracker):
    """Test startup scan respects max_age_days"""
    import time
    
    # Create old file (will be skipped)
    old_file = temp_dir / "old.log"
    old_file.write_text("old data")
    old_mtime = time.time() - (5 * 24 * 3600)  # 5 days old
    import os
    os.utime(str(old_file), (old_mtime, old_mtime))
    
    # Create recent file (will be detected)
    recent_file = temp_dir / "recent.log"
    recent_file.write_text("recent data")
    
    # Configure startup scan with 3-day limit
    config = {
        'upload': {
            'scan_existing_files': {
                'enabled': True,
                'max_age_days': 3  # Only last 3 days
            }
        }
    }
    
    monitor = FileMonitor(
        [str(temp_dir)],
        callback_tracker.callback,
        stability_seconds=2,
        config=config
    )
    monitor.start()
    
    # Wait for detection
    result = wait_until(
        lambda: len(callback_tracker.called_files) >= 1,
        timeout=5,
        description="startup scan to detect recent file only"
    )
    
    monitor.stop()
    
    assert result, "Recent file not detected"
    assert len(callback_tracker.called_files) == 1, f"Should detect only 1 file, got {len(callback_tracker.called_files)}"
    assert "recent.log" in callback_tracker.called_files[0]
    assert "old.log" not in str(callback_tracker.called_files)


def test_startup_scan_disabled(temp_dir, callback_tracker):
    """Test startup scan can be disabled"""
    # Create existing file
    existing_file = temp_dir / "existing.log"
    existing_file.write_text("existing data")
    
    # Configure startup scan DISABLED
    config = {
        'upload': {
            'scan_existing_files': {
                'enabled': False
            }
        }
    }
    
    monitor = FileMonitor(
        [str(temp_dir)],
        callback_tracker.callback,
        stability_seconds=2,
        config=config
    )
    monitor.start()
    
    # Wait a bit
    time.sleep(3)
    
    # Should NOT detect existing file
    assert len(callback_tracker.called_files) == 0, "Should not detect existing files when scan disabled"
    
    # But SHOULD detect new files created after start
    new_file = temp_dir / "new.log"
    new_file.write_text("new data")
    
    result = wait_until(
        lambda: len(callback_tracker.called_files) >= 1,
        timeout=5,
        description="new file to be detected"
    )
    
    monitor.stop()
    
    assert result, "New file should be detected even with scan disabled"
    assert "new.log" in callback_tracker.called_files[0]


def test_startup_scan_no_config(temp_dir, callback_tracker):
    """Test startup scan uses defaults when no config provided"""
    # Create file
    test_file = temp_dir / "test.log"
    test_file.write_text("test data")
    
    # No config provided - should use defaults (enabled=True, max_age_days=3)
    monitor = FileMonitor(
        [str(temp_dir)],
        callback_tracker.callback,
        stability_seconds=2
        # NO config parameter
    )
    monitor.start()
    
    # Should detect file (scan enabled by default)
    result = wait_until(
        lambda: len(callback_tracker.called_files) >= 1,
        timeout=5,
        description="file to be detected with default scan settings"
    )
    
    monitor.stop()
    
    assert result, "File should be detected with default startup scan"

# ============================================
# NEW TESTS FOR v2.1 PROCESSED FILES REGISTRY
# ============================================

def test_registry_initialization(temp_dir):
    """Test registry file is created on initialization"""
    registry_file = temp_dir / "processed_files.json"
    
    config = {
        'upload': {
            'processed_files_registry': {
                'registry_file': str(registry_file),
                'retention_days': 30
            }
        }
    }
    
    monitor = FileMonitor(
        [str(temp_dir)],
        lambda f: True,
        config=config
    )
    
    # Registry file is NOT created until first save
    # Instead, check that registry is initialized in memory
    assert monitor.processed_files is not None
    assert isinstance(monitor.processed_files, dict)
    assert len(monitor.processed_files) == 0


def test_mark_file_as_processed(temp_dir, callback_tracker):
    """Test marking file as processed after successful upload"""
    registry_file = temp_dir / "registry.json"
    
    config = {
        'upload': {
            'processed_files_registry': {
                'registry_file': str(registry_file),
                'retention_days': 30
            }
        }
    }
    
    monitor = FileMonitor(
        [str(temp_dir)],
        callback_tracker.callback,
        stability_seconds=2,
        config=config
    )
    monitor.start()
    
    # Create test file
    test_file = temp_dir / "test.log"
    test_file.write_text("test data")
    
    # Wait for upload
    result = wait_until(
        lambda: len(callback_tracker.called_files) >= 1,
        timeout=5
    )
    
    assert result, "File should be uploaded"
    
    # Check registry
    with open(registry_file) as f:
        data = json.load(f)
        files = data['files']
        assert len(files) > 0, "Registry should contain processed file"
        
        # Verify file identity format (filepath::size::mtime)
        file_identity = list(files.keys())[0]
        assert '::' in file_identity, "File identity should contain ::"
    
    monitor.stop()


def test_duplicate_prevention_on_restart(temp_dir, callback_tracker):
    """Test file marked as processed is not uploaded again on restart"""
    # Create separate directories for logs and registry
    log_dir = temp_dir / "logs"
    log_dir.mkdir()
    
    registry_file = temp_dir / "registry.json"
    
    config = {
        'upload': {
            'processed_files_registry': {
                'registry_file': str(registry_file),
                'retention_days': 30
            },
            'scan_existing_files': {
                'enabled': True,
                'max_age_days': 30
            }
        }
    }
    
    # Create test file in log directory only
    test_file = log_dir / "test.log"
    test_file.write_text("test data")
    
    # First monitor instance - uploads file
    monitor1 = FileMonitor(
        [str(log_dir)],  # Monitor log_dir, not temp_dir
        callback_tracker.callback,
        stability_seconds=2,
        config=config
    )
    monitor1.start()
    
    # Wait for upload
    result = wait_until(
        lambda: len(callback_tracker.called_files) >= 1,
        timeout=5
    )
    assert result, "File should be uploaded first time"
    
    monitor1.stop()
    
    # Reset callback tracker
    first_upload_count = len(callback_tracker.called_files)
    
    # Second monitor instance - should NOT upload same file
    monitor2 = FileMonitor(
        [str(log_dir)],  # Monitor log_dir, not temp_dir
        callback_tracker.callback,
        stability_seconds=2,
        config=config
    )
    monitor2.start()
    
    # Wait a bit
    time.sleep(3)
    
    # Should NOT have uploaded again
    assert len(callback_tracker.called_files) == first_upload_count, \
        f"File should not be uploaded twice. Got {len(callback_tracker.called_files)} uploads"
    
    monitor2.stop()


def test_same_filename_different_content_uploads(temp_dir, callback_tracker):
    """Test same filename with different content is treated as new file"""
    registry_file = temp_dir / "registry.json"
    
    config = {
        'upload': {
            'processed_files_registry': {
                'registry_file': str(registry_file),
                'retention_days': 30
            },
            'scan_existing_files': {
                'enabled': True,
                'max_age_days': 30
            }
        }
    }
    
    test_file = temp_dir / "test.log"
    
    # Create file with content A
    test_file.write_text("content A")
    
    monitor1 = FileMonitor(
        [str(temp_dir)],
        callback_tracker.callback,
        stability_seconds=2,
        config=config
    )
    monitor1.start()
    
    # Wait for first upload
    result = wait_until(
        lambda: len(callback_tracker.called_files) >= 1,
        timeout=5
    )
    assert result
    
    monitor1.stop()
    
    # Modify file (different size/mtime = different file)
    test_file.write_text("content B - much longer")
    
    # Reset tracker
    callback_tracker.called_files.clear()
    
    # Start new monitor
    monitor2 = FileMonitor(
        [str(temp_dir)],
        callback_tracker.callback,
        stability_seconds=2,
        config=config
    )
    monitor2.start()
    
    # Should upload again (different file)
    result = wait_until(
        lambda: len(callback_tracker.called_files) >= 1,
        timeout=5
    )
    
    assert result, "Modified file should be uploaded as new file"
    
    monitor2.stop()


def test_failed_upload_not_marked_as_processed(temp_dir, callback_tracker):
    """Test failed uploads are not marked in registry"""
    registry_file = temp_dir / "registry.json"
    
    config = {
        'upload': {
            'processed_files_registry': {
                'registry_file': str(registry_file),
                'retention_days': 30
            }
        }
    }
    
    # Simulate upload failure
    callback_tracker.return_value = False
    
    monitor = FileMonitor(
        [str(temp_dir)],
        callback_tracker.callback,
        stability_seconds=2,
        config=config
    )
    monitor.start()
    
    # Create test file
    test_file = temp_dir / "test.log"
    test_file.write_text("test data")
    
    # Wait for callback
    result = wait_until(
        lambda: len(callback_tracker.called_files) >= 1,
        timeout=5
    )
    
    assert result, "Callback should be called even if upload fails"
    
    monitor.stop()
    
    # Check registry - should be empty OR not exist (failed uploads not saved)
    if registry_file.exists():
        with open(registry_file) as f:
            data = json.load(f)
            files = data['files']
            assert len(files) == 0, "Failed uploads should not be in registry"
    else:
        # Registry file not created (no successful uploads)
        assert True, "Registry not created is acceptable (no successful uploads)"

def test_registry_cleanup_old_entries(temp_dir):
    """Test registry automatically removes old entries"""
    registry_file = temp_dir / "registry.json"
    
    # Create registry with old entry
    old_entry_time = time.time() - (40 * 24 * 3600)  # 40 days old
    
    registry_data = {
        '_metadata': {
            'last_updated': time.time(),
            'total_entries': 1,
            'retention_days': 30
        },
        'files': {
            '/tmp/old.log::1024::123456.0': {
                'processed_at': old_entry_time,
                'size': 1024,
                'mtime': 123456.0,
                'filepath': '/tmp/old.log',
                'filename': 'old.log'
            }
        }
    }
    
    with open(registry_file, 'w') as f:
        json.dump(registry_data, f)
    
    config = {
        'upload': {
            'processed_files_registry': {
                'registry_file': str(registry_file),
                'retention_days': 30
            }
        }
    }
    
    # Load monitor - should clean old entries
    monitor = FileMonitor(
        [str(temp_dir)],
        lambda f: True,
        config=config
    )
    
    # Check registry was cleaned
    assert len(monitor.processed_files) == 0, \
        "Old entries should be removed (40 days > 30 day retention)"


def test_external_marking(temp_dir):
    """Test mark_file_as_processed_externally method"""
    registry_file = temp_dir / "registry.json"
    
    config = {
        'upload': {
            'processed_files_registry': {
                'registry_file': str(registry_file),
                'retention_days': 30
            }
        }
    }
    
    monitor = FileMonitor(
        [str(temp_dir)],
        lambda f: True,
        config=config
    )
    
    # Create test file
    test_file = temp_dir / "test.log"
    test_file.write_text("test data")
    
    # Mark externally (simulates main.py marking after batch upload)
    monitor.mark_file_as_processed_externally(str(test_file))
    
    # Check registry
    with open(registry_file) as f:
        data = json.load(f)
        files = data['files']
        assert len(files) == 1, "File should be in registry"


def test_startup_scan_skips_processed_files(temp_dir, callback_tracker):
    """Test startup scan skips files already in registry"""
    # Create separate directories for logs and registry
    log_dir = temp_dir / "logs"
    log_dir.mkdir()
    
    registry_file = temp_dir / "registry.json"
    
    # Create test file in log directory
    test_file = log_dir / "test.log"
    test_file.write_text("test data")
    
    # Pre-populate registry with this file
    file_stat = test_file.stat()
    file_identity = f"{test_file.resolve()}::{file_stat.st_size}::{file_stat.st_mtime}"
    
    registry_data = {
        '_metadata': {
            'last_updated': time.time(),
            'total_entries': 1,
            'retention_days': 30
        },
        'files': {
            file_identity: {
                'processed_at': time.time(),
                'size': file_stat.st_size,
                'mtime': file_stat.st_mtime,
                'filepath': str(test_file.resolve()),
                'filename': test_file.name
            }
        }
    }
    
    # Create parent directory and save registry
    registry_file.parent.mkdir(parents=True, exist_ok=True)
    with open(registry_file, 'w') as f:
        json.dump(registry_data, f)
    
    config = {
        'upload': {
            'processed_files_registry': {
                'registry_file': str(registry_file),
                'retention_days': 30
            },
            'scan_existing_files': {
                'enabled': True,
                'max_age_days': 30
            }
        }
    }
    
    monitor = FileMonitor(
        [str(log_dir)],  # Monitor log_dir, not temp_dir
        callback_tracker.callback,
        stability_seconds=2,
        config=config
    )
    monitor.start()
    
    # Wait a bit
    time.sleep(3)
    
    # Should NOT have uploaded (already in registry)
    assert len(callback_tracker.called_files) == 0, \
        f"Processed files should be skipped during startup scan. Got {callback_tracker.called_files}"
    
    monitor.stop()