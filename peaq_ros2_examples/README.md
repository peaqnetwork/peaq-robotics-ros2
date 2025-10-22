# peaq ROS 2 Examples

Example launch files and demo scripts for the peaq ROS 2 SDK. This package provides comprehensive demonstrations of how to use the blockchain integration features for robot control and data management.

## 📦 Package Contents

### Launch Files

#### demo_core.launch.py
Demonstrates core blockchain functionality:
- Launches core and events nodes together
- Configurable network and logging settings
- Transaction status monitoring

#### demo_humanoid_unitree.launch.py
Complete humanoid robot integration demo:
- Launches core blockchain services
- Starts humanoid bridge with Unitree G1 adapter
- Full intent-to-motion pipeline

### Demo Scripts

#### create_identity.py
Interactive script for creating robot DIDs:
- Creates blockchain identities via ROS 2 services
- Monitors transaction status in real-time
- Demonstrates proper error handling

#### emit_intent.py
Interactive intent emitter for testing:
- Send locomotion, posture, and gesture intents
- Real-time intent creation and publishing
- Blockchain event integration

#### send_store_add_data.py
Data storage demonstration:
- Store robot telemetry on blockchain
- Read stored data back
- Transaction status monitoring

## 🚀 Quick Start

### 1. Core Blockchain Demo

```bash
# Launch core services
ros2 launch peaq_ros2_examples demo_core.launch.py

# In another terminal, create an identity
ros2 run peaq_ros2_examples create_identity

# In another terminal, store telemetry data
ros2 run peaq_ros2_examples send_store_add_data
```

### 2. Humanoid Robot Demo

```bash
# Launch complete humanoid integration (requires Unitree G1 robot)
ros2 launch peaq_ros2_examples demo_humanoid_unitree.launch.py \
  network:=agung \
  adapter:=unitree_g1

# In another terminal, emit robot intents
ros2 run peaq_ros2_examples emit_intent
```

## 📖 Usage Examples

### Creating Robot Identities

```bash
#!/bin/bash
# Set environment variables
export PEAQ_ROBOT_NETWORK=agung
export PEAQ_ROBOT_KEYSTORE=~/.peaq_robot/wallet.json

# Launch core services
ros2 launch peaq_ros2_examples demo_core.launch.py &

# Wait for services to be ready
sleep 3

# Create identity
ros2 run peaq_ros2_examples create_identity
```

### Emitting Robot Intents

```bash
#!/bin/bash
# Launch humanoid bridge (requires robot)
ros2 launch peaq_ros2_examples demo_humanoid_unitree.launch.py &

# Wait for bridge to be ready
sleep 5

# Start interactive intent emitter
ros2 run peaq_ros2_examples emit_intent
```

### Storing Robot Telemetry

```python
#!/usr/bin/env python3
import json
from peaq_ros2_examples.send_store_add_data import StorageClient

# Example telemetry data
telemetry = {
    "robot_id": "unitree_g1_001",
    "battery_level": 85.5,
    "position": {"x": 1.2, "y": 0.8, "z": 0.0},
    "status": "operational"
}

# Store on blockchain
client = StorageClient()
success = client.store_data("TELEMETRY_ROBOT_001", telemetry, "FAST")
```

## 🔧 Configuration

### Environment Setup

```bash
# Core blockchain configuration
export PEAQ_ROBOT_NETWORK=agung
export PEAQ_ROBOT_CONFIRMATION_MODE=FAST
export PEAQ_ROBOT_KEYSTORE=~/.peaq_robot/wallet.json
export PEAQ_ROBOT_KEY_PASSWORD=your_password_here

# Humanoid configuration
export PEAQ_ROBOT_HUMANOID_ADAPTER=unitree_g1
export PEAQ_ROBOT_ADAPTER_CONFIG='{"max_linear_velocity": 1.0, "max_angular_velocity": 2.0}'

# Logging
export PEAQ_ROBOT_LOG_LEVEL=INFO
export PEAQ_ROBOT_LOG_FORMAT=human
```

### Custom Launch Parameters

```bash
# Custom network and confirmation mode
ros2 launch peaq_ros2_examples demo_core.launch.py \
  network:=peaq \
  confirmation_mode:=FINAL \
  log_level:=DEBUG

# Custom humanoid adapter configuration
ros2 launch peaq_ros2_examples demo_humanoid_unitree.launch.py \
  adapter:=unitree_g1 \
  adapter_config:='{"max_linear_velocity": 0.5, "motion_timeout": 10.0}'
```

## 🎯 Demo Scenarios

### Scenario 1: Identity Management

1. **Launch core services**
   ```bash
   ros2 launch peaq_ros2_examples demo_core.launch.py
   ```

2. **Create robot identity**
   ```bash
   ros2 run peaq_ros2_examples create_identity
   ```

3. **Expected output:**
   ```
   🚀 Identity creation initiated: abc12345...
   📋 Transaction pending: abc12345...
   📦 Transaction in block: abc12345...
   ✅ Transaction finalized: abc12345...
   ✅ Identity created successfully
   ```

### Scenario 2: Data Storage

1. **Launch core services**
   ```bash
   ros2 launch peaq_ros2_examples demo_core.launch.py
   ```

2. **Store telemetry data**
   ```bash
   ros2 run peaq_ros2_examples send_store_add_data
   ```

3. **Expected output:**
   ```
   💾 Storing telemetry data...
   🚀 Storage transaction initiated: def67890...
   📋 Storage transaction pending: def67890...
   ✅ Storage transaction finalized: def67890...
   ✅ Telemetry data stored successfully
   📖 Retrieved data:
   {
     "robot_id": "unitree_g1_001",
     "battery_level": 85.5,
     "position": {"x": 1.2, "y": 0.8, "z": 0.0}
   }
   ```

### Scenario 3: Robot Control

1. **Launch humanoid integration** (requires Unitree G1 robot)
   ```bash
   ros2 launch peaq_ros2_examples demo_humanoid_unitree.launch.py
   ```

2. **Emit locomotion intent**
   ```bash
   ros2 run peaq_ros2_examples emit_intent
   # Choose option 1 (Locomotion) -> move -> vx: 0.5
   ```

3. **Expected output:**
   ```
   🤖 peaq ROS 2 Intent Emitter
   ========================================
   Available intents:
   1. Locomotion (move, walk, run, stop, turn, stand, sit)
   2. Posture (stand_straight, stand_relaxed, sit_chair, kneel, crouch)
   3. Gesture (wave, point, nod, shake_head, bow, dance)

   Choose intent type:
   1. Locomotion
   2. Posture
   3. Gesture
   q. Quit

   Enter choice: 1

   Locomotion Intent:
   Motion type (move/walk/run/stop/turn/stand/sit): move
   Velocity X (m/s, -2.0 to 2.0): 0.5
   Velocity Y (m/s, -2.0 to 2.0): 0
   Angular velocity Z (rad/s, -3.0 to 3.0): 0

   ✅ Intent emitted successfully!
   ```

## 🔍 Monitoring

### Real-time Status

All demo scripts provide real-time feedback:

- **Transaction Status**: PENDING → IN_BLOCK → FINALIZED
- **Intent Execution**: Intent type, source, and execution status
- **Error Handling**: Clear error messages and failure reasons

### Logging Output

```bash
# Human-readable logs
2024-01-01 12:00:00.123 📋 [INFO] Transaction PENDING | Hash: abc12345...
2024-01-01 12:00:01.456 ✅ [INFO] Intent executed: locomotion | Motion: move

# JSON logs (set PEAQ_ROBOT_LOG_FORMAT=json)
{
  "timestamp": "2024-01-01T12:00:00.123Z",
  "level": "INFO",
  "logger": "peaq_ros2_core.core_node",
  "message": "Transaction PENDING | Hash: abc12345...",
  "robot_data": {
    "tx_hash": "0xabc123...",
    "phase": "PENDING"
  }
}
```

## 🛠️ Customization

### Creating Custom Demo Scripts

```python
#!/usr/bin/env python3
import rclpy
import json
from peaq_ros2_humanoids.intents import IntentMessage, LocomotionIntent, MotionType

def create_custom_intent():
    # Create custom locomotion intent
    intent = LocomotionIntent(
        intent_type="locomotion",
        motion_type=MotionType.MOVE,
        velocity_x=1.0,
        velocity_y=0.0,
        velocity_z=0.0,
        duration=5.0
    )

    intent_message = IntentMessage(
        intent=intent,
        source="custom_script",
        destination="my_robot"
    )

    return intent_message

# Usage in your script
rclpy.init()
node = rclpy.create_node('custom_demo')

# Publish intent to blockchain events
events_pub = node.create_publisher(Event, 'peaq/events', 10)
intent_msg = create_custom_intent()
# Serialize and publish...
```

## 🔗 Dependencies

- ROS 2 (Humble or later)
- peaq_ros2_interfaces
- peaq_ros2_core
- peaq_ros2_humanoids

## 📋 Requirements

- Network connection to peaq blockchain (Agung testnet by default)
- Valid keystore file with wallet credentials
- For humanoid demos: Connected Unitree G1 robot with ROS integration

## 🧪 Testing the Examples

```bash
# Test all example scripts (requires full setup)
./test_examples.sh

# Test individual script
ros2 run peaq_ros2_examples create_identity --help
```

## 📄 License

Apache License 2.0
