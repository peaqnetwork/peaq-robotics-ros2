from glob import glob
import os

from setuptools import find_packages, setup


package_name = 'peaq_ros2_stream'


setup(
    name=package_name,
    version='0.0.1',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', [os.path.join('resource', package_name)]),
        (os.path.join('share', package_name), ['package.xml']),
        (os.path.join('share', package_name, 'launch'), glob(os.path.join('launch', '*.launch.py'))),
    ],
    install_requires=[
        'setuptools',
        'PyNaCl>=1.5.0',
        'PyYAML>=6.0',
        'requests>=2.31.0',
    ],
    zip_safe=True,
    maintainer='peaq robotics',
    maintainer_email='robotics@peaq.network',
    description='peaqOS Stream agent for signed ROS 2 topic receipts.',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'stream_agent_node = peaq_ros2_stream.stream_agent_node:main',
        ],
    },
)
