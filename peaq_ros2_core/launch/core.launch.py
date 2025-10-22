"""
Launch file for peaq ROS 2 core nodes.

This launch file starts both the core node (providing blockchain services)
and the events node (streaming blockchain events) as composable nodes.
"""
import os
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory


def generate_launch_description():
    """Generate launch description for peaq ROS 2 core nodes."""

    # Declare launch arguments
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

    keystore_path_arg = DeclareLaunchArgument(
        'keystore_path',
        default_value=os.getenv('PEAQ_ROBOT_KEYSTORE', '~/.peaq_robot/wallet.json'),
        description='Path to keystore file'
    )

    keystore_password_env_arg = DeclareLaunchArgument(
        'keystore_password_env',
        default_value=os.getenv('PEAQ_ROBOT_KEY_PASSWORD_ENV', 'PEAQ_ROBOT_KEY_PASSWORD'),
        description='Environment variable name for keystore password'
    )

    events_enabled_arg = DeclareLaunchArgument(
        'events_enabled',
        default_value=os.getenv('PEAQ_ROBOT_EVENTS_ENABLED', 'true'),
        description='Enable blockchain event streaming'
    )

    log_level_arg = DeclareLaunchArgument(
        'log_level',
        default_value=os.getenv('PEAQ_ROBOT_LOG_LEVEL', 'INFO'),
        description='Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)'
    )

    log_format_arg = DeclareLaunchArgument(
        'log_format',
        default_value=os.getenv('PEAQ_ROBOT_LOG_FORMAT', 'human'),
        description='Log format (human or json)'
    )

    # Core node (Python entry point)
    core_node = Node(
        package='peaq_ros2_core',
        executable='core_node',
        name='peaq_core_node',
        output='screen',
        parameters=[
            {
                'network': LaunchConfiguration('network'),
                'default_confirmation_mode': LaunchConfiguration('confirmation_mode'),
                'keystore.path': LaunchConfiguration('keystore_path'),
                'keystore.password_env': LaunchConfiguration('keystore_password_env'),
                'events.enabled': LaunchConfiguration('events_enabled'),
                'log_level': LaunchConfiguration('log_level'),
                'log_format': LaunchConfiguration('log_format'),
            }
        ],
        arguments=['--ros-args', '--enable-rosout-logs'],
    )

    # Events node (Python entry point)
    events_node = Node(
        package='peaq_ros2_core',
        executable='events_node',
        name='peaq_events_node',
        output='screen',
        parameters=[
            {
                'network': LaunchConfiguration('network'),
                'default_confirmation_mode': LaunchConfiguration('confirmation_mode'),
                'keystore.path': LaunchConfiguration('keystore_path'),
                'keystore.password_env': LaunchConfiguration('keystore_password_env'),
                'events.enabled': LaunchConfiguration('events_enabled'),
                'log_level': LaunchConfiguration('log_level'),
                'log_format': LaunchConfiguration('log_format'),
            }
        ],
        arguments=['--ros-args', '--enable-rosout-logs'],
    )

    # Create launch description
    ld = LaunchDescription()

    # Add launch arguments
    ld.add_action(network_arg)
    ld.add_action(confirmation_mode_arg)
    ld.add_action(keystore_path_arg)
    ld.add_action(keystore_password_env_arg)
    ld.add_action(events_enabled_arg)
    ld.add_action(log_level_arg)
    ld.add_action(log_format_arg)

    # Add nodes
    ld.add_action(core_node)
    ld.add_action(events_node)

    return ld
