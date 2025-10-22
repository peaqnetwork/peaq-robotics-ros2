#!/usr/bin/env python3
"""
Example script to emit robot intents using peaq ROS 2 event publishing.

This script demonstrates how to create and publish robot intents that
can be consumed by the humanoid bridge for execution.
"""
import sys
import rclpy
from rclpy.node import Node
import json

# Import custom interfaces
from peaq_ros2_interfaces.msg import Event

# Import intent models
from peaq_ros2_humanoids.intents import (
    IntentMessage, LocomotionIntent, PostureIntent, GestureIntent,
    MotionType, PostureType, GestureType, serialize_intent
)


class IntentEmitter(Node):
    """ROS 2 node for emitting robot intents."""

    def __init__(self):
        super().__init__('intent_emitter')

        # Create publisher for events
        self.events_publisher = self.create_publisher(
            Event,
            'peaq/events',
            10
        )

        self.get_logger().info('Intent emitter ready')

    def emit_intent(self, intent_message: IntentMessage):
        """Emit an intent as a blockchain event."""
        try:
            # Serialize intent to JSON
            payload_json = serialize_intent(intent_message)

            # Create event message
            event_msg = Event()
            event_msg.source = intent_message.source
            event_msg.type = f"intent_{intent_message.intent.intent_type}"
            event_msg.payload_json = payload_json

            # Publish event
            self.events_publisher.publish(event_msg)

            self.get_logger().info(f'📡 Emitted {intent_message.intent.intent_type} intent from {intent_message.source}')
            return True

        except Exception as e:
            self.get_logger().error(f'Failed to emit intent: {str(e)}')
            return False

    def emit_locomotion_intent(self, motion_type: str, velocity_x: float = 0.0,
                              velocity_y: float = 0.0, velocity_z: float = 0.0,
                              source: str = "operator"):
        """Emit a locomotion intent."""
        try:
            intent = LocomotionIntent(
                intent_type="locomotion",
                motion_type=MotionType(motion_type),
                velocity_x=velocity_x,
                velocity_y=velocity_y,
                velocity_z=velocity_z,
                priority=5
            )

            intent_message = IntentMessage(
                intent=intent,
                source=source
            )

            return self.emit_intent(intent_message)

        except Exception as e:
            self.get_logger().error(f'Failed to create locomotion intent: {str(e)}')
            return False

    def emit_posture_intent(self, posture_type: str, source: str = "operator"):
        """Emit a posture intent."""
        try:
            intent = PostureIntent(
                intent_type="posture",
                posture_type=PostureType(posture_type),
                transition_time=2.0,
                priority=3
            )

            intent_message = IntentMessage(
                intent=intent,
                source=source
            )

            return self.emit_intent(intent_message)

        except Exception as e:
            self.get_logger().error(f'Failed to create posture intent: {str(e)}')
            return False

    def emit_gesture_intent(self, gesture_type: str, speed: float = 1.0,
                           repetitions: int = 1, source: str = "operator"):
        """Emit a gesture intent."""
        try:
            intent = GestureIntent(
                intent_type="gesture",
                gesture_type=GestureType(gesture_type),
                speed=speed,
                amplitude=1.0,
                repetitions=repetitions,
                priority=2
            )

            intent_message = IntentMessage(
                intent=intent,
                source=source
            )

            return self.emit_intent(intent_message)

        except Exception as e:
            self.get_logger().error(f'Failed to create gesture intent: {str(e)}')
            return False


def main(args=None):
    """Main function."""
    rclpy.init(args=args)

    # Create emitter node
    emitter = IntentEmitter()

    print("🤖 peaq ROS 2 Intent Emitter")
    print("=" * 40)
    print("Available intents:")
    print("1. Locomotion (move, walk, run, stop, turn, stand, sit)")
    print("2. Posture (stand_straight, stand_relaxed, sit_chair, kneel, crouch)")
    print("3. Gesture (wave, point, nod, shake_head, bow, dance)")
    print()

    try:
        while rclpy.ok():
            print("Choose intent type:")
            print("1. Locomotion")
            print("2. Posture")
            print("3. Gesture")
            print("q. Quit")
            print()

            choice = input("Enter choice: ").strip().lower()

            if choice == 'q':
                break

            if choice == '1':
                # Locomotion intent
                print("\nLocomotion Intent:")
                motion_type = input("Motion type (move/walk/run/stop/turn/stand/sit): ").strip()
                if motion_type not in ['move', 'walk', 'run', 'stop', 'turn', 'stand', 'sit']:
                    print("❌ Invalid motion type")
                    continue

                vx = float(input("Velocity X (m/s, -2.0 to 2.0): ") or 0)
                vy = float(input("Velocity Y (m/s, -2.0 to 2.0): ") or 0)
                vz = float(input("Angular velocity Z (rad/s, -3.0 to 3.0): ") or 0)

                success = emitter.emit_locomotion_intent(motion_type, vx, vy, vz)

            elif choice == '2':
                # Posture intent
                print("\nPosture Intent:")
                posture_types = ['stand_straight', 'stand_relaxed', 'sit_chair', 'sit_floor', 'kneel', 'crouch']
                for i, pt in enumerate(posture_types, 1):
                    print(f"{i}. {pt}")

                try:
                    choice = int(input("Choose posture (1-6): "))
                    if 1 <= choice <= len(posture_types):
                        posture_type = posture_types[choice - 1]
                        success = emitter.emit_posture_intent(posture_type)
                    else:
                        print("❌ Invalid choice")
                        continue
                except ValueError:
                    print("❌ Invalid input")
                    continue

            elif choice == '3':
                # Gesture intent
                print("\nGesture Intent:")
                gesture_types = ['wave', 'point', 'nod', 'shake_head', 'bow', 'dance']
                for i, gt in enumerate(gesture_types, 1):
                    print(f"{i}. {gt}")

                try:
                    choice = int(input("Choose gesture (1-6): "))
                    if 1 <= choice <= len(gesture_types):
                        gesture_type = gesture_types[choice - 1]
                        speed = float(input("Speed (0.1-3.0, default 1.0): ") or 1.0)
                        repetitions = int(input("Repetitions (1-10, default 1): ") or 1)

                        success = emitter.emit_gesture_intent(gesture_type, speed, repetitions)
                    else:
                        print("❌ Invalid choice")
                        continue
                except ValueError:
                    print("❌ Invalid input")
                    continue

            else:
                print("❌ Invalid choice")
                continue

            if success:
                print("✅ Intent emitted successfully!")
            else:
                print("❌ Failed to emit intent")
            print()

    except KeyboardInterrupt:
        print("\n👋 Shutting down...")
    finally:
        emitter.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
