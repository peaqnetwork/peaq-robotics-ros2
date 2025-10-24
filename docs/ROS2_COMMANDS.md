# ROS 2 Commands Reference (Copy & Paste)

This reference collects common `ros2` topic publications and service calls used by peaq ROS 2 SDK. Commands assume you have sourced ROS 2 and the workspace:

```bash
source /opt/ros/humble/setup.bash
source install/setup.bash
```

Ensure your configuration file exists and is populated (see `peaq_ros2_examples/config/peaq_robot.example.yaml`).

## Nodes and Parameters

### Start Core Node

```bash
ros2 run peaq_ros2_core core_node --ros-args \
  -p config.yaml_path:=/work/peaq_ros2_examples/config/peaq_robot.yaml &

# Configure and activate lifecycle
ros2 lifecycle set /peaq_core_node configure
ros2 lifecycle set /peaq_core_node activate
```

### Start Storage Bridge

```bash
ros2 run peaq_ros2_core storage_bridge_node --ros-args \
  -p config.yaml_path:=/work/peaq_ros2_examples/config/peaq_robot.yaml &

# Configure and activate lifecycle
ros2 lifecycle set /peaq_storage_bridge_node configure
ros2 lifecycle set /peaq_storage_bridge_node activate
```

---

## Topics

### Publish StorageIngest (Upload Data)

Message type: `peaq_ros2_interfaces/msg/StorageIngest`

Fields:
- `key: string` (identifier for your data)
- `is_file: bool` (true if sending file content from `file_path`)
- `file_path: string` (path to file if `is_file` is true)
- `content: string` (raw text content if `is_file` is false)
- `content_type: string` (e.g., `text/plain`, `application/json`)
- `metadata_json: string` (JSON metadata)

Examples:

```bash
# Send raw text content
ros2 topic pub --once /peaq/storage/ingest \
  peaq_ros2_interfaces/msg/StorageIngest \
  '{key: "sensor_data", is_file: false, file_path: "", content: "temperature:25.5", content_type: "text/plain", metadata_json: "{}"}'

# Send JSON content
ros2 topic pub --once /peaq/storage/ingest \
  peaq_ros2_interfaces/msg/StorageIngest \
  '{key: "telemetry", is_file: false, file_path: "", content: "{\\"temp\\":25.5,\\"hum\\":60.2}", content_type: "application/json", metadata_json: "{}"}'

# Send file content by path
ros2 topic pub --once /peaq/storage/ingest \
  peaq_ros2_interfaces/msg/StorageIngest \
  '{key: "logfile", is_file: true, file_path: "/work/logs/sample.log", content: "", content_type: "text/plain", metadata_json: "{\\"tags\\":[\\"log\\"]}"}'
```

### Subscribe to Storage Results

Message type: `peaq_ros2_interfaces/msg/StorageResult`

```bash
ros2 topic echo /peaq/storage/status
```

### Subscribe to Transaction Status

Message type: `peaq_ros2_interfaces/msg/TxStatus`

```bash
ros2 topic echo /peaq/tx_status
```

---

## Services (Core Node)

### Get Node Info

Service: `/peaq_core_node/info` — `peaq_ros2_interfaces/srv/GetNodeInfo`

```bash
ros2 service call /peaq_core_node/info \
  peaq_ros2_interfaces/srv/GetNodeInfo
```

### Identity Create

Service: `/peaq_core_node/identity/create` — `peaq_ros2_interfaces/srv/IdentityCreate`

Request fields:
- `metadata_json: string` (optional, JSON string)

```bash
ros2 service call /peaq_core_node/identity/create \
  peaq_ros2_interfaces/srv/IdentityCreate \
  '{metadata_json: "{\\"type\\": \\"robot\\"}"}'
```

### Identity Read

Service: `/peaq_core_node/identity/read` — `peaq_ros2_interfaces/srv/IdentityRead`

```bash
ros2 service call /peaq_core_node/identity/read \
  peaq_ros2_interfaces/srv/IdentityRead
```

### Storage Read

Service: `/peaq_core_node/storage/read` — `peaq_ros2_interfaces/srv/StoreReadData`

Request fields:
- `key: string`

```bash
ros2 service call /peaq_core_node/storage/read \
  peaq_ros2_interfaces/srv/StoreReadData \
  '{key: "sensor_data"}'
```

### Storage Add (Direct Chain Write)

Service: `/peaq_core_node/storage/add` — `peaq_ros2_interfaces/srv/StoreAddData`

Request fields:
- `key: string`
- `value_json: string` (JSON string)
- `mode: string` (FAST or FINAL)

```bash
ros2 service call /peaq_core_node/storage/add \
  peaq_ros2_interfaces/srv/StoreAddData \
  '{key: "sensor_data", value_json: "{\\"cid\\":\\"Qm...\\"}", mode: "FAST"}'
```

---

## Services (Access Control)

### Create Role

Service: `/peaq_core_node/access/create_role` — `peaq_ros2_interfaces/srv/AccessCreateRole`

```bash
ros2 service call /peaq_core_node/access/create_role \
  peaq_ros2_interfaces/srv/AccessCreateRole \
  '{role: "operator", description: "Operator role"}'
```

### Create Permission

Service: `/peaq_core_node/access/create_permission` — `peaq_ros2_interfaces/srv/AccessCreatePermission`

```bash
ros2 service call /peaq_core_node/access/create_permission \
  peaq_ros2_interfaces/srv/AccessCreatePermission \
  '{permission: "storage:write", description: "Write storage data"}'
```

### Assign Permission to Role

Service: `/peaq_core_node/access/assign_permission` — `peaq_ros2_interfaces/srv/AccessAssignPermToRole`

```bash
ros2 service call /peaq_core_node/access/assign_permission \
  peaq_ros2_interfaces/srv/AccessAssignPermToRole \
  '{permission: "storage:write", role: "operator"}'
```

### Grant Role to User

Service: `/peaq_core_node/access/grant_role` — `peaq_ros2_interfaces/srv/AccessGrantRole`

```bash
ros2 service call /peaq_core_node/access/grant_role \
  peaq_ros2_interfaces/srv/AccessGrantRole \
  '{role: "operator", user: "did:peaq:5ABC..."}'
```

---

## Tips

- Always source ROS 2 and workspace before running commands.
- Ensure `peaq_ros2_core` nodes are configured/activated before invoking services.
- For JSON strings in shell, escape quotes as shown above.
- Monitor logs in another terminal:

```bash
tail -f /tmp/core_node.log /tmp/storage_bridge.log
```

