"""
Config loading for peaq_ros2_tether.

This repo's convention:
- Support ROS params (launch/CLI)
- Optional unified YAML overlay via param `config.yaml_path`
- Env var fallbacks (similar to peaq_ros2_core)
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, Optional

try:
    import yaml  # type: ignore

    _HAS_YAML = True
except Exception:
    _HAS_YAML = False


def _expand(path: str) -> str:
    return os.path.expanduser(path or '').strip()


@dataclass(frozen=True)
class TetherConfig:
    enabled: bool
    evm_rpc_url: str
    usdt_contract: str
    usdt_decimals: int
    wallet_registry_path: str
    unsafe_export_mnemonic: bool
    node_bin: str


def load_tether_config_from_params(params: Dict[str, Any]) -> TetherConfig:
    """
    Load tether config from ROS params + unified YAML overlay.

    YAML format (top-level):
    tether:
      enabled: true
      evm:
        rpc_url: "https://..."
      usdt:
        contract: "0x..."
        decimals: 6
      wallet_registry:
        path: "~/.peaq_robot/tether_wallets.json"
        unsafe_export_mnemonic: false
    """

    # Defaults from env (explicit so behavior is predictable in Docker/robots)
    enabled = os.getenv('PEAQ_TETHER_ENABLED', 'false').lower() == 'true'
    evm_rpc_url = os.getenv('PEAQ_TETHER_EVM_RPC', '').strip()
    usdt_contract = os.getenv('PEAQ_TETHER_USDT_CONTRACT', '').strip()
    usdt_decimals = int(os.getenv('PEAQ_TETHER_USDT_DECIMALS', '6'))
    wallet_registry_path = os.getenv('PEAQ_TETHER_WALLET_REGISTRY', '~/.peaq_robot/tether_wallets.json')
    unsafe_export_mnemonic = os.getenv('PEAQ_TETHER_UNSAFE_EXPORT_MNEMONIC', 'false').lower() == 'true'
    node_bin = os.getenv('PEAQ_TETHER_NODE_BIN', 'node').strip() or 'node'

    # Overlay from ROS params (flat)
    def _get_bool(key: str, cur: bool) -> bool:
        if key not in params:
            return cur
        return bool(params[key])

    def _get_str(key: str, cur: str) -> str:
        if key not in params:
            return cur
        return str(params[key]).strip()

    def _get_int(key: str, cur: int) -> int:
        if key not in params:
            return cur
        try:
            return int(params[key])
        except Exception:
            return cur

    enabled = _get_bool('tether.enabled', enabled)
    evm_rpc_url = _get_str('tether.evm.rpc_url', evm_rpc_url)
    usdt_contract = _get_str('tether.usdt.contract', usdt_contract)
    usdt_decimals = _get_int('tether.usdt.decimals', usdt_decimals)
    wallet_registry_path = _get_str('tether.wallet_registry.path', wallet_registry_path)
    unsafe_export_mnemonic = _get_bool('tether.wallet_registry.unsafe_export_mnemonic', unsafe_export_mnemonic)
    node_bin = _get_str('tether.node_bin', node_bin)

    # Unified YAML overlay (preferred in this repo)
    yaml_path = str(params.get('config.yaml_path') or os.getenv('PEAQ_ROS2_CONFIG_YAML', '')).strip()
    if yaml_path:
        if not _HAS_YAML:
            raise RuntimeError('PyYAML is required to load config.yaml_path for peaq_ros2_tether')
        with open(_expand(yaml_path), 'r') as f:
            data = yaml.safe_load(f) or {}
        tether = data.get('tether', {}) or {}
        if isinstance(tether, dict):
            enabled = bool(tether.get('enabled', enabled))
            evm = tether.get('evm', {}) or {}
            if isinstance(evm, dict):
                evm_rpc_url = str(evm.get('rpc_url', evm_rpc_url)).strip()
            usdt = tether.get('usdt', {}) or {}
            if isinstance(usdt, dict):
                usdt_contract = str(usdt.get('contract', usdt_contract)).strip()
                try:
                    usdt_decimals = int(usdt.get('decimals', usdt_decimals))
                except Exception:
                    pass
            reg = tether.get('wallet_registry', {}) or {}
            if isinstance(reg, dict):
                wallet_registry_path = str(reg.get('path', wallet_registry_path)).strip()
                unsafe_export_mnemonic = bool(reg.get('unsafe_export_mnemonic', unsafe_export_mnemonic))

    return TetherConfig(
        enabled=enabled,
        evm_rpc_url=evm_rpc_url,
        usdt_contract=usdt_contract,
        usdt_decimals=usdt_decimals,
        wallet_registry_path=_expand(wallet_registry_path),
        unsafe_export_mnemonic=unsafe_export_mnemonic,
        node_bin=node_bin,
    )

