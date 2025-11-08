#!/usr/bin/env python3
"""
Setup configuration for TVM Upload System.

This file provides backward compatibility for older pip/setuptools versions.
All configuration is defined in pyproject.toml (PEP 518/621), but this file
duplicates the essential settings for systems with setuptools < 64.0.

For modern installations (setuptools >= 64.0), pyproject.toml is used directly.
"""
from pathlib import Path

from setuptools import find_packages, setup

# Read README for long description
readme_file = Path(__file__).parent / "README.md"
long_description = readme_file.read_text(encoding="utf-8") if readme_file.exists() else ""

setup(
    name="tvm-upload",
    version="2.1.0",
    description="TVM Log Upload System for Autoware Vehicles",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Avinash Singh",
    author_email="avinash.singh@futu-re.co.jp",
    url="https://github.com/Futu-reADS/tvm-upload",
    # Package discovery
    packages=find_packages(where=".", exclude=["tests", "tests.*"]),
    package_dir={"": "."},
    # Python version requirement
    python_requires=">=3.10",
    # Runtime dependencies (must match pyproject.toml)
    install_requires=[
        "watchdog>=3.0.0",
        "boto3>=1.28.0",
        "pyyaml>=6.0",
    ],
    # Optional dependencies (must match pyproject.toml)
    extras_require={
        "test": [
            "pytest>=7.4.0",
            "pytest-cov>=4.1.0",
            "pytest-mock>=3.11.0",
        ],
        "dev": [
            "black>=23.0.0",
            "flake8>=6.0.0",
            "pylint>=2.17.0",
            "isort>=5.12.0",
            "pre-commit>=3.3.0",
        ],
    },
    # Entry points
    entry_points={
        "console_scripts": [
            "tvm-upload=src.main:main",
        ],
    },
    # Classifiers
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Developers",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Operating System :: POSIX :: Linux",
        "Topic :: System :: Monitoring",
        "Topic :: System :: Logging",
    ],
    # Include non-Python files
    include_package_data=True,
)
