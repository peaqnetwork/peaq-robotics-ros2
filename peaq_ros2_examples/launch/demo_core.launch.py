"""
Demo launch file for peaq ROS 2 core functionality.

This launch file demonstrates the core blockchain integration features
by starting the core and events nodes together.
"""
import os
from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription, DeclareLaunchArgument
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    """Generate launch description for peaq ROS 2 core demo."""

    # Declare launch arguments with sensible defaults
    network_arg = DeclareLaunchArgument(
        'network',
        default_value=os.getenv('PEAQ_ROBOT_NETWORK', 'agung'),
        description='Blockchain network (agung, peaq, or custom WSS URL)'
    )

    confirmation_mode_arg = DeclareLaunchArgument(
        'confirmation_mode',
        default_value=os.getenv('PEAQ_ROBOT_CONFIRMATION_MODE', 'FAST'),
        description='Transaction confirmation mode (FAST or FINAL)'
    )

    events_enabled_arg = DeclareLaunchArgument(
        'events_enabled',
        default_value=os.getenv('PEAQ_ROBOT_EVENTS_ENABLED', 'true'),
        description='Enable blockchain event streaming'
    )

    log_level_arg = DeclareLaunchArgument(
        'log_level',
        default_value=os.getenv('PEAQ_ROBOT_LOG_LEVEL', 'INFO'),
        description='Logging level'
    )

    # Include the core launch file with our parameters
    core_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource([
            FindPackageShare('peaq_ros2_core'), '/launch/core.launch.py'
        ]),
        launch_arguments={
            'network': LaunchConfiguration('network'),
            'confirmation_mode': LaunchConfiguration('confirmation_mode'),
            'events_enabled': LaunchConfiguration('events_enabled'),
            'log_level': LaunchConfiguration('log_level'),
        }.items()
    )

    # Create launch description
    ld = LaunchDescription()

    # Add launch arguments
    ld.add_action(network_arg)
    ld.add_action(confirmation_mode_arg)
    ld.add_action(events_enabled_arg)
    ld.add_action(log_level_arg)

    # Add core launch
    ld.add_action(core_launch)

    return ld
