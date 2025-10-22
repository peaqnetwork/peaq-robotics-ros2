"""
peaq ROS 2 Humanoids Package

Humanoid bridge for peaq blockchain integration providing:
- Blockchain intent to ROS topic/command translation
- Pluggable adapter system for different humanoid robots
- Unitree G1 adapter implementation
- Intent validation and execution framework
- Emergency stop and safety features
"""

from .common import HumanoidAdapter, AdapterFactory
from .intents import (
    IntentBase, IntentMessage, LocomotionIntent, PostureIntent,
    GestureIntent, TaskIntent, EmergencyIntent, MotionType,
    GestureType, PostureType, parse_intent_from_json, serialize_intent
)
from .humanoid_bridge_node import HumanoidBridgeNode
from .adapters.unitree_g1_adapter import UnitreeG1Adapter

__all__ = [
    "HumanoidAdapter",
    "AdapterFactory",
    "IntentBase",
    "IntentMessage",
    "LocomotionIntent",
    "PostureIntent",
    "GestureIntent",
    "TaskIntent",
    "EmergencyIntent",
    "MotionType",
    "GestureType",
    "PostureType",
    "parse_intent_from_json",
    "serialize_intent",
    "HumanoidBridgeNode",
    "UnitreeG1Adapter",
]
