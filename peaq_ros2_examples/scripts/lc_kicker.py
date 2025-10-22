#!/usr/bin/env python3
import sys
import time
import rclpy
from rclpy.node import Node
from lifecycle_msgs.srv import ChangeState, GetState


TARGETS = [
    '/peaq_core_node',
    '/peaq_events_node',
    '/peaq_humanoid_bridge_node',
]


class LifecycleKicker(Node):
    def __init__(self) -> None:
        super().__init__('peaq_lifecycle_kicker')

    def wait_ready(self, service_name: str, timeout_sec: float = 5.0) -> bool:
        client = self.create_client(ChangeState, service_name)
        end = time.time() + timeout_sec
        while time.time() < end and not client.wait_for_service(timeout_sec=0.2):
            pass
        return client.service_is_ready()

    def call_change(self, node_name: str, transition_id: int, timeout_sec: float = 5.0) -> bool:
        srv_name = f'{node_name}/change_state'
        if not self.wait_ready(srv_name, timeout_sec):
            self.get_logger().warning(f'Lifecycle service not ready: {srv_name}')
            return False
        client = self.create_client(ChangeState, srv_name)
        req = ChangeState.Request()
        req.transition.id = transition_id
        fut = client.call_async(req)
        rclpy.spin_until_future_complete(self, fut, timeout_sec=timeout_sec)
        if fut.result() is None:
            self.get_logger().warning(f'No response from {srv_name}')
            return False
        return bool(fut.result().success)

    def get_state(self, node_name: str, timeout_sec: float = 3.0) -> str:
        srv_name = f'{node_name}/get_state'
        client = self.create_client(GetState, srv_name)
        end = time.time() + timeout_sec
        while time.time() < end and not client.wait_for_service(timeout_sec=0.2):
            pass
        if not client.service_is_ready():
            return 'unknown'
        fut = client.call_async(GetState.Request())
        rclpy.spin_until_future_complete(self, fut, timeout_sec=timeout_sec)
        if fut.result():
            return fut.result().current_state.label
        return 'unknown'


def main() -> int:
    rclpy.init()
    node = LifecycleKicker()
    try:
        for n in TARGETS:
            before = node.get_state(n)
            node.get_logger().info(f'{n} state(before) = {before}')
            ok_cfg = node.call_change(n, 1)
            node.get_logger().info(f'{n} configure -> {ok_cfg}')
            ok_act = node.call_change(n, 3)
            node.get_logger().info(f'{n} activate  -> {ok_act}')
            after = node.get_state(n)
            node.get_logger().info(f'{n} state(after)  = {after}')
    finally:
        node.destroy_node()
        rclpy.shutdown()
    return 0


if __name__ == '__main__':
    sys.exit(main())


