#!/usr/bin/env python3
"""
Example script to create a DID identity using peaq ROS 2 services.

This script demonstrates how to call the identity creation service
and monitor the transaction status.
"""
import sys
import rclpy
from rclpy.node import Node
import json

# Import custom interfaces
from peaq_ros2_interfaces.srv import IdentityCreate
from peaq_ros2_interfaces.msg import TxStatus


class IdentityCreationClient(Node):
    """ROS 2 client for creating blockchain identities."""

    def __init__(self):
        super().__init__('identity_creation_client')

        # Create service client
        self.client = self.create_client(IdentityCreate, '~/identity/create')

        # Create subscriber for transaction status
        self.tx_status_subscriber = self.create_subscription(
            TxStatus,
            'peaq/tx_status',
            self.tx_status_callback,
            10
        )

        # Track transaction status
        self.pending_txs = set()

        self.get_logger().info('Identity creation client ready')

    def tx_status_callback(self, msg: TxStatus):
        """Handle transaction status updates."""
        if msg.tx_hash in self.pending_txs:
            if msg.phase == 'PENDING':
                self.get_logger().info(f'📋 Transaction pending: {msg.tx_hash[:8]}...')
            elif msg.phase == 'IN_BLOCK':
                self.get_logger().info(f'📦 Transaction in block: {msg.tx_hash[:8]}...')
            elif msg.phase == 'FINALIZED':
                self.get_logger().info(f'✅ Transaction finalized: {msg.tx_hash[:8]}...')
                self.pending_txs.discard(msg.tx_hash)
            elif msg.phase == 'FAILED':
                self.get_logger().error(f'❌ Transaction failed: {msg.tx_hash[:8]}... Error: {msg.error}')
                self.pending_txs.discard(msg.tx_hash)

    def create_identity(self, name: str, metadata: str = None):
        """Create a new identity."""
        if not self.client.wait_for_service(timeout_sec=5.0):
            self.get_logger().error('Identity creation service not available')
            return False

        # Prepare request
        request = IdentityCreate.Request()
        request.name = name
        request.metadata_json = metadata or json.dumps({
            'created_by': 'peaq_ros2_example',
            'timestamp': self.get_clock().now().to_msg().sec
        })

        # Make service call
        future = self.client.call_async(request)

        # Wait for response
        rclpy.spin_until_future_complete(self, future)

        if future.result() is not None:
            response = future.result()
            if response.tx_hash:
                self.get_logger().info(f'🚀 Identity creation initiated: {response.tx_hash[:8]}...')
                self.pending_txs.add(response.tx_hash)
                return True
            else:
                self.get_logger().error('❌ Identity creation failed')
                return False
        else:
            self.get_logger().error('❌ Service call failed')
            return False


def main(args=None):
    """Main function."""
    rclpy.init(args=args)

    # Create client node
    client = IdentityCreationClient()

    # Create identity (you can modify these parameters)
    name = "peaq_ros2_robot_001"
    metadata = json.dumps({
        "robot_type": "humanoid",
        "capabilities": ["locomotion", "manipulation", "perception"],
        "created_at": "2024-01-01T00:00:00Z"
    })

    success = client.create_identity(name, metadata)

    if success:
        print(f"✅ Identity creation initiated for '{name}'")
        print("📋 Monitoring transaction status... (Ctrl+C to exit)")

        try:
            # Keep the node running to monitor transaction status
            rclpy.spin(client)
        except KeyboardInterrupt:
            print("\n👋 Shutting down...")
        finally:
            client.destroy_node()
            rclpy.shutdown()
    else:
        print("❌ Failed to create identity")
        client.destroy_node()
        rclpy.shutdown()
        sys.exit(1)


if __name__ == '__main__':
    main()
