#!/usr/bin/env python3
"""
TVM Log Upload System - Main Application
Integrates all components for production use
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

logger = logging.getLogger(__name__)


class TVMUploadSystem:
    """
    Main system coordinator
    
    Responsibilities:
    - Load configuration
    - Start file monitoring
    - Upload files to S3
    - Manage disk space
    - Handle scheduling
    """
    
    def __init__(self, config_path: str):
        """
        Initialize TVM upload system
        
        Args:
            config_path: Path to configuration file
        """
        logger.info("Initializing TVM Upload System...")
        
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
        
        self.file_monitor = FileMonitor(
            directories=self.config.get('log_directories'),
            callback=self._on_file_ready,
            stability_seconds=self.config.get('upload.file_stable_seconds', 60)
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
        
        logger.info("Initialization complete")
    
    def start(self):
        """Start the system"""
        if self._running:
            logger.warning("Already running")
            return
        
        logger.info("Starting TVM Upload System...")
        
        # Check disk space before starting
        if not self.disk_manager.check_disk_space():
            logger.warning("Low disk space detected")
            logger.info("Running cleanup before starting...")
            self.disk_manager.cleanup_old_files()
        
        # Start file monitoring
        self.file_monitor.start()
        
        # Start scheduling thread
        self._running = True
        self._schedule_thread = threading.Thread(target=self._schedule_loop, daemon=True)
        self._schedule_thread.start()
        
        logger.info("System started successfully")
        logger.info(f"Upload schedule: {self.config.get('upload.schedule')} daily")
        logger.info(f"Monitoring directories: {len(self.config.get('log_directories'))}")
    
    def stop(self):
        """Stop the system gracefully"""
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
        if len(self._upload_queue) > 0:
            logger.info(f"Uploading {len(self._upload_queue)} queued files before shutdown...")
            self._process_upload_queue()
        
        # Print statistics
        self._print_statistics()
        
        logger.info("Shutdown complete")
    
    def _on_file_ready(self, filepath: str):
        """
        Called when file monitor detects a stable file
        
        Args:
            filepath: Path to stable file
        """
        self.stats['files_detected'] += 1
        
        logger.info(f"File ready: {Path(filepath).name}")
        
        # Add to upload queue
        with self._upload_lock:
            if filepath not in self._upload_queue:
                self._upload_queue.append(filepath)
        
        # Check if we should upload now
        if self._should_upload_now():
            self._process_upload_queue()
    
    def _should_upload_now(self) -> bool:
        """
        Determine if we should upload now based on schedule
        
        Returns:
            bool: True if within operational hours
        """
        now = datetime.now().time()
        
        # Get operational hours from config (optional)
        op_hours = self.config.get('upload.operational_hours')
        if not op_hours:
            # No restriction - always upload
            return True
        
        # Parse operational hours
        try:
            start_time = datetime.strptime(op_hours['start'], '%H:%M').time()
            end_time = datetime.strptime(op_hours['end'], '%H:%M').time()
            
            return start_time <= now <= end_time
        except:
            # If parsing fails, allow upload
            return True
    
    def _schedule_loop(self):
        """
        Background thread for scheduled uploads
        Checks every minute if it's time to upload
        """
        logger.info("Schedule loop started")
        
        while self._running:
            try:
                # Check if it's the scheduled upload time
                now = datetime.now().time()
                schedule_time = datetime.strptime(
                    self.config.get('upload.schedule'), 
                    '%H:%M'
                ).time()
                
                # If within 1 minute of schedule time, trigger upload
                if self._is_near_schedule_time(now, schedule_time):
                    logger.info(f"Scheduled upload time reached: {schedule_time}")
                    self._process_upload_queue()
                    
                    # Sleep until next day to avoid multiple triggers
                    time.sleep(3600)
                
            except Exception as e:
                logger.error(f"Error in schedule loop: {e}")
            
            # Check every minute
            time.sleep(60)
        
        logger.info("Schedule loop stopped")
    
    def _is_near_schedule_time(self, now: dt_time, schedule: dt_time) -> bool:
        """
        Check if current time is within 1 minute of scheduled time
        
        Args:
            now: Current time
            schedule: Scheduled time
            
        Returns:
            bool: True if within 1 minute
        """
        now_minutes = now.hour * 60 + now.minute
        schedule_minutes = schedule.hour * 60 + schedule.minute
        
        return abs(now_minutes - schedule_minutes) <= 1
    
    def _process_upload_queue(self):
        """Process all files in upload queue"""
        with self._upload_lock:
            if len(self._upload_queue) == 0:
                return
            
            files_to_upload = list(self._upload_queue)
            self._upload_queue.clear()
        
        logger.info(f"Processing {len(files_to_upload)} files for upload")
        
        for filepath in files_to_upload:
            self._upload_file(filepath)
        
        # Check disk space after uploads
        if not self.disk_manager.check_disk_space():
            logger.warning("Low disk space after uploads, running cleanup...")
            deleted = self.disk_manager.cleanup_old_files()
            logger.info(f"Cleanup freed space by deleting {deleted} files")
    
    def _upload_file(self, filepath: str):
        """
        Upload single file to S3
        
        Args:
            filepath: Path to file to upload
        """
        file_path = Path(filepath)
        
        if not file_path.exists():
            logger.warning(f"File disappeared: {file_path.name}")
            return
        
        # Get file size for stats
        file_size = file_path.stat().st_size
        
        # Upload
        success = self.upload_manager.upload_file(filepath)
        
        if success:
            self.stats['files_uploaded'] += 1
            self.stats['bytes_uploaded'] += file_size
            
            # Mark as uploaded in disk manager
            self.disk_manager.mark_uploaded(filepath)
            
            logger.info(f"Upload successful: {file_path.name} ({file_size / (1024**2):.2f} MB)")
        else:
            self.stats['files_failed'] += 1
            logger.error(f"Upload failed: {file_path.name}")
    
    def _print_statistics(self):
        """Print system statistics"""
        logger.info("\n" + "="*50)
        logger.info("System Statistics")
        logger.info("="*50)
        logger.info(f"Files detected:     {self.stats['files_detected']}")
        logger.info(f"Files uploaded:     {self.stats['files_uploaded']}")
        logger.info(f"Files failed:       {self.stats['files_failed']}")
        logger.info(f"Data uploaded:      {self.stats['bytes_uploaded'] / (1024**3):.2f} GB")
        logger.info("="*50 + "\n")


def signal_handler(signum, frame):
    """Handle shutdown signals"""
    logger.info(f"Received signal {signum}")
    if 'system' in globals():
        system.stop()
    sys.exit(0)


def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description='TVM Log Upload System')
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