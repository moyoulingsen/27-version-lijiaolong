from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    share = Path(get_package_share_directory("decision_process"))
    parameters = share / "config" / "communication.yaml"
    return LaunchDescription(
        [
            Node(
                package="decision_process",
                executable="decision_process",
                name="decision_process",
                output="screen",
                parameters=[str(parameters)],
            ),
            Node(
                package="decision_process",
                executable="pygame_ros_bridge.py",
                name="pygame_ros_bridge",
                output="screen",
            ),
        ]
    )
