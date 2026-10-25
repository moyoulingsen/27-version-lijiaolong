from datetime import datetime
from os.path import expanduser
from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    share = Path(get_package_share_directory("decision_process"))
    parameters = share / "config" / "communication.yaml"
    default_bag_output = Path(expanduser("~/.ros/decision_bags")) / (
        "match_" + datetime.now().strftime("%Y%m%d_%H%M%S")
    )
    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "record_bag",
                default_value="true",
                description="Record decision inputs and outputs with rosbag2",
            ),
            DeclareLaunchArgument(
                "bag_output",
                default_value=str(default_bag_output),
                description="Output directory for the rosbag2 recording",
            ),
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
            ExecuteProcess(
                condition=IfCondition(LaunchConfiguration("record_bag")),
                cmd=[
                    "ros2",
                    "bag",
                    "record",
                    "-o",
                    LaunchConfiguration("bag_output"),
                    "--topics",
                    "/serial_receive_data",
                    "/autoaim_to_decision",
                    "/state_estimation",
                    "/tf",
                    "/tf_static",
                    "/serial_send_data",
                    "/decision_to_autoaim",
                    "/goal_pose",
                    "/decision_goal_enabled",
                ],
                output="screen",
            ),
        ]
    )
