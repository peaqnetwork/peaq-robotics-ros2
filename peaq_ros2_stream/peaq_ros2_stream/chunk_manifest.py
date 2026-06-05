"""Signed chunk manifest builders."""

from __future__ import annotations

from typing import Any

from .crypto import SigningKeyMaterial, sign_text
from .encryption import ALGORITHM, EncryptedChunk, wrap_chunk_key
from .models import StreamAgentConfig

CHUNK_SCHEMA_VERSION = 'peaq.stream.chunks.v1'
BUYER_ACCESS_SCHEMA_VERSION = 'peaq.stream.buyer-access.v1'


def chunk_leaf_payload(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        'schemaVersion': manifest['schemaVersion'],
        'chunkId': manifest['chunkId'],
        'previousChunkId': manifest.get('previousChunkId'),
        'index': manifest['index'],
        'encryptedDataHash': manifest['encryptedDataHash'],
        'plaintextHash': manifest['plaintextHash'],
        'storageRef': manifest['storageRef'],
        'encryption': manifest['encryption'],
        'signature': manifest['signature'],
    }


def chunk_signature_payload(manifest: dict[str, Any]) -> str:
    return str(manifest['encryptedDataHash'])


def build_signed_chunk_manifest(
    cfg: StreamAgentConfig,
    encrypted: EncryptedChunk,
    signing_key: SigningKeyMaterial,
    signing_key_id: str,
    chunk_id: str,
    storage_ref: str,
    previous_chunk_id: str | None = None,
    index: int = 0,
) -> dict[str, Any]:
    if not cfg.key_recipients:
        raise ValueError('at least one key recipient is required for chunk encryption')
    key_recipients = [
        recipient.to_backend(wrap_chunk_key(encrypted.key_hex, recipient.public_key_hex)['wrappedKeyHex'])
        for recipient in cfg.key_recipients
    ]
    manifest: dict[str, Any] = {
        'schemaVersion': CHUNK_SCHEMA_VERSION,
        'chunkId': chunk_id,
        'previousChunkId': previous_chunk_id,
        'index': int(index),
        'encryptedDataHash': encrypted.encrypted_data_hash,
        'plaintextHash': encrypted.plaintext_hash,
        'storageRef': storage_ref,
        'encryption': {
            'algorithm': ALGORITHM,
            'nonce': encrypted.nonce_hex,
            'keyCommitment': encrypted.key_commitment,
            'keyRecipients': key_recipients,
        },
    }
    manifest['signature'] = {
        'algorithm': signing_key.algorithm,
        'machineDid': cfg.identity_ref,
        'keyId': signing_key_id,
        'publicKeyHex': signing_key.public_key_hex,
        'value': sign_text(encrypted.encrypted_data_hash, signing_key),
    }
    return manifest


def build_buyer_access(
    chunk_id: str,
    key_hex: str,
    buyer_recipient_id: str,
    buyer_public_key_hex: str,
) -> dict[str, Any]:
    wrapped = wrap_chunk_key(key_hex, buyer_public_key_hex)
    return {
        'schemaVersion': BUYER_ACCESS_SCHEMA_VERSION,
        'chunkId': chunk_id,
        'buyer': {
            'recipientId': buyer_recipient_id,
            'recipientType': 'buyer',
            'algorithm': wrapped['algorithm'],
            'publicKeyHex': buyer_public_key_hex.removeprefix('0x').lower(),
            'wrappedKeyHex': wrapped['wrappedKeyHex'],
        },
    }
