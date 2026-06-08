"""Stream envelope assembly."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .config import StreamAgentConfig, TopicRule
from .transform import payload_hash, should_inline_payload


SCHEMA_VERSION = 'peaqos-stream-envelope@v1'


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def build_unsigned_envelope(
    cfg: StreamAgentConfig,
    rule: TopicRule,
    policy_id: str,
    policy_version: int,
    sequence_number: int,
    transformed_payload: Any,
    source_timestamp: str | None,
    agent_received_at: str,
    signed_at: str | None = None,
) -> dict[str, Any]:
    payload_ref = None
    payload = None
    if should_inline_payload(transformed_payload, cfg.payload.store_inline, cfg.payload.inline_limit_bytes):
        payload = transformed_payload
    else:
        payload_ref = 'hash-only'

    item = {
        'machineId': cfg.machine_id,
        'agentId': cfg.agent_id,
        'identityRef': cfg.identity_ref,
        'topic': rule.topic,
        'messageType': rule.message_type,
        'schemaVersion': SCHEMA_VERSION,
        'policyId': policy_id,
        'policyVersion': int(policy_version),
        'sequenceNumber': int(sequence_number),
        'timestamps': {
            'sourceTimestamp': source_timestamp,
            'agentReceivedAt': agent_received_at,
            'signedAt': signed_at or utc_now_iso(),
        },
        'payloadHash': payload_hash(transformed_payload),
        'payloadRef': payload_ref,
    }
    if payload is not None:
        item['payload'] = payload
    return item
