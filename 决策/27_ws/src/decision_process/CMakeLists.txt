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

install(TARGETS
  decision_process_node
  test_data_publisher
  output_monitor
  DESTINATION lib/${PROJECT_NAME}
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
  ament_add_gtest(test_return_home_logic test/test_return_home_logic.cpp)
  target_include_directories(test_return_home_logic PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    $<INSTALL_INTERFACE:include>
  )
  ament_add_gtest(test_posture_logic test/test_posture_logic.cpp)
  target_include_directories(test_posture_logic PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    $<INSTALL_INTERFACE:include>
  )
  ament_add_gtest(test_attack_outpost_logic test/test_attack_outpost_logic.cpp)
  target_include_directories(test_attack_outpost_logic PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    $<INSTALL_INTERFACE:include>
  )
  ament_add_gtest(test_ammo_reserve_logic test/test_ammo_reserve_logic.cpp)
  target_include_directories(test_ammo_reserve_logic PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    $<INSTALL_INTERFACE:include>
  )
endif()

ament_export_dependencies(rosidl_default_runtime)
ament_package()
