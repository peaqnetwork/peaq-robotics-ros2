# Peaq ROS2 Configuration

## Unified Configuration (Recommended)

Use `peaq_robot.yaml` for all nodes. This single file configures both core_node and storage_bridge_node.

### Usage

```bash
# Start core node
ros2 run peaq_ros2_core core_node --ros-args \
  -p config.yaml_path:=/work/packages/ros2/peaq_ros2_examples/config/peaq_robot.yaml

# Start storage bridge
ros2 run peaq_ros2_core storage_bridge_node --ros-args \
  -p config.yaml_path:=/work/packages/ros2/peaq_ros2_examples/config/peaq_robot.yaml
```

### Benefits

1. **Single source of truth** - Network, wallet, and logging configured once
2. **No duplication** - Shared settings in one place
3. **Easy maintenance** - Update wallet path in one location
4. **Consistent configuration** - All nodes use same network/wallet
5. **Future-proof** - Easy to add new nodes

### Structure

```yaml
# Shared configuration (used by all nodes)
network: agung
wallet:
  path: /work/.ros_e2e_wallet.json
  auto_generate: false
logging:
  level: INFO
  format: human

# Core node specific
core_node:
  confirmation_mode: FAST
  events:
    enabled: true

# Storage bridge specific
storage_bridge:
  robot:
    require_did: true  # DID auto-derived from wallet
  storage:
    mode: pinata
    pinata:
      jwt: "your_jwt_here"
```

## Legacy Configuration (Still Supported)

Old separate files `core.yaml` and `bridge.yaml` still work for backward compatibility.

### Migration from Legacy

**Old way (2 files):**
```yaml
# core.yaml
network: agung
keystore:
  path: /work/.ros_e2e_wallet.json

# bridge.yaml
network: agung
signature:
  wallet_json_path: /work/.ros_e2e_wallet.json
```

**New way (1 file):**
```yaml
# peaq_robot.yaml
network: agung
wallet:
  path: /work/.ros_e2e_wallet.json
```

## Configuration Options

### Shared Settings

**network** - Blockchain network
- `agung` - Testnet (default)
- `peaq` - Mainnet
- Custom WSS URL

**wallet.path** - Path to wallet JSON file
- Absolute path recommended
- Used by all nodes

**wallet.auto_generate** - Auto-create wallet if missing (SAFE - never overwrites)
- `false` - Fail if wallet doesn't exist (default)
- `true` - Generate new wallet if file doesn't exist, use existing if it does
- **Important:** If wallet exists, it will be reused (never overwritten)
- **To regenerate:** Delete the wallet file first, then restart node

**logging.level** - Log verbosity
- `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`

**logging.format** - Log format
- `human` - Human-readable (default)
- `json` - JSON structured logs

### Core Node Settings

**core_node.confirmation_mode** - Transaction confirmation
- `FAST` - Wait for inclusion in block (default)
- `FINAL` - Wait for finalization

**core_node.events.enabled** - Event streaming
- `true` - Enable blockchain event streaming (default)
- `false` - Disable events

### Storage Bridge Settings

**storage_bridge.robot.require_did** - Require and verify DID
- `true` - Auto-derive DID from wallet, verify on blockchain, ERROR if not found (default, recommended for production)
- `false` - Skip DID verification, WARNING only (for development)
- **Note:** DID is automatically derived as `did:peaq:<wallet_address>`, no manual configuration needed

**storage_bridge.storage.mode** - Storage backend
- `local_ipfs` - Local IPFS daemon only
- `pinata` - Pinata cloud only (recommended)
- `both` - Upload to both

**storage_bridge.storage.pinata.jwt** - Pinata authentication
- Get from https://pinata.cloud
- Recommended over API key/secret

## Examples

### Development Setup

```yaml
network: agung
wallet:
  path: ~/.peaq_robot/dev_wallet.json
  auto_generate: true  # Creates wallet if missing, reuses if exists
logging:
  level: DEBUG

core_node:
  confirmation_mode: FAST

storage_bridge:
  robot:
    require_did: false  # Skip DID verification for faster dev
  storage:
    mode: local_ipfs
```

### Production Setup

```yaml
network: peaq  # Mainnet
wallet:
  path: /secure/production_wallet.json
  auto_generate: false
logging:
  level: INFO
  format: json

core_node:
  confirmation_mode: FINAL
  events:
    enabled: true

storage_bridge:
  robot:
    require_did: true  # Verify DID on blockchain (production)
  storage:
    mode: pinata
    pinata:
      jwt: "production_jwt_here"
      gateway_url: https://gateway.pinata.cloud/ipfs
```

### Testing Without DID

```yaml
network: agung
wallet:
  path: /tmp/test_wallet.json
  auto_generate: true

storage_bridge:
  robot:
    require_did: false  # Skip DID verification for testing
  storage:
    mode: local_ipfs
```

## Troubleshooting

### Network Mismatch

**Problem:** Storage bridge can't verify DID

**Solution:** Ensure `network` is the same for all nodes
```yaml
network: agung  # Must be same everywhere
```

### Wallet Not Found

**Problem:** `Failed to load wallet from /path/to/wallet.json`

**Solution:** Either create wallet or enable auto-generate
```yaml
wallet:
  path: /work/.ros_e2e_wallet.json
  auto_generate: true  # Creates if missing, reuses if exists
```

### Regenerate Wallet

**Problem:** Want to create a new wallet but auto_generate is reusing existing one

**Solution:** Delete the existing wallet file first
```bash
# Delete existing wallet
rm ~/.peaq_robot/storage_bridge_wallet.json

# Restart node - will generate new wallet
ros2 run peaq_ros2_core storage_bridge_node --ros-args \
  -p config.yaml_path:=/work/packages/ros2/peaq_ros2_examples/config/peaq_robot.yaml
```

### DID Verification Failed

**Problem:** `DID "did:peaq:5ABC..." does not exist on blockchain`

**Solution:** The DID is auto-derived from your wallet address. Create it first:
```bash
# DID will be shown in the error message
ros2 service call /peaq_core_node/identity/create \
  peaq_ros2_interfaces/srv/IdentityCreate \
  "{name: 'did:peaq:5ABC...'}"  # Use the DID from error message
```

Or disable verification for development:
```yaml
storage_bridge:
  robot:
    require_did: false
```

### How DID Auto-Derivation Works

**No manual DID configuration needed!**

1. Storage bridge loads wallet (existing or auto-generated)
2. Extracts wallet address (e.g., `5DRVRDMh8PvUb9ViXwFwasQ5CB1oDVHp4AGtKz8NCZKxar8K`)
3. Auto-derives DID: `did:peaq:5DRVRDMh8PvUb9ViXwFwasQ5CB1oDVHp4AGtKz8NCZKxar8K`
4. If `require_did=true`: verifies DID exists on blockchain
5. If `require_did=false`: skips verification (development mode)
