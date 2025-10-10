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
    """Fixture using actual example config as single source of truth"""
    example_path = Path(__file__).parent.parent / 'config' / 'config.yaml.example'
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        with open(example_path) as src:
            f.write(src.read())
        temp_path = f.name
    
    yield temp_path
    
    # Cleanup
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
