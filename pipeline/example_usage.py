#!/usr/bin/env python3
"""
Example of how to use prepare_jobs.py from worker.py
"""

from worker import prepare_and_download_logs, prepare_and_download_logs_subprocess

def example_direct_call():
    """Example using direct function call"""
    print("=== Direct Function Call Example ===")
    
    # Call the task directly
    prepare_and_download_logs(
        start_time="2024-01-01T00:00:00Z",
        end_time="2024-01-01T23:59:59Z",
        region="us-east-1"
    )

def example_subprocess_call():
    """Example using subprocess call"""
    print("=== Subprocess Call Example ===")
    
    # Call the subprocess version
    prepare_and_download_logs_subprocess(
        start_time="2024-01-01T00:00:00Z",
        end_time="2024-01-01T23:59:59Z",
        region="us-east-1"
    )

if __name__ == "__main__":
    # Choose which method to test
    example_direct_call()
    # example_subprocess_call()

