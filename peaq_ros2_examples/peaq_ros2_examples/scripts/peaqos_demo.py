#!/usr/bin/env python3
"""Small peaqOS ROS 2 demo: create a wallet and validate one event."""

import time

import rclpy
from rclpy.node import Node

from peaq_ros2_interfaces.srv import PeaqosCreateWallet, PeaqosValidateEvent


class _Demo(Node):
    def __init__(self) -> None:
        super().__init__('peaqos_demo')
        self.create_wallet = self.create_client(PeaqosCreateWallet, '/peaqos_node/wallet/create')
        self.validate_event = self.create_client(PeaqosValidateEvent, '/peaqos_node/events/validate')

    def run(self) -> int:
        if not self.create_wallet.wait_for_service(timeout_sec=10.0):
            self.get_logger().error('Service not available: /peaqos_node/wallet/create')
            return 2

        req = PeaqosCreateWallet.Request()
        req.label = 'peaqos_demo_machine'
        fut = self.create_wallet.call_async(req)
        rclpy.spin_until_future_complete(self, fut)
        res = fut.result()
        if not res or not res.success:
            self.get_logger().error(f'Create wallet failed: {getattr(res, "error", "")}')
            return 3
        self.get_logger().info(f'Created peaqOS machine wallet: {res.address}')

        if not self.validate_event.wait_for_service(timeout_sec=10.0):
            self.get_logger().error('Service not available: /peaqos_node/events/validate')
            return 4

        vreq = PeaqosValidateEvent.Request()
        vreq.machine_id = 1
        vreq.event_type = 1
        vreq.value = 1
        vreq.timestamp = int(time.time())
        vreq.raw_data_hex = '0x73656e736f723a6f6b'
        vreq.trust_level = 0
        vreq.source_chain_id = 3338
        vreq.source_tx_hash = ''
        vreq.metadata_hex = '0x7b7d'
        vfut = self.validate_event.call_async(vreq)
        rclpy.spin_until_future_complete(self, vfut)
        vres = vfut.result()
        if not vres or not vres.success:
            self.get_logger().error(f'Validate event failed: {getattr(vres, "error", "")}')
            return 5
        self.get_logger().info(f'Validated event data_hash={vres.data_hash}')
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
