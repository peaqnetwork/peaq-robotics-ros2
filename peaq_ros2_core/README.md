# peaq ROS 2 Core

Core ROS 2 nodes for peaq blockchain integration. This package provides the main blockchain service interfaces and event streaming functionality that bridges ROS 2 applications with the peaq blockchain through the peaq-robot SDK.

## 🚀 Features

- **Blockchain Service Nodes**: Lifecycle-managed ROS 2 nodes for blockchain operations
- **Event Streaming**: Real-time blockchain event processing and publishing
- **Transaction Monitoring**: Automatic transaction status tracking and publishing
- **Structured Logging**: Human-readable logs with optional JSON format
- **Configuration Management**: Flexible parameter-based configuration
- **Security-First**: Environment-based keystore password management

## 📦 Package Contents

### Core Components

#### CoreNode (`core_node.py`)
Main lifecycle-managed node providing blockchain services:
- Identity management (create/read DID)
- Blockchain storage (add/read data)
- Access control (roles and permissions)
- Transaction status publishing

#### EventsNode (`events_node.py`)
Event streaming node for blockchain events:
- Blockchain event subscription and processing
- Custom event publishing capabilities
- Transaction status forwarding

#### Configuration (`config.py`)
Configuration management with validation:
- Environment variable support
- ROS 2 parameter integration
- Network and keystore configuration

#### Logging (`logging.py`)
Structured logging with multiple formats:
- Human-readable format with emojis
- JSON format for structured logging
- Specialized logging functions for different operations

## 🔧 Installation

```bash
cd /path/to/Robotics-sdk/packages/ros2
colcon build --packages-select peaq_ros2_core
```

## ⚙️ Configuration

### Environment Variables

```bash
# Network configuration
export PEAQ_ROBOT_NETWORK=agung

# Confirmation mode
export PEAQ_ROBOT_CONFIRMATION_MODE=FAST

# Keystore
export PEAQ_ROBOT_KEYSTORE=~/.peaq_robot/wallet.json
export PEAQ_ROBOT_KEY_PASSWORD=mypassword

# Events
export PEAQ_ROBOT_EVENTS_ENABLED=true

# Logging
export PEAQ_ROBOT_LOG_LEVEL=INFO
export PEAQ_ROBOT_LOG_FORMAT=human
```

### ROS 2 Parameters

```yaml
# peaq_ros2_params.yaml
network: "agung"
default_confirmation_mode: "FAST"
keystore:
  path: "~/.peaq_robot/wallet.json"
  password_env: "PEAQ_ROBOT_KEY_PASSWORD"
events:
  enabled: true
log_level: "INFO"
log_format: "human"
```

## 🚀 Usage

### Launch Core Services

```bash
# Launch core blockchain services
ros2 launch peaq_ros2_core core.launch.py

# With custom parameters
ros2 launch peaq_ros2_core core.launch.py \
  network:=peaq \
  confirmation_mode:=FINAL \
  log_level:=DEBUG
```

### Programmatic Usage

```python
#!/usr/bin/env python3
import rclpy
from rclpy.lifecycle import LifecycleNode, LifecycleState, TransitionCallbackReturn
from peaq_ros2_core import PeaqRosConfig, load_config_from_params, setup_logging

class MyNode(LifecycleNode):
    def __init__(self):
        super().__init__('my_node')

        # Load configuration
        params = {p.name: p.value for p in self._parameters}
        self.config = load_config_from_params(params)
        self.logger = setup_logging(self.config)

        self.logger.info('My node configured successfully')

    def on_configure(self, state: LifecycleState) -> TransitionCallbackReturn:
        self.logger.info('Configuring my node...')
        return TransitionCallbackReturn.SUCCESS
```

## 📡 ROS 2 Topics

### Published Topics

- `peaq/tx_status` (peaq_ros2_interfaces/msg/TxStatus): Transaction status updates
- `peaq/events` (peaq_ros2_interfaces/msg/Event): Blockchain events

### Services

All services are provided under the `~/` namespace:

- `~/identity/create` (peaq_ros2_interfaces/srv/IdentityCreate)
- `~/identity/read` (peaq_ros2_interfaces/srv/IdentityRead)
- `~/storage/add` (peaq_ros2_interfaces/srv/StoreAddData)
- `~/storage/read` (peaq_ros2_interfaces/srv/StoreReadData)
- `~/access/create_role` (peaq_ros2_interfaces/srv/AccessCreateRole)
- `~/access/create_permission` (peaq_ros2_interfaces/srv/AccessCreatePermission)
- `~/access/assign_permission` (peaq_ros2_interfaces/srv/AccessAssignPermToRole)
- `~/access/grant_role` (peaq_ros2_interfaces/srv/AccessGrantRole)

## 📊 Logging

### Human-Readable Format
```
2024-01-01 12:00:00.123 📋 [INFO] Transaction PENDING | Hash: abc12345...
2024-01-01 12:00:01.456 ✅ [INFO] Identity created | Name: my_robot | Tx: abc12345...
```

### JSON Format
```json
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

## 🔒 Security Features

- **Keystore Password Protection**: Password sourced from environment variables only
- **No Secrets in Config**: All sensitive data handled through environment variables
- **Secure Defaults**: Sensible security defaults for all configurations

## 🧪 Testing

### Unit Tests

```bash
# Run core package tests
colcon test --packages-select peaq_ros2_core

# Run specific test file
colcon test --packages-select peaq_ros2_core --pytest-args -v test/test_config.py
```

### Integration Tests

```bash
# Test with mocked blockchain SDK
colcon test --packages-select peaq_ros2_core --event-handlers console_direct+
```

## 🔗 Dependencies

- ROS 2 (Humble or later)
- rclpy
- lifecycle
- peaq-robot (Python SDK)
- peaq_ros2_interfaces

## 📋 Node Lifecycle

The core nodes follow ROS 2 lifecycle management:

1. **Unconfigured**: Initial state
2. **Inactive**: Configured but not active
3. **Active**: Running and processing requests
4. **Finalized**: Shutting down

### Lifecycle Transitions

```bash
# Configure node
ros2 lifecycle set /peaq_core_node configure

# Activate node
ros2 lifecycle set /peaq_core_node activate

# Deactivate node
ros2 lifecycle set /peaq_core_node deactivate

# Shutdown node
ros2 lifecycle set /peaq_core_node shutdown
```

## 📖 Examples

See the [peaq_ros2_examples](../peaq_ros2_examples/) package for complete usage examples.

## 📄 License

Apache License 2.0
