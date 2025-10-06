#!/usr/bin/env python3
"""
Tests for Config Manager
"""

import pytest
import yaml
import tempfile
from pathlib import Path
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from config_manager import ConfigManager, ConfigValidationError

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
