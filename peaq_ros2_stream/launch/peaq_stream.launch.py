"""Launch peaqOS services and the Stream agent together."""

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

    config_yaml = LaunchConfiguration('config_yaml')

    peaqos_node = Node(
        package='peaq_ros2_peaqos',
        executable='peaqos_node',
        name='peaqos_node',
        output='screen',
        parameters=[{'config.yaml_path': config_yaml}],
        arguments=['--ros-args', '--enable-rosout-logs'],
    )

    stream_agent_node = Node(
        package='peaq_ros2_stream',
        executable='stream_agent_node',
        name='stream_agent_node',
        output='screen',
        parameters=[{'config.yaml_path': config_yaml}],
        arguments=['--ros-args', '--enable-rosout-logs'],
    )

    return LaunchDescription([config_yaml_arg, peaqos_node, stream_agent_node])
