cmake_minimum_required(VERSION 3.8)
project(decision_process)

if(NOT CMAKE_CXX_STANDARD)
  set(CMAKE_CXX_STANDARD 17)
endif()

if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

find_package(ament_cmake REQUIRED)
find_package(ament_index_cpp REQUIRED)
find_package(behaviortree_cpp REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(nav_msgs REQUIRED)
find_package(rclcpp REQUIRED)
find_package(rosidl_default_generators REQUIRED)
find_package(std_msgs REQUIRED)
find_package(tf2 REQUIRED)
find_package(tf2_ros REQUIRED)

rosidl_generate_interfaces(${PROJECT_NAME}
  "msg/ReceiveData.msg"
  "msg/DesicionSendData.msg"
  "msg/AutoaimToDecision.msg"
  "msg/DecisionToAutoaim.msg"
)

rosidl_get_typesupport_target(cpp_typesupport_target
  ${PROJECT_NAME} "rosidl_typesupport_cpp")

add_executable(decision_process_node
  src/decision_process_node.cpp
  behaviortree/cpp/aggressive_patrol_nodes.cpp
  behaviortree/cpp/attack_nodes.cpp
  behaviortree/cpp/bullet_nodes.cpp
  behaviortree/cpp/conservative_patrol_nodes.cpp
  behaviortree/cpp/patrol_nodes.cpp
  behaviortree/cpp/return_home_nodes.cpp
)
set_target_properties(decision_process_node PROPERTIES OUTPUT_NAME decision_process)
target_include_directories(decision_process_node PRIVATE
  ${CMAKE_CURRENT_SOURCE_DIR}/behaviortree/cpp
)
ament_target_dependencies(decision_process_node
  ament_index_cpp
  behaviortree_cpp
  geometry_msgs
  nav_msgs
  rclcpp
  std_msgs
  tf2
  tf2_ros
)
target_link_libraries(decision_process_node "${cpp_typesupport_target}")

install(TARGETS decision_process_node
  DESTINATION lib/${PROJECT_NAME}
)
install(PROGRAMS scripts/pygame_ros_bridge.py
  DESTINATION lib/${PROJECT_NAME}
)
install(DIRECTORY behaviortree/xml config launch
  DESTINATION share/${PROJECT_NAME}
)

ament_export_dependencies(rosidl_default_runtime)
ament_package()
