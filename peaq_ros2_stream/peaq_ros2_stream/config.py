"""Configuration loading for the peaqOS Stream agent."""

from __future__ import annotations

import os
from typing import Any, Mapping

from .models import (
    FIELD_ACTIONS,
    KEY_RECIPIENT_TYPES,
    QOS_PRESETS,
    BufferConfig,
    FieldRule,
    KeyRecipientConfig,
    PayloadConfig,
    PeaqosEventConfig,
    StreamAgentConfig,
    TopicRule,
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
    cfg['buffer']['path'] = _as_str(os.getenv('PEAQOS_STREAM_BUFFER_PATH'), cfg['buffer']['path'])
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
    }
    for param_key, (cfg_key, caster) in mapping.items():
        if param_key in params:
            if '.' in cfg_key:
                section, key = cfg_key.split('.', 1)
                cfg[section][key] = caster(params[param_key], cfg[section][key])
            else:
                cfg[cfg_key] = caster(params[param_key], cfg[cfg_key])


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
        heartbeat_interval_seconds=int(cfg['heartbeat_interval_seconds']),
        topics=topics,
        destinations=tuple(_as_list(cfg['destinations']) or ['backend']),
        buffer=BufferConfig(**cfg['buffer']),
        payload=PayloadConfig(**cfg['payload']),
        peaqos_event=PeaqosEventConfig(**cfg['peaqos_event']),
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
