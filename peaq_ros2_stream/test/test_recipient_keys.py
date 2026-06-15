from __future__ import annotations

import stat

from peaq_ros2_stream.recipient_keys import load_or_create_recipient_key, recipient_entry


def test_recipient_key_is_created_once_with_private_permissions(tmp_path):
    path = tmp_path / 'recipient.json'

    first = load_or_create_recipient_key(path)
    second = load_or_create_recipient_key(path)

    assert first == second
    assert first['algorithm'] == 'x25519-sealedbox'
    assert len(first['privateKeyHex']) == 64
    assert len(first['publicKeyHex']) == 64
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_recipient_entry_normalizes_public_key_hex():
    entry = recipient_entry('owner-1', 'owner', '0x' + 'AB' * 32)

    assert entry == {
        'recipient_id': 'owner-1',
        'recipient_type': 'owner',
        'public_key_hex': 'ab' * 32,
    }
