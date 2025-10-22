"""
Events ROS 2 node for streaming blockchain events and triggers.

This node subscribes to peaq_robot SDK events and publishes them to ROS topics.
It also handles transaction status callbacks and publishes them to the tx_status topic.
"""
import json
import rclpy
from rclpy.node import Node
from rclpy.lifecycle import LifecycleNode, LifecycleState, TransitionCallbackReturn

# Import peaq_robot SDK
from peaq_robot import on_event, query_state

# Import custom interfaces
from peaq_ros2_interfaces.msg import Event, TxStatus

# Import local modules
from .config import PeaqRosConfig, load_config_from_params
from .logging import setup_logging, log_event, log_transaction_status


class EventsNode(LifecycleNode):
    """Lifecycle-managed events node for blockchain event streaming."""

    def __init__(self, node_name: str = 'peaq_events_node'):
        super().__init__(node_name)

        # Initialize configuration
        self.config = None
        self.logger = None

        # Publishers
        self._events_publisher = None
        self._tx_status_publisher = None

        # Event callback reference (for cleanup)
        self._event_callback = None

        # Transaction status callback reference (for cleanup)
        self._tx_status_callback = None

    def on_configure(self, state: LifecycleState) -> TransitionCallbackReturn:
        """Configure the node with parameters."""
        self.get_logger().info('Configuring peaq events node...')

        try:
            # Load configuration from parameters
            params = {}
            for param in self._parameters:
                params[param.name] = param.value

            self.config = load_config_from_params(params)
            self.logger = setup_logging(self.config)

            # Create publishers
            self._create_publishers()

            # Set up event handlers if events are enabled
            if self.config.events_enabled:
                self._setup_event_handlers()

            self.logger.info('✅ Events node configured successfully')
            return TransitionCallbackReturn.SUCCESS

        except Exception as e:
            self.get_logger().error(f'Failed to configure events node: {str(e)}')
            return TransitionCallbackReturn.FAILURE

    def on_activate(self, state: LifecycleState) -> TransitionCallbackReturn:
        """Activate the node."""
        self.get_logger().info('Activating peaq events node...')
        self.logger.info('🚀 Events node activated')
        return TransitionCallbackReturn.SUCCESS

    def on_deactivate(self, state: LifecycleState) -> TransitionCallbackReturn:
        """Deactivate the node."""
        self.get_logger().info('Deactivating peaq events node...')
        self.logger.info('⏸️ Events node deactivated')
        return TransitionCallbackReturn.SUCCESS

    def on_cleanup(self, state: LifecycleState) -> TransitionCallbackReturn:
        """Clean up the node."""
        self.get_logger().info('Cleaning up peaq events node...')

        # Clean up event handlers
        if self._event_callback:
            # Note: peaq_robot SDK may not expose a way to remove callbacks
            # This is a limitation we need to handle
            pass

        # Clean up publishers
        if self._events_publisher:
            self.destroy_publisher(self._events_publisher)
        if self._tx_status_publisher:
            self.destroy_publisher(self._tx_status_publisher)

        self.logger.info('🧹 Events node cleaned up')
        return TransitionCallbackReturn.SUCCESS

    def on_shutdown(self, state: LifecycleState) -> TransitionCallbackReturn:
        """Shutdown the node."""
        self.get_logger().info('Shutting down peaq events node...')
        self.logger.info('👋 Events node shutdown')
        return TransitionCallbackReturn.SUCCESS

    def _create_publishers(self):
        """Create ROS 2 publishers."""
        self._events_publisher = self.create_publisher(
            Event,
            'peaq/events',
            10
        )

        self._tx_status_publisher = self.create_publisher(
            TxStatus,
            'peaq/tx_status',
            10
        )

        self.logger.info('📢 Events publishers created')

    def _setup_event_handlers(self):
        """Set up event handlers for blockchain events."""
        try:
            # Set up blockchain event handler
            self._event_callback = self._handle_blockchain_event
            on_event(self._event_callback)

            self.logger.info('🔗 Blockchain event handler registered')

        except Exception as e:
            self.logger.error(f'Failed to set up event handlers: {str(e)}')
            raise

    def _handle_blockchain_event(self, event_data):
        """Handle incoming blockchain events from peaq_robot SDK."""
        try:
            # Log the event
            log_event(
                self.logger,
                source='blockchain',
                event_type=event_data.get('type', 'unknown'),
                payload=event_data
            )

            # Publish to ROS topic
            self._publish_event('blockchain', event_data)

        except Exception as e:
            self.logger.error(f'Error handling blockchain event: {str(e)}')

    def _publish_event(self, source: str, event_data: dict):
        """Publish event to ROS topic."""
        if not self._events_publisher:
            return

        msg = Event()
        msg.source = source
        msg.type = event_data.get('type', 'unknown')
        msg.payload_json = json.dumps(event_data, indent=2)

        self._events_publisher.publish(msg)

    def publish_custom_event(self, source: str, event_type: str, payload: dict = None):
        """Publish a custom event to the ROS topic."""
        event_data = {
            'type': event_type,
            'timestamp': json.dumps(payload) if payload else None,
            'payload': payload or {}
        }

        # Log the event
        log_event(self.logger, source, event_type, payload)

        # Publish to ROS topic
        self._publish_event(source, event_data)

    def publish_tx_status(self, phase: str, tx_hash: str, block: int = 0, error: str = None):
        """Publish transaction status to ROS topic."""
        if not self._tx_status_publisher:
            return

        msg = TxStatus()
        msg.phase = phase
        msg.tx_hash = tx_hash
        msg.block = block
        msg.error = error or ''

        self._tx_status_publisher.publish(msg)

        # Also log the transaction status
        log_transaction_status(self.logger, phase, tx_hash, block, error)


def main(args=None):
    """Main entry point for the events node."""
    rclpy.init(args=args)

    # Create node with lifecycle management
    node = EventsNode()

    try:
        # Spin the node
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        # Cleanup
        node.destroy_node()
        rclpy.shutdown()
