#!/usr/bin/env python3
"""
Setup script for TVM Upload System
Install with: pip install -e .
"""

from setuptools import setup, find_packages
from pathlib import Path

# Read README for long description
readme_file = Path(__file__).parent / 'README.md'
long_description = readme_file.read_text() if readme_file.exists() else ''

setup(
    name='tvm-upload',
    version='2.1.0',
    description='TVM Log Upload System for Autoware Vehicles',
    long_description=long_description,
    long_description_content_type='text/markdown',
    author='Avinash',
    author_email='avinash.singh@futu-re.co.jp',
    url='https://github.com/Futu-reADS/tvm-upload',
    
    # Package discovery
    packages=find_packages(where='.', exclude=['tests', 'tests.*']),
    package_dir={'': '.'},
    
    # Python version requirement
    python_requires='>=3.10',
    
    # Runtime dependencies (from requirements.txt)
    install_requires=[
        'watchdog>=3.0.0',
        'boto3>=1.28.0',
        'pyyaml>=6.0',
    ],
    
    # Development/testing dependencies
    extras_require={
        'dev': [
            'pytest>=7.4.0',
            'pytest-cov>=4.1.0',
            'pytest-mock>=3.11.0',
        ],
        'test': [
            'pytest>=7.4.0',
            'pytest-cov>=4.1.0',
            'pytest-mock>=3.11.0',
        ],
    },
    
    # Entry points (command-line scripts)
    entry_points={
        'console_scripts': [
            'tvm-upload=src.main:main',
        ],
    },
    
    # Classifiers
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Operating System :: POSIX :: Linux',
    ],
    
    # Include non-Python files
    include_package_data=True,
)