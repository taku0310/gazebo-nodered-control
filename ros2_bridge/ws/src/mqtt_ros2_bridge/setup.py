from setuptools import setup

package_name = 'mqtt_ros2_bridge'

setup(
    name=package_name,
    version='0.1.0',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/launch', ['launch/bridge.launch.py']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='demo',
    maintainer_email='dev@example.com',
    description='MQTT to ROS 2 bridge for diff-drive cmd_vel control.',
    license='Apache-2.0',
    entry_points={
        'console_scripts': [
            'bridge_node = mqtt_ros2_bridge.bridge_node:main',
        ],
    },
)
