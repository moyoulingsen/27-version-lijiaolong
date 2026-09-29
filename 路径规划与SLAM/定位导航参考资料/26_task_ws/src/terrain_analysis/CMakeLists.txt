cmake_minimum_required(VERSION 3.8)
project(terrain_analysis)

cmake_policy(SET CMP0074 NEW)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

# Find ROS2 and external dependencies
find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(std_msgs REQUIRED)
find_package(sensor_msgs REQUIRED)
find_package(nav_msgs REQUIRED)
find_package(message_filters REQUIRED)
find_package(tf2_ros REQUIRED)
find_package(tf2 REQUIRED)
find_package(tf2_sensor_msgs REQUIRED)
find_package(pcl_conversions REQUIRED)
find_package(pcl_ros REQUIRED)

find_package(PCL REQUIRED)
find_package(OpenCV REQUIRED)

# Declare executables
add_executable(terrainAnalysis src/terrainAnalysis.cpp)

# Link dependencies to the executable
ament_target_dependencies(terrainAnalysis
  rclcpp
  std_msgs
  sensor_msgs
  nav_msgs
  message_filters
  tf2_ros
  tf2
  tf2_sensor_msgs
  pcl_conversions
  pcl_ros
)
target_link_libraries(terrainAnalysis ${PCL_LIBRARIES} ${OpenCV_LIBRARIES})


# Install the executable and launch files
install(TARGETS
  terrainAnalysis
  DESTINATION lib/${PROJECT_NAME})


install(DIRECTORY launch 
  DESTINATION share/${PROJECT_NAME}
)

ament_package()