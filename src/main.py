#!/usr/bin/env python3
"""
TVM Log Upload System - Main Application
Integrates all components for production use

This is the main entry point that coordinates file monitoring,
uploading, disk management, and scheduling.

Version: 2.0 - Added configurable deletion policies
"""

import sys
from pathlib import Path

# Add src to path for both direct execution and imports
current_dir = Path(__file__).parent
if str(current_dir) not in sys.path:
    sys.path.insert(0, str(current_dir))

import signal
import time
import logging
from datetime import datetime, time as dt_time
import threading
from typing import List

from config_manager import ConfigManager, ConfigValidationError
from file_monitor import FileMonitor
from upload_manager import UploadManager
from disk_manager import DiskManager
from cloudwatch_manager import CloudWatchManager
from queue_manager import QueueManager


logger = logging.getLogger(__name__)


class TVMUploadSystem:
    """
    Main system coordinator for TVM log upload.
    
    Coordinates:
    - Configuration management (config_manager)
    - File monitoring (file_monitor)
    - S3 uploads (upload_manager)
    - Disk space management (disk_manager)
    - Upload scheduling
    - Deletion policies (NEW v2.0)
    
    Architecture:
    1. File Monitor detects stable files â†’ adds to upload queue
    2. Scheduler triggers upload at configured time
    3. Upload Manager uploads files to S3 with retry
    4. Disk Manager tracks uploaded files and cleans up based on policy
    5. Age-based cleanup runs daily at scheduled time (NEW v2.0)
    
    Example:
        >>> system = TVMUploadSystem('/etc/tvm-upload/config.yaml')
        >>> system.start()
        >>> # ... system runs ...
        >>> system.stop()
    
    Attributes:
        config (ConfigManager): Configuration manager
        upload_manager (UploadManager): S3 upload manager
        disk_manager (DiskManager): Disk space manager
        file_monitor (FileMonitor): File monitoring component
        stats (dict): Runtime statistics (files detected/uploaded/failed)
    """
    
    def __init__(self, config_path: str):
        """
        Initialize TVM upload system.
        
        Loads configuration and initializes all components.
        Does not start monitoring - call start() to begin operation.
        
        Args:
            config_path: Path to configuration file
            
        Raises:
            FileNotFoundError: If config file doesn't exist
            ConfigValidationError: If config is invalid
        """
        logger.info("Initializing TVM Upload System v2.1...")
        
        # =========================================================================
        # STEP 1: Load and Validate Configuration
        # =========================================================================
        self.config = ConfigManager(config_path)
        
        # Get log_directories once and validate
        log_dir_configs = self.config.get('log_directories')
        
        # Validate that log_directories exists and is not empty
        if not log_dir_configs:
            raise ConfigValidationError(
                "log_directories is required but not configured in config file"
            )
        
        # =========================================================================
        # STEP 2: Extract Paths and Full Configs (ONCE, not three times!)
        # =========================================================================
        
        # Determine format and extract paths
        is_new_format = isinstance(log_dir_configs[0], dict)
        
        if is_new_format:
            # New format: [{path: "/path", source: "ros"}, ...]
            monitor_paths = [item['path'] for item in log_dir_configs]
        else:
            # Legacy format: ["/path/to/log", ...]
            monitor_paths = log_dir_configs
        
        logger.info(f"Configured {len(log_dir_configs)} log directories")
        if is_new_format:
            sources = [item['source'] for item in log_dir_configs]
            logger.info(f"Sources: {', '.join(sources)}")
        
        # =========================================================================
        # STEP 3: Initialize Components (pass appropriate format to each)
        # =========================================================================
        
        # Upload Manager: Needs full config (with source info)
        self.upload_manager = UploadManager(
            bucket=self.config.get('s3.bucket'),
            region=self.config.get('s3.region'),
            vehicle_id=self.config.get('vehicle_id'),
            profile_name=self.config.get('s3.profile'),
            log_directories=log_dir_configs  # Pass full config
        )
        
        # Disk Manager: Only needs paths (doesn't care about sources)
        self.disk_manager = DiskManager(
            log_directories=monitor_paths,  # Just paths
            reserved_gb=self.config.get('disk.reserved_gb'),
            warning_threshold=self.config.get('disk.warning_threshold', 0.90),
            critical_threshold=self.config.get('disk.critical_threshold', 0.95)
        )
        
        # Setup deletion callback to clean registry
        def on_file_deleted(filepath):
            """Remove deleted file from registry"""
            try:
                file_path = Path(filepath)
                if self.file_monitor._is_file_processed(file_path):
                    # Remove from registry
                    file_key = self.file_monitor._get_file_identity(file_path)
                    if file_key and file_key in self.file_monitor.processed_files:
                        del self.file_monitor.processed_files[file_key]
                        self.file_monitor._save_processed_registry()
                        logger.debug(f"Removed from registry: {file_path.name}")
            except Exception as e:
                logger.warning(f"Failed to remove from registry: {e}")
        
        self.disk_manager._on_file_deleted_callback = on_file_deleted
        
        # File Monitor: Only needs paths (doesn't care about sources)
        self.file_monitor = FileMonitor(
            directories=monitor_paths,  # Just paths
            callback=self._on_file_ready,
            stability_seconds=self.config.get('upload.file_stable_seconds', 60),
            config=self.config.config
        )
        
        # CloudWatch Manager
        self.cloudwatch = CloudWatchManager(
            region=self.config.get('s3.region'),
            vehicle_id=self.config.get('vehicle_id'),
            enabled=self.config.get('monitoring.cloudwatch_enabled', True)
        )
        
        # Queue Manager
        self.queue_manager = QueueManager(
            queue_file=self.config.get('upload.queue_file', '/var/lib/tvm-upload/queue.json')
        )
        
        # =========================================================================
        # STEP 4: Load Additional Settings
        # =========================================================================
        self.batch_upload_enabled = self.config.get('upload.batch_upload.enabled', True)
        self.upload_on_start = self.config.get('upload.upload_on_start', True)
        
        # =========================================================================
        # STEP 5: Initialize Runtime State
        # =========================================================================
        self._running = False
        self._upload_queue = []
        self._upload_lock = threading.Lock()
        self._schedule_thread = None
        
        # Statistics
        self.stats = {
            'files_detected': 0,
            'files_uploaded': 0,
            'files_failed': 0,
            'bytes_uploaded': 0
        }
        
        # Log deletion policy configuration
        self._log_deletion_config()
        
        logger.info("Initialization complete")
    
    def _log_deletion_config(self):
        """Log the current deletion policy configuration (NEW v2.0)."""
        logger.info("\n" + "="*60)
        logger.info("DELETION POLICY CONFIGURATION")
        logger.info("="*60)
        
        # Q1: Startup scan
        scan_config = self.config.get('upload.scan_existing_files', {})
        if scan_config.get('enabled', True):
            max_age = scan_config.get('max_age_days', 3)
            logger.info(f"Startup scan: ENABLED (upload files from last {max_age} days)")
        else:
            logger.info("Startup scan: DISABLED (only new files)")
        
        # Q2: After upload deletion (FIXED)
        after_upload_config = self.config.get('deletion.after_upload', {})
        
        if after_upload_config.get('enabled', True):  #NEW: Check enabled
            keep_days = after_upload_config.get('keep_days', 14)
            if keep_days == 0:
                logger.info("After upload: DELETE IMMEDIATELY")
            else:
                logger.info(f"After upload: KEEP for {keep_days} days")
        else:
            logger.info("After upload: DELETION DISABLED (keep files indefinitely)")
        
        # Q3: Age-based cleanup
        age_config = self.config.get('deletion.age_based', {})
        if age_config.get('enabled', True):
            max_age = age_config.get('max_age_days', 7)
            schedule = age_config.get('schedule_time', '02:00')
            logger.info(f"Age-based cleanup: ENABLED (delete >{max_age} days, daily at {schedule})")
        else:
            logger.info("Age-based cleanup: DISABLED")
        
        # Q5: Emergency cleanup
        emergency_enabled = self.config.get('deletion.emergency.enabled', False)
        if emergency_enabled:
            logger.info("Emergency cleanup: ENABLED (triggers at 90% disk full)")
        else:
            logger.info("Emergency cleanup: DISABLED")
        
        # Q4: S3 retention
        s3_retention = self.config.get('s3_lifecycle.retention_days', 14)
        logger.info(f"S3 retention: {s3_retention} days (AWS lifecycle policy)")
        
        logger.info("="*60 + "\n")
    
    def start(self):
        """
        Start the system.
        
        Starts file monitoring and scheduling thread.
        Checks disk space before starting and runs cleanup if needed.
        Optionally uploads queued files immediately on start (v2.1).
        
        Note:
            Safe to call multiple times - will not start if already running
        """
        if self._running:
            logger.warning("Already running")
            return
        
        logger.info("Starting TVM Upload System...")
        
        # Check disk space before starting
        if not self.disk_manager.check_disk_space():
            logger.warning("Low disk space detected")
            
            # Run emergency cleanup if enabled
            emergency_enabled = self.config.get('deletion.emergency.enabled', False)
            if emergency_enabled:
                logger.info("Running emergency cleanup before starting...")
                self.disk_manager.cleanup_old_files()
            else:
                logger.warning("Emergency cleanup disabled - disk may be full!")
        
        # Start file monitoring (includes startup scan)
        self.file_monitor.start()
        
        # ===== UPDATED: Upload on start with registry marking =====
        if self.upload_on_start and self.queue_manager.get_queue_size() > 0:
            queue_size = self.queue_manager.get_queue_size()
            logger.info(
                f"upload_on_start enabled - uploading {queue_size} queued files immediately"
            )
            
            # Upload and mark registry
            upload_results = self._process_upload_queue()
            
            successful_count = sum(1 for s in upload_results.values() if s)
            failed_count = len(upload_results) - successful_count
            
            if successful_count > 0:
                logger.info(
                    f"Scheduled upload complete: {successful_count} files uploaded, "
                    f"{failed_count} failed (will retry at next schedule)"
                )
            elif failed_count > 0:
                logger.warning(f"Scheduled upload: all {failed_count} files failed")
            else:
                logger.info("Scheduled upload: queue was empty")
        
        elif not self.upload_on_start and self.queue_manager.get_queue_size() > 0:
            logger.info(
                f"upload_on_start disabled - {self.queue_manager.get_queue_size()} files "
                f"queued for next scheduled upload"
            )
        # ===== END UPDATED =====
        
        # Start scheduling thread
        self._running = True
        self._schedule_thread = threading.Thread(target=self._schedule_loop, daemon=True)
        self._schedule_thread.start()
        
        logger.info("System started successfully")
        logger.info(f"Upload schedule: {self.config.get('upload.schedule')}")
        logger.info(f"Monitoring directories: {len(self.config.get('log_directories'))}")
    
    def stop(self):
        """
        Stop the system gracefully.
        
        Stops file monitoring and scheduling.
        Uploads any remaining queued files before shutdown.
        Prints final statistics.
        
        Note:
            Waits up to 5 seconds for schedule thread to terminate
        """
        if not self._running:
            return
        
        logger.info("Shutting down...")
        
        self._running = False
        
        # Stop monitoring
        self.file_monitor.stop()
        
        # Wait for schedule thread
        if self._schedule_thread:
            self._schedule_thread.join(timeout=5)
        
        # Upload any remaining queued files
        if self.queue_manager.get_queue_size() > 0:
            logger.info(f"Uploading {self.queue_manager.get_queue_size()} queued files before shutdown...")
            self._process_upload_queue()
        
        # Print statistics
        self._print_statistics()
        
        logger.info("Shutdown complete")
    
    def _on_file_ready(self, filepath: str) -> bool:
        """
        Callback when file monitor detects a stable file.
        
        Adds file to upload queue. Files are uploaded either:
        1. Immediately if within operational hours (optional)
        2. At scheduled interval (always)
        
        Args:
            filepath: Path to stable file
            
        Returns:
            bool: True if file was successfully uploaded, False if queued or failed
            
        Note:
            Return value is used by file_monitor to decide whether to mark
            file as processed in registry (only mark if upload succeeded).
            
            For batch uploads, registry marking happens in _process_upload_queue()
            for all files in the batch, and this function returns the status for
            the specific file that triggered the batch.
        """
        self.stats['files_detected'] += 1
        
        logger.info(f"File ready: {Path(filepath).name}")
        
        # Always add to persistent queue first
        self.queue_manager.add_file(filepath)
        
        # Check if operational hours allow immediate upload
        op_hours = self.config.get('upload.operational_hours', {})
        
        if op_hours.get('enabled', False):
            # Operational hours enabled - check if we can upload now
            if self._should_upload_now():
                logger.info("Within operational hours, uploading")
                
                if self.batch_upload_enabled:
                    # Upload entire queue (maximizes WiFi opportunities)
                    logger.info("Batch upload enabled - uploading entire queue")
                    
                    # ===== IMPROVED: Use explicit result from _process_upload_queue =====
                    # Instead of inferring success from queue state, use actual upload results
                    upload_results = self._process_upload_queue()
                    
                    # Check explicit result for this specific file
                    if filepath in upload_results:
                        success = upload_results[filepath]
                        if success:
                            logger.debug(f" Batch upload succeeded for trigger file: {Path(filepath).name}")
                        else:
                            logger.debug(f" Batch upload failed for trigger file: {Path(filepath).name}")
                        # Return FALSE regardless - registry already marked in _process_upload_queue()
                        return False
                    else:
                        # File not in results (shouldn't happen, but handle gracefully)
                        logger.warning(
                            f"Trigger file not in batch results: {Path(filepath).name} "
                            f"(possibly removed from queue before upload)"
                        )
                        return False
                    # ===== END IMPROVED =====
                else:
                    # Upload only this single file
                    logger.info("Batch upload disabled - uploading only this file")
                    return self._upload_single_file_now(filepath)
            else:
                logger.info("Outside operational hours, queued for scheduled upload")
                return False  # Queued, not uploaded yet
        else:
            # Operational hours disabled - queue for scheduled upload only
            logger.info(f"Queued for scheduled upload")
            return False  # Queued, not uploaded yet
    
    def _upload_single_file_now(self, filepath: str) -> bool:
        """
        Upload a single file immediately (for non-batch mode).
        
        Args:
            filepath: Path to file to upload
            
        Returns:
            bool: True if upload succeeded, False otherwise
        """
        file_path = Path(filepath)
        
        if not file_path.exists():
            logger.warning(f"File disappeared before upload: {file_path.name}")
            self.queue_manager.remove_from_queue(filepath)  # Remove from queue
            return False
        
        try:
            file_size = file_path.stat().st_size
            
            # Attempt upload
            from upload_manager import PermanentUploadError
            
            try:
                success = self.upload_manager.upload_file(filepath)
            except PermanentUploadError as e:
                logger.error(f"Permanent upload error: {e}")
                self.queue_manager.mark_permanent_failure(filepath, str(e))
                self.stats['files_failed'] += 1
                return False
            
            if success:
                # Upload succeeded
                self.stats['files_uploaded'] += 1
                self.stats['bytes_uploaded'] += file_size
                self.cloudwatch.record_upload_success(file_size)
                
                # Remove from queue
                self.queue_manager.remove_from_queue(filepath)
                
                # Handle file deletion based on policy
                self._handle_post_upload_deletion(file_path, file_size)
                
                return True
            else:
                # Upload failed (temporary error - will retry later)
                self.stats['files_failed'] += 1
                self.cloudwatch.record_upload_failure()
                self.queue_manager.mark_failed(filepath)
                logger.error(f"Upload failed (temporary): {file_path.name}")
                return False
                
        except Exception as e:
            logger.error(f"Unexpected error uploading {file_path.name}: {e}")
            self.stats['files_failed'] += 1
            return False


    def _handle_post_upload_deletion(self, file_path: Path, file_size: int):
        """
        Handle file deletion after successful upload based on configured policy.
        
        Args:
            file_path: Path to uploaded file
            file_size: Size of uploaded file in bytes
        """
        after_upload_config = self.config.get('deletion.after_upload', {})
        
        if after_upload_config.get('enabled', True):
            keep_days = after_upload_config.get('keep_days', 14)
            
            if keep_days == 0:
                # Delete immediately
                try:
                    file_path.unlink()
                    logger.info(
                        f"Upload successful + DELETED: {file_path.name} "
                        f"({file_size / (1024**2):.2f} MB)"
                    )
                except Exception as e:
                    logger.error(f"Failed to delete {file_path.name}: {e}")
                    # Fall back to marking for later cleanup
                    self.disk_manager.mark_uploaded(str(file_path), keep_until_days=0)
            else:
                # Keep for N days
                self.disk_manager.mark_uploaded(str(file_path), keep_until_days=keep_days)
                logger.info(
                    f"Upload successful, keeping for {keep_days} days: {file_path.name} "
                    f"({file_size / (1024**2):.2f} MB)"
                )
            
            # Run deferred deletion check
            deleted_count = self.disk_manager.cleanup_deferred_deletions()
            if deleted_count > 0:
                logger.info(f"Deferred deletion: removed {deleted_count} expired files")
        else:
            # Deletion disabled - keep indefinitely
            logger.info(
                f"Upload successful, deletion DISABLED - keeping indefinitely: {file_path.name} "
                f"({file_size / (1024**2):.2f} MB)"
            )

            

    def _should_upload_now(self) -> bool:
        """
        Determine if uploads should happen now based on operational hours.
        
        This is ONLY checked when operational_hours.enabled = true.
        When disabled, files queue until scheduled time.
        
        Returns:
            bool: True if within operational hours, False otherwise
        """
        now = datetime.now().time()

        # Check operational hours
        op_hours = self.config.get('upload.operational_hours', {})
        
        if not op_hours.get('enabled', False):
            # If operational hours not configured/enabled, 
            # this function shouldn't be called, but return False to be safe
            return False
        
        try:
            start_time = datetime.strptime(op_hours['start'], '%H:%M').time()
            end_time = datetime.strptime(op_hours['end'], '%H:%M').time()
            
            if not (start_time <= now <= end_time):
                logger.debug(f"Outside operational hours ({start_time}-{end_time})")
                return False
        except Exception as e:
            logger.warning(f"Error parsing operational hours: {e}")
            return False
        
        return True
    
    def _schedule_loop(self):
        """
        Background thread for scheduled uploads and cleanup.

        Supports two scheduling modes (v2.1):
        - Daily: Upload once per day at specific time
        - Interval: Upload every N hours/minutes

        Also handles age-based cleanup (runs daily at configured time).

        NEW v2.1: Marks successfully uploaded files in registry to prevent
        duplicate uploads on restart.

        Note:
            Runs in daemon thread, logs errors but continues running
        """
        logger.info("Schedule loop started")

        last_upload_time = None  # For interval mode (timestamp)
        last_upload_date = None  # For daily mode (date)
        last_cleanup_date = None

        while self._running:
            try:
                now = datetime.now()

                # Handle scheduled uploads
                last_upload_date, last_upload_time = self._handle_scheduled_uploads(
                    now, last_upload_date, last_upload_time
                )

                # Handle age-based cleanup
                last_cleanup_date = self._handle_age_based_cleanup(now, last_cleanup_date)

            except Exception as e:
                logger.error(f"Error in schedule loop: {e}")
                import traceback
                logger.debug(traceback.format_exc())

            # Check every minute
            time.sleep(60)

        logger.info("Schedule loop stopped")

    def _handle_scheduled_uploads(self, now, last_upload_date, last_upload_time):
        """
        Handle scheduled upload logic (daily or interval mode).

        Args:
            now: Current datetime
            last_upload_date: Last upload date (for daily mode)
            last_upload_time: Last upload timestamp (for interval mode)

        Returns:
            Tuple[date, float]: Updated (last_upload_date, last_upload_time)
        """
        schedule_config = self.config.get('upload.schedule')

        # Handle both old (string) and new (dict) format
        if isinstance(schedule_config, str):
            # Legacy format: "15:00" (treat as daily)
            schedule_time = datetime.strptime(schedule_config, '%H:%M').time()

            if self._is_near_schedule_time(now.time(), schedule_time):
                if last_upload_date != now.date():
                    logger.info(f"Scheduled upload time reached: {schedule_time}")
                    upload_results = self._process_upload_queue()
                    self._log_upload_results(upload_results, "Scheduled")

                    last_upload_date = now.date()
                    time.sleep(3600)  # Sleep 1 hour to avoid multiple triggers

        elif isinstance(schedule_config, dict):
            mode = schedule_config.get('mode', 'daily')

            if mode == 'daily':
                # Daily mode: Upload at specific time
                daily_time = datetime.strptime(
                    schedule_config.get('daily_time', '15:00'),
                    '%H:%M'
                ).time()

                if self._is_near_schedule_time(now.time(), daily_time):
                    if last_upload_date != now.date():
                        logger.info(f"Daily scheduled upload at {daily_time}")
                        upload_results = self._process_upload_queue()
                        self._log_upload_results(upload_results, "Daily")

                        last_upload_date = now.date()
                        time.sleep(3600)

            elif mode == 'interval':
                # Interval mode: Upload every N hours/minutes
                interval_hours = schedule_config.get('interval_hours', 0)
                interval_minutes = schedule_config.get('interval_minutes', 0)
                interval_seconds = (interval_hours * 3600) + (interval_minutes * 60)

                # Check if enough time has passed since last upload
                if last_upload_time is None or \
                   (now.timestamp() - last_upload_time) >= interval_seconds:
                    logger.info(
                        f"Interval upload triggered "
                        f"(every {interval_hours}h {interval_minutes}m)"
                    )
                    upload_results = self._process_upload_queue()
                    self._log_upload_results(upload_results, "Interval")

                    last_upload_time = now.timestamp()
                    time.sleep(10)  # Brief sleep to avoid tight loop

        return last_upload_date, last_upload_time

    def _handle_age_based_cleanup(self, now, last_cleanup_date):
        """
        Handle age-based cleanup if scheduled time reached.

        Args:
            now: Current datetime
            last_cleanup_date: Last cleanup date

        Returns:
            date: Updated last_cleanup_date if cleanup ran, otherwise unchanged
        """
        age_config = self.config.get('deletion.age_based', {})

        if age_config.get('enabled', True):
            cleanup_time = datetime.strptime(
                age_config.get('schedule_time', '02:00'),
                '%H:%M'
            ).time()

            if self._is_near_schedule_time(now.time(), cleanup_time):
                if last_cleanup_date != now.date():
                    logger.info("=== Running scheduled age-based cleanup ===")

                    max_age_days = age_config.get('max_age_days', 7)
                    deleted = self.disk_manager.cleanup_by_age(max_age_days)

                    logger.info(f"Age-based cleanup complete: {deleted} files deleted")
                    last_cleanup_date = now.date()

                    # Publish metrics after cleanup
                    usage, _, _ = self.disk_manager.get_disk_usage()
                    self.cloudwatch.publish_metrics(disk_usage_percent=usage * 100)

                    time.sleep(3600)

        return last_cleanup_date

    def _log_upload_results(self, upload_results: dict, upload_type: str):
        """
        Log summary of upload results.

        Eliminates code duplication across different upload modes (Daily/Interval/Scheduled).

        Args:
            upload_results: Dict of {filepath: success_bool}
            upload_type: Type of upload for logging ("Daily", "Interval", "Scheduled")
        """
        successful_count = sum(1 for s in upload_results.values() if s)
        failed_count = len(upload_results) - successful_count

        if successful_count > 0:
            logger.info(
                f"{upload_type} upload complete: {successful_count} files uploaded, "
                f"{failed_count} failed"
            )
        elif failed_count > 0:
            logger.warning(f"{upload_type} upload: all {failed_count} files failed")
        else:
            logger.warning(f"{upload_type} upload: all files failed")

    def _is_near_schedule_time(self, now: dt_time, schedule: dt_time) -> bool:
        """
        Check if current time is within 1 minute of scheduled time.
        
        Args:
            now: Current time
            schedule: Scheduled time
            
        Returns:
            bool: True if within 1 minute (before or after)
            
        Example:
            >>> _is_near_schedule_time(time(15, 00), time(15, 00))  # True
            >>> _is_near_schedule_time(time(15, 01), time(15, 00))  # True
            >>> _is_near_schedule_time(time(15, 02), time(15, 00))  # False
        """
        now_minutes = now.hour * 60 + now.minute
        schedule_minutes = schedule.hour * 60 + schedule.minute
        
        return  abs(now_minutes - schedule_minutes) <= 1
    
    def _process_upload_queue(self) -> dict:
        """
        Process all files in upload queue with batch registry optimization.
        
        Features:
        - Returns explicit success/failure status for each file
        - Only marks successfully uploaded files in registry
        - Failed files remain in queue for retry
        - Batch registry saves for efficiency (single disk write per batch)
        - Periodic checkpoints for large batches (safety against crashes)
        - try-finally ensures registry saved even on exception
        
        NEW v2.1: Marks successfully uploaded files in registry to prevent
        duplicate uploads on restart.
        
        Returns:
            dict: {filepath: success_bool} - Upload result for each file
                success_bool is True if uploaded successfully, False otherwise
                
        Note:
            Thread-safe - uses queue_manager's internal locking
        """
        batch = self.queue_manager.get_next_batch(max_files=50)

        if len(batch) == 0:
            logger.debug("Upload queue empty, nothing to process")
            return {}
        
        logger.info(f"Processing {len(batch)} files for upload")
        
        # Track upload results for each file
        upload_results = {}
        files_to_mark = []  # Collect successful uploads for registry
        checkpoint_interval = 10  # Save registry every N successful uploads
        
        try:
            for idx, filepath in enumerate(batch, start=1):
                # ===== IMPROVED: Get explicit success/failure from _upload_file =====
                # _upload_file now returns True/False instead of inferring from queue
                success = self._upload_file(filepath)
                upload_results[filepath] = success
                # ===== END IMPROVED =====
                
                # Collect successful uploads for registry marking
                if success:
                    files_to_mark.append(filepath)
                
                # Periodic checkpoint save for large batches
                # This limits data loss to checkpoint_interval files if crash occurs
                if len(files_to_mark) >= checkpoint_interval:
                    self._save_registry_checkpoint(files_to_mark, is_final=False)
                    files_to_mark = []  # Clear saved files
                
        except Exception as e:
            logger.error(f"Error during batch upload: {e}")
            import traceback
            logger.debug(traceback.format_exc())
        
        finally:
            # Final save for remaining files (always executes, even on exception)
            if files_to_mark:
                self._save_registry_checkpoint(files_to_mark, is_final=True)
        
        # Log summary
        successful_count = sum(1 for s in upload_results.values() if s)
        failed_count = len(upload_results) - successful_count
        logger.info(
            f"Upload batch complete: {successful_count} succeeded, "
            f"{failed_count} failed"
        )
        
        # Disk cleanup (unchanged)
        emergency_enabled = self.config.get('deletion.emergency.enabled', False)
        
        if emergency_enabled:
            usage, _, _ = self.disk_manager.get_disk_usage()
            
            # Critical threshold (>95%) - Delete ANY old files
            if usage >= self.disk_manager.critical_threshold:
                logger.error(" CRITICAL: Disk usage >95% - triggering EMERGENCY cleanup")
                deleted = self.disk_manager.emergency_cleanup_all_files()
                logger.warning(f" Emergency cleanup: {deleted} files deleted (ANY files, not just uploaded)")
            
            # Warning threshold (90-95%) - Delete uploaded files only
            elif usage >= self.disk_manager.warning_threshold:
                logger.warning(f"Disk usage at {usage*100:.1f}% (>90%) - cleaning uploaded files")
                deleted = self.disk_manager.cleanup_old_files()
                logger.info(f"Standard cleanup: {deleted} uploaded files deleted")
            
            # Below warning threshold - No cleanup needed
            else:
                logger.debug(f"Disk usage OK: {usage*100:.1f}%")
        else:
            logger.debug("Emergency cleanup disabled - skipping disk check")
        
        return upload_results

    def _save_registry_checkpoint(self, files_to_mark: List[str], is_final: bool = False):
        """
        Save registry checkpoint for batch of successful uploads.
        
        Marks all files in the list as processed in the registry with a single
        disk write operation. This optimizes I/O for batch uploads.
        
        Args:
            files_to_mark: List of successfully uploaded file paths
            is_final: True if this is the final save for the batch
        
        Example:
            # Checkpoint save (every 10 files)
            >>> self._save_registry_checkpoint(['file1.log', 'file2.log'], is_final=False)
            
            # Final save (remaining files)
            >>> self._save_registry_checkpoint(['file3.log'], is_final=True)
        
        Note:
            This method uses save_immediately=False to batch all marks,
            then calls save_registry() once for efficient disk I/O.
        """
        if not files_to_mark:
            return
        
        checkpoint_type = "Final" if is_final else "Checkpoint"
        logger.info(f"{checkpoint_type}: Marking {len(files_to_mark)} files in registry")
        
        # Mark all files with deferred save (in-memory only)
        for filepath in files_to_mark:
            self.file_monitor.mark_file_as_processed_externally(
                filepath, 
                save_immediately=False  # Defer save
            )
        
        # Single registry save for all files
        success = self.file_monitor.save_registry()
        
        if success:
            logger.info(f" {checkpoint_type} saved: {len(files_to_mark)} files marked")
        else:
            logger.error(
                f" {checkpoint_type} save failed: {len(files_to_mark)} files "
                f"may not be marked (will retry upload on restart)"
            )

    
    def _upload_file(self, filepath: str) -> bool:
        """
        Upload single file to S3.
        
        Updates statistics based on success/failure.
        Records CloudWatch metrics on success/failure.
        Handles file deletion based on configured policy (NEW v2.0).
        Handles permanent upload errors (NEW v2.1).
        
        Args:
            filepath: Path to file to upload
            
        Returns:
            bool: True if upload succeeded, False otherwise
            
        Note:
            Logs warning if file disappeared before upload
        """
        file_path = Path(filepath)

        if not file_path.exists():
            # Check if file was in processed registry
            if self.file_monitor._is_file_processed(file_path):
                logger.info(
                    f"File already processed and deleted: {file_path.name} "
                    f"(removed from queue, no re-upload needed)"
                )
            else:
                logger.warning(
                    f"File disappeared before upload: {file_path.name} "
                    f"(possibly deleted by user/policy, removed from queue)"
                )
            
            self.queue_manager.remove_from_queue(filepath)
            return False  # Not a success
        
        file_size = file_path.stat().st_size
        
        # ===== Handle permanent errors (v2.1) =====
        from upload_manager import PermanentUploadError
        
        try:
            success = self.upload_manager.upload_file(filepath)
        except PermanentUploadError as e:
            logger.error(f"Permanent upload error: {e}")
            self.queue_manager.mark_permanent_failure(filepath, str(e))
            self.stats['files_failed'] += 1
            self.cloudwatch.record_upload_failure()
            return False  # Failed permanently
        
        if success:
            self.stats['files_uploaded'] += 1
            self.stats['bytes_uploaded'] += file_size
            self.cloudwatch.record_upload_success(file_size)
            
            # Remove from queue
            self.queue_manager.remove_from_queue(filepath)
            
            # Handle post-upload deletion
            self._handle_post_upload_deletion(file_path, file_size)
            
            return True  # Success
            
        else:
            self.stats['files_failed'] += 1
            self.cloudwatch.record_upload_failure()
            
            # Increment attempt counter
            self.queue_manager.mark_failed(filepath)
            
            logger.error(f"Upload failed: {file_path.name}")
            return False  # Failed (temporary)
        
    def _print_statistics(self):
        """
        Print system statistics.
        
        Shows:
        - Files detected
        - Files uploaded successfully
        - Files failed
        - Total data uploaded (GB)
        """
        logger.info("\n" + "="*50)
        logger.info("System Statistics")
        logger.info("="*50)
        logger.info(f"Files detected:     {self.stats['files_detected']}")
        logger.info(f"Files uploaded:     {self.stats['files_uploaded']}")
        logger.info(f"Files failed:       {self.stats['files_failed']}")
        logger.info(f"Data uploaded:      {self.stats['bytes_uploaded'] / (1024**3):.2f} GB")
        logger.info("="*50 + "\n")

    def get_statistics(self) -> dict:
        """
        Public snapshot for tests/monitoring.
        Matches test expectations: keys 'detected', 'uploaded', 'failed'.
        """
        s = self.stats
        return {
            "detected": int(s.get("files_detected", 0)),
            "uploaded": int(s.get("files_uploaded", 0)),
            "failed":   int(s.get("files_failed", 0)),
            "bytes_uploaded": int(s.get("bytes_uploaded", 0)),
        }


def signal_handler(signum, frame):
    """
    Handle shutdown signals (SIGTERM, SIGINT).
    
    SIGTERM/SIGINT: Gracefully stops the system and exits.
    
    Note on SIGHUP:
    - SIGHUP triggers config validation but does NOT apply changes
    - Config changes require full service restart: sudo systemctl restart tvm-upload
    - SIGHUP is handled by ConfigManager, not this handler
    
    Args:
        signum: Signal number
        frame: Current stack frame
    """
    logger.info(f"Received signal {signum}")
    if 'system' in globals():
        system.stop()
    sys.exit(0)


def main():
    """
    Main entry point for TVM Upload System.
    
    Parses command-line arguments, sets up logging, and runs the system.
    Handles graceful shutdown on SIGTERM/SIGINT.
    
    Command-line arguments:
        --config: Path to configuration file
        --test-config: Test configuration and exit
        --log-level: Logging level (DEBUG, INFO, WARNING, ERROR)
    """
    import argparse
    
    parser = argparse.ArgumentParser(description='TVM Log Upload System v2.0')
    parser.add_argument(
        '--config',
        default='/etc/tvm-upload/config.yaml',
        help='Path to configuration file'
    )
    parser.add_argument(
        '--test-config',
        action='store_true',
        help='Test configuration and exit'
    )
    parser.add_argument(
        '--log-level',
        default='INFO',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        help='Logging level'
    )
    
    args = parser.parse_args()
    
    # Set up logging
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format='%(asctime)s [%(name)s] [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Test config mode
    if args.test_config:
        try:
            config = ConfigManager(args.config)
            logger.info("Configuration valid!")
            logger.info(f"Vehicle ID: {config.get('vehicle_id')}")
            logger.info(f"S3 Bucket: {config.get('s3.bucket')}")
            logger.info(f"Directories: {config.get('log_directories')}")
            
            # Show deletion policy (NEW v2.0)
            logger.info("\nDeletion Policy:")
            logger.info(f"  After upload: keep {config.get('deletion.after_upload.keep_days', 14)} days")
            logger.info(f"  Age cleanup: {config.get('deletion.age_based.max_age_days', 7)} days")
            logger.info(f"  Emergency: {config.get('deletion.emergency.enabled', False)}")
            
            sys.exit(0)
        except Exception as e:
            logger.error(f"Configuration error: {e}")
            sys.exit(1)
    
    # Register signal handlers
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    # Initialize and start system
    global system
    
    try:
        system = TVMUploadSystem(args.config)
        system.start()
        
        # Keep running
        logger.info("Running... Press Ctrl+C to stop")
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
        system.stop()
    except Exception as e:
        logger.error(f"FATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()