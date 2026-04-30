"""Local address-keyed EVM wallet registry for peaqOS."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PEAQ_CHAIN_ID = 'eip155:3338'
PEAQ_NETWORK = 'peaq'


@dataclass(frozen=True)
class CreatedWallet:
    address: str
    label: str


@dataclass(frozen=True)
class WalletMetadata:
    address: str
    label: str
    created_at: int

    def to_public_dict(self) -> dict[str, Any]:
        account_id = f'{PEAQ_CHAIN_ID}:{self.address}'
        return {
            'address': self.address,
            'label': self.label,
            'created_at': self.created_at,
            'account_id': account_id,
            'chain_id': PEAQ_CHAIN_ID,
            'network': PEAQ_NETWORK,
        }


def _require_eth_tools():
    try:
        from eth_account import Account  # type: ignore
        from eth_utils import is_address, to_checksum_address  # type: ignore
    except Exception as exc:
        raise RuntimeError(
            'eth-account and eth-utils are required for peaqOS wallet operations'
        ) from exc
    return Account, is_address, to_checksum_address


class PeaqosWalletRegistry:
    """Stores EVM private keys locally, keyed by checksummed address."""

    def __init__(self, path: str) -> None:
        self.path = Path(os.path.expanduser(path)).resolve()

    def create_wallet(self, label: str) -> CreatedWallet:
        Account, _, to_checksum_address = _require_eth_tools()
        acct = Account.create()
        address = to_checksum_address(acct.address)
        private_key = acct.key.hex()
        if not private_key.startswith('0x'):
            private_key = '0x' + private_key

        registry = self._read()
        registry.setdefault('version', 1)
        registry.setdefault('wallets', {})
        registry['wallets'][address] = {
            'label': label or 'machine_wallet',
            'address': address,
            'account_id': f'{PEAQ_CHAIN_ID}:{address}',
            'chain_id': PEAQ_CHAIN_ID,
            'network': PEAQ_NETWORK,
            'private_key': private_key,
            'created_at': int(time.time()),
        }
        self._write(registry)
        return CreatedWallet(address=address, label=label or 'machine_wallet')

    def list_wallets(self) -> list[WalletMetadata]:
        wallets = self._wallets()
        return sorted(
            (
                metadata
                for metadata in (
                    self._entry_to_metadata(key, entry)
                    for key, entry in wallets.items()
                    if isinstance(entry, dict)
                )
                if metadata is not None
            ),
            key=lambda wallet: (wallet.label, wallet.address),
        )

    def get_wallet(self, address: str) -> WalletMetadata:
        checksum = self.normalize_address(address)
        entry = self._find_wallet_entry(checksum)
        if not isinstance(entry, dict):
            raise KeyError(f'unknown local peaqOS wallet address: {checksum}')
        metadata = self._entry_to_metadata(checksum, entry)
        if metadata is None:
            raise RuntimeError(f'wallet metadata is malformed: {checksum}')
        return metadata

    def delete_wallet(self, address: str) -> bool:
        checksum = self.normalize_address(address)
        registry = self._read()
        wallets = registry.get('wallets', {})
        if not isinstance(wallets, dict):
            raise RuntimeError('wallet registry is malformed')

        if checksum in wallets:
            del wallets[checksum]
            self._write(registry)
            return True

        for key, entry in list(wallets.items()):
            if not isinstance(entry, dict) or not entry.get('address'):
                continue
            try:
                if self.normalize_address(str(entry['address'])) == checksum:
                    del wallets[key]
                    self._write(registry)
                    return True
            except Exception:
                continue
        return False

    def normalize_address(self, address: str) -> str:
        _, is_address, to_checksum_address = _require_eth_tools()
        value = (address or '').strip()
        if not value or not is_address(value):
            raise ValueError('address must be a valid 0x-prefixed EVM address')
        return str(to_checksum_address(value))

    def get_private_key(self, address: str) -> str:
        checksum = self.normalize_address(address)
        entry = self._find_wallet_entry(checksum)
        if not isinstance(entry, dict):
            raise KeyError(f'unknown local peaqOS wallet address: {checksum}')
        private_key = str(entry.get('private_key') or '').strip()
        if not private_key:
            raise RuntimeError(f'missing private key for local peaqOS wallet: {checksum}')
        return private_key

    def _wallets(self) -> dict[str, Any]:
        wallets = self._read().get('wallets', {})
        if not isinstance(wallets, dict):
            raise RuntimeError('wallet registry is malformed')
        return wallets

    def _find_wallet_entry(self, checksum: str) -> dict[str, Any] | None:
        wallets = self._wallets()
        entry = wallets.get(checksum)
        if not isinstance(entry, dict):
            # Backward-compatible scan in case a registry was keyed by labels.
            for value in wallets.values():
                if isinstance(value, dict) and value.get('address'):
                    try:
                        if self.normalize_address(str(value['address'])) == checksum:
                            entry = value
                            break
                    except Exception:
                        continue
        return entry if isinstance(entry, dict) else None

    def _entry_to_metadata(self, key: str, entry: dict[str, Any]) -> WalletMetadata | None:
        address_value = str(entry.get('address') or key).strip()
        try:
            address = self.normalize_address(address_value)
        except Exception:
            return None
        label = str(entry.get('label') or '').strip() or 'machine_wallet'
        try:
            created_at = int(entry.get('created_at') or 0)
        except Exception:
            created_at = 0
        return WalletMetadata(address=address, label=label, created_at=created_at)

    def _read(self) -> dict[str, Any]:
        if not self.path.exists():
            return {'version': 1, 'wallets': {}}
        try:
            data = json.loads(self.path.read_text(encoding='utf-8') or '{}')
        except Exception as exc:
            raise RuntimeError(f'failed reading wallet registry {self.path}: {exc}') from exc
        if not isinstance(data, dict):
            raise RuntimeError(f'wallet registry {self.path} must contain a JSON object')
        data.setdefault('version', 1)
        data.setdefault('wallets', {})
        return data

    def _write(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + '.tmp')
        tmp.write_text(json.dumps(data, indent=2, sort_keys=True), encoding='utf-8')
        os.chmod(tmp, 0o600)
        tmp.replace(self.path)
        try:
            os.chmod(self.path, 0o600)
        except Exception:
            pass
