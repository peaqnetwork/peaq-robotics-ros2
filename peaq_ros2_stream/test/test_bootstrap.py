from __future__ import annotations

import json
import stat

import pytest

from peaq_ros2_stream import bootstrap


class _Client:
    def __init__(self, base_url, api_key=''):
        self.base_url = base_url
        self.api_key = api_key
        self.calls = []

    def get_machine(self, machine_id):
        self.calls.append(('get_machine', machine_id))
        return {
            'id': machine_id,
            'status': 'active',
            'identityRef': 'did:peaq:0x0000000000000000000000000000000000000001',
        }

    def enroll_machine_agent(self, machine_id, label='Stream runtime', allowed_provider_keys=None):
        self.calls.append(('enroll_machine_agent', machine_id, label, allowed_provider_keys))
        return {'id': 'agent-1', 'agentToken': 'agent-token'}


def test_apply_stream_bootstrap_preserves_config_sections():
    data = {
        'peaq_os': {'enabled': True},
        'stream_agent': {
            'enabled': False,
            'topics': [
                {
                    'topic': '/battery',
                    'message_type': 'std_msgs/msg/String',
                    'qos_preset': 'reliable',
                }
            ],
        },
    }

    updated = bootstrap.apply_stream_bootstrap(
        data,
        api_base_url='https://api.example/',
        api_key='api-key',
        machine_id='machine-1',
        identity_ref='did:peaq:0x0000000000000000000000000000000000000001',
        agent_id='agent-1',
        agent_token='agent-token',
        storage_backend='s3',
        topics=[],
    )

    assert updated['peaq_os'] == {'enabled': True}
    assert updated['stream_agent']['enabled'] is True
    assert updated['stream_agent']['api_base_url'] == 'https://api.example'
    assert updated['stream_agent']['agent_id'] == 'agent-1'
    assert updated['stream_agent']['storage']['backend'] == 's3'
    assert updated['stream_agent']['topics'][0]['topic'] == '/battery'


def test_bootstrap_stream_agent_writes_private_runnable_config(tmp_path, monkeypatch):
    monkeypatch.setattr(bootstrap, 'StreamApiClient', _Client)
    source = tmp_path / 'source.yaml'
    output = tmp_path / 'seller.yaml'
    source.write_text(
        'stream_agent:\n'
        '  topics:\n'
        '    - topic: /battery\n'
        '      message_type: std_msgs/msg/String\n',
        encoding='utf8',
    )

    result = bootstrap.bootstrap_stream_agent(
        config_path=source,
        output_path=output,
        api_base_url='https://api.example',
        api_key='',
        machine_id='machine-1',
        label='Seller stream',
        storage_backend='local',
        topics=[],
        machine_recipient_key_path=tmp_path / 'machine-x25519.json',
        extra_key_recipients=[],
    )

    assert result['agentId'] == 'agent-1'
    assert output.exists()
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    key_payload = json.loads((tmp_path / 'machine-x25519.json').read_text(encoding='utf8'))
    assert stat.S_IMODE((tmp_path / 'machine-x25519.json').stat().st_mode) == 0o600
    assert key_payload['algorithm'] == 'x25519-sealedbox'
    assert len(key_payload['publicKeyHex']) == 64
    content = output.read_text(encoding='utf8')
    assert 'agent_token: agent-token' in content
    assert 'machine_id: machine-1' in content
    assert 'backend: local' in content
    assert 'recipient_type: machine' in content
    assert 'public_key_hex:' in content


def test_bootstrap_adds_owner_and_operator_recipients_without_replacing_existing(tmp_path, monkeypatch):
    monkeypatch.setattr(bootstrap, 'StreamApiClient', _Client)
    source = tmp_path / 'source.yaml'
    output = tmp_path / 'seller.yaml'
    source.write_text(
        'stream_agent:\n'
        '  topics:\n'
        '    - topic: /battery\n'
        '      message_type: std_msgs/msg/String\n'
        '  key_recipients:\n'
        '    - recipient_id: machine-existing\n'
        '      recipient_type: machine\n'
        f'      public_key_hex: {"11" * 32}\n',
        encoding='utf8',
    )

    bootstrap.bootstrap_stream_agent(
        config_path=source,
        output_path=output,
        api_base_url='https://api.example',
        api_key='',
        machine_id='machine-1',
        label='Seller stream',
        storage_backend='local',
        topics=[],
        machine_recipient_key_path=tmp_path / 'machine-x25519.json',
        extra_key_recipients=[
            {
                'recipient_id': 'owner-1',
                'recipient_type': 'owner',
                'public_key_hex': '22' * 32,
            },
            {
                'recipient_id': 'operator-1',
                'recipient_type': 'operator',
                'public_key_hex': '33' * 32,
            },
        ],
    )

    content = output.read_text(encoding='utf8')
    assert 'recipient_id: machine-existing' in content
    assert 'recipient_id: owner-1' in content
    assert 'recipient_id: operator-1' in content
    assert not (tmp_path / 'machine-x25519.json').exists()


def test_topic_items_require_matching_message_types():
    with pytest.raises(bootstrap.BootstrapError, match='same number'):
        bootstrap._topic_items(['/battery'], [])
