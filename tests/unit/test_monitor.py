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


@pytest.fixture
def monitor_config(tmp_path):
    """Create monitor config with temporary registry file for testing

    Uses a separate tmp_path to avoid registry file being detected as a log file.
    """
    import tempfile
    registry_dir = tempfile.mkdtemp()
    return {
        'upload': {
            'processed_files_registry': {
                'registry_file': str(Path(registry_dir) / 'test_registry.json'),
                'retention_days': 30
            }
        }
    }


def test_monitor_initialization(temp_dir, monitor_config):
    """Test file monitor can be initialized"""
    def dummy_callback(filepath):
        pass

    monitor = FileMonitor([str(temp_dir)], dummy_callback, config=monitor_config)

    assert monitor.stability_seconds == 60
    assert len(monitor.directories) == 1


def test_monitor_start_stop(temp_dir, monitor_config):
    """Test monitor can start and stop"""
    def dummy_callback(filepath):
        pass
    
    monitor = FileMonitor([str(temp_dir)], dummy_callback, config=monitor_config)
    
    monitor.start()
    assert monitor._running is True
    
    monitor.stop()
    assert monitor._running is False


def test_file_stability_detection(temp_dir, callback_tracker, monitor_config):
    """Test that stable files are detected"""
    monitor = FileMonitor([str(temp_dir)], callback_tracker.callback, stability_seconds=2, config=monitor_config)
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


def test_file_still_being_written(temp_dir, callback_tracker, monitor_config):
    """Test that files still being written are not marked stable"""
    monitor = FileMonitor([str(temp_dir)], callback_tracker.callback, stability_seconds=3, config=monitor_config)
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


def test_multiple_files(temp_dir, callback_tracker, monitor_config):
    """Test monitoring multiple files"""
    monitor = FileMonitor([str(temp_dir)], callback_tracker.callback, stability_seconds=2, config=monitor_config)
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


def test_hidden_files_ignored(temp_dir, callback_tracker, monitor_config):
    """Test that hidden files are ignored"""
    monitor = FileMonitor([str(temp_dir)], callback_tracker.callback, stability_seconds=2, config=monitor_config)
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


def test_nonexistent_directory(monitor_config):
    """Test that monitor creates missing directories"""
    nonexistent = Path("/tmp/tvm-test-nonexistent-dir")
    
    # Make sure it doesn't exist
    if nonexistent.exists():
        import shutil
        shutil.rmtree(nonexistent)
    
    def dummy_callback(filepath):
        pass
    
    monitor = FileMonitor([str(nonexistent)], dummy_callback, config=monitor_config)
    monitor.start()
    
    # Directory should have been created
    assert nonexistent.exists()
    
    monitor.stop()
    
    # Cleanup
    import shutil
    shutil.rmtree(nonexistent)


def test_get_tracked_files(temp_dir, callback_tracker, monitor_config):
    """Test getting list of tracked files"""
    monitor = FileMonitor([str(temp_dir)], callback_tracker.callback, stability_seconds=5, config=monitor_config)
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

def test_startup_scan_enabled(temp_dir, callback_tracker, monitor_config):
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
            },
            'processed_files_registry': {
                'registry_file': '/tmp/test_registry_' + str(id(temp_dir)) + '.json',
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


def test_startup_scan_max_age_days(temp_dir, callback_tracker, monitor_config):
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
            },
            'processed_files_registry': {
                'registry_file': '/tmp/test_registry_' + str(id(temp_dir)) + '.json',
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


def test_startup_scan_disabled(temp_dir, callback_tracker, monitor_config):
    """Test startup scan can be disabled"""
    # Create existing file
    existing_file = temp_dir / "existing.log"
    existing_file.write_text("existing data")
    
    # Configure startup scan DISABLED
    config = {
        'upload': {
            'scan_existing_files': {
                'enabled': False
            },
            'processed_files_registry': {
                'registry_file': '/tmp/test_registry_' + str(id(temp_dir)) + '.json',
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


def test_startup_scan_no_config(temp_dir, callback_tracker, monitor_config):
    """Test startup scan uses defaults when no config provided"""
    # Create file
    test_file = temp_dir / "test.log"
    test_file.write_text("test data")
    
    # Use monitor_config for registry path only - startup scan will use defaults (enabled=True, max_age_days=3)
    monitor = FileMonitor(
        [str(temp_dir)],
        callback_tracker.callback,
        stability_seconds=2,
        config=monitor_config  # Only for registry path, startup scan uses defaults
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

def test_registry_initialization(temp_dir, monitor_config):
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


def test_mark_file_as_processed(temp_dir, callback_tracker, monitor_config):
    """Test marking file as processed after successful upload"""
    # Separate directories: logs vs registry (prevents registry.json from being detected as log file)
    log_dir = temp_dir / "logs"
    log_dir.mkdir()

    registry_file = temp_dir / "registry.json"  # Registry in parent, logs in subdir

    config = {
        'upload': {
            'processed_files_registry': {
                'registry_file': str(registry_file),
                'retention_days': 30
            }
        }
    }

    monitor = FileMonitor(
        [str(log_dir)],  # Monitor logs directory, not temp_dir
        callback_tracker.callback,
        stability_seconds=2,
        config=config
    )
    monitor.start()

    # Create test file in logs directory
    test_file = log_dir / "test.log"
    test_file.write_text("test data")
    
    # Wait for upload callback
    result = wait_until(
        lambda: len(callback_tracker.called_files) >= 1,
        timeout=5,
        description="callback to be called"
    )
    assert result, "File should be uploaded"

    # Wait for registry to be written with file entry
    # Callback is invoked BEFORE _mark_file_processed() completes,
    # so we need to wait for the registry file to actually contain the entry
    def registry_contains_file():
        if not registry_file.exists():
            return False
        try:
            with open(registry_file) as f:
                data = json.load(f)
                return len(data.get('files', {})) > 0
        except (json.JSONDecodeError, FileNotFoundError):
            return False

    result = wait_until(
        registry_contains_file,
        timeout=3,
        description="registry file to contain processed file"
    )
    assert result, "Registry should contain processed file after callback completes"

    # Verify registry contents
    with open(registry_file) as f:
        data = json.load(f)
        files = data['files']
        assert len(files) > 0, "Registry should contain processed file"

        # Verify file identity format (filepath::size::mtime)
        file_identity = list(files.keys())[0]
        assert '::' in file_identity, "File identity should contain ::"
    
    monitor.stop()


def test_duplicate_prevention_on_restart(temp_dir, callback_tracker, monitor_config):
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


def test_same_filename_different_content_uploads(temp_dir, callback_tracker, monitor_config):
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


def test_failed_upload_not_marked_as_processed(temp_dir, callback_tracker, monitor_config):
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


def test_external_marking(temp_dir, monitor_config):
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


def test_startup_scan_skips_processed_files(temp_dir, callback_tracker, monitor_config):
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


# ============================================
# COMPREHENSIVE TESTS FOR RECURSIVE MONITORING
# ============================================

def test_recursive_monitoring_enabled(temp_dir, callback_tracker, monitor_config):
    """Test recursive monitoring detects files in subdirectories"""
    # Create subdirectory structure
    subdir1 = temp_dir / "subdir1"
    subdir1.mkdir()
    subdir2 = subdir1 / "subdir2"
    subdir2.mkdir()

    config = {
        'log_directories': [{
            'path': str(temp_dir),
            'source': 'test',
            'recursive': True
        }],
        'upload': {
            'processed_files_registry': {
                'registry_file': '/tmp/test_registry_' + str(id(temp_dir)) + '.json',
                'retention_days': 30
            },
            'scan_existing_files': {
                'enabled': True,
                'max_age_days': 30
            }
        }
    }

    # Create files at different depths
    file_root = temp_dir / "root.log"
    file_root.write_text("root level")

    file_sub1 = subdir1 / "sub1.log"
    file_sub1.write_text("subdir1 level")

    file_sub2 = subdir2 / "sub2.log"
    file_sub2.write_text("subdir2 level")

    monitor = FileMonitor(
        [str(temp_dir)],
        callback_tracker.callback,
        stability_seconds=2,
        config=config
    )
    monitor.start()

    # Should detect all 3 files
    result = wait_until(
        lambda: len(callback_tracker.called_files) >= 3,
        timeout=6,
        description="all 3 files in recursive structure"
    )

    monitor.stop()

    assert result, f"Should detect 3 files, got {len(callback_tracker.called_files)}"

    # Verify all files were detected
    files_str = str(callback_tracker.called_files)
    assert "root.log" in files_str
    assert "sub1.log" in files_str
    assert "sub2.log" in files_str


def test_recursive_monitoring_disabled(temp_dir, callback_tracker, monitor_config):
    """Test non-recursive monitoring ignores subdirectories"""
    # Create subdirectory
    subdir = temp_dir / "subdir"
    subdir.mkdir()

    config = {
        'log_directories': [{
            'path': str(temp_dir),
            'source': 'test',
            'recursive': False
        }],
        'upload': {
            'processed_files_registry': {
                'registry_file': '/tmp/test_registry_' + str(id(temp_dir)) + '.json',
                'retention_days': 30
            },
            'scan_existing_files': {
                'enabled': True,
                'max_age_days': 30
            }
        }
    }

    # Create files in root and subdirectory
    file_root = temp_dir / "root.log"
    file_root.write_text("root level")

    file_sub = subdir / "sub.log"
    file_sub.write_text("subdirectory level")

    monitor = FileMonitor(
        [str(temp_dir)],
        callback_tracker.callback,
        stability_seconds=2,
        config=config
    )
    monitor.start()

    # Should detect only root file
    result = wait_until(
        lambda: len(callback_tracker.called_files) >= 1,
        timeout=5,
        description="root level file only"
    )

    monitor.stop()

    assert result, "Should detect root file"
    assert len(callback_tracker.called_files) == 1, \
        f"Should detect only 1 file (root), got {len(callback_tracker.called_files)}"
    assert "root.log" in callback_tracker.called_files[0]
    assert "sub.log" not in str(callback_tracker.called_files)


def test_recursive_default_is_true(temp_dir, callback_tracker, monitor_config):
    """Test recursive defaults to True when not specified"""
    subdir = temp_dir / "subdir"
    subdir.mkdir()

    config = {
        'log_directories': [{
            'path': str(temp_dir),
            'source': 'test'
            # No recursive specified - should default to True
        }],
        'upload': {
            'processed_files_registry': {
                'registry_file': '/tmp/test_registry_' + str(id(temp_dir)) + '.json',
                'retention_days': 30
            },
            'scan_existing_files': {
                'enabled': True,
                'max_age_days': 30
            }
        }
    }

    file_sub = subdir / "sub.log"
    file_sub.write_text("subdirectory file")

    monitor = FileMonitor(
        [str(temp_dir)],
        callback_tracker.callback,
        stability_seconds=2,
        config=config
    )
    monitor.start()

    # Should detect subdirectory file (recursive=True by default)
    result = wait_until(
        lambda: len(callback_tracker.called_files) >= 1,
        timeout=5,
        description="subdirectory file with default recursive"
    )

    monitor.stop()

    assert result, "Should detect subdirectory file (recursive defaults to True)"
    assert "sub.log" in callback_tracker.called_files[0]


def test_mixed_recursive_configurations(temp_dir, callback_tracker, monitor_config):
    """Test multiple directories with different recursive settings"""
    # Create two separate directories
    dir1 = temp_dir / "dir1"
    dir1.mkdir()
    dir1_sub = dir1 / "subdir"
    dir1_sub.mkdir()

    dir2 = temp_dir / "dir2"
    dir2.mkdir()
    dir2_sub = dir2 / "subdir"
    dir2_sub.mkdir()

    config = {
        'log_directories': [
            {
                'path': str(dir1),
                'source': 'source1',
                'recursive': True  # Recursive enabled
            },
            {
                'path': str(dir2),
                'source': 'source2',
                'recursive': False  # Recursive disabled
            }
        ],
        'upload': {
            'processed_files_registry': {
                'registry_file': '/tmp/test_registry_' + str(id(temp_dir)) + '.json',
                'retention_days': 30
            },
            'scan_existing_files': {
                'enabled': True,
                'max_age_days': 30
            }
        }
    }

    # Create files in both directories and subdirectories
    file_dir1_root = dir1 / "root1.log"
    file_dir1_root.write_text("dir1 root")

    file_dir1_sub = dir1_sub / "sub1.log"
    file_dir1_sub.write_text("dir1 subdirectory")

    file_dir2_root = dir2 / "root2.log"
    file_dir2_root.write_text("dir2 root")

    file_dir2_sub = dir2_sub / "sub2.log"
    file_dir2_sub.write_text("dir2 subdirectory")

    monitor = FileMonitor(
        [str(dir1), str(dir2)],
        callback_tracker.callback,
        stability_seconds=2,
        config=config
    )
    monitor.start()

    # Should detect 3 files: dir1/root, dir1/sub, dir2/root
    # Should NOT detect: dir2/sub (recursive=False)
    result = wait_until(
        lambda: len(callback_tracker.called_files) >= 3,
        timeout=6,
        description="3 files from mixed recursive configs"
    )

    monitor.stop()

    assert result, f"Should detect 3 files, got {len(callback_tracker.called_files)}"

    files_str = str(callback_tracker.called_files)
    assert "root1.log" in files_str
    assert "sub1.log" in files_str  # Should be detected (dir1 is recursive)
    assert "root2.log" in files_str
    assert "sub2.log" not in files_str  # Should NOT be detected (dir2 is non-recursive)


# ============================================
# COMPREHENSIVE TESTS FOR PATTERN MATCHING
# ============================================

def test_pattern_matching_simple(temp_dir, callback_tracker, monitor_config):
    """Test simple pattern matching filters files correctly"""
    config = {
        'log_directories': [{
            'path': str(temp_dir),
            'source': 'test',
            'pattern': '*.log'
        }],
        'upload': {
            'processed_files_registry': {
                'registry_file': '/tmp/test_registry_' + str(id(temp_dir)) + '.json',
                'retention_days': 30
            },
            'scan_existing_files': {
                'enabled': True,
                'max_age_days': 30
            }
        }
    }

    # Create files with different extensions
    log_file = temp_dir / "test.log"
    log_file.write_text("log file")

    txt_file = temp_dir / "test.txt"
    txt_file.write_text("text file")

    tmp_file = temp_dir / "test.tmp"
    tmp_file.write_text("temp file")

    monitor = FileMonitor(
        [str(temp_dir)],
        callback_tracker.callback,
        stability_seconds=2,
        config=config
    )
    monitor.start()

    # Should detect only .log file
    result = wait_until(
        lambda: len(callback_tracker.called_files) >= 1,
        timeout=5,
        description=".log file with pattern matching"
    )

    monitor.stop()

    assert result, "Should detect .log file"
    assert len(callback_tracker.called_files) == 1, \
        f"Should detect only 1 file (.log), got {len(callback_tracker.called_files)}"
    assert "test.log" in callback_tracker.called_files[0]
    assert ".txt" not in str(callback_tracker.called_files)
    assert ".tmp" not in str(callback_tracker.called_files)


def test_pattern_matching_prefix(temp_dir, callback_tracker, monitor_config):
    """Test pattern matching with prefix (e.g., syslog*)"""
    config = {
        'log_directories': [{
            'path': str(temp_dir),
            'source': 'syslog',
            'pattern': 'syslog*'
        }],
        'upload': {
            'processed_files_registry': {
                'registry_file': '/tmp/test_registry_' + str(id(temp_dir)) + '.json',
                'retention_days': 30
            },
            'scan_existing_files': {
                'enabled': True,
                'max_age_days': 30
            }
        }
    }

    # Create syslog files
    syslog = temp_dir / "syslog"
    syslog.write_text("current syslog")

    syslog1 = temp_dir / "syslog.1"
    syslog1.write_text("rotated syslog 1")

    syslog2_gz = temp_dir / "syslog.2.gz"
    syslog2_gz.write_text("rotated syslog 2")

    # Create non-matching file
    other = temp_dir / "messages"
    other.write_text("other log")

    monitor = FileMonitor(
        [str(temp_dir)],
        callback_tracker.callback,
        stability_seconds=2,
        config=config
    )
    monitor.start()

    # Should detect 3 syslog* files
    result = wait_until(
        lambda: len(callback_tracker.called_files) >= 3,
        timeout=5,
        description="all syslog* files"
    )

    monitor.stop()

    assert result, f"Should detect 3 syslog files, got {len(callback_tracker.called_files)}"

    files_str = str(callback_tracker.called_files)
    assert "syslog" in files_str or "/syslog" in files_str
    assert "syslog.1" in files_str
    assert "syslog.2.gz" in files_str
    assert "messages" not in files_str


def test_pattern_matching_no_pattern_uploads_all(temp_dir, callback_tracker, monitor_config):
    """Test when no pattern is specified, all files are uploaded"""
    config = {
        'log_directories': [{
            'path': str(temp_dir),
            'source': 'test'
            # No pattern specified
        }],
        'upload': {
            'processed_files_registry': {
                'registry_file': '/tmp/test_registry_' + str(id(temp_dir)) + '.json',
                'retention_days': 30
            },
            'scan_existing_files': {
                'enabled': True,
                'max_age_days': 30
            }
        }
    }

    # Create various files
    log_file = temp_dir / "test.log"
    log_file.write_text("log")

    txt_file = temp_dir / "test.txt"
    txt_file.write_text("txt")

    mcap_file = temp_dir / "data.mcap"
    mcap_file.write_text("mcap")

    monitor = FileMonitor(
        [str(temp_dir)],
        callback_tracker.callback,
        stability_seconds=2,
        config=config
    )
    monitor.start()

    # Should detect all files
    result = wait_until(
        lambda: len(callback_tracker.called_files) >= 3,
        timeout=5,
        description="all files when no pattern specified"
    )

    monitor.stop()

    assert result, f"Should detect all 3 files, got {len(callback_tracker.called_files)}"


def test_pattern_matching_with_recursive(temp_dir, callback_tracker, monitor_config):
    """Test pattern matching works in recursive subdirectories"""
    # Create subdirectory structure
    subdir = temp_dir / "subdir"
    subdir.mkdir()

    config = {
        'log_directories': [{
            'path': str(temp_dir),
            'source': 'test',
            'pattern': '*.log',
            'recursive': True
        }],
        'upload': {
            'processed_files_registry': {
                'registry_file': '/tmp/test_registry_' + str(id(temp_dir)) + '.json',
                'retention_days': 30
            },
            'scan_existing_files': {
                'enabled': True,
                'max_age_days': 30
            }
        }
    }

    # Create .log files at different levels
    root_log = temp_dir / "root.log"
    root_log.write_text("root log")

    root_txt = temp_dir / "root.txt"
    root_txt.write_text("root txt")

    sub_log = subdir / "sub.log"
    sub_log.write_text("sub log")

    sub_txt = subdir / "sub.txt"
    sub_txt.write_text("sub txt")

    monitor = FileMonitor(
        [str(temp_dir)],
        callback_tracker.callback,
        stability_seconds=2,
        config=config
    )
    monitor.start()

    # Should detect 2 .log files (root and subdirectory)
    result = wait_until(
        lambda: len(callback_tracker.called_files) >= 2,
        timeout=5,
        description="2 .log files in recursive structure"
    )

    monitor.stop()

    assert result, f"Should detect 2 .log files, got {len(callback_tracker.called_files)}"
    assert len(callback_tracker.called_files) == 2, \
        f"Should detect exactly 2 files, got {len(callback_tracker.called_files)}"

    files_str = str(callback_tracker.called_files)
    assert "root.log" in files_str
    assert "sub.log" in files_str
    assert ".txt" not in files_str


def test_pattern_matching_multiple_directories(temp_dir, callback_tracker, monitor_config):
    """Test different patterns for different directories"""
    dir1 = temp_dir / "logs"
    dir1.mkdir()

    dir2 = temp_dir / "syslog"
    dir2.mkdir()

    config = {
        'log_directories': [
            {
                'path': str(dir1),
                'source': 'logs',
                'pattern': '*.log'
            },
            {
                'path': str(dir2),
                'source': 'syslog',
                'pattern': 'syslog*'
            }
        ],
        'upload': {
            'processed_files_registry': {
                'registry_file': '/tmp/test_registry_' + str(id(temp_dir)) + '.json',
                'retention_days': 30
            },
            'scan_existing_files': {
                'enabled': True,
                'max_age_days': 30
            }
        }
    }

    # Create files matching patterns
    dir1_log = dir1 / "app.log"
    dir1_log.write_text("app log")

    dir1_txt = dir1 / "app.txt"
    dir1_txt.write_text("app txt - should not match")

    dir2_syslog = dir2 / "syslog"
    dir2_syslog.write_text("syslog")

    dir2_messages = dir2 / "messages"
    dir2_messages.write_text("messages - should not match")

    monitor = FileMonitor(
        [str(dir1), str(dir2)],
        callback_tracker.callback,
        stability_seconds=2,
        config=config
    )
    monitor.start()

    # Should detect 2 files: app.log, syslog
    result = wait_until(
        lambda: len(callback_tracker.called_files) >= 2,
        timeout=5,
        description="2 files matching different patterns"
    )

    monitor.stop()

    assert result, f"Should detect 2 files, got {len(callback_tracker.called_files)}"
    assert len(callback_tracker.called_files) == 2, \
        f"Should detect exactly 2 files, got {len(callback_tracker.called_files)}"

    files_str = str(callback_tracker.called_files)
    assert "app.log" in files_str
    assert "syslog" in files_str or "/syslog" in files_str
    assert "app.txt" not in files_str
    assert "messages" not in files_str


def test_pattern_wildcard_complex(temp_dir, callback_tracker, monitor_config):
    """Test complex wildcard patterns"""
    config = {
        'log_directories': [{
            'path': str(temp_dir),
            'source': 'test',
            'pattern': 'test_*.mcap'
        }],
        'upload': {
            'processed_files_registry': {
                'registry_file': '/tmp/test_registry_' + str(id(temp_dir)) + '.json',
                'retention_days': 30
            },
            'scan_existing_files': {
                'enabled': True,
                'max_age_days': 30
            }
        }
    }

    # Create files
    match1 = temp_dir / "test_2024.mcap"
    match1.write_text("match")

    match2 = temp_dir / "test_run1.mcap"
    match2.write_text("match")

    no_match1 = temp_dir / "data.mcap"
    no_match1.write_text("no match")

    no_match2 = temp_dir / "test.log"
    no_match2.write_text("no match")

    monitor = FileMonitor(
        [str(temp_dir)],
        callback_tracker.callback,
        stability_seconds=2,
        config=config
    )
    monitor.start()

    # Should detect 2 files matching test_*.mcap
    result = wait_until(
        lambda: len(callback_tracker.called_files) >= 2,
        timeout=5,
        description="files matching test_*.mcap"
    )

    monitor.stop()

    assert result, f"Should detect 2 files, got {len(callback_tracker.called_files)}"
    assert len(callback_tracker.called_files) == 2

    files_str = str(callback_tracker.called_files)
    assert "test_2024.mcap" in files_str
    assert "test_run1.mcap" in files_str
    assert "data.mcap" not in files_str


# ============================================
# EDGE CASE TESTS
# ============================================

def test_deeply_nested_directories(temp_dir, callback_tracker, monitor_config):
    """Test monitoring deeply nested directory structures"""
    # Create 5 levels deep
    current = temp_dir
    for i in range(5):
        current = current / f"level{i}"
        current.mkdir()

    config = {
        'log_directories': [{
            'path': str(temp_dir),
            'source': 'test',
            'recursive': True
        }],
        'upload': {
            'processed_files_registry': {
                'registry_file': '/tmp/test_registry_' + str(id(temp_dir)) + '.json',
                'retention_days': 30
            },
            'scan_existing_files': {
                'enabled': True,
                'max_age_days': 30
            }
        }
    }

    # Create file at deepest level
    deep_file = current / "deep.log"
    deep_file.write_text("deep file")

    monitor = FileMonitor(
        [str(temp_dir)],
        callback_tracker.callback,
        stability_seconds=2,
        config=config
    )
    monitor.start()

    result = wait_until(
        lambda: len(callback_tracker.called_files) >= 1,
        timeout=5,
        description="deeply nested file"
    )

    monitor.stop()

    assert result, "Should detect file in deeply nested directory"
    assert "deep.log" in callback_tracker.called_files[0]


def test_symlinks_in_recursive_structure(temp_dir, callback_tracker, monitor_config):
    """Test that symlinks don't cause infinite loops in recursive monitoring"""
    import os

    # Create subdirectory
    subdir = temp_dir / "subdir"
    subdir.mkdir()

    # Create symlink pointing back to parent (potential infinite loop)
    symlink = subdir / "link_to_parent"
    try:
        os.symlink(str(temp_dir), str(symlink))
    except OSError:
        pytest.skip("Cannot create symlinks on this system")

    config = {
        'log_directories': [{
            'path': str(temp_dir),
            'source': 'test',
            'recursive': True
        }],
        'upload': {
            'processed_files_registry': {
                'registry_file': '/tmp/test_registry_' + str(id(temp_dir)) + '.json',
                'retention_days': 30
            },
            'scan_existing_files': {
                'enabled': True,
                'max_age_days': 30
            }
        }
    }

    # Create a regular file
    test_file = temp_dir / "test.log"
    test_file.write_text("test")

    # Should not crash or hang due to symlink loop
    monitor = FileMonitor(
        [str(temp_dir)],
        callback_tracker.callback,
        stability_seconds=2,
        config=config
    )
    monitor.start()

    result = wait_until(
        lambda: len(callback_tracker.called_files) >= 1,
        timeout=5,
        description="file detection without hanging on symlinks"
    )

    monitor.stop()

    assert result, "Should detect file without hanging on symlinks"


def test_file_created_in_new_subdirectory_while_running(temp_dir, callback_tracker, monitor_config):
    """Test that files in new subdirectories created after start are detected"""
    config = {
        'log_directories': [{
            'path': str(temp_dir),
            'source': 'test',
            'recursive': True
        }],
        'upload': {
            'processed_files_registry': {
                'registry_file': '/tmp/test_registry_' + str(id(temp_dir)) + '.json',
                'retention_days': 30
            },
            'scan_existing_files': {
                'enabled': False  # Disable startup scan
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

    # Create subdirectory after monitor starts
    time.sleep(0.5)
    new_subdir = temp_dir / "new_subdir"
    new_subdir.mkdir()

    # Create file in new subdirectory
    new_file = new_subdir / "new.log"
    new_file.write_text("new file in new subdir")

    result = wait_until(
        lambda: len(callback_tracker.called_files) >= 1,
        timeout=5,
        description="file in newly created subdirectory"
    )

    monitor.stop()

    assert result, "Should detect file in subdirectory created after monitor start"
    assert "new.log" in callback_tracker.called_files[0]


def test_empty_directory_no_errors(temp_dir, callback_tracker, monitor_config):
    """Test monitoring empty directory doesn't cause errors"""
    config = {
        'log_directories': [{
            'path': str(temp_dir),
            'source': 'test',
            'recursive': True
        }],
        'upload': {
            'processed_files_registry': {
                'registry_file': '/tmp/test_registry_' + str(id(temp_dir)) + '.json',
                'retention_days': 30
            },
            'scan_existing_files': {
                'enabled': True,
                'max_age_days': 30
            }
        }
    }

    # Start monitor on empty directory
    monitor = FileMonitor(
        [str(temp_dir)],
        callback_tracker.callback,
        stability_seconds=2,
        config=config
    )
    monitor.start()

    # Wait a bit
    time.sleep(2)

    # No files should be detected
    assert len(callback_tracker.called_files) == 0

    monitor.stop()


def test_pattern_with_question_mark_wildcard(temp_dir, callback_tracker, monitor_config):
    """Test pattern with ? wildcard (single character)"""
    config = {
        'log_directories': [{
            'path': str(temp_dir),
            'source': 'test',
            'pattern': 'log?.txt'
        }],
        'upload': {
            'processed_files_registry': {
                'registry_file': '/tmp/test_registry_' + str(id(temp_dir)) + '.json',
                'retention_days': 30
            },
            'scan_existing_files': {
                'enabled': True,
                'max_age_days': 30
            }
        }
    }

    # Create files
    match1 = temp_dir / "log1.txt"
    match1.write_text("match")

    match2 = temp_dir / "logA.txt"
    match2.write_text("match")

    no_match = temp_dir / "log10.txt"  # Two characters after "log"
    no_match.write_text("no match")

    monitor = FileMonitor(
        [str(temp_dir)],
        callback_tracker.callback,
        stability_seconds=2,
        config=config
    )
    monitor.start()

    result = wait_until(
        lambda: len(callback_tracker.called_files) >= 2,
        timeout=5,
        description="files matching log?.txt"
    )

    monitor.stop()

    assert result, f"Should detect 2 files, got {len(callback_tracker.called_files)}"
    assert len(callback_tracker.called_files) == 2

    files_str = str(callback_tracker.called_files)
    assert "log1.txt" in files_str
    assert "logA.txt" in files_str
    assert "log10.txt" not in files_str