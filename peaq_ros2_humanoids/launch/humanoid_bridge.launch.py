"""
Launch file for peaq ROS 2 humanoid bridge.

This launch file starts the humanoid bridge node that listens for blockchain events
and executes robot intents using the configured adapter.
"""
import os
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.parameter_descriptions import ParameterValue
from launch_ros.actions import Node


def generate_launch_description():
    """Generate launch description for peaq ROS 2 humanoid bridge."""

    # Declare launch arguments
    adapter_arg = DeclareLaunchArgument(
        'adapter',
        default_value=os.getenv('PEAQ_ROBOT_HUMANOID_ADAPTER', 'unitree_g1'),
        description='Humanoid adapter type (unitree_g1, custom, etc.)'
    )

    adapter_config_arg = DeclareLaunchArgument(
        'adapter_config',
        default_value=os.getenv('PEAQ_ROBOT_ADAPTER_CONFIG', '{}'),
        description='JSON configuration for the adapter'
    )

    ros_only_mode_arg = DeclareLaunchArgument(
        'ros_only_mode',
        default_value=os.getenv('PEAQ_ROBOT_ROS_ONLY_MODE', 'false'),
        description='Run in ROS-only mode (no blockchain connection)'
    )

    # Create humanoid bridge node
    humanoid_bridge_node = Node(
        package='peaq_ros2_humanoids',
        executable='humanoid_bridge_node',
        name='peaq_humanoid_bridge_node',
        output='screen',
        parameters=[
            {
                'humanoids.adapter': LaunchConfiguration('adapter'),
                # Ensure adapter_config is treated as a string parameter
                'humanoids.adapter_config': ParameterValue(LaunchConfiguration('adapter_config'), value_type=str),
                'ros_only_mode': LaunchConfiguration('ros_only_mode'),
            }
        ],
        # Add lifecycle management
        arguments=['--ros-args', '--enable-rosout-logs'],
    )

    # Create launch description
    ld = LaunchDescription()

    # Add launch arguments
    ld.add_action(adapter_arg)
    ld.add_action(adapter_config_arg)
    ld.add_action(ros_only_mode_arg)

    # Add node
    ld.add_action(humanoid_bridge_node)

    return ld
