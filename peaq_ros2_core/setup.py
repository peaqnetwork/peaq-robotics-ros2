from setuptools import find_packages, setup
import os
from glob import glob

package_name = 'peaq_ros2_core'

setup(
    name=package_name,
    version='1.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'launch'), glob(os.path.join('launch', '*.launch.py'))),
        (os.path.join('share', package_name, 'config'), glob(os.path.join('config', '*.yaml'))),
    ],
    install_requires=[
        'setuptools',
        'rclpy',
        'lifecycle',
        'peaq-robot-sdk>=1.0.0b1',
        'requests>=2.31.0',
        'PyNaCl>=1.5.0',
    ],
    zip_safe=True,
    maintainer='peaq robotics',
    maintainer_email='robotics@peaq.network',
    description='Core ROS 2 nodes for peaq blockchain integration',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'core_node = peaq_ros2_core.core_node:main',
            'events_node = peaq_ros2_core.events_node:main',
            'storage_bridge_node = peaq_ros2_core.storage_bridge_node:main',
        ],
    },
)
