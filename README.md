# peaq ROS 2 SDK

ROS 2 integration for peaq blockchain - enabling robots to interact with decentralized identity, storage, and access control systems.

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![ROS 2](https://img.shields.io/badge/ROS%202-Humble-blue)](https://docs.ros.org/en/humble/)
[![Python](https://img.shields.io/badge/Python-3.8%2B-blue)](https://www.python.org/)

## Features

- **🔐 Identity Management**: Create and manage robot DIDs on-chain
- **📦 Blockchain Storage**: Store robot telemetry with IPFS integration (Pinata support)
- **🔑 Access Control**: Role-based permissions for robot operations
- **📡 Event Streaming**: Real-time blockchain event processing
- **🤖 Humanoid Control**: Blockchain-driven robot motion control (Unitree G1 support)
- **🔄 Automatic Retry & Recovery**: Built-in retry logic and failure tracking for reliable operations

## Quick Start

### Prerequisites

- Docker (recommended) or ROS 2 Humble
- Python 3.8+
- Internet connection for blockchain and IPFS

### Docker Installation (Recommended)

```bash
# 1. Clone repository
git clone https://github.com/peaqnetwork/peaq-robotics-ros2.git
cd peaq-robotics-ros2

# 2. Build Docker image
docker build -t peaq-ros2:latest .

# 3. Start container
docker run -it --name peaq-ros2-test \
  -v $(pwd):/work \
  -w /work \
  -p 5001:5001 \
  -p 8080:8080 \
  peaq-ros2:latest

# 4. Inside container: Build packages
source /opt/ros/humble/setup.bash
colcon build
source install/setup.bash

# 5. Start core node
ros2 run peaq_ros2_core core_node --ros-args \
  -p config.yaml_path:=/work/peaq_ros2_examples/config/peaq_robot.yaml &

# 6. Configure and activate
ros2 lifecycle set /peaq_core_node configure
ros2 lifecycle set /peaq_core_node activate

# 7. Test
ros2 service call /peaq_core_node/info peaq_ros2_interfaces/srv/GetNodeInfo
```

### Local Installation

```bash
# 1. Install ROS 2 Humble
# Follow: https://docs.ros.org/en/humble/Installation.html

# 2. Clone and build
git clone https://github.com/peaqnetwork/peaq-robotics-ros2.git
cd peaq-robotics-ros2
pip install -r requirements.txt
source /opt/ros/humble/setup.bash
colcon build
source install/setup.bash

# 3. Run
ros2 run peaq_ros2_core core_node
```

## Documentation

- **[E2E_TEST.md](./E2E_TEST.md)** - Complete end-to-end testing guide with step-by-step instructions

## Architecture

```
┌───────────────────────────────────────────────────────────┐
│                     ROS 2 Application Layer               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │   Robot      │  │   Sensors    │  │  Actuators   │     │
│  │  Control     │  │   & Data     │  │  & Motion    │     │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘     │
└─────────┼─────────────────┼─────────────────┼─────────────┘
          │                 │                 │
          ▼                 ▼                 ▼
┌───────────────────────────────────────────────────────────┐
│                    peaq ROS 2 SDK Layer                   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │  Core Node   │  │Storage Bridge│  │Humanoid Bridge│    │
│  │  (Services)  │  │   (IPFS)     │  │  (Control)   │     │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘     │
└─────────┼─────────────────┼─────────────────┼─────────────┘
          │                 │                 │
          ▼                 ▼                 ▼
┌───────────────────────────────────────────────────────────┐
│                    peaq Blockchain Layer                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │   Identity   │  │   Storage    │  │    Access    │     │
│  │   Pallet     │  │   Pallet     │  │   Control    │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
└───────────────────────────────────────────────────────────┘
```


## Core Services

### Identity Management

Create and manage decentralized identities (DIDs) for robots:

```bash
# Create DID
ros2 service call /peaq_core_node/identity/create \
  peaq_ros2_interfaces/srv/IdentityCreate \
  '{metadata_json: "{\"type\": \"robot\"}"}'

# Read DID
ros2 service call /peaq_core_node/identity/read \
  peaq_ros2_interfaces/srv/IdentityRead
```

### Storage

Store data on blockchain with IPFS:

```bash
# Publish data
ros2 topic pub --once /peaq/storage/ingest \
  peaq_ros2_interfaces/msg/StorageIngest \
  '{key: "sensor_data", content: "temperature:25.5", is_file: false}'

# Read from blockchain
ros2 service call /peaq_core_node/storage/read \
  peaq_ros2_interfaces/srv/StoreReadData \
  '{key: "sensor_data"}'
```

### Access Control

Manage permissions and roles:

```bash
# Create role
ros2 service call /peaq_core_node/access/create_role \
  peaq_ros2_interfaces/srv/AccessCreateRole \
  '{role_id: "operator"}'

# Grant role
ros2 service call /peaq_core_node/access/grant_role \
  peaq_ros2_interfaces/srv/AccessGrantRole \
  '{user_did: "did:peaq:5G...", role_id: "operator"}'
```

## Configuration

All configuration is in a single file: `peaq_ros2_examples/config/peaq_robot.yaml`

### Basic Configuration

```yaml
# Network
network: agung  # testnet (or 'peaq' for mainnet)

# Wallet
wallet:
  path: /work/peaq_wallet.json
  auto_generate: true  # Auto-generate if doesn't exist

# Storage Bridge
storage_bridge:
  robot:
    require_did: true  # Verify DID on blockchain
  storage:
    mode: pinata  # or 'local_ipfs' or 'both'
    pinata:
      jwt: "your_pinata_jwt_token"
      gateway_url: "https://your-gateway.mypinata.cloud/ipfs"
```

### Get Pinata Credentials

1. Sign up at [pinata.cloud](https://pinata.cloud)
2. Create API key with pinning permissions
3. Get your gateway URL from dashboard
4. Add to `peaq_robot.yaml`

## Service Reference

### Available Services

| Service | Description | Parameters |
|---------|-------------|------------|
| `/peaq_core_node/info` | Get node information | None |
| `/peaq_core_node/identity/create` | Create DID | `metadata_json` (optional) |
| `/peaq_core_node/identity/read` | Read DID document | None |
| `/peaq_core_node/storage/add` | Store data on-chain | `key`, `value_json` |
| `/peaq_core_node/storage/read` | Read data from chain | `key` |
| `/peaq_core_node/access/create_role` | Create access role | `role_id` |
| `/peaq_core_node/access/grant_role` | Grant role to user | `user_did`, `role_id` |
| `/peaq_core_node/access/create_permission` | Create permission | `permission_id` |
| `/peaq_core_node/access/assign_permission` | Assign permission | `role_id`, `permission_id` |

### Message Types

| Topic | Message Type | Description |
|-------|--------------|-------------|
| `/peaq/storage/ingest` | `StorageIngest` | Publish data to store |
| `/peaq/storage/status` | `StorageResult` | Storage operation status |
| `/peaq/tx_status` | `TxStatus` | Transaction status updates |


## Retry and Recovery System

The storage bridge includes automatic retry logic for failed blockchain operations:

### Features

- **Automatic Retries**: Up to 3 attempts with 5-second delays
- **Failure Tracking**: All failures logged to `/tmp/storage_bridge_failures.jsonl`
- **Data Preservation**: IPFS CIDs saved even when blockchain fails
- **Easy Recovery**: Tools to retry failed operations

### Check Failures

```bash
# View summary
python3 scripts/check_storage_failures.py

# View details
python3 scripts/check_storage_failures.py --details

# Retry all failures
python3 scripts/retry_failed_storage.py

# Retry specific key
python3 scripts/retry_failed_storage.py --key sensor_data
```

### How It Works

```
Data Upload → IPFS Success (CID saved) → Blockchain Submit → FAILS
                                              ↓
                                         Retry #1 (5s delay)
                                              ↓
                                         Retry #2 (5s delay)
                                              ↓
                                         Retry #3 (5s delay)
                                              ↓
                                    Log to failure file
                                    (Data safe on IPFS!)
```

## Troubleshooting

### "The passed service type is invalid"

**Cause**: Workspace not sourced

**Solution**:
```bash
source /opt/ros/humble/setup.bash
source install/setup.bash
```

### Service calls hang

**Check node status**:
```bash
ros2 node list
ros2 lifecycle get /peaq_core_node
```

**If inactive**:
```bash
ros2 lifecycle set /peaq_core_node configure
ros2 lifecycle set /peaq_core_node activate
```

### Empty tx_hash in response

**Cause**: Insufficient wallet funds or transaction error

**Solution**:
1. Check logs: `tail -50 /tmp/core_node.log`
2. Fund wallet at https://faucet.peaq.network/
3. Retry operation

### Storage upload fails

**Check**:
1. IPFS daemon running: `ipfs version`
2. Pinata credentials correct in config
3. Network connectivity
4. Check failure log: `python3 scripts/check_storage_failures.py`

## Development

### Project Structure

```
peaq-robotics-ros2/
├── peaq_ros2_interfaces/    # ROS2 message/service definitions
├── peaq_ros2_core/          # Core node and storage bridge
├── peaq_ros2_humanoids/     # Humanoid robot adapters
├── peaq_ros2_examples/      # Example configurations
├── scripts/                 # Utility scripts
│   ├── check_storage_failures.py
│   ├── retry_failed_storage.py
│   └── docker-setup.sh
├── Dockerfile              # Docker image definition
├── requirements.txt        # Python dependencies
└── E2E_TEST.md            # Complete testing guide
```

### Building from Source

```bash
# Install dependencies
pip install -r requirements.txt

# Build all packages
source /opt/ros/humble/setup.bash
colcon build

# Build specific package
colcon build --packages-select peaq_ros2_core

# Clean build
rm -rf build install log
colcon build
```

### Running Tests

```bash
# Source workspace
source install/setup.bash

# Run tests
colcon test

# View test results
colcon test-result --verbose
```


## Examples

### Complete Workflow

```bash
# 1. Start core node
ros2 run peaq_ros2_core core_node --ros-args \
  -p config.yaml_path:=/work/peaq_ros2_examples/config/peaq_robot.yaml &

# 2. Configure and activate
ros2 lifecycle set /peaq_core_node configure
ros2 lifecycle set /peaq_core_node activate

# 3. Get wallet address
ros2 service call /peaq_core_node/info peaq_ros2_interfaces/srv/GetNodeInfo

# 4. Fund wallet at https://faucet.peaq.network/

# 5. Create DID
ros2 service call /peaq_core_node/identity/create \
  peaq_ros2_interfaces/srv/IdentityCreate \
  '{metadata_json: "{\"type\": \"robot\"}"}'

# 6. Start storage bridge
ros2 run peaq_ros2_core storage_bridge_node --ros-args \
  -p config.yaml_path:=/work/peaq_ros2_examples/config/peaq_robot.yaml &

# 7. Store data
ros2 topic pub --once /peaq/storage/ingest \
  peaq_ros2_interfaces/msg/StorageIngest \
  '{key: "sensor_data", content: "temperature:25.5", is_file: false}'

# 8. Verify on blockchain
ros2 service call /peaq_core_node/storage/read \
  peaq_ros2_interfaces/srv/StoreReadData \
  '{key: "sensor_data"}'
```

### Humanoid Robot Control

```bash
# Start humanoid bridge (Unitree G1)
ros2 run peaq_ros2_humanoids humanoid_bridge_node --ros-args \
  -p config.yaml_path:=/work/peaq_ros2_examples/config/peaq_robot.yaml

# Send motion command
ros2 topic pub /peaq/humanoid/motion \
  peaq_ros2_interfaces/msg/HumanoidMotion \
  '{action: "walk", parameters: "{\"speed\": 0.5}"}'
```

## Monitoring

### Real-time Logs

```bash
# Core node logs
tail -f /tmp/core_node.log

# Storage bridge logs
tail -f /tmp/storage_bridge.log

# Filter for errors
tail -f /tmp/core_node.log | grep -i error
```

### ROS 2 Tools

```bash
# List nodes
ros2 node list

# List topics
ros2 topic list

# List services
ros2 service list | grep peaq

# Echo topic
ros2 topic echo /peaq/storage/status

# Node info
ros2 node info /peaq_core_node
```

## Production Deployment

### Security Checklist

- [ ] Use production wallet (not auto-generated)
- [ ] Store wallet securely (encrypted, backed up)
- [ ] Use mainnet (`network: peaq`)
- [ ] Enable DID verification (`require_did: true`)
- [ ] Use FINAL confirmation mode for critical operations
- [ ] Set up monitoring and alerts
- [ ] Backup failure logs regularly
- [ ] Rotate Pinata credentials periodically

### Performance Tuning

```yaml
# In peaq_robot.yaml

# Fast confirmation (testing)
core_node:
  confirmation_mode: FAST

# Final confirmation (production)
core_node:
  confirmation_mode: FINAL

# Adjust retry settings
storage_bridge:
  retry:
    max_attempts: 5
    delay_seconds: 10.0
```

## Contributing

We welcome contributions! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

## Support

- **Documentation**: See [E2E_TEST.md](./E2E_TEST.md) for detailed testing guide
- **Issues**: Report bugs at [GitHub Issues](https://github.com/peaqnetwork/peaq-robotics-ros2/issues)
- **Community**: Join our [Discord](https://discord.gg/peaq)

## License

Apache 2.0 - See [LICENSE](LICENSE) file for details

## Acknowledgments

- Built on [ROS 2 Humble](https://docs.ros.org/en/humble/)
- Powered by [peaq Network](https://www.peaq.network/)
- IPFS integration via [Pinata](https://pinata.cloud/)

---

**Ready to get started?** Follow the [E2E_TEST.md](./E2E_TEST.md) guide for a complete walkthrough.

