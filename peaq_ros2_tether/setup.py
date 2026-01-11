from setuptools import setup


package_name = 'peaq_ros2_tether'


setup(
    name=package_name,
    version='0.0.1',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/js', [
            'js/package.json',
            'js/peaq_tether_cli.mjs',
        ]),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='peaq',
    maintainer_email='dev@peaq.network',
    description='peaq ROS 2 integration with Tether WDK (EVM wallet + USDT operations) via Node.js subprocess.',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'tether_node = peaq_ros2_tether.tether_node:main',
        ],
    },
)

