#!/usr/bin/env python3
"""
Tests for File Monitor
"""

import pytest
import time
import tempfile
from pathlib import Path
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from file_monitor import FileMonitor


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
    """Fixture to track callback calls"""
    class CallbackTracker:
        def __init__(self):
            self.called_files = []
        
        def callback(self, filepath):
            self.called_files.append(filepath)
            print(f"[Test] Callback received: {filepath}")
    
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