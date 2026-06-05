"""Ed25519 signing key management for Stream envelopes."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Mapping

from nacl.signing import SigningKey

from .transform import stable_json


@dataclass(frozen=True)
class SigningKeyMaterial:
    private_key_hex: str
    public_key_hex: str
    algorithm: str = 'ed25519'

    @property
    def signing_key(self) -> SigningKey:
        return SigningKey(bytes.fromhex(self.private_key_hex))


def load_or_create_signing_key(path: str) -> SigningKeyMaterial:
    expanded = os.path.expanduser(path)
    if os.path.exists(expanded):
        with open(expanded, 'r', encoding='utf8') as handle:
            data = json.load(handle)
        return SigningKeyMaterial(
            private_key_hex=str(data['privateKeyHex']).removeprefix('0x'),
            public_key_hex=str(data['publicKeyHex']).removeprefix('0x'),
        )

    key = SigningKey.generate()
    material = SigningKeyMaterial(
        private_key_hex=key.encode().hex(),
        public_key_hex=key.verify_key.encode().hex(),
    )
    os.makedirs(os.path.dirname(expanded) or '.', exist_ok=True)
    with open(expanded, 'w', encoding='utf8') as handle:
        json.dump(
            {
                'algorithm': material.algorithm,
                'privateKeyHex': material.private_key_hex,
                'publicKeyHex': material.public_key_hex,
            },
            handle,
            indent=2,
        )
    os.chmod(expanded, 0o600)
    return material


def sign_envelope(unsigned_envelope: Mapping[str, Any], material: SigningKeyMaterial, key_id: str) -> dict[str, Any]:
    signature = sign_payload(unsigned_envelope, material)
    envelope = dict(unsigned_envelope)
    envelope['signature'] = {
        'keyId': key_id,
        'algorithm': material.algorithm,
        'value': signature,
    }
    return envelope


def sign_payload(payload: Mapping[str, Any], material: SigningKeyMaterial) -> str:
    data = stable_json(dict(payload)).encode('utf8')
    return material.signing_key.sign(data).signature.hex()


def sign_text(value: str, material: SigningKeyMaterial) -> str:
    return material.signing_key.sign(value.encode('utf8')).signature.hex()
