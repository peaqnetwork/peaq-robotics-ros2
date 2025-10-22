#!/usr/bin/env python3
import json
import time
import threading
from typing import Optional

import rclpy
from rclpy.node import Node

from peaq_ros2_interfaces.msg import StorageIngest, StorageResult


class RosE2EIngestAndWait(Node):
    def __init__(self) -> None:
        super().__init__('ros_e2e_ingest_and_wait')
        self.publisher = self.create_publisher(StorageIngest, '/peaq/storage/ingest', 10)
        self.subscription = self.create_subscription(
            StorageResult,
            '/peaq/storage/status',
            self._handle_status,
            10,
        )
        self._target_key: Optional[str] = None
        self._tx_hash: Optional[str] = None
        self._ipfs_url: Optional[str] = None
        self._status: Optional[str] = None
        self._event = threading.Event()

    def publish_and_wait(self, *, content: dict, robot_id: str, timeout_sec: float = 90.0) -> Optional[str]:
        key = f'ROS_E2E_{int(time.time())}'
        self._target_key = key

        msg = StorageIngest()
        msg.key = key
        msg.is_file = False
        msg.file_path = ''
        msg.content = json.dumps(content)
        msg.content_type = 'application/json'
        msg.metadata_json = json.dumps({'robot_id': robot_id, 'ts': int(time.time())})

        # Publish a few times to ensure delivery
        for _ in range(5):
            self.publisher.publish(msg)
            time.sleep(0.2)

        # Wait for first status (may not include tx hash)
        first_ok = self._event.wait(timeout=timeout_sec)
        if not first_ok:
            self.get_logger().error('Timed out waiting for first StorageResult')
            return None

        # Print what we have so far
        print(f'PUBLISHED_KEY: {key}')
        if self._ipfs_url:
            print(f'ROS_STORAGE_IPFS_URL: {self._ipfs_url}')
        if self._status:
            print(f'ROS_STORAGE_STATUS: {self._status}')

        # Keep waiting (up to timeout) for tx hash if not yet available
        deadline = time.time() + timeout_sec
        while self._tx_hash is None and time.time() < deadline:
            rclpy.spin_once(self, timeout_sec=0.2)

        if self._tx_hash:
            print(f'ROS_STORAGE_TX_HASH: {self._tx_hash}')
        else:
            print('ROS_STORAGE_TX_HASH:')
        return self._tx_hash

    def _handle_status(self, msg: StorageResult) -> None:
        if not self._target_key or msg.key != self._target_key:
            return
        # Capture fields
        if msg.tx_hash:
            self._tx_hash = msg.tx_hash
        if msg.ipfs_url:
            self._ipfs_url = msg.ipfs_url
        if msg.status:
            self._status = msg.status
        # Signal on first status for our key
        if not self._event.is_set():
            self._event.set()


def main():
    rclpy.init()
    node = RosE2EIngestAndWait()
    try:
        # Start executor in a background thread
        executor = rclpy.executors.SingleThreadedExecutor()
        executor.add_node(node)

        exec_thread = threading.Thread(target=executor.spin, daemon=True)
        exec_thread.start()

        tx = node.publish_and_wait(content={'hello': 'from_ros'}, robot_id='humanoid_001', timeout_sec=90.0)
        if not tx:
            raise SystemExit(1)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()


