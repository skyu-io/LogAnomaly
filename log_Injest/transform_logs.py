#!/usr/bin/env python3
"""
Transform AWS CloudWatch logs to match the specified template format.
"""

import json
import sys
from datetime import datetime
from typing import Dict, Any, List

def timestamp_to_iso(timestamp_ms: int) -> str:
    """Convert timestamp in milliseconds to ISO format."""
    dt = datetime.fromtimestamp(timestamp_ms / 1000)
    return dt.isoformat() + "Z"

def timestamp_to_readable(timestamp_ms: int) -> str:
    """Convert timestamp in milliseconds to readable format."""
    dt = datetime.fromtimestamp(timestamp_ms / 1000)
    return dt.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]  # Remove last 3 digits for milliseconds

def extract_log_level(message: str) -> str:
    """Extract log level from message if present."""
    message_upper = message.upper()
    if "ERROR" in message_upper:
        return "error"
    elif "WARN" in message_upper:
        return "warn"
    elif "INFO" in message_upper:
        return "info"
    elif "DEBUG" in message_upper:
        return "debug"
    else:
        return "info"  # default

def transform_cloudwatch_log(cloudwatch_event: Dict[str, Any]) -> Dict[str, Any]:
    """Transform a single CloudWatch log event to the template format."""
    
    # Extract basic information
    timestamp_ms = cloudwatch_event.get("timestamp", 0)
    message = cloudwatch_event.get("message", "")
    log_stream = cloudwatch_event.get("logStreamName", "")
    
    # Convert timestamps
    iso_timestamp = timestamp_to_iso(timestamp_ms)
    readable_timestamp = timestamp_to_readable(timestamp_ms)
    
    # Extract log level
    log_level = extract_log_level(message)
    
    # Parse the message to extract structured data if it's JSON
    parsed_data = {}
    try:
        # Try to parse the message as JSON
        if message.strip().startswith("{"):
            parsed_data = json.loads(message.strip())
    except json.JSONDecodeError:
        # If not JSON, create a simple structure matching the template
        parsed_data = {
            "timestamp": iso_timestamp,
            "level": log_level,
            "message": message.strip()
        }
    
    # Create the transformed structure - EXACTLY matching the template
    transformed = {
        "@timestamp": readable_timestamp,
        "@message": {
            "time": iso_timestamp,
            "stream": "stdout",
            "_p": "F",
            "log": json.dumps(parsed_data) if parsed_data else message.strip(),
            "data": parsed_data,
            "kubernetes": {
                "pod_name": f"lambda-{log_stream.split('/')[-1] if log_stream else 'unknown'}",
                "pod_id": cloudwatch_event.get("eventId", ""),
                "docker_id": cloudwatch_event.get("eventId", ""),
            }
        }
    }
    
    return transformed

def main():
    if len(sys.argv) != 3:
        print("Usage: python3 transform_logs.py <input.json> <output.json>")
        sys.exit(1)
    
    input_file = sys.argv[1]
    output_file = sys.argv[2]
    
    try:
        # Read the input file
        with open(input_file, 'r') as f:
            cloudwatch_logs = json.load(f)
        
        # Transform each log event
        transformed_logs = []
        for log_event in cloudwatch_logs:
            transformed = transform_cloudwatch_log(log_event)
            transformed_logs.append(transformed)
        
        # Write the transformed logs
        with open(output_file, 'w') as f:
            json.dump(transformed_logs, f, indent=2)
        
        print(f"Successfully transformed {len(transformed_logs)} log entries")
        print(f"Output written to: {output_file}")
        
    except FileNotFoundError:
        print(f"Error: Input file '{input_file}' not found")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in input file: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()