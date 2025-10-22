#!/usr/bin/env python3
import json
import time
import hashlib
import sys

import rclpy
from rclpy.node import Node

from peaq_ros2_interfaces.msg import StorageIngest
from peaq_ros2_interfaces.srv import StoreReadData

try:
    import requests
    from nacl.signing import VerifyKey
except Exception as e:
    print("Missing deps: pip install requests pynacl", file=sys.stderr)
    raise


class IngestDemo(Node):
    def __init__(self, key: str, gateway: str = 'https://ipfs.io/ipfs'):
        super().__init__('ingest_demo')
        self.key = key
        self.gateway = gateway.rstrip('/')
        self.pub = self.create_publisher(StorageIngest, 'peaq/storage/ingest', 10)
        self.client = self.create_client(StoreReadData, '/peaq_core_node/storage/read')

    def publish_once(self):
        msg = StorageIngest()
        msg.key = self.key
        msg.is_file = False
        msg.file_path = ''
        msg.content = json.dumps({"hello": "world"})
        msg.content_type = 'application/json'
        msg.metadata_json = json.dumps({"robot_id": "humanoid_001", "ts": int(time.time())})
        self.pub.publish(msg)
        self.get_logger().info(f'Published StorageIngest for key={self.key}')

    def read_back(self, timeout_sec: float = 30.0) -> str:
        if not self.client.wait_for_service(timeout_sec=timeout_sec):
            raise RuntimeError('storage/read service not available')
        req = StoreReadData.Request()
        req.key = self.key
        future = self.client.call_async(req)
        rclpy.spin_until_future_complete(self, future, timeout_sec=timeout_sec)
        if not future.done() or future.result() is None:
            raise RuntimeError('storage/read call failed or timed out')
        return future.result().value_json

    def fetch(self, cid: str) -> bytes:
        url = f'{self.gateway}/{cid}'
        r = requests.get(url, timeout=20)
        r.raise_for_status()
        return r.content

    def verify(self, envelope_bytes: bytes, raw_bytes: bytes) -> bool:
        env = json.loads(envelope_bytes.decode('utf-8'))
        sha = hashlib.sha256(raw_bytes).hexdigest()
        hdr, prf = env['header'], env['proof']
        challenge = f"{sha}|{hdr['createdAt']}|{hdr['robotId']}".encode()
        VerifyKey(bytes.fromhex(prf['publicKeyHex'])).verify(challenge, bytes.fromhex(prf['signatureHex']))
        self.get_logger().info(f"dataSha256 matched: {env['payload']['dataSha256'] == sha}")
        return True


def main():
    key = f'E2E_TEST_SCRIPT_{int(time.time())}'
    gateway = 'https://ipfs.io/ipfs'
    if len(sys.argv) > 1:
        key = sys.argv[1]
    if len(sys.argv) > 2:
        gateway = sys.argv[2]

    rclpy.init()
    node = IngestDemo(key, gateway)
    try:
        node.publish_once()
        time.sleep(1.0)

        deadline = time.time() + 120.0
        value_json = ''
        while time.time() < deadline:
            try:
                value_json = node.read_back(30.0)
            except Exception as exc:
                node.get_logger().warning(f'storage/read error: {exc}; retrying...')
                time.sleep(5.0)
                continue

            try:
                parsed = json.loads(value_json)
            except json.JSONDecodeError:
                parsed = {}
            if isinstance(parsed, dict) and parsed.get('exists'):
                break
            node.get_logger().info('Value not available yet; retrying...')
            time.sleep(5.0)

        node.get_logger().info(f'value_json: {value_json[:120]}...')

        # value_json could be '{"envelopeCid":"..."}' or just '"CID"' or 'CID'
        envelope_cid = ''
        try:
            obj = json.loads(value_json)
            if isinstance(obj, dict):
                if 'envelopeCid' in obj:
                    envelope_cid = obj['envelopeCid']
                elif isinstance(obj.get('data'), dict) and 'envelopeCid' in obj['data']:
                    envelope_cid = obj['data']['envelopeCid']
                elif isinstance(obj, str):
                    envelope_cid = obj
            elif isinstance(obj, str):
                envelope_cid = obj
        except json.JSONDecodeError:
            envelope_cid = value_json.strip().strip('"')

        if not envelope_cid:
            raise RuntimeError('No envelopeCid parsed from value_json')

        node.get_logger().info(f'envelopeCid: {envelope_cid}')
        envelope = node.fetch(envelope_cid)
        data_cid = json.loads(envelope.decode('utf-8'))['payload']['dataCid']
        node.get_logger().info(f'dataCid: {data_cid}')
        raw = node.fetch(data_cid)

        node.verify(envelope, raw)
        print('OK: signature verified; data matches envelope')
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
