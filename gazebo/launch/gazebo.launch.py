"""Launch Gazebo Classic with the demo diff-drive world.

Honors the ``GAZEBO_HEADLESS`` environment variable: when set to ``1``
(or ``true``), only ``gzserver`` runs — useful inside CI or containers
without X11. Otherwise both ``gzserver`` and ``gzclient`` start.
"""

import os

from launch import LaunchDescription
from launch.actions import ExecuteProcess


def _truthy(value: str) -> bool:
    return value.lower() in ('1', 'true', 'yes', 'on')


def generate_launch_description() -> LaunchDescription:
    world_path = os.environ.get('WORLD_FILE', '/sim/worlds/diff_drive.world')
    headless = _truthy(os.environ.get('GAZEBO_HEADLESS', '1'))

    actions = [
        ExecuteProcess(
            cmd=[
                'gzserver',
                '--verbose',
                '-s', 'libgazebo_ros_init.so',
                '-s', 'libgazebo_ros_factory.so',
                world_path,
            ],
            output='screen',
        ),
    ]

    if not headless:
        actions.append(ExecuteProcess(cmd=['gzclient', '--verbose'], output='screen'))

    return LaunchDescription(actions)
