#!/usr/bin/env python3
"""Tests for queue manager"""

import pytest
import json
import tempfile
from pathlib import Path
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