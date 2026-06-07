"""Launch Gazebo Fortress + ros_gz_bridge for the demo.

Starts ``ign gazebo`` against the bundled SDF world (Fortress / SDF 1.9)
and a `ros_gz_bridge` parameter_bridge that wires the simulator's
``/cmd_vel`` and ``/odom`` gz transport topics to their ROS 2
equivalents, preserving the contract used by `mqtt_ros2_bridge`.

Fortress (Gazebo Sim 6.x) is the officially supported "new Gazebo"
for ROS 2 Humble. The visual experience matches Harmonic; only the
plugin namespace (``ignition::gazebo::*``) and message type names
(``ignition.msgs.*``) differ.
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
            cmd=['ign', 'gazebo', '-r', '-v', '4', world_path],
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
