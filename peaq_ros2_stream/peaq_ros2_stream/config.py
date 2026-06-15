"""Configuration loading for the peaqOS Stream agent."""

from __future__ import annotations

import os
from typing import Any, Mapping

from .models import (
    FIELD_ACTIONS,
    GoogleDriveStorageConfig,
    KEY_RECIPIENT_TYPES,
    QOS_PRESETS,
    STORAGE_BACKENDS,
    BufferConfig,
    DeliveryConfig,
    FieldRule,
    KeyRecipientConfig,
    PayloadConfig,
    PeaqosEventConfig,
    S3StorageConfig,
    StorageConfig,
    StreamAgentConfig,
    TopicRule,
    WalrusStorageConfig,
)

try:
    import yaml  # type: ignore

    _HAS_YAML = True
except Exception:
    _HAS_YAML = False


def _expand(path: str) -> str:
    return os.path.expanduser(path or '').strip()


def _as_bool(value: Any, current: bool) -> bool:
    if value is None:
        return current
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {'1', 'true', 'yes', 'on'}


def _as_int(value: Any, current: int) -> int:
    if value is None or value == '':
        return current
    try:
        return int(value)
    except Exception:
        return current


def _as_float(value: Any, current: float) -> float:
    if value is None or value == '':
        return current
    try:
        return float(value)
    except Exception:
        return current


def _as_str(value: Any, current: str) -> str:
    if value is None:
        return current
    text = str(value).strip()
    return text if text else current


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        items = value
    else:
        items = str(value).replace(';', ',').split(',')
    return [str(item).strip() for item in items if str(item).strip()]


def _parse_field_rule(raw: Mapping[str, Any]) -> FieldRule:
    path = _as_str(raw.get('path'), '')
    action = _as_str(raw.get('action'), 'include')
    if not path:
        raise ValueError('field rule path is required')
    if action not in FIELD_ACTIONS:
        raise ValueError(f'field rule action must be one of {sorted(FIELD_ACTIONS)}')
    public_key_hex = _as_str(raw.get('public_key_hex') or raw.get('publicKeyHex'), '')
    return FieldRule(path=path, action=action, public_key_hex=public_key_hex)


def _parse_topic_rule(raw: Mapping[str, Any]) -> TopicRule:
    topic = _as_str(raw.get('topic'), '')
    message_type = _as_str(raw.get('message_type') or raw.get('messageType'), '')
    qos_preset = _as_str(raw.get('qos_preset') or raw.get('qosPreset'), 'default')
    if not topic:
        raise ValueError('stream topic rule requires topic')
    if not message_type:
        raise ValueError('stream topic rule requires message_type')
    if qos_preset not in QOS_PRESETS:
        raise ValueError(f'qos_preset must be one of {sorted(QOS_PRESETS)}')
    depth_value = raw.get('depth')
    depth = None if depth_value in (None, '') else max(1, int(depth_value))
    field_rules = tuple(_parse_field_rule(item) for item in raw.get('field_rules', raw.get('fieldRules', [])) or [])
    return TopicRule(
        topic=topic,
        message_type=message_type,
        qos_preset=qos_preset,
        depth=depth,
        field_rules=field_rules,
    )


def _parse_key_recipient(raw: Mapping[str, Any]) -> KeyRecipientConfig:
    recipient_id = _as_str(raw.get('recipient_id') or raw.get('recipientId'), '')
    recipient_type = _as_str(raw.get('recipient_type') or raw.get('recipientType'), 'owner')
    public_key_hex = _as_str(raw.get('public_key_hex') or raw.get('publicKeyHex'), '').removeprefix('0x').lower()
    if not recipient_id:
        raise ValueError('key recipient requires recipient_id')
    if recipient_type not in KEY_RECIPIENT_TYPES:
        raise ValueError(f'key recipient type must be one of {sorted(KEY_RECIPIENT_TYPES)}')
    if len(public_key_hex) != 64 or any(char not in '0123456789abcdef' for char in public_key_hex):
        raise ValueError('key recipient public_key_hex must be a 32-byte hex string')
    return KeyRecipientConfig(recipient_id=recipient_id, recipient_type=recipient_type, public_key_hex=public_key_hex)


def _merge_stream_data(cfg: dict[str, Any], data: Mapping[str, Any]) -> None:
    stream = data.get('stream_agent', data.get('stream', {})) or {}
    if not isinstance(stream, Mapping):
        return

    cfg['enabled'] = _as_bool(stream.get('enabled'), cfg['enabled'])
    cfg['api_base_url'] = _as_str(stream.get('api_base_url') or stream.get('apiBaseUrl'), cfg['api_base_url'])
    cfg['api_key'] = _as_str(stream.get('api_key') or stream.get('apiKey'), cfg['api_key'])
    cfg['machine_id'] = _as_str(stream.get('machine_id') or stream.get('machineId'), cfg['machine_id'])
    cfg['agent_id'] = _as_str(stream.get('agent_id') or stream.get('agentId'), cfg['agent_id'])
    cfg['agent_token'] = _as_str(stream.get('agent_token') or stream.get('agentToken'), cfg['agent_token'])
    cfg['identity_ref'] = _as_str(stream.get('identity_ref') or stream.get('identityRef'), cfg['identity_ref'])
    cfg['policy_name'] = _as_str(stream.get('policy_name') or stream.get('policyName'), cfg['policy_name'])
    cfg['policy_path'] = _as_str(stream.get('policy_path') or stream.get('policyPath'), cfg['policy_path'])
    cfg['signing_key_path'] = _as_str(
        stream.get('signing_key_path') or stream.get('signingKeyPath'),
        cfg['signing_key_path'],
    )
    cfg['sequence_state_path'] = _as_str(
        stream.get('sequence_state_path') or stream.get('sequenceStatePath'),
        cfg['sequence_state_path'],
    )
    cfg['chunk_storage_path'] = _as_str(
        stream.get('chunk_storage_path') or stream.get('chunkStoragePath'),
        cfg['chunk_storage_path'],
    )
    cfg['chunk_manifest_path'] = _as_str(
        stream.get('chunk_manifest_path') or stream.get('chunkManifestPath'),
        cfg['chunk_manifest_path'],
    )
    cfg['chunk_catalog_path'] = _as_str(
        stream.get('chunk_catalog_path') or stream.get('chunkCatalogPath'),
        cfg['chunk_catalog_path'],
    )
    cfg['chunk_key_store_path'] = _as_str(
        stream.get('chunk_key_store_path') or stream.get('chunkKeyStorePath'),
        cfg['chunk_key_store_path'],
    )
    cfg['heartbeat_interval_seconds'] = max(
        5,
        _as_int(
            stream.get('heartbeat_interval_seconds') or stream.get('heartbeatIntervalSeconds'),
            cfg['heartbeat_interval_seconds'],
        ),
    )

    topics = stream.get('topics') or stream.get('topic_rules') or stream.get('topicRules')
    if isinstance(topics, list):
        cfg['topics'] = topics

    destinations = stream.get('destinations')
    if destinations is not None:
        cfg['destinations'] = _as_list(destinations)

    recipients = stream.get('key_recipients') or stream.get('keyRecipients') or []
    if isinstance(recipients, list):
        cfg['key_recipients'] = recipients

    buffer_data = stream.get('buffer', {}) or {}
    if isinstance(buffer_data, Mapping):
        cfg['buffer']['path'] = _as_str(buffer_data.get('path'), cfg['buffer']['path'])
        cfg['buffer']['max_events'] = max(
            1,
            _as_int(buffer_data.get('max_events') or buffer_data.get('maxEvents'), cfg['buffer']['max_events']),
        )
        cfg['buffer']['retention_seconds'] = max(
            0,
            _as_int(
                buffer_data.get('retention_seconds') or buffer_data.get('retentionSeconds'),
                cfg['buffer']['retention_seconds'],
            ),
        )
        cfg['buffer']['retry_interval_seconds'] = max(
            1,
            _as_int(
                buffer_data.get('retry_interval_seconds') or buffer_data.get('retryIntervalSeconds'),
                cfg['buffer']['retry_interval_seconds'],
            ),
        )
        overflow = _as_str(buffer_data.get('overflow'), cfg['buffer']['overflow'])
        cfg['buffer']['overflow'] = 'pause' if overflow == 'pause' else 'drop_oldest'

    payload_data = stream.get('payload', {}) or {}
    if isinstance(payload_data, Mapping):
        cfg['payload']['store_inline'] = _as_bool(
            payload_data.get('store_inline') if 'store_inline' in payload_data else payload_data.get('storeInline'),
            cfg['payload']['store_inline'],
        )
        cfg['payload']['inline_limit_bytes'] = max(
            0,
            _as_int(
                payload_data.get('inline_limit_bytes') or payload_data.get('inlineLimitBytes'),
                cfg['payload']['inline_limit_bytes'],
            ),
        )

    event_data = stream.get('peaqos_event') or stream.get('peaqosEvent') or {}
    if isinstance(event_data, Mapping):
        cfg['peaqos_event']['enabled'] = _as_bool(event_data.get('enabled'), cfg['peaqos_event']['enabled'])
        cfg['peaqos_event']['node_name'] = _as_str(
            event_data.get('node_name') or event_data.get('nodeName'),
            cfg['peaqos_event']['node_name'],
        )
        for key in ('machine_id', 'event_type', 'trust_level', 'source_chain_id'):
            camel = ''.join([key.split('_')[0], *[part.capitalize() for part in key.split('_')[1:]]])
            cfg['peaqos_event'][key] = _as_int(event_data.get(key) or event_data.get(camel), cfg['peaqos_event'][key])

    storage_data = stream.get('storage', {}) or {}
    if isinstance(storage_data, Mapping):
        backend = _as_str(storage_data.get('backend'), cfg['storage']['backend']).lower()
        cfg['storage']['backend'] = backend if backend in STORAGE_BACKENDS else cfg['storage']['backend']
        walrus_data = storage_data.get('walrus', {}) or {}
        if isinstance(walrus_data, Mapping):
            cfg['storage']['walrus']['publisher_url'] = _as_str(
                walrus_data.get('publisher_url') or walrus_data.get('publisherUrl'),
                cfg['storage']['walrus']['publisher_url'],
            )
            cfg['storage']['walrus']['aggregator_url'] = _as_str(
                walrus_data.get('aggregator_url') or walrus_data.get('aggregatorUrl'),
                cfg['storage']['walrus']['aggregator_url'],
            )
            cfg['storage']['walrus']['publisher_token'] = _as_str(
                walrus_data.get('publisher_token') or walrus_data.get('publisherToken'),
                cfg['storage']['walrus']['publisher_token'],
            )
            cfg['storage']['walrus']['epochs'] = max(
                1,
                _as_int(walrus_data.get('epochs'), cfg['storage']['walrus']['epochs']),
            )
            cfg['storage']['walrus']['permanent'] = _as_bool(
                walrus_data.get('permanent'),
                cfg['storage']['walrus']['permanent'],
            )
            cfg['storage']['walrus']['timeout_sec'] = max(
                1.0,
                _as_float(
                    walrus_data.get('timeout_sec') or walrus_data.get('timeoutSec'),
                    cfg['storage']['walrus']['timeout_sec'],
                ),
            )
        s3_data = storage_data.get('s3', {}) or {}
        if isinstance(s3_data, Mapping):
            cfg['storage']['s3']['bucket'] = _as_str(s3_data.get('bucket'), cfg['storage']['s3']['bucket'])
            cfg['storage']['s3']['prefix'] = _as_str(s3_data.get('prefix'), cfg['storage']['s3']['prefix'])
            cfg['storage']['s3']['endpoint_url'] = _as_str(
                s3_data.get('endpoint_url') or s3_data.get('endpointUrl'),
                cfg['storage']['s3']['endpoint_url'],
            )
            cfg['storage']['s3']['region'] = _as_str(
                s3_data.get('region') or s3_data.get('region_name') or s3_data.get('regionName'),
                cfg['storage']['s3']['region'],
            )
            cfg['storage']['s3']['access_key_id'] = _as_str(
                s3_data.get('access_key_id') or s3_data.get('accessKeyId'),
                cfg['storage']['s3']['access_key_id'],
            )
            cfg['storage']['s3']['secret_access_key'] = _as_str(
                s3_data.get('secret_access_key') or s3_data.get('secretAccessKey'),
                cfg['storage']['s3']['secret_access_key'],
            )
            cfg['storage']['s3']['session_token'] = _as_str(
                s3_data.get('session_token') or s3_data.get('sessionToken'),
                cfg['storage']['s3']['session_token'],
            )
        drive_data = storage_data.get('google_drive') or storage_data.get('googleDrive') or storage_data.get('google-drive') or {}
        if isinstance(drive_data, Mapping):
            cfg['storage']['google_drive']['folder_id'] = _as_str(
                drive_data.get('folder_id') or drive_data.get('folderId'),
                cfg['storage']['google_drive']['folder_id'],
            )
            cfg['storage']['google_drive']['credentials_path'] = _as_str(
                drive_data.get('credentials_path') or drive_data.get('credentialsPath'),
                cfg['storage']['google_drive']['credentials_path'],
            )

    delivery_data = stream.get('delivery', {}) or {}
    if isinstance(delivery_data, Mapping):
        cfg['delivery']['enabled'] = _as_bool(delivery_data.get('enabled'), cfg['delivery']['enabled'])
        cfg['delivery']['host'] = _as_str(delivery_data.get('host'), cfg['delivery']['host'])
        cfg['delivery']['port'] = max(1, _as_int(delivery_data.get('port'), cfg['delivery']['port']))
        cfg['delivery']['token'] = _as_str(delivery_data.get('token'), cfg['delivery']['token'])
        cfg['delivery']['poll_interval_seconds'] = max(
            1,
            _as_int(
                delivery_data.get('poll_interval_seconds') or delivery_data.get('pollIntervalSeconds'),
                cfg['delivery']['poll_interval_seconds'],
            ),
        )

def _apply_policy_file(cfg: dict[str, Any]) -> None:
    policy_path = cfg.get('policy_path', '')
    if not policy_path:
        return
    if not _HAS_YAML:
        raise RuntimeError('PyYAML is required to load stream_agent.policy_path')
    with open(_expand(policy_path), 'r', encoding='utf8') as handle:
        raw = yaml.safe_load(handle) or {}
    if not isinstance(raw, Mapping):
        raise ValueError('stream policy file must contain a mapping')
    policy = raw.get('stream_policy', raw)
    if not isinstance(policy, Mapping):
        raise ValueError('stream policy file must contain stream_policy mapping')
    _merge_stream_data(cfg, {'stream_agent': policy})


def _apply_env(cfg: dict[str, Any]) -> None:
    cfg['enabled'] = _as_bool(os.getenv('PEAQOS_STREAM_ENABLED'), cfg['enabled'])
    cfg['api_base_url'] = _as_str(os.getenv('PEAQOS_STREAM_API_BASE_URL'), cfg['api_base_url'])
    cfg['api_key'] = _as_str(os.getenv('PEAQOS_STREAM_API_KEY'), cfg['api_key'])
    cfg['machine_id'] = _as_str(os.getenv('PEAQOS_STREAM_MACHINE_ID'), cfg['machine_id'])
    cfg['agent_id'] = _as_str(os.getenv('PEAQOS_STREAM_AGENT_ID'), cfg['agent_id'])
    cfg['agent_token'] = _as_str(os.getenv('PEAQOS_STREAM_AGENT_TOKEN'), cfg['agent_token'])
    cfg['identity_ref'] = _as_str(os.getenv('PEAQOS_STREAM_IDENTITY_REF'), cfg['identity_ref'])
    cfg['policy_path'] = _as_str(os.getenv('PEAQOS_STREAM_POLICY_PATH'), cfg['policy_path'])
    cfg['signing_key_path'] = _as_str(os.getenv('PEAQOS_STREAM_SIGNING_KEY_PATH'), cfg['signing_key_path'])
    cfg['chunk_storage_path'] = _as_str(os.getenv('PEAQOS_STREAM_CHUNK_STORAGE_PATH'), cfg['chunk_storage_path'])
    cfg['chunk_manifest_path'] = _as_str(os.getenv('PEAQOS_STREAM_CHUNK_MANIFEST_PATH'), cfg['chunk_manifest_path'])
    cfg['chunk_catalog_path'] = _as_str(os.getenv('PEAQOS_STREAM_CHUNK_CATALOG_PATH'), cfg['chunk_catalog_path'])
    cfg['chunk_key_store_path'] = _as_str(os.getenv('PEAQOS_STREAM_CHUNK_KEY_STORE_PATH'), cfg['chunk_key_store_path'])
    cfg['buffer']['path'] = _as_str(os.getenv('PEAQOS_STREAM_BUFFER_PATH'), cfg['buffer']['path'])
    storage_backend = _as_str(os.getenv('PEAQOS_STREAM_STORAGE_BACKEND'), cfg['storage']['backend']).lower()
    cfg['storage']['backend'] = storage_backend if storage_backend in STORAGE_BACKENDS else cfg['storage']['backend']
    cfg['storage']['walrus']['publisher_url'] = _as_str(
        os.getenv('PEAQOS_STREAM_WALRUS_PUBLISHER_URL') or os.getenv('WALRUS_PUBLISHER_URL'),
        cfg['storage']['walrus']['publisher_url'],
    )
    cfg['storage']['walrus']['aggregator_url'] = _as_str(
        os.getenv('PEAQOS_STREAM_WALRUS_AGGREGATOR_URL') or os.getenv('WALRUS_AGGREGATOR_URL'),
        cfg['storage']['walrus']['aggregator_url'],
    )
    cfg['storage']['walrus']['publisher_token'] = _as_str(
        os.getenv('PEAQOS_STREAM_WALRUS_PUBLISHER_TOKEN') or os.getenv('WALRUS_PUBLISHER_TOKEN'),
        cfg['storage']['walrus']['publisher_token'],
    )
    cfg['storage']['walrus']['epochs'] = max(
        1,
        _as_int(os.getenv('PEAQOS_STREAM_WALRUS_EPOCHS'), cfg['storage']['walrus']['epochs']),
    )
    cfg['storage']['walrus']['permanent'] = _as_bool(
        os.getenv('PEAQOS_STREAM_WALRUS_PERMANENT'),
        cfg['storage']['walrus']['permanent'],
    )
    cfg['storage']['walrus']['timeout_sec'] = max(
        1.0,
        _as_float(os.getenv('PEAQOS_STREAM_WALRUS_TIMEOUT_SEC'), cfg['storage']['walrus']['timeout_sec']),
    )
    cfg['storage']['s3']['bucket'] = _as_str(
        os.getenv('PEAQOS_STREAM_S3_BUCKET') or os.getenv('AWS_S3_BUCKET'),
        cfg['storage']['s3']['bucket'],
    )
    cfg['storage']['s3']['prefix'] = _as_str(
        os.getenv('PEAQOS_STREAM_S3_PREFIX'),
        cfg['storage']['s3']['prefix'],
    )
    cfg['storage']['s3']['endpoint_url'] = _as_str(
        os.getenv('PEAQOS_STREAM_S3_ENDPOINT_URL') or os.getenv('AWS_ENDPOINT_URL_S3') or os.getenv('AWS_ENDPOINT_URL'),
        cfg['storage']['s3']['endpoint_url'],
    )
    cfg['storage']['s3']['region'] = _as_str(
        os.getenv('PEAQOS_STREAM_S3_REGION') or os.getenv('AWS_REGION') or os.getenv('AWS_DEFAULT_REGION'),
        cfg['storage']['s3']['region'],
    )
    cfg['storage']['s3']['access_key_id'] = _as_str(
        os.getenv('PEAQOS_STREAM_S3_ACCESS_KEY_ID') or os.getenv('AWS_ACCESS_KEY_ID'),
        cfg['storage']['s3']['access_key_id'],
    )
    cfg['storage']['s3']['secret_access_key'] = _as_str(
        os.getenv('PEAQOS_STREAM_S3_SECRET_ACCESS_KEY') or os.getenv('AWS_SECRET_ACCESS_KEY'),
        cfg['storage']['s3']['secret_access_key'],
    )
    cfg['storage']['s3']['session_token'] = _as_str(
        os.getenv('PEAQOS_STREAM_S3_SESSION_TOKEN') or os.getenv('AWS_SESSION_TOKEN'),
        cfg['storage']['s3']['session_token'],
    )
    cfg['storage']['google_drive']['folder_id'] = _as_str(
        os.getenv('PEAQOS_STREAM_GOOGLE_DRIVE_FOLDER_ID') or os.getenv('GOOGLE_DRIVE_FOLDER_ID'),
        cfg['storage']['google_drive']['folder_id'],
    )
    cfg['storage']['google_drive']['credentials_path'] = _as_str(
        os.getenv('PEAQOS_STREAM_GOOGLE_DRIVE_CREDENTIALS_PATH') or os.getenv('GOOGLE_APPLICATION_CREDENTIALS'),
        cfg['storage']['google_drive']['credentials_path'],
    )
    cfg['delivery']['enabled'] = _as_bool(os.getenv('PEAQOS_STREAM_DELIVERY_ENABLED'), cfg['delivery']['enabled'])
    cfg['delivery']['host'] = _as_str(os.getenv('PEAQOS_STREAM_DELIVERY_HOST'), cfg['delivery']['host'])
    cfg['delivery']['port'] = max(
        1,
        _as_int(os.getenv('PEAQOS_STREAM_DELIVERY_PORT'), cfg['delivery']['port']),
    )
    cfg['delivery']['token'] = _as_str(os.getenv('PEAQOS_STREAM_DELIVERY_TOKEN'), cfg['delivery']['token'])
    cfg['delivery']['poll_interval_seconds'] = max(
        1,
        _as_int(os.getenv('PEAQOS_STREAM_DELIVERY_POLL_INTERVAL_SECONDS'), cfg['delivery']['poll_interval_seconds']),
    )
    owner_id = _as_str(os.getenv('PEAQOS_STREAM_OWNER_ID'), '')
    owner_public_key_hex = _as_str(os.getenv('PEAQOS_STREAM_OWNER_PUBLIC_KEY_HEX'), '').removeprefix('0x').lower()
    if owner_id and owner_public_key_hex:
        cfg['key_recipients'] = [
            *cfg['key_recipients'],
            {
                'recipient_id': owner_id,
                'recipient_type': 'owner',
                'public_key_hex': owner_public_key_hex,
            },
        ]
def _apply_params(cfg: dict[str, Any], params: Mapping[str, Any]) -> None:
    mapping = {
        'stream_agent.enabled': ('enabled', _as_bool),
        'stream_agent.api_base_url': ('api_base_url', _as_str),
        'stream_agent.api_key': ('api_key', _as_str),
        'stream_agent.machine_id': ('machine_id', _as_str),
        'stream_agent.agent_id': ('agent_id', _as_str),
        'stream_agent.agent_token': ('agent_token', _as_str),
        'stream_agent.identity_ref': ('identity_ref', _as_str),
        'stream_agent.policy_path': ('policy_path', _as_str),
        'stream_agent.signing_key_path': ('signing_key_path', _as_str),
        'stream_agent.sequence_state_path': ('sequence_state_path', _as_str),
        'stream_agent.chunk_storage_path': ('chunk_storage_path', _as_str),
        'stream_agent.chunk_manifest_path': ('chunk_manifest_path', _as_str),
        'stream_agent.chunk_catalog_path': ('chunk_catalog_path', _as_str),
        'stream_agent.chunk_key_store_path': ('chunk_key_store_path', _as_str),
        'stream_agent.storage_backend': ('storage.backend', _as_str),
        'stream_agent.s3_bucket': ('storage.s3.bucket', _as_str),
        'stream_agent.s3_prefix': ('storage.s3.prefix', _as_str),
        'stream_agent.s3_endpoint_url': ('storage.s3.endpoint_url', _as_str),
        'stream_agent.s3_region': ('storage.s3.region', _as_str),
        'stream_agent.google_drive_folder_id': ('storage.google_drive.folder_id', _as_str),
        'stream_agent.google_drive_credentials_path': ('storage.google_drive.credentials_path', _as_str),
        'stream_agent.delivery_enabled': ('delivery.enabled', _as_bool),
        'stream_agent.delivery_host': ('delivery.host', _as_str),
        'stream_agent.delivery_port': ('delivery.port', _as_int),
        'stream_agent.delivery_token': ('delivery.token', _as_str),
        'stream_agent.delivery_poll_interval_seconds': ('delivery.poll_interval_seconds', _as_int),
    }
    for param_key, (cfg_key, caster) in mapping.items():
        if param_key in params:
            if '.' in cfg_key:
                keys = cfg_key.split('.')
                target = cfg
                for key in keys[:-1]:
                    target = target[key]
                target[keys[-1]] = caster(params[param_key], target[keys[-1]])
            else:
                cfg[cfg_key] = caster(params[param_key], cfg[cfg_key])
    backend = str(cfg['storage']['backend']).strip().lower()
    cfg['storage']['backend'] = backend if backend in STORAGE_BACKENDS else 'local'


def _default_config_dict() -> dict[str, Any]:
    return {
        'enabled': False,
        'api_base_url': 'http://127.0.0.1:8000',
        'api_key': '',
        'machine_id': '',
        'agent_id': '',
        'agent_token': '',
        'identity_ref': '',
        'policy_name': 'ROS 2 Stream Policy',
        'policy_path': '',
        'signing_key_path': '~/.peaq_robot/stream_signing_key.json',
        'sequence_state_path': '~/.peaq_robot/stream_sequences.json',
        'chunk_storage_path': '~/.peaq_robot/stream_chunks',
        'chunk_manifest_path': '~/.peaq_robot/stream_manifests/chunks.json',
        'chunk_catalog_path': '~/.peaq_robot/stream_catalog.sqlite3',
        'chunk_key_store_path': '~/.peaq_robot/stream_chunk_keys.sqlite3',
        'heartbeat_interval_seconds': 60,
        'topics': [],
        'destinations': ['backend'],
        'key_recipients': [],
        'buffer': {
            'path': '~/.peaq_robot/stream_buffer.sqlite3',
            'max_events': 1000,
            'retention_seconds': 86400,
            'retry_interval_seconds': 30,
            'overflow': 'drop_oldest',
        },
        'payload': {
            'store_inline': False,
            'inline_limit_bytes': 4096,
        },
        'peaqos_event': {
            'enabled': False,
            'node_name': 'peaqos_node',
            'machine_id': 0,
            'event_type': 1,
            'trust_level': 0,
            'source_chain_id': 0,
            'service_wait_sec': 2.0,
            'timeout_sec': 30.0,
        },
        'storage': {
            'backend': 'local',
            'walrus': {
                'publisher_url': '',
                'aggregator_url': '',
                'publisher_token': '',
                'epochs': 5,
                'permanent': True,
                'timeout_sec': 30.0,
            },
            's3': {
                'bucket': '',
                'prefix': 'peaq-stream',
                'endpoint_url': '',
                'region': '',
                'access_key_id': '',
                'secret_access_key': '',
                'session_token': '',
            },
            'google_drive': {
                'folder_id': '',
                'credentials_path': '',
            },
        },
        'delivery': {
            'enabled': False,
            'host': '127.0.0.1',
            'port': 8765,
            'token': '',
            'poll_interval_seconds': 15,
        },
    }


def _build_config(cfg: dict[str, Any]) -> StreamAgentConfig:
    topics = tuple(_parse_topic_rule(item) for item in cfg['topics'])
    key_recipients = tuple(_parse_key_recipient(item) for item in cfg['key_recipients'])
    if cfg['enabled']:
        missing = [
            name
            for name in ('machine_id', 'agent_id', 'agent_token', 'identity_ref')
            if not str(cfg.get(name, '')).strip()
        ]
        if missing:
            raise ValueError(f'stream_agent missing required fields: {", ".join(missing)}')
        if not topics:
            raise ValueError('stream_agent requires at least one topic when enabled')
        if not key_recipients:
            raise ValueError('stream_agent requires at least one key_recipient when enabled')
    if cfg['delivery']['enabled'] and not str(cfg['delivery']['token']).strip():
        raise ValueError('stream_agent delivery requires token when enabled')

    return StreamAgentConfig(
        enabled=bool(cfg['enabled']),
        api_base_url=str(cfg['api_base_url']).rstrip('/'),
        api_key=str(cfg['api_key']),
        machine_id=str(cfg['machine_id']),
        agent_id=str(cfg['agent_id']),
        agent_token=str(cfg['agent_token']),
        identity_ref=str(cfg['identity_ref']),
        policy_name=str(cfg['policy_name']),
        policy_path=str(cfg['policy_path']),
        signing_key_path=str(cfg['signing_key_path']),
        sequence_state_path=str(cfg['sequence_state_path']),
        chunk_storage_path=str(cfg['chunk_storage_path']),
        chunk_manifest_path=str(cfg['chunk_manifest_path']),
        chunk_catalog_path=str(cfg['chunk_catalog_path']),
        chunk_key_store_path=str(cfg['chunk_key_store_path']),
        heartbeat_interval_seconds=int(cfg['heartbeat_interval_seconds']),
        topics=topics,
        destinations=tuple(_as_list(cfg['destinations']) or ['backend']),
        buffer=BufferConfig(**cfg['buffer']),
        payload=PayloadConfig(**cfg['payload']),
        peaqos_event=PeaqosEventConfig(**cfg['peaqos_event']),
        storage=StorageConfig(
            backend=str(cfg['storage']['backend']),
            walrus=WalrusStorageConfig(**cfg['storage']['walrus']),
            s3=S3StorageConfig(**cfg['storage']['s3']),
            google_drive=GoogleDriveStorageConfig(**cfg['storage']['google_drive']),
        ),
        delivery=DeliveryConfig(**cfg['delivery']),
        key_recipients=key_recipients,
    )


def load_stream_agent_config_from_dict(data: Mapping[str, Any]) -> StreamAgentConfig:
    cfg = _default_config_dict()
    _merge_stream_data(cfg, data)
    _apply_policy_file(cfg)
    return _build_config(cfg)


def load_stream_agent_config_from_params(params: Mapping[str, Any]) -> StreamAgentConfig:
    cfg = _default_config_dict()
    yaml_path = str(params.get('config.yaml_path') or os.getenv('PEAQ_ROS2_CONFIG_YAML', '')).strip()
    if yaml_path:
        if not _HAS_YAML:
            raise RuntimeError('PyYAML is required to load config.yaml_path for peaq_ros2_stream')
        with open(_expand(yaml_path), 'r', encoding='utf8') as handle:
            _merge_stream_data(cfg, yaml.safe_load(handle) or {})
    _apply_env(cfg)
    _apply_params(cfg, params)
    _apply_policy_file(cfg)
    return _build_config(cfg)
