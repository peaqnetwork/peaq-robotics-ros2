# peaq ROS 2 Interfaces

ROS 2 interface definitions for peaq blockchain integration. This package contains the message and service definitions that enable communication between ROS 2 nodes and the peaq blockchain through the peaq-robot SDK.

## 📋 Package Contents

### Message Types

#### TxStatus.msg
Transaction status message for monitoring blockchain transaction progress:
```rosmsg
string phase      # PENDING, IN_BLOCK, FINALIZED, FAILED, DROPPED
string tx_hash    # Transaction hash (optional)
uint64 block      # Block number (0 if not in block yet)
string error      # Error message if failed
```

#### Event.msg
Generic event message for blockchain event streaming:
```rosmsg
string source      # Event source (e.g., 'blockchain', 'robot')
string type        # Event type (e.g., 'intent_received', 'telemetry_update')
string payload_json # JSON payload containing event data
```

### Service Definitions

#### Identity Services

**IdentityCreate.srv**
Create a new DID identity on-chain:
```rossrv
string name
string metadata_json
---
string tx_hash
```

**IdentityRead.srv**
Read DID document from chain:
```rossrv
---
string doc_json
```

#### Storage Services

**StoreAddData.srv**
Add data to blockchain storage:
```rossrv
string key
string value_json
string mode  # FAST or FINAL
---
string result
```

**StoreReadData.srv**
Read data from blockchain storage:
```rossrv
string key
---
string value_json
```

#### Access Control Services

**AccessCreateRole.srv**
Create a new role in the access control system:
```rossrv
string role
string description
---
string tx_hash
```

**AccessCreatePermission.srv**
Create a new permission:
```rossrv
string permission
string description
---
string tx_hash
```

**AccessAssignPermToRole.srv**
Assign a permission to a role:
```rossrv
string permission
string role
---
string tx_hash
```

**AccessGrantRole.srv**
Grant a role to a user:
```rossrv
string role
string user
---
string tx_hash
```

## 🔧 Installation

This package is part of the peaq ROS 2 SDK and should be built as part of the complete workspace:

```bash
cd /path/to/Robotics-sdk/packages/ros2
colcon build --packages-select peaq_ros2_interfaces
```

## 📖 Usage

### Publishing Transaction Status

```python
#!/usr/bin/env python3
import rclpy
from peaq_ros2_interfaces.msg import TxStatus

rclpy.init()
node = rclpy.create_node('tx_status_publisher')

publisher = node.create_publisher(TxStatus, 'peaq/tx_status', 10)

msg = TxStatus()
msg.phase = 'FINALIZED'
msg.tx_hash = '0x1234567890abcdef...'
msg.block = 12345
msg.error = ''

publisher.publish(msg)
```

### Calling Identity Services

```python
#!/usr/bin/env python3
import rclpy
from peaq_ros2_interfaces.srv import IdentityCreate

rclpy.init()
node = rclpy.create_node('identity_client')

client = node.create_client(IdentityCreate, '~/identity/create')

request = IdentityCreate.Request()
request.name = "my_robot"
request.metadata_json = '{"type": "humanoid"}'

future = client.call_async(request)
rclpy.spin_until_future_complete(node, future)

if future.result():
    print(f"Created identity: {future.result().tx_hash}")
```

## 🔗 Dependencies

- ROS 2 (Humble or later)
- builtin_interfaces
- rcl_interfaces

## 📋 Build Information

This package generates C++ and Python interfaces from the `.msg` and `.srv` files during the build process. The generated files are placed in the package's install directory.

## 🧪 Testing

Run tests for this package:

```bash
colcon test --packages-select peaq_ros2_interfaces
```

## 📄 License

Apache License 2.0
