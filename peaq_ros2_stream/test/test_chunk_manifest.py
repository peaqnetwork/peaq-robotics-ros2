from __future__ import annotations

import hashlib

from nacl.public import PrivateKey, SealedBox
from nacl.signing import SigningKey, VerifyKey

from peaq_ros2_stream.chunk_manifest import (
    build_buyer_access,
    build_signed_chunk_manifest,
    chunk_signature_payload,
)
from peaq_ros2_stream.config import load_stream_agent_config_from_dict
from peaq_ros2_stream.crypto import SigningKeyMaterial
from peaq_ros2_stream.chunk_storage import append_manifest, build_and_store_chunk, last_manifest_chunk_id
from peaq_ros2_stream.encryption import decrypt_chunk_payload, encrypt_chunk_payload, wrap_chunk_key_for_buyer


def _cfg(owner_public_key_hex: str = ''):
    key_recipients = []
    if owner_public_key_hex:
        key_recipients.append(
            {
                'recipient_id': 'owner-1',
                'recipient_type': 'owner',
                'public_key_hex': owner_public_key_hex,
            }
        )
    return load_stream_agent_config_from_dict(
        {
            'stream_agent': {
                'machine_id': 'mach_1',
                'agent_id': 'agent_1',
                'agent_token': 'token',
                'identity_ref': 'did:peaq:mach_1',
                'topics': [{'topic': '/battery', 'message_type': 'std_msgs/msg/String'}],
                'key_recipients': key_recipients,
            }
        }
    )


def _material() -> SigningKeyMaterial:
    key = SigningKey(bytes(32))
    return SigningKeyMaterial(private_key_hex=key.encode().hex(), public_key_hex=key.verify_key.encode().hex())


def test_chunk_encryption_and_buyer_key_wrapping_round_trip():
    payload = [{'data': '72'}, {'data': '73'}]
    key = bytes.fromhex('01' * 32)
    nonce = bytes.fromhex('02' * 24)
    encrypted = encrypt_chunk_payload(payload, key=key, nonce=nonce)

    assert encrypted.plaintext_hash.startswith('sha256:')
    assert encrypted.encrypted_data_hash == 'sha256:' + hashlib.sha256(encrypted.ciphertext_bytes).hexdigest()
    assert encrypted.key_commitment == 'sha256:' + hashlib.sha256(key).hexdigest()
    assert decrypt_chunk_payload(encrypted.ciphertext_bytes, key, nonce) == encrypted.plaintext_bytes

    buyer_private = PrivateKey.generate()
    wrapped = wrap_chunk_key_for_buyer(encrypted.key_hex, buyer_private.public_key.encode().hex())
    unwrapped_key = SealedBox(buyer_private).decrypt(bytes.fromhex(wrapped['wrappedKeyHex']))
    assert unwrapped_key == key


def test_signed_chunk_manifest_matches_final_schema_and_signature_contract():
    owner_private = PrivateKey.generate()
    cfg = _cfg(owner_private.public_key.encode().hex())
    material = _material()
    chunks = []
    for index in range(2):
        encrypted = encrypt_chunk_payload([{'data': str(index)}], key=bytes([index + 1]) * 32, nonce=bytes([index + 3]) * 24)
        manifest = build_signed_chunk_manifest(
            cfg,
            encrypted,
            material,
            'stream-key-1',
            f'chunk-{index}',
            f'file:///chunk-{index}.bin',
            previous_chunk_id=None if index == 0 else f'chunk-{index - 1}',
            index=index,
        )
        assert set(manifest.keys()) == {
            'schemaVersion',
            'chunkId',
            'previousChunkId',
            'index',
            'encryptedDataHash',
            'plaintextHash',
            'storageRef',
            'encryption',
            'signature',
        }
        assert manifest['schemaVersion'] == 'peaq.stream.chunks.v1'
        assert manifest['index'] == index
        assert manifest['previousChunkId'] == (None if index == 0 else f'chunk-{index - 1}')
        VerifyKey(bytes.fromhex(material.public_key_hex)).verify(
            chunk_signature_payload(manifest).encode('utf8'),
            bytes.fromhex(manifest['signature']['value']),
        )
        assert manifest['signature']['algorithm'] == 'ed25519'
        assert manifest['signature']['machineDid'] == 'did:peaq:mach_1'
        assert manifest['signature']['keyId'] == 'stream-key-1'
        assert manifest['signature']['publicKeyHex'] == material.public_key_hex
        recipient = manifest['encryption']['keyRecipients'][0]
        assert recipient['recipientType'] == 'owner'
        assert SealedBox(owner_private).decrypt(bytes.fromhex(recipient['wrappedKeyHex'])) == bytes([index + 1]) * 32
        chunks.append(manifest)

    buyer_private = PrivateKey.generate()
    buyer_access = build_buyer_access(
        chunks[0]['chunkId'],
        '01' * 32,
        'did:peaq:buyer-1',
        buyer_private.public_key.encode().hex(),
    )
    assert buyer_access['schemaVersion'] == 'peaq.stream.buyer-access.v1'
    assert buyer_access['chunkId'] == chunks[0]['chunkId']
    assert buyer_access['buyer']['recipientType'] == 'buyer'
    assert buyer_access['buyer']['algorithm'] == 'x25519-sealedbox'
    assert SealedBox(buyer_private).decrypt(bytes.fromhex(buyer_access['buyer']['wrappedKeyHex'])) == bytes.fromhex('01' * 32)


def test_local_chunk_storage_writes_one_file_and_manifest_array(tmp_path):
    owner_private = PrivateKey.generate()
    cfg = _cfg(owner_private.public_key.encode().hex())
    material = _material()
    encrypted = encrypt_chunk_payload([{'data': '72'}], key=b'\x04' * 32, nonce=b'\x05' * 24)

    manifest = build_and_store_chunk(
        tmp_path / 'chunks',
        cfg,
        encrypted,
        material,
        'stream-key-1',
        index=0,
    )
    manifests = append_manifest(tmp_path / 'manifests.json', manifest)

    assert len(list((tmp_path / 'chunks').glob('*.bin'))) == 1
    assert manifests == [manifest]
    assert last_manifest_chunk_id(tmp_path / 'manifests.json') == manifest['chunkId']
    assert set(manifests[0].keys()) == {
        'schemaVersion',
        'chunkId',
        'previousChunkId',
        'index',
        'encryptedDataHash',
        'plaintextHash',
        'storageRef',
        'encryption',
        'signature',
    }
