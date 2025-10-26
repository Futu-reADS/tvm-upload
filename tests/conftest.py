# tests/conftest.py
"""
Common fixtures for all test types
These are shared across unit, integration, and e2e tests
"""

import pytest
import tempfile
import sys
from pathlib import Path

# Add project root to Python path so 'src' module can be imported
# This allows tests to run without installing the package
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))


@pytest.fixture
def temp_dir():
    """Create temporary directory for tests"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def temp_file():
    """Create temporary test file"""
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.log') as f:
        f.write('test data\n' * 100)
        temp_path = f.name
    
    yield temp_path
    
    # Cleanup
    Path(temp_path).unlink(missing_ok=True)


@pytest.fixture
def large_temp_file():
    """Create large temporary file (>5MB) for multipart tests"""
    with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.mcap') as f:
        f.write(b'0' * (6 * 1024 * 1024))  # 6MB
        temp_path = f.name
    
    yield temp_path
    
    Path(temp_path).unlink(missing_ok=True)