import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import EmitEvent, RegisterEventHandler
from launch.event_handlers import OnProcessExit
from launch.events import Shutdown
from launch_ros.actions import Node


def generate_launch_description():
    package_share = get_package_share_directory("decision_process")
    production_tree = os.path.join(
        package_share, "behavior_trees", "decision_master.xml"
    )

    decision_node = Node(
        package="decision_process",
        executable="decision_process",
        name="decision_process",
        output="screen",
        parameters=[
            {
                "behavior_tree_xml": production_tree,
                "publish_rate_hz": 10.0,
                "behavior_tree_tick_rate_hz": 10.0,
            }
        ],
    )

    input_publisher = Node(
        package="decision_process",
        executable="return_home_input_publisher",
        name="return_home_input_publisher",
        output="screen",
    )

    output_monitor = Node(
        package="decision_process",
        executable="decision_output_stream_monitor",
        name="decision_output_stream_monitor",
        output="screen",
    )

    stop_launch_when_finished = RegisterEventHandler(
        OnProcessExit(
            target_action=input_publisher,
            on_exit=[
                EmitEvent(
                    event=Shutdown(reason="第一个回归消息流执行完成")
                )
            ],
        )
    )

    return LaunchDescription(
        [decision_node, input_publisher, output_monitor, stop_launch_when_finished]
    )
