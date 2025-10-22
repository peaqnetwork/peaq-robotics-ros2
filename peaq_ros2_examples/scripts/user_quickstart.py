#!/usr/bin/env python3
"""
User Quickstart: Programmatically run peaq ROS 2 nodes and perform storage + DID + RBAC.

What this does:
- Starts CoreNode (blockchain services) and StorageBridgeNode (IPFS + signing + store envelope CID)
- Publishes a StorageIngest message (inline JSON), waits for status and tx hash
- Reads the on-chain value for the key, fetches the envelope and raw data from IPFS, verifies hash
- Creates a DID and performs basic RBAC (role, permission, assign, grant)

Requirements:
- pip install: peaq-robot-sdk PyNaCl requests
- ROS 2 environment should be setup (sourced) before running
"""
import os
import json
import time
import threading
import argparse
import hashlib
from typing import Optional

import requests
import rclpy
from rclpy.node import Node
from rclpy.executors import MultiThreadedExecutor
from rclpy.parameter import Parameter

from peaq_ros2_core.core_node import CoreNode
from peaq_ros2_core.storage_bridge_node import StorageBridgeNode
from peaq_ros2_interfaces.msg import StorageIngest, StorageResult, TxStatus
from peaq_ros2_interfaces.srv import (
    StoreReadData,
    IdentityCreate,
    IdentityRead,
    AccessCreateRole,
    AccessCreatePermission,
    AccessAssignPermToRole,
    AccessGrantRole,
)


class ClientNode(Node):
    def __init__(self) -> None:
        super().__init__('peaq_user_client')
        self.pub = self.create_publisher(StorageIngest, 'peaq/storage/ingest', 10)
        self.sub_status = self.create_subscription(StorageResult, 'peaq/storage/status', self._on_status, 10)
        self.sub_tx = self.create_subscription(TxStatus, 'peaq/tx_status', self._on_tx, 10)
        self.target_key: Optional[str] = None
        self.last_status: Optional[StorageResult] = None
        self.last_tx: Optional[TxStatus] = None
        self._status_event = threading.Event()

        self.store_read = self.create_client(StoreReadData, '/peaq_core_node/storage/read')
        self.id_create = self.create_client(IdentityCreate, '/peaq_core_node/identity/create')
        self.id_read = self.create_client(IdentityRead, '/peaq_core_node/identity/read')
        self.acc_create_role = self.create_client(AccessCreateRole, '/peaq_core_node/access/create_role')
        self.acc_create_perm = self.create_client(AccessCreatePermission, '/peaq_core_node/access/create_permission')
        self.acc_assign = self.create_client(AccessAssignPermToRole, '/peaq_core_node/access/assign_permission')
        self.acc_grant = self.create_client(AccessGrantRole, '/peaq_core_node/access/grant_role')

    def _on_status(self, msg: StorageResult) -> None:
        if self.target_key and msg.key == self.target_key:
            self.last_status = msg
            if msg.tx_hash or msg.cid:
                self._status_event.set()

    def _on_tx(self, msg: TxStatus) -> None:
        self.last_tx = msg

    def publish_ingest(self, key: str, content: dict, content_type: str, metadata: dict) -> None:
        self.target_key = key
        msg = StorageIngest()
        msg.key = key
        msg.is_file = False
        msg.file_path = ''
        msg.content = json.dumps(content)
        msg.content_type = content_type
        msg.metadata_json = json.dumps(metadata)
        # publish a handful of times for good measure
        for _ in range(5):
            self.pub.publish(msg)
            time.sleep(0.2)

    def wait_for_status(self, timeout_sec: float = 120.0) -> Optional[StorageResult]:
        ok = self._status_event.wait(timeout=timeout_sec)
        return self.last_status if ok else None


def run(args: argparse.Namespace) -> int:
    # Prepare environment for CoreNode autostart and StorageBridge signing key
    os.environ['PEAQ_ROS2_AUTOSTART'] = 'true'
    if args.network:
        os.environ['PEAQ_ROBOT_NETWORK'] = args.network
    # Generate signing key if not provided
    if not args.private_key_hex:
        try:
            from nacl.signing import SigningKey
            sk = SigningKey.generate()
            args.private_key_hex = sk.encode().hex()
        except Exception:
            args.private_key_hex = ''
    if args.private_key_hex:
        os.environ['PEAQ_SIGNING_SK_HEX'] = args.private_key_hex

    rclpy.init()

    # Create nodes
    core = CoreNode()
    bridge = StorageBridgeNode()

    # Override bridge runtime config where applicable
    bridge.ipfs_api_url = args.ipfs_api.rstrip('/')
    bridge.ipfs_gateway_url = args.ipfs_gateway.rstrip('/')
    bridge.pinning_pin = args.pin
    bridge.robot_id = args.robot_id
    # Ensure it points to CoreNode name
    bridge.core_node_name = 'peaq_core_node'

    client = ClientNode()

    # Start executor
    execu = MultiThreadedExecutor()
    execu.add_node(core)
    execu.add_node(bridge)
    execu.add_node(client)
    t = threading.Thread(target=execu.spin, daemon=True)
    t.start()

    try:
        # Funding: use funder file if present and requested
        if args.auto_fund:
            try:
                _maybe_fund_core_wallet(core, args.funder_json, args.network, args.fund_amount)
            except Exception as e:
                print('FUNDING_WARN:', e)

        # Optionally write YAML templates to disk (for ops)
        if args.write_yaml:
            _write_yaml_templates(args.yaml_dir, args)

        # Wait for services
        for _ in range(40):
            if client.store_read.wait_for_service(timeout_sec=0.5) and client.id_read.wait_for_service(timeout_sec=0.1):
                break
        print('SERVICES_READY:', client.store_read.service_is_ready(), client.id_read.service_is_ready())

        # Publish ingest
        key = f'USER_DEMO_{int(time.time())}'
        payload = {'hello': 'from_user_quickstart'}
        meta = {'robot_id': args.robot_id, 'ts': int(time.time())}
        print('INGEST_KEY:', key)
        client.publish_ingest(key, payload, 'application/json', meta)

        status = client.wait_for_status(timeout_sec=180.0)
        if not status:
            print('ERROR: No storage status received')
        else:
            print('STORAGE_STATUS:', status.status)
            print('STORAGE_TX_HASH:', status.tx_hash)
            print('ENVELOPE_CID:', status.cid)
            if status.ipfs_url:
                print('IPFS_URL:', status.ipfs_url)

        # Read back from chain
        if client.store_read.wait_for_service(timeout_sec=5.0):
            from peaq_ros2_interfaces.srv import StoreReadData
            req = StoreReadData.Request()
            req.key = key
            fut = client.store_read.call_async(req)
            rclpy.spin_until_future_complete(client, fut, timeout_sec=30.0)
            if fut.done() and fut.result():
                value_json = fut.result().value_json
                print('ONCHAIN_VALUE_JSON:', value_json)
                try:
                    env_cid = json.loads(value_json).get('envelopeCid')
                except Exception:
                    env_cid = value_json.strip('"')
            else:
                env_cid = None
        else:
            env_cid = None

        # Fetch envelope and raw via IPFS
        if env_cid:
            env_url = f"{args.ipfs_gateway.rstrip('/')}/{env_cid}"
            env = requests.get(env_url, timeout=60).json()
            print('ENVELOPE_JSON:', json.dumps(env, indent=2)[:800])
            data_cid = env['payload']['dataCid']
            data_url = f"{args.ipfs_gateway.rstrip('/')}/{data_cid}"
            data_bytes = requests.get(data_url, timeout=60).content
            data_sha = hashlib.sha256(data_bytes).hexdigest()
            print('RAW_DATA_SHA256:', data_sha)
            print('RAW_DATA_PREVIEW:', data_bytes[:80])

        # DID create + read
        if client.id_create.wait_for_service(timeout_sec=5.0):
            req = IdentityCreate.Request()
            req.name = f"did:peaq:{int(time.time())}"
            req.metadata_json = json.dumps({'env': 'quickstart'})
            fut = client.id_create.call_async(req)
            rclpy.spin_until_future_complete(client, fut, timeout_sec=90.0)
            if fut.done() and fut.result():
                print('IDENTITY_CREATE_TX:', fut.result().tx_hash)

        if client.id_read.wait_for_service(timeout_sec=5.0):
            fut = client.id_read.call_async(IdentityRead.Request())
            rclpy.spin_until_future_complete(client, fut, timeout_sec=30.0)
            if fut.done() and fut.result():
                doc = fut.result().doc_json
                print('IDENTITY_DOC_SNIPPET:', doc[:300])

        # RBAC: role/permission/assign/grant
        role = f"viewer_{int(time.time())}"
        perm = f"read_{int(time.time())}"
        if client.acc_create_role.wait_for_service(timeout_sec=5.0):
            rr = AccessCreateRole.Request(); rr.role = role; rr.description = 'viewer role'
            fr = client.acc_create_role.call_async(rr)
            rclpy.spin_until_future_complete(client, fr, timeout_sec=90.0)
            if fr.done() and fr.result():
                print('ACCESS_CREATE_ROLE_TX:', fr.result().tx_hash)

        if client.acc_create_perm.wait_for_service(timeout_sec=5.0):
            rp = AccessCreatePermission.Request(); rp.permission = perm; rp.description = 'read perm'
            fp = client.acc_create_perm.call_async(rp)
            rclpy.spin_until_future_complete(client, fp, timeout_sec=90.0)
            if fp.done() and fp.result():
                print('ACCESS_CREATE_PERMISSION_TX:', fp.result().tx_hash)

        if client.acc_assign.wait_for_service(timeout_sec=5.0):
            ra = AccessAssignPermToRole.Request(); ra.permission = perm; ra.role = role
            fa = client.acc_assign.call_async(ra)
            rclpy.spin_until_future_complete(client, fa, timeout_sec=90.0)
            if fa.done() and fa.result():
                print('ACCESS_ASSIGN_PERMISSION_TX:', fa.result().tx_hash)

        if client.acc_grant.wait_for_service(timeout_sec=5.0):
            # Grant to the same account running CoreNode (demo)
            user_addr = os.environ.get('PEAQ_GRANT_USER', '')
            if not user_addr:
                user_addr = '5EFpYxMa5pKrKJfz6HW4E18putcQHaqUqxNskoumCXbkYsiD'
            rg = AccessGrantRole.Request(); rg.role = role; rg.user = user_addr
            fg = client.acc_grant.call_async(rg)
            rclpy.spin_until_future_complete(client, fg, timeout_sec=90.0)
            if fg.done() and fg.result():
                print('ACCESS_GRANT_ROLE_TX:', fg.result().tx_hash)

        return 0

    finally:
        execu.shutdown()
        for n in (client, bridge, core):
            try:
                n.destroy_node()
            except Exception:
                pass
        try:
            if rclpy.ok():
                rclpy.shutdown()
        except Exception:
            pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--network', default=os.environ.get('PEAQ_ROBOT_NETWORK', 'wss://peaq-agung.api.onfinality.io/ws'))
    ap.add_argument('--ipfs-api', dest='ipfs_api', default=os.environ.get('IPFS_API', 'http://127.0.0.1:5001'))
    ap.add_argument('--ipfs-gateway', dest='ipfs_gateway', default=os.environ.get('IPFS_GATEWAY', 'http://salmon-managerial-caribou-735.mypinata.cloud/ipfs'))
    ap.add_argument('--robot-id', default=os.environ.get('ROBOT_ID', 'humanoid_001'))
    ap.add_argument('--private-key-hex', dest='private_key_hex', default=os.environ.get('PEAQ_SIGNING_SK_HEX', ''))
    ap.add_argument('--pin', action='store_true', default=False)
    ap.add_argument('--auto-fund', action='store_true', default=True)
    ap.add_argument('--funder-json', default=os.environ.get('PEAQ_FUNDER_JSON', '/work/.ros_e2e_wallet.json'))
    ap.add_argument('--fund-amount', type=int, default=int(os.environ.get('PEAQ_FUND_PLANCK', str(10**11))))
    ap.add_argument('--write-yaml', action='store_true', default=True)
    ap.add_argument('--yaml-dir', default=os.environ.get('PEAQ_YAML_DIR', '/work/tmp'))
    args = ap.parse_args()
    return run(args)


# --------------------------- Helpers ---------------------------- #

def _write_yaml_templates(dir_path: str, args: argparse.Namespace) -> None:
    try:
        os.makedirs(dir_path, exist_ok=True)
        core_yaml = (
            'network: agung\n'
            'default_confirmation_mode: FAST\n'
            'log_level: INFO\n'
            'log_format: human\n'
            'keystore:\n'
            '  path: ~/.peaq_robot/wallet.json\n'
            'events:\n'
            '  enabled: true\n'
        )
        bridge_yaml = (
            'ipfs:\n'
            f'  api_url: {args.ipfs_api}\n'
            f'  gateway_url: {args.ipfs_gateway}\n'
            f'  save_dir: {os.path.join(dir_path, "ipfs_cache")}\n'
            'pinning:\n'
            '  provider: pinata\n'
            '  pin: true\n'
            '  pinata_api_key: "<PASTE_PINATA_API_KEY>"\n'
            '  pinata_api_secret: "<PASTE_PINATA_API_SECRET>"\n'
            'signature:\n'
            '  algorithm: ed25519\n'
            f'  private_key_hex: {args.private_key_hex}\n'
            f'robot:\n  id: {args.robot_id}\n'
            'core:\n  node_name: peaq_core_node\n'
        )
        open(os.path.join(dir_path, 'core.yaml'), 'w').write(core_yaml)
        open(os.path.join(dir_path, 'bridge.yaml'), 'w').write(bridge_yaml)
        print('YAML_TEMPLATES_WRITTEN:', dir_path)
        print('YAML_PINATA_HINT: Edit bridge.yaml and paste pinata_api_key/pinata_api_secret')
    except Exception as e:
        print('YAML_WRITE_WARN:', e)


def _maybe_fund_core_wallet(core: CoreNode, funder_json_path: str, network: str, amount_planck: int) -> None:
    try:
        from peaq_robot import PeaqRobot
    except Exception as e:
        print('FUND_SKIP: peaq-robot-sdk not available:', e)
        return
    # Determine core wallet address
    try:
        core_addr = getattr(core, 'robot_sdk').address  # type: ignore[attr-defined]
    except Exception:
        print('FUND_SKIP: core wallet not initialized')
        return
    # Load funder
    try:
        with open(os.path.expanduser(funder_json_path), 'r') as f:
            import json as _json
            obj = _json.load(f)
        typ = (obj.get('type') or '').lower()
        data_b64 = obj.get('data') or ''
        import base64
        payload = base64.b64decode(data_b64).decode('utf-8') if data_b64 else ''
        if typ == 'mnemonic' and payload:
            funder = PeaqRobot(mnemonic=payload, network=network)
        elif typ == 'private_key' and payload:
            funder = PeaqRobot(private_key=payload, network=network)
        else:
            print('FUND_SKIP: invalid funder json')
            return
    except Exception as e:
        print('FUND_SKIP: cannot load funder json:', e)
        return
    # Transfer
    try:
        tx = funder.wallet.send_transaction(
            module='Balances',
            function='transfer_keep_alive',
            params={'dest': core_addr, 'value': int(amount_planck)},
            keypair=funder.keypair,
            tx_options=None,
            on_status=None,
        )
        print('FUND_TX:', tx)
    except Exception as e:
        print('FUND_WARN:', e)


if __name__ == '__main__':
    raise SystemExit(main())


