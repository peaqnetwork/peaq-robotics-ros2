"""
Demo launch file for peaq ROS 2 humanoid bridge with Unitree G1.

This launch file demonstrates the complete humanoid integration by starting
both the core blockchain services and the humanoid bridge with Unitree G1 adapter.
"""
import os
from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription, DeclareLaunchArgument
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    """Generate launch description for peaq ROS 2 humanoid demo with Unitree G1."""

    # Declare launch arguments
    network_arg = DeclareLaunchArgument(
        'network',
        default_value=os.getenv('PEAQ_ROBOT_NETWORK', 'agung'),
        description='Blockchain network'
    )

    adapter_arg = DeclareLaunchArgument(
        'adapter',
        default_value=os.getenv('PEAQ_ROBOT_HUMANOID_ADAPTER', 'unitree_g1'),
        description='Humanoid adapter type'
    )

    adapter_config_arg = DeclareLaunchArgument(
        'adapter_config',
        default_value=os.getenv('PEAQ_ROBOT_ADAPTER_CONFIG',
                               '{"max_linear_velocity": 1.0, "max_angular_velocity": 2.0, "motion_timeout": 5.0}'),
        description='JSON configuration for the adapter'
    )

    # Include core launch
    core_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource([
            FindPackageShare('peaq_ros2_core'), '/launch/core.launch.py'
        ]),
        launch_arguments={
            'network': LaunchConfiguration('network'),
            'events_enabled': 'true',
        }.items()
    )

    # Include humanoid bridge launch
    humanoid_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource([
            FindPackageShare('peaq_ros2_humanoids'), '/launch/humanoid_bridge.launch.py'
        ]),
        launch_arguments={
            'adapter': LaunchConfiguration('adapter'),
            'adapter_config': LaunchConfiguration('adapter_config'),
        }.items()
    )

    # Create launch description
    ld = LaunchDescription()

    # Add launch arguments
    ld.add_action(network_arg)
    ld.add_action(adapter_arg)
    ld.add_action(adapter_config_arg)

    # Add launches
    ld.add_action(core_launch)
    ld.add_action(humanoid_launch)

    return ld
