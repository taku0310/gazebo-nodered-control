"""Launch Gazebo Harmonic + ros_gz_bridge for the demo.

Starts ``gz sim`` against the bundled SDF world (Harmonic / SDF 1.10)
and a `ros_gz_bridge` parameter_bridge that wires the simulator's
``/cmd_vel`` and ``/odom`` gz transport topics to their ROS 2
equivalents, preserving the contract used by `mqtt_ros2_bridge`.
"""

import os

from launch import LaunchDescription
from launch.actions import ExecuteProcess
from launch_ros.actions import Node


def generate_launch_description() -> LaunchDescription:
    world_path = os.environ.get('WORLD_FILE', '/sim/worlds/diff_drive.sdf')
    bridge_config = os.environ.get('BRIDGE_CONFIG', '/sim/config/ros_gz_bridge.yaml')

    return LaunchDescription([
        ExecuteProcess(
            cmd=['gz', 'sim', '-r', '-v', '4', world_path],
            output='screen',
        ),
        Node(
            package='ros_gz_bridge',
            executable='parameter_bridge',
            name='ros_gz_bridge',
            arguments=['--ros-args', '-p', f'config_file:={bridge_config}'],
            output='screen',
        ),
    ])
