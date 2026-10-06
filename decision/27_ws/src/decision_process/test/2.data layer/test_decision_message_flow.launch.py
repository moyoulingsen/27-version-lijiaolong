import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, EmitEvent, OpaqueFunction, RegisterEventHandler
from launch.event_handlers import OnProcessExit
from launch.events import Shutdown
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


SCENARIOS = {
    "1": ("return_home", "return_home_input_publisher", 3),
    "return_home": ("return_home", "return_home_input_publisher", 3),
    "2": ("posture", "posture_input_publisher", 1),
    "posture": ("posture", "posture_input_publisher", 1),
    "3": ("attack_outpost", "attack_outpost_input_publisher", 3),
    "attack_outpost": ("attack_outpost", "attack_outpost_input_publisher", 3),
    "4": ("no_ammo", "no_ammo_input_publisher", 3),
    "no_ammo": ("no_ammo", "no_ammo_input_publisher", 3),
    "5": ("dodge", "dodge_input_publisher", 1),
    "dodge": ("dodge", "dodge_input_publisher", 1),
    "6": ("patrol", "patrol_input_publisher", 3),
    "patrol": ("patrol", "patrol_input_publisher", 3),
    "7": ("spin_control", "spin_control_input_publisher", 3),
    "spin_control": ("spin_control", "spin_control_input_publisher", 3),
    "8": ("gimbal_control", "gimbal_control_input_publisher", 1),
    "gimbal_control": ("gimbal_control", "gimbal_control_input_publisher", 1),
    "9": ("low_health_recovery", "low_health_recovery_input_publisher", 3),
    "low_health_recovery": ("low_health_recovery", "low_health_recovery_input_publisher", 3),
    "10": ("health_threshold_parameter", "health_threshold_parameter_input_publisher", 3),
    "health_threshold_parameter": ("health_threshold_parameter", "health_threshold_parameter_input_publisher", 3),
}


def build_scenario(context):
    requested = LaunchConfiguration("scenario").perform(context).strip().lower()
    if requested not in SCENARIOS:
        valid = ", ".join(["1..10", "return_home", "posture", "attack_outpost", "no_ammo", "dodge", "patrol", "spin_control", "gimbal_control", "low_health_recovery", "health_threshold_parameter"])
        raise RuntimeError(f"未知消息测试场景 '{requested}'，可用值：{valid}")

    scenario_name, input_executable, default_posture = SCENARIOS[requested]
    package_share = get_package_share_directory("decision_process")
    tree_name = "10_health_threshold_parameter.xml" if scenario_name == "health_threshold_parameter" else "decision_master.xml"
    production_tree = os.path.join(package_share, "behavior_trees", tree_name)

    decision_node = Node(
        package="decision_process", executable="decision_process",
        name="decision_process", output="screen",
        parameters=[{
            "behavior_tree_xml": production_tree,
            "publish_rate_hz": 10.0,
            "behavior_tree_tick_rate_hz": 10.0,
            "default_posture": default_posture,
        }],
    )
    input_publisher = Node(
        package="decision_process", executable=input_executable,
        name=input_executable, output="screen",
    )
    output_monitor = Node(
        package="decision_process", executable="decision_output_stream_monitor",
        name="decision_output_stream_monitor", output="screen",
    )
    stop_when_finished = RegisterEventHandler(
        OnProcessExit(
            target_action=input_publisher,
            on_exit=[EmitEvent(event=Shutdown(reason=f"消息测试 {scenario_name} 执行完成"))],
        )
    )
    return [decision_node, input_publisher, output_monitor, stop_when_finished]


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument("scenario", default_value="1"),
        OpaqueFunction(function=build_scenario),
    ])
