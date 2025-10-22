#!/usr/bin/env python3
import os
import sys
import json
import argparse
import requests


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--cid', required=True)
    parser.add_argument('--gw', default=os.environ.get('IPFS_GATEWAY', 'http://ipfsdaemon:8080/ipfs'))
    args = parser.parse_args()

    env_url = f"{args.gw.rstrip('/')}/{args.cid}"
    print(f"ENVELOPE_URL: {env_url}")
    r = requests.get(env_url, timeout=30)
    r.raise_for_status()
    envelope = r.json()
    print("ENVELOPE_HEAD:", json.dumps(envelope.get('header', {}), separators=(',', ':')))
    payload = envelope.get('payload', {})
    data_cid = payload.get('dataCid', '')
    print(f"DATA_CID: {data_cid}")
    if not data_cid:
        sys.exit(1)

    raw_url = f"{args.gw.rstrip('/')}/{data_cid}"
    print(f"RAW_URL: {raw_url}")
    rr = requests.get(raw_url, timeout=30)
    rr.raise_for_status()
    raw = rr.content
    try:
        preview = raw.decode('utf-8', errors='replace')[:500]
    except Exception:
        preview = str(raw[:200])
    print("RAW_PREVIEW:")
    print(preview)


if __name__ == '__main__':
    main()


