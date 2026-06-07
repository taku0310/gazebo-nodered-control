from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description() -> LaunchDescription:
    return LaunchDescription([
        Node(
            package='mqtt_ros2_bridge',
            executable='bridge_node',
            name='mqtt_ros2_bridge',
            output='screen',
            emulate_tty=True,
        ),
    ])
