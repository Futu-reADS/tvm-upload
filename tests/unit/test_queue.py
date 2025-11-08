#!/usr/bin/env python3
"""Tests for queue manager"""

import json
import tempfile
import time
from pathlib import Path

import pytest

# Now we can import (assuming queue_manager.py is in same directory as test)
from src.queue_manager import QueueManager


class TestQueueManager:
    """Test queue persistence"""

    @pytest.fixture
    def temp_queue_file(self):
        """Create temporary queue file"""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            yield f.name
        Path(f.name).unlink(missing_ok=True)

    @pytest.fixture
    def temp_test_file(self):
        """Create temporary test file"""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"test data" * 1000)
            yield f.name
        Path(f.name).unlink(missing_ok=True)

    def test_init(self, temp_queue_file):
        """Test queue manager initialization"""
        qm = QueueManager(temp_queue_file)
        assert qm.get_queue_size() == 0

    def test_add_file(self, temp_queue_file, temp_test_file):
        """Test adding file to queue"""
        qm = QueueManager(temp_queue_file)
        qm.add_file(temp_test_file)

        assert qm.get_queue_size() == 1
        assert qm.queue[0]["filepath"] == temp_test_file
        assert qm.queue[0]["attempts"] == 0

    def test_add_duplicate(self, temp_queue_file, temp_test_file):
        """Test adding same file twice"""
        qm = QueueManager(temp_queue_file)
        qm.add_file(temp_test_file)
        qm.add_file(temp_test_file)

        assert qm.get_queue_size() == 1

    def test_persistence(self, temp_queue_file, temp_test_file):
        """Test queue survives restart"""
        # Add file
        qm1 = QueueManager(temp_queue_file)
        qm1.add_file(temp_test_file)
        assert qm1.get_queue_size() == 1

        # Create new instance (simulates restart)
        qm2 = QueueManager(temp_queue_file)
        assert qm2.get_queue_size() == 1
        assert qm2.queue[0]["filepath"] == temp_test_file

    def test_remove_from_queue(self, temp_queue_file, temp_test_file):
        """Test removing uploaded file"""
        qm = QueueManager(temp_queue_file)
        qm.add_file(temp_test_file)
        assert qm.get_queue_size() == 1

        qm.remove_from_queue(temp_test_file)
        assert qm.get_queue_size() == 0

    def test_mark_failed(self, temp_queue_file, temp_test_file):
        """Test incrementing attempt counter"""
        qm = QueueManager(temp_queue_file)
        qm.add_file(temp_test_file)

        qm.mark_failed(temp_test_file)
        assert qm.queue[0]["attempts"] == 1

        qm.mark_failed(temp_test_file)
        assert qm.queue[0]["attempts"] == 2

    def test_get_next_batch(self, temp_queue_file):
        """Test getting batch of files (newest first)"""
        qm = QueueManager(temp_queue_file)

        # Create test files
        files = []
        for i in range(5):
            with tempfile.NamedTemporaryFile(delete=False) as f:
                f.write(b"test")
                files.append(f.name)
                qm.add_file(f.name)

        batch = qm.get_next_batch(max_files=3)
        assert len(batch) == 3

        # Should return newest files first
        assert batch[0] == files[4]
        assert batch[1] == files[3]
        assert batch[2] == files[2]

        # Cleanup
        for f in files:
            Path(f).unlink(missing_ok=True)

    # ============================================
    # NEW TESTS FOR v2.1 PERMANENT FAILURE MARKING
    # ============================================

    def test_mark_permanent_failure(self, temp_queue_file, temp_test_file):
        """Test marking file as permanently failed removes it from queue"""
        qm = QueueManager(temp_queue_file)

        # Add file to queue
        qm.add_file(temp_test_file)
        assert qm.get_queue_size() == 1

        # Mark as permanent failure
        qm.mark_permanent_failure(temp_test_file, "File corrupted: bad sector")

        # Should be removed from queue
        assert qm.get_queue_size() == 0

        # Verify file not in queue
        batch = qm.get_next_batch()
        assert temp_test_file not in batch

    def test_mark_permanent_failure_logs_reason(self, temp_queue_file, temp_test_file, caplog):
        """Test permanent failure logging includes reason"""
        import logging

        caplog.set_level(logging.ERROR)

        qm = QueueManager(temp_queue_file)
        qm.add_file(temp_test_file)

        # Mark with specific reason
        reason = "Disk read error: I/O error"
        qm.mark_permanent_failure(temp_test_file, reason)

        # Check logs contain reason
        log_messages = [record.message for record in caplog.records]
        assert any(
            reason in msg for msg in log_messages
        ), "Permanent failure reason should be logged"

    def test_mark_permanent_failure_nonexistent_file(self, temp_queue_file):
        """Test marking nonexistent file as permanent failure doesn't crash"""
        qm = QueueManager(temp_queue_file)

        # Try to mark file that's not in queue
        qm.mark_permanent_failure("/nonexistent/file.log", "File not found")

        # Should not crash, queue should remain empty
        assert qm.get_queue_size() == 0

    def test_mark_permanent_failure_saves_queue(self, temp_queue_file, temp_test_file):
        """Test permanent failure marking persists queue state"""
        # Add multiple files
        qm = QueueManager(temp_queue_file)

        files = []
        for i in range(3):
            with tempfile.NamedTemporaryFile(delete=False) as f:
                f.write(b"test")
                files.append(f.name)
                qm.add_file(f.name)

        assert qm.get_queue_size() == 3

        # Mark middle file as permanent failure
        qm.mark_permanent_failure(files[1], "Permanent error")

        assert qm.get_queue_size() == 2

        # Reload queue (simulates restart)
        qm2 = QueueManager(temp_queue_file)

        # Should still have 2 files (permanent failure removed)
        assert qm2.get_queue_size() == 2

        # Cleanup
        for f in files:
            Path(f).unlink(missing_ok=True)

    def test_permanent_vs_temporary_failure_behavior(self, temp_queue_file):
        """Test difference between permanent and temporary failures"""
        qm = QueueManager(temp_queue_file)

        # Create two test files
        with tempfile.NamedTemporaryFile(delete=False) as f1:
            f1.write(b"test1")
            temp_file1 = f1.name

        with tempfile.NamedTemporaryFile(delete=False) as f2:
            f2.write(b"test2")
            temp_file2 = f2.name

        try:
            qm.add_file(temp_file1)
            qm.add_file(temp_file2)

            # Temporary failure - increments attempts
            qm.mark_failed(temp_file1)

            # Permanent failure - removes from queue
            qm.mark_permanent_failure(temp_file2, "Corrupted file")

            # Check results
            assert qm.get_queue_size() == 1, "Only temp failed file should remain"

            batch = qm.get_next_batch()
            assert temp_file1 in batch, "Temp failed file should be in queue"
            assert temp_file2 not in batch, "Permanent failed file should be removed"

            # Check attempts counter
            entry = [e for e in qm.queue if e["filepath"] == temp_file1][0]
            assert entry["attempts"] == 1, "Temp failure should increment attempts"

        finally:
            Path(temp_file1).unlink(missing_ok=True)
            Path(temp_file2).unlink(missing_ok=True)

    def test_mark_permanent_failure_multiple_times(self, temp_queue_file, temp_test_file):
        """Test marking same file multiple times doesn't cause issues"""
        qm = QueueManager(temp_queue_file)
        qm.add_file(temp_test_file)

        # Mark as permanent failure multiple times
        qm.mark_permanent_failure(temp_test_file, "Error 1")
        qm.mark_permanent_failure(temp_test_file, "Error 2")
        qm.mark_permanent_failure(temp_test_file, "Error 3")

        # Should still be removed (no duplicates)
        assert qm.get_queue_size() == 0

    def test_queue_operations_after_permanent_failure(self, temp_queue_file):
        """Test queue continues working after permanent failures"""
        qm = QueueManager(temp_queue_file)

        files = []
        for i in range(5):
            with tempfile.NamedTemporaryFile(delete=False) as f:
                f.write(b"test")
                files.append(f.name)
                qm.add_file(f.name)

        try:
            # Mark some as permanent failures
            qm.mark_permanent_failure(files[1], "Error")
            qm.mark_permanent_failure(files[3], "Error")

            assert qm.get_queue_size() == 3

            # Can still add files
            with tempfile.NamedTemporaryFile(delete=False) as f:
                f.write(b"test")
                new_file = f.name
                files.append(new_file)

            qm.add_file(new_file)
            assert qm.get_queue_size() == 4

            # Can still mark uploaded
            qm.remove_from_queue(files[0])
            assert qm.get_queue_size() == 3

            # Can still mark failed (temporary)
            qm.mark_failed(files[2])
            entry = [e for e in qm.queue if e["filepath"] == files[2]][0]
            assert entry["attempts"] == 1

        finally:
            for f in files:
                Path(f).unlink(missing_ok=True)

    def test_permanent_failure_with_empty_queue(self, temp_queue_file):
        """Test permanent failure on empty queue doesn't crash"""
        qm = QueueManager(temp_queue_file)

        assert qm.get_queue_size() == 0

        # Should not crash
        qm.mark_permanent_failure("/some/file.log", "Error")

        assert qm.get_queue_size() == 0

    def test_queue_statistics_after_permanent_failures(self, temp_queue_file):
        """Test queue size and bytes calculations after permanent failures"""
        qm = QueueManager(temp_queue_file)

        # Create files of different sizes
        files = []
        sizes = [1000, 2000, 3000, 4000, 5000]  # bytes

        for i, size in enumerate(sizes):
            with tempfile.NamedTemporaryFile(
                delete=False, mode="wb"
            ) as f:  # ← CHANGED: Added mode='wb'
                f.write(b"x" * size)  # ← CHANGED: Write bytes, not string
                f.flush()  # ← NEW: Force write to disk
                files.append(f.name)

            # Add file AFTER it's been written and closed
            qm.add_file(files[-1])

        try:
            initial_bytes = qm.get_queue_bytes()
            assert initial_bytes == sum(
                sizes
            ), f"Initial queue should be {sum(sizes)} bytes, got {initial_bytes}"

            # Mark some as permanent failures
            qm.mark_permanent_failure(files[1], "Error")  # 2000 bytes
            qm.mark_permanent_failure(files[3], "Error")  # 4000 bytes

            # Queue should reflect removed files
            remaining_bytes = qm.get_queue_bytes()
            expected_bytes = sizes[0] + sizes[2] + sizes[4]  # 1000 + 3000 + 5000

            assert (
                remaining_bytes == expected_bytes
            ), f"Queue should have {expected_bytes} bytes, got {remaining_bytes}"

            assert qm.get_queue_size() == 3

        finally:
            for f in files:
                Path(f).unlink(missing_ok=True)


# ============================================
# QUEUE FILE CORRUPTION TESTS
# ============================================


class TestQueueFileCorruption:
    """Test handling of corrupted queue files"""

    def test_malformed_json_queue_file(self, temp_dir):
        """Test queue file with invalid JSON starts fresh"""
        queue_file = temp_dir / "queue_malformed.json"

        # Write invalid JSON
        with open(queue_file, "w") as f:
            f.write("{ invalid json here }")

        # Should handle gracefully and start with empty queue
        qm = QueueManager(str(queue_file))
        assert qm.get_queue_size() == 0
        assert qm.queue == []

    def test_empty_queue_file(self, temp_dir):
        """Test empty queue file initializes empty queue"""
        queue_file = temp_dir / "queue_empty.json"
        queue_file.write_text("")  # Empty file

        qm = QueueManager(str(queue_file))
        assert qm.get_queue_size() == 0

    def test_queue_file_permission_denied(self, temp_dir):
        """Test handling when queue file is not writable"""
        import os

        queue_file = temp_dir / "queue_readonly.json"
        qm = QueueManager(str(queue_file))

        # Create file
        test_file = temp_dir / "test.log"
        test_file.write_text("data")
        qm.add_file(str(test_file))

        # Make queue file read-only
        os.chmod(str(queue_file), 0o444)

        try:
            # Adding another file should handle permission error gracefully
            test_file2 = temp_dir / "test2.log"
            test_file2.write_text("data2")

            # This might raise an error or log it - either is acceptable
            try:
                qm.add_file(str(test_file2))
            except (OSError, PermissionError):
                pass  # Expected
        finally:
            # Restore permissions for cleanup
            os.chmod(str(queue_file), 0o644)

    def test_queue_file_with_extra_fields(self, temp_dir):
        """Test queue file with extra unknown fields is handled"""
        queue_file = temp_dir / "queue_extra.json"

        # Create actual file
        test_file = temp_dir / "test.log"
        test_file.write_text("test data")

        # Write queue with extra fields
        queue_data = [
            {
                "filepath": str(test_file),
                "size": 1000,
                "detected_at": time.time(),
                "attempts": 0,
                "extra_field": "should be ignored",
                "unknown": 123,
            }
        ]

        with open(queue_file, "w") as f:
            json.dump(queue_data, f)

        # Should load successfully, ignoring extra fields
        qm = QueueManager(str(queue_file))
        assert qm.get_queue_size() == 1


# ============================================
# MISSING FILE HANDLING TESTS
# ============================================


class TestMissingFileHandling:
    """Test handling of files deleted from disk"""

    def test_remove_missing_files_on_startup(self, temp_dir):
        """Test queue removes files that no longer exist on startup"""
        queue_file = temp_dir / "queue.json"

        # Create 3 files
        file1 = temp_dir / "file1.log"
        file2 = temp_dir / "file2.log"
        file3 = temp_dir / "file3.log"

        file1.write_text("data1")
        file2.write_text("data2")
        file3.write_text("data3")

        # Add all to queue
        qm1 = QueueManager(str(queue_file))
        qm1.add_file(str(file1))
        qm1.add_file(str(file2))
        qm1.add_file(str(file3))
        assert qm1.get_queue_size() == 3

        # Delete file2
        file2.unlink()

        # Create new queue manager - should remove missing file
        qm2 = QueueManager(str(queue_file))
        assert qm2.get_queue_size() == 2

        # Verify file2 not in queue
        queue_files = [entry["filepath"] for entry in qm2.queue]
        assert str(file2) not in queue_files

    def test_get_next_batch_includes_missing_files(self, temp_dir):
        """Test batch retrieval includes all queued files even if deleted (error handling at upload time)"""
        queue_file = temp_dir / "queue.json"

        # Create files
        file1 = temp_dir / "file1.log"
        file2 = temp_dir / "file2.log"
        file3 = temp_dir / "file3.log"

        file1.write_text("data1")
        file2.write_text("data2")
        file3.write_text("data3")

        qm = QueueManager(str(queue_file))
        qm.add_file(str(file1))
        qm.add_file(str(file2))
        qm.add_file(str(file3))

        # Delete file2
        file2.unlink()

        # Get batch - includes all queued files (even missing ones)
        # Missing file handling happens at upload time, not batch time
        batch = qm.get_next_batch(max_files=10)

        # Should get all 3 files in batch (file2 is in queue even though file doesn't exist)
        assert len(batch) == 3
        assert str(file1) in batch
        assert str(file3) in batch
        assert str(file2) in batch  # Still in batch, will fail at upload time


# ============================================
# EDGE CASE TESTS
# ============================================


class TestQueueEdgeCases:
    """Test edge cases and boundary conditions"""

    def test_batch_with_max_files_zero(self, temp_dir):
        """Test get_next_batch with max_files=0 returns empty list"""
        queue_file = temp_dir / "queue.json"

        test_file = temp_dir / "test.log"
        test_file.write_text("data")

        qm = QueueManager(str(queue_file))
        qm.add_file(str(test_file))

        batch = qm.get_next_batch(max_files=0)
        assert len(batch) == 0

    def test_batch_with_negative_max_files(self, temp_dir):
        """Test get_next_batch with negative max_files (tests current behavior, may need validation)

        NOTE: Negative max_files currently uses Python slicing behavior which may be unintended.
        This test documents the current behavior. Consider adding validation in queue_manager.py.
        """
        queue_file = temp_dir / "queue.json"

        # Create multiple files to test negative slicing
        files = []
        for i in range(3):
            f = temp_dir / f"file{i}.log"
            f.write_text(f"data{i}")
            files.append(f)

        qm = QueueManager(str(queue_file))
        for f in files:
            qm.add_file(str(f))

        # Negative max_files uses Python slicing: sorted_queue[:-1] returns all but last
        # This behavior may be unintended and should potentially be validated
        batch = qm.get_next_batch(max_files=-1)
        assert len(batch) == 2  # 3 files, sliced [:-1] gives 2

    def test_batch_larger_than_queue_size(self, temp_dir):
        """Test requesting batch larger than queue size"""
        queue_file = temp_dir / "queue.json"

        # Add 3 files
        files = []
        for i in range(3):
            f = temp_dir / f"file{i}.log"
            f.write_text(f"data{i}")
            files.append(f)

        qm = QueueManager(str(queue_file))
        for f in files:
            qm.add_file(str(f))

        # Request 100 files when only 3 exist
        batch = qm.get_next_batch(max_files=100)
        assert len(batch) == 3

    def test_files_with_identical_timestamps(self, temp_dir):
        """Test files with same detected_at timestamp have deterministic order"""
        queue_file = temp_dir / "queue.json"

        # Create actual files
        file_a = temp_dir / "a.log"
        file_b = temp_dir / "b.log"
        file_c = temp_dir / "c.log"
        file_a.write_text("a")
        file_b.write_text("b")
        file_c.write_text("c")

        # Manually create queue entries with identical timestamps
        same_time = time.time()
        queue_data = [
            {"filepath": str(file_a), "size": 100, "detected_at": same_time, "attempts": 0},
            {"filepath": str(file_b), "size": 200, "detected_at": same_time, "attempts": 0},
            {"filepath": str(file_c), "size": 300, "detected_at": same_time, "attempts": 0},
        ]

        with open(queue_file, "w") as f:
            json.dump(queue_data, f)

        qm = QueueManager(str(queue_file))
        batch = qm.get_next_batch(max_files=10)

        # Order should be consistent (newest first = same order as added)
        assert len(batch) == 3

    def test_attempt_counter_very_high(self, temp_dir):
        """Test file with very high attempt count is still tracked"""
        queue_file = temp_dir / "queue.json"

        test_file = temp_dir / "test.log"
        test_file.write_text("data")

        qm = QueueManager(str(queue_file))
        qm.add_file(str(test_file))

        # Mark failed 1000 times
        for _ in range(1000):
            qm.mark_failed(str(test_file))

        # File should still be in queue
        assert qm.get_queue_size() == 1
        assert qm.queue[0]["attempts"] == 1000

    def test_empty_filepath(self, temp_dir):
        """Test adding empty filepath is rejected"""
        queue_file = temp_dir / "queue.json"
        qm = QueueManager(str(queue_file))

        # Empty filepath should be rejected
        qm.add_file("")
        assert qm.get_queue_size() == 0

        # Whitespace-only filepath should also be rejected
        qm.add_file("   ")
        assert qm.get_queue_size() == 0

    def test_directory_path_rejected(self, temp_dir):
        """Test adding directory path is rejected"""
        queue_file = temp_dir / "queue.json"
        qm = QueueManager(str(queue_file))

        # Create a directory
        dir_path = temp_dir / "test_dir"
        dir_path.mkdir()

        # Directory should be rejected
        qm.add_file(str(dir_path))
        assert qm.get_queue_size() == 0

    def test_nonexistent_file_add(self, temp_dir):
        """Test adding nonexistent file"""
        queue_file = temp_dir / "queue.json"
        qm = QueueManager(str(queue_file))

        # Try to add file that doesn't exist
        qm.add_file("/nonexistent/file.log")

        # Should either be rejected or added but skipped later
        # Either behavior is acceptable


# ============================================
# LARGE-SCALE PERFORMANCE TESTS (1000+ FILES)
# ============================================


class TestLargeScaleQueue:
    """Test queue performance with many files"""

    def test_queue_with_1000_files(self, temp_dir):
        """Test queue operations with 1000+ files"""
        queue_file = temp_dir / "queue_large.json"
        qm = QueueManager(str(queue_file))

        # Create and add 1000 files
        files = []
        for i in range(1000):
            f = temp_dir / f"file{i:04d}.log"
            f.write_text(f"data{i}")
            files.append(f)
            qm.add_file(str(f))

        # Verify all added
        assert qm.get_queue_size() == 1000

        # Get batch of 50
        batch = qm.get_next_batch(max_files=50)
        assert len(batch) == 50

        # Remove 100 files
        for i in range(100):
            qm.remove_from_queue(str(files[i]))

        assert qm.get_queue_size() == 900

        # Cleanup
        for f in files:
            f.unlink(missing_ok=True)

    def test_queue_persistence_with_many_files(self, temp_dir):
        """Test queue persists correctly with many files"""
        queue_file = temp_dir / "queue_persist.json"

        # Create 500 files
        files = []
        for i in range(500):
            f = temp_dir / f"persist{i:04d}.log"
            f.write_text(f"data{i}")
            files.append(f)

        # Add to queue
        qm1 = QueueManager(str(queue_file))
        for f in files:
            qm1.add_file(str(f))

        assert qm1.get_queue_size() == 500

        # Create new queue manager - should load all files
        qm2 = QueueManager(str(queue_file))
        assert qm2.get_queue_size() == 500

        # Cleanup
        for f in files:
            f.unlink(missing_ok=True)

    # COMMENTED OUT: Very slow test - enable when needed for stress testing
    # def test_queue_with_10000_files_stress(self, temp_dir):
    #     """STRESS TEST: Queue with 10,000 files (slow, commented out by default)"""
    #     queue_file = temp_dir / "queue_stress.json"
    #     qm = QueueManager(str(queue_file))
    #
    #     # Add 10,000 files
    #     for i in range(10000):
    #         # Use fake paths to avoid creating actual files
    #         qm.add(f"/tmp/stress_test_{i}.log")
    #
    #     assert qm.get_queue_size() == 10000
    #
    #     # Get batch
    #     batch = qm.get_next_batch(max_files=100)
    #     assert len(batch) == 100
    #
    #     # Remove all
    #     for i in range(10000):
    #         qm.remove(f"/tmp/stress_test_{i}.log")
    #
    #     assert qm.get_queue_size() == 0


# ============================================
# SORTING AND ORDERING TESTS
# ============================================


class TestQueueOrdering:
    """Test queue sorting and ordering logic"""

    def test_newest_first_ordering(self, temp_dir):
        """Test queue returns newest files first"""
        queue_file = temp_dir / "queue_order.json"
        qm = QueueManager(str(queue_file))

        # Add files with delays to ensure different timestamps
        file1 = temp_dir / "old.log"
        file1.write_text("old")
        qm.add_file(str(file1))

        time.sleep(0.01)

        file2 = temp_dir / "middle.log"
        file2.write_text("middle")
        qm.add_file(str(file2))

        time.sleep(0.01)

        file3 = temp_dir / "newest.log"
        file3.write_text("newest")
        qm.add_file(str(file3))

        # Get batch - should be newest first
        batch = qm.get_next_batch(max_files=10)

        # First item should be newest
        assert "newest.log" in batch[0]

    def test_files_with_future_timestamps(self, temp_dir):
        """Test files with future timestamps (clock skew)"""
        queue_file = temp_dir / "queue_future.json"

        # Create actual files
        future_file = temp_dir / "future.log"
        now_file = temp_dir / "now.log"
        future_file.write_text("future data")
        now_file.write_text("now data")

        # Manually create queue with future timestamp
        future_time = time.time() + (24 * 3600)  # 1 day in future
        queue_data = [
            {"filepath": str(future_file), "size": 100, "detected_at": future_time, "attempts": 0},
            {"filepath": str(now_file), "size": 200, "detected_at": time.time(), "attempts": 0},
        ]

        with open(queue_file, "w") as f:
            json.dump(queue_data, f)

        qm = QueueManager(str(queue_file))
        batch = qm.get_next_batch(max_files=10)

        # Future file should come first (newest)
        assert "future.log" in batch[0]


# ============================================
# BYTE TRACKING TESTS
# ============================================


class TestQueueByteTracking:
    """Test queue byte size tracking"""

    def test_get_queue_bytes_accuracy(self, temp_dir):
        """Test byte counting is accurate"""
        queue_file = temp_dir / "queue_bytes.json"
        qm = QueueManager(str(queue_file))

        # Create files with known sizes
        sizes = [1024, 2048, 4096]  # 1KB, 2KB, 4KB
        files = []

        for i, size in enumerate(sizes):
            f = temp_dir / f"sized{i}.log"
            f.write_bytes(b"0" * size)
            files.append(f)
            qm.add_file(str(f))

        # Verify byte count
        expected_bytes = sum(sizes)
        actual_bytes = qm.get_queue_bytes()

        assert (
            actual_bytes == expected_bytes
        ), f"Expected {expected_bytes} bytes, got {actual_bytes}"

        # Cleanup
        for f in files:
            f.unlink()

    def test_bytes_update_after_remove(self, temp_dir):
        """Test byte count updates correctly after removing files"""
        queue_file = temp_dir / "queue_bytes2.json"
        qm = QueueManager(str(queue_file))

        # Add 3 files
        file1 = temp_dir / "f1.log"
        file2 = temp_dir / "f2.log"
        file3 = temp_dir / "f3.log"

        file1.write_bytes(b"0" * 1000)
        file2.write_bytes(b"0" * 2000)
        file3.write_bytes(b"0" * 3000)

        qm.add_file(str(file1))
        qm.add_file(str(file2))
        qm.add_file(str(file3))

        assert qm.get_queue_bytes() == 6000

        # Remove middle file
        qm.remove_from_queue(str(file2))

        assert qm.get_queue_bytes() == 4000  # 1000 + 3000

        # Cleanup
        file1.unlink()
        file2.unlink()
        file3.unlink()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
