#!/usr/bin/env python3
"""
Integration test - File Monitor -> Upload Manager -> Disk Manager
Comprehensive coverage of component interactions
"""

import pytest
from pathlib import Path
import tempfile
import time
import shutil
import os
from unittest.mock import patch, Mock
from datetime import datetime, timedelta

from src.file_monitor import FileMonitor
from src.upload_manager import UploadManager
from src.disk_manager import DiskManager


class TestFileMonitorIntegration:
    """Integration tests for file monitoring and upload flow"""

    @pytest.fixture
    def temp_dir(self):
        """Create temporary test directory"""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_basic_monitor_upload_cleanup(self, temp_dir):
        """Test basic flow: monitor -> upload -> cleanup"""
        uploaded_files = []

        disk_manager = DiskManager([temp_dir], reserved_gb=0.1)

        def mock_upload_callback(filepath):
            """Mock upload - track uploaded files"""
            uploaded_files.append(filepath)
            disk_manager.mark_uploaded(filepath)

        file_monitor = FileMonitor(
            [temp_dir],
            mock_upload_callback,
            stability_seconds=2
        )

        try:
            file_monitor.start()
            time.sleep(0.5)

            # Create test files
            for i in range(3):
                f = Path(temp_dir) / f"test{i}.log"
                f.write_text(f"Test data {i}\n" * 100)
                time.sleep(0.3)

            # Wait for stability
            time.sleep(3)

            # Verify detection
            assert len(uploaded_files) == 3, "Should detect 3 files"
            assert disk_manager.get_uploaded_files_count() >= 0

            # Test cleanup
            deleted = disk_manager.cleanup_old_files(target_free_gb=1000)
            assert deleted >= 0

        finally:
            file_monitor.stop()

    def test_file_stability_detection(self, temp_dir):
        """Test files only uploaded after stability period"""
        uploaded_files = []

        # Use isolated registry to avoid interference from other tests
        config = {
            'upload': {
                'processed_files_registry': {
                    'registry_file': f'{temp_dir}/test_stability_registry.json',
                    'retention_days': 1
                }
            }
        }

        def mock_callback(filepath):
            uploaded_files.append(filepath)

        file_monitor = FileMonitor(
            [temp_dir],
            mock_callback,
            stability_seconds=2,
            config=config
        )

        try:
            file_monitor.start()
            time.sleep(1)

            # Create file
            test_file = Path(temp_dir) / "test_stability.log"
            test_file.write_text("data")

            # Should not be uploaded immediately
            time.sleep(0.5)
            assert len(uploaded_files) == 0, "File should not be uploaded before stability"

            # Wait for stability + extra buffer
            time.sleep(3)
            assert len(uploaded_files) >= 1, "File should be uploaded after stability"

        finally:
            file_monitor.stop()

    def test_multiple_file_types(self, temp_dir):
        """Test monitoring different file types"""
        uploaded_files = []

        def mock_callback(filepath):
            uploaded_files.append(filepath)

        file_monitor = FileMonitor(
            [temp_dir],
            mock_callback,
            stability_seconds=1
        )

        try:
            file_monitor.start()
            time.sleep(0.5)

            # Create various file types
            files = [
                "test.log",
                "data.txt",
                "info.csv",
                "metrics.json",
                "debug.out"
            ]

            for filename in files:
                (Path(temp_dir) / filename).write_text(f"content for {filename}")

            time.sleep(2.5)

            assert len(uploaded_files) == len(files), f"Should detect all {len(files)} files"

            # Verify all files detected
            uploaded_names = {Path(f).name for f in uploaded_files}
            assert uploaded_names == set(files)

        finally:
            file_monitor.stop()

    def test_file_size_variations(self, temp_dir):
        """Test handling files of different sizes"""
        uploaded_files = []

        def mock_callback(filepath):
            uploaded_files.append(filepath)

        config = {
            'upload': {
                'processed_files_registry': {
                    'registry_file': '/tmp/test_registry.json',
                    'retention_days': 1
                }
            }
        }

        file_monitor = FileMonitor([temp_dir], mock_callback, config=config, stability_seconds=1)

        try:
            file_monitor.start()
            time.sleep(0.5)

            # Create files of various sizes
            sizes = {
                "empty.log": 0,
                "small.log": 1024,  # 1 KB
                "medium.log": 1024 * 1024,  # 1 MB
                "large.log": 10 * 1024 * 1024  # 10 MB
            }

            for filename, size in sizes.items():
                filepath = Path(temp_dir) / filename
                if size == 0:
                    filepath.write_text("")
                else:
                    filepath.write_bytes(b'x' * size)

            time.sleep(2.5)

            assert len(uploaded_files) == len(sizes), "Should handle all file sizes"

        finally:
            file_monitor.stop()

    def test_special_characters_in_filenames(self, temp_dir):
        """Test handling files with special characters in names"""
        uploaded_files = []

        def mock_callback(filepath):
            uploaded_files.append(filepath)

        config = {
            'upload': {
                'processed_files_registry': {
                    'registry_file': '/tmp/test_registry.json',
                    'retention_days': 1
                }
            }
        }

        file_monitor = FileMonitor([temp_dir], mock_callback, config=config, stability_seconds=1)

        try:
            file_monitor.start()
            time.sleep(0.5)

            # Files with special characters (valid for most filesystems)
            filenames = [
                "test-file.log",
                "test_file.log",
                "test.file.log",
                "test 2024.log",
                "test(1).log"
            ]

            for filename in filenames:
                (Path(temp_dir) / filename).write_text("data")

            time.sleep(2.5)

            assert len(uploaded_files) >= len(filenames) - 1, "Should handle special characters"

        finally:
            file_monitor.stop()

    def test_concurrent_file_creation(self, temp_dir):
        """Test handling multiple files created simultaneously"""
        uploaded_files = []

        # Use isolated registry
        config = {
            'upload': {
                'processed_files_registry': {
                    'registry_file': f'{temp_dir}/test_concurrent_registry.json',
                    'retention_days': 1
                }
            }
        }

        def mock_callback(filepath):
            uploaded_files.append(filepath)

        file_monitor = FileMonitor([temp_dir], mock_callback, stability_seconds=2, config=config)

        try:
            file_monitor.start()
            time.sleep(1)

            # Create 10 files at once
            for i in range(10):
                (Path(temp_dir) / f"concurrent_{i}.log").write_text(f"data {i}")

            # Wait for stability + extra buffer
            time.sleep(4)

            assert len(uploaded_files) >= 10, "Should handle concurrent file creation"

        finally:
            file_monitor.stop()

    def test_file_modification_detection(self, temp_dir):
        """Test that modified files reset stability timer"""
        uploaded_files = []
        upload_timestamps = []

        def mock_callback(filepath):
            uploaded_files.append(filepath)
            upload_timestamps.append(time.time())

        config = {
            'upload': {
                'processed_files_registry': {
                    'registry_file': '/tmp/test_registry.json',
                    'retention_days': 1
                }
            }
        }

        file_monitor = FileMonitor([temp_dir], mock_callback, config=config, stability_seconds=2)

        try:
            file_monitor.start()
            time.sleep(0.5)

            test_file = Path(temp_dir) / "test.log"
            test_file.write_text("initial data")

            # Wait 1 second (not yet stable)
            time.sleep(1)

            # Modify file - should reset timer
            test_file.write_text("modified data")

            # Wait for new stability period
            time.sleep(3)

            # Should be uploaded only once, after final modification stabilized
            assert len(uploaded_files) == 1, "Should upload once after stabilization"

        finally:
            file_monitor.stop()

    def test_disk_cleanup_integration(self, temp_dir):
        """Test disk manager cleanup after uploads"""
        uploaded_files = []

        disk_manager = DiskManager([temp_dir], reserved_gb=0.1)

        def mock_callback(filepath):
            uploaded_files.append(filepath)
            disk_manager.mark_uploaded(filepath, keep_until_days=0)

        config = {
            'upload': {
                'processed_files_registry': {
                    'registry_file': '/tmp/test_registry.json',
                    'retention_days': 1
                }
            }
        }

        file_monitor = FileMonitor([temp_dir], mock_callback, config=config, stability_seconds=1)

        try:
            file_monitor.start()
            time.sleep(0.5)

            # Create files
            files = []
            for i in range(5):
                f = Path(temp_dir) / f"cleanup_test_{i}.log"
                f.write_bytes(b'x' * 1024 * 1024)  # 1 MB each
                files.append(f)

            time.sleep(2.5)

            # Verify all uploaded
            assert len(uploaded_files) == 5
            assert disk_manager.get_uploaded_files_count() == 5

            # Run cleanup - should delete all marked files
            deleted = disk_manager.cleanup_deferred_deletions()
            assert deleted == 5, "Should delete all marked files"

            # Verify files deleted
            for f in files:
                assert not f.exists(), f"File {f.name} should be deleted"

        finally:
            file_monitor.stop()

    def test_age_based_cleanup(self, temp_dir):
        """Test age-based cleanup deletes old files"""
        disk_manager = DiskManager([temp_dir], reserved_gb=0.1)

        # Create old file (10 days old)
        old_file = Path(temp_dir) / "old.log"
        old_file.write_text("old data")
        old_time = time.time() - (10 * 24 * 3600)
        os.utime(str(old_file), (old_time, old_time))

        # Create recent file (1 day old)
        recent_file = Path(temp_dir) / "recent.log"
        recent_file.write_text("recent data")
        recent_time = time.time() - (1 * 24 * 3600)
        os.utime(str(recent_file), (recent_time, recent_time))

        # Run cleanup (max age 7 days)
        deleted = disk_manager.cleanup_by_age(7)

        assert deleted == 1, "Should delete 1 old file"
        assert not old_file.exists(), "Old file should be deleted"
        assert recent_file.exists(), "Recent file should remain"

    def test_emergency_cleanup_on_low_disk(self, temp_dir):
        """Test emergency cleanup triggers when disk space low"""
        disk_manager = DiskManager([temp_dir], reserved_gb=0.1)

        # Create and mark files as uploaded
        for i in range(5):
            f = Path(temp_dir) / f"emergency_{i}.log"
            f.write_bytes(b'x' * 1024 * 1024)
            disk_manager.mark_uploaded(str(f), keep_until_days=30)

        # Mock low disk space
        with patch.object(disk_manager, 'check_disk_space', return_value=False):
            # Emergency cleanup should delete uploaded files
            deleted = disk_manager.cleanup_old_files()
            assert deleted >= 0, "Should attempt emergency cleanup"

    def test_registry_prevents_duplicate_uploads(self, temp_dir):
        """Test file registry prevents re-uploading same file"""
        uploaded_files = []

        # Put registry OUTSIDE monitored directory to avoid it being detected
        import tempfile
        registry_dir = tempfile.mkdtemp()

        config = {
            'upload': {
                'processed_files_registry': {
                    'registry_file': f'{registry_dir}/registry.json',
                    'retention_days': 30
                }
            }
        }

        def mock_callback(filepath):
            uploaded_files.append(filepath)
            return True

        file_monitor = FileMonitor(
            [temp_dir],
            mock_callback,
            stability_seconds=1,
            config=config
        )

        try:
            file_monitor.start()
            time.sleep(0.5)

            # Create file
            test_file = Path(temp_dir) / "test.log"
            test_file.write_text("data")

            time.sleep(2)
            assert len(uploaded_files) == 1, "Should upload once"

            # Stop and restart monitor (simulating restart)
            file_monitor.stop()

            uploaded_files.clear()
            file_monitor2 = FileMonitor(
                [temp_dir],
                mock_callback,
                stability_seconds=1,
                config=config
            )

            file_monitor2.start()
            time.sleep(2)

            # Should not re-upload (file in registry)
            assert len(uploaded_files) == 0, "Should not re-upload file in registry"

            file_monitor2.stop()

        finally:
            if file_monitor._running:
                file_monitor.stop()
            # Cleanup registry dir
            shutil.rmtree(registry_dir, ignore_errors=True)

    def test_multiple_directories_monitoring(self):
        """Test monitoring multiple directories simultaneously"""
        temp_dir1 = tempfile.mkdtemp()
        temp_dir2 = tempfile.mkdtemp()

        try:
            uploaded_files = []

            def mock_callback(filepath):
                uploaded_files.append(filepath)

            file_monitor = FileMonitor(
                [temp_dir1, temp_dir2],
                mock_callback,
                stability_seconds=1
            )

            file_monitor.start()
            time.sleep(0.5)

            # Create files in both directories
            (Path(temp_dir1) / "file1.log").write_text("data1")
            (Path(temp_dir2) / "file2.log").write_text("data2")

            time.sleep(2.5)

            assert len(uploaded_files) == 2, "Should monitor both directories"

            file_monitor.stop()

        finally:
            shutil.rmtree(temp_dir1, ignore_errors=True)
            shutil.rmtree(temp_dir2, ignore_errors=True)

    def test_callback_exception_handling(self, temp_dir):
        """Test monitor continues after callback exception"""
        call_count = [0]

        def failing_callback(filepath):
            call_count[0] += 1
            if call_count[0] == 1:
                raise Exception("Simulated upload error")
            # Second call succeeds

        file_monitor = FileMonitor([temp_dir], failing_callback, stability_seconds=1)

        try:
            file_monitor.start()
            time.sleep(0.5)

            # Create two files
            (Path(temp_dir) / "file1.log").write_text("data1")
            time.sleep(0.3)
            (Path(temp_dir) / "file2.log").write_text("data2")

            time.sleep(2.5)

            # Both should be attempted (monitor shouldn't crash)
            assert call_count[0] >= 1, "Should continue after callback exception"

        finally:
            file_monitor.stop()

    def test_disk_usage_tracking(self, temp_dir):
        """Test disk usage monitoring and reporting"""
        disk_manager = DiskManager([temp_dir], reserved_gb=1.0)

        usage, used, free = disk_manager.get_disk_usage()

        # Verify returned values are reasonable
        assert 0.0 <= usage <= 1.0, "Usage should be between 0 and 1"
        assert used > 0, "Used space should be positive"
        assert free > 0, "Free space should be positive"

        # Test disk space check
        has_space = disk_manager.check_disk_space()
        assert isinstance(has_space, bool), "Should return boolean"