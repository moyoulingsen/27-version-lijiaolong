from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    package_share = Path(get_package_share_directory("decision_process"))
    parameter_file = package_share / "config" / "communication.yaml"

    return LaunchDescription(
        [
            Node(
                package="decision_process",
                executable="decision_process_node",
                name="decision_process",
                output="screen",
                parameters=[str(parameter_file)],
            )
        ]
    )
