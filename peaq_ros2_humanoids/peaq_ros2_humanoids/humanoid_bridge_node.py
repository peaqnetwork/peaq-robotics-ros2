"""
Humanoid Bridge Node for peaq blockchain integration.

This node listens for blockchain events containing robot intents and executes them
using the appropriate humanoid adapter (e.g., Unitree G1).
"""
import os
import json
import rclpy
from rclpy.node import Node
from rclpy.lifecycle import LifecycleNode, LifecycleState, TransitionCallbackReturn

# Import custom interfaces
from peaq_ros2_interfaces.msg import Event

# Import local modules
from .common import AdapterFactory
from .intents import IntentMessage, parse_intent_from_json
from peaq_ros2_core.config import PeaqRosConfig, load_config_from_params
from peaq_ros2_core.logging import setup_logging, log_event


class HumanoidBridgeNode(LifecycleNode):
    """Lifecycle-managed humanoid bridge node."""

    def __init__(self, node_name: str = 'peaq_humanoid_bridge_node'):
        super().__init__(node_name)

        # Initialize configuration
        self.config = None
        self.logger = None

        # Adapter management
        self.adapter = None
        self.adapter_type = None

        # ROS subscribers
        self._events_subscriber = None

        # Control state
        self._ros_only_mode = False

        # Optional autostart without lifecycle transitions (for dev/offline mode)
        if os.getenv('PEAQ_ROS2_AUTOSTART', 'false').lower() == 'true':
            try:
                self._autostart_setup()
            except Exception as e:
                self.get_logger().error(f'Autostart setup failed: {str(e)}')

    def on_configure(self, state: LifecycleState) -> TransitionCallbackReturn:
        """Configure the node with parameters."""
        self.get_logger().info('Configuring peaq humanoid bridge node...')

        try:
            # Load configuration from parameters
            params = {}
            for param in self._parameters:
                params[param.name] = param.value

            self.config = load_config_from_params(params)
            self.logger = setup_logging(self.config)

            # Get adapter configuration
            self.adapter_type = params.get('humanoids.adapter', 'unitree_g1')
            adapter_config = params.get('humanoids.adapter_config', {})

            # Create adapter
            self._create_adapter(adapter_config)

            # Create subscribers
            self._create_subscribers()

            self.logger.info('✅ Humanoid bridge node configured successfully')
            return TransitionCallbackReturn.SUCCESS

        except Exception as e:
            self.get_logger().error(f'Failed to configure humanoid bridge node: {str(e)}')
            return TransitionCallbackReturn.FAILURE

    def on_activate(self, state: LifecycleState) -> TransitionCallbackReturn:
        """Activate the node."""
        self.get_logger().info('Activating peaq humanoid bridge node...')

        # Initialize adapter
        if self.adapter and not self.adapter.initialize():
            self.get_logger().error('Failed to initialize humanoid adapter')
            return TransitionCallbackReturn.FAILURE

        self.logger.info('🚀 Humanoid bridge node activated')
        return TransitionCallbackReturn.SUCCESS

    def on_deactivate(self, state: LifecycleState) -> TransitionCallbackReturn:
        """Deactivate the node."""
        self.get_logger().info('Deactivating peaq humanoid bridge node...')

        # Shutdown adapter
        if self.adapter:
            self.adapter.shutdown()

        self.logger.info('⏸️ Humanoid bridge node deactivated')
        return TransitionCallbackReturn.SUCCESS

    def on_cleanup(self, state: LifecycleState) -> TransitionCallbackReturn:
        """Clean up the node."""
        self.get_logger().info('Cleaning up peaq humanoid bridge node...')

        # Clean up adapter
        if self.adapter:
            self.adapter.shutdown()

        # Clean up subscribers
        if self._events_subscriber:
            self.destroy_subscription(self._events_subscriber)

        self.logger.info('🧹 Humanoid bridge node cleaned up')
        return TransitionCallbackReturn.SUCCESS

    def on_shutdown(self, state: LifecycleState) -> TransitionCallbackReturn:
        """Shutdown the node."""
        self.get_logger().info('Shutting down peaq humanoid bridge node...')
        self.logger.info('👋 Humanoid bridge node shutdown')
        return TransitionCallbackReturn.SUCCESS

    def _create_adapter(self, adapter_config: dict):
        """Create and configure the humanoid adapter."""
        try:
            self.logger.info(f'🤖 Creating {self.adapter_type} adapter...')

            self.adapter = AdapterFactory.create_adapter(
                self.adapter_type,
                self,
                adapter_config
            )

            self.logger.info(f'✅ {self.adapter_type} adapter created successfully')

        except Exception as e:
            error_msg = f'Failed to create adapter: {str(e)}'
            self.get_logger().error(error_msg)
            raise RuntimeError(error_msg)

    def _create_subscribers(self):
        """Create ROS subscribers."""
        # Subscribe to blockchain events
        self._events_subscriber = self.create_subscription(
            Event,
            'peaq/events',
            self._handle_blockchain_event,
            10
        )

        self.logger.info('📡 Event subscriber created')

    def _autostart_setup(self):
        """Initialize config, adapter and subscribers without lifecycle transitions."""
        params = {}
        for param in self._parameters:
            params[param.name] = param.value
        self.config = load_config_from_params(params)
        self.logger = setup_logging(self.config)
        self.adapter_type = params.get('humanoids.adapter', 'unitree_g1')
        adapter_config = params.get('humanoids.adapter_config', {})
        self._create_adapter(adapter_config)
        self._create_subscribers()
        self.logger.info('⚙️ Humanoid autostart completed')

    def _handle_blockchain_event(self, msg: Event):
        """Handle incoming blockchain events."""
        try:
            # Log the event
            log_event(self.logger, msg.source, msg.type, {'payload': msg.payload_json})

            # Parse intent from event payload
            try:
                intent_message = parse_intent_from_json(msg.payload_json)
            except Exception as e:
                self.logger.warning(f'Failed to parse intent from event: {str(e)}')
                return

            # Check if this intent is for us
            if not self._should_handle_intent(intent_message):
                return

            # Execute the intent
            self._execute_intent(intent_message)

        except Exception as e:
            self.logger.error(f'Error handling blockchain event: {str(e)}')

    def _should_handle_intent(self, intent_message: IntentMessage) -> bool:
        """Check if we should handle this intent."""
        # Check destination if specified
        if intent_message.destination:
            # This could be used for multi-robot scenarios
            robot_name = self.get_name().replace('peaq_humanoid_bridge_node', '').strip('_')
            if robot_name and intent_message.destination != robot_name:
                return False

        # Check if adapter is ready
        if not self.adapter or not self.adapter.is_ready():
            self.logger.warning('Adapter not ready, skipping intent')
            return False

        return True

    def _execute_intent(self, intent_message: IntentMessage):
        """Execute the intent using the appropriate adapter method."""
        try:
            intent = intent_message.intent

            self.logger.info(f'⚡ Executing intent: {intent.intent_type} (priority: {intent.priority})')

            success = False

            if intent.intent_type == 'locomotion':
                from .intents import LocomotionIntent
                locomotion_intent = LocomotionIntent(**intent.dict())
                success = self.adapter.execute_locomotion_intent(locomotion_intent)

            elif intent.intent_type == 'posture':
                from .intents import PostureIntent
                posture_intent = PostureIntent(**intent.dict())
                success = self.adapter.execute_posture_intent(posture_intent)

            elif intent.intent_type == 'gesture':
                from .intents import GestureIntent
                gesture_intent = GestureIntent(**intent.dict())
                success = self.adapter.execute_gesture_intent(gesture_intent)

            elif intent.intent_type == 'task':
                from .intents import TaskIntent
                task_intent = TaskIntent(**intent.dict())
                success = self.adapter.execute_task_intent(task_intent)

            elif intent.intent_type == 'emergency':
                from .intents import EmergencyIntent
                emergency_intent = EmergencyIntent(**intent.dict())
                success = self.adapter.handle_emergency_intent(emergency_intent)

            else:
                self.logger.warning(f'⚠️ Unknown intent type: {intent.intent_type}')
                return

            if success:
                self.logger.info(f'✅ Intent executed successfully: {intent.intent_type}')

                # Publish telemetry if configured
                self._publish_robot_telemetry()
            else:
                self.logger.error(f'❌ Failed to execute intent: {intent.intent_type}')

        except Exception as e:
            self.logger.error(f'Error executing intent: {str(e)}')

    def _publish_robot_telemetry(self):
        """Publish robot state as telemetry data."""
        try:
            if not self.adapter:
                return

            # Get robot state
            robot_state = self.adapter.get_robot_state()

            # Create telemetry payload
            telemetry_data = {
                'robot_state': robot_state,
                'adapter_type': self.adapter_type,
                'timestamp': self.get_clock().now().to_msg().sec,
            }

            # In a real implementation, you might want to publish this to a telemetry topic
            # or send it back to blockchain storage for logging

            self.logger.debug(f'📊 Robot telemetry: {telemetry_data}')

        except Exception as e:
            self.logger.error(f'Error publishing telemetry: {str(e)}')

    def execute_intent_from_json(self, json_data: str) -> bool:
        """Execute an intent from JSON string (for testing or manual control)."""
        try:
            intent_message = parse_intent_from_json(json_data)
            self._execute_intent(intent_message)
            return True
        except Exception as e:
            self.logger.error(f'Failed to execute intent from JSON: {str(e)}')
            return False

    def get_adapter_info(self) -> dict:
        """Get information about the current adapter."""
        if not self.adapter:
            return {'adapter_type': None, 'is_ready': False}

        return {
            'adapter_type': self.adapter_type,
            'is_ready': self.adapter.is_ready(),
            'robot_state': self.adapter.get_robot_state(),
        }

    def emergency_stop(self) -> bool:
        """Perform emergency stop."""
        if self.adapter:
            return self.adapter.emergency_stop()
        return False

    def clear_emergency_stop(self) -> bool:
        """Clear emergency stop state."""
        if self.adapter:
            return self.adapter.clear_emergency_stop()
        return False


def main(args=None):
    """Main entry point for the humanoid bridge node."""
    rclpy.init(args=args)

    # Create node with lifecycle management
    node = HumanoidBridgeNode()

    try:
        # Spin the node
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        # Cleanup
        node.destroy_node()
        rclpy.shutdown()
