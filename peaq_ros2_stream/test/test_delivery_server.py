from __future__ import annotations

import json
from urllib.error import HTTPError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

import pytest
from nacl.public import PrivateKey
from nacl.signing import SigningKey

from peaq_ros2_stream.chunk_catalog import StreamChunkCatalog, record_from_manifest
from peaq_ros2_stream.chunk_storage import append_manifest, build_and_store_chunk
from peaq_ros2_stream.config import load_stream_agent_config_from_dict
from peaq_ros2_stream.crypto import SigningKeyMaterial
from peaq_ros2_stream.delivery_client import (
    StreamDeliveryClient,
    decrypt_delivered_chunk,
    fetch_storage_chunk,
    verify_delivered_chunk,
)
from peaq_ros2_stream.delivery_server import StreamDeliveryServer
from peaq_ros2_stream.encryption import encrypt_chunk_payload, wrap_chunk_key_for_buyer


def _cfg(owner_public_key_hex: str):
    return load_stream_agent_config_from_dict(
        {
            'stream_agent': {
                'machine_id': 'mach_1',
                'agent_id': 'agent_1',
                'agent_token': 'token',
                'identity_ref': 'did:peaq:mach_1',
                'topics': [{'topic': '/battery', 'message_type': 'std_msgs/msg/String'}],
                'key_recipients': [
                    {
                        'recipient_id': 'owner-1',
                        'recipient_type': 'owner',
                        'public_key_hex': owner_public_key_hex,
                    }
                ],
            }
        }
    )


def _material() -> SigningKeyMaterial:
    key = SigningKey(bytes(32))
    return SigningKeyMaterial(private_key_hex=key.encode().hex(), public_key_hex=key.verify_key.encode().hex())


def _request(base_url: str, path: str, token: str = '', extra_headers: dict[str, str] | None = None):
    headers = {'authorization': f'Bearer {token}'} if token else {}
    headers.update(extra_headers or {})
    request = Request(f'{base_url}{path}', headers=headers)
    with urlopen(request, timeout=3) as response:
        body = response.read()
        content_type = response.headers.get('content-type', '')
        response_headers = dict(response.headers)
        status = response.status
    return body, content_type, response_headers, status


def test_delivery_server_lists_manifest_and_encrypted_chunk_data(tmp_path):
    owner_private = PrivateKey.generate()
    cfg = _cfg(owner_private.public_key.encode().hex())
    encrypted = encrypt_chunk_payload({'data': '72'}, key=b'\x0a' * 32, nonce=b'\x0b' * 24)
    manifest = build_and_store_chunk(
        tmp_path / 'chunks',
        cfg,
        encrypted,
        _material(),
        'stream-key-1',
        index=2,
    )
    manifest_path = tmp_path / 'manifests.json'
    append_manifest(manifest_path, manifest)

    catalog = StreamChunkCatalog(str(tmp_path / 'catalog.sqlite3'))
    catalog.upsert(
        record_from_manifest(
            manifest,
            machine_id='mach_1',
            agent_id='agent_1',
            topic='/battery',
            message_type='std_msgs/msg/String',
            policy_id='policy-1',
            policy_version=1,
            sequence_number=2,
            source_timestamp=None,
            agent_received_at='2026-06-09T11:00:00Z',
            manifest_path=str(manifest_path),
        )
    )

    server = StreamDeliveryServer(catalog, str(manifest_path), token='delivery-token', port=0)
    server.start()
    try:
        host, port = server.address
        base_url = f'http://{host}:{port}'

        health_body, _, _, _ = _request(base_url, '/health')
        assert json.loads(health_body) == {'ok': True}

        with pytest.raises(HTTPError) as missing_auth:
            _request(base_url, '/chunks')
        assert missing_auth.value.code == 401

        query = urlencode({'topic': '/battery'})
        list_body, _, _, _ = _request(base_url, f'/chunks?{query}', token='delivery-token')
        listed = json.loads(list_body)
        assert listed['count'] == 1
        assert listed['items'][0]['chunk_id'] == manifest['chunkId']

        chunk_path = quote(manifest['chunkId'], safe='')
        manifest_body, _, _, _ = _request(base_url, f'/chunks/{chunk_path}/manifest', token='delivery-token')
        assert json.loads(manifest_body)['item'] == manifest

        data_body, content_type, _, status = _request(base_url, f'/chunks/{chunk_path}/data', token='delivery-token')
        assert content_type == 'application/octet-stream'
        assert status == 200
        assert data_body == encrypted.ciphertext_bytes
        verify_delivered_chunk(manifest, data_body)

        partial_body, _, partial_headers, partial_status = _request(
            base_url,
            f'/chunks/{chunk_path}/data',
            token='delivery-token',
            extra_headers={'range': 'bytes=0-9'},
        )
        assert partial_status == 206
        assert partial_body == encrypted.ciphertext_bytes[:10]
        assert partial_headers['content-range'].startswith('bytes 0-9/')

        server.allow_token('session-token')
        token_body, _, _, _ = _request(base_url, f'/chunks/{chunk_path}/data', token='session-token')
        assert token_body == encrypted.ciphertext_bytes

        client = StreamDeliveryClient(base_url, 'delivery-token')
        delivered = client.fetch_chunk(manifest['chunkId'])
        assert delivered.manifest == manifest
        assert delivered.encrypted_data == encrypted.ciphertext_bytes

        from_storage = fetch_storage_chunk(manifest)
        assert from_storage.encrypted_data == encrypted.ciphertext_bytes

        buyer_private = PrivateKey.generate()
        wrapped = wrap_chunk_key_for_buyer(encrypted.key_hex, buyer_private.public_key.encode().hex())
        buyer_access = {
            'schemaVersion': 'peaq.stream.buyer-access.v1',
            'chunkId': manifest['chunkId'],
            'buyer': {
                'recipientId': 'did:peaq:buyer',
                'recipientType': 'buyer',
                'algorithm': 'x25519-sealedbox',
                'publicKeyHex': buyer_private.public_key.encode().hex(),
                'wrappedKeyHex': wrapped['wrappedKeyHex'],
            },
        }
        plaintext = decrypt_delivered_chunk(
            delivered.manifest,
            delivered.encrypted_data,
            buyer_access,
            buyer_private.encode().hex(),
        )
        assert plaintext == encrypted.plaintext_bytes
    finally:
        server.stop()
