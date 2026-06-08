from __future__ import annotations

import pytest

from peaq_ros2_stream.config import load_stream_agent_config_from_dict
from peaq_ros2_stream.qos import qos_spec_for_rule


def test_stream_agent_config_validates_topic_rules():
    cfg = load_stream_agent_config_from_dict(
        {
            'stream_agent': {
                'enabled': True,
                'api_base_url': 'http://127.0.0.1:8000',
                'machine_id': 'mach_1',
                'agent_id': 'agent_1',
                'agent_token': 'token',
                'identity_ref': 'peaqos:machine:mach_1',
                'chunk_storage_path': '/tmp/stream-chunks',
                'chunk_manifest_path': '/tmp/stream-manifests/chunks.json',
                'topics': [
                    {
                        'topic': '/battery',
                        'message_type': 'std_msgs/msg/String',
                        'qos_preset': 'sensor_data',
                        'depth': 7,
                        'field_rules': [
                            {'path': 'data', 'action': 'hash'},
                        ],
                    }
                ],
                'buffer': {
                    'max_events': 5,
                    'retention_seconds': 60,
                    'retry_interval_seconds': 2,
                    'overflow': 'drop_oldest',
                },
                'payload': {
                    'store_inline': False,
                    'inline_limit_bytes': 128,
                },
                'key_recipients': [
                    {
                        'recipient_id': 'owner-1',
                        'recipient_type': 'owner',
                        'public_key_hex': '11' * 32,
                    }
                ],
                'destinations': ['backend'],
            }
        }
    )

    assert cfg.enabled is True
    assert cfg.topics[0].topic == '/battery'
    assert cfg.topics[0].message_type == 'std_msgs/msg/String'
    assert cfg.topics[0].qos_preset == 'sensor_data'
    assert cfg.buffer.max_events == 5
    assert cfg.payload.inline_limit_bytes == 128
    assert cfg.chunk_storage_path == '/tmp/stream-chunks'
    assert cfg.chunk_manifest_path == '/tmp/stream-manifests/chunks.json'
    assert cfg.policy_payload()['topicRules'][0]['messageType'] == 'std_msgs/msg/String'
    assert cfg.key_recipients[0].recipient_id == 'owner-1'


def test_stream_agent_config_rejects_missing_message_type():
    with pytest.raises(ValueError, match='message_type'):
        load_stream_agent_config_from_dict(
            {
                'stream_agent': {
                    'enabled': True,
                    'machine_id': 'mach_1',
                    'agent_id': 'agent_1',
                    'agent_token': 'token',
                    'identity_ref': 'peaqos:machine:mach_1',
                    'topics': [{'topic': '/battery'}],
                }
            }
        )


def test_qos_preset_mapping():
    cfg = load_stream_agent_config_from_dict(
        {
            'stream_agent': {
                'topics': [
                    {'topic': '/scan', 'message_type': 'sensor_msgs/msg/LaserScan', 'qos_preset': 'sensor_data'},
                    {'topic': '/status', 'message_type': 'std_msgs/msg/String', 'qos_preset': 'reliable', 'depth': 12},
                ]
            }
        }
    )

    sensor = qos_spec_for_rule(cfg.topics[0])
    reliable = qos_spec_for_rule(cfg.topics[1])
    assert sensor.reliability == 'best_effort'
    assert sensor.depth == 5
    assert reliable.reliability == 'reliable'
    assert reliable.depth == 12
