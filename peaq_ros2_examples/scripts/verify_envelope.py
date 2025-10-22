#!/usr/bin/env python3
import os
import sys
import json
import argparse
import hashlib
import requests

try:
    from nacl.signing import VerifyKey
    from nacl.encoding import HexEncoder
except Exception as e:
    print("PyNaCl not available:", e)
    sys.exit(2)


def fetch_json(url: str) -> dict:
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    return r.json()


def fetch_bytes(url: str) -> bytes:
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    return r.content


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--cid', required=True)
    ap.add_argument('--gw', default=os.environ.get('IPFS_GATEWAY', 'http://ipfsdaemon:8080/ipfs'))
    args = ap.parse_args()

    env_url = f"{args.gw.rstrip('/')}/{args.cid}"
    print(f"ENVELOPE_URL: {env_url}")

    envelope = fetch_json(env_url)
    print("ENVELOPE_JSON:")
    print(json.dumps(envelope, indent=2, sort_keys=True))

    payload = envelope.get('payload', {})
    header = envelope.get('header', {})
    proof = envelope.get('proof', {})
    data_cid = payload.get('dataCid', '')
    data_sha = payload.get('dataSha256', '')
    created_at = header.get('createdAt', 0)
    robot_id = header.get('robotId', '')

    if not data_cid:
        print('ERROR: dataCid missing in envelope')
        sys.exit(1)

    raw_url = f"{args.gw.rstrip('/')}/{data_cid}"
    print(f"RAW_URL: {raw_url}")
    raw = fetch_bytes(raw_url)

    raw_sha = hashlib.sha256(raw).hexdigest()
    print(f"RAW_SHA256: {raw_sha}")
    print(f"MATCHES_ENVELOPE_SHA: {str(raw_sha == data_sha)}")

    # Verify signature
    algo = (proof.get('algorithm') or '').lower()
    pub_hex = proof.get('publicKeyHex') or ''
    sig_hex = proof.get('signatureHex') or ''
    ok = False
    if algo == 'ed25519' and pub_hex and sig_hex:
        challenge = f"{raw_sha}|{int(created_at)}|{robot_id}".encode('utf-8')
        try:
            vk = VerifyKey(pub_hex, encoder=HexEncoder)
            vk.verify(challenge, bytes.fromhex(sig_hex))
            ok = True
        except Exception:
            ok = False
    print(f"SIGNATURE_VALID: {ok}")

    # Raw preview (best-effort decode)
    try:
        txt = raw.decode('utf-8')
    except Exception:
        txt = raw[:500].hex()
    print("RAW_CONTENT:")
    print(txt)


if __name__ == '__main__':
    main()


