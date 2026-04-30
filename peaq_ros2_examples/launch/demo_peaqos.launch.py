"""Launch file for peaqOS onboarding demo services."""

import os

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    config_yaml_arg = DeclareLaunchArgument(
        'config_yaml',
        default_value=os.getenv('PEAQ_ROS2_CONFIG_YAML', ''),
        description='Path to unified YAML config passed as config.yaml_path',
    )

    peaqos_node = Node(
        package='peaq_ros2_peaqos',
        executable='peaqos_node',
        name='peaqos_node',
        output='screen',
        parameters=[{
            'config.yaml_path': LaunchConfiguration('config_yaml'),
        }],
        arguments=['--ros-args', '--enable-rosout-logs'],
    )

    return LaunchDescription([config_yaml_arg, peaqos_node])
