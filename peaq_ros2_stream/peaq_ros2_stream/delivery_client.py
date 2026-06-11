"""Client helpers for downloading and verifying delivered Stream chunks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import unquote, urlparse

import requests
from nacl.public import PrivateKey, SealedBox
from nacl.signing import VerifyKey

from .chunk_manifest import chunk_signature_payload
from .encryption import decrypt_chunk_payload
from .storage_adapters import read_google_drive_file, read_s3_object, read_walrus_blob
from .transform import byte_hash


@dataclass(frozen=True)
class DeliveredChunk:
    manifest: dict[str, Any]
    encrypted_data: bytes


class StreamDeliveryClient:
    def __init__(self, base_url: str, token: str, timeout: float = 10.0) -> None:
        self.base_url = base_url.rstrip('/')
        self.token = token
        self.timeout = timeout
        self.session = requests.Session()

    def _headers(self) -> dict[str, str]:
        return {'authorization': f'Bearer {self.token}'}

    def list_chunks(self, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        response = self.session.get(
            f'{self.base_url}/chunks',
            params=params or {},
            headers=self._headers(),
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        return [item for item in payload.get('items', []) if isinstance(item, dict)]

    def get_manifest(self, chunk_id: str) -> dict[str, Any]:
        response = self.session.get(
            f'{self.base_url}/chunks/{chunk_id}/manifest',
            headers=self._headers(),
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        item = payload.get('item')
        if not isinstance(item, dict):
            raise ValueError('delivery response did not include a chunk manifest')
        return item

    def get_encrypted_data(self, chunk_id: str) -> bytes:
        response = self.session.get(
            f'{self.base_url}/chunks/{chunk_id}/data',
            headers=self._headers(),
            timeout=self.timeout,
        )
        response.raise_for_status()
        return bytes(response.content)

    def fetch_chunk(self, chunk_id: str) -> DeliveredChunk:
        manifest = self.get_manifest(chunk_id)
        encrypted_data = self.get_encrypted_data(chunk_id)
        verify_delivered_chunk(manifest, encrypted_data)
        return DeliveredChunk(manifest=manifest, encrypted_data=encrypted_data)


def verify_delivered_chunk(manifest: dict[str, Any], encrypted_data: bytes) -> None:
    expected_hash = str(manifest.get('encryptedDataHash') or '')
    actual_hash = byte_hash(encrypted_data)
    if actual_hash != expected_hash:
        raise ValueError('delivered chunk encryptedDataHash mismatch')

    signature = manifest.get('signature')
    if not isinstance(signature, dict):
        raise ValueError('delivered chunk manifest is missing signature')
    public_key_hex = str(signature.get('publicKeyHex') or '').removeprefix('0x')
    value_hex = str(signature.get('value') or '').removeprefix('0x')
    if not public_key_hex or not value_hex:
        raise ValueError('delivered chunk signature is incomplete')
    VerifyKey(bytes.fromhex(public_key_hex)).verify(
        chunk_signature_payload(manifest).encode('utf8'),
        bytes.fromhex(value_hex),
    )


def unwrap_buyer_chunk_key(buyer_access: dict[str, Any], buyer_private_key_hex: str) -> bytes:
    buyer = buyer_access.get('buyer')
    if not isinstance(buyer, dict):
        raise ValueError('buyer access is missing buyer data')
    if buyer.get('recipientType') != 'buyer':
        raise ValueError('buyer access recipientType must be buyer')
    wrapped_key_hex = str(buyer.get('wrappedKeyHex') or '').removeprefix('0x')
    if not wrapped_key_hex:
        raise ValueError('buyer access is missing wrappedKeyHex')
    private_key = PrivateKey(bytes.fromhex(buyer_private_key_hex.removeprefix('0x')))
    return bytes(SealedBox(private_key).decrypt(bytes.fromhex(wrapped_key_hex)))


def decrypt_delivered_chunk(
    manifest: dict[str, Any],
    encrypted_data: bytes,
    buyer_access: dict[str, Any],
    buyer_private_key_hex: str,
) -> bytes:
    verify_delivered_chunk(manifest, encrypted_data)
    if str(buyer_access.get('chunkId') or '') != str(manifest.get('chunkId') or ''):
        raise ValueError('buyer access chunkId does not match manifest chunkId')
    encryption = manifest.get('encryption')
    if not isinstance(encryption, dict):
        raise ValueError('delivered chunk manifest is missing encryption data')
    nonce_hex = str(encryption.get('nonce') or '').removeprefix('0x')
    key = unwrap_buyer_chunk_key(buyer_access, buyer_private_key_hex)
    return decrypt_chunk_payload(encrypted_data, key, bytes.fromhex(nonce_hex))


def read_storage_ref(
    storage_ref: str,
    *,
    walrus_aggregator_url: str = '',
    s3_client: Any | None = None,
    google_drive_service: Any | None = None,
    google_drive_credentials_path: str = '',
    http_session: requests.Session | None = None,
    timeout: float = 10.0,
) -> bytes:
    parsed = urlparse(storage_ref)
    if parsed.scheme == 'file':
        return open(unquote(parsed.path), 'rb').read()
    if parsed.scheme == 'walrus':
        return read_walrus_blob(walrus_aggregator_url, parsed.netloc or parsed.path.lstrip('/'), session=http_session, timeout=timeout)
    if parsed.scheme == 's3':
        return read_s3_object(storage_ref, client=s3_client)
    if parsed.scheme in {'gdrive', 'google-drive'}:
        return read_google_drive_file(
            parsed.netloc or parsed.path.lstrip('/'),
            service=google_drive_service,
            credentials_path=google_drive_credentials_path,
        )
    raise ValueError(f'unsupported stream storageRef scheme: {parsed.scheme}')


def fetch_storage_chunk(manifest: dict[str, Any], **kwargs: Any) -> DeliveredChunk:
    encrypted_data = read_storage_ref(str(manifest.get('storageRef') or ''), **kwargs)
    verify_delivered_chunk(manifest, encrypted_data)
    return DeliveredChunk(manifest=manifest, encrypted_data=encrypted_data)
