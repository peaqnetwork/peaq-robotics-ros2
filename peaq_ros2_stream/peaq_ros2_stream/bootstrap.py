"""Stream seller setup command."""

from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path
from typing import Any, Mapping

from .api import StreamApiClient
from .config import load_stream_agent_config_from_dict
from .models import STORAGE_BACKENDS
from .recipient_keys import load_or_create_recipient_key, recipient_entry

try:
    import yaml  # type: ignore

    _HAS_YAML = True
except Exception:
    _HAS_YAML = False


class BootstrapError(RuntimeError):
    pass


def _expand(path: str) -> Path:
    return Path(os.path.expanduser(path)).resolve()


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    if not _HAS_YAML:
        raise BootstrapError('PyYAML is required to read stream config files')
    with path.open('r', encoding='utf8') as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, Mapping):
        raise BootstrapError('stream config file must contain a mapping')
    return dict(data)


def _write_yaml(path: Path, data: Mapping[str, Any]) -> None:
    if not _HAS_YAML:
        raise BootstrapError('PyYAML is required to write stream config files')
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf8') as handle:
        yaml.safe_dump(dict(data), handle, sort_keys=False)
    path.chmod(0o600)


def _topic_items(topics: list[str], message_types: list[str]) -> list[dict[str, str]]:
    if not topics and not message_types:
        return []
    if len(topics) != len(message_types):
        raise BootstrapError('--topic and --message-type must be provided the same number of times')
    return [
        {
            'topic': topic,
            'message_type': message_type,
            'qos_preset': 'default',
            'field_rules': [],
        }
        for topic, message_type in zip(topics, message_types)
    ]


def _recipient_items(args: argparse.Namespace) -> list[dict[str, str]]:
    recipients = []
    if args.owner_public_key_hex:
        recipients.append(
            recipient_entry(
                args.owner_recipient_id or 'owner',
                'owner',
                args.owner_public_key_hex,
            )
        )
    if args.operator_public_key_hex:
        recipients.append(
            recipient_entry(
                args.operator_recipient_id or 'operator',
                'operator',
                args.operator_public_key_hex,
            )
        )
    return recipients


def _merge_key_recipients(
    existing: list[dict[str, str]],
    additions: list[dict[str, str]],
) -> list[dict[str, str]]:
    merged = list(existing)
    seen = {
        (
            str(item.get('recipient_id') or item.get('recipientId') or ''),
            str(item.get('recipient_type') or item.get('recipientType') or ''),
        )
        for item in merged
        if isinstance(item, dict)
    }
    for item in additions:
        key = (item['recipient_id'], item['recipient_type'])
        if key not in seen:
            merged.append(item)
            seen.add(key)
    return merged


def apply_stream_bootstrap(
    data: Mapping[str, Any],
    *,
    api_base_url: str,
    api_key: str,
    machine_id: str,
    identity_ref: str,
    agent_id: str,
    agent_token: str,
    storage_backend: str,
    topics: list[dict[str, str]],
    key_recipients: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    updated = dict(data)
    stream = dict(updated.get('stream_agent') or {})
    stream.update(
        {
            'enabled': True,
            'api_base_url': api_base_url.rstrip('/'),
            'machine_id': machine_id,
            'agent_id': agent_id,
            'agent_token': agent_token,
            'identity_ref': identity_ref,
        }
    )
    if api_key:
        stream['api_key'] = api_key
    if topics and not stream.get('topics'):
        stream['topics'] = topics
    if storage_backend:
        storage = dict(stream.get('storage') or {})
        storage['backend'] = storage_backend
        stream['storage'] = storage
    if key_recipients:
        current = stream.get('key_recipients') or stream.get('keyRecipients') or []
        if not isinstance(current, list):
            current = []
        stream['key_recipients'] = _merge_key_recipients(current, key_recipients)
    updated['stream_agent'] = stream
    return updated


def bootstrap_stream_agent(
    *,
    config_path: Path,
    output_path: Path,
    api_base_url: str,
    api_key: str,
    machine_id: str,
    label: str,
    storage_backend: str,
    topics: list[dict[str, str]],
    machine_recipient_key_path: Path,
    extra_key_recipients: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    if not api_base_url:
        raise BootstrapError('api base URL is required')
    if not machine_id:
        raise BootstrapError('machine id is required')
    if storage_backend and storage_backend not in STORAGE_BACKENDS:
        raise BootstrapError(f'storage backend must be one of {sorted(STORAGE_BACKENDS)}')

    client = StreamApiClient(api_base_url, api_key=api_key)
    machine = client.get_machine(machine_id)
    identity_ref = str(machine.get('identityRef') or '').strip()
    if machine.get('status') != 'active' or not identity_ref:
        raise BootstrapError('machine must be active and have identityRef before Stream can start')

    agent = client.enroll_machine_agent(machine_id, label=label, allowed_provider_keys=['stream'])
    agent_id = str(agent.get('id') or '').strip()
    agent_token = str(agent.get('agentToken') or '').strip()
    if not agent_id or not agent_token:
        raise BootstrapError('agent enrollment response did not include agent id and token')

    data = _load_yaml(config_path)
    stream = data.get('stream_agent') if isinstance(data.get('stream_agent'), Mapping) else {}
    existing_recipients = []
    if isinstance(stream, Mapping):
        existing_recipients = stream.get('key_recipients') or stream.get('keyRecipients') or []
    key_recipients = list(extra_key_recipients or [])
    if not existing_recipients:
        recipient_key = load_or_create_recipient_key(machine_recipient_key_path)
        key_recipients.append(recipient_entry(machine_id, 'machine', recipient_key['publicKeyHex']))
    updated = apply_stream_bootstrap(
        data,
        api_base_url=api_base_url,
        api_key=api_key,
        machine_id=machine_id,
        identity_ref=identity_ref,
        agent_id=agent_id,
        agent_token=agent_token,
        storage_backend=storage_backend,
        topics=topics,
        key_recipients=key_recipients,
    )
    load_stream_agent_config_from_dict(updated)
    _write_yaml(output_path, updated)
    return {
        'machineId': machine_id,
        'identityRef': identity_ref,
        'agentId': agent_id,
        'configPath': str(output_path),
        'machineRecipientKeyPath': str(machine_recipient_key_path),
        'launchCommand': f'ros2 launch peaq_ros2_stream peaq_stream.launch.py config_yaml:={output_path}',
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Enroll a Stream runtime agent and write a runnable seller config.')
    parser.add_argument('--config', default=os.getenv('PEAQ_ROS2_CONFIG_YAML', '~/.peaq_robot/peaq_stream.yaml'))
    parser.add_argument('--output', default='')
    parser.add_argument('--api-base-url', default=os.getenv('PEAQOS_STREAM_API_BASE_URL', 'http://127.0.0.1:8000'))
    parser.add_argument('--api-key', default=os.getenv('PEAQOS_STREAM_API_KEY', ''))
    parser.add_argument('--machine-id', default=os.getenv('PEAQOS_STREAM_MACHINE_ID', ''))
    parser.add_argument('--label', default='Stream runtime')
    parser.add_argument('--storage-backend', default=os.getenv('PEAQOS_STREAM_STORAGE_BACKEND', ''))
    parser.add_argument(
        '--machine-recipient-key',
        default=os.getenv('PEAQOS_STREAM_MACHINE_RECIPIENT_KEY_PATH', '~/.peaq_robot/stream_machine_x25519_key.json'),
    )
    parser.add_argument('--owner-recipient-id', default=os.getenv('PEAQOS_STREAM_OWNER_ID', ''))
    parser.add_argument('--owner-public-key-hex', default=os.getenv('PEAQOS_STREAM_OWNER_PUBLIC_KEY_HEX', ''))
    parser.add_argument('--operator-recipient-id', default=os.getenv('PEAQOS_STREAM_OPERATOR_ID', ''))
    parser.add_argument('--operator-public-key-hex', default=os.getenv('PEAQOS_STREAM_OPERATOR_PUBLIC_KEY_HEX', ''))
    parser.add_argument('--topic', action='append', default=[])
    parser.add_argument('--message-type', action='append', default=[])
    parser.add_argument('--start', action='store_true')
    return parser


def main() -> None:
    args = _parser().parse_args()
    config_path = _expand(args.config)
    output_path = _expand(args.output or args.config)
    result = bootstrap_stream_agent(
        config_path=config_path,
        output_path=output_path,
        api_base_url=args.api_base_url,
        api_key=args.api_key,
        machine_id=args.machine_id,
        label=args.label,
        storage_backend=args.storage_backend,
        topics=_topic_items(args.topic, args.message_type),
        machine_recipient_key_path=_expand(args.machine_recipient_key),
        extra_key_recipients=_recipient_items(args),
    )
    print(f'config={result["configPath"]}')
    print(f'machineId={result["machineId"]}')
    print(f'identityRef={result["identityRef"]}')
    print(f'agentId={result["agentId"]}')
    print(f'machineRecipientKey={result["machineRecipientKeyPath"]}')
    print(result['launchCommand'])
    if args.start:
        subprocess.run(
            [
                'ros2',
                'launch',
                'peaq_ros2_stream',
                'peaq_stream.launch.py',
                f'config_yaml:={result["configPath"]}',
            ],
            check=True,
        )


if __name__ == '__main__':
    main()
