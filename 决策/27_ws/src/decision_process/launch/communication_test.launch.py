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
                parameters=[
                    str(parameter_file),
                    {
                        "publish_goal": True,
                        "goal_x": 1.0,
                        "goal_y": 1.0,
                        "goal_yaw": 0.5,
                        "default_posture": 1,
                        "default_confirm_respawn": 1,
                        "default_tripod_mode": 0,
                        "default_spin_mode": 3,
                        "default_shoot_mode": 1,
                        "default_target_color": 2,
                        "default_target_number": 8,
                        "default_decide_yaw": 0.75,
                    },
                ],
            ),
            Node(
                package="decision_process",
                executable="test_data_publisher",
                output="screen",
            ),
            Node(
                package="decision_process",
                executable="output_monitor",
                output="screen",
            ),
        ]
    )
