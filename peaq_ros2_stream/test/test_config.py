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
                'chunk_catalog_path': '/tmp/stream-catalog.sqlite3',
                'chunk_key_store_path': '/tmp/stream-chunk-keys.sqlite3',
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
                'storage': {
                    'backend': 'walrus',
                    'walrus': {
                        'publisher_url': 'https://publisher.example',
                        'aggregator_url': 'https://aggregator.example',
                        'publisher_token': 'token',
                        'epochs': 2,
                        'permanent': False,
                        'timeout_sec': 5,
                    },
                },
                'delivery': {
                    'enabled': True,
                    'host': '127.0.0.1',
                    'port': 9001,
                    'token': 'delivery-token',
                    'poll_interval_seconds': 4,
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
    assert cfg.chunk_catalog_path == '/tmp/stream-catalog.sqlite3'
    assert cfg.chunk_key_store_path == '/tmp/stream-chunk-keys.sqlite3'
    assert cfg.storage.backend == 'walrus'
    assert cfg.storage.walrus.publisher_url == 'https://publisher.example'
    assert cfg.storage.walrus.aggregator_url == 'https://aggregator.example'
    assert cfg.storage.walrus.epochs == 2
    assert cfg.storage.walrus.permanent is False
    assert cfg.delivery.enabled is True
    assert cfg.delivery.port == 9001
    assert cfg.delivery.poll_interval_seconds == 4
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


def test_stream_agent_config_rejects_delivery_without_token():
    with pytest.raises(ValueError, match='delivery requires token'):
        load_stream_agent_config_from_dict(
            {
                'stream_agent': {
                    'delivery': {'enabled': True},
                }
            }
        )


def test_stream_agent_config_rejects_enabled_without_key_recipient():
    with pytest.raises(ValueError, match='key_recipient'):
        load_stream_agent_config_from_dict(
            {
                'stream_agent': {
                    'enabled': True,
                    'machine_id': 'mach_1',
                    'agent_id': 'agent_1',
                    'agent_token': 'token',
                    'identity_ref': 'peaqos:machine:mach_1',
                    'topics': [{'topic': '/battery', 'message_type': 'std_msgs/msg/String'}],
                }
            }
        )


def test_stream_agent_config_loads_s3_storage():
    cfg = load_stream_agent_config_from_dict(
        {
            'stream_agent': {
                'storage': {
                    'backend': 's3',
                    's3': {
                        'bucket': 'stream-bucket',
                        'prefix': 'machine-1/chunks',
                        'endpoint_url': 'https://s3.example',
                        'region': 'eu-central-1',
                        'access_key_id': 'access-key',
                        'secret_access_key': 'secret-key',
                        'session_token': 'session-token',
                    },
                },
            }
        }
    )

    assert cfg.storage.backend == 's3'
    assert cfg.storage.s3.bucket == 'stream-bucket'
    assert cfg.storage.s3.prefix == 'machine-1/chunks'
    assert cfg.storage.s3.endpoint_url == 'https://s3.example'
    assert cfg.storage.s3.region == 'eu-central-1'
    assert cfg.storage.s3.access_key_id == 'access-key'
    assert cfg.storage.s3.secret_access_key == 'secret-key'
    assert cfg.storage.s3.session_token == 'session-token'


def test_stream_agent_config_loads_google_drive_storage():
    cfg = load_stream_agent_config_from_dict(
        {
            'stream_agent': {
                'storage': {
                    'backend': 'google-drive',
                    'google_drive': {
                        'folder_id': 'folder-1',
                        'credentials_path': '/tmp/drive-credentials.json',
                    },
                },
            }
        }
    )

    assert cfg.storage.backend == 'google-drive'
    assert cfg.storage.google_drive.folder_id == 'folder-1'
    assert cfg.storage.google_drive.credentials_path == '/tmp/drive-credentials.json'


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
