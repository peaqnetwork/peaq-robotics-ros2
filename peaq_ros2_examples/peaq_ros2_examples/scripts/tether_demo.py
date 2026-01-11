#!/usr/bin/env python3
"""
Demo: peaq ROS2 + Tether WDK integration (peaq EVM USDT).

This demo expects `peaq_tether_node` to be running.

Recommended:
- Enable and configure `tether:` in the unified YAML config (copy example).
- Start the node via:
    ros2 launch peaq_ros2_examples demo_tether.launch.py config_yaml:=/ABS/PATH/peaq_robot.yaml
"""

import rclpy
from rclpy.node import Node

from peaq_ros2_interfaces.srv import TetherCreateWallet, TetherGetUsdtBalance, TetherTransferUsdt


class _Demo(Node):
    def __init__(self) -> None:
        super().__init__('peaq_tether_demo')
        self.create_cli = self.create_client(TetherCreateWallet, '/peaq_tether_node/wallet/create')
        self.balance_cli = self.create_client(TetherGetUsdtBalance, '/peaq_tether_node/usdt/balance')
        self.transfer_cli = self.create_client(TetherTransferUsdt, '/peaq_tether_node/usdt/transfer')

    def run(self) -> int:
        if not self.create_cli.wait_for_service(timeout_sec=10.0):
            self.get_logger().error('Service not available: /peaq_tether_node/wallet/create')
            return 2

        # 1) Create wallet (mnemonic stored locally; not exported)
        req = TetherCreateWallet.Request()
        req.label = 'demo_wallet'
        req.export_mnemonic = False
        fut = self.create_cli.call_async(req)
        rclpy.spin_until_future_complete(self, fut)
        res = fut.result()
        if not res or not res.success:
            self.get_logger().error(f'CreateWallet failed: {getattr(res, "error", "")}')
            return 3
        self.get_logger().info(f'Created address={res.address}')

        # 2) USDT balance
        breq = TetherGetUsdtBalance.Request()
        breq.address = res.address
        bfut = self.balance_cli.call_async(breq)
        rclpy.spin_until_future_complete(self, bfut)
        bres = bfut.result()
        if not bres or not bres.success:
            self.get_logger().error(f'Balance failed: {getattr(bres, "error", "")}')
            return 4
        self.get_logger().info(f'USDT balance: raw={bres.balance_raw} formatted={bres.balance_formatted}')

        # 3) Optional: Dry-run USDT transfer (only if balance > 0).
        # For a freshly created wallet, balance is typically 0, and ERC20 transfer simulation
        # will revert with insufficient balance. That's expected; we skip to keep the demo green.
        try:
            has_funds = int(bres.balance_raw or '0') > 0
        except Exception:
            has_funds = False

        if has_funds:
            treq = TetherTransferUsdt.Request()
            treq.from_address = res.address
            treq.to_address = res.address
            treq.amount = '0.01'
            treq.dry_run = True
            tfut = self.transfer_cli.call_async(treq)
            rclpy.spin_until_future_complete(self, tfut)
            tres = tfut.result()
            if not tres or not tres.success:
                self.get_logger().error(f'Transfer (dry-run) failed: {getattr(tres, "error", "")}')
                return 5
            self.get_logger().info(f'Transfer dry-run status={tres.status} tx_hash={tres.tx_hash}')
        else:
            self.get_logger().info('Skipping transfer dry-run (wallet has 0 USDT).')

        return 0


def main() -> None:
    rclpy.init()
    node = _Demo()
    try:
        code = node.run()
    finally:
        try:
            node.destroy_node()
        except Exception:
            pass
        rclpy.shutdown()
    raise SystemExit(code)


if __name__ == '__main__':
    main()

