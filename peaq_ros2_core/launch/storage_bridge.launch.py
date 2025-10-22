from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription([
        Node(
            package='peaq_ros2_core',
            executable='storage_bridge_node',
            name='peaq_storage_bridge_node',
            output='screen',
            parameters=[
                {'ipfs.api_url': 'http://127.0.0.1:5001'},
                {'ipfs.gateway_url': 'https://ipfs.io/ipfs'},
                {'pinning.provider': 'none'},
                {'pinning.pin': False},
                {'signature.algorithm': 'ed25519'},
                {'signature.private_key_hex': ''},
                {'robot.id': ''},
                {'core_node_name': 'peaq_core_node'},
            ],
        ),
    ])


