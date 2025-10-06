#!/usr/bin/env python3
"""Manual test for S3 upload - requires AWS credentials"""


import sys
from pathlib import Path
import tempfile
from pathlib import Path
from src.upload_manager import UploadManager

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

# Create test file
with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.log') as f:
    f.write("Test log data\n" * 100)
    test_file = f.name

print(f"Created test file: {test_file}")

# Initialize uploader (use your actual AWS credentials)
# For testing, use your personal AWS account, not China
uploader = UploadManager(
    bucket="YOUR-TEST-BUCKET",  # Replace with your bucket
    region="us-east-1",          # Replace with your region
    vehicle_id="vehicle-test"
)

# Upload
print("Uploading...")
result = uploader.upload_file(test_file)

if result:
    print("SUCCESS: File uploaded to S3")
    
    # Verify
    if uploader.verify_upload(test_file):
        print("VERIFIED: File exists in S3")
    else:
        print("WARNING: Upload succeeded but verification failed")
else:
    print("FAILED: Upload did not succeed")

# Cleanup
Path(test_file).unlink()
print(f"Deleted test file: {test_file}")
