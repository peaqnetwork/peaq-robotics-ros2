"""Local X25519 recipient keys for Stream chunk recovery."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from nacl.public import PrivateKey


def load_or_create_recipient_key(path: str | Path) -> dict[str, str]:
    key_path = Path(path).expanduser()
    if key_path.exists():
        return _read_key_file(key_path)

    private_key = PrivateKey.generate()
    payload = {
        'algorithm': 'x25519-sealedbox',
        'privateKeyHex': private_key.encode().hex(),
        'publicKeyHex': private_key.public_key.encode().hex(),
    }
    key_path.parent.mkdir(parents=True, exist_ok=True)
    with key_path.open('w', encoding='utf8') as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
    key_path.chmod(0o600)
    return payload


def _read_key_file(path: Path) -> dict[str, str]:
    with path.open('r', encoding='utf8') as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError('recipient key file must contain a JSON object')
    public_key_hex = _clean_hex(payload.get('publicKeyHex'))
    private_key_hex = _clean_hex(payload.get('privateKeyHex'))
    if len(public_key_hex) != 64:
        raise ValueError('recipient public key must be a 32-byte hex string')
    if len(private_key_hex) != 64:
        raise ValueError('recipient private key must be a 32-byte hex string')
    return {
        'algorithm': 'x25519-sealedbox',
        'privateKeyHex': private_key_hex,
        'publicKeyHex': public_key_hex,
    }


def recipient_entry(recipient_id: str, recipient_type: str, public_key_hex: str) -> dict[str, str]:
    return {
        'recipient_id': recipient_id,
        'recipient_type': recipient_type,
        'public_key_hex': _clean_hex(public_key_hex),
    }


def _clean_hex(value: Any) -> str:
    return str(value or '').removeprefix('0x').lower()
