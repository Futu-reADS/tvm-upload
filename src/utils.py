#!/usr/bin/env python3
"""
Utility functions for TVM Upload System
Common helpers for byte conversions and formatting
"""


def bytes_to_mb(bytes_value: int) -> float:
    """Convert bytes to megabytes."""
    return bytes_value / (1024**2)


def bytes_to_gb(bytes_value: int) -> float:
    """Convert bytes to gigabytes."""
    return bytes_value / (1024**3)


def format_bytes(bytes_value: int, precision: int = 2) -> str:
    """Format bytes as human-readable string with auto-scaling (KB/MB/GB/TB)."""
    if bytes_value < 1024**2:
        return f"{bytes_value / 1024:.{precision}f} KB"
    elif bytes_value < 1024**3:
        return f"{bytes_value / 1024**2:.{precision}f} MB"
    elif bytes_value < 1024**4:
        return f"{bytes_value / 1024**3:.{precision}f} GB"
    else:
        return f"{bytes_value / 1024**4:.{precision}f} TB"


if __name__ == "__main__":
    print(f"1 MB = {format_bytes(1024**2)}")
    print(f"100 MB = {format_bytes(100 * 1024**2)}")
    print(f"1.5 GB = {format_bytes(int(1.5 * 1024**3))}")
    print(f"5 TB = {format_bytes(5 * 1024**4)}")
    print(f"\n{bytes_to_mb(1048576):.2f} MB")
    print(f"{bytes_to_gb(1073741824):.2f} GB")
