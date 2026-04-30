"""peaqOS SDK adapter used by the ROS 2 node."""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import requests

from .config import PeaqosConfig
from .wallet_registry import CreatedWallet, PeaqosWalletRegistry


_MACHINE_ACCOUNT_FACTORY_DEPLOY11_ABI: list[dict[str, Any]] = [
    {
        'inputs': [
            {'internalType': 'address', 'name': 'owner', 'type': 'address'},
            {'internalType': 'address', 'name': 'machine', 'type': 'address'},
            {'internalType': 'uint256', 'name': 'salt', 'type': 'uint256'},
        ],
        'name': 'createAccount',
        'outputs': [{'internalType': 'address', 'name': '', 'type': 'address'}],
        'stateMutability': 'nonpayable',
        'type': 'function',
    },
    {
        'inputs': [
            {'internalType': 'address', 'name': 'owner', 'type': 'address'},
            {'internalType': 'address', 'name': 'machine', 'type': 'address'},
            {'internalType': 'uint256', 'name': 'salt', 'type': 'uint256'},
        ],
        'name': 'getAddress',
        'outputs': [{'internalType': 'address', 'name': '', 'type': 'address'}],
        'stateMutability': 'view',
        'type': 'function',
    },
    {
        'anonymous': False,
        'inputs': [
            {'indexed': True, 'internalType': 'address', 'name': 'account', 'type': 'address'},
            {'indexed': True, 'internalType': 'address', 'name': 'owner', 'type': 'address'},
            {'indexed': True, 'internalType': 'address', 'name': 'machine', 'type': 'address'},
        ],
        'name': 'AccountCreated',
        'type': 'event',
    },
]

_MACHINE_NFT_ADAPTER_TOKEN_ABI: list[dict[str, Any]] = [
    {
        'inputs': [],
        'name': 'token',
        'outputs': [{'internalType': 'address', 'name': '', 'type': 'address'}],
        'stateMutability': 'view',
        'type': 'function',
    },
]

# LayerZero v2 Type 3 options with executor lzReceive gas=200_000, value=0.
# This mirrors peaq-os-mcr-core scripts using
# Options.newOptions().addExecutorLzReceiveOption(200_000, 0).
# Encoding: type=3, worker=executor(1), option_size=17, option_type=lzReceive(1),
# gas=uint128(200_000). The value field is omitted when zero.
_DEFAULT_LZ_RECEIVE_OPTIONS = bytes.fromhex(
    '00030100110100000000000000000000000000030d40'
)

_ZERO_EVM_ADDRESS = '0x' + ('0' * 40)
_NONEXISTENT_TOKEN_MARKERS = (
    'nonexistent token',
    'invalid token id',
    'owner query for nonexistent token',
    'erc721: invalid token',
    'erc721nonexistenttoken',
    '0x7e273289',  # ERC721NonexistentToken(uint256)
)


@dataclass(frozen=True)
class PeaqosErrorInfo:
    code: str
    field: str
    message: str


def error_info(exc: BaseException) -> PeaqosErrorInfo:
    return PeaqosErrorInfo(
        code=str(getattr(exc, 'code', '') or exc.__class__.__name__),
        field=str(getattr(exc, 'field', '') or ''),
        message=str(exc),
    )


class PeaqosAdapter:
    """Thin wrapper around peaq-os-sdk plus local wallet lookup."""

    def __init__(self, config: PeaqosConfig) -> None:
        self.config = config
        self.wallets = PeaqosWalletRegistry(config.expanded_wallet_registry_path)
        self._session = requests.Session()

    def create_wallet(self, label: str) -> CreatedWallet:
        return self.wallets.create_wallet(label=label or 'machine_wallet')

    def list_wallets(self) -> list[dict[str, Any]]:
        return [wallet.to_public_dict() for wallet in self.wallets.list_wallets()]

    def get_wallet(self, address: str) -> dict[str, Any]:
        return self.wallets.get_wallet(address).to_public_dict()

    def delete_wallet(self, address: str) -> bool:
        return self.wallets.delete_wallet(address)

    def setup_faucet_2fa(self, owner_address: str, qr_format: str) -> dict[str, Any]:
        if not self.config.faucet_base_url:
            raise RuntimeError('peaq_os.faucet_base_url is required')
        try:
            return self._setup_faucet_2fa_prefixed(owner_address, qr_format)
        except Exception as prefixed_exc:  # noqa: BLE001
            try:
                return self._setup_faucet_2fa_sdk(owner_address, qr_format)
            except Exception:
                raise prefixed_exc

    def _setup_faucet_2fa_sdk(self, owner_address: str, qr_format: str) -> dict[str, Any]:
        from peaq_os_sdk.registration.faucet import setup_faucet_2fa

        return dict(setup_faucet_2fa(
            self._session,
            owner_address,
            self.config.faucet_base_url,
            qr_format or self.config.default_qr_format,
        ))

    def confirm_faucet_2fa(self, owner_address: str, two_factor_code: str) -> None:
        if not self.config.faucet_base_url:
            raise RuntimeError('peaq_os.faucet_base_url is required')
        try:
            self._confirm_faucet_2fa_prefixed(owner_address, two_factor_code)
            return
        except Exception as prefixed_exc:  # noqa: BLE001
            try:
                self._confirm_faucet_2fa_sdk(owner_address, two_factor_code)
                return
            except Exception:
                raise prefixed_exc

    def _confirm_faucet_2fa_sdk(self, owner_address: str, two_factor_code: str) -> None:
        from peaq_os_sdk.registration.faucet import confirm_faucet_2fa

        confirm_faucet_2fa(
            self._session,
            owner_address,
            self.config.faucet_base_url,
            two_factor_code,
        )

    def fund_wallet(
        self,
        *,
        owner_address: str,
        target_address: str,
        chain_id: str,
        two_factor_code: str,
        request_id: str,
    ) -> tuple[str, dict[str, Any]]:
        if not self.config.faucet_base_url:
            raise RuntimeError('peaq_os.faucet_base_url is required')
        effective_request_id = (request_id or '').strip() or str(uuid.uuid4())
        from peaq_os_sdk.registration.fund_from_gas_station import fund_from_gas_station

        result = fund_from_gas_station(
            self._session,
            owner_address,
            target_address,
            self.config.faucet_base_url,
            two_factor_code,
            chain_id or 'peaq',
            effective_request_id,
        )
        return effective_request_id, dict(result)

    def register_agent(self, address: str) -> int:
        signer = self._resolve_address(address, self.config.default_machine_address, 'address')
        client = self._client_for_address(signer)
        return int(_call_register_machine(client))

    def register_machine(self, address: str) -> int:
        signer = self._resolve_address(address, self.config.default_machine_address, 'address')
        client = self._client_for_address(signer)
        return int(_call_register_machine(client))

    def register_for(self, proxy_address: str, machine_address: str) -> int:
        proxy = self._resolve_address(proxy_address, self.config.default_proxy_address, 'proxy_address')
        if not machine_address:
            raise ValueError('machine_address is required')
        machine = self.wallets.normalize_address(machine_address)
        client = self._client_for_address(proxy)
        return int(client.register_for(machine))

    def mint_nft(self, signer_address: str, machine_id: int, recipient: str) -> str:
        signer = self._resolve_default_proxy_signer(signer_address)
        client = self._client_for_address(signer)
        mint_recipient = self._normalize_external_address(recipient or signer, 'recipient')
        return str(client.mint_nft(machine_id=int(machine_id), recipient=mint_recipient))

    def token_id_of(self, signer_address: str, machine_id: int) -> int:
        signer = self._resolve_default_proxy_signer(signer_address)
        client = self._client_for_address(signer)
        return int(client.token_id_of(machine_id=int(machine_id)))

    def read_did_attribute(
        self,
        *,
        signer_address: str,
        did_address: str,
        name: str,
    ) -> dict[str, Any]:
        signer = self._resolve_address(
            signer_address,
            self.config.default_machine_address,
            'signer_address',
        )
        client = self._client_for_address(signer)
        address = self._normalize_did_address(did_address, 'did_address')

        from peaq_os_sdk.did.did_precompile import read_attribute

        return dict(read_attribute(client, address, name))

    def write_machine_did_attributes(
        self,
        *,
        signer_address: str,
        machine_id: int,
        nft_token_id: int,
        operator_did: str,
        documentation_url: str,
        data_api: str,
        data_visibility: str,
    ) -> str:
        signer = self._resolve_address(
            signer_address,
            self.config.default_machine_address,
            'signer_address',
        )
        client = self._client_for_address(signer)
        return str(client.write_machine_did_attributes(
            machine_id=int(machine_id),
            nft_token_id=int(nft_token_id),
            operator_did=(operator_did or '').strip(),
            documentation_url=(documentation_url or '').strip(),
            data_api=(data_api or '').strip(),
            data_visibility=(data_visibility or '').strip(),
        ))

    def write_proxy_did_attributes(
        self,
        *,
        signer_address: str,
        proxy_agent_id: int,
        machine_ids: list[int],
    ) -> str:
        signer = self._resolve_default_proxy_signer(signer_address)
        client = self._client_for_address(signer)
        return str(client.write_proxy_did_attributes(
            proxy_agent_id=int(proxy_agent_id),
            machine_ids=[int(machine_id) for machine_id in machine_ids],
        ))

    def validate_event(
        self,
        *,
        machine_id: int,
        event_type: int,
        value: int,
        timestamp: int,
        raw_data_hex: str,
        trust_level: int,
        source_chain_id: int,
        source_tx_hash: str,
        metadata_hex: str,
    ) -> str:
        from peaq_os_sdk.utils.data_hash import compute_data_hash
        from peaq_os_sdk.validation import validate_submit_event_params

        params = _event_params(
            machine_id=machine_id,
            event_type=event_type,
            value=value,
            timestamp=timestamp,
            raw_data_hex=raw_data_hex,
            trust_level=trust_level,
            source_chain_id=source_chain_id,
            source_tx_hash=source_tx_hash,
            metadata_hex=metadata_hex,
        )
        validate_submit_event_params(params)
        if params.raw_data is None:
            return '0x' + ('0' * 64)
        digest = compute_data_hash(params.raw_data)
        if isinstance(digest, bytes):
            return '0x' + digest.hex()
        return str(digest)

    def submit_event(
        self,
        *,
        signer_address: str,
        machine_id: int,
        event_type: int,
        value: int,
        timestamp: int,
        raw_data_hex: str,
        trust_level: int,
        source_chain_id: int,
        source_tx_hash: str,
        metadata_hex: str,
    ) -> tuple[str, str]:
        signer = self._resolve_address(
            signer_address,
            self.config.default_machine_address,
            'signer_address',
        )
        client = self._client_for_address(signer)
        params = _event_params(
            machine_id=machine_id,
            event_type=event_type,
            value=value,
            timestamp=timestamp,
            raw_data_hex=raw_data_hex,
            trust_level=trust_level,
            source_chain_id=source_chain_id,
            source_tx_hash=source_tx_hash,
            metadata_hex=metadata_hex,
        )
        tx_hash, data_hash = client.submit_event(
            machine_id=params.machine_id,
            event_type=params.event_type,
            value=params.value,
            timestamp=params.timestamp,
            raw_data=params.raw_data,
            trust_level=params.trust_level,
            source_chain_id=params.source_chain_id,
            source_tx_hash=params.source_tx_hash,
            metadata=params.metadata,
        )
        return str(tx_hash), _bytes32_to_hex(data_hash)

    def batch_submit_events(self, signer_address: str, events_json: str) -> list[str]:
        signer = self._resolve_address(
            signer_address,
            self.config.default_machine_address,
            'signer_address',
        )
        try:
            decoded = json.loads(events_json or '[]')
        except json.JSONDecodeError as exc:
            raise ValueError(f'events_json must be valid JSON: {exc.msg}') from exc
        if not isinstance(decoded, list):
            raise ValueError('events_json must be a JSON array')

        events = []
        for index, item in enumerate(decoded):
            if not isinstance(item, dict):
                raise ValueError(f'events_json[{index}] must be a JSON object')
            events.append(_event_params_from_mapping(item, f'events_json[{index}]'))

        client = self._client_for_address(signer)
        return [str(tx_hash) for tx_hash in client.batch_submit_events(events)]

    def query_mcr(self, did: str) -> dict[str, Any]:
        return self._query_json(did, 'mcr', 'query_mcr')

    def query_machine(self, did: str) -> dict[str, Any]:
        return self._query_json(did, 'machine', 'query_machine')

    def query_operator_machines(self, did: str) -> dict[str, Any]:
        return self._query_json(did, 'operator_machines', 'query_operator_machines')

    def get_smart_account_address(
        self,
        *,
        signer_address: str,
        owner: str,
        machine: str,
        daily_limit: str,
        salt: str,
    ) -> str:
        signer = self._resolve_default_proxy_signer(signer_address)
        client = self._client_for_address(signer)
        owner_address = self._normalize_external_address(owner or signer, 'owner')
        machine_address = self._normalize_external_address(
            machine or self.config.default_machine_address,
            'machine',
        )
        parsed_salt = _parse_uint256(salt, 'salt')
        try:
            return str(client.get_smart_account_address(
                owner=owner_address,
                machine=machine_address,
                salt=parsed_salt,
            ))
        except TypeError:
            parsed_daily_limit = _parse_uint256(daily_limit or '0', 'daily_limit')
            try:
                return str(client.get_smart_account_address(
                    owner=owner_address,
                    machine=machine_address,
                    daily_limit=parsed_daily_limit,
                    salt=parsed_salt,
                ))
            except Exception:  # noqa: BLE001
                return self._get_smart_account_address_deploy11(
                    client,
                    owner=owner_address,
                    machine=machine_address,
                    salt=parsed_salt,
                )
        except Exception:  # noqa: BLE001
            return self._get_smart_account_address_deploy11(
                client,
                owner=owner_address,
                machine=machine_address,
                salt=parsed_salt,
            )

    def deploy_smart_account(
        self,
        *,
        signer_address: str,
        owner: str,
        machine: str,
        daily_limit: str,
        salt: str,
    ) -> str:
        signer = self._resolve_default_proxy_signer(signer_address)
        client = self._client_for_address(signer)
        owner_address = self._normalize_external_address(owner or signer, 'owner')
        machine_address = self._normalize_external_address(
            machine or self.config.default_machine_address,
            'machine',
        )
        parsed_salt = _parse_uint256(salt, 'salt')
        try:
            return str(client.deploy_smart_account(
                owner=owner_address,
                machine=machine_address,
                salt=parsed_salt,
            ))
        except TypeError:
            parsed_daily_limit = _parse_uint256(daily_limit or '0', 'daily_limit')
            try:
                return str(client.deploy_smart_account(
                    owner=owner_address,
                    machine=machine_address,
                    daily_limit=parsed_daily_limit,
                    salt=parsed_salt,
                ))
            except Exception:  # noqa: BLE001
                return self._deploy_smart_account_deploy11(
                    client,
                    owner=owner_address,
                    machine=machine_address,
                    salt=parsed_salt,
                )
        except Exception:  # noqa: BLE001
            return self._deploy_smart_account_deploy11(
                client,
                owner=owner_address,
                machine=machine_address,
                salt=parsed_salt,
            )

    def bridge_nft(
        self,
        *,
        signer_address: str,
        token_id: int,
        source: str,
        destination: str,
        recipient: str,
        base_rpc_url: str,
        base_nft_address: str,
        options_hex: str,
    ) -> str:
        signer = self._resolve_default_proxy_signer(signer_address)
        client = self._client_for_address(signer)
        options = (
            _decode_hex(options_hex, 'options_hex')
            if (options_hex or '').strip()
            else _DEFAULT_LZ_RECEIVE_OPTIONS
        )
        if (source or '').strip().lower() == 'peaq':
            self._approve_machine_nft_adapter_if_needed(client, int(token_id))
        return str(client.bridge_nft(
            token_id=int(token_id),
            source=(source or '').strip().lower(),
            destination=(destination or '').strip().lower(),
            recipient=self._normalize_external_address(recipient, 'recipient'),
            base_rpc_url=(base_rpc_url or '').strip() or None,
            base_nft_address=(
                self._normalize_external_address(base_nft_address, 'base_nft_address')
                if (base_nft_address or '').strip()
                else None
            ),
            options=options,
        ))

    def wait_for_bridge_arrival(
        self,
        *,
        dst_rpc_url: str,
        dst_nft_address: str,
        token_id: int,
        timeout: int,
    ) -> bool:
        wait_timeout = int(timeout) if int(timeout) > 0 else 300
        address = self._normalize_external_address(dst_nft_address, 'dst_nft_address')
        return _wait_for_bridge_arrival_direct(
            dst_rpc_url=(dst_rpc_url or '').strip(),
            dst_nft_address=address,
            token_id=int(token_id),
            timeout=wait_timeout,
        )

    def _resolve_address(self, supplied: str, default: str, field: str) -> str:
        candidate = (supplied or '').strip() or (default or '').strip()
        if not candidate:
            raise ValueError(f'{field} is required')
        return self.wallets.normalize_address(candidate)

    def _resolve_default_proxy_signer(self, supplied: str) -> str:
        default = self.config.default_proxy_address or self.config.default_machine_address
        return self._resolve_address(supplied, default, 'signer_address')

    def _normalize_external_address(self, address: str, field: str) -> str:
        try:
            return self.wallets.normalize_address(address)
        except ValueError as exc:
            raise ValueError(f'{field} must be a valid 0x-prefixed EVM address') from exc

    def _normalize_did_address(self, value: str, field: str) -> str:
        text = (value or '').strip()
        if text.startswith('did:peaq:'):
            text = text.removeprefix('did:peaq:')
        return self._normalize_external_address(text, field)

    def _query_client(self):
        return SimpleNamespace(api_url=self.config.api_url, session=self._session)

    def _query_json(self, did: str, kind: str, operation: str) -> dict[str, Any]:
        from peaq_os_sdk.exceptions import ApiError
        from peaq_os_sdk.query._internal.did import validate_did
        from peaq_os_sdk.query.http_client import build_url, get_json

        validated_did = validate_did(did)
        if kind == 'operator_machines':
            path = f'/operator/{validated_did}/machines'
        else:
            path = f'/{kind}/{validated_did}'
        body = get_json(
            self._session,
            build_url(self.config.api_url, path),
            operation=operation,
        )
        if not isinstance(body, dict):
            raise ApiError(
                f'{operation}: MCR API returned a malformed response body',
                code='BAD_RESPONSE',
            )
        return dict(body)

    def _client_for_address(self, address: str):
        private_key = self.wallets.get_private_key(address)
        return self._new_client(private_key)

    def _new_client(self, private_key: str):
        self._require_base_config()
        from peaq_os_sdk import OperationalLimits, PeaqosClient

        limits = OperationalLimits(
            max_value_per_tx=self.config.operational_limits.max_value_per_tx,
            rate_limit_max_events=self.config.operational_limits.rate_limit_max_events,
            rate_limit_window_seconds=self.config.operational_limits.rate_limit_window_seconds,
        )
        return PeaqosClient(
            rpc_url=self.config.rpc_url,
            private_key=private_key,
            identity_registry=self.config.contracts.identity_registry,
            identity_staking=self.config.contracts.identity_staking,
            event_registry=self.config.contracts.event_registry,
            machine_nft=self.config.contracts.machine_nft,
            did_registry=self.config.contracts.did_registry,
            batch_precompile=self.config.contracts.batch_precompile,
            machine_account_factory=self.config.contracts.machine_account_factory or None,
            machine_nft_adapter=self.config.contracts.machine_nft_adapter or None,
            api_url=self.config.api_url,
            operational_limits=limits,
        )

    def _setup_faucet_2fa_prefixed(self, owner_address: str, qr_format: str) -> dict[str, Any]:
        body = self._post_faucet_json(
            '/faucet/2fa/setup',
            {'ownerAddress': owner_address, 'format': qr_format or self.config.default_qr_format},
            'setup_faucet_2fa',
        )
        data = body.get('data') if isinstance(body, dict) else None
        if not isinstance(data, dict):
            raise RuntimeError('setup_faucet_2fa: malformed data payload')
        return {
            'owner_address': str(data.get('ownerAddress') or owner_address),
            'otpauth_uri': str(data.get('otpauthUri') or ''),
            'qr_image_url': str(data.get('qrImageUrl') or ''),
        }

    def _confirm_faucet_2fa_prefixed(self, owner_address: str, two_factor_code: str) -> None:
        self._post_faucet_json(
            '/faucet/2fa/confirm',
            {'ownerAddress': owner_address, 'twoFactorCode': two_factor_code},
            'confirm_faucet_2fa',
        )

    def _post_faucet_json(self, path: str, payload: dict[str, Any], operation: str) -> dict[str, Any]:
        from peaq_os_sdk.exceptions import ApiError

        url = self.config.faucet_base_url.rstrip('/') + path
        try:
            response = self._session.post(url, json=payload, timeout=30)
        except requests.RequestException as exc:
            raise ApiError(
                f'{operation}: network request to {url} failed',
                code='NETWORK_ERROR',
            ) from exc
        try:
            body = response.json()
        except ValueError as exc:
            raise ApiError(
                f'{operation}: faucet at {url} returned a non-JSON response',
                code='INVALID_RESPONSE',
            ) from exc
        if not isinstance(body, dict):
            raise ApiError(f'{operation}: unexpected response envelope', code='UNEXPECTED_RESPONSE')
        if not response.ok:
            code = str(body.get('code') or response.status_code)
            message = str(body.get('message') or f'faucet error {code}')
            raise ApiError(f'{operation}: {message}', code=code)
        if body.get('status') != 'success':
            raise ApiError(f'{operation}: unexpected response envelope', code='UNEXPECTED_RESPONSE')
        return body

    def _get_deploy11_factory(self, client: Any):
        if not self.config.contracts.machine_account_factory:
            raise RuntimeError('peaq_os.contracts.machine_account_factory is required')
        return client.web3.eth.contract(
            address=client.web3.to_checksum_address(self.config.contracts.machine_account_factory),
            abi=_MACHINE_ACCOUNT_FACTORY_DEPLOY11_ABI,
        )

    def _get_smart_account_address_deploy11(
        self,
        client: Any,
        *,
        owner: str,
        machine: str,
        salt: int,
    ) -> str:
        factory = self._get_deploy11_factory(client)
        result = factory.functions.getAddress(
            client.web3.to_checksum_address(owner),
            client.web3.to_checksum_address(machine),
            int(salt),
        ).call()
        if not isinstance(result, str) or not result.startswith('0x') or len(result) != 42:
            raise RuntimeError('MachineAccountFactory.getAddress returned an invalid address')
        return result

    def _deploy_smart_account_deploy11(
        self,
        client: Any,
        *,
        owner: str,
        machine: str,
        salt: int,
    ) -> str:
        from peaq_os_sdk.utils.transaction import send_and_await

        factory = self._get_deploy11_factory(client)
        receipt = send_and_await(
            client.web3,
            client.account,
            factory,
            'createAccount',
            args=[
                client.web3.to_checksum_address(owner),
                client.web3.to_checksum_address(machine),
                int(salt),
            ],
        )
        events = factory.events.AccountCreated().process_receipt(receipt)
        if not events:
            raise RuntimeError('No AccountCreated event found in transaction receipt')
        account = events[0]['args']['account']
        if not isinstance(account, str) or not account.startswith('0x') or len(account) != 42:
            raise RuntimeError('AccountCreated event has a malformed account address')
        return account

    def _approve_machine_nft_adapter_if_needed(self, client: Any, token_id: int) -> None:
        adapter = self.config.contracts.machine_nft_adapter
        if not adapter:
            raise RuntimeError('peaq_os.contracts.machine_nft_adapter is required')
        adapter_address = client.web3.to_checksum_address(adapter)
        expected_nft_address = client.web3.to_checksum_address(self.config.contracts.machine_nft)
        adapter_contract = client.web3.eth.contract(
            address=adapter_address,
            abi=_MACHINE_NFT_ADAPTER_TOKEN_ABI,
        )
        wrapped_nft_address = client.web3.to_checksum_address(
            adapter_contract.functions.token().call()
        )
        if wrapped_nft_address.lower() != expected_nft_address.lower():
            raise RuntimeError(
                'peaq_os.contracts.machine_nft_adapter wraps a different MachineNFT: '
                f'adapter token()={wrapped_nft_address}, '
                f'peaq_os.contracts.machine_nft={expected_nft_address}'
            )
        owner_address = client.web3.to_checksum_address(client.address)

        approved = client.machine_nft.functions.getApproved(int(token_id)).call()
        if str(approved).lower() == adapter_address.lower():
            return
        approved_for_all = client.machine_nft.functions.isApprovedForAll(
            owner_address,
            adapter_address,
        ).call()
        if bool(approved_for_all):
            return

        from peaq_os_sdk.utils.transaction import send_and_await

        send_and_await(
            client.web3,
            client.account,
            client.machine_nft,
            'approve',
            args=[adapter_address, int(token_id)],
        )

    def _require_base_config(self) -> None:
        missing = []
        if not self.config.rpc_url:
            missing.append('peaq_os.rpc_url')
        for key, value in {
            'identity_registry': self.config.contracts.identity_registry,
            'identity_staking': self.config.contracts.identity_staking,
            'event_registry': self.config.contracts.event_registry,
            'machine_nft': self.config.contracts.machine_nft,
            'did_registry': self.config.contracts.did_registry,
            'batch_precompile': self.config.contracts.batch_precompile,
        }.items():
            if not value:
                missing.append(f'peaq_os.contracts.{key}')
        if missing:
            raise RuntimeError('missing peaqOS config: ' + ', '.join(missing))


def _decode_optional_hex(value: str, field: str) -> bytes | None:
    text = (value or '').strip()
    if not text:
        return None
    return _decode_hex(text, field)


def _decode_hex(value: str, field: str) -> bytes:
    text = (value or '').strip()
    if text.startswith('0x'):
        text = text[2:]
    if len(text) % 2 != 0:
        raise ValueError(f'{field} must contain an even number of hex characters')
    try:
        return bytes.fromhex(text)
    except ValueError as exc:
        raise ValueError(f'{field} must be hex encoded') from exc


def _call_register_machine(client: Any) -> int:
    if hasattr(client, 'register_machine'):
        return int(client.register_machine())
    return int(client.register_agent())


def _event_params(
    *,
    machine_id: int,
    event_type: int,
    value: int,
    timestamp: int,
    raw_data_hex: str,
    trust_level: int,
    source_chain_id: int,
    source_tx_hash: str,
    metadata_hex: str,
):
    from peaq_os_sdk.types.events import SubmitEventParams

    source_hash = (source_tx_hash or '').strip() or None
    return SubmitEventParams(
        machine_id=int(machine_id),
        event_type=int(event_type),
        value=int(value),
        timestamp=int(timestamp),
        raw_data=_decode_optional_hex(raw_data_hex, 'raw_data_hex'),
        trust_level=int(trust_level),
        source_chain_id=int(source_chain_id),
        source_tx_hash=source_hash,
        metadata=_decode_hex(metadata_hex, 'metadata_hex') if metadata_hex else b'',
    )


def _event_params_from_mapping(raw: dict[str, Any], prefix: str):
    raw_data_hex = _first_present(raw, 'raw_data_hex', 'rawDataHex', 'raw_data', 'rawData')
    metadata_hex = _first_present(raw, 'metadata_hex', 'metadataHex', 'metadata')
    source_tx_hash = _first_present(raw, 'source_tx_hash', 'sourceTxHash')
    return _event_params(
        machine_id=_required(raw, prefix, 'machine_id', 'machineId'),
        event_type=_required(raw, prefix, 'event_type', 'eventType'),
        value=_required(raw, prefix, 'value'),
        timestamp=_required(raw, prefix, 'timestamp'),
        raw_data_hex=str(raw_data_hex or ''),
        trust_level=_required(raw, prefix, 'trust_level', 'trustLevel'),
        source_chain_id=_required(raw, prefix, 'source_chain_id', 'sourceChainId'),
        source_tx_hash=str(source_tx_hash or ''),
        metadata_hex=str(metadata_hex or ''),
    )


def _first_present(raw: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in raw:
            return raw[key]
    return None


def _required(raw: dict[str, Any], prefix: str, *keys: str) -> Any:
    value = _first_present(raw, *keys)
    if value is None or value == '':
        raise ValueError(f'{prefix}.{keys[0]} is required')
    return value


def _parse_uint256(value: str, field: str) -> int:
    text = str(value or '').strip()
    if not text:
        raise ValueError(f'{field} is required')
    try:
        parsed = int(text, 0)
    except ValueError as exc:
        raise ValueError(f'{field} must be an unsigned integer string') from exc
    if parsed < 0:
        raise ValueError(f'{field} must be an unsigned integer string')
    return parsed


def _wait_for_bridge_arrival_direct(
    *,
    dst_rpc_url: str,
    dst_nft_address: str,
    token_id: int,
    timeout: int,
) -> bool:
    if not dst_rpc_url:
        raise ValueError('dst_rpc_url is required')
    if timeout <= 60:
        raise ValueError('timeout must be greater than 60 seconds')

    from peaq_os_sdk.abis import load_abi
    from web3 import Web3

    web3 = Web3(Web3.HTTPProvider(dst_rpc_url, request_kwargs={'timeout': 30}))
    contract = web3.eth.contract(
        address=web3.to_checksum_address(dst_nft_address),
        abi=load_abi('MachineNFT'),
    )
    deadline = time.monotonic() + timeout

    while True:
        try:
            owner = contract.functions.ownerOf(int(token_id)).call()
            return isinstance(owner, str) and bool(owner) and owner.lower() != _ZERO_EVM_ADDRESS
        except Exception as exc:  # noqa: BLE001
            if not _is_nonexistent_token_error(exc):
                raise

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False
        time.sleep(min(10.0, remaining))


def _is_nonexistent_token_error(exc: BaseException) -> bool:
    text = str(exc).lower()
    return any(marker in text for marker in _NONEXISTENT_TOKEN_MARKERS)


def _bytes32_to_hex(value: object) -> str:
    if isinstance(value, (bytes, bytearray)):
        return '0x' + bytes(value).hex()
    text = str(value)
    return text if text.startswith('0x') else '0x' + text
