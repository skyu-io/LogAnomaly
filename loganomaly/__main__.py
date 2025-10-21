#!/usr/bin/env python3
"""
Command-line interface for loganomaly module.
Supports: python -m loganomaly --input <input_folder> --output <output_folder> --config <config_file>
"""

import argparse
import os
import sys
from pathlib import Path

def main():
    """Main entry point for loganomaly CLI"""
    parser = argparse.ArgumentParser(description="LogAnomaly - Advanced Log Analysis with AI")
    parser.add_argument("--input", "-i", required=True, help="Input folder containing log files")
    parser.add_argument("--output", "-o", required=True, help="Output folder for results")
    parser.add_argument("--config", "-c", help="Configuration file (optional)")
    
    args = parser.parse_args()
    
    # Validate input folder
    if not os.path.exists(args.input):
        print(f"Error: Input folder not found: {args.input}")
        sys.exit(1)
    
    # Create output folder if it doesn't exist
    os.makedirs(args.output, exist_ok=True)
    
    # Check for log files
    supported_extensions = (".json", ".log", ".txt")
    log_files = [f for f in os.listdir(args.input) if f.endswith(supported_extensions)]
    
    if not log_files:
        print(f"Warning: No supported log files (.json, .log, .txt) found in {args.input}")
        return
    
    print(f"Found {len(log_files)} log files to process: {log_files}")
    
    # Temporarily modify the config
    from loganomaly import config as app_config
    original_input_folder = app_config.INPUT_FOLDER
    original_results_folder = app_config.RESULTS_FOLDER
    
    try:
        # Update config to use provided folders
        app_config.INPUT_FOLDER = args.input
        app_config.RESULTS_FOLDER = args.output
        
        # Import and run the processor
        from loganomaly.processor import process_all_files
        print("Starting log anomaly analysis...")
        process_all_files()
        print(f"Completed. Results saved in → {args.output}")
        
    finally:
        # Restore original config values
        app_config.INPUT_FOLDER = original_input_folder
        app_config.RESULTS_FOLDER = original_results_folder

if __name__ == "__main__":
    main()
