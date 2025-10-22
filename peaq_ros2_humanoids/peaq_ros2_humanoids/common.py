"""
Common interfaces and base classes for humanoid robot adapters.

This module defines the abstract base classes that all humanoid adapters
must implement, providing a consistent interface for robot control.
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Tuple
import rclpy
from rclpy.node import Node
import logging

from .intents import IntentMessage, LocomotionIntent, PostureIntent, GestureIntent, TaskIntent, EmergencyIntent


class HumanoidAdapter(ABC):
    """Abstract base class for humanoid robot adapters."""

    def __init__(self, node: Node, adapter_config: Dict[str, Any]):
        """
        Initialize the adapter.

        Args:
            node: ROS 2 node instance
            adapter_config: Configuration specific to this adapter
        """
        self.node = node
        self.config = adapter_config
        self.logger = logging.getLogger(f'{node.get_name()}.{self.__class__.__name__}')

        # Initialize adapter-specific state
        self._is_initialized = False
        self._emergency_stop = False

        # Robot state
        self.robot_state = {
            'is_connected': False,
            'battery_level': 100.0,
            'is_moving': False,
            'current_posture': 'unknown',
            'position': (0.0, 0.0, 0.0),
            'orientation': (0.0, 0.0, 0.0, 1.0),
        }

    @abstractmethod
    def initialize(self) -> bool:
        """
        Initialize the robot connection and setup.

        Returns:
            True if initialization successful, False otherwise
        """
        pass

    @abstractmethod
    def shutdown(self) -> bool:
        """
        Shutdown the robot connection gracefully.

        Returns:
            True if shutdown successful, False otherwise
        """
        pass

    @abstractmethod
    def execute_locomotion_intent(self, intent: LocomotionIntent) -> bool:
        """
        Execute a locomotion intent.

        Args:
            intent: Locomotion intent to execute

        Returns:
            True if execution successful, False otherwise
        """
        pass

    @abstractmethod
    def execute_posture_intent(self, intent: PostureIntent) -> bool:
        """
        Execute a posture intent.

        Args:
            intent: Posture intent to execute

        Returns:
            True if execution successful, False otherwise
        """
        pass

    @abstractmethod
    def execute_gesture_intent(self, intent: GestureIntent) -> bool:
        """
        Execute a gesture intent.

        Args:
            intent: Gesture intent to execute

        Returns:
            True if execution successful, False otherwise
        """
        pass

    @abstractmethod
    def execute_task_intent(self, intent: TaskIntent) -> bool:
        """
        Execute a task intent.

        Args:
            intent: Task intent to execute

        Returns:
            True if execution successful, False otherwise
        """
        pass

    @abstractmethod
    def handle_emergency_intent(self, intent: EmergencyIntent) -> bool:
        """
        Handle an emergency intent (usually involves stopping all motion).

        Args:
            intent: Emergency intent to handle

        Returns:
            True if handled successfully, False otherwise
        """
        pass

    @abstractmethod
    def get_robot_state(self) -> Dict[str, Any]:
        """
        Get current robot state.

        Returns:
            Dictionary containing robot state information
        """
        pass

    def is_ready(self) -> bool:
        """Check if adapter is ready to execute intents."""
        return self._is_initialized and not self._emergency_stop

    def emergency_stop(self) -> bool:
        """Perform emergency stop of all robot motion."""
        self.logger.warning("🚨 EMERGENCY STOP ACTIVATED")
        self._emergency_stop = True
        return self._stop_all_motion()

    @abstractmethod
    def _stop_all_motion(self) -> bool:
        """
        Internal method to stop all robot motion.

        Returns:
            True if stop successful, False otherwise
        """
        pass

    def clear_emergency_stop(self) -> bool:
        """Clear emergency stop state (use with caution)."""
        self.logger.info("✅ Emergency stop cleared")
        self._emergency_stop = False
        return True


class AdapterFactory:
    """Factory for creating humanoid adapters."""

    _adapters = {}

    @classmethod
    def register_adapter(cls, adapter_type: str, adapter_class):
        """Register an adapter class."""
        cls._adapters[adapter_type] = adapter_class

    @classmethod
    def create_adapter(cls, adapter_type: str, node: Node, config: Dict[str, Any]) -> HumanoidAdapter:
        """Create an adapter instance."""
        if adapter_type not in cls._adapters:
            raise ValueError(f"Unknown adapter type: {adapter_type}")

        adapter_class = cls._adapters[adapter_type]
        return adapter_class(node, config)

    @classmethod
    def get_available_adapters(cls) -> list:
        """Get list of available adapter types."""
        return list(cls._adapters.keys())


# Register default adapters
def register_default_adapters():
    """Register the default adapters."""
    try:
        from .adapters.unitree_g1_adapter import UnitreeG1Adapter
        AdapterFactory.register_adapter('unitree_g1', UnitreeG1Adapter)
    except ImportError:
        pass  # Unitree G1 adapter may not be available


# Auto-register adapters when module is imported
register_default_adapters()
