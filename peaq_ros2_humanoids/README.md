# peaq ROS 2 Humanoids

Humanoid bridge for peaq blockchain integration with robot motion control. This package provides the infrastructure to translate blockchain intents into robot actions through pluggable adapters for different humanoid robot platforms.

## 🤖 Features

- **Intent-Based Control**: Blockchain events translated to robot actions
- **Pluggable Adapters**: Support for multiple humanoid robot platforms
- **Unitree G1 Integration**: Complete adapter for Unitree G1 humanoid robot
- **Motion Control**: Locomotion, posture, and gesture execution
- **Emergency Safety**: Built-in emergency stop functionality
- **ROS Integration**: Standard ROS topics for robot control and feedback

## 📦 Package Contents

### Core Components

#### HumanoidBridgeNode (`humanoid_bridge_node.py`)
Main node that bridges blockchain events to robot control:
- Listens for blockchain events containing robot intents
- Validates and executes intents using appropriate adapters
- Provides emergency stop and safety features
- Publishes robot telemetry and state information

#### Intent System (`intents.py`)
Structured intent definitions with validation:
- **LocomotionIntent**: Robot movement commands (velocity, gait, duration)
- **PostureIntent**: Robot posture changes (stand, sit, kneel, crouch)
- **GestureIntent**: Robot gestures (wave, point, nod, bow, dance)
- **TaskIntent**: Complex behavior tasks (patrol, follow, greet)
- **EmergencyIntent**: Emergency stop and safety commands

#### Adapter Framework (`common.py`)
Abstract base classes for robot adapters:
- **HumanoidAdapter**: Base class all adapters must implement
- **AdapterFactory**: Factory pattern for adapter creation and management
- **Emergency Stop**: Built-in safety mechanisms

#### Unitree G1 Adapter (`adapters/unitree_g1_adapter.py`)
Complete implementation for Unitree G1 humanoid robot:
- ROS topic integration (`/cmd_vel`, `/joint_states`, etc.)
- Motion execution with velocity scaling and safety limits
- Posture and gesture implementations
- Battery and joint state monitoring

## 🔧 Installation

```bash
cd /path/to/Robotics-sdk/packages/ros2
colcon build --packages-select peaq_ros2_humanoids
```

## ⚙️ Configuration

### Environment Variables

```bash
# Humanoid adapter selection
export PEAQ_ROBOT_HUMANOID_ADAPTER=unitree_g1

# Adapter configuration (JSON)
export PEAQ_ROBOT_ADAPTER_CONFIG='{"max_linear_velocity": 1.0, "max_angular_velocity": 2.0}'
```

### ROS 2 Parameters

```yaml
# humanoid_bridge_params.yaml
humanoids:
  adapter: "unitree_g1"
  adapter_config:
    max_linear_velocity: 1.0
    max_angular_velocity: 2.0
    motion_timeout: 5.0
    joint_names: ["left_arm", "right_arm", "head"]
```

## 🚀 Usage

### Launch Humanoid Bridge

```bash
# Launch with Unitree G1 adapter
ros2 launch peaq_ros2_humanoids humanoid_bridge.launch.py \
  adapter:=unitree_g1 \
  adapter_config:='{"max_linear_velocity": 1.0, "max_angular_velocity": 2.0}'

# Launch in ROS-only mode (no blockchain)
ros2 launch peaq_ros2_humanoids humanoid_bridge.launch.py \
  ros_only_mode:=true
```

### Intent Examples

#### Locomotion Intent
```json
{
  "intent": {
    "intent_type": "locomotion",
    "motion_type": "move",
    "velocity_x": 0.5,
    "velocity_y": 0.0,
    "velocity_z": 0.0,
    "duration": 3.0,
    "gait_type": "walking"
  },
  "source": "operator",
  "destination": "robot_001"
}
```

#### Posture Intent
```json
{
  "intent": {
    "intent_type": "posture",
    "posture_type": "stand_straight",
    "transition_time": 2.0
  },
  "source": "blockchain",
  "priority": 3
}
```

#### Gesture Intent
```json
{
  "intent": {
    "intent_type": "gesture",
    "gesture_type": "wave",
    "speed": 1.5,
    "amplitude": 1.2,
    "repetitions": 3
  },
  "source": "operator",
  "priority": 2
}
```

### Emergency Control

```python
#!/usr/bin/env python3
import rclpy
from peaq_ros2_humanoids import HumanoidBridgeNode

rclpy.init()
node = HumanoidBridgeNode()

# Emergency stop
node.emergency_stop()

# Clear emergency (use with caution)
node.clear_emergency_stop()
```

## 📡 ROS 2 Integration

### Subscribed Topics

- `peaq/events` (peaq_ros2_interfaces/msg/Event): Blockchain events containing intents

### Published Topics

- `/cmd_vel` (geometry_msgs/msg/Twist): Robot velocity commands
- `/cmd_pose` (geometry_msgs/msg/Pose): Robot pose commands
- `/joint/*/command` (std_msgs/msg/Float64): Individual joint commands

### Subscribed Topics (Robot State)

- `/battery_state` (sensor_msgs/msg/BatteryState): Battery level monitoring
- `/joint_states` (sensor_msgs/msg/JointState): Joint position feedback

## 🔒 Safety Features

- **Emergency Stop**: Immediate halt of all robot motion
- **Velocity Limiting**: Configurable maximum velocities for safety
- **Timeout Protection**: Automatic motion stop after configurable duration
- **Intent Validation**: Type checking and range validation for all intents
- **Adapter Isolation**: Each adapter runs in isolated error boundaries

## 🎯 Intent Types

### Locomotion Intents

| Motion Type | Description | Parameters |
|-------------|-------------|------------|
| `move` | General movement | velocity_x, velocity_y, velocity_z, duration |
| `walk` | Walking gait | velocity_x, velocity_y, step_length, step_height |
| `run` | Running gait | velocity_x, velocity_y, higher speeds |
| `stop` | Halt all motion | none required |
| `turn` | In-place rotation | velocity_z only |
| `stand` | Stand in place | none required |
| `sit` | Sit down | transition_time |

### Posture Intents

| Posture Type | Description |
|--------------|-------------|
| `stand_straight` | Upright standing position |
| `stand_relaxed` | Relaxed standing position |
| `sit_chair` | Sitting on chair posture |
| `sit_floor` | Sitting on floor posture |
| `kneel` | Kneeling posture |
| `crouch` | Crouched posture |

### Gesture Intents

| Gesture Type | Description | Parameters |
|--------------|-------------|------------|
| `wave` | Hand waving gesture | speed, amplitude, repetitions |
| `point` | Pointing gesture | speed, amplitude, repetitions |
| `nod` | Head nodding | speed, amplitude, repetitions |
| `shake_head` | Head shaking | speed, amplitude, repetitions |
| `bow` | Bowing gesture | speed, amplitude, repetitions |
| `dance` | Dance movements | speed, amplitude, repetitions |

## 🛠️ Adding New Adapters

To add support for a new humanoid robot:

1. Create adapter class inheriting from `HumanoidAdapter`
2. Implement all abstract methods
3. Register with `AdapterFactory.register_adapter()`
4. Add configuration parameters

```python
from peaq_ros2_humanoids.common import HumanoidAdapter

class MyRobotAdapter(HumanoidAdapter):
    def initialize(self) -> bool:
        # Initialize robot connection
        return True

    def execute_locomotion_intent(self, intent):
        # Translate intent to robot commands
        return True

    # ... implement other abstract methods
```

## 🧪 Testing

### Unit Tests

```bash
# Run humanoid package tests
colcon test --packages-select peaq_ros2_humanoids

# Test specific adapter
colcon test --packages-select peaq_ros2_humanoids --pytest-args -k "test_unitree_g1"
```

### Integration Tests

```bash
# Test intent execution (requires robot connection)
ros2 run peaq_ros2_humanoids test_intent_execution
```

## 🔗 Dependencies

- ROS 2 (Humble or later)
- rclpy
- geometry_msgs
- sensor_msgs
- pydantic (for intent validation)
- peaq-robot (Python SDK)
- peaq_ros2_interfaces
- peaq_ros2_core

## 📋 Supported Robots

- **Unitree G1**: Complete implementation with ROS integration
- **Extensible**: Framework supports additional robots via adapters

## 📖 Examples

See the [peaq_ros2_examples](../peaq_ros2_examples/) package for complete usage examples and demo scripts.

## 📄 License

Apache License 2.0
