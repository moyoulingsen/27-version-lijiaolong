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
find_package(rcl_interfaces REQUIRED)
find_package(rosidl_default_generators REQUIRED)

rosidl_generate_interfaces(${PROJECT_NAME}
  "msg/ReceiveData.msg"
  "msg/DesicionSendData.msg"
  "msg/AutoaimToDecision.msg"
  "msg/DecisionToAutoaim.msg"
)

rosidl_get_typesupport_target(cpp_typesupport_target
  ${PROJECT_NAME} "rosidl_typesupport_cpp")

add_executable(decision_process_node
  src/behavior_tree_nodes.cpp
  src/decision_process_main.cpp
  src/decision_process_node.cpp
)
set_target_properties(decision_process_node PROPERTIES
  OUTPUT_NAME decision_process
)
target_include_directories(decision_process_node PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>
)
ament_target_dependencies(decision_process_node
  ament_index_cpp
  behaviortree_cpp
  geometry_msgs
  nav_msgs
  rclcpp
  rcl_interfaces
)
target_link_libraries(decision_process_node "${cpp_typesupport_target}")

add_executable(test_data_publisher src/test_data_publisher.cpp)
ament_target_dependencies(test_data_publisher
  nav_msgs
  rclcpp
)
target_link_libraries(test_data_publisher "${cpp_typesupport_target}")

add_executable(output_monitor src/output_monitor.cpp)
ament_target_dependencies(output_monitor
  geometry_msgs
  rclcpp
)
target_link_libraries(output_monitor "${cpp_typesupport_target}")

add_executable(return_home_input_publisher
  "test/2.data layer/01_return_home/return_home_input_publisher.cpp"
)
ament_target_dependencies(return_home_input_publisher
  nav_msgs
  rclcpp
)
target_link_libraries(return_home_input_publisher "${cpp_typesupport_target}")

add_executable(decision_output_stream_monitor
  "test/2.data layer/common/decision_output_stream_monitor.cpp"
)
ament_target_dependencies(decision_output_stream_monitor
  geometry_msgs
  rclcpp
)
target_link_libraries(decision_output_stream_monitor "${cpp_typesupport_target}")

add_executable(posture_input_publisher
  "test/2.data layer/02_posture/posture_input_publisher.cpp"
)
ament_target_dependencies(posture_input_publisher nav_msgs rclcpp)
target_link_libraries(posture_input_publisher "${cpp_typesupport_target}")

add_executable(attack_outpost_input_publisher
  "test/2.data layer/03_attack_outpost/attack_outpost_input_publisher.cpp"
)
ament_target_dependencies(attack_outpost_input_publisher nav_msgs rclcpp)
target_link_libraries(attack_outpost_input_publisher "${cpp_typesupport_target}")

add_executable(no_ammo_input_publisher
  "test/2.data layer/04_no_ammo/no_ammo_input_publisher.cpp"
)
ament_target_dependencies(no_ammo_input_publisher nav_msgs rclcpp)
target_link_libraries(no_ammo_input_publisher "${cpp_typesupport_target}")

add_executable(dodge_input_publisher
  "test/2.data layer/05_dodge/dodge_input_publisher.cpp"
)
ament_target_dependencies(dodge_input_publisher nav_msgs rclcpp)
target_link_libraries(dodge_input_publisher "${cpp_typesupport_target}")

add_executable(patrol_input_publisher
  "test/2.data layer/06_patrol/patrol_input_publisher.cpp"
)
ament_target_dependencies(patrol_input_publisher nav_msgs rclcpp)
target_link_libraries(patrol_input_publisher "${cpp_typesupport_target}")

add_executable(spin_control_input_publisher
  "test/2.data layer/07_spin_control/spin_control_input_publisher.cpp"
)
ament_target_dependencies(spin_control_input_publisher nav_msgs rclcpp)
target_link_libraries(spin_control_input_publisher "${cpp_typesupport_target}")

add_executable(gimbal_control_input_publisher
  "test/2.data layer/08_gimbal_control/gimbal_control_input_publisher.cpp"
)
ament_target_dependencies(gimbal_control_input_publisher nav_msgs rclcpp)
target_link_libraries(gimbal_control_input_publisher "${cpp_typesupport_target}")

add_executable(low_health_recovery_input_publisher
  "test/2.data layer/09_low_health_recovery/low_health_recovery_input_publisher.cpp"
)
ament_target_dependencies(low_health_recovery_input_publisher nav_msgs rclcpp)
target_link_libraries(low_health_recovery_input_publisher "${cpp_typesupport_target}")

add_executable(health_threshold_parameter_input_publisher
  "test/2.data layer/10_health_threshold_parameter/health_threshold_parameter_input_publisher.cpp"
)
ament_target_dependencies(health_threshold_parameter_input_publisher nav_msgs rclcpp)
target_link_libraries(health_threshold_parameter_input_publisher "${cpp_typesupport_target}")

install(TARGETS
  decision_process_node
  test_data_publisher
  output_monitor
  return_home_input_publisher
  decision_output_stream_monitor
  posture_input_publisher
  attack_outpost_input_publisher
  no_ammo_input_publisher
  dodge_input_publisher
  patrol_input_publisher
  spin_control_input_publisher
  gimbal_control_input_publisher
  low_health_recovery_input_publisher
  health_threshold_parameter_input_publisher
  DESTINATION lib/${PROJECT_NAME}
)

install(FILES
  "test/2.data layer/test_decision_message_flow.launch.py"
  "test/2.data layer/01_return_home/test_return_home_message_flow.launch.py"
  "test/2.data layer/02_posture/test_posture_message_flow.launch.py"
  "test/2.data layer/03_attack_outpost/test_attack_outpost_message_flow.launch.py"
  "test/2.data layer/04_no_ammo/test_no_ammo_message_flow.launch.py"
  "test/2.data layer/05_dodge/test_dodge_message_flow.launch.py"
  "test/2.data layer/06_patrol/test_patrol_message_flow.launch.py"
  "test/2.data layer/07_spin_control/test_spin_control_message_flow.launch.py"
  "test/2.data layer/08_gimbal_control/test_gimbal_control_message_flow.launch.py"
  "test/2.data layer/09_low_health_recovery/test_low_health_recovery_message_flow.launch.py"
  "test/2.data layer/10_health_threshold_parameter/test_health_threshold_parameter_message_flow.launch.py"
  DESTINATION share/${PROJECT_NAME}/launch
)

install(DIRECTORY
  behavior_trees
  config
  docs
  launch
  DESTINATION share/${PROJECT_NAME}
)

install(DIRECTORY include/
  DESTINATION include
)

if(BUILD_TESTING)
  find_package(ament_cmake_gtest REQUIRED)
  ament_add_gtest(
    test_return_home_logic
    "test/1.logical layer/test_return_home_logic.cpp"
  )
  target_include_directories(test_return_home_logic PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    $<INSTALL_INTERFACE:include>
  )
  ament_add_gtest(
    test_posture_logic
    "test/1.logical layer/test_posture_logic.cpp"
  )
  target_include_directories(test_posture_logic PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    $<INSTALL_INTERFACE:include>
  )
  ament_add_gtest(
    test_attack_outpost_logic
    "test/1.logical layer/test_attack_outpost_logic.cpp"
  )
  target_include_directories(test_attack_outpost_logic PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    $<INSTALL_INTERFACE:include>
  )
  ament_add_gtest(
    test_ammo_reserve_logic
    "test/1.logical layer/test_ammo_reserve_logic.cpp"
  )
  target_include_directories(test_ammo_reserve_logic PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    $<INSTALL_INTERFACE:include>
  )
  ament_add_gtest(
    test_dodge_logic
    "test/1.logical layer/test_dodge_logic.cpp"
  )
  target_include_directories(test_dodge_logic PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    $<INSTALL_INTERFACE:include>
  )
  ament_add_gtest(
    test_patrol_logic
    "test/1.logical layer/test_patrol_logic.cpp"
  )
  target_include_directories(test_patrol_logic PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    $<INSTALL_INTERFACE:include>
  )
  ament_add_gtest(
    test_spin_control_logic
    "test/1.logical layer/test_spin_control_logic.cpp"
  )
  target_include_directories(test_spin_control_logic PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    $<INSTALL_INTERFACE:include>
  )
  ament_add_gtest(
    test_gimbal_control_logic
    "test/1.logical layer/test_gimbal_control_logic.cpp"
  )
  target_include_directories(test_gimbal_control_logic PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    $<INSTALL_INTERFACE:include>
  )
  ament_add_gtest(
    test_health_recovery_logic
    "test/1.logical layer/test_health_recovery_logic.cpp"
  )
  target_include_directories(test_health_recovery_logic PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    $<INSTALL_INTERFACE:include>
  )
  ament_add_gtest(
    test_health_threshold_parameter
    "test/1.logical layer/test_health_threshold_parameter.cpp"
  )
  target_include_directories(test_health_threshold_parameter PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    $<INSTALL_INTERFACE:include>
  )
endif()

ament_export_dependencies(rosidl_default_runtime)
ament_package()
