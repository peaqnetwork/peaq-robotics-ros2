#!/usr/bin/env bash
set -euo pipefail

# Source ROS 2 and workspace overlays
if [ -f /opt/ros/humble/setup.bash ]; then
  set +u
  source /opt/ros/humble/setup.bash
  set -u
fi

cd /work
if [ -f install/setup.bash ]; then
  set +u
  . install/setup.bash
  set -u
fi

# Ensure dependencies from PyPI (use official SDK)
pip3 install -q --upgrade pynacl requests peaq-robot-sdk >/dev/null 2>&1 || true

# Build the workspace to pick up latest edits
colcon build --merge-install >/dev/null 2>&1 || true

# Re-source overlays after build
if [ -f install/setup.bash ]; then
  set +u
  . install/setup.bash
  set -u
fi

# Wait for IPFS daemon container to be ready (ipfsdaemon on peaqnet)
for i in $(seq 1 30); do
  if curl -sS http://ipfsdaemon:5001/api/v0/version >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

# Start CoreNode (autostart services/publishers)
pkill -f peaq_ros2_core.core_node >/dev/null 2>&1 || true
env PEAQ_ROS2_AUTOSTART=true PEAQ_ROBOT_NETWORK="wss://peaq-agung.api.onfinality.io/ws" \
  nohup ros2 run peaq_ros2_core core_node >/tmp/core.log 2>&1 &
sleep 3

# Generate signing key and start StorageBridge pointing to ipfsdaemon
SK=$(python3 peaq_ros2_examples/scripts/gen_sk.py)
pkill -f peaq_ros2_core.storage_bridge_node >/dev/null 2>&1 || true
nohup ros2 run peaq_ros2_core storage_bridge_node \
  --ros-args \
  -p signature.private_key_hex:=$SK \
  -p ipfs.api_url:=http://ipfsdaemon:5001 \
  -p ipfs.gateway_url:=http://ipfsdaemon:8080/ipfs \
  -p pinning.provider:=none \
  -p pinning.pin:=false \
  -p robot.id:=humanoid_001 \
  -p robot.require_did:=false \
  -p core_node_name:=peaq_core_node \
  >/tmp/bridge.log 2>&1 &
sleep 3

# Run e2e ingest and wait script
python3 peaq_ros2_examples/scripts/ros_e2e_ingest_and_wait.py > /tmp/e2e.out 2>&1 || true

echo '--- E2E.OUT ---'
tail -n 200 /tmp/e2e.out || true
echo '--- BRIDGE.LOG ---'
tail -n 200 /tmp/bridge.log || true
echo '--- CORE.LOG ---'
tail -n 200 /tmp/core.log || true


