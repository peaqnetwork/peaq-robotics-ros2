#!/usr/bin/env python3
"""
Example script to store data on the blockchain using peaq ROS 2 services.

This script demonstrates how to call the storage service to add data
and monitor the transaction status.
"""
import sys
import rclpy
from rclpy.node import Node
import json

# Import custom interfaces
from peaq_ros2_interfaces.srv import StoreAddData, StoreReadData
from peaq_ros2_interfaces.msg import TxStatus


class StorageClient(Node):
    """ROS 2 client for blockchain storage operations."""

    def __init__(self):
        super().__init__('storage_client')

        # Create service clients
        self.store_add_client = self.create_client(StoreAddData, '~/storage/add')
        self.store_read_client = self.create_client(StoreReadData, '~/storage/read')

        # Create subscriber for transaction status
        self.tx_status_subscriber = self.create_subscription(
            TxStatus,
            'peaq/tx_status',
            self.tx_status_callback,
            10
        )

        # Track transaction status
        self.pending_txs = set()

        self.get_logger().info('Storage client ready')

    def tx_status_callback(self, msg: TxStatus):
        """Handle transaction status updates."""
        if msg.tx_hash in self.pending_txs:
            if msg.phase == 'PENDING':
                self.get_logger().info(f'📋 Storage transaction pending: {msg.tx_hash[:8]}...')
            elif msg.phase == 'IN_BLOCK':
                self.get_logger().info(f'📦 Storage transaction in block: {msg.tx_hash[:8]}...')
            elif msg.phase == 'FINALIZED':
                self.get_logger().info(f'✅ Storage transaction finalized: {msg.tx_hash[:8]}...')
                self.pending_txs.discard(msg.tx_hash)
            elif msg.phase == 'FAILED':
                self.get_logger().error(f'❌ Storage transaction failed: {msg.tx_hash[:8]}... Error: {msg.error}')
                self.pending_txs.discard(msg.tx_hash)

    def store_data(self, key: str, value: dict, mode: str = "FAST"):
        """Store data on the blockchain."""
        if not self.store_add_client.wait_for_service(timeout_sec=5.0):
            self.get_logger().error('Storage add service not available')
            return False

        # Prepare request
        request = StoreAddData.Request()
        request.key = key
        request.value_json = json.dumps(value)
        request.mode = mode

        # Make service call
        future = self.store_add_client.call_async(request)

        # Wait for response
        rclpy.spin_until_future_complete(self, future)

        if future.result() is not None:
            response = future.result()
            if response.result.startswith('Success:'):
                tx_hash = response.result.split(': ')[1]
                self.get_logger().info(f'🚀 Storage transaction initiated: {tx_hash[:8]}...')
                self.pending_txs.add(tx_hash)
                return True
            else:
                self.get_logger().error(f'❌ Storage failed: {response.result}')
                return False
        else:
            self.get_logger().error('❌ Storage service call failed')
            return False

    def read_data(self, key: str):
        """Read data from the blockchain."""
        if not self.store_read_client.wait_for_service(timeout_sec=5.0):
            self.get_logger().error('Storage read service not available')
            return None

        # Prepare request
        request = StoreReadData.Request()
        request.key = key

        # Make service call
        future = self.store_read_client.call_async(request)

        # Wait for response
        rclpy.spin_until_future_complete(self, future)

        if future.result() is not None:
            response = future.result()
            try:
                data = json.loads(response.value_json)
                self.get_logger().info(f'✅ Read data for key: {key}')
                return data
            except json.JSONDecodeError:
                self.get_logger().error(f'❌ Invalid JSON response: {response.value_json}')
                return None
        else:
            self.get_logger().error('❌ Storage read service call failed')
            return None


def main(args=None):
    """Main function."""
    rclpy.init(args=args)

    # Create client node
    client = StorageClient()

    print("💾 peaq ROS 2 Storage Demo")
    print("=" * 40)

    try:
        # Store some sample data
        print("Storing telemetry data...")
        telemetry_data = {
            "robot_id": "unitree_g1_001",
            "timestamp": "2024-01-01T12:00:00Z",
            "battery_level": 85.5,
            "position": {"x": 1.2, "y": 0.8, "z": 0.0},
            "temperature": 22.3,
            "status": "operational"
        }

        success = client.store_data("TELEMETRY_ROBOT_001", telemetry_data, "FAST")

        if success:
            print("✅ Telemetry data stored successfully")
            print("📋 Monitoring transaction status... (Ctrl+C to exit)")
            print()

            # Wait a moment then try to read the data
            import time
            time.sleep(2.0)

            print("Reading stored data...")
            read_data = client.read_data("TELEMETRY_ROBOT_001")

            if read_data:
                print("📖 Retrieved data:")
                print(json.dumps(read_data, indent=2))

            # Keep the node running to monitor transaction status
            rclpy.spin(client)
        else:
            print("❌ Failed to store data")

    except KeyboardInterrupt:
        print("\n👋 Shutting down...")
    finally:
        client.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
