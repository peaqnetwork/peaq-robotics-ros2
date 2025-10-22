#!/usr/bin/env bash
set -euo pipefail

# Source ROS 2 and workspace overlays safely
if [ -f /opt/ros/humble/setup.bash ]; then
  set +u
  source /opt/ros/humble/setup.bash
  set -u
fi
if [ -f /work/install/setup.bash ]; then
  set +u
  source /work/install/setup.bash
  set -u
fi

# Rebuild to pick latest source with symlink-install
colcon build --merge-install --symlink-install >/dev/null 2>&1 || true
if [ -f /work/install/setup.bash ]; then
  set +u
  source /work/install/setup.bash
  set -u
fi

# Ensure PyPI SDK
pip3 install -q --upgrade peaq-robot-sdk >/dev/null 2>&1 || true

# Start CoreNode (autostart services/publishers)
pkill -f peaq_ros2_core.core_node >/dev/null 2>&1 || true
env PEAQ_ROS2_AUTOSTART=true PEAQ_ROBOT_NETWORK="wss://peaq-agung.api.onfinality.io/ws" \
  nohup ros2 run peaq_ros2_core core_node >/tmp/core_idacc.log 2>&1 &
sleep 3

# Wait for identity service
for i in $(seq 1 30); do
  if ros2 service list | grep -q "/peaq_core_node/identity/read"; then
    break
  fi
  sleep 2
done

# Run identity/access tester
python3 /work/packages/ros2/peaq_ros2_examples/scripts/test_identity_access.py > /tmp/idacc.out 2>&1 || true

echo '--- IDACC.OUT ---'
tail -n 200 /tmp/idacc.out || true
echo '--- CORE.IDACC.LOG ---'
tail -n 200 /tmp/core_idacc.log || true


