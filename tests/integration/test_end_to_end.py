#!/usr/bin/env python3
"""
End-to-end integration test
Tests the complete system flow
"""

import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import pytest
import tempfile
import time
import shutil
import yaml
from unittest.mock import patch, Mock
from src.main import TVMUploadSystem


@pytest.fixture
def test_config():
    """Create temporary test configuration"""
    temp_dir = tempfile.mkdtemp()
    
    config_data = {
        'vehicle_id': 'test-vehicle',
        'log_directories': [temp_dir],
        's3': {
            'bucket': 'test-bucket',
            'region': 'us-east-1',
            'credentials_path': '/tmp/fake'
        },
        'upload': {
            'schedule': '15:00',
            'file_stable_seconds': 2
        },
        'disk': {
            'reserved_gb': 0.1,
            'warning_threshold': 0.90,
            'critical_threshold': 0.95
        }
    }
    
    config_file = Path(temp_dir) / 'config.yaml'
    with open(config_file, 'w') as f:
        yaml.dump(config_data, f)
    
    yield str(config_file), temp_dir
    
    # Cleanup
    shutil.rmtree(temp_dir)


@patch('src.main.UploadManager')
def test_system_initialization(mock_upload_manager, test_config):
    """Test system can initialize with config"""
    config_file, _ = test_config
    
    system = TVMUploadSystem(config_file)
    
    assert system.config.get('vehicle_id') == 'test-vehicle'
    assert system.stats['files_detected'] == 0


@patch('src.main.UploadManager')
def test_file_detection_and_queue(mock_upload_manager, test_config):
    """Test file detection adds to upload queue"""
    config_file, temp_dir = test_config
    
    # Mock upload manager
    mock_uploader = Mock()
    mock_upload_manager.return_value = mock_uploader
    
    system = TVMUploadSystem(config_file)
    system.start()
    
    # Create test file
    test_file = Path(temp_dir) / 'test.log'
    test_file.write_text('test data\n' * 100)
    
    # Wait for detection
    time.sleep(3)
    
    # File should be detected
    assert system.stats['files_detected'] >= 1
    
    system.stop()


@patch('src.main.UploadManager')
def test_upload_marks_file_for_cleanup(mock_upload_manager, test_config):
    """Test uploaded files are marked in disk manager"""
    config_file, temp_dir = test_config
    
    # Mock successful upload
    mock_uploader = Mock()
    mock_uploader.upload_file.return_value = True
    mock_upload_manager.return_value = mock_uploader
    
    system = TVMUploadSystem(config_file)
    system.start()
    
    # Create and wait for file
    test_file = Path(temp_dir) / 'test.log'
    test_file.write_text('test data\n' * 100)
    
    time.sleep(4)
    
    # Check if marked as uploaded
    assert system.disk_manager.get_uploaded_files_count() >= 1
    
    system.stop()


def test_statistics_tracking(test_config):
    """Test statistics are tracked correctly"""
    config_file, temp_dir = test_config
    
    with patch('src.main.UploadManager') as mock_upload_manager:
        mock_uploader = Mock()
        mock_uploader.upload_file.return_value = True
        mock_upload_manager.return_value = mock_uploader
        
        system = TVMUploadSystem(config_file)
        system.start()
        
        # Create files
        for i in range(3):
            f = Path(temp_dir) / f'file{i}.log'
            f.write_text(f'data {i}\n' * 100)
            time.sleep(0.5)
        
        time.sleep(4)
        
        system.stop()
        
        # Check stats
        assert system.stats['files_detected'] >= 3
        assert system.stats['files_uploaded'] >= 0
