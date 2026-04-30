from setuptools import setup
import os

package_name = 'peaq_ros2_examples'

def _gather_files(rel_dir, exts=(".py", ".launch.py")):
    base = os.path.join(os.path.dirname(__file__), rel_dir)
    files = []
    if os.path.isdir(base):
        for f in os.listdir(base):
            if any(f.endswith(ext) for ext in exts):
                files.append(os.path.join(rel_dir, f))
    return files

launch_files = _gather_files('launch', ('.launch.py',))
script_files = [
    os.path.join('scripts', 'create_identity.py'),
    os.path.join('scripts', 'emit_intent.py'),
    os.path.join('scripts', 'send_store_add_data.py'),
    os.path.join('scripts', 'e2e_real_test.py'),
    os.path.join('scripts', 'peaqos_demo.py'),
]

setup(
    name=package_name,
    version='1.0.0',
    tests_require=['pytest'],
    packages=[package_name, package_name + '.scripts'],
    data_files=[
        ('share/ament_index/resource_index/packages', [os.path.join('resource', package_name)]),
        (os.path.join('share', package_name), ['package.xml']),
        (os.path.join('share', package_name, 'launch'), launch_files),
        (os.path.join('share', package_name, 'scripts'), script_files),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='peaq robotics',
    maintainer_email='robotics@peaq.network',
    description='Example launch files and demo scripts for peaq ROS 2 SDK',
    license='Apache-2.0',
    entry_points={
        'console_scripts': [
            'tether_demo = peaq_ros2_examples.scripts.tether_demo:main',
        ],
    },
)
