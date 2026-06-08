from __future__ import annotations

from nacl.signing import SigningKey, VerifyKey

from peaq_ros2_stream.config import FieldRule, load_stream_agent_config_from_dict
from peaq_ros2_stream.crypto import SigningKeyMaterial, sign_envelope
from peaq_ros2_stream.envelope import build_unsigned_envelope
from peaq_ros2_stream.sequence import SequenceStore
from peaq_ros2_stream.transform import apply_field_rules, payload_hash, stable_json


def test_field_rules_hash_anonymize_and_exclude_nested_payload():
    payload = {
        'header': {'stamp': {'sec': 1, 'nanosec': 5}},
        'pose': {'x': 1.0, 'y': 2.0},
        'operator': {'name': 'alice'},
        'secret': 'keep local',
        'samples': [1, 2, 3],
    }
    transformed = apply_field_rules(
        payload,
        [
            FieldRule(path='pose', action='include'),
            FieldRule(path='operator.name', action='include'),
            FieldRule(path='secret', action='include'),
            FieldRule(path='samples', action='include'),
            FieldRule(path='operator.name', action='anonymize'),
            FieldRule(path='secret', action='hash'),
            FieldRule(path='samples', action='exclude'),
        ],
    )

    assert transformed['pose'] == {'x': 1.0, 'y': 2.0}
    assert transformed['operator']['name'] == {'redacted': True}
    assert transformed['secret'].startswith('sha256:')
    assert 'samples' not in transformed


def test_envelope_hash_sequence_and_signature_are_deterministic(tmp_path):
    cfg = load_stream_agent_config_from_dict(
        {
            'stream_agent': {
                'machine_id': 'mach_1',
                'agent_id': 'agent_1',
                'agent_token': 'token',
                'identity_ref': 'peaqos:machine:mach_1',
                'payload': {'store_inline': True, 'inline_limit_bytes': 512},
                'topics': [{'topic': '/battery', 'message_type': 'std_msgs/msg/String'}],
            }
        }
    )
    sequence = SequenceStore(str(tmp_path / 'seq.json'))
    assert sequence.next('mach_1', '/battery', 1) == 0
    assert sequence.next('mach_1', '/battery', 1) == 1

    payload = {'data': '73'}
    unsigned = build_unsigned_envelope(
        cfg,
        cfg.topics[0],
        'stream_pol_1',
        1,
        0,
        payload,
        None,
        '2026-05-29T10:00:00Z',
        signed_at='2026-05-29T10:00:01Z',
    )
    seed = SigningKey(bytes(32))
    material = SigningKeyMaterial(private_key_hex=seed.encode().hex(), public_key_hex=seed.verify_key.encode().hex())
    first = sign_envelope(unsigned, material, 'stream-key')
    second = sign_envelope(unsigned, material, 'stream-key')

    assert unsigned['payloadHash'] == payload_hash(payload)
    assert stable_json(unsigned) == stable_json(dict(reversed(list(unsigned.items()))))
    assert first['signature']['value'] == second['signature']['value']
    VerifyKey(bytes.fromhex(material.public_key_hex)).verify(
        stable_json(unsigned).encode('utf8'),
        bytes.fromhex(first['signature']['value']),
    )
