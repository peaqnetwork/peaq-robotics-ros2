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

### Standalone (Non-Docker) Setup

Use this if you want to run on your host machine or directly on a robot/humanoid without Docker.

1) Install prerequisites

```bash
# Ubuntu 22.04 recommended (Linux host)
sudo apt update && sudo apt install -y \
  python3-pip git curl wget nano vim \
  python3-colcon-common-extensions build-essential

# Optional dev helpers
sudo apt install -y ros-humble-ros-dev-tools || true

# Install ROS 2 Humble (desktop) and source it
# Follow official guide: https://docs.ros.org/en/humble/Installation.html
# Tip: add this to ~/.bashrc after install
echo 'source /opt/ros/humble/setup.bash' >> ~/.bashrc
source ~/.bashrc
```

2) Install IPFS (Kubo) and initialize

```bash
# Download and install Kubo (IPFS)
KUBO_VER=v0.38.1
wget https://dist.ipfs.tech/kubo/${KUBO_VER}/kubo_${KUBO_VER}_linux-amd64.tar.gz
tar -xvzf kubo_${KUBO_VER}_linux-amd64.tar.gz
cd kubo && sudo bash install.sh && cd ..
rm -rf kubo kubo_${KUBO_VER}_linux-amd64.tar.gz

# Initialize IPFS repo
ipfs init

# Start IPFS daemon (new terminal recommended)
ipfs daemon

# Optional: run IPFS via systemd (Ubuntu)
sudo bash -c 'cat >/etc/systemd/system/ipfs.service <<EOF
[Unit]
Description=IPFS daemon
After=network-online.target

[Service]
User='"$USER"'
ExecStart=/usr/local/bin/ipfs daemon
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF'
sudo systemctl daemon-reload && sudo systemctl enable --now ipfs
```

3) Python dependencies

```bash
pip3 install --upgrade pip
pip3 install -r requirements.txt
 
# Resolve any missing system deps
sudo rosdep init 2>/dev/null || true
rosdep update
rosdep install --from-paths . --ignore-src -r -y || true
```

4) Build and source workspace

```bash
source /opt/ros/humble/setup.bash
colcon build
source install/setup.bash
```

5) Configure credentials and run

```bash
# Create your config from the example and set Pinata JWT/gateway
cp peaq_ros2_examples/config/peaq_robot.example.yaml \
   peaq_ros2_examples/config/peaq_robot.yaml

# Edit peaq_ros2_examples/config/peaq_robot.yaml
# - storage_bridge.storage.pinata.jwt = YOUR_PINATA_JWT
# - storage_bridge.storage.pinata.gateway_url = your Pinata gateway URL

# Start core node
ros2 run peaq_ros2_core core_node --ros-args \
  -p config.yaml_path:=/work/peaq_ros2_examples/config/peaq_robot.yaml &

# Configure and activate
ros2 lifecycle set /peaq_core_node configure
ros2 lifecycle set /peaq_core_node activate

# Start storage bridge
ros2 run peaq_ros2_core storage_bridge_node --ros-args \
  -p config.yaml_path:=/work/peaq_ros2_examples/config/peaq_robot.yaml &
```

Notes:
- If running on a robot, ensure network/firewall allows IPFS API (default 5001) and gateway (8080) locally or adjust config accordingly.
- Pinata credentials must never be committed; they belong only in your local `peaq_robot.yaml`.
- Platform note: Native ROS 2 Humble support varies by OS. Docker-based setup is recommended for consistency. If running natively on a non-Linux OS, consider a Linux VM or WSL for best results.

Manual equivalent of Dockerfile steps:
- Install apt packages: python3-pip, git, curl, wget, editors
- Install Kubo (IPFS), `ipfs init`, and run `ipfs daemon`
- `pip3 install -r requirements.txt`
- Ensure ROS 2 Humble is installed and sourced

### Running on Humanoids/Robots (Host OS)

For humanoids (e.g., Unitree G1) or robots without Docker:

1) Follow the Standalone Setup steps above (install ROS 2, IPFS, Python deps).

2) Configure humanoid adapter

```yaml
# In peaq_ros2_examples/config/peaq_robot.yaml
humanoids:
  adapter: unitree_g1  # or your custom adapter
  adapter_config:
    max_linear_velocity: 1.0
    max_angular_velocity: 2.0
    motion_timeout: 5.0
```

3) Launch humanoid bridge

```bash
ros2 run peaq_ros2_humanoids humanoid_bridge_node --ros-args \
  -p config.yaml_path:=/work/peaq_ros2_examples/config/peaq_robot.yaml
```

4) Safety
- Verify emergency stop wiring/command path before real motion.
- Start with low velocities and short timeouts; validate in a safe area.

Troubleshooting on devices:
- Ensure real-time clock and time sync are correct.
- Validate ROS 2 network discovery across interfaces (set `ROS_DOMAIN_ID` consistently).
- IPFS must be running locally or `storage_bridge.storage.local_ipfs.api_url` should point to a reachable node.

## Documentation

- **[E2E_TEST.md](./E2E_TEST.md)** - Complete end-to-end testing guide with step-by-step instructions

## Tether WDK (peaq EVM USDT) Integration

This repo includes an optional ROS2 node (`peaq_ros2_tether`) that integrates with Tether WDK’s EVM wallet module to:
- Create EVM wallets (mnemonic stored locally on the robot/machine)
- Query USDT balance (ERC-20)
- Transfer USDT on peaq EVM

Constraints/notes:
- No WDK chain listing changes required (WDK EVM wallet supports arbitrary EVM RPC providers).
- No smart contract deployments required (uses existing USDT contract).
- Secrets are stored in a **single local registry file**; do not enable mnemonic export in production.

Setup (once, on the robot/machine):

```bash
cd peaq_ros2_tether/js
npm install
```

Config:
- Copy `peaq_ros2_examples/config/peaq_robot.example.yaml` to `peaq_robot.yaml`
- Set:
  - `tether.enabled: true`
  - `tether.evm.rpc_url: https://quicknode1.peaq.xyz`
  - `tether.usdt.contract: 0xf4D9235269a96aaDaFc9aDAe454a0618eBE37949`

Run (same style as core/storage nodes — direct `ros2 run` + direct service calls):

```bash
ros2 run peaq_ros2_tether tether_node --ros-args \
  -p config.yaml_path:=/work/peaq_ros2_examples/config/peaq_robot.yaml &

# In another terminal:
# 1) Create wallet
ros2 service call /peaq_tether_node/wallet/create \
  peaq_ros2_interfaces/srv/TetherCreateWallet \
  "{label: 'robot_001', export_mnemonic: false}"

# 2) Check USDT balance
# You can pass either:
# - wallet_id (for new wallets, this is the wallet address), OR
# - address directly
ros2 service call /peaq_tether_node/usdt/balance \
  peaq_ros2_interfaces/srv/TetherGetUsdtBalance \
  "{wallet_id: '<WALLET_ADDRESS>', address: ''}"

ros2 service call /peaq_tether_node/usdt/balance \
  peaq_ros2_interfaces/srv/TetherGetUsdtBalance \
  "{wallet_id: '', address: '<EVM_ADDRESS>'}"

# 3) Transfer USDT
# Dry-run (quote) transfer (does not broadcast)
ros2 service call /peaq_tether_node/usdt/transfer \
  peaq_ros2_interfaces/srv/TetherTransferUsdt \
  "{wallet_id: '<WALLET_ADDRESS>', to_address: '<TO_EVM_ADDRESS>', amount: '0.1', dry_run: true}"

# Real transfer (broadcast)
ros2 service call /peaq_tether_node/usdt/transfer \
  peaq_ros2_interfaces/srv/TetherTransferUsdt \
  "{wallet_id: '<WALLET_ADDRESS>', to_address: '<TO_EVM_ADDRESS>', amount: '0.1', dry_run: false}"
```

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

1) Copy example config and fill in secrets:

```bash
cp peaq_ros2_examples/config/peaq_robot.example.yaml \
   peaq_ros2_examples/config/peaq_robot.yaml

# Edit peaq_ros2_examples/config/peaq_robot.yaml and set:
# - storage_bridge.storage.pinata.jwt = YOUR_PINATA_JWT
# - storage_bridge.storage.pinata.gateway_url = your Pinata gateway URL
```

2) Minimal config structure:

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
      jwt: "YOUR_PINATA_JWT"
      gateway_url: "https://your-gateway.mypinata.cloud/ipfs"
```

### Get Pinata Credentials

1. Sign up at [pinata.cloud](https://pinata.cloud)
2. Create API key with pinning permissions
3. Get your gateway URL from dashboard
4. Add to `peaq_ros2_examples/config/peaq_robot.yaml`

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
- **Community**: Join our [Discord](https://discord.gg/peaqnetwork)

## License

Apache 2.0 - See [LICENSE](LICENSE) file for details

## Acknowledgments

- Built on [ROS 2 Humble](https://docs.ros.org/en/humble/)
- Powered by [peaq Network](https://www.peaq.network/)
- IPFS integration via [Pinata](https://pinata.cloud/)

---

**Ready to get started?** Follow the [E2E_TEST.md](./E2E_TEST.md) guide for a complete walkthrough.


## Robot Profiles

### Plug-and-Play Integration

The SDK includes standardized robot profiles for popular platforms, enabling quick integration without learning each robot's specific API.

### Available Profiles

**Industrial Arms:**
- Universal Robots UR5
- KUKA LBR iiwa
- Franka Emika Panda

**Mobile Robots:**
- Boston Dynamics Spot

**Custom Robots:**
- Template for creating your own profiles

### Using a Profile

```yaml
# In peaq_robot.yaml
robot:
  profile: "profiles/industrial_arms/universal_robots_ur5.yaml"
```

Or programmatically:

```python
from peaq_ros2_core.profile_loader import load_profile

# Load profile
profile = load_profile("universal_robots_ur5")

# Access standardized topics
joint_states_topic = profile.topics['joint_states']
joint_trajectory_topic = profile.topics['joint_trajectory']

# Get safety limits
joint_limits = profile.safety['joint_limits']
for limit in joint_limits:
    print(f"{limit['name']}: max velocity = {limit['max_velocity']} rad/s")
```

### Creating Custom Profiles

1. Copy the template:
   ```bash
   cp profiles/custom/template.yaml profiles/custom/my_robot.yaml
   ```

2. Fill in your robot's specifications

3. Validate:
   ```bash
   python3 scripts/validate_profile.py profiles/custom/my_robot.yaml
   ```

4. Use in your application:
   ```yaml
   robot:
     profile: "profiles/custom/my_robot.yaml"
   ```

### Benefits

✅ **Standardized Interface** - Same code works across different robots  
✅ **Safety Built-in** - Profiles include safety limits and constraints  
✅ **Quick Onboarding** - Switch robots by changing one line  
✅ **Well-Documented** - Clear specifications for each robot  
✅ **Validated** - Schema validation ensures correctness  

### Profile Schema

Each profile is a YAML file with the following structure:

```yaml
# Profile Metadata
profile:
  name: "Robot Name"
  manufacturer: "Manufacturer Name"
  model: "Model Number"
  type: "industrial_arm|mobile_robot|humanoid|custom"
  version: "1.0.0"
  description: "Brief description"

# Robot Specifications
specifications:
  degrees_of_freedom: 6
  payload: 5.0  # kg
  reach: 850    # mm
  weight: 18.4  # kg
  
# Standard Topic Mappings (ROS 2)
topics:
  # Joint states (sensor_msgs/JointState)
  joint_states: "/joint_states"
  
  # Command interfaces
  joint_trajectory: "/joint_trajectory_controller/joint_trajectory"
  velocity_command: "/velocity_controller/command"
  position_command: "/position_controller/command"
  
  # Sensor data
  force_torque: "/force_torque_sensor"
  camera_rgb: "/camera/color/image_raw"
  camera_depth: "/camera/depth/image_raw"
  lidar: "/scan"
  imu: "/imu/data"
  
  # Robot state
  robot_status: "/robot_status"
  error_state: "/error_state"

# Safety Limits
safety:
  joint_limits:
    - name: "joint_1"
      min: -3.14159  # radians
      max: 3.14159
      max_velocity: 2.0  # rad/s
      max_acceleration: 5.0  # rad/s²
      max_torque: 150.0  # Nm
  
  workspace_limits:
    x: [-1.0, 1.0]  # meters
    y: [-1.0, 1.0]
    z: [0.0, 2.0]
  
  emergency_stop:
    topic: "/emergency_stop"
    type: "std_msgs/Bool"

# Control Configuration
control:
  # Available controllers
  controllers:
    - name: "joint_trajectory_controller"
      type: "position"
      default: true
    - name: "velocity_controller"
      type: "velocity"
    - name: "force_controller"
      type: "force"
  
  # Control loop rate
  update_rate: 100  # Hz
  
  # PID gains (if applicable)
  pid_gains:
    joint_1:
      p: 100.0
      i: 0.1
      d: 10.0

# Calibration
calibration:
  required: true
  procedure: "homing"  # homing|manual|automatic
  home_position: [0.0, -1.57, 1.57, 0.0, 1.57, 0.0]  # radians
  calibration_topic: "/calibration_status"

# Blockchain Integration
blockchain:
  # Data to store on-chain
  telemetry:
    - joint_states
    - force_torque
    - robot_status
  
  # Update frequency
  update_interval: 10.0  # seconds
  
  # DID metadata
  metadata:
    robot_type: "industrial_arm"
    capabilities: ["pick_and_place", "welding", "assembly"]

# Optional: Custom Parameters
custom:
  # Robot-specific parameters
  tool_offset: [0.0, 0.0, 0.15]  # meters
  tcp_frame: "tool0"
  base_frame: "base_link"
```

### Supported Robot Types

**Industrial Arms:**
- Universal Robots (UR3, UR5, UR10)
- KUKA (iiwa, KR series)
- ABB (IRB series)
- Franka Emika (Panda)

**Mobile Robots:**
- Boston Dynamics (Spot)
- Clearpath (Husky, Jackal)
- TurtleBot series

**Humanoids:**
- Unitree (G1, H1)
- Boston Dynamics (Atlas)
- PAL Robotics (TALOS)

