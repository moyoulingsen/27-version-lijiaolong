cmake_minimum_required(VERSION 3.8)
project(rm_decision_sim)

find_package(ament_cmake REQUIRED)

install(PROGRAMS
  scripts/generate_map.py
  scripts/nav_goal_adapter.py
  scripts/rm_map_simulator.py
  DESTINATION lib/${PROJECT_NAME}
)

install(FILES
  scripts/arena_data.py
  DESTINATION lib/${PROJECT_NAME}
)

install(DIRECTORY
  config
  launch
  maps
  models
  rviz
  worlds
  DESTINATION share/${PROJECT_NAME}
)

ament_package()
