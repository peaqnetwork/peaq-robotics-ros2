"""Configuration loading for the peaqOS ROS 2 node."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict

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


@dataclass(frozen=True)
class PeaqosContracts:
    identity_registry: str = ''
    identity_staking: str = ''
    event_registry: str = ''
    machine_nft: str = ''
    did_registry: str = ''
    batch_precompile: str = ''
    machine_account_factory: str = ''
    machine_nft_adapter: str = ''


@dataclass(frozen=True)
class PeaqosOperationalLimits:
    max_value_per_tx: int = 0
    rate_limit_max_events: int = 0
    rate_limit_window_seconds: int = 0


@dataclass(frozen=True)
class PeaqosConfig:
    enabled: bool = False
    rpc_url: str = ''
    api_url: str = 'http://127.0.0.1:8000'
    faucet_base_url: str = ''
    wallet_registry_path: str = '~/.peaq_robot/peaqos_wallets.json'
    default_machine_address: str = ''
    default_proxy_address: str = ''
    default_owner_address: str = ''
    default_qr_format: str = 'svg'
    contracts: PeaqosContracts = field(default_factory=PeaqosContracts)
    operational_limits: PeaqosOperationalLimits = field(default_factory=PeaqosOperationalLimits)

    @property
    def expanded_wallet_registry_path(self) -> str:
        return _expand(self.wallet_registry_path)


def _apply_yaml(cfg: dict[str, Any], data: dict[str, Any]) -> None:
    peaq_os = data.get('peaq_os', {}) or data.get('peaqos', {}) or {}
    if not isinstance(peaq_os, dict):
        return

    cfg['enabled'] = _as_bool(peaq_os.get('enabled'), cfg['enabled'])
    evm = peaq_os.get('evm', {}) or {}
    if isinstance(evm, dict):
        cfg['rpc_url'] = _as_str(evm.get('rpc_url'), cfg['rpc_url'])
    cfg['rpc_url'] = _as_str(peaq_os.get('rpc_url'), cfg['rpc_url'])
    cfg['api_url'] = _as_str(peaq_os.get('api_url'), cfg['api_url'])
    cfg['faucet_base_url'] = _as_str(peaq_os.get('faucet_base_url'), cfg['faucet_base_url'])

    faucet = peaq_os.get('faucet', {}) or {}
    if isinstance(faucet, dict):
        cfg['faucet_base_url'] = _as_str(faucet.get('base_url'), cfg['faucet_base_url'])
        cfg['default_qr_format'] = _as_str(faucet.get('qr_format'), cfg['default_qr_format'])

    registry = peaq_os.get('wallet_registry', {}) or {}
    if isinstance(registry, dict):
        cfg['wallet_registry_path'] = _as_str(registry.get('path'), cfg['wallet_registry_path'])

    defaults = peaq_os.get('defaults', {}) or {}
    if isinstance(defaults, dict):
        cfg['default_machine_address'] = _as_str(
            defaults.get('machine_address'),
            cfg['default_machine_address'],
        )
        cfg['default_proxy_address'] = _as_str(
            defaults.get('proxy_address'),
            cfg['default_proxy_address'],
        )
        cfg['default_owner_address'] = _as_str(
            defaults.get('owner_address'),
            cfg['default_owner_address'],
        )

    contracts = peaq_os.get('contracts', {}) or {}
    if isinstance(contracts, dict):
        for key in PeaqosContracts.__dataclass_fields__.keys():
            cfg['contracts'][key] = _as_str(contracts.get(key), cfg['contracts'][key])

    limits = peaq_os.get('operational_limits', {}) or {}
    if isinstance(limits, dict):
        cfg['operational_limits']['max_value_per_tx'] = _as_int(
            limits.get('max_value_per_tx'),
            cfg['operational_limits']['max_value_per_tx'],
        )
        cfg['operational_limits']['rate_limit_max_events'] = _as_int(
            limits.get('rate_limit_max_events'),
            cfg['operational_limits']['rate_limit_max_events'],
        )
        cfg['operational_limits']['rate_limit_window_seconds'] = _as_int(
            limits.get('rate_limit_window_seconds'),
            cfg['operational_limits']['rate_limit_window_seconds'],
        )


def _apply_env(cfg: dict[str, Any]) -> None:
    cfg['enabled'] = _as_bool(os.getenv('PEAQOS_ENABLED'), cfg['enabled'])
    cfg['rpc_url'] = _as_str(os.getenv('PEAQOS_RPC_URL'), cfg['rpc_url'])
    cfg['api_url'] = _as_str(os.getenv('PEAQOS_MCR_API_URL'), cfg['api_url'])
    cfg['faucet_base_url'] = _as_str(os.getenv('PEAQOS_FAUCET_URL'), cfg['faucet_base_url'])
    cfg['wallet_registry_path'] = _as_str(
        os.getenv('PEAQOS_WALLET_REGISTRY'),
        cfg['wallet_registry_path'],
    )
    cfg['default_machine_address'] = _as_str(
        os.getenv('PEAQOS_DEFAULT_MACHINE_ADDRESS'),
        cfg['default_machine_address'],
    )
    cfg['default_proxy_address'] = _as_str(
        os.getenv('PEAQOS_DEFAULT_PROXY_ADDRESS'),
        cfg['default_proxy_address'],
    )
    cfg['default_owner_address'] = _as_str(
        os.getenv('PEAQOS_DEFAULT_OWNER_ADDRESS'),
        cfg['default_owner_address'],
    )
    cfg['default_qr_format'] = _as_str(os.getenv('PEAQOS_QR_FORMAT'), cfg['default_qr_format'])

    env_contracts = {
        'identity_registry': 'IDENTITY_REGISTRY_ADDRESS',
        'identity_staking': 'IDENTITY_STAKING_ADDRESS',
        'event_registry': 'EVENT_REGISTRY_ADDRESS',
        'machine_nft': 'MACHINE_NFT_ADDRESS',
        'did_registry': 'DID_REGISTRY_ADDRESS',
        'batch_precompile': 'BATCH_PRECOMPILE_ADDRESS',
        'machine_account_factory': 'MACHINE_ACCOUNT_FACTORY_ADDRESS',
        'machine_nft_adapter': 'MACHINE_NFT_ADAPTER_ADDRESS',
    }
    for key, env_key in env_contracts.items():
        cfg['contracts'][key] = _as_str(os.getenv(env_key), cfg['contracts'][key])

    cfg['operational_limits']['max_value_per_tx'] = _as_int(
        os.getenv('PEAQOS_MAX_VALUE_PER_TX'),
        cfg['operational_limits']['max_value_per_tx'],
    )
    cfg['operational_limits']['rate_limit_max_events'] = _as_int(
        os.getenv('PEAQOS_RATE_LIMIT_MAX_EVENTS'),
        cfg['operational_limits']['rate_limit_max_events'],
    )
    cfg['operational_limits']['rate_limit_window_seconds'] = _as_int(
        os.getenv('PEAQOS_RATE_LIMIT_WINDOW_SECONDS'),
        cfg['operational_limits']['rate_limit_window_seconds'],
    )


def _apply_params(cfg: dict[str, Any], params: Dict[str, Any]) -> None:
    mapping = {
        'peaq_os.enabled': ('enabled', _as_bool),
        'peaq_os.rpc_url': ('rpc_url', _as_str),
        'peaq_os.api_url': ('api_url', _as_str),
        'peaq_os.faucet_base_url': ('faucet_base_url', _as_str),
        'peaq_os.wallet_registry.path': ('wallet_registry_path', _as_str),
        'peaq_os.defaults.machine_address': ('default_machine_address', _as_str),
        'peaq_os.defaults.proxy_address': ('default_proxy_address', _as_str),
        'peaq_os.defaults.owner_address': ('default_owner_address', _as_str),
        'peaq_os.faucet.qr_format': ('default_qr_format', _as_str),
    }
    for param_key, (cfg_key, caster) in mapping.items():
        if param_key in params:
            cfg[cfg_key] = caster(params[param_key], cfg[cfg_key])

    for key in PeaqosContracts.__dataclass_fields__.keys():
        param_key = f'peaq_os.contracts.{key}'
        if param_key in params:
            cfg['contracts'][key] = _as_str(params[param_key], cfg['contracts'][key])

    for key in PeaqosOperationalLimits.__dataclass_fields__.keys():
        param_key = f'peaq_os.operational_limits.{key}'
        if param_key in params:
            cfg['operational_limits'][key] = _as_int(
                params[param_key],
                cfg['operational_limits'][key],
            )


def load_peaqos_config_from_params(params: Dict[str, Any]) -> PeaqosConfig:
    cfg: dict[str, Any] = {
        'enabled': False,
        'rpc_url': '',
        'api_url': 'http://127.0.0.1:8000',
        'faucet_base_url': '',
        'wallet_registry_path': '~/.peaq_robot/peaqos_wallets.json',
        'default_machine_address': '',
        'default_proxy_address': '',
        'default_owner_address': '',
        'default_qr_format': 'svg',
        'contracts': {key: '' for key in PeaqosContracts.__dataclass_fields__.keys()},
        'operational_limits': {
            key: 0 for key in PeaqosOperationalLimits.__dataclass_fields__.keys()
        },
    }

    yaml_path = str(params.get('config.yaml_path') or os.getenv('PEAQ_ROS2_CONFIG_YAML', '')).strip()
    if yaml_path:
        if not _HAS_YAML:
            raise RuntimeError('PyYAML is required to load config.yaml_path for peaq_ros2_peaqos')
        with open(_expand(yaml_path), 'r') as f:
            _apply_yaml(cfg, yaml.safe_load(f) or {})

    _apply_env(cfg)
    _apply_params(cfg, params)

    return PeaqosConfig(
        enabled=bool(cfg['enabled']),
        rpc_url=str(cfg['rpc_url']),
        api_url=str(cfg['api_url']),
        faucet_base_url=str(cfg['faucet_base_url']),
        wallet_registry_path=_expand(str(cfg['wallet_registry_path'])),
        default_machine_address=str(cfg['default_machine_address']),
        default_proxy_address=str(cfg['default_proxy_address']),
        default_owner_address=str(cfg['default_owner_address']),
        default_qr_format=str(cfg['default_qr_format'] or 'svg'),
        contracts=PeaqosContracts(**cfg['contracts']),
        operational_limits=PeaqosOperationalLimits(**cfg['operational_limits']),
    )
