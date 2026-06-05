from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    config_yaml = LaunchConfiguration('config_yaml')
    return LaunchDescription(
        [
            DeclareLaunchArgument('config_yaml', default_value=''),
            Node(
                package='peaq_ros2_stream',
                executable='stream_agent_node',
                name='stream_agent_node',
                output='screen',
                parameters=[{'config.yaml_path': config_yaml}],
            ),
        ]
    )
