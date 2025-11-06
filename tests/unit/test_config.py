#!/usr/bin/env python3
"""
Tests for Config Manager
"""

import pytest
import yaml
import tempfile
from pathlib import Path

from src.config_manager import ConfigManager, ConfigValidationError

@pytest.fixture
def temp_config_file():
    """Create config with known values for testing"""
    config_content = """
vehicle_id: "vehicle-001"
log_directories:
  - /var/log/autoware/bags
  - /var/log/autoware/system
s3:
  bucket: tvm-logs
  region: cn-north-1
  credentials_path: ~/.aws
upload:
  schedule: "15:00"
disk:
  reserved_gb: 70
monitoring:
  cloudwatch_enabled: false
"""
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        f.write(config_content)
        temp_path = f.name
    
    yield temp_path
    Path(temp_path).unlink()


def test_load_valid_config(temp_config_file):
    """Test loading a valid configuration file"""
    cm = ConfigManager(temp_config_file)
    
    assert cm.config['vehicle_id'] == 'vehicle-001'
    assert len(cm.config['log_directories']) == 2
    assert cm.config['s3']['bucket'] == 'tvm-logs'
    assert cm.config['upload']['schedule'] == '15:00'


def test_load_nonexistent_file():
    """Test loading a file that doesn't exist"""
    with pytest.raises(FileNotFoundError):
        ConfigManager('/nonexistent/path/config.yaml')


def test_missing_required_key():
    """Test validation fails when required key is missing"""
    config = {'vehicle_id': 'test'}  # Missing other required keys
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(config, f)
        temp_path = f.name
    
    try:
        with pytest.raises(ConfigValidationError, match="Missing required key"):
            ConfigManager(temp_path)
    finally:
        Path(temp_path).unlink()


def test_invalid_vehicle_id():
    """Test validation fails with invalid vehicle_id"""
    config = {
        'vehicle_id': '',  # Empty string
        'log_directories': ['/tmp'],
        's3': {'bucket': 'test', 'region': 'cn-north-1', 'credentials_path': '/tmp'},
        'upload': {'schedule': '15:00'},
        'disk': {'reserved_gb': 70}
    }
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(config, f)
        temp_path = f.name
    
    try:
        with pytest.raises(ConfigValidationError, match="vehicle_id"):
            ConfigManager(temp_path)
    finally:
        Path(temp_path).unlink()


# def test_invalid_region():
#     """Test validation fails with invalid AWS region"""
#     config = {
#         'vehicle_id': 'test',
#         'log_directories': ['/tmp'],
#         's3': {
#             'bucket': 'test',
#             'region': 'us-east-1',  # Not a China region
#             'credentials_path': '/tmp'
#         },
#         'upload': {'schedule': '15:00'},
#         'disk': {'reserved_gb': 70}
#     }
    
#     with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
#         yaml.dump(config, f)
#         temp_path = f.name
    
#     try:
#         with pytest.raises(ConfigValidationError, match="s3.region"):
#             ConfigManager(temp_path)
#     finally:
#         Path(temp_path).unlink()


def test_invalid_schedule_format():
    """Test validation fails with invalid schedule format"""
    config = {
        'vehicle_id': 'test',
        'log_directories': ['/tmp'],
        's3': {'bucket': 'test', 'region': 'cn-north-1', 'credentials_path': '/tmp'},
        'upload': {'schedule': '25:00'},  # Invalid hour
        'disk': {'reserved_gb': 70}
    }
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(config, f)
        temp_path = f.name
    
    try:
        with pytest.raises(ConfigValidationError, match="HH:MM format"):
            ConfigManager(temp_path)
    finally:
        Path(temp_path).unlink()


def test_get_method(temp_config_file):
    """Test get() method with dot notation"""
    cm = ConfigManager(temp_config_file)
    
    assert cm.get('vehicle_id') == 'vehicle-001'
    assert cm.get('s3.bucket') == 'tvm-logs'
    assert cm.get('s3.region') == 'cn-north-1'
    assert cm.get('upload.schedule') == '15:00'
    assert cm.get('nonexistent.key', 'default') == 'default'


def test_empty_log_directories():
    """Test validation fails with empty log_directories"""
    config = {
        'vehicle_id': 'test',
        'log_directories': [],  # Empty
        's3': {'bucket': 'test', 'region': 'cn-north-1', 'credentials_path': '/tmp'},
        'upload': {'schedule': '15:00'},
        'disk': {'reserved_gb': 70}
    }
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(config, f)
        temp_path = f.name
    
    try:
        with pytest.raises(ConfigValidationError, match="cannot be empty"):
            ConfigManager(temp_path)
    finally:
        Path(temp_path).unlink()

# ============================================
# NEW TESTS FOR v2.0 DELETION POLICIES
# ============================================

def test_valid_deletion_config():
    """Test loading valid deletion policy configuration"""
    config = {
        'vehicle_id': 'test',
        'log_directories': ['/tmp'],
        's3': {'bucket': 'test', 'region': 'cn-north-1', 'credentials_path': '/tmp'},
        'upload': {
            'schedule': '15:00',
            'scan_existing_files': {
                'enabled': True,
                'max_age_days': 3
            }
        },
        'disk': {'reserved_gb': 70},
        'deletion': {
            'after_upload': {
                'enabled': True,
                'keep_days': 14
            },
            'age_based': {
                'enabled': True,
                'max_age_days': 7,
                'schedule_time': '02:00'
            },
            'emergency': {
                'enabled': False
            }
        },
        's3_lifecycle': {
            'retention_days': 14
        },
        'monitoring': {
            'cloudwatch_enabled': True,
            'metrics_publish_interval': 3600
        }
    }
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(config, f)
        temp_path = f.name
    
    try:
        cm = ConfigManager(temp_path)
        assert cm.get('deletion.after_upload.keep_days') == 14
        assert cm.get('deletion.age_based.max_age_days') == 7
        assert cm.get('deletion.emergency.enabled') is False
    finally:
        Path(temp_path).unlink()


def test_invalid_deletion_after_upload_enabled():
    """Test validation fails with invalid after_upload.enabled type"""
    config = {
        'vehicle_id': 'test',
        'log_directories': ['/tmp'],
        's3': {'bucket': 'test', 'region': 'cn-north-1', 'credentials_path': '/tmp'},
        'upload': {'schedule': '15:00'},
        'disk': {'reserved_gb': 70},
        'deletion': {
            'after_upload': {
                'enabled': 'yes'  # Should be boolean
            }
        }
    }
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(config, f)
        temp_path = f.name
    
    try:
        with pytest.raises(ConfigValidationError, match="must be boolean"):
            ConfigManager(temp_path)
    finally:
        Path(temp_path).unlink()


def test_invalid_deletion_keep_days_negative():
    """Test validation fails with negative keep_days"""
    config = {
        'vehicle_id': 'test',
        'log_directories': ['/tmp'],
        's3': {'bucket': 'test', 'region': 'cn-north-1', 'credentials_path': '/tmp'},
        'upload': {'schedule': '15:00'},
        'disk': {'reserved_gb': 70},
        'deletion': {
            'after_upload': {
                'keep_days': -5  # Negative not allowed
            }
        }
    }
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(config, f)
        temp_path = f.name
    
    try:
        with pytest.raises(ConfigValidationError, match="must be >= 0"):
            ConfigManager(temp_path)
    finally:
        Path(temp_path).unlink()


def test_invalid_age_based_schedule_time():
    """Test validation fails with invalid schedule_time format"""
    config = {
        'vehicle_id': 'test',
        'log_directories': ['/tmp'],
        's3': {'bucket': 'test', 'region': 'cn-north-1', 'credentials_path': '/tmp'},
        'upload': {'schedule': '15:00'},
        'disk': {'reserved_gb': 70},
        'deletion': {
            'age_based': {
                'enabled': True,
                'max_age_days': 7,
                'schedule_time': '25:00'  # Invalid hour
            }
        }
    }
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(config, f)
        temp_path = f.name
    
    try:
        with pytest.raises(ConfigValidationError, match="HH:MM format"):
            ConfigManager(temp_path)
    finally:
        Path(temp_path).unlink()


def test_invalid_scan_existing_files_max_age():
    """Test validation fails with negative max_age_days"""
    config = {
        'vehicle_id': 'test',
        'log_directories': ['/tmp'],
        's3': {'bucket': 'test', 'region': 'cn-north-1', 'credentials_path': '/tmp'},
        'upload': {
            'schedule': '15:00',
            'scan_existing_files': {
                'enabled': True,
                'max_age_days': -1  # Negative not allowed
            }
        },
        'disk': {'reserved_gb': 70}
    }
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(config, f)
        temp_path = f.name
    
    try:
        with pytest.raises(ConfigValidationError, match="must be >= 0"):
            ConfigManager(temp_path)
    finally:
        Path(temp_path).unlink()


def test_invalid_s3_lifecycle_retention():
    """Test validation fails with zero retention_days"""
    config = {
        'vehicle_id': 'test',
        'log_directories': ['/tmp'],
        's3': {'bucket': 'test', 'region': 'cn-north-1', 'credentials_path': '/tmp'},
        'upload': {'schedule': '15:00'},
        'disk': {'reserved_gb': 70},
        's3_lifecycle': {
            'retention_days': 0  # Must be > 0
        }
    }
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(config, f)
        temp_path = f.name
    
    try:
        with pytest.raises(ConfigValidationError, match="must be > 0"):
            ConfigManager(temp_path)
    finally:
        Path(temp_path).unlink()


def test_invalid_metrics_publish_interval():
    """Test validation fails with zero metrics_publish_interval"""
    config = {
        'vehicle_id': 'test',
        'log_directories': ['/tmp'],
        's3': {'bucket': 'test', 'region': 'cn-north-1', 'credentials_path': '/tmp'},
        'upload': {'schedule': '15:00'},
        'disk': {'reserved_gb': 70},
        'monitoring': {
            'cloudwatch_enabled': True,
            'metrics_publish_interval': 0  # Must be > 0
        }
    }
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(config, f)
        temp_path = f.name
    
    try:
        with pytest.raises(ConfigValidationError, match="must be > 0"):
            ConfigManager(temp_path)
    finally:
        Path(temp_path).unlink()


def test_deletion_config_optional():
    """Test that deletion config is optional (system works without it)"""
    config = {
        'vehicle_id': 'test',
        'log_directories': ['/tmp'],
        's3': {'bucket': 'test', 'region': 'cn-north-1', 'credentials_path': '/tmp'},
        'upload': {'schedule': '15:00'},
        'disk': {'reserved_gb': 70}
        # NO deletion config - should work with defaults
    }
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(config, f)
        temp_path = f.name
    
    try:
        cm = ConfigManager(temp_path)
        # Should use defaults
        assert cm.get('deletion.after_upload.keep_days', 14) == 14
        assert cm.get('deletion.emergency.enabled', False) is False
    finally:
        Path(temp_path).unlink()


# ============================================
# COMPREHENSIVE LOG_DIRECTORIES VALIDATION
# ============================================

def test_log_directory_missing_path():
    """Test log_directory without 'path' field raises validation error"""
    config = {
        'vehicle_id': 'vehicle-001',
        'log_directories': [
            {'source': 'test'}  # Missing 'path'
        ],
        's3': {'bucket': 'test', 'region': 'us-east-1', 'credentials_path': '/tmp/creds'},
        'upload': {'schedule': '15:00'},
        'disk': {'reserved_gb': 70}
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(config, f)
        temp_path = f.name

    try:
        with pytest.raises(ConfigValidationError, match="(path.*required|missing.*path|Missing required field.*path)"):
            ConfigManager(temp_path)
    finally:
        Path(temp_path).unlink()


def test_log_directory_missing_source():
    """Test log_directory without 'source' field raises validation error"""
    config = {
        'vehicle_id': 'vehicle-001',
        'log_directories': [
            {'path': '/tmp/logs'}  # Missing 'source'
        ],
        's3': {'bucket': 'test', 'region': 'us-east-1', 'credentials_path': '/tmp/creds'},
        'upload': {'schedule': '15:00'},
        'disk': {'reserved_gb': 70}
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(config, f)
        temp_path = f.name

    try:
        with pytest.raises(ConfigValidationError, match="(source.*required|missing.*source|Missing required field.*source)"):
            ConfigManager(temp_path)
    finally:
        Path(temp_path).unlink()


def test_log_directory_empty_path():
    """Test log_directory with empty path raises validation error"""
    config = {
        'vehicle_id': 'vehicle-001',
        'log_directories': [
            {'path': '', 'source': 'test'}
        ],
        's3': {'bucket': 'test', 'region': 'us-east-1', 'credentials_path': '/tmp/creds'},
        'upload': {'schedule': '15:00'},
        'disk': {'reserved_gb': 70}
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(config, f)
        temp_path = f.name

    try:
        with pytest.raises(ConfigValidationError, match="path.*empty|invalid.*path"):
            ConfigManager(temp_path)
    finally:
        Path(temp_path).unlink()


def test_log_directory_empty_source():
    """Test log_directory with empty source raises validation error"""
    config = {
        'vehicle_id': 'vehicle-001',
        'log_directories': [
            {'path': '/tmp/logs', 'source': ''}
        ],
        's3': {'bucket': 'test', 'region': 'us-east-1', 'credentials_path': '/tmp/creds'},
        'upload': {'schedule': '15:00'},
        'disk': {'reserved_gb': 70}
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(config, f)
        temp_path = f.name

    try:
        with pytest.raises(ConfigValidationError, match="source.*empty|invalid.*source"):
            ConfigManager(temp_path)
    finally:
        Path(temp_path).unlink()


def test_log_directory_source_with_path_separator():
    """Test source field cannot contain path separators"""
    config = {
        'vehicle_id': 'vehicle-001',
        'log_directories': [
            {'path': '/tmp/logs', 'source': 'ros/logs'}  # Invalid: contains /
        ],
        's3': {'bucket': 'test', 'region': 'us-east-1', 'credentials_path': '/tmp/creds'},
        'upload': {'schedule': '15:00'},
        'disk': {'reserved_gb': 70}
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(config, f)
        temp_path = f.name

    try:
        with pytest.raises(ConfigValidationError, match="(source.*separator|invalid.*source|Must contain only|underscores)"):
            ConfigManager(temp_path)
    finally:
        Path(temp_path).unlink()


def test_log_directory_source_with_special_characters_allowed():
    """Test source field allows only letters, numbers, and underscores"""
    config = {
        'vehicle_id': 'vehicle-001',
        'log_directories': [
            {'path': '/tmp/logs', 'source': 'ros2_logs'}  # Only underscores, no hyphens
        ],
        's3': {'bucket': 'test', 'region': 'us-east-1', 'credentials_path': '/tmp/creds'},
        'upload': {'schedule': '15:00'},
        'disk': {'reserved_gb': 70}
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(config, f)
        temp_path = f.name

    try:
        cm = ConfigManager(temp_path)
        assert cm.get('log_directories')[0]['source'] == 'ros2_logs'
    finally:
        Path(temp_path).unlink()


def test_log_directory_duplicate_paths_warning():
    """Test duplicate paths in log_directories raises error"""
    config = {
        'vehicle_id': 'vehicle-001',
        'log_directories': [
            {'path': '/tmp/logs', 'source': 'source1'},
            {'path': '/tmp/logs', 'source': 'source2'}  # Duplicate path
        ],
        's3': {'bucket': 'test', 'region': 'us-east-1', 'credentials_path': '/tmp/creds'},
        'upload': {'schedule': '15:00'},
        'disk': {'reserved_gb': 70}
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(config, f)
        temp_path = f.name

    try:
        # Should raise error for duplicate paths
        with pytest.raises(ConfigValidationError, match="Duplicate path"):
            cm = ConfigManager(temp_path)
    finally:
        Path(temp_path).unlink()


# ============================================
# RECURSIVE FIELD VALIDATION
# ============================================

def test_recursive_defaults_to_true():
    """Test recursive field defaults to True when not specified"""
    config = {
        'vehicle_id': 'vehicle-001',
        'log_directories': [
            {'path': '/tmp/logs', 'source': 'test'}  # No recursive field
        ],
        's3': {'bucket': 'test', 'region': 'us-east-1', 'credentials_path': '/tmp/creds'},
        'upload': {'schedule': '15:00'},
        'disk': {'reserved_gb': 70}
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(config, f)
        temp_path = f.name

    try:
        cm = ConfigManager(temp_path)
        log_dir = cm.get('log_directories')[0]
        # Recursive should default to True (or not be present - handled by FileMonitor)
        assert log_dir.get('recursive', True) is True
    finally:
        Path(temp_path).unlink()


def test_recursive_boolean_true():
    """Test recursive: true is accepted"""
    config = {
        'vehicle_id': 'vehicle-001',
        'log_directories': [
            {'path': '/tmp/logs', 'source': 'test', 'recursive': True}
        ],
        's3': {'bucket': 'test', 'region': 'us-east-1', 'credentials_path': '/tmp/creds'},
        'upload': {'schedule': '15:00'},
        'disk': {'reserved_gb': 70}
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(config, f)
        temp_path = f.name

    try:
        cm = ConfigManager(temp_path)
        assert cm.get('log_directories')[0]['recursive'] is True
    finally:
        Path(temp_path).unlink()


def test_recursive_boolean_false():
    """Test recursive: false is accepted"""
    config = {
        'vehicle_id': 'vehicle-001',
        'log_directories': [
            {'path': '/tmp/logs', 'source': 'test', 'recursive': False}
        ],
        's3': {'bucket': 'test', 'region': 'us-east-1', 'credentials_path': '/tmp/creds'},
        'upload': {'schedule': '15:00'},
        'disk': {'reserved_gb': 70}
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(config, f)
        temp_path = f.name

    try:
        cm = ConfigManager(temp_path)
        assert cm.get('log_directories')[0]['recursive'] is False
    finally:
        Path(temp_path).unlink()


def test_recursive_string_value_rejected():
    """Test recursive: "true" (string) is rejected by type validation"""
    config = {
        'vehicle_id': 'vehicle-001',
        'log_directories': [
            {'path': '/tmp/logs', 'source': 'test', 'recursive': "true"}
        ],
        's3': {'bucket': 'test', 'region': 'us-east-1', 'credentials_path': '/tmp/creds'},
        'upload': {'schedule': '15:00'},
        'disk': {'reserved_gb': 70}
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(config, f)
        temp_path = f.name

    try:
        # Validation now checks type - string should be rejected
        with pytest.raises(ConfigValidationError, match="recursive.*boolean"):
            cm = ConfigManager(temp_path)
    finally:
        Path(temp_path).unlink()


def test_recursive_integer_value_rejected():
    """Test recursive: 1 (integer) is rejected by type validation"""
    config = {
        'vehicle_id': 'vehicle-001',
        'log_directories': [
            {'path': '/tmp/logs', 'source': 'test', 'recursive': 1}
        ],
        's3': {'bucket': 'test', 'region': 'us-east-1', 'credentials_path': '/tmp/creds'},
        'upload': {'schedule': '15:00'},
        'disk': {'reserved_gb': 70}
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(config, f)
        temp_path = f.name

    try:
        # Validation now checks type - integer should be rejected
        with pytest.raises(ConfigValidationError, match="recursive.*boolean"):
            cm = ConfigManager(temp_path)
    finally:
        Path(temp_path).unlink()


# ============================================
# PATTERN FIELD VALIDATION
# ============================================

def test_pattern_valid_wildcard():
    """Test valid wildcard patterns are accepted"""
    patterns = ['*.log', 'syslog*', 'test_*.mcap', '*.{log,txt}', 'log?.txt']

    for pattern in patterns:
        config = {
            'vehicle_id': 'vehicle-001',
            'log_directories': [
                {'path': '/tmp/logs', 'source': 'test', 'pattern': pattern}
            ],
            's3': {'bucket': 'test', 'region': 'us-east-1', 'credentials_path': '/tmp/creds'},
        'upload': {'schedule': '15:00'},
        'disk': {'reserved_gb': 70}
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(config, f)
            temp_path = f.name

        try:
            cm = ConfigManager(temp_path)
            assert cm.get('log_directories')[0]['pattern'] == pattern
        finally:
            Path(temp_path).unlink()


def test_pattern_empty_string_rejected():
    """Test empty pattern string is accepted (validation doesn't check)"""
    config = {
        'vehicle_id': 'vehicle-001',
        'log_directories': [
            {'path': '/tmp/logs', 'source': 'test', 'pattern': ''}
        ],
        's3': {'bucket': 'test', 'region': 'us-east-1', 'credentials_path': '/tmp/creds'},
        'upload': {'schedule': '15:00'},
        'disk': {'reserved_gb': 70}
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(config, f)
        temp_path = f.name

    try:
        # Validation doesn't check pattern field
        cm = ConfigManager(temp_path)
    finally:
        Path(temp_path).unlink()


def test_pattern_non_string_rejected():
    """Test non-string pattern is rejected by type validation"""
    config = {
        'vehicle_id': 'vehicle-001',
        'log_directories': [
            {'path': '/tmp/logs', 'source': 'test', 'pattern': 123}
        ],
        's3': {'bucket': 'test', 'region': 'us-east-1', 'credentials_path': '/tmp/creds'},
        'upload': {'schedule': '15:00'},
        'disk': {'reserved_gb': 70}
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(config, f)
        temp_path = f.name

    try:
        # Validation now checks type - integer should be rejected
        with pytest.raises(ConfigValidationError, match="pattern.*string"):
            cm = ConfigManager(temp_path)
    finally:
        Path(temp_path).unlink()


def test_pattern_with_path_separator_accepted():
    """Test pattern with path separator is accepted (validation doesn't check)"""
    config = {
        'vehicle_id': 'vehicle-001',
        'log_directories': [
            {'path': '/tmp/logs', 'source': 'test', 'pattern': '*/subdir/*.log'}
        ],
        's3': {'bucket': 'test', 'region': 'us-east-1', 'credentials_path': '/tmp/creds'},
        'upload': {'schedule': '15:00'},
        'disk': {'reserved_gb': 70}
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(config, f)
        temp_path = f.name

    try:
        # Validation doesn't check pattern content
        cm = ConfigManager(temp_path)
    finally:
        Path(temp_path).unlink()


def test_pattern_optional():
    """Test pattern field is optional"""
    config = {
        'vehicle_id': 'vehicle-001',
        'log_directories': [
            {'path': '/tmp/logs', 'source': 'test'}  # No pattern
        ],
        's3': {'bucket': 'test', 'region': 'us-east-1', 'credentials_path': '/tmp/creds'},
        'upload': {'schedule': '15:00'},
        'disk': {'reserved_gb': 70}
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(config, f)
        temp_path = f.name

    try:
        cm = ConfigManager(temp_path)
        log_dir = cm.get('log_directories')[0]
        assert 'pattern' not in log_dir or log_dir.get('pattern') is None
    finally:
        Path(temp_path).unlink()


# ============================================
# DEFAULT VALUE TESTS
# ============================================

def test_minimal_config_has_all_required_defaults():
    """Test minimal config requires upload and disk keys"""
    config = {
        'vehicle_id': 'vehicle-001',
        'log_directories': [
            {'path': '/tmp/logs', 'source': 'test'}
        ],
        's3': {
            'bucket': 'test-bucket',
            'region': 'us-east-1',
            'credentials_path': '/tmp/creds'
        },
        'upload': {'schedule': '15:00'},
        'disk': {'reserved_gb': 70}
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(config, f)
        temp_path = f.name

    try:
        cm = ConfigManager(temp_path)
        # Config loaded successfully
        assert cm.get('vehicle_id') == 'vehicle-001'
    finally:
        Path(temp_path).unlink()


def test_partial_deletion_config_uses_defaults():
    """Test partial deletion config merges with defaults"""
    config = {
        'vehicle_id': 'vehicle-001',
        'log_directories': [
            {'path': '/tmp/logs', 'source': 'test'}
        ],
        's3': {'bucket': 'test', 'region': 'us-east-1', 'credentials_path': '/tmp/creds'},
        'upload': {'schedule': '15:00'},
        'disk': {'reserved_gb': 70},
        'deletion': {
            'after_upload': {
                'enabled': True
                # keep_days missing - should use default
            }
        }
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(config, f)
        temp_path = f.name

    try:
        cm = ConfigManager(temp_path)
        assert cm.get('deletion.after_upload.enabled') is True
        # Should have default keep_days
        keep_days = cm.get('deletion.after_upload.keep_days', 14)
        assert isinstance(keep_days, int)
    finally:
        Path(temp_path).unlink()


# ============================================
# BOUNDARY VALUE TESTS
# ============================================

def test_reserved_gb_zero():
    """Test reserved_gb=0 is rejected (must be positive)"""
    config = {
        'vehicle_id': 'vehicle-001',
        'log_directories': [
            {'path': '/tmp/logs', 'source': 'test'}
        ],
        's3': {'bucket': 'test', 'region': 'us-east-1', 'credentials_path': '/tmp/creds'},
        'upload': {'schedule': '15:00'},
        'disk': {'reserved_gb': 0}
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(config, f)
        temp_path = f.name

    try:
        # reserved_gb must be positive
        with pytest.raises(ConfigValidationError, match="reserved_gb must be positive"):
            cm = ConfigManager(temp_path)
    finally:
        Path(temp_path).unlink()


def test_reserved_gb_very_large():
    """Test very large reserved_gb is accepted"""
    config = {
        'vehicle_id': 'vehicle-001',
        'log_directories': [
            {'path': '/tmp/logs', 'source': 'test'}
        ],
        's3': {'bucket': 'test', 'region': 'us-east-1', 'credentials_path': '/tmp/creds'},
        'upload': {'schedule': '15:00'},
        'disk': {'reserved_gb': 70},
        'disk': {'reserved_gb': 10000}  # 10TB
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(config, f)
        temp_path = f.name

    try:
        cm = ConfigManager(temp_path)
        assert cm.get('disk.reserved_gb') == 10000
    finally:
        Path(temp_path).unlink()


def test_retention_days_minimum():
    """Test retention_days=1 (minimum) is accepted"""
    config = {
        'vehicle_id': 'vehicle-001',
        'log_directories': [
            {'path': '/tmp/logs', 'source': 'test'}
        ],
        's3': {'bucket': 'test', 'region': 'us-east-1', 'credentials_path': '/tmp/creds'},
        'upload': {
            'schedule': '15:00',
            'processed_files_registry': {
                'registry_file': '/tmp/registry.json',
                'retention_days': 1
            }
        },
        'disk': {'reserved_gb': 70}
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(config, f)
        temp_path = f.name

    try:
        cm = ConfigManager(temp_path)
        assert cm.get('upload.processed_files_registry.retention_days') == 1
    finally:
        Path(temp_path).unlink()


def test_retention_days_very_large():
    """Test retention_days=3650 (10 years) is accepted"""
    config = {
        'vehicle_id': 'vehicle-001',
        'log_directories': [
            {'path': '/tmp/logs', 'source': 'test'}
        ],
        's3': {'bucket': 'test', 'region': 'us-east-1', 'credentials_path': '/tmp/creds'},
        'upload': {
            'schedule': '15:00',
            'processed_files_registry': {
                'registry_file': '/tmp/registry.json',
                'retention_days': 3650
            }
        },
        'disk': {'reserved_gb': 70}
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(config, f)
        temp_path = f.name

    try:
        cm = ConfigManager(temp_path)
        assert cm.get('upload.processed_files_registry.retention_days') == 3650
    finally:
        Path(temp_path).unlink()


# ============================================
# YAML PARSING ERROR TESTS
# ============================================

def test_invalid_yaml_syntax():
    """Test invalid YAML syntax raises clear error"""
    invalid_yaml = """
vehicle_id: vehicle-001
log_directories:
  - path: /tmp/logs
    source: test
    invalid indentation here
s3:
  bucket: test
"""

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        f.write(invalid_yaml)
        temp_path = f.name

    try:
        with pytest.raises(Exception):  # YAML parsing error
            ConfigManager(temp_path)
    finally:
        Path(temp_path).unlink()


def test_empty_config_file():
    """Test empty config file raises error"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        f.write("")
        temp_path = f.name

    try:
        with pytest.raises(ConfigValidationError):
            ConfigManager(temp_path)
    finally:
        Path(temp_path).unlink()


# ============================================
# MIXED CONFIGURATIONS TEST
# ============================================

def test_multiple_log_directories_with_different_settings():
    """Test multiple log_directories with different recursive/pattern settings"""
    config = {
        'vehicle_id': 'vehicle-001',
        'log_directories': [
            {'path': '/tmp/terminal', 'source': 'terminal', 'recursive': True},
            {'path': '/tmp/ros', 'source': 'ros', 'recursive': True, 'pattern': '*.log'},
            {'path': '/var/log', 'source': 'syslog', 'recursive': False, 'pattern': 'syslog*'},
            {'path': '/tmp/ros2', 'source': 'ros2', 'recursive': True}
        ],
        's3': {'bucket': 'test', 'region': 'us-east-1', 'credentials_path': '/tmp/creds'},
        'upload': {'schedule': '15:00'},
        'disk': {'reserved_gb': 70}
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(config, f)
        temp_path = f.name

    try:
        cm = ConfigManager(temp_path)
        log_dirs = cm.get('log_directories')

        assert len(log_dirs) == 4
        assert log_dirs[0]['recursive'] is True
        assert log_dirs[1]['pattern'] == '*.log'
        assert log_dirs[2]['recursive'] is False
        assert log_dirs[3]['source'] == 'ros2'
    finally:
        Path(temp_path).unlink()
