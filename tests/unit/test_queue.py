#!/usr/bin/env python3
"""Tests for queue manager"""

import pytest
import json
import tempfile
from pathlib import Path

# Now we can import (assuming queue_manager.py is in same directory as test)
from src.queue_manager import QueueManager


class TestQueueManager:
    """Test queue persistence"""
    
    @pytest.fixture
    def temp_queue_file(self):
        """Create temporary queue file"""
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
            yield f.name
        Path(f.name).unlink(missing_ok=True)
    
    @pytest.fixture
    def temp_test_file(self):
        """Create temporary test file"""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b'test data' * 1000)
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
        assert qm.queue[0]['filepath'] == temp_test_file
        assert qm.queue[0]['attempts'] == 0
    
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
        assert qm2.queue[0]['filepath'] == temp_test_file
    
    def test_mark_uploaded(self, temp_queue_file, temp_test_file):
        """Test removing uploaded file"""
        qm = QueueManager(temp_queue_file)
        qm.add_file(temp_test_file)
        assert qm.get_queue_size() == 1
        
        qm.mark_uploaded(temp_test_file)
        assert qm.get_queue_size() == 0
    
    def test_mark_failed(self, temp_queue_file, temp_test_file):
        """Test incrementing attempt counter"""
        qm = QueueManager(temp_queue_file)
        qm.add_file(temp_test_file)
        
        qm.mark_failed(temp_test_file)
        assert qm.queue[0]['attempts'] == 1
        
        qm.mark_failed(temp_test_file)
        assert qm.queue[0]['attempts'] == 2
    
    def test_get_next_batch(self, temp_queue_file):
        """Test getting batch of files (newest first)"""
        qm = QueueManager(temp_queue_file)
        
        # Create test files
        files = []
        for i in range(5):
            with tempfile.NamedTemporaryFile(delete=False) as f:
                f.write(b'test')
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
        assert any(reason in msg for msg in log_messages), \
            "Permanent failure reason should be logged"


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
                f.write(b'test')
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
            f1.write(b'test1')
            temp_file1 = f1.name
        
        with tempfile.NamedTemporaryFile(delete=False) as f2:
            f2.write(b'test2')
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
            entry = [e for e in qm.queue if e['filepath'] == temp_file1][0]
            assert entry['attempts'] == 1, "Temp failure should increment attempts"
            
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
                f.write(b'test')
                files.append(f.name)
                qm.add_file(f.name)
        
        try:
            # Mark some as permanent failures
            qm.mark_permanent_failure(files[1], "Error")
            qm.mark_permanent_failure(files[3], "Error")
            
            assert qm.get_queue_size() == 3
            
            # Can still add files
            with tempfile.NamedTemporaryFile(delete=False) as f:
                f.write(b'test')
                new_file = f.name
                files.append(new_file)
            
            qm.add_file(new_file)
            assert qm.get_queue_size() == 4
            
            # Can still mark uploaded
            qm.mark_uploaded(files[0])
            assert qm.get_queue_size() == 3
            
            # Can still mark failed (temporary)
            qm.mark_failed(files[2])
            entry = [e for e in qm.queue if e['filepath'] == files[2]][0]
            assert entry['attempts'] == 1
            
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
            with tempfile.NamedTemporaryFile(delete=False, mode='wb') as f:  # ← CHANGED: Added mode='wb'
                f.write(b'x' * size)  # ← CHANGED: Write bytes, not string
                f.flush()  # ← NEW: Force write to disk
                files.append(f.name)
            
            # Add file AFTER it's been written and closed
            qm.add_file(files[-1])
        
        try:
            initial_bytes = qm.get_queue_bytes()
            assert initial_bytes == sum(sizes), \
                f"Initial queue should be {sum(sizes)} bytes, got {initial_bytes}"
            
            # Mark some as permanent failures
            qm.mark_permanent_failure(files[1], "Error")  # 2000 bytes
            qm.mark_permanent_failure(files[3], "Error")  # 4000 bytes
            
            # Queue should reflect removed files
            remaining_bytes = qm.get_queue_bytes()
            expected_bytes = sizes[0] + sizes[2] + sizes[4]  # 1000 + 3000 + 5000
            
            assert remaining_bytes == expected_bytes, \
                f"Queue should have {expected_bytes} bytes, got {remaining_bytes}"
            
            assert qm.get_queue_size() == 3
            
        finally:
            for f in files:
                Path(f).unlink(missing_ok=True)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])