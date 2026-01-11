"""
Launch file for Tether WDK demo (peaq EVM USDT).

This starts:
- peaq_tether_node (ROS2 services wrapping Tether WDK via Node.js subprocess)

You should point it to the unified config YAML (peaq_robot.yaml / peaq_robot.example.yaml copy):
  ros2 launch peaq_ros2_examples demo_tether.launch.py config_yaml:=/work/peaq_ros2_examples/config/peaq_robot.yaml
"""

import os
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    config_yaml_arg = DeclareLaunchArgument(
        'config_yaml',
        default_value=os.getenv('PEAQ_ROS2_CONFIG_YAML', ''),
        description='Path to unified YAML config (passed as config.yaml_path)',
    )

    tether_node = Node(
        package='peaq_ros2_tether',
        executable='tether_node',
        name='peaq_tether_node',
        output='screen',
        parameters=[{
            'config.yaml_path': LaunchConfiguration('config_yaml'),
        }],
        arguments=['--ros-args', '--enable-rosout-logs'],
    )

    ld = LaunchDescription()
    ld.add_action(config_yaml_arg)
    ld.add_action(tether_node)
    return ld

