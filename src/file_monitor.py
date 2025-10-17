#!/usr/bin/env python3
"""
File Monitor for TVM Log Upload System
Watches directories and detects completed log files

Uses watchdog library to monitor filesystem events and determines when
files are complete based on size stability over a configured period.

Version: 2.0 - Added startup scan for existing files
"""

import time
import threading
import logging
from pathlib import Path
from typing import Callable, Dict, Tuple, List
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileCreatedEvent, FileModifiedEvent

logger = logging.getLogger(__name__)


class FileMonitor:
    """
    Monitors directories for completed log files using watchdog.
    
    A file is considered "complete" when its size hasn't changed for
    the configured stability period (default: 60 seconds). This ensures
    files are fully written before processing.
    
    Architecture:
    - Watchdog Observer: Detects filesystem events (create/modify)
    - File Tracker: Tracks file sizes and last modification time
    - Stability Checker: Background thread that checks for stable files
    - Startup Scanner: Scans for existing files on initialization (NEW v2.0)
    
    Example:
        >>> def on_complete(filepath):
        ...     print(f"File ready: {filepath}")
        >>> monitor = FileMonitor(['/var/log'], on_complete, stability_seconds=60)
        >>> monitor.start()
        >>> # ... monitor runs in background ...
        >>> monitor.stop()
    
    Attributes:
        directories (List[Path]): Directories being monitored
        callback (Callable): Function called when file is stable
        stability_seconds (int): Seconds file must be unchanged
        file_tracker (dict): Maps filepath to (size, timestamp)
        config (dict): Configuration dictionary for startup scan
    """
    
    def __init__(self, 
                 directories: List[str], 
                 callback: Callable[[str], None],
                 stability_seconds: int = 60,
                 config: dict = None):
        """
        Initialize file monitor.
        
        Args:
            directories: List of directory paths to monitor
            callback: Function to call when file is ready (receives file path)
            stability_seconds: Seconds file must be unchanged to be "complete"
            config: Configuration dict for startup scan settings (NEW v2.0)
            
        Note:
            Directories will be created if they don't exist
        """
        self.directories = [Path(d) for d in directories]
        self.callback = callback
        self.stability_seconds = stability_seconds
        self.config = config or {}
        
        # Track file sizes: {filepath: (size, last_check_time)}
        self.file_tracker: Dict[Path, Tuple[int, float]] = {}
        
        # Watchdog components
        self.observer = Observer()
        self.handler = LogFileHandler(self._on_file_event)
        
        # Control flags
        self._running = False
        self._checker_thread = None
        
        logger.info(f"Initialized monitoring {len(directories)} directories")
        logger.info(f"Stability period: {stability_seconds} seconds")
    
    def start(self):
        """
        Start monitoring directories.
        
        Starts the watchdog observer and stability checker thread.
        Creates directories if they don't exist.
        Optionally scans for existing files based on configuration (NEW v2.0).
        
        Note:
            Safe to call multiple times - will not start if already running
        """
        if self._running:
            logger.warning("Already running")
            return
        
        # Verify directories exist
        for directory in self.directories:
            if not directory.exists():
                logger.warning(f"Directory does not exist: {directory}")
                logger.info(f"Creating directory: {directory}")
                directory.mkdir(parents=True, exist_ok=True)
        
        # ===== NEW: Configurable startup scan (v2.0) =====
        scan_config = self.config.get('upload', {}).get('scan_existing_files', {})
        
        if scan_config.get('enabled', True):  # Default: enabled
            max_age_days = scan_config.get('max_age_days', 3)  # Default: 3 days (Maeda-san's choice)
            
            logger.info(f"Scanning for existing files (max age: {max_age_days} days)...")
            
            cutoff_time = time.time() - (max_age_days * 24 * 3600)
            existing_count = 0
            skipped_count = 0
            
            for directory in self.directories:
                for file_path in directory.iterdir():
                    if file_path.is_file() and not file_path.name.startswith('.'):
                        try:
                            mtime = file_path.stat().st_mtime
                            
                            if max_age_days == 0 or mtime > cutoff_time:

                                # Only add if not already tracked
                                if file_path in self.file_tracker:
                                    logger.debug(f"Skipping already-tracked file: {file_path.name}")
                                    continue
                                # Add to tracker for stability check
                                self._on_file_event(str(file_path))
                                existing_count += 1
                                logger.debug(f"Found existing file: {file_path.name}")
                            else:
                                logger.debug(f"Skipping old file: {file_path.name} "
                                           f"({(time.time() - mtime) / 86400:.1f} days old)")
                                skipped_count += 1
                        except (OSError, FileNotFoundError) as e:
                            logger.debug(f"Error checking file {file_path}: {e}")
            
            logger.info(f"Startup scan complete: {existing_count} files added to queue")
            if skipped_count > 0:
                logger.info(f"Skipped {skipped_count} files older than {max_age_days} days")
        else:
            logger.info("Startup scan disabled - will only upload new files created after startup")
        # ===== END NEW =====
        
        # Start watchdog observer
        for directory in self.directories:
            self.observer.schedule(self.handler, str(directory), recursive=False)
        
        self.observer.start()
        
        # Start stability checker thread
        self._running = True
        self._checker_thread = threading.Thread(target=self._stability_checker, daemon=True)
        self._checker_thread.start()
        
        logger.info("Started monitoring")
    
    def stop(self):
        """
        Stop monitoring directories.
        
        Gracefully stops the watchdog observer and stability checker thread.
        Waits for threads to terminate (max 2 seconds for checker).
        
        Note:
            Safe to call multiple times
        """
        if not self._running:
            return
        
        self._running = False
        
        # Stop observer
        self.observer.stop()
        self.observer.join()
        
        # Wait for checker thread
        if self._checker_thread:
            self._checker_thread.join(timeout=2)
        
        logger.info("Stopped monitoring")
    
    def _on_file_event(self, file_path: str):
        """
        Called when watchdog detects a file create or modify event.
        
        Updates the file tracker with current file size and timestamp.
        Ignores hidden files (starting with '.') and directories.
        
        Args:
            file_path: Path to the file that changed
            
        Note:
            This runs in watchdog's event thread
        """
        path = Path(file_path)
        
        # Only track regular files (not directories)
        if not path.is_file():
            return
        
        # Skip hidden files and marker files
        if path.name.startswith('.'):
            return
        
        # Get current file size
        try:
            size = path.stat().st_size
        except (OSError, FileNotFoundError):
            # File might have been deleted
            return
        
        # Update tracker
        current_time = time.time()
        self.file_tracker[path] = (size, current_time)
        
        logger.debug(f"Tracking: {path.name} ({size} bytes)")
    
    def _stability_checker(self):
        """
        Background thread that periodically checks file stability.
        
        Checks all tracked files to see if they've been stable (unchanged)
        for the configured stability period. Checks immediately on start,
        then periodically based on stability_seconds (max 10 second intervals).
        
        Note:
            Runs in daemon thread, automatically stops when main thread exits
        """
        logger.info("Stability checker started")
        
        while self._running:
            self._check_stable_files()
            
            # Sleep in small increments so we can stop quickly
            sleep_time = min(self.stability_seconds, 10)
            for _ in range(sleep_time):
                if not self._running:
                    break
                time.sleep(1)
        
        logger.info("Stability checker stopped")
    
    def _check_stable_files(self):
        """
        Check all tracked files for stability.
        
        For each tracked file:
        1. Check if it still exists
        2. Get current size
        3. Compare with tracked size
        4. If unchanged for stability_seconds, mark as stable and call callback
        
        Automatically removes deleted files from tracker.
        Resets timer if file size changes.
        """
        logger.debug(f"Checking {len(self.file_tracker)} tracked files")
        current_time = time.time()
        stable_files = []
        
        for file_path, (tracked_size, last_check) in list(self.file_tracker.items()):
            # Check if file still exists
            if not file_path.exists():
                # File was deleted, remove from tracker
                del self.file_tracker[file_path]
                continue
            
            # Get current size
            try:
                current_size = file_path.stat().st_size
            except (OSError, FileNotFoundError):
                # File disappeared, remove from tracker
                del self.file_tracker[file_path]
                continue
            
            # Check if size changed
            if current_size != tracked_size:
                # Size changed, update tracker
                self.file_tracker[file_path] = (current_size, current_time)
                continue
            
            # Check if stable for required duration
            time_unchanged = current_time - last_check
            if time_unchanged >= self.stability_seconds:
                stable_files.append(file_path)
        
        # Process stable files
        for file_path in stable_files:
            logger.info(f"File stable: {file_path.name} ({self.file_tracker[file_path][0]} bytes)")
            
            # Remove from tracker (so we don't process it again)
            del self.file_tracker[file_path]
            
            # Call callback
            try:
                self.callback(str(file_path))
            except Exception as e:
                logger.error(f"Callback failed for {file_path}: {e}")
    
    def get_tracked_files(self) -> List[str]:
        """
        Get list of currently tracked files.
        
        Returns:
            List of file paths being tracked (not yet stable)
            
        Note:
            Useful for debugging and monitoring
        """
        return [str(p) for p in self.file_tracker.keys()]


class LogFileHandler(FileSystemEventHandler):
    """
    Watchdog event handler for log files.
    
    Forwards file create and modify events to a callback function.
    Ignores directory events.
    """
    
    def __init__(self, callback: Callable[[str], None]):
        """
        Initialize handler with callback.
        
        Args:
            callback: Function to call when file event occurs (receives file path)
        """
        self.callback = callback
    
    def on_created(self, event):
        """
        Called when a file is created.
        
        Args:
            event: FileSystemEvent with event details
        """
        if not event.is_directory:
            self.callback(event.src_path)
    
    def on_modified(self, event):
        """
        Called when a file is modified.
        
        Args:
            event: FileSystemEvent with event details
        """
        if not event.is_directory:
            self.callback(event.src_path)


if __name__ == '__main__':
    import sys
    
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    if len(sys.argv) < 2:
        logger.error("Usage: python file_monitor.py <directory>")
        sys.exit(1)
    
    directory = sys.argv[1]
    
    def on_file_ready(filepath):
        logger.info(f"*** FILE READY: {filepath} ***")
    
    # Test with startup scan enabled
    test_config = {
        'upload': {
            'scan_existing_files': {
                'enabled': True,
                'max_age_days': 3
            }
        }
    }
    
    monitor = FileMonitor([directory], on_file_ready, stability_seconds=10, config=test_config)
    
    try:
        monitor.start()
        logger.info(f"Monitoring {directory}")
        logger.info("Create/modify files to test. Press Ctrl+C to stop.")
        
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Stopping...")
        monitor.stop()