"""
Launch file for E2E test with storage bridge
"""
from launch import LaunchDescription
from launch_ros.actions import Node
from launch.actions import DeclareLaunchArgument, TimerAction
from launch.substitutions import LaunchConfiguration
import os

def generate_launch_description():
    # Get paths
    pkg_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config_file = os.path.join(pkg_dir, 'config', 'e2e_test_bridge.yaml')
    wallet_file = os.path.join(os.path.dirname(pkg_dir), '..', '..', '.ros_e2e_wallet.json')
    
    # Declare arguments
    network_arg = DeclareLaunchArgument(
        'network',
        default_value='wss://wsspc1-qa.agung.peaq.network',
        description='Blockchain network URL'
    )
    
    mnemonic_arg = DeclareLaunchArgument(
        'mnemonic',
        default_value='april blade under child catch crane ritual mass rotate visa social truly',
        description='Wallet mnemonic'
    )
    
    # Core node
    core_node = Node(
        package='peaq_ros2_core',
        executable='core_node',
        name='peaq_core_node',
        output='screen',
        parameters=[{
            'network': LaunchConfiguration('network'),
            'mnemonic': LaunchConfiguration('mnemonic'),
        }]
    )
    
    # Storage bridge node (start after core node)
    bridge_node = TimerAction(
        period=3.0,
        actions=[
            Node(
                package='peaq_ros2_core',
                executable='storage_bridge_node',
                name='peaq_storage_bridge_node',
                output='screen',
                parameters=[{
                    'config.yaml_path': config_file,
                }]
            )
        ]
    )
    
    # Test node (start after bridge)
    test_node = TimerAction(
        period=6.0,
        actions=[
            Node(
                package='peaq_ros2_examples',
                executable='e2e_real_test.py',
                name='e2e_test_node',
                output='screen',
            )
        ]
    )
    
    return LaunchDescription([
        network_arg,
        mnemonic_arg,
        core_node,
        bridge_node,
        test_node,
    ])
