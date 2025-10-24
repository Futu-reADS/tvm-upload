#!/usr/bin/env python3
"""
File Monitor for TVM Log Upload System
Watches directories and detects completed log files

Uses watchdog library to monitor filesystem events and determines when
files are complete based on size stability over a configured period.

Version: 2.0 - Added startup scan for existing files
Version: 2.1 - Added processed files registry to prevent duplicate uploads
"""

import json  # ← ADD THIS
import time
import threading
import logging
from pathlib import Path
from typing import Callable, Dict, Tuple, List
from datetime import datetime  # ← ADD THIS
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileCreatedEvent, FileModifiedEvent

logger = logging.getLogger(__name__)

# Registry Configuration
DEFAULT_REGISTRY_PATH = '/var/lib/tvm-upload/processed_files.json'
DEFAULT_RETENTION_DAYS = 30  # Keep registry entries for 30 days
FILE_IDENTITY_SEPARATOR = '::'  # Separator for filepath::size::mtime format


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
            
        Raises:
            PermissionError: If registry file cannot be written
            
        Note:
            Directories will be created if they don't exist
        """
        self.directories = [Path(d) for d in directories]
        self.callback = callback
        self.stability_seconds = stability_seconds
        self.config = config or {}
        
        # In-memory: Track files currently being written (stability check)
        # Format: {Path: (size, last_check_time)}
        self.file_tracker: Dict[Path, Tuple[int, float]] = {}
        
        # Persistent: Track files already uploaded (duplicate prevention)
        # Load registry settings from config
        registry_config = self.config.get('upload', {}).get('processed_files_registry', {})
        self.registry_file = Path(registry_config.get(
            'registry_file',
            DEFAULT_REGISTRY_PATH
        ))
        self.registry_retention_days = registry_config.get('retention_days', DEFAULT_RETENTION_DAYS)
        
        # Load processed files registry
        self.processed_files: Dict[str, dict] = self._load_processed_registry()
        
        # ===== NEW: Validate registry is writable at startup =====
        logger.info(f"Validating registry writability: {self.registry_file}")
        try:
            # Ensure directory exists
            parent_dir = self.registry_file.parent
            if not parent_dir.exists():
                parent_dir.mkdir(parents=True, exist_ok=True)
            
            # Test write by saving current registry (even if empty)
            self._save_processed_registry()
            logger.info("✓ Registry file is writable")
            
        except (PermissionError, OSError) as e:
            logger.error(f"✗ Registry file is NOT writable: {e}")
            logger.error("="*60)
            logger.error("FATAL: Cannot write to registry file")
            logger.error(f"Path: {self.registry_file}")
            logger.error("Registry persistence is REQUIRED for production operation")
            logger.error("Without persistent registry, files will be uploaded multiple times")
            logger.error("")
            logger.error("Action required:")
            logger.error("  1. Fix permissions: sudo chmod 666 {registry_file}")
            logger.error("  2. Or change registry_file path in config.yaml")
            logger.error("="*60)
            raise  # Fail fast - cannot continue without writable registry
        # ===== END NEW =====
        
        # Watchdog components
        self.observer = Observer()
        self.handler = LogFileHandler(self._on_file_event)
        
        # Control flags
        self._running = False
        self._checker_thread = None
        
        logger.info(f"Initialized monitoring {len(directories)} directories")
        logger.info(f"Stability period: {stability_seconds} seconds")
        logger.info(f"Processed files registry: {self.registry_file}")
        logger.info(f"Registry retention: {self.registry_retention_days} days")
        logger.info(f"Registry loaded: {len(self.processed_files)} entries")
    
    def _get_file_identity(self, file_path: Path) -> str:
        """
        Generate unique file identity key using path + size + mtime.
        
        This ensures same filename on different days = different files.
        Format: {absolute_path}::{size}::{mtime}
        
        Args:
            file_path: Path to file
            
        Returns:
            str: Unique identifier (e.g., "/var/log/file.log::1024::1705132800.0")
            None: If file cannot be accessed
            
        Example:
            >>> _get_file_identity(Path('/var/log/test.log'))
            '/var/log/test.log::104857600::1705132800.123'
        """
        try:
            stat = file_path.stat()
            size = stat.st_size
            mtime = stat.st_mtime

            # Create unique key: filepath::size::mtime
            return f"{file_path.resolve()}{FILE_IDENTITY_SEPARATOR}{size}{FILE_IDENTITY_SEPARATOR}{mtime}"
        except (OSError, FileNotFoundError) as e:
            logger.debug(f"Cannot get identity for {file_path}: {e}")
            return None
    
    
    def start(self):
        """
        Start monitoring directories.
        
        Starts the watchdog observer and stability checker thread.
        Creates directories if they don't exist.
        Optionally scans for existing files based on configuration (NEW v2.0).
        Uses processed files registry to prevent duplicate uploads (NEW v2.1).
        
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
        
        # ===== Startup scan with duplicate prevention =====
        scan_config = self.config.get('upload', {}).get('scan_existing_files', {})
        
        if scan_config.get('enabled', True):  # Default: enabled
            max_age_days = scan_config.get('max_age_days', 3)
            
            logger.info(f"Scanning for existing files (max age: {max_age_days} days)...")
            
            cutoff_time = time.time() - (max_age_days * 24 * 3600)
            existing_count = 0
            skipped_processed = 0
            skipped_tracked = 0
            skipped_old = 0
            
            for directory in self.directories:
                if not directory.exists():
                    continue
                
                for file_path in directory.iterdir():
                    if not file_path.is_file() or file_path.name.startswith('.'):
                        continue
                    
                    try:
                        mtime = file_path.stat().st_mtime
                        
                        # ✅ Check 1: Already processed? (with metadata)
                        if self._is_file_processed(file_path):
                            skipped_processed += 1
                            continue
                        
                        # ✅ Check 2: Already tracking? (in-memory)
                        if file_path in self.file_tracker:
                            logger.debug(f"Skipping already-tracked file: {file_path.name}")
                            skipped_tracked += 1
                            continue
                        
                        # ✅ Check 3: Within age window?
                        if max_age_days == 0 or mtime > cutoff_time:
                            self._on_file_event(str(file_path))
                            existing_count += 1
                            logger.debug(f"Found existing file: {file_path.name}")
                        else:
                            age_days = (time.time() - mtime) / 86400
                            logger.debug(
                                f"Skipping old file: {file_path.name} "
                                f"({age_days:.1f} days old, cutoff: {max_age_days} days)"
                            )
                            skipped_old += 1
                            
                    except (OSError, FileNotFoundError) as e:
                        logger.debug(f"Error checking file {file_path}: {e}")
            
            logger.info(
                f"Startup scan complete: {existing_count} files added, "
                f"{skipped_processed} already processed, "
                f"{skipped_tracked} already tracked, "
                f"{skipped_old} too old"
            )
        else:
            logger.info("Startup scan disabled - will only upload new files created after startup")
        
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
    
    def _load_processed_registry(self) -> dict:
        """
        Load processed files registry from disk with automatic cleanup.
        
        Registry format:
        {
            "filepath::size::mtime": {
                "processed_at": timestamp,
                "size": bytes,
                "mtime": timestamp,
                "filepath": str,
                "filename": str
            }
        }
        
        Cleanup actions:
        - Remove entries older than retention_days
        
        Returns:
            dict: Loaded registry (empty dict if file doesn't exist)
        """
        if not self.registry_file.exists():
            logger.info("No existing processed files registry, starting fresh")
            return {}
        
        try:
            with open(self.registry_file, 'r') as f:
                data = json.load(f)
            
            # Handle both old and new format
            if '_metadata' in data:
                files_data = data.get('files', {})
            else:
                # Legacy format (flat dict)
                files_data = data
            
            original_count = len(files_data)
            cutoff_time = time.time() - (self.registry_retention_days * 24 * 3600)
            
            # Remove time-expired entries
            cleaned = {
                key: meta 
                for key, meta in files_data.items() 
                if meta.get('processed_at', 0) > cutoff_time
            }
            
            removed = original_count - len(cleaned)
            if removed > 0:
                logger.info(
                    f"Registry cleanup: removed {removed}/{original_count} old entries "
                    f"(retention: {self.registry_retention_days} days)"
                )
            
            logger.info(f"Loaded {len(cleaned)} processed files from registry")
            return cleaned
            
        except json.JSONDecodeError as e:
            logger.error(f"Registry file corrupted: {e}")
            logger.warning("Starting with empty registry")
            return {}
        except Exception as e:
            logger.error(f"Failed to load processed registry: {e}")
            return {}


    def _save_processed_registry(self):
        """
        Save processed files registry to disk with metadata.
        
        Saves in JSON format with metadata for debugging and monitoring.
        Creates parent directories if they don't exist.
        
        Raises:
            PermissionError: If registry file cannot be written (CRITICAL)
            OSError: If disk I/O fails (CRITICAL)
        """
        try:
            # Ensure directory exists
            parent_dir = self.registry_file.parent
            if not parent_dir.exists():
                try:
                    parent_dir.mkdir(parents=True, exist_ok=True)
                except PermissionError as e:
                    logger.error(f"CRITICAL: Cannot create registry directory: {parent_dir}")
                    logger.error(f"Permission denied: {e}")
                    logger.error("Registry persistence is REQUIRED for production operation")
                    raise  # Fail fast - this is critical
            
            # Build registry data with metadata
            registry_data = {
                '_metadata': {
                    'last_updated': datetime.now().isoformat(),
                    'total_entries': len(self.processed_files),
                    'retention_days': self.registry_retention_days
                },
                'files': self.processed_files
            }
            
            # Write atomically using temp file
            temp_file = self.registry_file.with_suffix('.json.tmp')
            with open(temp_file, 'w') as f:
                json.dump(registry_data, f, indent=2)
            
            # Atomic rename
            temp_file.replace(self.registry_file)
            
            logger.debug(f"Saved {len(self.processed_files)} entries to registry")
            
        except PermissionError as e:
            logger.error(f"CRITICAL: Permission denied writing registry: {e}")
            logger.error(f"Registry file: {self.registry_file}")
            logger.error("="*60)
            logger.error("SYSTEM CANNOT CONTINUE WITHOUT PERSISTENT REGISTRY")
            logger.error("Registry persistence is REQUIRED to prevent duplicate uploads")
            logger.error("Action required: Fix permissions or change registry_file path in config")
            logger.error("="*60)
            raise  # Fail fast - don't continue without registry
            
        except OSError as e:
            logger.error(f"CRITICAL: Disk I/O error writing registry: {e}")
            logger.error(f"Registry file: {self.registry_file}")
            logger.error("="*60)
            logger.error("SYSTEM CANNOT CONTINUE - DISK I/O FAILURE")
            logger.error("Action required: Check disk space and filesystem health")
            logger.error("="*60)
            raise  # Fail fast - disk issues are critical
            
        except Exception as e:
            logger.error(f"CRITICAL: Unexpected error saving registry: {e}")
            logger.error(f"Registry file: {self.registry_file}")
            import traceback
            logger.error(traceback.format_exc())
            raise  # Fail fast for any unexpected errors

    def _is_file_processed(self, file_path: Path) -> bool:
        """
        Check if file has already been processed (uploaded).
        
        Uses file identity (path + size + mtime) to detect:
        - Same file rescanned: SKIP (already processed)
        - Same filename, different day: PROCESS (new file)
        
        Args:
            file_path: Path to check
            
        Returns:
            bool: True if already processed, False if new
        """
        file_identity = self._get_file_identity(file_path)
        
        if file_identity is None:
            return False
        
        is_processed = file_identity in self.processed_files
        
        if is_processed:
            meta = self.processed_files[file_identity]
            processed_time = datetime.fromtimestamp(meta['processed_at']).isoformat()
            logger.debug(
                f"File already processed: {file_path.name} "
                f"(processed at {processed_time}, size: {meta['size']} bytes)"
            )
        
        return is_processed


    def _mark_file_processed(self, file_path: Path, save_immediately: bool = True):
        """
        Mark file as processed with metadata.
        
        Stores:
        - File identity (path::size::mtime)
        - Processing timestamp
        - File size and mtime
        - Filepath and filename for debugging
        
        Args:
            file_path: Path to mark as processed
            save_immediately: If True, save registry to disk immediately.
                            If False, only update in-memory dict (caller must save).
                            Use False for batch operations, then call save_registry().
        
        Example:
            # Single file (immediate save)
            monitor._mark_file_processed(file_path)
            
            # Batch operation (deferred save)
            for file_path in batch:
                monitor._mark_file_processed(file_path, save_immediately=False)
            monitor.save_registry()  # Single save for entire batch
        """
        file_identity = self._get_file_identity(file_path)
        
        if file_identity is None:
            logger.warning(f"Cannot mark file as processed (stat failed): {file_path}")
            return
        
        try:
            stat = file_path.stat()
            
            self.processed_files[file_identity] = {
                'processed_at': time.time(),
                'size': stat.st_size,
                'mtime': stat.st_mtime,
                'filepath': str(file_path.resolve()),
                'filename': file_path.name
            }
            
            # Only save if requested (allows batching)
            if save_immediately:
                self._save_processed_registry()
                logger.info(
                    f"Marked as processed: {file_path.name} "
                    f"(size: {stat.st_size / (1024**2):.2f} MB)"
                )
            else:
                logger.debug(
                    f"Marked as processed (deferred save): {file_path.name} "
                    f"(size: {stat.st_size / (1024**2):.2f} MB)"
                )
                
        except Exception as e:
            logger.error(f"Failed to mark file as processed: {e}")

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
        
        v2.1: Prevents double-marking by checking registry before AND after callback.
        This handles batch uploads where files are marked inside _process_upload_queue().
        
        Automatically removes deleted files from tracker.
        Resets timer if file size changes.
        """
        logger.debug(f"Checking {len(self.file_tracker)} tracked files")
        current_time = time.time()
        stable_files = []
        
        for file_path, (tracked_size, last_check) in list(self.file_tracker.items()):
            # Check if file still exists
            if not file_path.exists():
                del self.file_tracker[file_path]
                logger.debug(f"File deleted, removed from tracker: {file_path.name}")
                continue
            
            # Get current size
            try:
                current_size = file_path.stat().st_size
            except (OSError, FileNotFoundError):
                del self.file_tracker[file_path]
                logger.debug(f"File disappeared, removed from tracker: {file_path.name}")
                continue
            
            # Check if size changed
            if current_size != tracked_size:
                self.file_tracker[file_path] = (current_size, current_time)
                logger.debug(
                    f"File size changed: {file_path.name} "
                    f"({tracked_size} -> {current_size} bytes)"
                )
                continue
            
            # Check if stable for required duration
            time_unchanged = current_time - last_check
            if time_unchanged >= self.stability_seconds:
                stable_files.append(file_path)
        
        # Process stable files
        for file_path in stable_files:
            logger.info(
                f"File stable: {file_path.name} "
                f"({self.file_tracker[file_path][0] / (1024**2):.2f} MB)"
            )
            
            # Step 1: Remove from tracker (no longer monitoring)
            del self.file_tracker[file_path]
            
            # Step 2: Check if already processed (safety check - prevents duplicate uploads)
            if self._is_file_processed(file_path):
                logger.info(f"File already processed (skipping duplicate): {file_path.name}")
                continue
            
            # Step 3: Call callback (upload) and check result
            upload_success = False
            try:
                upload_success = self.callback(str(file_path))
                
                if upload_success is None:
                    logger.warning(f"Callback returned None, assuming success: {file_path.name}")
                    upload_success = True
                    
            except Exception as e:
                logger.error(f"Callback failed for {file_path}: {e}")
                import traceback
                logger.debug(traceback.format_exc())
                upload_success = False
            
            # ===== Step 4: Check registry AGAIN after callback =====
            # For batch uploads, file may have been marked inside _process_upload_queue()
            # If so, don't mark again (prevents double-marking + double disk write)
            if self._is_file_processed(file_path):
                if upload_success:
                    logger.debug(
                        f"✓ Already marked during upload (batch): {file_path.name} "
                        f"(skipping duplicate mark)"
                    )
                else:
                    logger.warning(
                        f"File marked as processed but callback returned False: {file_path.name} "
                        f"(possible race condition or batch upload)"
                    )
                continue  # ← Skip marking
            # ===== END Step 4 =====
            
            # Step 5: Mark as processed ONLY if success AND not already marked
            if upload_success:
                self._mark_file_processed(file_path)
                logger.info(f"✓ Uploaded + marked as processed: {file_path.name}")
            else:
                logger.warning(
                    f"✗ Upload failed, NOT marking as processed: {file_path.name} "
                    f"(will retry on next restart if within scan age)"
                )
    
    def get_tracked_files(self) -> List[str]:
        """
        Get list of currently tracked files.
        
        Returns:
            List of file paths being tracked (not yet stable)
            
        Note:
            Useful for debugging and monitoring
        """
        return [str(p) for p in self.file_tracker.keys()]
    
    def mark_file_as_processed_externally(self, filepath: str, save_immediately: bool = True):
        """
        Mark a file as processed externally (called by main.py).
        
        Used when files are uploaded outside the normal callback flow:
        - Batch uploads (other files in the batch)
        - Scheduled uploads (files uploaded by schedule, not by stability trigger)
        
        This prevents duplicate uploads on service restart.
        
        Args:
            filepath: Path to file that was successfully uploaded
            save_immediately: If True, save registry to disk immediately.
                            If False, caller must call save_registry() manually.
                            Use False for batch operations to optimize disk I/O.
                
        Example:
            # Single file upload
            >>> file_monitor.mark_file_as_processed_externally('/var/log/file.log')
            
            # Batch upload (efficient)
            >>> for filepath in batch:
            ...     file_monitor.mark_file_as_processed_externally(filepath, save_immediately=False)
            >>> file_monitor.save_registry()  # Single save for entire batch
        """
        file_path = Path(filepath)
        
        # Safety check: Only mark if not already processed
        if not self._is_file_processed(file_path):
            self._mark_file_processed(file_path, save_immediately=save_immediately)
            
            if save_immediately:
                logger.info(f"✓ Marked as processed (external): {file_path.name}")
            else:
                logger.debug(f"✓ Marked as processed (external, deferred): {file_path.name}")
        else:
            logger.debug(f"Already marked as processed: {file_path.name}")


    def save_registry(self):
        """
        Manually save registry to disk.
        
        Use after batch operations with save_immediately=False to write
        all accumulated changes with a single disk I/O operation.
        
        Example:
            >>> # Batch operation
            >>> for filepath in batch:
            ...     monitor.mark_file_as_processed_externally(filepath, save_immediately=False)
            >>> monitor.save_registry()  # Single save for all files
        
        Note:
            Includes retry logic for transient I/O errors.
        """
        max_retries = 3
        retry_delay = 1  # seconds
        
        for attempt in range(1, max_retries + 1):
            try:
                self._save_processed_registry()
                
                if attempt > 1:
                    logger.info(f"Registry saved successfully (after {attempt} attempts)")
                else:
                    logger.debug("Registry saved successfully")
                
                return True
                
            except OSError as e:
                if attempt < max_retries:
                    logger.warning(
                        f"Registry save failed (attempt {attempt}/{max_retries}): {e}. "
                        f"Retrying in {retry_delay}s..."
                    )
                    time.sleep(retry_delay)
                else:
                    logger.error(
                        f"Registry save failed after {max_retries} attempts: {e}"
                    )
                    logger.error(
                        "IN-MEMORY MARKS WILL BE LOST ON RESTART! "
                        "Check disk space and permissions."
                    )
                    return False
            
            except Exception as e:
                logger.error(f"Unexpected error saving registry: {e}")
                import traceback
                logger.debug(traceback.format_exc())
                return False
        
        return False

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