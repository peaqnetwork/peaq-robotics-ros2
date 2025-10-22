#!/usr/bin/env python3
"""
Storage Bridge Failure Checker and Recovery Tool

This script helps you:
1. View all failed storage operations
2. Analyze failure patterns
3. Generate recovery commands to retry failed operations
"""

import json
import sys
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any


def load_failures(log_path: str = '/tmp/storage_bridge_failures.jsonl') -> List[Dict[str, Any]]:
    """Load all failure records from the JSONL log file."""
    failures = []
    log_file = Path(log_path)
    
    if not log_file.exists():
        print(f"No failure log found at {log_path}")
        return failures
    
    with open(log_file, 'r') as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    failures.append(json.loads(line))
                except json.JSONDecodeError as e:
                    print(f"Warning: Failed to parse line: {e}")
    
    return failures


def print_summary(failures: List[Dict[str, Any]]) -> None:
    """Print summary statistics of failures."""
    if not failures:
        print("✅ No failures recorded!")
        return
    
    print(f"\n{'='*80}")
    print(f"STORAGE BRIDGE FAILURE SUMMARY")
    print(f"{'='*80}\n")
    
    print(f"Total failures: {len(failures)}")
    
    # Group by stage
    stages = {}
    for f in failures:
        stage = f.get('stage', 'unknown')
        stages[stage] = stages.get(stage, 0) + 1
    
    print(f"\nFailures by stage:")
    for stage, count in sorted(stages.items(), key=lambda x: x[1], reverse=True):
        print(f"  {stage}: {count}")
    
    # Group by error type
    errors = {}
    for f in failures:
        error = f.get('error', 'unknown')
        # Extract error type (first 50 chars)
        error_type = error[:50] + '...' if len(error) > 50 else error
        errors[error_type] = errors.get(error_type, 0) + 1
    
    print(f"\nTop error types:")
    for error, count in sorted(errors.items(), key=lambda x: x[1], reverse=True)[:5]:
        print(f"  [{count}x] {error}")
    
    # Recent failures
    print(f"\nMost recent failures:")
    recent = sorted(failures, key=lambda x: x.get('timestamp', 0), reverse=True)[:5]
    for f in recent:
        timestamp = f.get('timestamp_iso', 'unknown')
        key = f.get('key', 'unknown')
        stage = f.get('stage', 'unknown')
        print(f"  {timestamp} - {key} ({stage})")


def print_details(failures: List[Dict[str, Any]]) -> None:
    """Print detailed information about each failure."""
    if not failures:
        return
    
    print(f"\n{'='*80}")
    print(f"DETAILED FAILURE RECORDS")
    print(f"{'='*80}\n")
    
    for i, f in enumerate(failures, 1):
        print(f"[{i}] Failure at {f.get('timestamp_iso', 'unknown')}")
        print(f"    Key: {f.get('key', 'unknown')}")
        print(f"    Stage: {f.get('stage', 'unknown')}")
        print(f"    Envelope CID: {f.get('envelope_cid', 'unknown')}")
        print(f"    Data CID: {f.get('data_cid', 'unknown')}")
        print(f"    Attempts: {f.get('attempts', 0)}")
        print(f"    Error: {f.get('error', 'unknown')}")
        print(f"    Robot ID: {f.get('robot_id', 'unknown')}")
        print(f"    Network: {f.get('network', 'unknown')}")
        
        # Show IPFS URL if available
        gateway = f.get('ipfs_gateway', '')
        envelope_cid = f.get('envelope_cid', '')
        if gateway and envelope_cid:
            ipfs_url = f"{gateway.rstrip('/')}/{envelope_cid}"
            print(f"    IPFS URL: {ipfs_url}")
        
        print()


def generate_recovery_commands(failures: List[Dict[str, Any]], core_node: str = 'peaq_core_node') -> None:
    """Generate ROS2 commands to retry failed operations."""
    if not failures:
        return
    
    print(f"\n{'='*80}")
    print(f"RECOVERY COMMANDS")
    print(f"{'='*80}\n")
    
    print("Run these commands to retry failed blockchain submissions:\n")
    
    for i, f in enumerate(failures, 1):
        key = f.get('key', '')
        envelope_cid = f.get('envelope_cid', '')
        
        if not key or not envelope_cid:
            continue
        
        print(f"# [{i}] Retry {key}")
        print(f"# Data is available at: {f.get('ipfs_gateway', '')}/{envelope_cid}")
        print(f"ros2 service call /{core_node}/storage/add peaq_ros2_interfaces/srv/StoreAddData \\")
        print(f"  '{{key: \"{key}\", value_json: \"{{\\\\\\\\\\\\\\\"envelopeCid\\\\\\\\\\\\\\\": \\\\\\\\\\\\\\\"{envelope_cid}\\\\\\\\\\\\\\\"}}\"}}'")
        print()
        print(f"# Or use Python to avoid escaping issues:")
        print(f"python3 -c \"import subprocess; subprocess.run(['ros2', 'service', 'call', '/{core_node}/storage/add', 'peaq_ros2_interfaces/srv/StoreAddData', '{{key: \\\"{key}\\\", value_json: \\\"{{\\\\\\\\\\\"envelopeCid\\\\\\\\\\\": \\\\\\\\\\\"{envelope_cid}\\\\\\\\\\\"}}\\\"}}']])\"")
        print()


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Storage Bridge Failure Checker and Recovery Tool',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # View summary of failures
  python3 check_storage_failures.py
  
  # View detailed failure information
  python3 check_storage_failures.py --details
  
  # Generate recovery commands
  python3 check_storage_failures.py --recovery
  
  # Use custom log file
  python3 check_storage_failures.py --log /path/to/failures.jsonl
  
  # Clear failure log after review
  python3 check_storage_failures.py --clear
        """
    )
    
    parser.add_argument(
        '--log',
        default='/tmp/storage_bridge_failures.jsonl',
        help='Path to failure log file (default: /tmp/storage_bridge_failures.jsonl)'
    )
    parser.add_argument(
        '--details',
        action='store_true',
        help='Show detailed information about each failure'
    )
    parser.add_argument(
        '--recovery',
        action='store_true',
        help='Generate recovery commands to retry failed operations'
    )
    parser.add_argument(
        '--core-node',
        default='peaq_core_node',
        help='Name of core node for recovery commands (default: peaq_core_node)'
    )
    parser.add_argument(
        '--clear',
        action='store_true',
        help='Clear the failure log after displaying (use with caution!)'
    )
    
    args = parser.parse_args()
    
    # Load failures
    failures = load_failures(args.log)
    
    # Always show summary
    print_summary(failures)
    
    # Show details if requested
    if args.details:
        print_details(failures)
    
    # Generate recovery commands if requested
    if args.recovery:
        generate_recovery_commands(failures, args.core_node)
    
    # Clear log if requested
    if args.clear:
        if failures:
            response = input(f"\n⚠️  Clear {len(failures)} failure records from {args.log}? (yes/no): ")
            if response.lower() == 'yes':
                Path(args.log).unlink()
                print(f"✅ Cleared {args.log}")
            else:
                print("Cancelled")
        else:
            print("No failures to clear")
    
    # Exit with appropriate code
    sys.exit(0 if not failures else 1)


if __name__ == '__main__':
    main()
