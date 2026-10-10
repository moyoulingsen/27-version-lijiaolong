from pathlib import Path

from ament_index_python.packages import get_package_share_directory, PackageNotFoundError
from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    IncludeLaunchDescription,
    OpaqueFunction,
    RegisterEventHandler,
    Shutdown,
    TimerAction,
)
from launch.conditions import IfCondition, UnlessCondition
from launch.event_handlers import OnProcessExit
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import Command, FindExecutable, LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


SCENARIO_TREE = {
    "return_home": "decision_master.xml",
    "posture": "decision_master.xml",
    "attack_outpost": "decision_master.xml",
    "no_ammo": "decision_master.xml",
    "dodge": "decision_master.xml",
}
SCENARIO_START = {
    "return_home": (14.0, 4.0, 0.0),
    "posture": (4.971, 7.5, 0.0),
    "attack_outpost": (4.971, 7.5, 0.0),
    "no_ammo": (10.0, 4.0, 0.0),
    "dodge": (4.0, 5.0, 0.0),
}


def _launch_setup(context):
    scenario = LaunchConfiguration("scenario").perform(context)
    if scenario not in SCENARIO_TREE:
        raise RuntimeError(f"Unknown scenario '{scenario}', choose one of {tuple(SCENARIO_TREE)}")
    try:
        get_package_share_directory("nav2_controller")
        get_package_share_directory("nav2_navfn_planner")
    except PackageNotFoundError as error:
        raise RuntimeError(
            "Nav2 is required but not installed. Run: "
            "sudo apt install ros-jazzy-navigation2 ros-jazzy-nav2-bringup"
        ) from error

    package_share = Path(get_package_share_directory("rm_decision_sim"))
    decision_share = Path(get_package_share_directory("decision_process"))
    ros_gz_share = Path(get_package_share_directory("ros_gz_sim"))
    start_x, start_y, start_yaw = SCENARIO_START[scenario]
    world = package_share / "worlds/rm_arena.sdf"
    robot = package_share / "models/sentry.urdf.xacro"
    robot_description = ParameterValue(
        Command([FindExecutable(name="xacro"), " ", str(robot)]), value_type=str
    )

    gazebo_gui = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(str(ros_gz_share / "launch/gz_sim.launch.py")),
        launch_arguments={"gz_args": f"-r -v 2 {world}"}.items(),
        condition=IfCondition(LaunchConfiguration("gazebo_gui")),
    )
    gazebo_headless = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(str(ros_gz_share / "launch/gz_sim.launch.py")),
        launch_arguments={"gz_args": f"-s -r -v 2 {world}"}.items(),
        condition=UnlessCondition(LaunchConfiguration("gazebo_gui")),
    )
    state_publisher = Node(
        package="robot_state_publisher",
        executable="robot_state_publisher",
        output="screen",
        parameters=[{"use_sim_time": True, "robot_description": robot_description}],
    )
    spawn = Node(
        package="ros_gz_sim",
        executable="create",
        output="screen",
        arguments=[
            "-world", "rm_arena", "-name", "sentry", "-topic", "robot_description",
            "-x", str(start_x), "-y", str(start_y), "-z", "0.20", "-Y", str(start_yaw),
        ],
    )
    bridge = Node(
        package="ros_gz_bridge",
        executable="parameter_bridge",
        name="ros_gz_bridge",
        output="screen",
        parameters=[{"config_file": str(package_share / "config/bridge.yaml")}],
    )

    nav2 = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(str(package_share / "launch/nav2.launch.py")),
        launch_arguments={
            "params_file": str(package_share / "config/nav2_params.yaml"),
            "map": str(package_share / "maps/arena.yaml"),
        }.items(),
    )
    goal_adapter = Node(
        package="rm_decision_sim",
        executable="nav_goal_adapter.py",
        output="screen",
        parameters=[{"use_sim_time": True}],
    )
    scenario_driver = Node(
        package="rm_decision_sim",
        executable="rm_map_simulator.py",
        name="rm_decision_scenario",
        output="screen",
        parameters=[
            {
                "use_sim_time": True,
                "scenario": scenario,
                "dataset_path": LaunchConfiguration("dataset_path"),
                "game_id": ParameterValue(LaunchConfiguration("game_id"), value_type=int),
                "exit_on_result": ParameterValue(
                    LaunchConfiguration("exit_on_result"), value_type=bool
                ),
            }
        ],
    )
    decision = Node(
        package="decision_process",
        executable="decision_process",
        name="decision_process",
        output="screen",
        parameters=[
            str(decision_share / "config/communication.yaml"),
            {
                "use_sim_time": True,
                "behavior_tree_xml": str(
                    decision_share / "behavior_trees" / SCENARIO_TREE[scenario]
                ),
                "publish_goal": False,
                "default_posture": 1 if scenario == "posture" else 3,
                "default_tripod_mode": 1,
                "default_shoot_mode": 0,
            },
        ],
    )
    rviz = Node(
        package="rviz2",
        executable="rviz2",
        name="rviz2",
        output="screen",
        arguments=["-d", str(package_share / "rviz/rm_decision_sim.rviz")],
        parameters=[{"use_sim_time": True}],
        condition=IfCondition(LaunchConfiguration("rviz")),
    )
    shutdown_handler = RegisterEventHandler(
        OnProcessExit(
            target_action=scenario_driver,
            on_exit=[Shutdown(reason="scenario validator exited")],
        )
    )

    return [
        gazebo_gui,
        gazebo_headless,
        state_publisher,
        bridge,
        TimerAction(period=2.0, actions=[spawn]),
        TimerAction(period=4.0, actions=[nav2, goal_adapter]),
        TimerAction(period=5.0, actions=[scenario_driver, decision, rviz]),
        shutdown_handler,
    ]


def _default_dataset():
    source_candidate = Path(__file__).resolve().parents[2] / "data/rmuc_2026_region_dataset.sqlite"
    if source_candidate.is_file():
        return str(source_candidate)
    return str(Path(__file__).resolve().parents[1] / "config/dataset_snapshot.yaml")


def generate_launch_description():
    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "scenario",
                default_value="attack_outpost",
                description="return_home, posture, attack_outpost, no_ammo, or dodge",
            ),
            DeclareLaunchArgument("dataset_path", default_value=_default_dataset()),
            DeclareLaunchArgument("game_id", default_value="0"),
            DeclareLaunchArgument("gazebo_gui", default_value="true"),
            DeclareLaunchArgument("rviz", default_value="true"),
            DeclareLaunchArgument("exit_on_result", default_value="false"),
            OpaqueFunction(function=_launch_setup),
        ]
    )
