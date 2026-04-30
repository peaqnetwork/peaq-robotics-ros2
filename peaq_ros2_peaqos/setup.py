from setuptools import setup
import os
from glob import glob


package_name = 'peaq_ros2_peaqos'


setup(
    name=package_name,
    version='0.0.1',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml', 'README.md']),
        (os.path.join('share', package_name, 'launch'), glob(os.path.join('launch', '*.launch.py'))),
    ],
    install_requires=[
        'setuptools',
        'peaq-os-sdk>=0.0.2',
        'eth-account',
        'requests>=2.31.0',
    ],
    zip_safe=True,
    maintainer='peaq',
    maintainer_email='dev@peaq.network',
    description='peaqOS ROS 2 integration for machine onboarding, NFTs, DID attributes, events, MCR, and bridge flows.',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'peaqos_node = peaq_ros2_peaqos.peaqos_node:main',
        ],
    },
)
