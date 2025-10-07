#!/usr/bin/env python3
"""
Queue Manager for TVM Log Upload System
Persists upload queue to disk
"""

import json
import logging
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class QueueManager:
    """
    Manages persistent upload queue.
    
    Features:
    - Save queue to JSON file
    - Load queue on startup
    - Sort by priority (newest first)
    - Remove duplicates
    
    Queue Entry Format:
    {
        "filepath": "/var/log/file.mcap",
        "size": 104857600,
        "detected_at": "2025-10-14T15:30:00",
        "attempts": 0
    }
    """
    
    def __init__(self, queue_file: str = '/var/lib/tvm-upload/queue.json'):
        """
        Initialize queue manager.
        
        Args:
            queue_file: Path to queue JSON file
        """
        self.queue_file = Path(queue_file)
        self.queue: List[Dict[str, Any]] = []
        
        # Ensure directory exists
        try:
            self.queue_file.parent.mkdir(parents=True, exist_ok=True)
        except PermissionError:
            # If permission denied, use /tmp instead (for tests)
            self.queue_file = Path('/tmp/tvm-upload') / self.queue_file.name
            self.queue_file.parent.mkdir(parents=True, exist_ok=True)
            logger.warning(f"Permission denied for queue directory, using: {self.queue_file}")
        
        # Load existing queue
        self.load_queue()
        
        logger.info(f"Queue manager initialized with {len(self.queue)} pending files")
    
    def add_file(self, filepath: str):
        """
        Add file to upload queue.
        
        Args:
            filepath: Path to file to upload
        """
        file_path = Path(filepath)
        
        # Check if already in queue
        if any(entry['filepath'] == filepath for entry in self.queue):
            logger.debug(f"File already in queue: {file_path.name}")
            return
        
        # Get file size
        try:
            size = file_path.stat().st_size
        except (OSError, FileNotFoundError):
            logger.warning(f"Cannot stat file: {filepath}")
            return
        
        # Add to queue
        entry = {
            'filepath': filepath,
            'size': size,
            'detected_at': datetime.now().isoformat(),
            'attempts': 0
        }
        
        self.queue.append(entry)
        logger.info(f"Added to queue: {file_path.name} ({size / (1024**2):.1f} MB)")
        
        # Save queue
        self.save_queue()
    
    def get_next_batch(self, max_files: int = 10) -> List[str]:
        """
        Get next batch of files to upload (newest first).
        
        Args:
            max_files: Maximum files to return
            
        Returns:
            List of file paths
        """
        # Sort by detected_at (newest first)
        sorted_queue = sorted(
            self.queue,
            key=lambda x: x['detected_at'],
            reverse=True
        )
        
        # Return filepaths only
        batch = [entry['filepath'] for entry in sorted_queue[:max_files]]
        
        logger.debug(f"Next batch: {len(batch)} files")
        return batch
    
    def mark_uploaded(self, filepath: str):
        """
        Remove file from queue after successful upload.
        
        Args:
            filepath: Path to uploaded file
        """
        self.queue = [
            entry for entry in self.queue
            if entry['filepath'] != filepath
        ]
        
        logger.info(f"Removed from queue: {Path(filepath).name}")
        self.save_queue()
    
    def mark_failed(self, filepath: str):
        """
        Increment attempt counter for failed upload.
        
        Args:
            filepath: Path to failed file
        """
        for entry in self.queue:
            if entry['filepath'] == filepath:
                entry['attempts'] += 1
                logger.warning(f"Upload failed (attempt {entry['attempts']}): {Path(filepath).name}")
                break
        
        self.save_queue()
    
    def get_queue_size(self) -> int:
        """Get number of files in queue."""
        return len(self.queue)
    
    def get_queue_bytes(self) -> int:
        """Get total bytes in queue."""
        return sum(entry['size'] for entry in self.queue)
    
    def save_queue(self):
        """Save queue to JSON file."""
        try:
            with open(self.queue_file, 'w') as f:
                json.dump(self.queue, f, indent=2)
            logger.debug(f"Queue saved: {len(self.queue)} files")
        except Exception as e:
            logger.error(f"Failed to save queue: {e}")
    
    def load_queue(self):
        """Load queue from JSON file."""
        if not self.queue_file.exists():
            logger.info("No existing queue file, starting fresh")
            return
        
        try:
            with open(self.queue_file, 'r') as f:
                self.queue = json.load(f)
            
            # Remove files that no longer exist
            original_count = len(self.queue)
            self.queue = [
                entry for entry in self.queue
                if Path(entry['filepath']).exists()
            ]
            removed = original_count - len(self.queue)
            
            if removed > 0:
                logger.warning(f"Removed {removed} missing files from queue")
                self.save_queue()
            
            logger.info(f"Loaded queue: {len(self.queue)} files ({self.get_queue_bytes() / (1024**3):.2f} GB)")
            
        except Exception as e:
            logger.error(f"Failed to load queue: {e}")
            self.queue = []
    
    def clear_queue(self):
        """Clear entire queue (for testing)."""
        self.queue = []
        self.save_queue()
        logger.info("Queue cleared")


if __name__ == '__main__':
    import tempfile
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Test with temporary queue file
    with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
        queue_file = f.name
    
    qm = QueueManager(queue_file)
    
    # Add test files
    qm.add_file('/tmp/test1.log')
    qm.add_file('/tmp/test2.log')
    
    # Get batch
    batch = qm.get_next_batch()
    logger.info(f"Batch: {batch}")
    
    # Mark uploaded
    qm.mark_uploaded('/tmp/test1.log')
    
    logger.info(f"Queue size: {qm.get_queue_size()}")
    
    # Cleanup
    Path(queue_file).unlink()