"""Local encrypted chunk file storage for Stream v1."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .chunk_manifest import CHUNK_SCHEMA_VERSION, build_signed_chunk_manifest
from .crypto import SigningKeyMaterial
from .encryption import EncryptedChunk
from .models import StreamAgentConfig
from .transform import payload_hash


def deterministic_chunk_id(
    previous_chunk_id: str | None,
    index: int,
    plaintext_hash: str,
    encrypted_data_hash: str,
) -> str:
    return payload_hash(
        {
            'schemaVersion': CHUNK_SCHEMA_VERSION,
            'previousChunkId': previous_chunk_id,
            'index': int(index),
            'plaintextHash': plaintext_hash,
            'encryptedDataHash': encrypted_data_hash,
        }
    )


def chunk_file_name(chunk_id: str) -> str:
    return f'{chunk_id.removeprefix("sha256:")}.bin'


def write_encrypted_chunk_file(directory: str | Path, chunk_id: str, encrypted: EncryptedChunk) -> str:
    root = Path(directory).expanduser()
    root.mkdir(parents=True, exist_ok=True)
    path = root / chunk_file_name(chunk_id)
    path.write_bytes(encrypted.ciphertext_bytes)
    return path.resolve().as_uri()


def build_and_store_chunk(
    directory: str | Path,
    cfg: StreamAgentConfig,
    encrypted: EncryptedChunk,
    signing_key: SigningKeyMaterial,
    signing_key_id: str,
    previous_chunk_id: str | None = None,
    index: int = 0,
) -> dict[str, Any]:
    chunk_id = deterministic_chunk_id(
        previous_chunk_id,
        index,
        encrypted.plaintext_hash,
        encrypted.encrypted_data_hash,
    )
    storage_ref = write_encrypted_chunk_file(directory, chunk_id, encrypted)
    return build_signed_chunk_manifest(
        cfg,
        encrypted,
        signing_key,
        signing_key_id,
        chunk_id=chunk_id,
        storage_ref=storage_ref,
        previous_chunk_id=previous_chunk_id,
        index=index,
    )


def append_manifest(manifest_path: str | Path, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    path = Path(manifest_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        with path.open('r', encoding='utf8') as handle:
            manifests = json.load(handle)
        if not isinstance(manifests, list):
            raise ValueError('manifest file must contain a JSON array')
    else:
        manifests = []
    manifests.append(manifest)
    with path.open('w', encoding='utf8') as handle:
        json.dump(manifests, handle, indent=2, sort_keys=True)
    return manifests


def read_manifest_array(manifest_path: str | Path) -> list[dict[str, Any]]:
    path = Path(manifest_path).expanduser()
    if not path.exists():
        return []
    with path.open('r', encoding='utf8') as handle:
        manifests = json.load(handle)
    if not isinstance(manifests, list):
        raise ValueError('manifest file must contain a JSON array')
    return [item for item in manifests if isinstance(item, dict)]


def last_manifest_chunk_id(manifest_path: str | Path) -> str | None:
    manifests = read_manifest_array(manifest_path)
    if not manifests:
        return None
    chunk_id = manifests[-1].get('chunkId')
    return str(chunk_id) if chunk_id else None
