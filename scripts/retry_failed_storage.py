#!/usr/bin/env python3
"""
Retry Failed Storage Operations

This script reads the failure log and retries failed blockchain submissions.
"""

import json
import sys
import subprocess
from pathlib import Path


def load_failures(log_path: str = '/tmp/storage_bridge_failures.jsonl'):
    """Load all failure records."""
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


def retry_storage_add(key: str, envelope_cid: str, core_node: str = 'peaq_core_node'):
    """Retry a failed storage operation."""
    # Create the value_json with proper escaping for YAML
    value_json = json.dumps({"envelopeCid": envelope_cid}).replace('"', '\\"')
    
    # Create the full request
    request = f'{{key: "{key}", value_json: "{value_json}"}}'
    
    print(f"\nRetrying: {key}")
    print(f"  Envelope CID: {envelope_cid}")
    print(f"  Command: ros2 service call /{core_node}/storage/add peaq_ros2_interfaces/srv/StoreAddData '{request}'")
    
    # Call the service
    try:
        result = subprocess.run(
            ['ros2', 'service', 'call', f'/{core_node}/storage/add', 
             'peaq_ros2_interfaces/srv/StoreAddData', request],
            capture_output=True,
            text=True,
            timeout=60
        )
        
        if result.returncode == 0:
            print(f"  ✅ Success!")
            print(f"  Response: {result.stdout}")
            return True
        else:
            print(f"  ❌ Failed!")
            print(f"  Error: {result.stderr}")
            return False
    except subprocess.TimeoutExpired:
        print(f"  ❌ Timeout!")
        return False
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return False


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Retry Failed Storage Operations',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Retry all failed operations
  python3 retry_failed_storage.py
  
  # Retry specific key
  python3 retry_failed_storage.py --key temperature_sensor
  
  # Use custom log file
  python3 retry_failed_storage.py --log /path/to/failures.jsonl
  
  # Dry run (show what would be retried)
  python3 retry_failed_storage.py --dry-run
        """
    )
    
    parser.add_argument(
        '--log',
        default='/tmp/storage_bridge_failures.jsonl',
        help='Path to failure log file'
    )
    parser.add_argument(
        '--key',
        help='Retry only this specific key'
    )
    parser.add_argument(
        '--core-node',
        default='peaq_core_node',
        help='Name of core node'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be retried without actually retrying'
    )
    
    args = parser.parse_args()
    
    # Load failures
    failures = load_failures(args.log)
    
    if not failures:
        print("✅ No failures to retry!")
        return 0
    
    # Filter by key if specified
    if args.key:
        failures = [f for f in failures if f.get('key') == args.key]
        if not failures:
            print(f"No failures found for key: {args.key}")
            return 1
    
    print(f"\nFound {len(failures)} failed operation(s) to retry\n")
    print("="*80)
    
    # Retry each failure
    success_count = 0
    fail_count = 0
    
    for i, f in enumerate(failures, 1):
        key = f.get('key', '')
        envelope_cid = f.get('envelope_cid', '')
        
        if not key or not envelope_cid:
            print(f"\n[{i}] Skipping invalid record (missing key or CID)")
            continue
        
        print(f"\n[{i}/{len(failures)}]")
        
        if args.dry_run:
            print(f"Would retry: {key}")
            print(f"  Envelope CID: {envelope_cid}")
            print(f"  IPFS URL: {f.get('ipfs_gateway', '')}/{envelope_cid}")
            continue
        
        if retry_storage_add(key, envelope_cid, args.core_node):
            success_count += 1
        else:
            fail_count += 1
    
    # Summary
    print("\n" + "="*80)
    if args.dry_run:
        print(f"\nDry run complete. Would retry {len(failures)} operation(s).")
    else:
        print(f"\nRetry complete:")
        print(f"  ✅ Success: {success_count}")
        print(f"  ❌ Failed: {fail_count}")
        
        if success_count > 0:
            print(f"\n💡 Tip: Clear the failure log after verifying success:")
            print(f"  python3 scripts/check_storage_failures.py --clear")
    
    return 0 if fail_count == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
