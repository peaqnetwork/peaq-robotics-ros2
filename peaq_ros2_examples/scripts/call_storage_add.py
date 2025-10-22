#!/usr/bin/env python3
import os
import json
import time
import rclpy
from rclpy.node import Node
from peaq_ros2_interfaces.srv import StoreAddData


class StorageAddClient(Node):
    def __init__(self) -> None:
        super().__init__('storage_add_client')
        self.client = self.create_client(StoreAddData, '/peaq_core_node/storage/add')

    def call_add(self, key: str, envelope_cid: str, timeout_sec: float = 120.0) -> str:
        if not self.client.wait_for_service(timeout_sec=10.0):
            raise RuntimeError('storage/add service not available')
        req = StoreAddData.Request()
        req.key = key
        req.value_json = json.dumps({'envelopeCid': envelope_cid})
        req.mode = ''
        fut = self.client.call_async(req)
        rclpy.spin_until_future_complete(self, fut, timeout_sec=timeout_sec)
        if not fut.done() or fut.result() is None:
            raise RuntimeError('storage/add call timed out')
        result = fut.result().result or ''
        print('RESULT:', result)
        if result.startswith('Success:'):
            tx = result.split(':', 1)[1].strip()
            print('TX_HASH:', tx)
            return tx
        raise RuntimeError(result)


def main():
    rclpy.init()
    node = StorageAddClient()
    try:
        key = os.environ.get('ADD_KEY') or f'ROS_E2E_MANUAL_{int(time.time())}'
        cid = os.environ.get('ADD_CID') or ''
        if not cid:
            raise RuntimeError('ADD_CID env is required')
        node.call_add(key, cid)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()


