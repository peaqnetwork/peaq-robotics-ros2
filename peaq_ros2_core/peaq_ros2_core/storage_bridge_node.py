"""
Storage Bridge Node

Subscribes to a generic ingest topic, signs content, uploads raw data and a
signed verification envelope to IPFS, stores the envelope CID in the storage
palette via CoreNode's ~/storage/add service, and publishes status updates.

IMPORTANT: The envelope format (peaq-ipfs-envelope@v1) is IMMUTABLE and AUTOMATIC.
Users publish raw machine data to /peaq/storage/ingest, and this node automatically:
1. Uploads raw data to IPFS (gets dataCid)
2. Computes SHA256 hash of raw data
3. Signs the hash with Ed25519 private key
4. Creates envelope with schema, header, payload, and proof sections
5. Uploads envelope to IPFS (gets envelopeCid)
6. Stores envelopeCid on blockchain

The envelope structure is fixed and cannot be modified by users:
{
  "schema": "peaq-ipfs-envelope@v1",
  "header": {"contentType", "createdAt", "robotId"},
  "payload": {"dataCid", "dataSha256"},
  "proof": {"algorithm": "ed25519", "publicKeyHex", "signatureHex"},
  "meta": {...}
}

This node keeps configuration minimal and does not persist IPFS URLs on-chain.
"""
from __future__ import annotations

import os
import io
import json
import time
import hashlib
from pathlib import Path
from typing import Optional, Dict, Any

import rclpy
from rclpy.node import Node
from rclpy.executors import MultiThreadedExecutor

from peaq_ros2_interfaces.msg import StorageIngest, StorageResult, TxStatus
from peaq_ros2_interfaces.srv import StoreAddData

try:
    # Optional dependency: PyNaCl for ed25519
    from nacl.signing import SigningKey
    from nacl.encoding import HexEncoder
    _HAS_NACL = True
except Exception:
    _HAS_NACL = False

try:
    import requests
    _HAS_REQUESTS = True
except Exception:
    _HAS_REQUESTS = False

try:
    import yaml  # type: ignore
    _HAS_YAML = True
except Exception:
    _HAS_YAML = False

try:
    # Optional: derivation from mnemonic via substrate-interface
    from substrateinterface import Keypair, KeypairType  # type: ignore
    _HAS_SUBSTRATE = True
except Exception:
    _HAS_SUBSTRATE = False


class StorageBridgeNode(Node):
    def __init__(self) -> None:
        super().__init__('peaq_storage_bridge_node')

        # Parameters with sensible defaults
        self.declare_parameter('config.yaml_path', '')
        self.declare_parameter('ipfs.api_url', 'http://127.0.0.1:5001')
        self.declare_parameter('ipfs.gateway_url', 'https://ipfs.io/ipfs')
        self.declare_parameter('ipfs.save_dir', '')  # optional: save uploaded artifacts locally
        self.declare_parameter('pinning.provider', 'none')  # none|pinata
        self.declare_parameter('pinning.pin', False)
        # Default to Robonomics-style: local add then optional pin-by-cid
        self.declare_parameter('pinning.mode', 'pin_by_cid')  # pin_by_cid|upload
        self.declare_parameter('pinata.api_key', '')
        self.declare_parameter('pinata.api_secret', '')
        self.declare_parameter('pinata.jwt', '')
        self.declare_parameter('signature.algorithm', 'sr25519')  # Use Sr25519 (Substrate standard)
        self.declare_parameter('signature.private_key_hex', '')
        self.declare_parameter('signature.private_key_file', '')
        self.declare_parameter('signature.wallet_json_path', '')
        self.declare_parameter('signature.seed', '')  # mnemonic or 32-byte hex seed
        self.declare_parameter('signature.auto_generate', False)  # Auto-generate wallet if none provided
        self.declare_parameter('robot.id', '')
        self.declare_parameter('robot.require_did', True)  # Require DID and verify on blockchain
        self.declare_parameter('core_node_name', 'peaq_core_node')
        self.declare_parameter('network', 'agung')  # Network to use (agung, peaq, or custom URL)

        # Resolve params
        self.yaml_path: str = self.get_parameter('config.yaml_path').get_parameter_value().string_value
        self.ipfs_api_url: str = self.get_parameter('ipfs.api_url').get_parameter_value().string_value
        self.ipfs_gateway_url: str = self.get_parameter('ipfs.gateway_url').get_parameter_value().string_value
        self.ipfs_save_dir: str = self.get_parameter('ipfs.save_dir').get_parameter_value().string_value
        self.pinning_provider: str = self.get_parameter('pinning.provider').get_parameter_value().string_value
        self.pinning_pin: bool = self.get_parameter('pinning.pin').get_parameter_value().bool_value
        self.pinning_mode: str = self.get_parameter('pinning.mode').get_parameter_value().string_value
        self.pinata_api_key: str = self.get_parameter('pinata.api_key').get_parameter_value().string_value
        self.pinata_api_secret: str = self.get_parameter('pinata.api_secret').get_parameter_value().string_value
        self.pinata_jwt: str = self.get_parameter('pinata.jwt').get_parameter_value().string_value
        self.signature_algorithm: str = self.get_parameter('signature.algorithm').get_parameter_value().string_value
        self.private_key_hex: str = self.get_parameter('signature.private_key_hex').get_parameter_value().string_value or os.getenv('PEAQ_SIGNING_SK_HEX', '')
        self.private_key_file: str = self.get_parameter('signature.private_key_file').get_parameter_value().string_value or os.getenv('PEAQ_SIGNING_SK_FILE', '')
        self.wallet_json_path: str = self.get_parameter('signature.wallet_json_path').get_parameter_value().string_value or os.getenv('PEAQ_SIGNING_WALLET_JSON', '')
        self.signature_seed: str = self.get_parameter('signature.seed').get_parameter_value().string_value or os.getenv('PEAQ_SIGNING_SEED', '')
        self.signature_auto_generate: bool = self.get_parameter('signature.auto_generate').get_parameter_value().bool_value
        self.robot_id: str = self.get_parameter('robot.id').get_parameter_value().string_value
        self.robot_require_did: bool = self.get_parameter('robot.require_did').get_parameter_value().bool_value
        self.core_node_name: str = self.get_parameter('core_node_name').get_parameter_value().string_value
        self.network: str = self.get_parameter('network').get_parameter_value().string_value

        # YAML overlay (optional)
        env_yaml = os.getenv('PEAQ_ROS2_BRIDGE_YAML', '')
        yaml_path = self.yaml_path or env_yaml
        if yaml_path:
            if not _HAS_YAML:
                self.get_logger().error('PyYAML is required to load YAML config')
            else:
                try:
                    with open(os.path.expanduser(yaml_path), 'r') as f:
                        data = yaml.safe_load(f) or {}
                    
                    # Support both old flat structure and new unified structure
                    # New structure: storage_bridge section for bridge-specific config
                    bridge_config = data.get('storage_bridge', {})
                    
                    # Network (shared, top-level)
                    self.network = data.get('network', self.network)
                    
                    # Wallet (shared, top-level) - NEW unified structure
                    wallet = data.get('wallet', {})
                    if isinstance(wallet, dict):
                        if 'path' in wallet:
                            self.wallet_json_path = wallet['path']
                        if 'auto_generate' in wallet:
                            self.signature_auto_generate = bool(wallet['auto_generate'])
                    
                    # Storage configuration (bridge-specific)
                    storage_cfg = bridge_config.get('storage', {})
                    if isinstance(storage_cfg, dict):
                        # Storage mode
                        mode = storage_cfg.get('mode', '')
                        if mode == 'local_ipfs':
                            self.pinning_provider = 'none'
                        elif mode == 'pinata':
                            self.pinning_provider = 'pinata'
                        elif mode == 'both':
                            self.pinning_provider = 'pinata'
                        
                        # Local IPFS config
                        local_ipfs = storage_cfg.get('local_ipfs', {})
                        if isinstance(local_ipfs, dict):
                            self.ipfs_api_url = local_ipfs.get('api_url', self.ipfs_api_url)
                            self.ipfs_gateway_url = local_ipfs.get('gateway_url', self.ipfs_gateway_url)
                            self.ipfs_save_dir = local_ipfs.get('save_dir', self.ipfs_save_dir)
                        
                        # Pinata config
                        pinata = storage_cfg.get('pinata', {})
                        if isinstance(pinata, dict):
                            self.pinata_jwt = pinata.get('jwt', self.pinata_jwt)
                            self.pinata_api_key = pinata.get('api_key', self.pinata_api_key)
                            self.pinata_api_secret = pinata.get('api_secret', self.pinata_api_secret)
                            self.ipfs_gateway_url = pinata.get('gateway_url', self.ipfs_gateway_url)
                            self.pinning_pin = bool(pinata.get('pin', self.pinning_pin))
                            self.pinning_mode = pinata.get('mode', self.pinning_mode)
                    
                    # Legacy IPFS config support (old structure)
                    ipfs_cfg = data.get('ipfs') or {}
                    if isinstance(ipfs_cfg, dict):
                        self.ipfs_api_url = ipfs_cfg.get('api_url', self.ipfs_api_url)
                        self.ipfs_gateway_url = ipfs_cfg.get('gateway_url', self.ipfs_gateway_url)
                        self.ipfs_save_dir = ipfs_cfg.get('save_dir', self.ipfs_save_dir)
                    
                    # Legacy pinning config support (old structure)
                    pin_cfg = data.get('pinning') or {}
                    if isinstance(pin_cfg, dict):
                        self.pinning_provider = pin_cfg.get('provider', self.pinning_provider)
                        self.pinning_pin = bool(pin_cfg.get('pin', self.pinning_pin))
                        self.pinning_mode = pin_cfg.get('mode', self.pinning_mode)
                        self.pinata_api_key = pin_cfg.get('pinata_api_key', self.pinata_api_key)
                        self.pinata_api_secret = pin_cfg.get('pinata_api_secret', self.pinata_api_secret)
                        self.pinata_jwt = pin_cfg.get('pinata_jwt', self.pinata_jwt)
                    
                    # Signature configuration (bridge-specific)
                    sig_cfg = bridge_config.get('signature', data.get('signature', {}))
                    if isinstance(sig_cfg, dict):
                        self.signature_algorithm = sig_cfg.get('algorithm', self.signature_algorithm)
                        # Legacy support for wallet_json_path in signature section
                        if 'wallet_json_path' in sig_cfg:
                            self.wallet_json_path = sig_cfg['wallet_json_path']
                        if 'auto_generate' in sig_cfg:
                            self.signature_auto_generate = bool(sig_cfg['auto_generate'])
                        self.private_key_hex = sig_cfg.get('private_key_hex', self.private_key_hex)
                        self.private_key_file = sig_cfg.get('private_key_file', self.private_key_file)
                        self.signature_seed = sig_cfg.get('seed', self.signature_seed)
                    
                    # Robot configuration (bridge-specific)
                    robot_cfg = bridge_config.get('robot', data.get('robot', {}))
                    if isinstance(robot_cfg, dict):
                        self.robot_id = robot_cfg.get('id', self.robot_id)
                        self.robot_require_did = bool(robot_cfg.get('require_did', self.robot_require_did))
                    
                    # Core node connection (bridge-specific)
                    core_cfg = bridge_config.get('core', data.get('core', {}))
                    if isinstance(core_cfg, dict):
                        self.core_node_name = core_cfg.get('node_name', self.core_node_name)
                except Exception as e:
                    self.get_logger().error(f'Failed to load YAML config: {e}')

        # Validate basic deps
        if not _HAS_REQUESTS:
            self.get_logger().error('requests library is required for IPFS HTTP API')
        if self.signature_algorithm.lower() == 'ed25519' and not _HAS_NACL:
            self.get_logger().error('PyNaCl is required for ed25519 signing')

        # Prepare save dir if set
        self._save_dir_path: Optional[Path] = None
        if self.ipfs_save_dir:
            try:
                p = Path(self.ipfs_save_dir).expanduser().resolve()
                p.mkdir(parents=True, exist_ok=True)
                self._save_dir_path = p
            except Exception as e:
                self.get_logger().warn(f'Failed to prepare ipfs.save_dir: {e}')

        # Initialize PeaqRobot SDK for Sr25519 signing (same as core_node)
        self._robot_sdk = None
        self._init_robot_sdk()
        
        # Auto-derive DID from wallet address
        if self._robot_sdk and not self.robot_id:
            self.robot_id = f'did:peaq:{self._robot_sdk.address}'
            self.get_logger().info(f'Auto-derived DID from wallet: {self.robot_id}')

        # ROS comms
        self._ingest_sub = self.create_subscription(
            StorageIngest,
            '/peaq/storage/ingest',
            self._handle_ingest,
            10
        )
        self._status_pub = self.create_publisher(StorageResult, '/peaq/storage/status', 10)

        # Track tx statuses
        self._pending_tx_by_key: Dict[str, str] = {}
        self._tx_sub = self.create_subscription(
            TxStatus,
            '/peaq/tx_status',
            self._handle_tx_status,
            10
        )

        # Keep references to pending service futures to avoid GC cancelling callbacks
        self._pending_futures = []  # type: list

        # Failure tracking and retry system
        self._failure_log_path = '/tmp/storage_bridge_failures.jsonl'
        self._retry_queue: Dict[str, Dict[str, Any]] = {}  # key -> retry_info
        self._max_retries = 3
        self._retry_delay_seconds = 5.0

        # Service client to CoreNode storage add (absolute name)
        self._store_add_srv_name = f'/{self.core_node_name}/storage/add'
        self._store_add_client = self.create_client(StoreAddData, self._store_add_srv_name)
        
        # Service client to CoreNode identity read (for DID verification)
        from peaq_ros2_interfaces.srv import IdentityRead
        self._identity_read_srv_name = f'/{self.core_node_name}/identity/read'
        self._identity_read_client = self.create_client(IdentityRead, self._identity_read_srv_name)

        # Validate and verify DID based on require_did setting
        if self.robot_require_did:
            # Ensure we have a DID
            if not self.robot_id:
                self.get_logger().error(
                    f'DID "{self.robot_id}" does not exist on {self.network} network. '
                    f'Create the DID first (DID is auto-derived from wallet address):\n'
                    f'  ros2 service call /{self.core_node_name}/identity/create \\\n'
                    f'    peaq_ros2_interfaces/srv/IdentityCreate \\\n'
                    f'    "{{metadata_json: \'{{}}\'}}" \n'
                    f'Or set require_did=false for development.'
                )
                raise ValueError('DID is required but could not be derived from wallet')
            
            # Validate DID format
            if not self._is_valid_did(self.robot_id):
                self.get_logger().error(
                    f'require_did is true but DID "{self.robot_id}" is not valid. '
                    f'Expected format: did:peaq:<address>. Set require_did=false to disable this check.'
                )
                raise ValueError(f'Invalid DID format: {self.robot_id}')
            
            # Verify DID exists on blockchain (require_did=true implies verification)
            self.get_logger().info(f'Verifying DID on {self.network} network: {self.robot_id}')
            
            # Check if core node is available
            if not self._identity_read_client.wait_for_service(timeout_sec=5.0):
                self.get_logger().error(
                    f'Cannot verify DID - core node not available at {self._identity_read_srv_name}. '
                    f'Ensure core_node is running or set require_did=false for development.'
                )
                raise RuntimeError(f'Core node not available for DID verification')
            
            # Verify DID exists on chain
            if not self._verify_did_exists(self.robot_id):
                self.get_logger().error(
                    f'DID "{self.robot_id}" does not exist on {self.network} network. '
                    f'Create the DID first:\n'
                    f'  ros2 service call /{self.core_node_name}/identity/create \\\n'
                    f'    peaq_ros2_interfaces/srv/IdentityCreate \\\n'
                    f'    "{{name: \'{self.robot_id}\'}}" \n'
                    f'Or set require_did=false for development.'
                )
                raise ValueError(f'DID not found on blockchain: {self.robot_id}')
            
            self.get_logger().info(f'✓ DID verified on {self.network} network')
        else:
            # require_did=false: just warn if DID is missing or not verified
            if self.robot_id:
                self.get_logger().warn(
                    f'Using DID {self.robot_id} without verification (require_did=false). '
                    f'Set require_did=true for production.'
                )
            else:
                self.get_logger().warn(
                    'No DID configured and require_did=false. '
                    'This may cause issues with storage operations. Set require_did=true for production.'
                )

        self.get_logger().info(f'peaq_storage_bridge_node ready (network: {self.network})')

    # ---------------------------- ROS Callbacks ---------------------------- #
    def _handle_ingest(self, msg: StorageIngest) -> None:
        try:
            self.get_logger().info(f"Processing ingest key={msg.key} is_file={msg.is_file}")
            created_at = int(self.get_clock().now().to_msg().sec)
            robot_id = self.robot_id or 'unknown'

            self.get_logger().debug('Reading content bytes')
            # 1) Read content bytes
            data_bytes = self._read_content(msg)
            data_sha256 = hashlib.sha256(data_bytes).hexdigest()
            self.get_logger().debug(f'Content size={len(data_bytes)} sha256={data_sha256[:8]}...')

            # 2) Sign challenge
            self.get_logger().debug('Signing payload')
            public_key_hex, signature_hex = self._sign_payload(data_sha256, created_at, robot_id)
            self.get_logger().debug('Signature generated')

            # 3) Upload raw data
            if self.pinning_provider.lower() == 'pinata' and self.pinning_pin and self.pinning_mode == 'upload':
                self.get_logger().info('Uploading raw data to Pinata (upload mode)')
                data_cid = self._pinata_upload_bytes(data_bytes, name=f'{self.robot_id}-raw')
            else:
                self.get_logger().info('Uploading raw data to IPFS')
                data_cid = self._ipfs_add_bytes(data_bytes, pin=self.pinning_pin)
            self.get_logger().info(f'Raw data CID: {data_cid}')
            self._maybe_save_local(f'{data_cid}.data', data_bytes)

            # 4) Build and upload envelope
            self.get_logger().debug('Building envelope JSON')
            envelope = self._build_envelope(
                content_type=msg.content_type,
                created_at=created_at,
                robot_id=robot_id,
                data_cid=data_cid,
                data_sha256=data_sha256,
                algorithm=self.signature_algorithm,
                public_key_hex=public_key_hex,
                signature_hex=signature_hex,
                metadata_json=msg.metadata_json,
            )
            envelope_bytes = json.dumps(envelope, separators=(',', ':'), ensure_ascii=False).encode('utf-8')
            if self.pinning_provider.lower() == 'pinata' and self.pinning_pin and self.pinning_mode == 'upload':
                self.get_logger().info('Uploading envelope to Pinata (upload mode)')
                envelope_cid = self._pinata_upload_bytes(envelope_bytes, name=f'{self.robot_id}-envelope')
            else:
                self.get_logger().info('Uploading envelope to IPFS')
                envelope_cid = self._ipfs_add_bytes(envelope_bytes, pin=self.pinning_pin)
            self.get_logger().info(f'Envelope CID: {envelope_cid}')
            self._maybe_save_local(f'{envelope_cid}.envelope.json', envelope_bytes)

            # Optional: Pin to Pinata by CID (only when not in upload mode)
            if (
                self.pinning_provider.lower() == 'pinata'
                and self.pinning_pin
                and self.pinning_mode != 'upload'
            ):
                try:
                    self._pin_to_pinata(data_cid, name=f'{self.robot_id}-raw')
                    self._pin_to_pinata(envelope_cid, name=f'{self.robot_id}-envelope')
                except Exception as e:
                    self.get_logger().warn(f'Pinata pin failed: {e}')

            # 5) Store envelope CID on-chain via CoreNode storage service
            value_obj = { 'envelopeCid': envelope_cid }
            self.get_logger().info('Calling storage add service (async)')
            # Publish early PENDING with CID (no tx yet)
            self._publish_status(
                key=msg.key,
                cid=envelope_cid,
                tx_hash='',
                status='PENDING',
                error='',
            )
            
            # Store metadata for potential retry
            retry_info = {
                'key': msg.key,
                'envelope_cid': envelope_cid,
                'data_cid': data_cid,
                'value_json': json.dumps(value_obj),
                'attempt': 0,
                'max_retries': self._max_retries,
                'timestamp': time.time(),
                'stage': 'blockchain_submit',
            }
            self._retry_queue[msg.key] = retry_info
            
            self._call_store_add_async(msg.key, json.dumps(value_obj), envelope_cid)

        except Exception as e:
            self.get_logger().error(f"Ingest failed for key={msg.key}: {e}")
            self._publish_status(
                key=msg.key,
                cid='',
                tx_hash='',
                status='FAILED',
                error=str(e),
            )

    def _handle_tx_status(self, msg: TxStatus) -> None:
        key = self._pending_tx_by_key.get(msg.tx_hash)
        if not key:
            return
        # Re-publish latest status for the stored key
        self._publish_status(
            key=key,
            cid='',
            tx_hash=msg.tx_hash,
            status=msg.phase or '',
            error=msg.error or '',
        )
        # Clear mapping on terminal states
        if msg.phase in ('FINALIZED', 'FAILED'):
            self._pending_tx_by_key.pop(msg.tx_hash, None)

    # ----------------------------- IPFS Helpers ---------------------------- #
    def _ipfs_add_bytes(self, data: bytes, pin: bool = False) -> str:
        if not _HAS_REQUESTS:
            raise RuntimeError('requests not available for IPFS HTTP API')
        api_base = self._normalize_ipfs_api_base(self.ipfs_api_url)
        url = f'{api_base}/api/v0/add'
        files = {'file': ('data', io.BytesIO(data), 'application/octet-stream')}
        params = {'pin': 'true' if pin else 'false'}
        last_exc: Optional[Exception] = None
        for attempt in range(3):
            try:
                resp = requests.post(url, files=files, params=params, timeout=60)
                resp.raise_for_status()
                try:
                    res = resp.json()
                    cid = res.get('Hash') or res.get('Cid') or ''
                    if not cid:
                        raise ValueError('IPFS add returned no CID')
                    return cid
                except ValueError:
                    text = resp.text
                    marker = 'Hash":"'
                    if marker in text:
                        cid = text.split(marker, 1)[1].split('"', 1)[0]
                        return cid
                    raise
            except Exception as e:
                last_exc = e
                # brief backoff
                try:
                    time.sleep(0.5 * (attempt + 1))
                except Exception:
                    pass
        raise RuntimeError(f'IPFS add failed after retries: {last_exc}')

    def _pin_to_pinata(self, cid: str, name: Optional[str] = None) -> None:
        """Pin an existing CID in Pinata.

        Prefer the v3 public pin-by-CID endpoint when a JWT is provided; otherwise
        fall back to the legacy v1 pinByHash with API key/secret.
        """
        if not _HAS_REQUESTS:
            return

        # v3 with JWT
        if self.pinata_jwt:
            headers = {
                'Authorization': f'Bearer {self.pinata_jwt}',
                'Content-Type': 'application/json',
            }
            body = { 'cid': cid }
            if name:
                body['name'] = name
            # Optional fields supported by v3 API: group_id, keyvalues, host_nodes
            for attempt in range(2):
                try:
                    resp = requests.post(
                        'https://api.pinata.cloud/v3/files/public/pin_by_cid',
                        headers=headers,
                        json=body,
                        timeout=30,
                    )
                    resp.raise_for_status()
                    return
                except Exception as e:
                    self.get_logger().warn(f'Pinata v3 pin_by_cid failed (try {attempt+1}): {e}')
                    try:
                        time.sleep(0.5 * (attempt + 1))
                    except Exception:
                        pass

        # Fallback: v1 with API key/secret
        if self.pinata_api_key and self.pinata_api_secret:
            headers = {
                'pinata_api_key': self.pinata_api_key,
                'pinata_secret_api_key': self.pinata_api_secret,
                'Content-Type': 'application/json',
            }
            body = { 'hashToPin': cid }
            if name:
                body['pinataMetadata'] = { 'name': name }
            for attempt in range(2):
                try:
                    resp = requests.post(
                        'https://api.pinata.cloud/pinning/pinByHash',
                        headers=headers,
                        json=body,
                        timeout=30,
                    )
                    resp.raise_for_status()
                    break
                except Exception as e:
                    self.get_logger().warn(f'Pinata v1 pinByHash failed (try {attempt+1}): {e}')
                    try:
                        time.sleep(0.5 * (attempt + 1))
                    except Exception:
                        pass
        # If neither JWT nor key/secret, do nothing
        # no return needed; if it fails an exception is raised

    def _pinata_upload_bytes(self, data: bytes, name: Optional[str] = None) -> str:
        """Upload bytes to Pinata (returns CID). Tries JWT first, then key/secret.
        Uses v1 pinFileToIPFS which accepts either Bearer JWT or key/secret headers.
        """
        if not _HAS_REQUESTS:
            raise RuntimeError('requests not available for Pinata HTTP API')

        files = {'file': ('data', io.BytesIO(data), 'application/octet-stream')}
        headers = {'Content-Type': 'application/json'}
        params_json = {}
        if name:
            params_json['pinataMetadata'] = {'name': name}

        # Try JWT first
        if self.pinata_jwt:
            for attempt in range(2):
                try:
                    hdr = {'Authorization': f'Bearer {self.pinata_jwt}'}
                    resp = requests.post(
                        'https://api.pinata.cloud/pinning/pinFileToIPFS',
                        headers=hdr,
                        files=files,
                        data={'pinataMetadata': json.dumps(params_json.get('pinataMetadata', {}))} if params_json else None,
                        timeout=60,
                    )
                    resp.raise_for_status()
                    js = resp.json()
                    return js.get('IpfsHash') or js.get('cid') or js.get('Hash') or ''
                except Exception as e:
                    self.get_logger().warn(f'Pinata upload (JWT) failed (try {attempt+1}): {e}')
                    try:
                        time.sleep(0.5 * (attempt + 1))
                    except Exception:
                        pass
        # Fallback to key/secret
        if self.pinata_api_key and self.pinata_api_secret:
            hdr = {
                'pinata_api_key': self.pinata_api_key,
                'pinata_secret_api_key': self.pinata_api_secret,
            }
            for attempt in range(2):
                resp = requests.post(
                    'https://api.pinata.cloud/pinning/pinFileToIPFS',
                    headers=hdr,
                    files=files,
                    data={'pinataMetadata': json.dumps(params_json.get('pinataMetadata', {}))} if params_json else None,
                    timeout=60,
                )
                try:
                    resp.raise_for_status()
                    js = resp.json()
                    return js.get('IpfsHash') or js.get('cid') or js.get('Hash') or ''
                except Exception as e:
                    self.get_logger().warn(f'Pinata upload (key/secret) failed (try {attempt+1}): {e}')
                    try:
                        time.sleep(0.5 * (attempt + 1))
                    except Exception:
                        pass
        raise RuntimeError('No Pinata credentials available for upload')

    @staticmethod
    def _normalize_ipfs_api_base(api: str) -> str:
        api = api.strip()
        if api.startswith('http://') or api.startswith('https://'):
            return api.rstrip('/')
        # Basic multiaddr support: /ip4/127.0.0.1/tcp/5001/http -> http://127.0.0.1:5001
        if api.startswith('/ip4/') and '/tcp/' in api:
            try:
                parts = api.split('/')
                host = parts[2]
                port = parts[4]
                scheme = 'http'
                if len(parts) > 5 and parts[5] == 'https':
                    scheme = 'https'
                return f'{scheme}://{host}:{port}'
            except Exception:
                pass
        # Default
        return 'http://127.0.0.1:5001'

    def _maybe_save_local(self, filename: str, content: bytes) -> None:
        if not self._save_dir_path:
            return
        try:
            path = self._save_dir_path / filename
            with open(path, 'wb') as f:
                f.write(content)
        except Exception as e:
            self.get_logger().warn(f'Failed saving to {self._save_dir_path}: {e}')

    # --------------------------- Robot SDK Initialization ---------------------------- #
    def _init_robot_sdk(self):
        """Initialize PeaqRobot SDK for Sr25519 signing (same wallet as core_node)."""
        try:
            from peaq_robot import PeaqRobot
            
            # Resolve network URL
            network_url = self._resolve_network_url(self.network)
            
            # Handle auto-generate wallet
            keystore_path = self.wallet_json_path
            if self.signature_auto_generate and keystore_path:
                keystore_path = self._handle_auto_generate_wallet(keystore_path, network_url)
            
            # Initialize PeaqRobot with the same wallet as core_node
            self._robot_sdk = PeaqRobot(
                network=network_url,
                keystore_path=keystore_path
            )
            
            self.get_logger().info(f'Initialized PeaqRobot SDK with wallet: {self._robot_sdk.address}')
            
        except Exception as e:
            self.get_logger().error(f'Failed to initialize PeaqRobot SDK: {e}')
            raise
    
    def _resolve_network_url(self, network: str) -> str:
        """Resolve network name to WebSocket URL."""
        if network.startswith('ws://') or network.startswith('wss://'):
            return network
        
        mappings = {
            'agung': 'wss://peaq-agung.api.onfinality.io/ws',
            'testnet': 'wss://peaq-agung.api.onfinality.io/ws',
            'peaq': 'wss://wss.mainnet.peaq.network',
            'mainnet': 'wss://wss.mainnet.peaq.network',
        }
        return mappings.get(network.lower(), network)
    
    def _handle_auto_generate_wallet(self, wallet_path: str, network_url: str) -> str:
        """Handle auto-generate wallet logic using PeaqRobot.
        
        If wallet exists: use it (log warning)
        If wallet doesn't exist: generate new one using PeaqRobot
        
        Returns the wallet path to use.
        """
        from peaq_robot import PeaqRobot
        
        expanded_path = os.path.expanduser(wallet_path)
        
        if os.path.exists(expanded_path):
            self.get_logger().warning(
                f'auto_generate=true but wallet already exists at {expanded_path}. '
                f'Using existing wallet. To regenerate, delete the file first.'
            )
            return expanded_path
        
        # Generate new wallet using PeaqRobot
        self.get_logger().info(f'Generating new wallet at {expanded_path}...')
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(expanded_path), exist_ok=True)
        
        # Generate using PeaqRobot (it will auto-generate and save)
        temp_robot = PeaqRobot(
            network=network_url,
            keystore_path=expanded_path
        )
        
        self.get_logger().info(f'New wallet generated at {expanded_path}')
        self.get_logger().info(f'   Address: {temp_robot.address}')
        
        return expanded_path

    # --------------------------- Key Resolution ---------------------------- #
    def _resolve_private_key_hex(self) -> str:
        """Resolve ed25519 private key hex from multiple sources.
        Priority: private_key_hex (already set) > private_key_file > wallet_json_path > seed.
        """
        if self.private_key_hex:
            return self._normalize_hex(self.private_key_hex)
        if self.private_key_file:
            pk = self._load_private_key_from_file(self.private_key_file)
            if pk:
                return self._normalize_hex(pk)
        if self.wallet_json_path:
            pk = self._load_private_key_from_wallet_json(self.wallet_json_path)
            if pk:
                return self._normalize_hex(pk)
        if self.signature_seed:
            pk = self._derive_from_seed(self.signature_seed)
            if pk:
                return self._normalize_hex(pk)
        return ''
    
    def _generate_new_wallet(self) -> str:
        """Generate a new Ed25519 wallet and save it to configured wallet path.
        Only generates if wallet file doesn't exist (safe by default).
        Returns the private key hex.
        """
        try:
            if not _HAS_NACL:
                self.get_logger().error('PyNaCl is required for wallet generation')
                return ''
            
            # Use configured wallet path, or default if not set
            if self.wallet_json_path:
                wallet_path = Path(os.path.expanduser(self.wallet_json_path))
                self.get_logger().info(f'Using configured wallet path: {wallet_path}')
            else:
                wallet_dir = Path.home() / '.peaq_robot'
                wallet_dir.mkdir(parents=True, exist_ok=True)
                wallet_path = wallet_dir / 'storage_bridge_wallet.json'
                self.get_logger().warn(f'No wallet path configured, using default: {wallet_path}')
            
            # Ensure parent directory exists
            wallet_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Check if wallet already exists
            if wallet_path.exists():
                self.get_logger().warning(
                    f'auto_generate=true but wallet already exists at {wallet_path}. '
                    f'Using existing wallet. To generate new wallet, delete the file first.'
                )
                # Load and return existing wallet's private key
                try:
                    existing_key = self._load_private_key_from_wallet_json(str(wallet_path))
                    if existing_key:
                        return existing_key
                    else:
                        self.get_logger().error(f'Existing wallet file is invalid or unreadable')
                        return ''
                except Exception as e:
                    self.get_logger().error(f'Failed to load existing wallet: {e}')
                    return ''
            
            # Generate new Ed25519 keypair
            sk = SigningKey.generate()
            private_key_hex = sk.encode(encoder=HexEncoder).decode('ascii')
            vk = sk.verify_key
            public_key_hex = vk.encode(encoder=HexEncoder).decode('ascii')
            
            import json as _json
            wallet_data = {
                'version': 1,
                'type': 'private_key',
                'encoding': 'hex',
                'data': private_key_hex,
                'public_key': public_key_hex,
                'algorithm': 'ed25519',
                'created_at': int(time.time()),
                'note': 'Auto-generated by storage_bridge_node'
            }
            
            with open(wallet_path, 'w') as f:
                _json.dump(wallet_data, f, indent=2)
            
            self.get_logger().info(f'Generated new wallet saved to: {wallet_path}')
            self.get_logger().info(f'Public key: {public_key_hex}')
            self.get_logger().warn('IMPORTANT: Backup your wallet file! This is the only copy of your private key.')
            
            return private_key_hex
        except Exception as e:
            self.get_logger().error(f'Failed to generate wallet: {e}')
            return ''

    def _get_wallet_address_from_private_key(self, private_key_hex: str) -> str:
        """Derive SS58 wallet address from Ed25519 private key hex.
        Returns empty string on failure.
        """
        try:
            if not _HAS_SUBSTRATE:
                self.get_logger().warn('substrateinterface is required to derive wallet address')
                return ''
            
            if not _HAS_NACL:
                self.get_logger().warn('PyNaCl is required to derive wallet address')
                return ''
            
            # Normalize hex
            pk_hex = self._normalize_hex(private_key_hex)
            
            # Ed25519: private key is 32 bytes (64 hex chars)
            # Get public key from private key using PyNaCl
            sk = SigningKey(bytes.fromhex(pk_hex))  # Already bytes, no encoder needed
            vk = sk.verify_key
            public_key_bytes = bytes(vk)
            
            # Create keypair from public key to get SS58 address
            keypair = Keypair(
                ss58_address=None,
                public_key=public_key_bytes,
                private_key=bytes.fromhex(pk_hex),
                ss58_format=42,  # Generic substrate format
                crypto_type=KeypairType.ED25519
            )
            
            return keypair.ss58_address
        except Exception as e:
            self.get_logger().warn(f'Failed to derive wallet address from private key: {e}')
            return ''
    
    @staticmethod
    def _normalize_hex(h: str) -> str:
        h = (h or '').strip()
        if h.startswith('0x') or h.startswith('0X'):
            h = h[2:]
        return h

    def _load_private_key_from_file(self, path: str) -> str:
        try:
            with open(os.path.expanduser(path), 'r') as f:
                content = f.read().strip()
            return content
        except Exception as e:
            self.get_logger().warn(f'Could not read signature.private_key_file: {e}')
            return ''

    def _load_private_key_from_wallet_json(self, path: str) -> str:
        try:
            import json as _json, base64
            with open(os.path.expanduser(path), 'r') as f:
                obj = _json.load(f)
            typ = (obj.get('type') or '').lower()
            enc = (obj.get('encoding') or '').lower()
            data = obj.get('data') or ''
            payload = data
            if enc == 'base64':
                try:
                    payload = base64.b64decode(data).decode('utf-8')
                except Exception:
                    payload = data
            if typ == 'private_key':
                return payload
            if typ == 'mnemonic' or self._looks_like_mnemonic(payload):
                return self._derive_from_seed(payload)
            return ''
        except Exception as e:
            self.get_logger().warn(f'Could not parse wallet json for signature: {e}')
            return ''

    @staticmethod
    def _looks_like_mnemonic(text: str) -> bool:
        return bool(text and (' ' in text) and len(text.split()) >= 12)

    def _derive_from_seed(self, seed: str) -> str:
        # If 64-character hex, treat as ed25519 seed
        s = seed.strip()
        if s.startswith('0x') or s.startswith('0X'):
            s = s[2:]
        if len(s) == 64 and all(c in '0123456789abcdefABCDEF' for c in s):
            try:
                sk = SigningKey(bytes.fromhex(s))
                return sk.encode(encoder=HexEncoder).decode('ascii')
            except Exception:
                return ''
        # Otherwise, try deriving from mnemonic via substrate-interface if available
        if _HAS_SUBSTRATE:
            try:
                kp = Keypair.create_from_mnemonic(s, crypto_type=KeypairType.ED25519)
                # Substrate Keypair exposes private_key as bytes
                pk_bytes = getattr(kp, 'private_key', None)
                if pk_bytes:
                    return pk_bytes.hex()
            except Exception as e:
                self.get_logger().warn(f'Failed mnemonic derivation via substrate: {e}')
        return ''

    # --------------------------- Signing & Envelope ------------------------ #
    def _sign_payload(self, data_sha256: str, created_at: int, robot_id: str) -> (str, str):
        algo = self.signature_algorithm.lower()
        challenge = f'{data_sha256}|{created_at}|{robot_id}'.encode('utf-8')
        
        if algo == 'sr25519':
            # Use PeaqRobot's keypair for Sr25519 signing (Substrate standard)
            if not self._robot_sdk:
                raise RuntimeError('PeaqRobot SDK not initialized for sr25519 signing')
            
            # Sign using Sr25519
            import hashlib
            challenge_hash = hashlib.sha256(challenge).digest()
            signature = self._robot_sdk.keypair.sign(challenge_hash)
            public_key = self._robot_sdk.keypair.public_key
            
            return public_key.hex(), signature.hex()
        
        elif algo == 'ed25519':
            # Legacy Ed25519 support (deprecated - use sr25519 instead)
            if not _HAS_NACL:
                raise RuntimeError('PyNaCl is required for ed25519 signing')
            if not self.private_key_hex:
                raise RuntimeError('signature.private_key_hex is required for ed25519 signing')
            sk = SigningKey(self.private_key_hex, encoder=HexEncoder)
            sig = sk.sign(challenge).signature
            vk = sk.verify_key
            return vk.encode(encoder=HexEncoder).decode('ascii'), sig.hex()
        
        raise RuntimeError(f'Unsupported signature algorithm: {self.signature_algorithm}')

    @staticmethod
    def _build_envelope(
        *,
        content_type: str,
        created_at: int,
        robot_id: str,
        data_cid: str,
        data_sha256: str,
        algorithm: str,
        public_key_hex: str,
        signature_hex: str,
        metadata_json: str,
    ) -> Dict[str, Any]:
        header = {
            'contentType': content_type or 'application/octet-stream',
            'createdAt': created_at,
            'robotId': robot_id,
        }
        payload = {
            'dataCid': data_cid,
            'dataSha256': data_sha256,
        }
        proof = {
            'algorithm': algorithm,
            'publicKeyHex': public_key_hex,
            'signatureHex': signature_hex,
        }
        env: Dict[str, Any] = {
            'schema': 'peaq-ipfs-envelope@v1',
            'header': header,
            'payload': payload,
            'proof': proof,
        }
        if metadata_json:
            try:
                env['meta'] = json.loads(metadata_json)
            except Exception:
                env['meta'] = {'raw': metadata_json}
        return env

    # --------------------------- Storage Pallet Call ----------------------- #
    def _call_store_add_async(self, key: str, value_json: str, envelope_cid: str) -> None:
        if not self._store_add_client.wait_for_service(timeout_sec=5.0):
            self.get_logger().error(f'Storage add service not available: {self._store_add_srv_name}')
            # Publish failed status
            self._publish_status(key=key, cid=envelope_cid, tx_hash='', status='FAILED', error='storage/add service unavailable')
            return
        req = StoreAddData.Request()
        req.key = key
        req.value_json = value_json
        req.mode = ''  # let CoreNode apply default confirmation mode
        future = self._store_add_client.call_async(req)
        self._pending_futures.append(future)

        def _done_cb(fut):
            try:
                if fut.cancelled():
                    self.get_logger().error('Storage add call cancelled')
                    self._handle_blockchain_failure(key, envelope_cid, 'storage/add cancelled')
                    return
                res = fut.result()
                if res is None:
                    self.get_logger().error('Storage add returned no result')
                    self._handle_blockchain_failure(key, envelope_cid, 'no result')
                    return
                result_text = res.result or ''
                if result_text.startswith('Success:'):
                    tx_hash = result_text.split(':', 1)[1].strip()
                    # Track mapping for subsequent tx status updates
                    if tx_hash:
                        self._pending_tx_by_key[tx_hash] = key
                    # Publish initial PENDING with tx hash
                    self._publish_status(key=key, cid=envelope_cid, tx_hash=tx_hash, status='PENDING', error='')
                    self.get_logger().info(f'Storage add service returned tx={tx_hash}')
                    # Success - remove from retry queue
                    self._retry_queue.pop(key, None)
                else:
                    self.get_logger().error(f'Storage add error: {result_text}')
                    self._handle_blockchain_failure(key, envelope_cid, result_text)
            except Exception as exc:  # noqa: BLE001
                self.get_logger().error(f'storage add callback error: {exc}')
                self._handle_blockchain_failure(key, envelope_cid, str(exc))
            finally:
                try:
                    self._pending_futures.remove(fut)
                except Exception:
                    pass

        future.add_done_callback(_done_cb)

    # --------------------------- Retry & Failure Tracking ------------------------ #
    def _handle_blockchain_failure(self, key: str, envelope_cid: str, error: str) -> None:
        """Handle blockchain submission failure with retry logic and failure tracking."""
        retry_info = self._retry_queue.get(key)
        if not retry_info:
            self.get_logger().error(f'No retry info found for key={key}')
            self._publish_status(key=key, cid=envelope_cid, tx_hash='', status='FAILED', error=error)
            self._log_failure(key, envelope_cid, '', 'blockchain_submit', error, 0, 0)
            return
        
        retry_info['attempt'] += 1
        attempt = retry_info['attempt']
        max_retries = retry_info['max_retries']
        
        self.get_logger().warn(
            f'Blockchain submission failed for key={key} (attempt {attempt}/{max_retries}): {error}'
        )
        
        # Check if we should retry
        if attempt < max_retries:
            # Schedule retry
            self.get_logger().info(f'Scheduling retry for key={key} in {self._retry_delay_seconds}s')
            self._publish_status(
                key=key,
                cid=envelope_cid,
                tx_hash='',
                status='RETRYING',
                error=f'Retry {attempt}/{max_retries}: {error}',
            )
            
            # Create timer for retry
            retry_timer = self.create_timer(
                self._retry_delay_seconds,
                lambda: self._retry_blockchain_submit(key)
            )
            retry_info['retry_timer'] = retry_timer
        else:
            # Max retries exceeded - log failure permanently
            self.get_logger().error(
                f'Max retries ({max_retries}) exceeded for key={key}. '
                f'Data uploaded to IPFS (CID: {envelope_cid}) but NOT stored on blockchain.'
            )
            self._publish_status(
                key=key,
                cid=envelope_cid,
                tx_hash='',
                status='FAILED',
                error=f'Max retries exceeded: {error}',
            )
            
            # Log to persistent failure log
            self._log_failure(
                key=key,
                envelope_cid=envelope_cid,
                data_cid=retry_info.get('data_cid', ''),
                stage='blockchain_submit',
                error=error,
                attempts=attempt,
                timestamp=retry_info.get('timestamp', time.time()),
            )
            
            # Remove from retry queue
            self._retry_queue.pop(key, None)
    
    def _retry_blockchain_submit(self, key: str) -> None:
        """Retry blockchain submission for a failed operation."""
        retry_info = self._retry_queue.get(key)
        if not retry_info:
            self.get_logger().warn(f'Retry called but no retry info for key={key}')
            return
        
        # Cancel and remove the timer
        if 'retry_timer' in retry_info:
            retry_info['retry_timer'].cancel()
            del retry_info['retry_timer']
        
        envelope_cid = retry_info['envelope_cid']
        value_json = retry_info['value_json']
        attempt = retry_info['attempt']
        
        self.get_logger().info(f'Retrying blockchain submission for key={key} (attempt {attempt})')
        
        # Update stage for tracking
        retry_info['stage'] = f'blockchain_submit_retry_{attempt}'
        
        # Retry the blockchain submission
        self._call_store_add_async(key, value_json, envelope_cid)
    
    def _log_failure(
        self,
        key: str,
        envelope_cid: str,
        data_cid: str,
        stage: str,
        error: str,
        attempts: int,
        timestamp: float,
    ) -> None:
        """Log failure to persistent JSONL file for later analysis/recovery."""
        try:
            failure_record = {
                'timestamp': timestamp or time.time(),
                'timestamp_iso': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(timestamp or time.time())),
                'key': key,
                'stage': stage,
                'envelope_cid': envelope_cid,
                'data_cid': data_cid,
                'error': error,
                'attempts': attempts,
                'robot_id': self.robot_id,
                'network': self.network,
                'ipfs_gateway': self.ipfs_gateway_url,
            }
            
            # Append to JSONL file
            with open(self._failure_log_path, 'a') as f:
                f.write(json.dumps(failure_record) + '\n')
            
            self.get_logger().info(f'Failure logged to {self._failure_log_path}')
            self.get_logger().info(
                f'RECOVERY INFO: Data is available at IPFS CID {envelope_cid}. '
                f'You can manually retry blockchain submission with: '
                f'ros2 service call /{self.core_node_name}/storage/add '
                f'peaq_ros2_interfaces/srv/StoreAddData '
                f'"{{key: \\"{key}\\", value_json: \\"{{\\\\\\\"envelopeCid\\\\\\\": \\\\\\"{envelope_cid}\\\\\\"}}\\"}}\"'
            )
            
        except Exception as e:
            self.get_logger().error(f'Failed to log failure to {self._failure_log_path}: {e}')

    # ------------------------------- Utilities ---------------------------- #
    def _publish_status(self, *, key: str, cid: str, tx_hash: str, status: str, error: str) -> None:
        msg = StorageResult()
        msg.key = key
        msg.cid = cid
        base_url = self.ipfs_gateway_url.rstrip('/')
        msg.ipfs_url = (base_url + '/' + cid) if cid else ''
        msg.tx_hash = tx_hash
        msg.status = status
        msg.error = error
        self._status_pub.publish(msg)

    @staticmethod
    def _is_valid_did(robot_id: str) -> bool:
        if not robot_id:
            return False
        parts = robot_id.split(':')
        if len(parts) != 3:
            return False
        if parts[0] != 'did' or parts[1] != 'peaq':
            return False
        if not parts[2] or len(parts[2]) < 10:
            return False
        return True
    
    def _verify_did_exists(self, did: str) -> bool:
        """Verify that a DID exists on the blockchain by calling the identity/read service.
        
        Args:
            did: The DID to verify (e.g., did:peaq:5DRV...)
            
        Returns:
            True if DID exists on blockchain, False otherwise
        """
        try:
            from peaq_ros2_interfaces.srv import IdentityRead
            
            # Wait for identity read service to be available
            if not self._identity_read_client.wait_for_service(timeout_sec=10.0):
                self.get_logger().error(f'Identity read service not available: {self._identity_read_srv_name}')
                self.get_logger().error('Make sure the core node is running before starting the storage bridge')
                return False
            
            # Call the service synchronously (no parameters - reads DID for core_node's wallet)
            req = IdentityRead.Request()
            
            self.get_logger().info(f'Calling identity/read service to verify DID: {did}')
            future = self._identity_read_client.call_async(req)
            
            # Wait for response (with timeout)
            import rclpy
            timeout = 15.0  # seconds
            start_time = time.time()
            while not future.done():
                rclpy.spin_once(self, timeout_sec=0.1)
                if time.time() - start_time > timeout:
                    self.get_logger().error(f'Timeout waiting for identity/read response')
                    return False
            
            response = future.result()
            if response is None:
                self.get_logger().error('Identity read returned no result')
                return False
            
            # Parse the doc_json response
            doc_json = response.doc_json or '{}'
            self.get_logger().debug(f'Identity read doc_json: {doc_json[:200]}...')
            
            # Parse JSON to check exists field
            try:
                import json
                doc = json.loads(doc_json)
                exists = doc.get('exists', False)
                read_status = doc.get('read_status', '')
                
                if exists and read_status == 'success':
                    self.get_logger().info(f'DID verified successfully on blockchain')
                    return True
                else:
                    self.get_logger().info(f'DID not found on blockchain (exists={exists}, status={read_status})')
                    return False
            except json.JSONDecodeError as e:
                self.get_logger().error(f'Failed to parse identity read response: {e}')
                return False
            
        except Exception as e:
            self.get_logger().error(f'Failed to verify DID on blockchain: {e}')
            return False

    @staticmethod
    def _read_content(msg: StorageIngest) -> bytes:
        if msg.is_file:
            if not msg.file_path:
                raise ValueError('file_path is required when is_file=true')
            with open(msg.file_path, 'rb') as f:
                return f.read()
        return (msg.content or '').encode('utf-8')


def main(args=None) -> None:
    rclpy.init(args=args)
    node = StorageBridgeNode()
    executor = MultiThreadedExecutor()
    executor.add_node(node)
    try:
        executor.spin()
    except KeyboardInterrupt:
        pass
    finally:
        executor.shutdown()
        try:
            node.destroy_node()
        except Exception:
            pass
        try:
            if rclpy.ok():
                rclpy.shutdown()
        except Exception:
            pass
