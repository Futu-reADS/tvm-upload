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

from config_manager import ConfigManager
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
    1. File Monitor detects stable files → adds to upload queue
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
        logger.info("Initializing TVM Upload System v2.0...")
        
        # Load configuration
        self.config = ConfigManager(config_path)
        
        # Initialize components
        self.upload_manager = UploadManager(
            bucket=self.config.get('s3.bucket'),
            region=self.config.get('s3.region'),
            vehicle_id=self.config.get('vehicle_id')
        )
        
        self.disk_manager = DiskManager(
            log_directories=self.config.get('log_directories'),
            reserved_gb=self.config.get('disk.reserved_gb'),
            warning_threshold=self.config.get('disk.warning_threshold', 0.90),
            critical_threshold=self.config.get('disk.critical_threshold', 0.95)
        )
        
        # Pass config to FileMonitor for startup scan (NEW v2.0)
        self.file_monitor = FileMonitor(
            directories=self.config.get('log_directories'),
            callback=self._on_file_ready,
            stability_seconds=self.config.get('upload.file_stable_seconds', 60),
            config=self.config.config  # Pass full config dict
        )

        self.cloudwatch = CloudWatchManager(
            region=self.config.get('s3.region'),
            vehicle_id=self.config.get('vehicle_id'),
            enabled=self.config.get('monitoring.cloudwatch_enabled', True)
        )

        self.queue_manager = QueueManager(
            queue_file=self.config.get('upload.queue_file', '/var/lib/tvm-upload/queue.json')
        )
        
        # Runtime state
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
        
        # Log deletion policy configuration (NEW v2.0)
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
        
        if after_upload_config.get('enabled', True):  # ← NEW: Check enabled
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
        
        # Start scheduling thread
        self._running = True
        self._schedule_thread = threading.Thread(target=self._schedule_loop, daemon=True)
        self._schedule_thread.start()
        
        logger.info("System started successfully")
        logger.info(f"Upload schedule: {self.config.get('upload.schedule')} daily")
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
    
    def _on_file_ready(self, filepath: str):
        """
        Callback when file monitor detects a stable file.
        
        Adds file to upload queue and triggers immediate upload
        if within operational hours.
        
        Args:
            filepath: Path to stable file
            
        Note:
            Thread-safe - uses lock to protect upload queue
        """
        self.stats['files_detected'] += 1
        
        logger.info(f"File ready: {Path(filepath).name}")
        
        # Add to persistent queue
        self.queue_manager.add_file(filepath)
        
        # Check if we should upload now
        if self._should_upload_now():
            self._process_upload_queue()
    
    def _should_upload_now(self) -> bool:
        """
        Determine if uploads should happen now based on operational hours.
        
        Checks if current time is within configured operational hours.
        If operational_hours not configured, always returns True.
        
        Returns:
            bool: True if within operational hours (or no restriction)
            
        Note:
            Silently allows upload if operational_hours parsing fails
        """
        now = datetime.now().time()
    
        # Check operational hours
        op_hours = self.config.get('upload.operational_hours')
        if op_hours and op_hours.get('enabled', True):
            try:
                start_time = datetime.strptime(op_hours['start'], '%H:%M').time()
                end_time = datetime.strptime(op_hours['end'], '%H:%M').time()
                
                if not (start_time <= now <= end_time):
                    logger.debug(f"Outside operational hours ({start_time}-{end_time})")
                    return False
            except Exception as e:
                logger.warning(f"Error parsing operational hours: {e}")
                # If parsing fails, allow upload
        
        return True
    
    def _schedule_loop(self):
        """
        Background thread for scheduled uploads and cleanup.
        
        Checks every minute for:
        - Scheduled upload time
        - Age-based cleanup time (NEW v2.0)
        
        Sleeps 1 hour after triggering to avoid multiple triggers.
        
        Note:
            Runs in daemon thread, logs errors but continues running
        """
        logger.info("Schedule loop started")
    
        last_upload_date = None
        last_cleanup_date = None
        
        while self._running:
            try:
                now = datetime.now()
                
                # ===== Scheduled upload check =====
                schedule_time = datetime.strptime(
                    self.config.get('upload.schedule'),
                    '%H:%M'
                ).time()
                
                if self._is_near_schedule_time(now.time(), schedule_time):
                    if last_upload_date != now.date():
                        logger.info(f"Scheduled upload time reached: {schedule_time}")
                        
                        if self._should_upload_now():
                            self._process_upload_queue()
                            last_upload_date = now.date()
                        else:
                            logger.info("Upload skipped: outside operational hours")
                        
                        # Sleep 1 hour to avoid multiple triggers
                        time.sleep(3600)
                
                # ===== NEW: Age-based cleanup check (v2.0) =====
                age_config = self.config.get('deletion.age_based', {})
                
                if age_config.get('enabled', True):  # Default: enabled
                    cleanup_time = datetime.strptime(
                        age_config.get('schedule_time', '02:00'),
                        '%H:%M'
                    ).time()
                    
                    if self._is_near_schedule_time(now.time(), cleanup_time):
                        if last_cleanup_date != now.date():
                            logger.info("=== Running scheduled age-based cleanup ===")
                            
                            max_age_days = age_config.get('max_age_days', 7)  # Default: 7 (Maeda-san)
                            deleted = self.disk_manager.cleanup_by_age(max_age_days)
                            
                            logger.info(f"Age-based cleanup complete: {deleted} files deleted")
                            last_cleanup_date = now.date()
                            
                            # Publish metrics after cleanup
                            usage, _, _ = self.disk_manager.get_disk_usage()
                            self.cloudwatch.publish_metrics(disk_usage_percent=usage * 100)
                            
                            # Sleep 1 hour to avoid multiple triggers
                            time.sleep(3600)
                # ===== END NEW =====
                
            except Exception as e:
                logger.error(f"Error in schedule loop: {e}")
            
            # Check every minute
            time.sleep(60)
        
        logger.info("Schedule loop stopped")
    
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
        
        return abs(now_minutes - schedule_minutes) <= 1
    
    def _process_upload_queue(self):
        """
        Process all files in upload queue.
        
        Uploads all queued files and checks disk space afterward.
        Runs cleanup if disk space is low after uploads (NEW v2.0: only if emergency enabled).
        
        Note:
            Thread-safe - uses lock to snapshot and clear queue atomically
        """
        batch = self.queue_manager.get_next_batch(max_files=50)
    
        if len(batch) == 0:
            return
        
        logger.info(f"Processing {len(batch)} files for upload")
        
        for filepath in batch:
            self._upload_file(filepath)
        
        # NEW v2.0: Check if emergency cleanup is enabled
        emergency_enabled = self.config.get('deletion.emergency.enabled', False)
        
        if emergency_enabled:
            # Check disk space after uploads
            if not self.disk_manager.check_disk_space():
                logger.warning("Low disk space after uploads, running EMERGENCY cleanup...")
                deleted = self.disk_manager.cleanup_old_files()
                logger.info(f"Emergency cleanup freed space by deleting {deleted} files")
        else:
            logger.debug("Emergency cleanup disabled - skipping disk check")
    
    def _upload_file(self, filepath: str):
        """
        Upload single file to S3.
        
        Updates statistics based on success/failure.
        Records CloudWatch metrics on success/failure.
        Handles file deletion based on configured policy (NEW v2.0).
        
        Args:
            filepath: Path to file to upload
            
        Note:
            Logs warning if file disappeared before upload
        """
        file_path = Path(filepath)
    
        if not file_path.exists():
            logger.warning(f"File disappeared: {file_path.name}")
            self.queue_manager.mark_uploaded(filepath)  # Remove from queue
            return
        
        file_size = file_path.stat().st_size
        success = self.upload_manager.upload_file(filepath)
        
        if success:
            self.stats['files_uploaded'] += 1
            self.stats['bytes_uploaded'] += file_size
            self.cloudwatch.record_upload_success(file_size)
            
            # Remove from queue
            self.queue_manager.mark_uploaded(filepath)
            
            # ===== NEW: Configurable deletion after upload (v2.0) =====
            after_upload_config = self.config.get('deletion.after_upload', {})
            
            if after_upload_config.get('enabled', True):
                keep_days = self.config.get('deletion.after_upload.keep_days', 14)  # Default: 14 (Maeda-san)
                
                if keep_days == 0:
                    # Option A1: Delete immediately
                    try:
                        file_path.unlink()
                        logger.info(f"Upload successful + DELETED: {file_path.name} "
                                f"({file_size / (1024**2):.2f} MB)")
                    except Exception as e:
                        logger.error(f"Failed to delete {file_path.name}: {e}")
                        # Fall back to marking for later cleanup
                        self.disk_manager.mark_uploaded(filepath, keep_until_days=0)
                else:
                    # Option A2: Keep for N days
                    self.disk_manager.mark_uploaded(filepath, keep_until_days=keep_days)
                    logger.info(f"Upload successful, keeping for {keep_days} days: {file_path.name} "
                            f"({file_size / (1024**2):.2f} MB)")
                
                # Run deferred deletion check (deletes files whose keep_until expired)
                deleted_count = self.disk_manager.cleanup_deferred_deletions()
                if deleted_count > 0:
                    logger.info(f"Deferred deletion: removed {deleted_count} expired files")
            
            else:
                # ← NEW: Deletion disabled branch
                logger.info(f"Upload successful, deletion DISABLED - keeping indefinitely: {file_path.name} "
                      f"({file_size / (1024**2):.2f} MB)")
            
        else:
            self.stats['files_failed'] += 1
            self.cloudwatch.record_upload_failure()
            
            # Increment attempt counter
            self.queue_manager.mark_failed(filepath)
            
            logger.error(f"Upload failed: {file_path.name}")
        
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


def signal_handler(signum, frame):
    """
    Handle shutdown signals (SIGTERM, SIGINT).
    
    Gracefully stops the system and exits.
    
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