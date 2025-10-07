# TVM Log Upload System

## Quick Start

### Development Setup
```bash
git clone git@github.com:Futu-reADS/tvm-upload.git
cd tvm-upload
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt


### All tests
./run_tests.sh

### Specific test file
pytest tests/test_monitor.py -v