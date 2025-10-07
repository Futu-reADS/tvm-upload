#!/usr/bin/env python3
"""
Configuration Manager for TVM Log Upload System
Loads, validates, and manages YAML configuration
"""

import yaml
import os
import signal
import logging
from pathlib import Path
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


class ConfigValidationError(Exception):
    """Raised when configuration validation fails"""
    pass


class ConfigManager:
    """
    Manages system configuration from YAML file
    
    Features:
    - Load and validate YAML config
    - Hot-reload on SIGHUP signal
    - Schema validation
    """
    
    def __init__(self, config_path: str):
        """
        Initialize config manager
        
        Args:
            config_path: Path to YAML config file
        """
        self.config_path = Path(config_path)
        self.config = {}
        
        # Set up signal handler for hot reload
        signal.signal(signal.SIGHUP, self._handle_reload_signal)
        
        # Load initial config
        self.load_config()
    
    def load_config(self) -> Dict[str, Any]:
        """
        Load configuration from YAML file
        
        Returns:
            dict: Loaded configuration
            
        Raises:
            FileNotFoundError: If config file doesn't exist
            yaml.YAMLError: If YAML is invalid
            ConfigValidationError: If validation fails
        """
        if not self.config_path.exists():
            raise FileNotFoundError(f"Config file not found: {self.config_path}")
        
        # Read YAML file
        with open(self.config_path, 'r') as f:
            self.config = yaml.safe_load(f)
        
        # Validate configuration
        self.validate_config(self.config)
        
        logger.info(f"Loaded config from {self.config_path}")
        return self.config
    
    def reload_config(self) -> Dict[str, Any]:
        """
        Reload configuration (called on SIGHUP)
        
        Returns:
            dict: Reloaded configuration
        """
        logger.info("Reloading configuration...")
        try:
            return self.load_config()
        except Exception as e:
            logger.error(f"Failed to reload config: {e}")
            logger.info("Keeping existing configuration")
            return self.config
    
    def validate_config(self, config: Dict[str, Any]) -> bool:
        """
        Validate configuration schema and values
        
        Args:
            config: Configuration dictionary to validate
            
        Returns:
            bool: True if valid
            
        Raises:
            ConfigValidationError: If validation fails
        """
        # Required top-level keys
        required_keys = ['vehicle_id', 'log_directories', 's3', 'upload', 'disk']
        for key in required_keys:
            if key not in config:
                raise ConfigValidationError(f"Missing required key: {key}")
        
        # Validate vehicle_id
        if not isinstance(config['vehicle_id'], str) or not config['vehicle_id']:
            raise ConfigValidationError("vehicle_id must be a non-empty string")
        
        # Validate log_directories
        if not isinstance(config['log_directories'], list):
            raise ConfigValidationError("log_directories must be a list")
        if len(config['log_directories']) == 0:
            raise ConfigValidationError("log_directories cannot be empty")
        
        # Validate S3 config
        s3_required = ['bucket', 'region', 'credentials_path']
        for key in s3_required:
            if key not in config['s3']:
                raise ConfigValidationError(f"Missing s3.{key}")
        
        # Validate region
        # valid_regions = ['cn-north-1', 'cn-northwest-1']
        # if config['s3']['region'] not in valid_regions:
        #     raise ConfigValidationError(
        #         f"s3.region must be one of {valid_regions}"
        #     )


        # Validate region exists (allow any AWS region)
        if not config['s3']['region']:
            raise ConfigValidationError("s3.region cannot be empty")
                
        # Validate upload config
        if 'schedule' not in config['upload']:
            raise ConfigValidationError("Missing upload.schedule")
        
        # Validate schedule format (HH:MM)
        schedule = config['upload']['schedule']
        if not self._is_valid_time_format(schedule):
            raise ConfigValidationError(
                f"upload.schedule must be in HH:MM format, got: {schedule}"
            )
        
        # Validate disk config
        if 'reserved_gb' not in config['disk']:
            raise ConfigValidationError("Missing disk.reserved_gb")
        
        if not isinstance(config['disk']['reserved_gb'], (int, float)):
            raise ConfigValidationError("disk.reserved_gb must be a number")
        
        if config['disk']['reserved_gb'] <= 0:
            raise ConfigValidationError("disk.reserved_gb must be positive")
        
        # Validate thresholds
        if 'warning_threshold' in config['disk']:
            if not 0 < config['disk']['warning_threshold'] < 1:
                raise ConfigValidationError(
                    "disk.warning_threshold must be between 0 and 1"
                )
        
        if 'critical_threshold' in config['disk']:
            if not 0 < config['disk']['critical_threshold'] < 1:
                raise ConfigValidationError(
                    "disk.critical_threshold must be between 0 and 1"
                )
        
        logger.info("Configuration validated successfully")
        return True
    
    def _is_valid_time_format(self, time_str: str) -> bool:
        """
        Check if string is valid HH:MM format
        
        Args:
            time_str: Time string to validate
            
        Returns:
            bool: True if valid HH:MM format
        """
        try:
            parts = time_str.split(':')
            if len(parts) != 2:
                return False
            
            hours = int(parts[0])
            minutes = int(parts[1])
            
            return 0 <= hours <= 23 and 0 <= minutes <= 59
        except (ValueError, AttributeError):
            return False
    
    def _handle_reload_signal(self, signum, frame):
        """Signal handler for SIGHUP"""
        self.reload_config()
    
    def get(self, key: str, default=None) -> Any:
        """
        Get configuration value by key
        
        Args:
            key: Dot-separated key path (e.g., 's3.bucket')
            default: Default value if key not found
            
        Returns:
            Configuration value or default
        """
        keys = key.split('.')
        value = self.config
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        
        return value


if __name__ == '__main__':
    import sys
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    if len(sys.argv) < 2:
        logger.error("Usage: python config_manager.py <config_file>")
        sys.exit(1)
    
    try:
        cm = ConfigManager(sys.argv[1])
        logger.info("Configuration loaded successfully!")
        logger.info(f"Vehicle ID: {cm.get('vehicle_id')}")
        logger.info(f"Log directories: {cm.get('log_directories')}")
        logger.info(f"S3 bucket: {cm.get('s3.bucket')}")
        logger.info(f"S3 region: {cm.get('s3.region')}")
        logger.info(f"Upload schedule: {cm.get('upload.schedule')}")
    except Exception as e:
        logger.error(f"ERROR: {e}")
        sys.exit(1)