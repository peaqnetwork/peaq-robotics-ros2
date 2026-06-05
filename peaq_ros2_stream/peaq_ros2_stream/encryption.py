"""Chunk encryption and buyer key wrapping."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from nacl.public import PublicKey, SealedBox
from nacl.secret import Aead
from nacl.utils import random

from .transform import payload_hash, stable_json


ALGORITHM = 'xchacha20-poly1305'
WRAP_ALGORITHM = 'x25519-sealedbox'


@dataclass(frozen=True)
class EncryptedChunk:
    plaintext_bytes: bytes
    ciphertext_bytes: bytes
    key_hex: str
    nonce_hex: str
    plaintext_hash: str
    encrypted_data_hash: str
    key_commitment: str


def encode_chunk_payload(payload: Any) -> bytes:
    return stable_json(payload).encode('utf8')


def encrypt_chunk_payload(payload: Any, key: bytes | None = None, nonce: bytes | None = None, aad: bytes = b'') -> EncryptedChunk:
    data = encode_chunk_payload(payload)
    key_bytes = key or random(Aead.KEY_SIZE)
    nonce_bytes = nonce or random(Aead.NONCE_SIZE)
    if len(key_bytes) != Aead.KEY_SIZE:
        raise ValueError('chunk key must be 32 bytes')
    if len(nonce_bytes) != Aead.NONCE_SIZE:
        raise ValueError('chunk nonce must be 24 bytes')
    encrypted = Aead(key_bytes).encrypt(data, aad=aad, nonce=nonce_bytes)
    ciphertext = bytes(encrypted.ciphertext)
    return EncryptedChunk(
        plaintext_bytes=data,
        ciphertext_bytes=ciphertext,
        key_hex=key_bytes.hex(),
        nonce_hex=nonce_bytes.hex(),
        plaintext_hash=payload_hash(payload),
        encrypted_data_hash=payload_hash(ciphertext.hex()),
        key_commitment=payload_hash(key_bytes.hex()),
    )


def decrypt_chunk_payload(ciphertext: bytes, key: bytes, nonce: bytes, aad: bytes = b'') -> bytes:
    return bytes(Aead(key).decrypt(ciphertext, aad=aad, nonce=nonce))


def wrap_chunk_key(key_hex: str, public_key_hex: str) -> dict[str, str]:
    key_bytes = bytes.fromhex(key_hex.removeprefix('0x'))
    recipient_key = PublicKey(bytes.fromhex(public_key_hex.removeprefix('0x')))
    return {
        'algorithm': WRAP_ALGORITHM,
        'wrappedKeyHex': SealedBox(recipient_key).encrypt(key_bytes).hex(),
    }


def wrap_chunk_key_for_buyer(key_hex: str, buyer_public_key_hex: str) -> dict[str, str]:
    return wrap_chunk_key(key_hex, buyer_public_key_hex)
