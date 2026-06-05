"""Canonical message conversion and Stream field rules."""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import is_dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

try:
    from nacl.public import PublicKey, SealedBox  # type: ignore

    _HAS_NACL_PUBLIC = True
except Exception:
    _HAS_NACL_PUBLIC = False

from .config import FieldRule


def stable_json(value: Any) -> str:
    if value is None or not isinstance(value, (dict, list, tuple)):
        return json.dumps(value, separators=(',', ':'), ensure_ascii=False)
    if isinstance(value, (list, tuple)):
        return '[' + ','.join(stable_json(item) for item in value) + ']'
    return (
        '{'
        + ','.join(
            f'{json.dumps(str(key), separators=(",", ":"), ensure_ascii=False)}:{stable_json(item)}'
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        )
        + '}'
    )


def payload_hash(payload: Any) -> str:
    return 'sha256:' + hashlib.sha256(stable_json(payload).encode('utf8')).hexdigest()


def canonical_message_dict(message: Any) -> Any:
    if message is None or isinstance(message, (str, int, float, bool)):
        return message
    if isinstance(message, bytes):
        return list(message)
    if isinstance(message, (list, tuple)):
        return [canonical_message_dict(item) for item in message]
    if isinstance(message, Mapping):
        return {str(key): canonical_message_dict(value) for key, value in message.items()}
    if is_dataclass(message):
        return canonical_message_dict(asdict(message))
    if hasattr(message, 'get_fields_and_field_types'):
        fields = message.get_fields_and_field_types().keys()
        return {field: canonical_message_dict(getattr(message, field)) for field in fields}
    if hasattr(message, '__slots__'):
        return {
            field.lstrip('_'): canonical_message_dict(getattr(message, field))
            for field in getattr(message, '__slots__')
            if hasattr(message, field)
        }
    return str(message)


def extract_source_timestamp(payload: Mapping[str, Any]) -> str | None:
    header = payload.get('header')
    if not isinstance(header, Mapping):
        return None
    stamp = header.get('stamp')
    if not isinstance(stamp, Mapping):
        return None
    sec = stamp.get('sec')
    nanosec = stamp.get('nanosec', stamp.get('nanoseconds', 0))
    if not isinstance(sec, int):
        return None
    nanos = int(nanosec or 0)
    return datetime.fromtimestamp(sec + nanos / 1_000_000_000, timezone.utc).isoformat().replace('+00:00', 'Z')


def _path_parts(path: str) -> list[str]:
    return [part for part in path.split('.') if part]


def _get_path(data: Mapping[str, Any], path: str) -> tuple[bool, Any]:
    current: Any = data
    for part in _path_parts(path):
        if not isinstance(current, Mapping) or part not in current:
            return False, None
        current = current[part]
    return True, current


def _set_path(data: dict[str, Any], path: str, value: Any) -> None:
    parts = _path_parts(path)
    current = data
    for part in parts[:-1]:
        next_value = current.get(part)
        if not isinstance(next_value, dict):
            next_value = {}
            current[part] = next_value
        current = next_value
    if parts:
        current[parts[-1]] = value


def _delete_path(data: dict[str, Any], path: str) -> None:
    parts = _path_parts(path)
    current: Any = data
    for part in parts[:-1]:
        if not isinstance(current, dict) or part not in current:
            return
        current = current[part]
    if isinstance(current, dict) and parts:
        current.pop(parts[-1], None)


def _encrypt_value(value: Any, public_key_hex: str) -> dict[str, Any]:
    value_hash = payload_hash(value)
    if not public_key_hex or not _HAS_NACL_PUBLIC:
        return {'encrypted': False, 'valueHash': value_hash}
    public_key = PublicKey(bytes.fromhex(public_key_hex.removeprefix('0x')))
    ciphertext = SealedBox(public_key).encrypt(stable_json(value).encode('utf8')).hex()
    return {'encrypted': True, 'algorithm': 'x25519-sealedbox', 'valueHash': value_hash, 'ciphertext': ciphertext}


def _rule_value(rule: FieldRule | Mapping[str, Any], key: str, default: str = '') -> str:
    if isinstance(rule, FieldRule):
        return str(getattr(rule, key, default))
    return str(rule.get(key, rule.get('publicKeyHex' if key == 'public_key_hex' else key, default)) or '')


def apply_field_rules(payload: Mapping[str, Any], rules: Iterable[FieldRule | Mapping[str, Any]]) -> dict[str, Any]:
    rule_list = list(rules)
    include_rules = [rule for rule in rule_list if _rule_value(rule, 'action', 'include') == 'include']
    if include_rules:
        transformed: dict[str, Any] = {}
        for rule in include_rules:
            path = _rule_value(rule, 'path')
            exists, value = _get_path(payload, path)
            if exists:
                _set_path(transformed, path, copy.deepcopy(value))
    else:
        transformed = copy.deepcopy(dict(payload))

    for rule in rule_list:
        action = _rule_value(rule, 'action', 'include')
        path = _rule_value(rule, 'path')
        if action == 'include':
            continue
        exists, value = _get_path(transformed, path)
        if not exists:
            continue
        if action == 'exclude':
            _delete_path(transformed, path)
        elif action == 'anonymize':
            _set_path(transformed, path, {'redacted': True})
        elif action == 'hash':
            _set_path(transformed, path, payload_hash(value))
        elif action == 'encrypt':
            _set_path(transformed, path, _encrypt_value(value, _rule_value(rule, 'public_key_hex')))

    return transformed


def should_inline_payload(payload: Any, store_inline: bool, inline_limit_bytes: int) -> bool:
    if not store_inline:
        return False
    return len(stable_json(payload).encode('utf8')) <= inline_limit_bytes
