#!/usr/bin/env python3
"""End-to-end storage test with on-chain status + IPFS verification."""

import argparse
import json
import sys
import time
from dataclasses import dataclass, field
from typing import List, Optional

import requests
import rclpy
from rclpy.node import Node

from peaq_ros2_interfaces.msg import StorageIngest, StorageResult, TxStatus
from peaq_ros2_interfaces.srv import StoreReadData, IdentityRead


@dataclass
class StatusEntry:
    status: str
    cid: str
    tx_hash: str
    error: str


@dataclass
class TxEntry:
    phase: str
    block: int
    error: str


class StorageE2ETest(Node):
    def __init__(self, key: str, gateway: str, wait_sec: float) -> None:
        super().__init__('peaq_storage_e2e_test')
        self.key = key
        self.gateway = gateway.rstrip('/')
        self.wait_sec = wait_sec

        self.publisher = self.create_publisher(StorageIngest, 'peaq/storage/ingest', 10)
        self.store_client = self.create_client(StoreReadData, '/peaq_core_node/storage/read')
        self.identity_client = self.create_client(IdentityRead, '/peaq_core_node/identity/read')

        self.envelope_cid: Optional[str] = None
        self.tx_hash: Optional[str] = None
        self.status_history: List[StatusEntry] = []
        self.tx_history: List[TxEntry] = []
        self.final_phase: Optional[str] = None

        self.create_subscription(StorageResult, 'peaq/storage/status', self._status_cb, 10)
        self.create_subscription(TxStatus, 'peaq/tx_status', self._tx_cb, 10)

    def _status_cb(self, msg: StorageResult) -> None:
        if msg.key != self.key:
            return
        entry = StatusEntry(msg.status, msg.cid, msg.tx_hash, msg.error)
        self.status_history.append(entry)
        self.get_logger().info(f"storage/status: status={msg.status} tx_hash={msg.tx_hash} cid={msg.cid}")
        if msg.cid and not self.envelope_cid:
            self.envelope_cid = msg.cid
        if msg.tx_hash and not self.tx_hash:
            self.tx_hash = msg.tx_hash

    def _tx_cb(self, msg: TxStatus) -> None:
        if not self.tx_hash or msg.tx_hash != self.tx_hash:
            return
        entry = TxEntry(msg.phase, msg.block, msg.error)
        self.tx_history.append(entry)
        self.get_logger().info(f"tx_status: phase={msg.phase} block={msg.block} error={msg.error}")
        if msg.phase in ('FINALIZED', 'FAILED'):
            self.final_phase = msg.phase

    def publish_intent(self) -> None:
        msg = StorageIngest()
        msg.key = self.key
        msg.is_file = False
        msg.file_path = ''
        msg.content = json.dumps({'hello': 'world'})
        msg.content_type = 'application/json'
        msg.metadata_json = json.dumps({'robot_id': 'humanoid_001', 'ts': int(time.time())})
        self.publisher.publish(msg)
        self.get_logger().info('Published StorageIngest')

    def wait_for_status(self) -> None:
        deadline = time.time() + self.wait_sec
        while time.time() < deadline:
            rclpy.spin_once(self, timeout_sec=0.5)
            if self.envelope_cid and self.tx_hash and self.final_phase:
                return
        raise RuntimeError('Timed out waiting for storage status / tx finalisation')

    def call_storage_read(self) -> str:
        if not self.store_client.wait_for_service(timeout_sec=10.0):
            raise RuntimeError('storage/read service unavailable')
        req = StoreReadData.Request()
        req.key = self.key
        future = self.store_client.call_async(req)
        rclpy.spin_until_future_complete(self, future, timeout_sec=20.0)
        if not future.done() or future.result() is None:
            raise RuntimeError('storage/read call failed or timed out')
        return future.result().value_json

    def call_identity_read(self) -> Optional[str]:
        if not self.identity_client.wait_for_service(timeout_sec=5.0):
            self.get_logger().warn('identity/read service unavailable')
            return None
        req = IdentityRead.Request()
        future = self.identity_client.call_async(req)
        rclpy.spin_until_future_complete(self, future, timeout_sec=10.0)
        if not future.done() or future.result() is None:
            self.get_logger().warn('identity/read request failed')
            return None
        return future.result().doc_json

    def fetch_ipfs(self, cid: str) -> bytes:
        url = f'{self.gateway}/{cid}'
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        return resp.content

    def run(self) -> None:
        self.publish_intent()
        self.wait_for_status()

        value_json = self.call_storage_read()
        print(f'value_json: {value_json}')

        envelope_cid = self._parse_envelope_cid(value_json)
        print(f'envelopeCid: {envelope_cid}')

        envelope_bytes = self.fetch_ipfs(envelope_cid)
        envelope = json.loads(envelope_bytes.decode('utf-8'))
        data_cid = envelope['payload']['dataCid']
        data_bytes = self.fetch_ipfs(data_cid)
        print(f'dataCid: {data_cid}')
        print(f'data preview: {data_bytes[:80]!r}')

        self._verify_signature(envelope, data_bytes)

        did_doc = self.call_identity_read()
        if did_doc:
            print('identity document snippet:', did_doc[:160], '...')

        print('status history:', [entry.__dict__ for entry in self.status_history])
        print('tx hash:', self.tx_hash)
        print('tx history:', [entry.__dict__ for entry in self.tx_history])

    @staticmethod
    def _parse_envelope_cid(value_json: str) -> str:
        value_json = value_json.strip()
        try:
            obj = json.loads(value_json)
            if isinstance(obj, dict) and 'envelopeCid' in obj:
                return obj['envelopeCid']
            if isinstance(obj, str):
                return obj.strip('"')
        except json.JSONDecodeError:
            pass
        return value_json.strip('"')

    def _verify_signature(self, envelope: dict, data_bytes: bytes) -> None:
        from nacl.signing import VerifyKey

        data_sha = envelope['payload']['dataSha256']
        import hashlib
        computed_sha = hashlib.sha256(data_bytes).hexdigest()
        if data_sha != computed_sha:
            raise RuntimeError(f'Hash mismatch: envelope={data_sha} computed={computed_sha}')

        hdr = envelope['header']
        prf = envelope['proof']
        challenge = f"{computed_sha}|{hdr['createdAt']}|{hdr['robotId']}".encode()
        VerifyKey(bytes.fromhex(prf['publicKeyHex'])).verify(challenge, bytes.fromhex(prf['signatureHex']))
        print('Signature verification succeeded')
        print('public key:', prf['publicKeyHex'])


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description='peaq storage end-to-end test')
    parser.add_argument('--key', default='E2E_TEST_E2E', help='Storage key to use')
    parser.add_argument('--gateway', default='https://ipfs.io/ipfs', help='IPFS gateway URL')
    parser.add_argument('--wait', type=float, default=90.0, help='Wait time for tx finalization')
    args = parser.parse_args(argv)

    rclpy.init()
    try:
        node = StorageE2ETest(args.key, args.gateway, args.wait)
        node.run()
        return 0
    except Exception as exc:  # pylint: disable=broad-except
        print('E2E_TEST_ERROR:', exc)
        return 1
    finally:
        rclpy.shutdown()


if __name__ == '__main__':
    sys.exit(main())


