from __future__ import annotations

from nacl.public import PrivateKey
from nacl.signing import SigningKey

from peaq_ros2_stream.chunk_catalog import StreamChunkCatalog, record_from_manifest
from peaq_ros2_stream.chunk_storage import build_and_store_chunk
from peaq_ros2_stream.config import load_stream_agent_config_from_dict
from peaq_ros2_stream.crypto import SigningKeyMaterial
from peaq_ros2_stream.encryption import encrypt_chunk_payload


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


def test_chunk_catalog_records_local_file_and_queries_by_topic_and_time(tmp_path):
    owner_private = PrivateKey.generate()
    cfg = _cfg(owner_private.public_key.encode().hex())
    encrypted = encrypt_chunk_payload(
        {'data': '72'},
        key=b'\x06' * 32,
        nonce=b'\x07' * 24,
    )
    manifest = build_and_store_chunk(
        tmp_path / 'chunks',
        cfg,
        encrypted,
        _material(),
        'stream-key-1',
        index=9,
    )
    catalog = StreamChunkCatalog(str(tmp_path / 'catalog.sqlite3'))
    record = record_from_manifest(
        manifest,
        machine_id='mach_1',
        agent_id='agent_1',
        topic='/battery',
        message_type='std_msgs/msg/String',
        policy_id='policy-1',
        policy_version=3,
        sequence_number=9,
        source_timestamp='2026-06-09T10:00:00Z',
        agent_received_at='2026-06-09T10:00:01Z',
        manifest_path=str(tmp_path / 'manifests.json'),
    )

    catalog.upsert(record)

    loaded = catalog.get(manifest['chunkId'])
    assert loaded is not None
    assert loaded.topic == '/battery'
    assert loaded.chunk_index == 9
    assert loaded.observed_at == '2026-06-09T10:00:00Z'
    assert loaded.storage_provider == 'file'
    assert loaded.local_path.endswith('.bin')
    assert loaded.size_bytes == len(encrypted.ciphertext_bytes)

    matches = catalog.list_chunks(
        machine_id='mach_1',
        topic='/battery',
        start_time='2026-06-09T09:59:00Z',
        end_time='2026-06-09T10:01:00Z',
    )
    assert [item.chunk_id for item in matches] == [manifest['chunkId']]

    catalog.update_storage(manifest['chunkId'], 'walrus://blob-1', status='uploaded')
    updated = catalog.get(manifest['chunkId'])
    assert updated is not None
    assert updated.storage_ref == 'walrus://blob-1'
    assert updated.storage_provider == 'walrus'
    assert updated.local_path == ''
    assert updated.status == 'uploaded'
