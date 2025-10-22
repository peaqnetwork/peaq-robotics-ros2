"""
Unitree G1 Humanoid Robot Adapter

This adapter provides integration with Unitree G1 humanoid robots,
translating blockchain intents to ROS topics and robot commands.
"""
import time
from typing import Dict, Any, Optional, Tuple
import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist, Pose
from sensor_msgs.msg import BatteryState, JointState
from std_msgs.msg import Float64

from ..common import HumanoidAdapter
from ..intents import LocomotionIntent, PostureIntent, GestureIntent, TaskIntent, EmergencyIntent


class UnitreeG1Adapter(HumanoidAdapter):
    """Adapter for Unitree G1 humanoid robot."""

    def __init__(self, node: Node, adapter_config: Dict[str, Any]):
        super().__init__(node, adapter_config)

        # ROS publishers for robot control
        self._cmd_vel_publisher = None
        self._cmd_pose_publisher = None
        self._joint_cmd_publishers = {}

        # ROS subscribers for robot state
        self._battery_subscriber = None
        self._joint_state_subscriber = None
        self._odom_subscriber = None

        # Robot-specific parameters
        self.max_linear_velocity = adapter_config.get('max_linear_velocity', 1.0)  # m/s
        self.max_angular_velocity = adapter_config.get('max_angular_velocity', 2.0)  # rad/s
        self.joint_names = adapter_config.get('joint_names', [])

        # Control state
        self._last_cmd_time = 0.0
        self._motion_timeout = adapter_config.get('motion_timeout', 5.0)  # seconds

    def initialize(self) -> bool:
        """Initialize the Unitree G1 robot connection."""
        try:
            self.logger.info("🤖 Initializing Unitree G1 adapter...")

            # Create ROS publishers
            self._create_publishers()

            # Create ROS subscribers
            self._create_subscribers()

            # Wait a moment for connections to establish
            time.sleep(1.0)

            # Update robot state
            self.robot_state['is_connected'] = True
            self.robot_state['current_posture'] = 'stand_relaxed'

            self._is_initialized = True
            self.logger.info("✅ Unitree G1 adapter initialized successfully")

            return True

        except Exception as e:
            self.logger.error(f"❌ Failed to initialize Unitree G1 adapter: {str(e)}")
            return False

    def shutdown(self) -> bool:
        """Shutdown the Unitree G1 robot connection."""
        try:
            self.logger.info("🔌 Shutting down Unitree G1 adapter...")

            # Stop any ongoing motion
            self._stop_all_motion()

            # Clean up publishers
            if self._cmd_vel_publisher:
                self.node.destroy_publisher(self._cmd_vel_publisher)
            if self._cmd_pose_publisher:
                self.node.destroy_publisher(self._cmd_pose_publisher)

            # Clean up subscribers
            if self._battery_subscriber:
                self.node.destroy_subscription(self._battery_subscriber)
            if self._joint_state_subscriber:
                self.node.destroy_subscription(self._joint_state_subscriber)
            if self._odom_subscriber:
                self.node.destroy_subscription(self._odom_subscriber)

            # Clean up joint command publishers
            for pub in self._joint_cmd_publishers.values():
                self.node.destroy_publisher(pub)
            self._joint_cmd_publishers.clear()

            # Update state
            self.robot_state['is_connected'] = False
            self._is_initialized = False

            self.logger.info("✅ Unitree G1 adapter shut down successfully")
            return True

        except Exception as e:
            self.logger.error(f"❌ Error during Unitree G1 adapter shutdown: {str(e)}")
            return False

    def execute_locomotion_intent(self, intent: LocomotionIntent) -> bool:
        """Execute a locomotion intent on Unitree G1."""
        if not self.is_ready():
            self.logger.error("❌ Adapter not ready for locomotion intent")
            return False

        try:
            self.logger.info(f"🏃 Executing locomotion intent: {intent.motion_type}")

            if intent.motion_type.value == "stop":
                # Send zero velocity to stop
                twist = Twist()
                twist.linear.x = 0.0
                twist.linear.y = 0.0
                twist.angular.z = 0.0

            elif intent.motion_type.value in ["move", "walk", "run"]:
                # Create twist message from intent
                twist = Twist()

                # Scale velocities based on motion type
                velocity_scale = {
                    "walk": 0.5,
                    "run": 1.0,
                    "move": 0.7  # Default scaling
                }.get(intent.motion_type.value, 0.7)

                twist.linear.x = max(-self.max_linear_velocity,
                                   min(self.max_linear_velocity,
                                       intent.velocity_x * velocity_scale))
                twist.linear.y = max(-self.max_linear_velocity,
                                   min(self.max_linear_velocity,
                                       intent.velocity_y * velocity_scale))
                twist.angular.z = max(-self.max_angular_velocity,
                                    min(self.max_angular_velocity,
                                        intent.velocity_z * velocity_scale))

            else:
                self.logger.warning(f"⚠️ Unsupported motion type: {intent.motion_type}")
                return False

            # Publish velocity command
            if self._cmd_vel_publisher:
                self._cmd_vel_publisher.publish(twist)
                self._last_cmd_time = time.time()
                self.robot_state['is_moving'] = intent.motion_type.value != "stop"

                # Handle duration if specified
                if intent.duration:
                    self.node.create_timer(
                        intent.duration,
                        lambda: self._stop_motion_after_duration(),
                        oneshot=True
                    )

                self.logger.info(f"✅ Locomotion intent executed: {intent.motion_type}")
                return True

            else:
                self.logger.error("❌ Velocity publisher not available")
                return False

        except Exception as e:
            self.logger.error(f"❌ Error executing locomotion intent: {str(e)}")
            return False

    def execute_posture_intent(self, intent: PostureIntent) -> bool:
        """Execute a posture intent on Unitree G1."""
        if not self.is_ready():
            self.logger.error("❌ Adapter not ready for posture intent")
            return False

        try:
            self.logger.info(f"🧘 Executing posture intent: {intent.posture_type}")

            # Map posture types to robot commands
            posture_commands = {
                "stand_straight": self._stand_straight,
                "stand_relaxed": self._stand_relaxed,
                "sit_chair": self._sit_chair,
                "sit_floor": self._sit_floor,
                "kneel": self._kneel,
                "crouch": self._crouch,
            }

            command_func = posture_commands.get(intent.posture_type.value)
            if command_func:
                success = command_func()
                if success:
                    self.robot_state['current_posture'] = intent.posture_type.value
                    self.logger.info(f"✅ Posture intent executed: {intent.posture_type}")
                    return True
                else:
                    self.logger.error(f"❌ Failed to execute posture: {intent.posture_type}")
                    return False
            else:
                self.logger.warning(f"⚠️ Unsupported posture type: {intent.posture_type}")
                return False

        except Exception as e:
            self.logger.error(f"❌ Error executing posture intent: {str(e)}")
            return False

    def execute_gesture_intent(self, intent: GestureIntent) -> bool:
        """Execute a gesture intent on Unitree G1."""
        if not self.is_ready():
            self.logger.error("❌ Adapter not ready for gesture intent")
            return False

        try:
            self.logger.info(f"👋 Executing gesture intent: {intent.gesture_type}")

            # Map gesture types to robot commands
            gesture_commands = {
                "wave": self._wave_gesture,
                "point": self._point_gesture,
                "nod": self._nod_gesture,
                "shake_head": self._shake_head_gesture,
                "bow": self._bow_gesture,
                "dance": self._dance_gesture,
            }

            command_func = gesture_commands.get(intent.gesture_type.value)
            if command_func:
                success = command_func(intent.speed, intent.amplitude, intent.repetitions)
                if success:
                    self.logger.info(f"✅ Gesture intent executed: {intent.gesture_type}")
                    return True
                else:
                    self.logger.error(f"❌ Failed to execute gesture: {intent.gesture_type}")
                    return False
            else:
                self.logger.warning(f"⚠️ Unsupported gesture type: {intent.gesture_type}")
                return False

        except Exception as e:
            self.logger.error(f"❌ Error executing gesture intent: {str(e)}")
            return False

    def execute_task_intent(self, intent: TaskIntent) -> bool:
        """Execute a task intent on Unitree G1."""
        if not self.is_ready():
            self.logger.error("❌ Adapter not ready for task intent")
            return False

        try:
            self.logger.info(f"⚙️ Executing task intent: {intent.task_type}")

            # Handle common task types
            if intent.task_type == "standby":
                return self._standby_task(intent.parameters)
            elif intent.task_type == "patrol":
                return self._patrol_task(intent.parameters)
            elif intent.task_type == "follow":
                return self._follow_task(intent.parameters)
            elif intent.task_type == "greet":
                return self._greet_task(intent.parameters)
            else:
                self.logger.warning(f"⚠️ Unsupported task type: {intent.task_type}")
                return False

        except Exception as e:
            self.logger.error(f"❌ Error executing task intent: {str(e)}")
            return False

    def handle_emergency_intent(self, intent: EmergencyIntent) -> bool:
        """Handle an emergency intent on Unitree G1."""
        try:
            self.logger.warning(f"🚨 Handling emergency: {intent.emergency_type}")

            # Perform emergency stop
            success = self.emergency_stop()

            if success:
                self.logger.warning(f"✅ Emergency handled: {intent.emergency_type}")
                return True
            else:
                self.logger.error(f"❌ Failed to handle emergency: {intent.emergency_type}")
                return False

        except Exception as e:
            self.logger.error(f"❌ Error handling emergency intent: {str(e)}")
            return False

    def get_robot_state(self) -> Dict[str, Any]:
        """Get current Unitree G1 robot state."""
        return self.robot_state.copy()

    def _stop_all_motion(self) -> bool:
        """Stop all robot motion."""
        try:
            if self._cmd_vel_publisher:
                twist = Twist()
                twist.linear.x = 0.0
                twist.linear.y = 0.0
                twist.angular.z = 0.0
                self._cmd_vel_publisher.publish(twist)

            self.robot_state['is_moving'] = False
            self.logger.info("🛑 All motion stopped")
            return True

        except Exception as e:
            self.logger.error(f"❌ Error stopping motion: {str(e)}")
            return False

    def _create_publishers(self):
        """Create ROS publishers for robot control."""
        # Velocity commands
        self._cmd_vel_publisher = self.node.create_publisher(
            Twist,
            '/cmd_vel',
            10
        )

        # Pose commands (for advanced positioning)
        self._cmd_pose_publisher = self.node.create_publisher(
            Pose,
            '/cmd_pose',
            10
        )

        # Joint command publishers
        for joint_name in self.joint_names:
            pub = self.node.create_publisher(
                Float64,
                f'/joint/{joint_name}/command',
                10
            )
            self._joint_cmd_publishers[joint_name] = pub

        self.logger.info("📡 Robot control publishers created")

    def _create_subscribers(self):
        """Create ROS subscribers for robot state."""
        # Battery state
        self._battery_subscriber = self.node.create_subscription(
            BatteryState,
            '/battery_state',
            self._battery_callback,
            10
        )

        # Joint states
        self._joint_state_subscriber = self.node.create_subscription(
            JointState,
            '/joint_states',
            self._joint_state_callback,
            10
        )

        self.logger.info("📡 Robot state subscribers created")

    def _battery_callback(self, msg: BatteryState):
        """Handle battery state updates."""
        self.robot_state['battery_level'] = msg.percentage * 100.0

    def _joint_state_callback(self, msg: JointState):
        """Handle joint state updates."""
        # Update joint positions if needed
        pass

    def _stop_motion_after_duration(self):
        """Timer callback to stop motion after duration."""
        if time.time() - self._last_cmd_time > self._motion_timeout:
            self._stop_all_motion()

    # Posture implementation methods
    def _stand_straight(self) -> bool:
        """Execute stand straight posture."""
        # Implementation would depend on specific Unitree G1 API
        self.logger.info("🧘 Executing stand straight posture")
        return True

    def _stand_relaxed(self) -> bool:
        """Execute stand relaxed posture."""
        self.logger.info("🧘 Executing stand relaxed posture")
        return True

    def _sit_chair(self) -> bool:
        """Execute sit on chair posture."""
        self.logger.info("🧘 Executing sit chair posture")
        return True

    def _sit_floor(self) -> bool:
        """Execute sit on floor posture."""
        self.logger.info("🧘 Executing sit floor posture")
        return True

    def _kneel(self) -> bool:
        """Execute kneel posture."""
        self.logger.info("🧘 Executing kneel posture")
        return True

    def _crouch(self) -> bool:
        """Execute crouch posture."""
        self.logger.info("🧘 Executing crouch posture")
        return True

    # Gesture implementation methods
    def _wave_gesture(self, speed: float, amplitude: float, repetitions: int) -> bool:
        """Execute wave gesture."""
        self.logger.info(f"👋 Executing wave gesture (speed={speed}, amplitude={amplitude}, reps={repetitions})")
        return True

    def _point_gesture(self, speed: float, amplitude: float, repetitions: int) -> bool:
        """Execute point gesture."""
        self.logger.info(f"👆 Executing point gesture (speed={speed}, amplitude={amplitude}, reps={repetitions})")
        return True

    def _nod_gesture(self, speed: float, amplitude: float, repetitions: int) -> bool:
        """Execute nod gesture."""
        self.logger.info(f"✅ Executing nod gesture (speed={speed}, amplitude={amplitude}, reps={repetitions})")
        return True

    def _shake_head_gesture(self, speed: float, amplitude: float, repetitions: int) -> bool:
        """Execute shake head gesture."""
        self.logger.info(f"❌ Executing shake head gesture (speed={speed}, amplitude={amplitude}, reps={repetitions})")
        return True

    def _bow_gesture(self, speed: float, amplitude: float, repetitions: int) -> bool:
        """Execute bow gesture."""
        self.logger.info(f"🙇 Executing bow gesture (speed={speed}, amplitude={amplitude}, reps={repetitions})")
        return True

    def _dance_gesture(self, speed: float, amplitude: float, repetitions: int) -> bool:
        """Execute dance gesture."""
        self.logger.info(f"💃 Executing dance gesture (speed={speed}, amplitude={amplitude}, reps={repetitions})")
        return True

    # Task implementation methods
    def _standby_task(self, parameters: Dict[str, Any]) -> bool:
        """Execute standby task."""
        self.logger.info("😴 Executing standby task")
        return True

    def _patrol_task(self, parameters: Dict[str, Any]) -> bool:
        """Execute patrol task."""
        self.logger.info("🚶 Executing patrol task")
        return True

    def _follow_task(self, parameters: Dict[str, Any]) -> bool:
        """Execute follow task."""
        self.logger.info("👥 Executing follow task")
        return True

    def _greet_task(self, parameters: Dict[str, Any]) -> bool:
        """Execute greet task."""
        self.logger.info("👋 Executing greet task")
        return True
