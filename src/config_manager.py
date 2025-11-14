#!/usr/bin/env python3
"""
Configuration Manager for TVM Log Upload System
Loads, validates, and manages YAML configuration

This module provides configuration management with hot-reload capability
and comprehensive validation for the TVM log upload system.

Version: 2.0 - Added deletion policy configuration support
"""

import logging
import os
import re
import signal
from pathlib import Path
from typing import Any, Dict, List

import yaml

logger = logging.getLogger(__name__)


class ConfigValidationError(Exception):
    """
    Raised when configuration validation fails.

    This exception is raised when the configuration file is malformed,
    missing required fields, or contains invalid values.
    """

    pass


class ConfigManager:
    """
    Manages system configuration from YAML file.

    Features:
    - Load and validate YAML config
    - Hot-reload on SIGHUP signal
    - Schema validation
    - Dot-notation access to nested values
    - Support for deletion policies (v2.0)

    Example:
        >>> config = ConfigManager('/etc/tvm-upload/config.yaml')
        >>> bucket = config.get('s3.bucket')
        >>> config.reload_config()  # Manual reload

    Attributes:
        config_path (Path): Path to the configuration file
        config (dict): Loaded configuration dictionary
    """

    def __init__(self, config_path: str):
        """
        Initialize config manager and load configuration.

        Args:
            config_path: Path to YAML config file

        Raises:
            FileNotFoundError: If config file doesn't exist
            yaml.YAMLError: If YAML syntax is invalid
            ConfigValidationError: If validation fails
        """
        self.config_path = Path(config_path)
        self.config = {}
        signal.signal(signal.SIGHUP, self._handle_reload_signal)
        self.load_config()

    def load_config(self) -> Dict[str, Any]:
        """Load and validate configuration from YAML file."""
        if not self.config_path.exists():
            raise FileNotFoundError(f"Config file not found: {self.config_path}")

        with open(self.config_path, "r") as f:
            self.config = yaml.safe_load(f)

        if self.config is None:
            raise ConfigValidationError("Config file is empty or contains only whitespace")

        # Expand environment variables in paths
        self.config = self._expand_env_vars(self.config)

        self.validate_config(self.config)
        logger.info(f"Loaded config from {self.config_path}")
        return self.config

    def reload_config(self) -> Dict[str, Any]:
        """
        Reload configuration from disk (SIGHUP handler).

        NOTE: Config changes require service restart - SIGHUP only validates.
        Hot-reload does NOT update cached values in components.
        """
        logger.info("Reloading configuration...")
        logger.warning(
            "Config reload detected (SIGHUP). "
            "Note: Most config changes require SERVICE RESTART to take effect. "
            "Only validation is performed on reload."
        )

        try:
            old_config = self.config.copy()
            new_config = self.load_config()

            # Check if critical settings changed
            critical_changes = []

            if old_config.get("upload", {}).get("schedule") != new_config.get("upload", {}).get(
                "schedule"
            ):
                critical_changes.append("upload.schedule")

            if old_config.get("upload", {}).get("file_stable_seconds") != new_config.get(
                "upload", {}
            ).get("file_stable_seconds"):
                critical_changes.append("upload.file_stable_seconds")

            if old_config.get("s3") != new_config.get("s3"):
                critical_changes.append("s3.*")

            if old_config.get("disk") != new_config.get("disk"):
                critical_changes.append("disk.*")

            if critical_changes:
                logger.warning(f"CRITICAL CONFIG CHANGES DETECTED: {', '.join(critical_changes)}")
                logger.warning("These changes will NOT take effect until service restart!")
                logger.warning("Action required: sudo systemctl restart tvm-upload")

            logger.info("Config validation successful (changes require restart)")
            return new_config

        except Exception as e:
            logger.error(f"Failed to reload config: {e}")
            logger.info("Keeping existing configuration")
            return self.config

    def _expand_env_vars(self, config: Any) -> Any:
        """
        Recursively expand environment variables in configuration values.

        Supports:
        - ${VAR_NAME} - Environment variable expansion
        - ${HOME} - User's home directory
        - ${USER} - Current username
        - ~ or ~/ - Tilde expansion to home directory

        Args:
            config: Configuration value (dict, list, str, or other)

        Returns:
            Configuration with expanded environment variables

        Examples:
            "/home/USER/.aws" -> "/home/ABC/.aws" (if USER=ABC)
            "${HOME}/.aws" -> "/home/ABC/.aws"
            "~/.aws" -> "/home/ABC/.aws"
        """
        if isinstance(config, dict):
            return {key: self._expand_env_vars(value) for key, value in config.items()}
        elif isinstance(config, list):
            return [self._expand_env_vars(item) for item in config]
        elif isinstance(config, str):
            # First expand tilde (~)
            expanded = os.path.expanduser(config)
            # Then expand environment variables (${VAR} or $VAR)
            expanded = os.path.expandvars(expanded)
            return expanded
        else:
            return config

    def _validate_log_directories(self, log_dirs):
        """Validate log directories (supports legacy string list or new dict format)."""
        if not isinstance(log_dirs, list):
            raise ConfigValidationError("log_directories must be a list")

        if len(log_dirs) == 0:
            raise ConfigValidationError("log_directories cannot be empty")

        seen_sources = set()
        seen_paths = set()

        for idx, item in enumerate(log_dirs):
            if isinstance(item, str):
                logger.warning(
                    f"log_directories[{idx}]: Using legacy string format. "
                    f"Consider migrating to new format with explicit 'source' field."
                )
                path = item
                if path in seen_paths:
                    raise ConfigValidationError(f"Duplicate path in log_directories: {path}")
                seen_paths.add(path)
                continue

            if not isinstance(item, dict):
                raise ConfigValidationError(
                    f"log_directories[{idx}]: Must be string or dict, got {type(item)}"
                )

            if "path" not in item:
                raise ConfigValidationError(
                    f"log_directories[{idx}]: Missing required field 'path'"
                )

            path = item["path"]
            if not isinstance(path, str) or not path:
                raise ConfigValidationError(
                    f"log_directories[{idx}].path: Must be non-empty string"
                )

            if path in seen_paths:
                raise ConfigValidationError(f"log_directories[{idx}]: Duplicate path '{path}'")
            seen_paths.add(path)

            if "source" not in item:
                raise ConfigValidationError(
                    f"log_directories[{idx}]: Missing required field 'source'"
                )

            source = item["source"]
            if not isinstance(source, str) or not source:
                raise ConfigValidationError(
                    f"log_directories[{idx}].source: Must be non-empty string"
                )

            if not re.match(r"^[a-zA-Z0-9_]+$", source):
                raise ConfigValidationError(
                    f"log_directories[{idx}].source: Must contain only letters, "
                    f"numbers, and underscores. Got: '{source}'"
                )

            if source in seen_sources:
                raise ConfigValidationError(
                    f"log_directories[{idx}]: Duplicate source name '{source}'"
                )
            seen_sources.add(source)

            # Validate recursive parameter
            if "recursive" in item:
                if not isinstance(item["recursive"], bool):
                    raise ConfigValidationError(
                        f"log_directories[{idx}].recursive: Must be boolean, got {type(item['recursive'])}"
                    )

            # Validate pattern parameter
            if "pattern" in item:
                if not isinstance(item["pattern"], str):
                    raise ConfigValidationError(
                        f"log_directories[{idx}].pattern: Must be string, got {type(item['pattern'])}"
                    )

            # Validate allow_deletion parameter
            if "allow_deletion" in item:
                if not isinstance(item["allow_deletion"], bool):
                    raise ConfigValidationError(
                        f"log_directories[{idx}].allow_deletion: Must be boolean, got {type(item['allow_deletion'])}"
                    )

        logger.info(f"Validated {len(log_dirs)} log directories")
        if seen_sources:
            logger.info(f"Sources: {', '.join(sorted(seen_sources))}")

    def validate_config(self, config: Dict[str, Any]) -> bool:
        """Validate configuration schema and values."""
        required_keys = ["vehicle_id", "log_directories", "s3", "upload", "disk"]
        for key in required_keys:
            if key not in config:
                raise ConfigValidationError(f"Missing required key: {key}")

        if not isinstance(config["vehicle_id"], str) or not config["vehicle_id"]:
            raise ConfigValidationError("vehicle_id must be a non-empty string")

        self._validate_log_directories(config["log_directories"])
        self._validate_s3_config(config["s3"])
        self._validate_upload_config(config["upload"])
        self._validate_disk_config(config["disk"])

        if "deletion" in config:
            self._validate_deletion_config(config["deletion"])

        if "s3_lifecycle" in config:
            self._validate_s3_lifecycle_config(config["s3_lifecycle"])

        if "monitoring" in config:
            self._validate_monitoring_config(config["monitoring"])

        logger.info("Configuration validated successfully")
        return True

    def _validate_s3_config(self, s3_config: Dict[str, Any]) -> None:
        """Validate S3 configuration section."""
        # credentials_path is optional - AWS SDK will auto-discover credentials
        s3_required = ["bucket", "region"]
        for key in s3_required:
            if key not in s3_config:
                raise ConfigValidationError(f"Missing s3.{key}")

        # Validate region exists (allow any AWS region)
        if not s3_config["region"]:
            raise ConfigValidationError("s3.region cannot be empty")

    def _validate_upload_config(self, upload_config: Dict[str, Any]) -> None:
        """Validate upload configuration section."""
        if "schedule" not in upload_config:
            raise ConfigValidationError("Missing upload.schedule")

        schedule = upload_config["schedule"]

        if isinstance(schedule, str):
            if not self._is_valid_time_format(schedule):
                raise ConfigValidationError(
                    f"upload.schedule must be in HH:MM format, got: {schedule}"
                )

        elif isinstance(schedule, dict):
            if "mode" not in schedule:
                raise ConfigValidationError("Missing upload.schedule.mode")

            mode = schedule["mode"]
            valid_modes = ["daily", "interval"]
            if mode not in valid_modes:
                raise ConfigValidationError(
                    f"upload.schedule.mode must be one of {valid_modes}, got: {mode}"
                )

            if mode == "daily":
                if "daily_time" not in schedule:
                    raise ConfigValidationError(
                        "upload.schedule.daily_time required when mode='daily'"
                    )

                if not self._is_valid_time_format(schedule["daily_time"]):
                    raise ConfigValidationError(
                        f"upload.schedule.daily_time must be HH:MM format, got: {schedule['daily_time']}"
                    )

            if mode == "interval":
                interval_hours = schedule.get("interval_hours", 0)
                interval_minutes = schedule.get("interval_minutes", 0)

                if not isinstance(interval_hours, (int, float)):
                    raise ConfigValidationError("upload.schedule.interval_hours must be a number")

                if not isinstance(interval_minutes, (int, float)):
                    raise ConfigValidationError("upload.schedule.interval_minutes must be a number")

                if interval_hours < 0 or interval_minutes < 0:
                    raise ConfigValidationError("upload.schedule intervals must be >= 0")

                if interval_hours == 0 and interval_minutes == 0:
                    raise ConfigValidationError(
                        "upload.schedule: at least one interval must be > 0"
                    )

                total_minutes = interval_hours * 60 + interval_minutes
                if total_minutes < 5:
                    raise ConfigValidationError("upload.schedule: minimum interval is 5 minutes")

                if total_minutes > 24 * 60:
                    raise ConfigValidationError("upload.schedule: maximum interval is 24 hours")

        else:
            raise ConfigValidationError(
                "upload.schedule must be string (HH:MM) or object with 'mode'"
            )

        if "file_stable_seconds" in upload_config:
            stable_secs = upload_config["file_stable_seconds"]
            if not isinstance(stable_secs, (int, float)) or stable_secs < 0:
                raise ConfigValidationError(
                    "upload.file_stable_seconds must be a non-negative number"
                )

        if "operational_hours" in upload_config:
            op_hours = upload_config["operational_hours"]
            if "enabled" in op_hours and not isinstance(op_hours["enabled"], bool):
                raise ConfigValidationError("upload.operational_hours.enabled must be boolean")

            if op_hours.get("enabled", False):
                if "start" not in op_hours or "end" not in op_hours:
                    raise ConfigValidationError(
                        "upload.operational_hours requires 'start' and 'end' when enabled"
                    )

                if not self._is_valid_time_format(op_hours["start"]):
                    raise ConfigValidationError(
                        f"upload.operational_hours.start must be HH:MM format"
                    )

                if not self._is_valid_time_format(op_hours["end"]):
                    raise ConfigValidationError(
                        f"upload.operational_hours.end must be HH:MM format"
                    )

        if "scan_existing_files" in upload_config:
            scan_config = upload_config["scan_existing_files"]

            if "enabled" in scan_config and not isinstance(scan_config["enabled"], bool):
                raise ConfigValidationError("upload.scan_existing_files.enabled must be boolean")

            if "max_age_days" in scan_config:
                max_age = scan_config["max_age_days"]
                if not isinstance(max_age, (int, float)) or max_age < 0:
                    raise ConfigValidationError(
                        "upload.scan_existing_files.max_age_days must be >= 0"
                    )

        if "processed_files_registry" in upload_config:
            registry = upload_config["processed_files_registry"]

            if "registry_file" in registry:
                if not isinstance(registry["registry_file"], str):
                    raise ConfigValidationError(
                        "upload.processed_files_registry.registry_file must be string"
                    )

            if "retention_days" in registry:
                retention = registry["retention_days"]
                if not isinstance(retention, (int, float)) or retention <= 0:
                    raise ConfigValidationError(
                        "upload.processed_files_registry.retention_days must be > 0"
                    )

        # Validate upload_on_start
        if "upload_on_start" in upload_config:
            if not isinstance(upload_config["upload_on_start"], bool):
                raise ConfigValidationError("upload.upload_on_start must be boolean")

        # Validate queue_file
        if "queue_file" in upload_config:
            if not isinstance(upload_config["queue_file"], str):
                raise ConfigValidationError("upload.queue_file must be string")

        if "batch_upload" in upload_config:
            batch = upload_config["batch_upload"]

            if "enabled" in batch and not isinstance(batch["enabled"], bool):
                raise ConfigValidationError("upload.batch_upload.enabled must be boolean")

            if "include_run_directory" in batch and not isinstance(
                batch["include_run_directory"], bool
            ):
                raise ConfigValidationError(
                    "upload.batch_upload.include_run_directory must be boolean"
                )

        # Validate directory_configs (NEW v2.1)
        if "directory_configs" in upload_config:
            dir_configs = upload_config["directory_configs"]

            if not isinstance(dir_configs, list):
                raise ConfigValidationError("upload.directory_configs must be a list")

            for i, dir_config in enumerate(dir_configs):
                if not isinstance(dir_config, dict):
                    raise ConfigValidationError(
                        f"upload.directory_configs[{i}] must be a dictionary"
                    )

                # Validate 'path' field (required)
                if "path" not in dir_config:
                    raise ConfigValidationError(
                        f"upload.directory_configs[{i}]: missing required field 'path'"
                    )

                if not isinstance(dir_config["path"], str):
                    raise ConfigValidationError(
                        f"upload.directory_configs[{i}].path must be string"
                    )

                # Validate 'type' field (optional)
                if "type" in dir_config:
                    valid_types = ["ros_log", "system_log", "bag_log", "default"]
                    if dir_config["type"] not in valid_types:
                        raise ConfigValidationError(
                            f"upload.directory_configs[{i}].type must be one of {valid_types}, "
                            f"got: {dir_config['type']}"
                        )

                # Validate boolean fields (optional)
                for flag in ["include_run_directory", "match_by_pid"]:
                    if flag in dir_config and not isinstance(dir_config[flag], bool):
                        raise ConfigValidationError(
                            f"upload.directory_configs[{i}].{flag} must be boolean"
                        )

    def _validate_disk_config(self, disk_config: Dict[str, Any]) -> None:
        """Validate disk configuration section."""
        if "reserved_gb" not in disk_config:
            raise ConfigValidationError("Missing disk.reserved_gb")

        if not isinstance(disk_config["reserved_gb"], (int, float)):
            raise ConfigValidationError("disk.reserved_gb must be a number")

        if disk_config["reserved_gb"] <= 0:
            raise ConfigValidationError("disk.reserved_gb must be positive")

        # Validate thresholds
        if "warning_threshold" in disk_config:
            if not 0 < disk_config["warning_threshold"] < 1:
                raise ConfigValidationError("disk.warning_threshold must be between 0 and 1")

        if "critical_threshold" in disk_config:
            if not 0 < disk_config["critical_threshold"] < 1:
                raise ConfigValidationError("disk.critical_threshold must be between 0 and 1")

        # Validate that critical threshold is >= warning threshold
        if "warning_threshold" in disk_config and "critical_threshold" in disk_config:
            if disk_config["critical_threshold"] <= disk_config["warning_threshold"]:
                raise ConfigValidationError(
                    f"disk.critical_threshold ({disk_config['critical_threshold']}) must be greater than "
                    f"disk.warning_threshold ({disk_config['warning_threshold']})"
                )

    def _validate_deletion_config(self, deletion_config: Dict[str, Any]) -> None:
        """Validate deletion policy configuration (NEW in v2.0)."""
        # Validate after_upload section
        if "after_upload" in deletion_config:
            after_upload = deletion_config["after_upload"]

            if "enabled" in after_upload and not isinstance(after_upload["enabled"], bool):
                raise ConfigValidationError("deletion.after_upload.enabled must be boolean")

            if "keep_days" in after_upload:
                keep_days = after_upload["keep_days"]
                if not isinstance(keep_days, (int, float)) or keep_days < 0:
                    raise ConfigValidationError("deletion.after_upload.keep_days must be >= 0")

        # Validate age_based section
        if "age_based" in deletion_config:
            age_based = deletion_config["age_based"]

            if "enabled" in age_based and not isinstance(age_based["enabled"], bool):
                raise ConfigValidationError("deletion.age_based.enabled must be boolean")

            if "max_age_days" in age_based:
                max_age = age_based["max_age_days"]
                if not isinstance(max_age, (int, float)) or max_age < 0:
                    raise ConfigValidationError("deletion.age_based.max_age_days must be >= 0")

            if "schedule_time" in age_based:
                schedule_time = age_based["schedule_time"]
                if not self._is_valid_time_format(schedule_time):
                    raise ConfigValidationError(
                        f"deletion.age_based.schedule_time must be HH:MM format, got: {schedule_time}"
                    )

        # Validate emergency section
        if "emergency" in deletion_config:
            emergency = deletion_config["emergency"]

            if "enabled" in emergency and not isinstance(emergency["enabled"], bool):
                raise ConfigValidationError("deletion.emergency.enabled must be boolean")

    def _validate_s3_lifecycle_config(self, s3_lifecycle_config: Dict[str, Any]) -> None:
        """Validate S3 lifecycle configuration (NEW in v2.0)."""
        if "retention_days" in s3_lifecycle_config:
            retention = s3_lifecycle_config["retention_days"]
            if not isinstance(retention, (int, float)) or retention <= 0:
                raise ConfigValidationError("s3_lifecycle.retention_days must be > 0")

    def _validate_monitoring_config(self, monitoring_config: Dict[str, Any]) -> None:
        """Validate monitoring configuration (NEW in v2.0)."""
        if "cloudwatch_enabled" in monitoring_config:
            if not isinstance(monitoring_config["cloudwatch_enabled"], bool):
                raise ConfigValidationError("monitoring.cloudwatch_enabled must be boolean")

    def _is_valid_time_format(self, time_str: str) -> bool:
        """
        Check if string is valid HH:MM format.

        Validates that:
        - String contains exactly one colon
        - Hours are in range 0-23
        - Minutes are in range 0-59

        Args:
            time_str: Time string to validate

        Returns:
            bool: True if valid HH:MM format, False otherwise

        Examples:
            >>> _is_valid_time_format("15:30")  # True
            >>> _is_valid_time_format("25:00")  # False (invalid hour)
            >>> _is_valid_time_format("12:70")  # False (invalid minute)
        """
        try:
            parts = time_str.split(":")
            if len(parts) != 2:
                return False

            hours = int(parts[0])
            minutes = int(parts[1])

            return 0 <= hours <= 23 and 0 <= minutes <= 59
        except (ValueError, AttributeError):
            return False

    def _handle_reload_signal(self, signum, frame):
        """
        Signal handler for SIGHUP.

        Triggers configuration reload when SIGHUP signal is received.

        Args:
            signum: Signal number
            frame: Current stack frame
        """
        self.reload_config()

    def get(self, key: str, default=None) -> Any:
        """
        Get configuration value by dot-separated key path.

        Supports nested key access using dot notation.

        Args:
            key: Dot-separated key path (e.g., 's3.bucket')
            default: Default value if key not found

        Returns:
            Configuration value or default if not found

        Examples:
            >>> config.get('vehicle_id')  # 'vehicle-001'
            >>> config.get('s3.bucket')  # 'tvm-logs'
            >>> config.get('missing.key', 'default')  # 'default'
            >>> config.get('deletion.after_upload.keep_days', 0)  # 14
        """
        keys = key.split(".")
        value = self.config

        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default

        return value


if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
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

        # NEW: Display deletion policy settings
        logger.info("\nDeletion Policy Settings:")
        logger.info(f"  Scan existing files: {cm.get('upload.scan_existing_files.enabled', False)}")
        logger.info(
            f"  Max age for scan: {cm.get('upload.scan_existing_files.max_age_days', 0)} days"
        )
        logger.info(f"  Keep after upload: {cm.get('deletion.after_upload.keep_days', 0)} days")
        logger.info(f"  Age-based cleanup: {cm.get('deletion.age_based.enabled', False)}")
        logger.info(f"  Age-based max age: {cm.get('deletion.age_based.max_age_days', 0)} days")
        logger.info(f"  Emergency cleanup: {cm.get('deletion.emergency.enabled', False)}")
        logger.info(f"  S3 retention: {cm.get('s3_lifecycle.retention_days', 14)} days")

    except Exception as e:
        logger.error(f"ERROR: {e}")
        sys.exit(1)
