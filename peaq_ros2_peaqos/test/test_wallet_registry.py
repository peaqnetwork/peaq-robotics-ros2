"""Tests for the local peaqOS wallet registry."""

import json

from peaq_ros2_peaqos.wallet_registry import (
    PEAQ_CHAIN_ID,
    PEAQ_NETWORK,
    PeaqosWalletRegistry,
)


ADDRESS = '0x000000000000000000000000000000000000dEaD'
PRIVATE_KEY = '0x' + '11' * 32


class _FakeAccountInstance:
    address = ADDRESS

    class key:
        @staticmethod
        def hex():
            return PRIVATE_KEY


class _FakeAccount:
    @staticmethod
    def create():
        return _FakeAccountInstance()


def _fake_require_eth_tools():
    def is_address(value):
        return isinstance(value, str) and value.startswith('0x') and len(value) == 42

    def to_checksum_address(value):
        if value.lower() == ADDRESS.lower():
            return ADDRESS
        return value

    return _FakeAccount, is_address, to_checksum_address


def test_wallet_registry_public_metadata_excludes_private_key(tmp_path, monkeypatch):
    monkeypatch.setattr(
        'peaq_ros2_peaqos.wallet_registry._require_eth_tools',
        _fake_require_eth_tools,
    )
    registry_path = tmp_path / 'wallets.json'
    registry = PeaqosWalletRegistry(str(registry_path))

    created = registry.create_wallet('robot-1')
    metadata = registry.get_wallet(created.address).to_public_dict()

    assert metadata == {
        'address': created.address,
        'label': 'robot-1',
        'created_at': metadata['created_at'],
        'account_id': f'{PEAQ_CHAIN_ID}:{created.address}',
        'chain_id': PEAQ_CHAIN_ID,
        'network': PEAQ_NETWORK,
    }
    assert 'private_key' not in metadata

    stored = json.loads(registry_path.read_text(encoding='utf-8'))
    assert stored['wallets'][created.address]['private_key'].startswith('0x')
    assert registry.get_private_key(created.address).startswith('0x')


def test_wallet_registry_keeps_address_only_lookup_for_legacy_keys(tmp_path, monkeypatch):
    monkeypatch.setattr(
        'peaq_ros2_peaqos.wallet_registry._require_eth_tools',
        _fake_require_eth_tools,
    )
    registry_path = tmp_path / 'wallets.json'
    registry = PeaqosWalletRegistry(str(registry_path))
    created = registry.create_wallet('robot-1')

    data = json.loads(registry_path.read_text(encoding='utf-8'))
    data['wallets'] = {'robot-1': data['wallets'].pop(created.address)}
    registry_path.write_text(json.dumps(data), encoding='utf-8')

    assert registry.get_wallet(created.address).address == created.address
    assert registry.delete_wallet(created.address) is True
    assert registry.list_wallets() == []
