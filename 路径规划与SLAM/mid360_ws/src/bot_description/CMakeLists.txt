cmake_minimum_required(VERSION 3.8)
project(bot_description)

find_package(ament_cmake REQUIRED)

install(
  DIRECTORY urdf meshes scan_mode launch worlds rviz
  DESTINATION share/${PROJECT_NAME}
)

ament_package()
