from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription, TimerAction
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import Command, FindExecutable
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    package_share = Path(get_package_share_directory("rm_decision_sim"))
    ros_gz_share = Path(get_package_share_directory("ros_gz_sim"))
    world = package_share / "worlds/rm_arena.sdf"
    robot = package_share / "models/sentry.urdf.xacro"
    description = ParameterValue(
        Command([FindExecutable(name="xacro"), " ", str(robot)]), value_type=str
    )
    gazebo = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(str(ros_gz_share / "launch/gz_sim.launch.py")),
        launch_arguments={"gz_args": f"-r -v 2 {world}"}.items(),
    )
    state_publisher = Node(
        package="robot_state_publisher",
        executable="robot_state_publisher",
        parameters=[{"use_sim_time": True, "robot_description": description}],
    )
    spawn = Node(
        package="ros_gz_sim",
        executable="create",
        arguments=[
            "-world", "rm_arena", "-name", "sentry", "-topic", "robot_description",
            "-x", "4.971", "-y", "7.5", "-z", "0.20",
        ],
        output="screen",
    )
    bridge = Node(
        package="ros_gz_bridge",
        executable="parameter_bridge",
        parameters=[{"config_file": str(package_share / "config/bridge.yaml")}],
        output="screen",
    )
    return LaunchDescription([gazebo, state_publisher, bridge, TimerAction(period=2.0, actions=[spawn])])
