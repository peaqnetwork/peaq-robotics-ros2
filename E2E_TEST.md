# End-to-End Testing Guide (Real Machine Simulation)

This guide simulates a **real machine** where ROS2, IPFS, and all services run together in one environment.

## ⚠️ CRITICAL: Always Source the Workspace

**Before running ANY `ros2` command, you MUST source the workspace:**

```bash
source /opt/ros/humble/setup.bash
source install/setup.bash
```

**If you get "The passed service type is invalid" error, you forgot to source!**

See [TROUBLESHOOTING.md](./TROUBLESHOOTING.md) for more details.

## Test Flow Overview

1. Build Docker image (with IPFS included)
2. Start container (single container, like a real machine)
3. Start IPFS daemon inside container
4. Build ROS2 packages
5. Start core node with auto-generated wallet
6. Create DID and verify
7. Start storage bridge
8. Send sensor data
9. Verify data on blockchain and Pinata gateway

---

## Optional: Tether WDK (peaq EVM USDT) Integration Test

This is a **separate** integration demo that uses Tether WDK’s EVM wallet module to create an EVM wallet and interact with the existing USDT ERC-20 contract on peaq EVM.

### Prerequisites

- Node.js 18+
- `npm install` executed once:

```bash
cd /work/peaq_ros2_tether/js
npm install
```

### Configure

Copy and edit unified config:

```bash
cp /work/peaq_ros2_examples/config/peaq_robot.example.yaml \
   /work/peaq_ros2_examples/config/peaq_robot.yaml
```

Then set in `peaq_robot.yaml`:
- `tether.enabled: true`
- `tether.evm.rpc_url: https://quicknode1.peaq.xyz`
- `tether.usdt.contract: 0xf4D9235269a96aaDaFc9aDAe454a0618eBE37949`

### Run

```bash
source /opt/ros/humble/setup.bash
source install/setup.bash

nohup ros2 run peaq_ros2_tether tether_node --ros-args \
  -p config.yaml_path:=/work/peaq_ros2_examples/config/peaq_robot.yaml \
  > /tmp/tether_node.log 2>&1 &

sleep 2
tail -n 50 /tmp/tether_node.log
```

In another terminal:

```bash
source /opt/ros/humble/setup.bash
source install/setup.bash

# 1) Create wallet
ros2 service call /peaq_tether_node/wallet/create \
  peaq_ros2_interfaces/srv/TetherCreateWallet \
  "{label: 'robot_001', export_mnemonic: false}"

# 2) Check USDT balance (by address)
ros2 service call /peaq_tether_node/usdt/balance \
  peaq_ros2_interfaces/srv/TetherGetUsdtBalance \
  "{wallet_id: '', address: '0x...'}"

# 3) Dry-run USDT transfer (quote)
ros2 service call /peaq_tether_node/usdt/transfer \
  peaq_ros2_interfaces/srv/TetherTransferUsdt \
  "{wallet_id: '...', to_address: '0x...', amount: '0.1', dry_run: true}"

# Optional: run the demo node (separate ROS node that calls the same services)
ros2 run peaq_ros2_examples tether_demo
```

### Notes

- Wallet mnemonics are stored locally in a shared registry file (default `~/.peaq_robot/tether_wallets.json`).
- Mnemonic export is **disabled by default** and should remain disabled in production.
- If the newly created wallet has **0 USDT**, transfer dry-runs may revert with an expected error like `ERC20: transfer amount exceeds balance`.

---

## Prerequisites

- Docker installed and running
- Internet connection (for blockchain and Pinata)
- Git (to clone repository)

---

## Step 1: Clone Repository

```bash
git clone https://github.com/peaqnetwork/peaq-robotics-ros2.git
cd peaq-robotics-ros2
```

---

## Step 2: Clean Up Previous Containers (if any)

**Option A: Use cleanup script (recommended)**

```bash
./scripts/cleanup.sh
```

**Option B: Manual cleanup**

```bash
# Remove any existing containers and images
docker stop peaq-ros2-test ipfsdaemon ipfs-daemon 2>/dev/null
docker rm peaq-ros2-test ipfsdaemon ipfs-daemon 2>/dev/null
docker rmi peaq-ros2:latest 2>/dev/null

# Verify cleanup
docker ps -a | grep peaq
```

**Expected Output:**
```
✅ Cleanup complete! No peaq or IPFS containers found.
Ready for fresh build!
```

---

## Step 3: Build Docker Image

The Docker image includes:
- ROS2 Humble
- IPFS (Kubo)
- All Python dependencies
- Everything needed for a real machine

```bash
# Clean build
docker build -t peaq-ros2:latest .
```

**Expected Output:**
```
Successfully installed ipfs, peaq-robot-sdk-0.0.2, pydantic-2.12.3 ...
Successfully tagged peaq-ros2:latest
```

**Build time:** ~2-3 minutes (includes IPFS installation)

---

## Step 4: Start Container

```bash
# Start container (single container, like a real machine)
docker run -it --name peaq-ros2-test \
  -v $(pwd):/work \
  -w /work \
  -p 5001:5001 \
  -p 8080:8080 \
  peaq-ros2:latest
```

**If you get "container name already in use" error:**
```bash
# Remove the existing container
docker rm -f peaq-ros2-test

# Then run the docker run command again
```

You're now inside the container - this simulates being logged into a real machine.

**Alternative: Run container in background (detached mode)**
```bash
# Start container in background
docker run -d --name peaq-ros2-test \
  -v $(pwd):/work \
  -w /work \
  -p 5001:5001 \
  -p 8080:8080 \
  peaq-ros2:latest \
  tail -f /dev/null

# Then bash into it
docker exec -it peaq-ros2-test bash
```

**Tip: Open multiple terminals**
```bash
# Terminal 1: Main work
docker exec -it peaq-ros2-test bash

# Terminal 2: Monitor logs
docker exec -it peaq-ros2-test bash
tail -f /tmp/core_node.log

# Terminal 3: Monitor storage bridge
docker exec -it peaq-ros2-test bash
tail -f /tmp/storage_bridge.log
```

---

## Step 5: Start IPFS Daemon

Inside the container:

```bash
# Start IPFS daemon in background
ipfs daemon > /tmp/ipfs.log 2>&1 &

# Wait for IPFS to start
sleep 3

# Verify IPFS is running
ipfs version
```

**Expected Output:**
```
ipfs version 0.38.1
```

---

## Step 6: Build ROS2 Packages

Still inside the container:

```bash
# Source ROS2
source /opt/ros/humble/setup.bash

# Build all packages
colcon build

# Source workspace
source install/setup.bash
```

**Expected Output:**
```
Summary: 4 packages finished [~7s]
  ✅ peaq_ros2_interfaces
  ✅ peaq_ros2_core
  ✅ peaq_ros2_humanoids
  ✅ peaq_ros2_examples
```

---

## Step 7: Configure peaq_robot.yaml

**Option A: Edit with nano (recommended)**

```bash
nano peaq_ros2_examples/config/peaq_robot.yaml
```

**Option B: Edit with vim**

```bash
vim peaq_ros2_examples/config/peaq_robot.yaml
```

**Option C: Edit from host machine**

Exit container (Ctrl+D) and edit on your host machine:
```bash
nano peaq_ros2_examples/config/peaq_robot.yaml
# Then re-enter container: docker exec -it peaq-ros2-test bash
```

Ensure these settings:

```yaml
network: agung

wallet:
  path: /work/peaq_wallet.json
  auto_generate: true

storage_bridge:
  robot:
    require_did: true
  storage:
    mode: pinata
    local_ipfs:
      api_url: http://127.0.0.1:5001  # IPFS running locally
    pinata:
      jwt: "YOUR_PINATA_JWT_TOKEN"
      gateway_url: "YOUR_PINATA_GATEWAY_URL"
```

Save and exit (Ctrl+X, Y, Enter)

---

## Step 8: Start Core Node

```bash
# Start core node in background
nohup bash -c 'source /opt/ros/humble/setup.bash && source install/setup.bash && ros2 run peaq_ros2_core core_node --ros-args -p config.yaml_path:=/work/peaq_ros2_examples/config/peaq_robot.yaml' > /tmp/core_node.log 2>&1 &

# Wait for initialization
sleep 5

# Check logs to verify startup
tail -20 /tmp/core_node.log

# Configure and activate
source /opt/ros/humble/setup.bash
source install/setup.bash
ros2 lifecycle set /peaq_core_node configure
ros2 lifecycle set /peaq_core_node activate

# Check logs after activation
tail -10 /tmp/core_node.log
```

**Expected in logs:**
```
🔑 Core node wallet address: 5G269m9Q...
🔗 Connected to agung network
✅ Core node configured successfully
🚀 Core node activated
```

---

## Step 9: Verify Core Node

```bash
# Check node is running
ros2 node list

# List services
ros2 service list | grep peaq_core_node
```

**Expected Output:**
```
/peaq_core_node

/peaq_core_node/identity/create
/peaq_core_node/identity/read
/peaq_core_node/storage/add
/peaq_core_node/storage/read
...
```

---

## Step 10: Get Wallet Address

```bash
# Use the info service to get node info (includes wallet address)
ros2 service call /peaq_core_node/info \
  peaq_ros2_interfaces/srv/GetNodeInfo
```

**Expected Output:**
```
response:
peaq_ros2_interfaces.srv.GetNodeInfo_Response(result='{
  "node_name": "peaq_core_node",
  "network": "agung",
  "wallet_address": "5G269m9QkYuxED5C8wuMq75o4DreyMPqZKhy36mgwK4uTPUX",
  "did": "did:peaq:5G269m9QkYuxED5C8wuMq75o4DreyMPqZKhy36mgwK4uTPUX",
  ...
}')
```

Copy the `wallet_address` field from the JSON response.

---

## Step 11: Fund Wallet

1. Visit: https://faucet.peaq.network/
2. Paste your wallet address
3. Request tokens
4. Wait ~30 seconds

---

## Step 12: Create DID

```bash
ros2 service call /peaq_core_node/identity/create \
  peaq_ros2_interfaces/srv/IdentityCreate \
  '{metadata_json: "{\\\"type\\\": \\\"robot\\\"}"}'

# Check logs for result
tail -10 /tmp/core_node.log
```

**Expected Output (if wallet is funded):**
```
response:
peaq_ros2_interfaces.srv.IdentityCreate_Response(tx_hash='0x1234...')
```

**Logs should show:**
```
Creating identity: did:peaq:5G269m9Q...
✅ Identity created successfully
```

**If wallet needs funds, you'll see:**
```
tx_hash: ''
```

**Logs will show:**
```
❌ Failed to create identity: Transaction error: Inability to pay some fees
```

The DID is auto-derived as: `did:peaq:<your_wallet_address>`

---

## Step 13: Verify DID

```bash
# IdentityRead takes no parameters (uses configured identity)
ros2 service call /peaq_core_node/identity/read \
  peaq_ros2_interfaces/srv/IdentityRead

# Check logs
tail -10 /tmp/core_node.log
```

**Expected Output:**
```
response:
peaq_ros2_interfaces.srv.IdentityRead_Response(doc_json='{"did": "did:peaq:...", "metadata": {...}}')
```

**Logs should show:**
```
Reading identity document
✅ Identity read successfully
```

---

## Step 14: Start Storage Bridge

```bash
# Start storage bridge in background
nohup bash -c 'source /opt/ros/humble/setup.bash && source install/setup.bash && ros2 run peaq_ros2_core storage_bridge_node --ros-args -p config.yaml_path:=/work/peaq_ros2_examples/config/peaq_robot.yaml' > /tmp/storage_bridge.log 2>&1 &

# Wait for initialization
sleep 5

# Check logs
tail -20 /tmp/storage_bridge.log

# Configure and activate
ros2 lifecycle set /peaq_storage_bridge_node configure
ros2 lifecycle set /peaq_storage_bridge_node activate

# Check logs after activation
tail -10 /tmp/storage_bridge.log
```

**Expected in logs:**
```
Storage bridge node starting...
✅ Storage bridge configured
✅ Storage bridge activated
Subscribed to /peaq/storage/ingest
```

---

## Step 15: Send Sensor Data

```bash
ros2 topic pub --once /peaq/storage/ingest \
  peaq_ros2_interfaces/msg/StorageIngest \
  '{key: "temperature_sensor", content: "temperature:25.5,humidity:60.2", is_file: false}'

# Check storage bridge logs
tail -20 /tmp/storage_bridge.log

# Check core node logs (for blockchain transaction)
tail -20 /tmp/core_node.log
```

**Expected in storage bridge logs:**
```
Received storage ingest request: temperature_sensor
Uploading to IPFS...
✅ Uploaded to IPFS: QmXXX...
Storing on blockchain...
✅ Stored on blockchain
```

---

## Step 16: Monitor Results

```bash
# Listen for result on topic
ros2 topic echo /peaq/storage/result --once
```

**Expected Output:**
```
success: true
cid: 'Qme9cBe76Se3UXy4peVUVuG1KDnwvQXavsGa659MdLLAxV'
ipfs_url: 'https://salmon-managerial-caribou-735.mypinata.cloud/ipfs/Qme9cBe76Se3UXy4peVUVuG1KDnwvQXavsGa659MdLLAxV'
```

**Alternative: Check logs directly**
```bash
# Storage bridge logs show the full flow
tail -30 /tmp/storage_bridge.log
```

---

## Step 17: Verify on Blockchain

```bash
ros2 service call /peaq_core_node/storage/read \
  peaq_ros2_interfaces/srv/StoreReadData \
  '{key: "temperature_sensor"}'

# Check logs
tail -10 /tmp/core_node.log
```

**Expected Output:**
```
response:
peaq_ros2_interfaces.srv.StoreReadData_Response(value_json='{"cid": "QmXXX...", ...}')
```

**Logs should show:**
```
Reading storage data: temperature_sensor
✅ Storage data read successfully
```

---

## Step 18: Verify in Browser

1. Copy the `ipfs_url` from Step 15
2. Open browser
3. Paste URL
4. You should see: `temperature:25.5,humidity:60.2`

---

## Monitoring & Debugging Tips

### Real-time Log Monitoring

**Option 1: Follow logs in real-time**
```bash
# Core node logs
tail -f /tmp/core_node.log

# Storage bridge logs
tail -f /tmp/storage_bridge.log

# IPFS logs
tail -f /tmp/ipfs.log
```

**Option 2: Open multiple terminal sessions**
```bash
# From host machine, open new terminal and exec into container
docker exec -it peaq-ros2-test bash

# Then tail logs in each terminal
```

### Check All Running Processes
```bash
ps aux | grep ros2
ps aux | grep ipfs
```

### Check ROS2 Node Status
```bash
# List all nodes
ros2 node list

# Check node info
ros2 node info /peaq_core_node

# List all topics
ros2 topic list

# List all services
ros2 service list | grep peaq
```

### View Full Logs
```bash
# View all core node logs
cat /tmp/core_node.log

# View all storage bridge logs
cat /tmp/storage_bridge.log

# Search logs for errors
grep -i error /tmp/core_node.log
grep -i error /tmp/storage_bridge.log
```

---

## Cleanup

```bash
# Stop all processes
pkill -f ros2
pkill -f ipfs

# Exit container
exit

# Remove container
docker stop peaq-ros2-test
docker rm peaq-ros2-test
```

---

## Why This Approach?

✅ **Simulates Real Machine:**
- Everything runs in one environment
- IPFS and ROS2 together
- No separate containers

✅ **Production-Ready:**
- Same setup you'd use on actual robot
- All services in one place
- Easy to deploy

✅ **Easier to Understand:**
- One container = one machine
- Clear service dependencies
- Simpler networking

---

## Success Criteria

- [x] Docker image built with IPFS included
- [x] Single container running (like real machine)
- [x] IPFS daemon running inside container
- [x] All ROS2 packages built
- [x] Core node running and activated
- [x] Wallet auto-generated
- [x] DID created and verified
- [x] Storage bridge running
- [x] Data stored on blockchain
- [x] Data visible via Pinata gateway

**This is how it would work on a real robot!** 🤖
