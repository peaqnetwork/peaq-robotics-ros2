"""
Pydantic models for robot motion and behavior intents.

These models define the structure of intents that can be sent to humanoid robots
via blockchain events or triggers, providing a standardized interface for robot control.
"""
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, validator
from enum import Enum


class MotionType(str, Enum):
    """Types of motion intents."""
    MOVE = "move"
    WALK = "walk"
    RUN = "run"
    STOP = "stop"
    TURN = "turn"
    STAND = "stand"
    SIT = "sit"
    GESTURE = "gesture"


class GestureType(str, Enum):
    """Types of gestures."""
    WAVE = "wave"
    POINT = "point"
    NOD = "nod"
    SHAKE_HEAD = "shake_head"
    BOW = "bow"
    DANCE = "dance"


class PostureType(str, Enum):
    """Robot posture presets."""
    STAND_STRAIGHT = "stand_straight"
    STAND_RELAXED = "stand_relaxed"
    SIT_CHAIR = "sit_chair"
    SIT_FLOOR = "sit_floor"
    KNEEL = "kneel"
    CROUCH = "crouch"


class IntentBase(BaseModel):
    """Base model for all intents."""
    intent_type: str = Field(..., description="Type of intent")
    timestamp: Optional[float] = Field(default=None, description="Unix timestamp when intent was created")
    priority: int = Field(default=1, ge=1, le=10, description="Priority level (1-10, higher = more important)")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class LocomotionIntent(IntentBase):
    """Intent for robot locomotion (movement)."""
    intent_type: str = "locomotion"

    motion_type: MotionType = Field(..., description="Type of motion to perform")
    velocity_x: float = Field(..., ge=-2.0, le=2.0, description="Velocity in x direction (m/s)")
    velocity_y: float = Field(default=0.0, ge=-2.0, le=2.0, description="Velocity in y direction (m/s)")
    velocity_z: float = Field(default=0.0, ge=-3.0, le=3.0, description="Angular velocity around z axis (rad/s)")

    # Optional parameters for advanced motion
    duration: Optional[float] = Field(default=None, gt=0, description="Duration of motion in seconds")
    gait_type: Optional[str] = Field(default=None, description="Specific gait pattern to use")
    step_length: Optional[float] = Field(default=None, gt=0, description="Step length in meters")
    step_height: Optional[float] = Field(default=None, gt=0, description="Step height in meters")

    @validator('motion_type')
    def validate_motion_type_for_velocities(cls, v, values):
        """Validate that velocities make sense for the motion type."""
        vx = values.get('velocity_x', 0)
        vy = values.get('velocity_y', 0)
        vz = values.get('velocity_z', 0)

        if v == MotionType.STOP:
            if any(abs(vel) > 0.01 for vel in [vx, vy, vz]):
                raise ValueError("STOP motion should have zero velocities")
        elif v == MotionType.STAND:
            if any(abs(vel) > 0.01 for vel in [vx, vy, vz]):
                raise ValueError("STAND motion should have zero velocities")
        elif v == MotionType.SIT:
            if any(abs(vel) > 0.01 for vel in [vx, vy, vz]):
                raise ValueError("SIT motion should have zero velocities")

        return v


class PostureIntent(IntentBase):
    """Intent for robot posture changes."""
    intent_type: str = "posture"

    posture_type: PostureType = Field(..., description="Target posture")
    transition_time: float = Field(default=2.0, gt=0, description="Time to transition to new posture (seconds)")
    hold_time: Optional[float] = Field(default=None, gt=0, description="Time to hold posture before next action")


class GestureIntent(IntentBase):
    """Intent for robot gestures."""
    intent_type: str = "gesture"

    gesture_type: GestureType = Field(..., description="Type of gesture to perform")
    speed: float = Field(default=1.0, gt=0, le=3.0, description="Speed multiplier for gesture")
    amplitude: float = Field(default=1.0, gt=0, le=2.0, description="Amplitude multiplier for gesture")
    repetitions: int = Field(default=1, ge=1, le=10, description="Number of times to repeat gesture")


class TaskIntent(IntentBase):
    """Intent for complex tasks or behaviors."""
    intent_type: str = "task"

    task_type: str = Field(..., description="Type of task to perform")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Task-specific parameters")
    expected_duration: Optional[float] = Field(default=None, gt=0, description="Expected duration in seconds")


class EmergencyIntent(IntentBase):
    """Intent for emergency situations."""
    intent_type: str = "emergency"

    emergency_type: str = Field(..., description="Type of emergency")
    severity: int = Field(default=5, ge=1, le=10, description="Severity level (1-10)")
    action: str = Field(..., description="Emergency action to take")
    message: Optional[str] = Field(default=None, description="Human-readable emergency message")


class IntentMessage(BaseModel):
    """Wrapper for intent messages with validation."""
    intent: IntentBase = Field(..., description="The intent payload")
    source: str = Field(..., description="Source of the intent (e.g., 'blockchain', 'operator')")
    destination: Optional[str] = Field(default=None, description="Specific robot or component destination")

    class Config:
        """Pydantic configuration."""
        json_encoders = {
            IntentBase: lambda v: v.dict()
        }


def parse_intent_from_json(json_data: str) -> IntentMessage:
    """Parse intent from JSON string."""
    try:
        data = json.loads(json_data)
        return IntentMessage(**data)
    except Exception as e:
        raise ValueError(f"Failed to parse intent JSON: {str(e)}")


def serialize_intent(intent_message: IntentMessage) -> str:
    """Serialize intent message to JSON string."""
    # Pydantic v2: use model_dump + json.dumps for pretty output
    import json
    return json.dumps(intent_message.model_dump(), indent=2)
