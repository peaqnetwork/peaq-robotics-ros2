"""ROS 2 node exposing peaqOS machine onboarding services."""

from __future__ import annotations

import json
from typing import Any, Dict

import rclpy
from rclpy.node import Node

from peaq_ros2_interfaces.srv import (
    PeaqosBatchSubmitEvents,
    PeaqosBridgeNft,
    PeaqosConfirmFaucet2FA,
    PeaqosCreateWallet,
    PeaqosDeleteWallet,
    PeaqosDeploySmartAccount,
    PeaqosFundWallet,
    PeaqosGetWallet,
    PeaqosGetSmartAccountAddress,
    PeaqosListWallets,
    PeaqosMintNft,
    PeaqosQueryMachine,
    PeaqosQueryMcr,
    PeaqosQueryOperatorMachines,
    PeaqosReadDidAttribute,
    PeaqosRegisterAgent,
    PeaqosRegisterFor,
    PeaqosRegisterMachine,
    PeaqosSetupFaucet2FA,
    PeaqosSubmitEvent,
    PeaqosTokenIdOf,
    PeaqosValidateEvent,
    PeaqosWaitForBridgeArrival,
    PeaqosWriteMachineDidAttributes,
    PeaqosWriteProxyDidAttributes,
)

from .adapter import PeaqosAdapter, error_info
from .config import load_peaqos_config_from_params


class PeaqosNode(Node):
    """Service node for peaqOS onboarding and event preflight operations."""

    def __init__(self) -> None:
        super().__init__('peaqos_node')
        self._declare_parameters()
        self.cfg = load_peaqos_config_from_params(self._collect_non_default_params())
        self.adapter = PeaqosAdapter(self.cfg)

        if not self.cfg.enabled:
            self.get_logger().warn(
                'peaqOS integration is disabled (peaq_os.enabled=false). '
                'Services will return errors until enabled.'
            )
        if self.cfg.enabled and not self.cfg.rpc_url:
            self.get_logger().warn('peaq_os.rpc_url is empty; registration calls will fail.')

        self._srv_wallet = self.create_service(
            PeaqosCreateWallet,
            '~/wallet/create',
            self._handle_create_wallet,
        )
        self._srv_wallet_list = self.create_service(
            PeaqosListWallets,
            '~/wallet/list',
            self._handle_list_wallets,
        )
        self._srv_wallet_get = self.create_service(
            PeaqosGetWallet,
            '~/wallet/get',
            self._handle_get_wallet,
        )
        self._srv_wallet_delete = self.create_service(
            PeaqosDeleteWallet,
            '~/wallet/delete',
            self._handle_delete_wallet,
        )
        self._srv_setup_2fa = self.create_service(
            PeaqosSetupFaucet2FA,
            '~/faucet/setup_2fa',
            self._handle_setup_2fa,
        )
        self._srv_confirm_2fa = self.create_service(
            PeaqosConfirmFaucet2FA,
            '~/faucet/confirm_2fa',
            self._handle_confirm_2fa,
        )
        self._srv_fund = self.create_service(
            PeaqosFundWallet,
            '~/wallet/fund',
            self._handle_fund_wallet,
        )
        self._srv_register = self.create_service(
            PeaqosRegisterAgent,
            '~/agent/register',
            self._handle_register_agent,
        )
        self._srv_register_machine = self.create_service(
            PeaqosRegisterMachine,
            '~/machine/register',
            self._handle_register_machine,
        )
        self._srv_register_for = self.create_service(
            PeaqosRegisterFor,
            '~/agent/register_for',
            self._handle_register_for,
        )
        self._srv_register_machine_for = self.create_service(
            PeaqosRegisterFor,
            '~/machine/register_for',
            self._handle_register_for,
        )
        self._srv_mint_nft = self.create_service(
            PeaqosMintNft,
            '~/nft/mint',
            self._handle_mint_nft,
        )
        self._srv_token_id_of = self.create_service(
            PeaqosTokenIdOf,
            '~/nft/token_id_of',
            self._handle_token_id_of,
        )
        self._srv_read_did_attr = self.create_service(
            PeaqosReadDidAttribute,
            '~/did/read_attribute',
            self._handle_read_did_attribute,
        )
        self._srv_write_machine_did_attrs = self.create_service(
            PeaqosWriteMachineDidAttributes,
            '~/did/write_machine_attributes',
            self._handle_write_machine_did_attributes,
        )
        self._srv_write_proxy_did_attrs = self.create_service(
            PeaqosWriteProxyDidAttributes,
            '~/did/write_proxy_attributes',
            self._handle_write_proxy_did_attributes,
        )
        self._srv_validate_event = self.create_service(
            PeaqosValidateEvent,
            '~/events/validate',
            self._handle_validate_event,
        )
        self._srv_submit_event = self.create_service(
            PeaqosSubmitEvent,
            '~/events/submit',
            self._handle_submit_event,
        )
        self._srv_batch_submit_events = self.create_service(
            PeaqosBatchSubmitEvents,
            '~/events/batch_submit',
            self._handle_batch_submit_events,
        )
        self._srv_query_mcr = self.create_service(
            PeaqosQueryMcr,
            '~/mcr/query',
            self._handle_query_mcr,
        )
        self._srv_query_machine = self.create_service(
            PeaqosQueryMachine,
            '~/mcr/machine',
            self._handle_query_machine,
        )
        self._srv_query_operator_machines = self.create_service(
            PeaqosQueryOperatorMachines,
            '~/mcr/operator_machines',
            self._handle_query_operator_machines,
        )
        self._srv_smart_account_address = self.create_service(
            PeaqosGetSmartAccountAddress,
            '~/smart_account/address',
            self._handle_get_smart_account_address,
        )
        self._srv_smart_account_deploy = self.create_service(
            PeaqosDeploySmartAccount,
            '~/smart_account/deploy',
            self._handle_deploy_smart_account,
        )
        self._srv_bridge_nft = self.create_service(
            PeaqosBridgeNft,
            '~/bridge/nft',
            self._handle_bridge_nft,
        )
        self._srv_wait_for_bridge_arrival = self.create_service(
            PeaqosWaitForBridgeArrival,
            '~/bridge/wait_arrival',
            self._handle_wait_for_bridge_arrival,
        )

        self.get_logger().info('peaqos_node ready')

    def _declare_parameters(self) -> None:
        self.declare_parameter('config.yaml_path', '')
        self.declare_parameter('peaq_os.enabled', False)
        self.declare_parameter('peaq_os.rpc_url', '')
        self.declare_parameter('peaq_os.api_url', '')
        self.declare_parameter('peaq_os.faucet_base_url', '')
        self.declare_parameter('peaq_os.wallet_registry.path', '')
        self.declare_parameter('peaq_os.defaults.machine_address', '')
        self.declare_parameter('peaq_os.defaults.proxy_address', '')
        self.declare_parameter('peaq_os.defaults.owner_address', '')
        self.declare_parameter('peaq_os.faucet.qr_format', '')

        for key in (
            'identity_registry',
            'identity_staking',
            'event_registry',
            'machine_nft',
            'did_registry',
            'batch_precompile',
            'machine_account_factory',
            'machine_nft_adapter',
        ):
            self.declare_parameter(f'peaq_os.contracts.{key}', '')

        self.declare_parameter('peaq_os.operational_limits.max_value_per_tx', 0)
        self.declare_parameter('peaq_os.operational_limits.rate_limit_max_events', 0)
        self.declare_parameter('peaq_os.operational_limits.rate_limit_window_seconds', 0)

    def _collect_non_default_params(self) -> Dict[str, Any]:
        params: Dict[str, Any] = {
            'config.yaml_path': str(self.get_parameter('config.yaml_path').value or '').strip()
        }
        defaults: dict[str, Any] = {
            'peaq_os.enabled': False,
            'peaq_os.rpc_url': '',
            'peaq_os.api_url': '',
            'peaq_os.faucet_base_url': '',
            'peaq_os.wallet_registry.path': '',
            'peaq_os.defaults.machine_address': '',
            'peaq_os.defaults.proxy_address': '',
            'peaq_os.defaults.owner_address': '',
            'peaq_os.faucet.qr_format': '',
            'peaq_os.operational_limits.max_value_per_tx': 0,
            'peaq_os.operational_limits.rate_limit_max_events': 0,
            'peaq_os.operational_limits.rate_limit_window_seconds': 0,
        }
        for key in (
            'identity_registry',
            'identity_staking',
            'event_registry',
            'machine_nft',
            'did_registry',
            'batch_precompile',
            'machine_account_factory',
            'machine_nft_adapter',
        ):
            defaults[f'peaq_os.contracts.{key}'] = ''

        for key, default in defaults.items():
            value = self.get_parameter(key).value
            if isinstance(value, str):
                if value.strip() and value.strip() != str(default):
                    params[key] = value.strip()
            elif value != default:
                params[key] = value
        return params

    def _enabled(self, response: Any) -> bool:
        if self.cfg.enabled:
            return True
        response.success = False
        response.error = 'peaq_os.enabled=false'
        if hasattr(response, 'error_code'):
            response.error_code = 'DISABLED'
        return False

    def _fill_error(self, response: Any, exc: BaseException) -> Any:
        info = error_info(exc)
        response.success = False
        response.error = info.message
        if hasattr(response, 'error_code'):
            response.error_code = info.code
        if hasattr(response, 'error_field'):
            response.error_field = info.field
        return response

    def _handle_create_wallet(
        self,
        request: PeaqosCreateWallet.Request,
        response: PeaqosCreateWallet.Response,
    ):
        if not self._enabled(response):
            return response
        try:
            created = self.adapter.create_wallet((request.label or '').strip())
            response.address = created.address
            response.success = True
            response.error = ''
        except Exception as exc:  # noqa: BLE001
            return self._fill_error(response, exc)
        return response

    def _handle_list_wallets(
        self,
        request: PeaqosListWallets.Request,
        response: PeaqosListWallets.Response,
    ):
        _ = request
        if not self._enabled(response):
            return response
        try:
            response.wallets_json = json.dumps(self.adapter.list_wallets(), sort_keys=True)
            response.success = True
            response.error = ''
        except Exception as exc:  # noqa: BLE001
            return self._fill_error(response, exc)
        return response

    def _handle_get_wallet(
        self,
        request: PeaqosGetWallet.Request,
        response: PeaqosGetWallet.Response,
    ):
        if not self._enabled(response):
            return response
        try:
            response.wallet_json = json.dumps(
                self.adapter.get_wallet((request.address or '').strip()),
                sort_keys=True,
            )
            response.success = True
            response.error = ''
        except Exception as exc:  # noqa: BLE001
            return self._fill_error(response, exc)
        return response

    def _handle_delete_wallet(
        self,
        request: PeaqosDeleteWallet.Request,
        response: PeaqosDeleteWallet.Response,
    ):
        if not self._enabled(response):
            return response
        try:
            response.deleted = self.adapter.delete_wallet((request.address or '').strip())
            response.success = True
            response.error = ''
        except Exception as exc:  # noqa: BLE001
            return self._fill_error(response, exc)
        return response

    def _handle_setup_2fa(
        self,
        request: PeaqosSetupFaucet2FA.Request,
        response: PeaqosSetupFaucet2FA.Response,
    ):
        if not self._enabled(response):
            return response
        try:
            owner = (request.owner_address or '').strip() or self.cfg.default_owner_address
            qr_format = (request.qr_format or '').strip() or self.cfg.default_qr_format
            result = self.adapter.setup_faucet_2fa(owner, qr_format)
            response.owner_address = str(result.get('owner_address') or result.get('ownerAddress') or owner)
            response.otpauth_uri = str(result.get('otpauth_uri') or result.get('otpauthUri') or '')
            response.qr_image_url = str(result.get('qr_image_url') or result.get('qrImageUrl') or '')
            response.success = True
            response.error_code = ''
            response.error = ''
        except Exception as exc:  # noqa: BLE001
            return self._fill_error(response, exc)
        return response

    def _handle_confirm_2fa(
        self,
        request: PeaqosConfirmFaucet2FA.Request,
        response: PeaqosConfirmFaucet2FA.Response,
    ):
        if not self._enabled(response):
            return response
        try:
            owner = (request.owner_address or '').strip() or self.cfg.default_owner_address
            code = (request.two_factor_code or '').strip()
            self.adapter.confirm_faucet_2fa(owner, code)
            response.success = True
            response.error_code = ''
            response.error = ''
        except Exception as exc:  # noqa: BLE001
            return self._fill_error(response, exc)
        return response

    def _handle_fund_wallet(
        self,
        request: PeaqosFundWallet.Request,
        response: PeaqosFundWallet.Response,
    ):
        if not self._enabled(response):
            return response
        try:
            owner = (request.owner_address or '').strip() or self.cfg.default_owner_address
            request_id, result = self.adapter.fund_wallet(
                owner_address=owner,
                target_address=(request.target_address or '').strip(),
                chain_id=(request.chain_id or '').strip() or 'peaq',
                two_factor_code=(request.two_factor_code or '').strip(),
                request_id=(request.request_id or '').strip(),
            )
            response.status = str(result.get('status') or '')
            response.request_id = request_id
            response.tx_hash = str(result.get('tx_hash') or result.get('txHash') or '')
            response.funded_amount = str(result.get('funded_amount') or result.get('fundedAmount') or '')
            response.current_balance = str(result.get('current_balance') or result.get('currentBalance') or '')
            response.min_gas_balance = str(result.get('min_gas_balance') or result.get('minGasBalance') or '')
            response.success = True
            response.error_code = ''
            response.error = ''
        except Exception as exc:  # noqa: BLE001
            return self._fill_error(response, exc)
        return response

    def _handle_register_agent(
        self,
        request: PeaqosRegisterAgent.Request,
        response: PeaqosRegisterAgent.Response,
    ):
        if not self._enabled(response):
            return response
        try:
            response.machine_id = self.adapter.register_agent((request.address or '').strip())
            response.success = True
            response.error_code = ''
            response.error = ''
        except Exception as exc:  # noqa: BLE001
            return self._fill_error(response, exc)
        return response

    def _handle_register_machine(
        self,
        request: PeaqosRegisterMachine.Request,
        response: PeaqosRegisterMachine.Response,
    ):
        if not self._enabled(response):
            return response
        try:
            response.machine_id = self.adapter.register_machine((request.address or '').strip())
            response.success = True
            response.error_code = ''
            response.error = ''
        except Exception as exc:  # noqa: BLE001
            return self._fill_error(response, exc)
        return response

    def _handle_register_for(
        self,
        request: PeaqosRegisterFor.Request,
        response: PeaqosRegisterFor.Response,
    ):
        if not self._enabled(response):
            return response
        try:
            response.machine_id = self.adapter.register_for(
                (request.proxy_address or '').strip(),
                (request.machine_address or '').strip(),
            )
            response.success = True
            response.error_code = ''
            response.error = ''
        except Exception as exc:  # noqa: BLE001
            return self._fill_error(response, exc)
        return response

    def _handle_mint_nft(
        self,
        request: PeaqosMintNft.Request,
        response: PeaqosMintNft.Response,
    ):
        if not self._enabled(response):
            return response
        try:
            response.tx_hash = self.adapter.mint_nft(
                (request.signer_address or '').strip(),
                int(request.machine_id),
                (request.recipient or '').strip(),
            )
            response.success = True
            response.error_code = ''
            response.error_field = ''
            response.error = ''
        except Exception as exc:  # noqa: BLE001
            return self._fill_error(response, exc)
        return response

    def _handle_token_id_of(
        self,
        request: PeaqosTokenIdOf.Request,
        response: PeaqosTokenIdOf.Response,
    ):
        if not self._enabled(response):
            return response
        try:
            response.token_id = self.adapter.token_id_of(
                (request.signer_address or '').strip(),
                int(request.machine_id),
            )
            response.success = True
            response.error_code = ''
            response.error_field = ''
            response.error = ''
        except Exception as exc:  # noqa: BLE001
            return self._fill_error(response, exc)
        return response

    def _handle_write_machine_did_attributes(
        self,
        request: PeaqosWriteMachineDidAttributes.Request,
        response: PeaqosWriteMachineDidAttributes.Response,
    ):
        if not self._enabled(response):
            return response
        try:
            response.tx_hash = self.adapter.write_machine_did_attributes(
                signer_address=(request.signer_address or '').strip(),
                machine_id=int(request.machine_id),
                nft_token_id=int(request.nft_token_id),
                operator_did=(request.operator_did or '').strip(),
                documentation_url=(request.documentation_url or '').strip(),
                data_api=(request.data_api or '').strip(),
                data_visibility=(request.data_visibility or '').strip(),
            )
            response.success = True
            response.error_code = ''
            response.error_field = ''
            response.error = ''
        except Exception as exc:  # noqa: BLE001
            return self._fill_error(response, exc)
        return response

    def _handle_read_did_attribute(
        self,
        request: PeaqosReadDidAttribute.Request,
        response: PeaqosReadDidAttribute.Response,
    ):
        if not self._enabled(response):
            return response
        try:
            result = self.adapter.read_did_attribute(
                signer_address=(request.signer_address or '').strip(),
                did_address=(request.did_address or '').strip(),
                name=(request.name or '').strip(),
            )
            response.attribute_name = str(result.get('name') or '')
            response.value = str(result.get('value') or '')
            response.validity = int(result.get('validity') or 0)
            response.created = int(result.get('created') or 0)
            response.success = True
            response.error_code = ''
            response.error_field = ''
            response.error = ''
        except Exception as exc:  # noqa: BLE001
            return self._fill_error(response, exc)
        return response

    def _handle_write_proxy_did_attributes(
        self,
        request: PeaqosWriteProxyDidAttributes.Request,
        response: PeaqosWriteProxyDidAttributes.Response,
    ):
        if not self._enabled(response):
            return response
        try:
            response.tx_hash = self.adapter.write_proxy_did_attributes(
                signer_address=(request.signer_address or '').strip(),
                proxy_agent_id=int(request.proxy_agent_id),
                machine_ids=[int(machine_id) for machine_id in request.machine_ids],
            )
            response.success = True
            response.error_code = ''
            response.error_field = ''
            response.error = ''
        except Exception as exc:  # noqa: BLE001
            return self._fill_error(response, exc)
        return response

    def _handle_validate_event(
        self,
        request: PeaqosValidateEvent.Request,
        response: PeaqosValidateEvent.Response,
    ):
        if not self._enabled(response):
            return response
        try:
            response.data_hash = self.adapter.validate_event(
                machine_id=int(request.machine_id),
                event_type=int(request.event_type),
                value=int(request.value),
                timestamp=int(request.timestamp),
                raw_data_hex=request.raw_data_hex,
                trust_level=int(request.trust_level),
                source_chain_id=int(request.source_chain_id),
                source_tx_hash=request.source_tx_hash,
                metadata_hex=request.metadata_hex,
            )
            response.success = True
            response.error_code = ''
            response.error_field = ''
            response.error = ''
        except Exception as exc:  # noqa: BLE001
            return self._fill_error(response, exc)
        return response

    def _handle_submit_event(
        self,
        request: PeaqosSubmitEvent.Request,
        response: PeaqosSubmitEvent.Response,
    ):
        if not self._enabled(response):
            return response
        try:
            tx_hash, data_hash = self.adapter.submit_event(
                signer_address=(request.signer_address or '').strip(),
                machine_id=int(request.machine_id),
                event_type=int(request.event_type),
                value=int(request.value),
                timestamp=int(request.timestamp),
                raw_data_hex=request.raw_data_hex,
                trust_level=int(request.trust_level),
                source_chain_id=int(request.source_chain_id),
                source_tx_hash=request.source_tx_hash,
                metadata_hex=request.metadata_hex,
            )
            response.tx_hash = tx_hash
            response.data_hash = data_hash
            response.success = True
            response.error_code = ''
            response.error_field = ''
            response.error = ''
        except Exception as exc:  # noqa: BLE001
            return self._fill_error(response, exc)
        return response

    def _handle_batch_submit_events(
        self,
        request: PeaqosBatchSubmitEvents.Request,
        response: PeaqosBatchSubmitEvents.Response,
    ):
        if not self._enabled(response):
            return response
        try:
            tx_hashes = self.adapter.batch_submit_events(
                (request.signer_address or '').strip(),
                request.events_json,
            )
            response.tx_hashes_json = json.dumps(tx_hashes, sort_keys=True)
            response.success = True
            response.error_code = ''
            response.error_field = ''
            response.error = ''
        except Exception as exc:  # noqa: BLE001
            return self._fill_error(response, exc)
        return response

    def _handle_query_mcr(
        self,
        request: PeaqosQueryMcr.Request,
        response: PeaqosQueryMcr.Response,
    ):
        if not self._enabled(response):
            return response
        try:
            result = self.adapter.query_mcr((request.did or '').strip())
            response.result_json = json.dumps(result, sort_keys=True)
            response.success = True
            response.error_code = ''
            response.error_field = ''
            response.error = ''
        except Exception as exc:  # noqa: BLE001
            return self._fill_error(response, exc)
        return response

    def _handle_query_machine(
        self,
        request: PeaqosQueryMachine.Request,
        response: PeaqosQueryMachine.Response,
    ):
        if not self._enabled(response):
            return response
        try:
            result = self.adapter.query_machine((request.did or '').strip())
            response.result_json = json.dumps(result, sort_keys=True)
            response.success = True
            response.error_code = ''
            response.error_field = ''
            response.error = ''
        except Exception as exc:  # noqa: BLE001
            return self._fill_error(response, exc)
        return response

    def _handle_query_operator_machines(
        self,
        request: PeaqosQueryOperatorMachines.Request,
        response: PeaqosQueryOperatorMachines.Response,
    ):
        if not self._enabled(response):
            return response
        try:
            result = self.adapter.query_operator_machines((request.did or '').strip())
            response.result_json = json.dumps(result, sort_keys=True)
            response.success = True
            response.error_code = ''
            response.error_field = ''
            response.error = ''
        except Exception as exc:  # noqa: BLE001
            return self._fill_error(response, exc)
        return response

    def _handle_get_smart_account_address(
        self,
        request: PeaqosGetSmartAccountAddress.Request,
        response: PeaqosGetSmartAccountAddress.Response,
    ):
        if not self._enabled(response):
            return response
        try:
            response.address = self.adapter.get_smart_account_address(
                signer_address=(request.signer_address or '').strip(),
                owner=(request.owner or '').strip(),
                machine=(request.machine or '').strip(),
                daily_limit=(request.daily_limit or '').strip(),
                salt=(request.salt or '').strip(),
            )
            response.success = True
            response.error_code = ''
            response.error_field = ''
            response.error = ''
        except Exception as exc:  # noqa: BLE001
            return self._fill_error(response, exc)
        return response

    def _handle_deploy_smart_account(
        self,
        request: PeaqosDeploySmartAccount.Request,
        response: PeaqosDeploySmartAccount.Response,
    ):
        if not self._enabled(response):
            return response
        try:
            response.address = self.adapter.deploy_smart_account(
                signer_address=(request.signer_address or '').strip(),
                owner=(request.owner or '').strip(),
                machine=(request.machine or '').strip(),
                daily_limit=(request.daily_limit or '').strip(),
                salt=(request.salt or '').strip(),
            )
            response.success = True
            response.error_code = ''
            response.error_field = ''
            response.error = ''
        except Exception as exc:  # noqa: BLE001
            return self._fill_error(response, exc)
        return response

    def _handle_bridge_nft(
        self,
        request: PeaqosBridgeNft.Request,
        response: PeaqosBridgeNft.Response,
    ):
        if not self._enabled(response):
            return response
        try:
            response.tx_hash = self.adapter.bridge_nft(
                signer_address=(request.signer_address or '').strip(),
                token_id=int(request.token_id),
                source=(request.source or '').strip(),
                destination=(request.destination or '').strip(),
                recipient=(request.recipient or '').strip(),
                base_rpc_url=(request.base_rpc_url or '').strip(),
                base_nft_address=(request.base_nft_address or '').strip(),
                options_hex=(request.options_hex or '').strip(),
            )
            response.success = True
            response.error_code = ''
            response.error_field = ''
            response.error = ''
        except Exception as exc:  # noqa: BLE001
            return self._fill_error(response, exc)
        return response

    def _handle_wait_for_bridge_arrival(
        self,
        request: PeaqosWaitForBridgeArrival.Request,
        response: PeaqosWaitForBridgeArrival.Response,
    ):
        if not self._enabled(response):
            return response
        try:
            response.arrived = self.adapter.wait_for_bridge_arrival(
                dst_rpc_url=(request.dst_rpc_url or '').strip(),
                dst_nft_address=(request.dst_nft_address or '').strip(),
                token_id=int(request.token_id),
                timeout=int(request.timeout),
            )
            response.success = True
            response.error_code = ''
            response.error_field = ''
            response.error = ''
        except Exception as exc:  # noqa: BLE001
            return self._fill_error(response, exc)
        return response


def main(args=None) -> None:
    rclpy.init(args=args)
    node = PeaqosNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        try:
            node.destroy_node()
        except Exception:
            pass
        try:
            if rclpy.ok():
                rclpy.shutdown()
        except Exception:
            pass


if __name__ == '__main__':
    main()
