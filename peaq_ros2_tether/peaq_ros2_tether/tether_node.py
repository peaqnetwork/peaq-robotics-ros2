from __future__ import annotations

import os
from typing import Any, Dict

import rclpy
from rclpy.node import Node

from peaq_ros2_interfaces.srv import TetherCreateWallet, TetherGetUsdtBalance, TetherTransferUsdt

from .config import load_tether_config_from_params
from .tether_client import TetherWDKClient, resolve_installed_cli_path


class TetherNode(Node):
    """
    ROS2 node exposing Tether WDK (EVM wallet + USDT ERC20) via services.

    Security invariants:
    - Wallet secrets (mnemonic) are stored locally in a shared registry file.
    - We never accept private keys / mnemonic over ROS services.
    - Mnemonic export is gated by config `tether.wallet_registry.unsafe_export_mnemonic`.
    """

    def __init__(self) -> None:
        super().__init__('peaq_tether_node')

        # Match existing repo pattern: allow unified YAML overlay
        self.declare_parameter('config.yaml_path', '')
        self.declare_parameter('tether.enabled', False)
        self.declare_parameter('tether.evm.rpc_url', '')
        self.declare_parameter('tether.usdt.contract', '')
        self.declare_parameter('tether.usdt.decimals', 6)
        self.declare_parameter('tether.wallet_registry.path', '~/.peaq_robot/tether_wallets.json')
        self.declare_parameter('tether.wallet_registry.unsafe_export_mnemonic', False)
        self.declare_parameter('tether.node_bin', 'node')

        # NOTE: ros2 CLI interprets unquoted 0x... values as numbers (DOUBLE),
        # which breaks parameter typing for string params like tether.usdt.contract.
        # Always pass contract addresses quoted in launch/CLI, e.g.:
        #   -p tether.usdt.contract:=\"0xabc...\"
        # For extra safety, if an override arrives as numeric, we coerce it to a hex-ish string.

        params: Dict[str, Any] = {}
        for name in self._parameters.keys():
            val = self.get_parameter(name).value
            # Defensive conversion for mis-typed CLI override (e.g., 0x.. parsed as DOUBLE).
            if name == 'tether.usdt.contract' and isinstance(val, float):
                # Best effort: represent as integer without scientific notation.
                try:
                    val = hex(int(val))
                except Exception:
                    val = str(val)
            params[name] = val

        self.cfg = load_tether_config_from_params(params)

        if not self.cfg.enabled:
            self.get_logger().warn(
                'Tether integration is disabled (tether.enabled=false). '
                'Services will be available but will return errors until enabled.'
            )

        if not self.cfg.usdt_contract:
            self.get_logger().warn('tether.usdt.contract is empty; balance/transfer will fail until configured.')

        if not self.cfg.evm_rpc_url:
            self.get_logger().warn('tether.evm.rpc_url is empty; wallet/balance/transfer will fail until configured.')

        cli_path = resolve_installed_cli_path()
        self._client = TetherWDKClient(
            node_bin=self.cfg.node_bin,
            cli_path=cli_path,
            evm_rpc_url=self.cfg.evm_rpc_url,
            usdt_contract=self.cfg.usdt_contract,
            usdt_decimals=self.cfg.usdt_decimals,
            wallet_registry_path=self.cfg.wallet_registry_path,
            unsafe_export_mnemonic=self.cfg.unsafe_export_mnemonic,
        )

        # Services
        self._srv_create = self.create_service(TetherCreateWallet, '~/wallet/create', self._handle_create_wallet)
        self._srv_balance = self.create_service(TetherGetUsdtBalance, '~/usdt/balance', self._handle_usdt_balance)
        self._srv_transfer = self.create_service(TetherTransferUsdt, '~/usdt/transfer', self._handle_usdt_transfer)

        self.get_logger().info('peaq_tether_node ready')

    def _reject(self, msg: str):
        self.get_logger().error(msg)

    def _handle_create_wallet(self, request: TetherCreateWallet.Request, response: TetherCreateWallet.Response):
        if not self.cfg.enabled:
            response.success = False
            response.error = 'tether.enabled=false'
            return response

        export_requested = bool(request.export_mnemonic)
        export_allowed = bool(self.cfg.unsafe_export_mnemonic)
        export = export_requested and export_allowed

        if export_requested and not export_allowed:
            self.get_logger().warn('Mnemonic export requested but disabled by config; returning empty mnemonic.')

        label = (request.label or '').strip() or 'robot_wallet'
        res = self._client.create_wallet(label=label, export_mnemonic=export)
        if not res.ok:
            response.success = False
            response.error = res.error
            return response

        response.address = str(res.data.get('address') or '')
        response.mnemonic = str(res.data.get('mnemonic') or '') if export else ''
        response.success = True
        response.error = ''
        return response

    def _handle_usdt_balance(self, request: TetherGetUsdtBalance.Request, response: TetherGetUsdtBalance.Response):
        if not self.cfg.enabled:
            response.success = False
            response.error = 'tether.enabled=false'
            return response

        address = (request.address or '').strip()
        if not address:
            response.success = False
            response.error = 'address is required'
            return response

        res = self._client.get_usdt_balance(address=address)
        if not res.ok:
            response.success = False
            response.error = res.error
            return response

        response.balance_raw = str(res.data.get('balance_raw') or '')
        response.balance_formatted = str(res.data.get('balance_formatted') or '')
        response.success = True
        response.error = ''
        return response

    def _handle_usdt_transfer(self, request: TetherTransferUsdt.Request, response: TetherTransferUsdt.Response):
        if not self.cfg.enabled:
            response.success = False
            response.error = 'tether.enabled=false'
            return response

        from_address = (request.from_address or '').strip()
        to_address = (request.to_address or '').strip()
        amount = (request.amount or '').strip()
        dry_run = bool(request.dry_run)

        if not from_address:
            response.success = False
            response.error = 'from_address is required'
            return response
        if not to_address:
            response.success = False
            response.error = 'to_address is required'
            return response
        if not amount:
            response.success = False
            response.error = 'amount is required'
            return response

        res = self._client.transfer_usdt(from_address=from_address, to_address=to_address, amount=amount, dry_run=dry_run)
        if not res.ok:
            response.success = False
            response.error = res.error
            return response

        response.tx_hash = str(res.data.get('tx_hash') or '')
        response.status = str(res.data.get('status') or '')
        response.success = True
        response.error = ''
        return response


def main(args=None) -> None:
    rclpy.init(args=args)
    node = TetherNode()
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

