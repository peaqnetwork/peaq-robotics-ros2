"""Shared Stream agent data models."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any


FIELD_ACTIONS = {'include', 'exclude', 'encrypt', 'anonymize', 'hash'}
QOS_PRESETS = {'default', 'sensor_data', 'reliable'}
KEY_RECIPIENT_TYPES = {'machine', 'owner', 'operator'}


def _expand(path: str) -> str:
    return os.path.expanduser(path or '').strip()


@dataclass(frozen=True)
class FieldRule:
    path: str
    action: str = 'include'
    public_key_hex: str = ''

    def to_backend(self) -> dict[str, str]:
        item = {'path': self.path, 'action': self.action}
        if self.public_key_hex:
            item['publicKeyHex'] = self.public_key_hex
        return item


@dataclass(frozen=True)
class TopicRule:
    topic: str
    message_type: str
    qos_preset: str = 'default'
    depth: int | None = None
    field_rules: tuple[FieldRule, ...] = field(default_factory=tuple)

    def to_backend(self) -> dict[str, Any]:
        item: dict[str, Any] = {
            'topic': self.topic,
            'messageType': self.message_type,
            'qosPreset': self.qos_preset,
            'fieldRules': [rule.to_backend() for rule in self.field_rules],
        }
        if self.depth is not None:
            item['depth'] = self.depth
        return item


@dataclass(frozen=True)
class BufferConfig:
    path: str = '~/.peaq_robot/stream_buffer.sqlite3'
    max_events: int = 1000
    retention_seconds: int = 86400
    retry_interval_seconds: int = 30
    overflow: str = 'drop_oldest'

    @property
    def expanded_path(self) -> str:
        return _expand(self.path)

    def to_backend(self) -> dict[str, Any]:
        return {
            'maxEvents': self.max_events,
            'retentionSeconds': self.retention_seconds,
            'retryIntervalSeconds': self.retry_interval_seconds,
            'overflow': self.overflow,
        }


@dataclass(frozen=True)
class PayloadConfig:
    store_inline: bool = False
    inline_limit_bytes: int = 4096

    def to_backend(self) -> dict[str, Any]:
        return {
            'storeInline': self.store_inline,
            'inlineLimitBytes': self.inline_limit_bytes,
        }


@dataclass(frozen=True)
class PeaqosEventConfig:
    enabled: bool = False
    node_name: str = 'peaqos_node'
    machine_id: int = 0
    event_type: int = 1
    trust_level: int = 0
    source_chain_id: int = 0
    service_wait_sec: float = 2.0
    timeout_sec: float = 30.0


@dataclass(frozen=True)
class KeyRecipientConfig:
    recipient_id: str
    recipient_type: str
    public_key_hex: str

    def to_backend(self, wrapped_key_hex: str) -> dict[str, str]:
        return {
            'recipientId': self.recipient_id,
            'recipientType': self.recipient_type,
            'algorithm': 'x25519-sealedbox',
            'publicKeyHex': self.public_key_hex,
            'wrappedKeyHex': wrapped_key_hex,
        }


@dataclass(frozen=True)
class StreamAgentConfig:
    enabled: bool = False
    api_base_url: str = 'http://127.0.0.1:8000'
    api_key: str = ''
    machine_id: str = ''
    agent_id: str = ''
    agent_token: str = ''
    identity_ref: str = ''
    policy_name: str = 'ROS 2 Stream Policy'
    policy_path: str = ''
    signing_key_path: str = '~/.peaq_robot/stream_signing_key.json'
    sequence_state_path: str = '~/.peaq_robot/stream_sequences.json'
    chunk_storage_path: str = '~/.peaq_robot/stream_chunks'
    chunk_manifest_path: str = '~/.peaq_robot/stream_manifests/chunks.json'
    heartbeat_interval_seconds: int = 60
    topics: tuple[TopicRule, ...] = field(default_factory=tuple)
    destinations: tuple[str, ...] = ('backend',)
    buffer: BufferConfig = field(default_factory=BufferConfig)
    payload: PayloadConfig = field(default_factory=PayloadConfig)
    peaqos_event: PeaqosEventConfig = field(default_factory=PeaqosEventConfig)
    key_recipients: tuple[KeyRecipientConfig, ...] = field(default_factory=tuple)

    @property
    def expanded_signing_key_path(self) -> str:
        return _expand(self.signing_key_path)

    @property
    def expanded_sequence_state_path(self) -> str:
        return _expand(self.sequence_state_path)

    @property
    def expanded_chunk_storage_path(self) -> str:
        return _expand(self.chunk_storage_path)

    @property
    def expanded_chunk_manifest_path(self) -> str:
        return _expand(self.chunk_manifest_path)

    def policy_payload(self) -> dict[str, Any]:
        return {
            'name': self.policy_name,
            'status': 'active',
            'topicRules': [topic.to_backend() for topic in self.topics],
            'buffer': self.buffer.to_backend(),
            'payload': self.payload.to_backend(),
            'destinations': list(self.destinations),
        }
