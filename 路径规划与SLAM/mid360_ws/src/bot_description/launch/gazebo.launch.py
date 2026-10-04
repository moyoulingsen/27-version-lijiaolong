#!/usr/bin/env python3

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, TimerAction
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import Command, FindExecutable, LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    package_share = get_package_share_directory('bot_description')
    robot_xacro = os.path.join(package_share, 'urdf', 'robot.urdf.xacro')

    world = LaunchConfiguration('world')
    gui = LaunchConfiguration('gui')
    use_sim_time = LaunchConfiguration('use_sim_time')
    x = LaunchConfiguration('x')
    y = LaunchConfiguration('y')
    z = LaunchConfiguration('z')

    robot_description = Command([
        FindExecutable(name='xacro'),
        ' ',
        robot_xacro,
        ' camera_topic:=', LaunchConfiguration('camera_topic'),
        ' camera_info_topic:=', LaunchConfiguration('camera_info_topic'),
        ' mid360_topic:=', LaunchConfiguration('mid360_topic'),
        ' laser_topic:=', LaunchConfiguration('laser_topic'),
    ])

    gazebo = IncludeLaunchDescription(
        PythonLaunchDescriptionSource([
            FindPackageShare('gazebo_ros'),
            '/launch/gazebo.launch.py',
        ]),
        launch_arguments={
            'world': world,
            'gui': gui,
            'verbose': 'true',
        }.items(),
    )

    state_publisher = Node(
        package='robot_state_publisher',
        executable='robot_state_publisher',
        name='robot_state_publisher',
        output='screen',
        parameters=[
            {'robot_description': robot_description},
            {'use_sim_time': use_sim_time},
        ],
    )

    spawn_robot = Node(
        package='gazebo_ros',
        executable='spawn_entity.py',
        name='spawn_bot_description',
        output='screen',
        arguments=[
            '-entity', 'mid360_robot',
            '-topic', 'robot_description',
            '-x', x,
            '-y', y,
            '-z', z,
        ],
    )

    return LaunchDescription([
        DeclareLaunchArgument(
            'world',
            default_value=PathJoinSubstitution([
                FindPackageShare('bot_description'), 'worlds', 'mid360_demo.world'
            ]),
            description='Gazebo world file.',
        ),
        DeclareLaunchArgument('gui', default_value='true', description='Start Gazebo GUI.'),
        DeclareLaunchArgument('use_sim_time', default_value='true'),
        DeclareLaunchArgument('x', default_value='0.0'),
        DeclareLaunchArgument('y', default_value='0.0'),
        DeclareLaunchArgument('z', default_value='0.20'),
        DeclareLaunchArgument('camera_topic', default_value='/camera/image_raw'),
        DeclareLaunchArgument('camera_info_topic', default_value='/camera/camera_info'),
        DeclareLaunchArgument('mid360_topic', default_value='/mid360_points'),
        DeclareLaunchArgument('laser_topic', default_value='/laser_points'),
        gazebo,
        state_publisher,
        # Give gzserver time to load libgazebo_ros_factory before spawning. 
        TimerAction(period=3.0, actions=[spawn_robot]),
    ])
