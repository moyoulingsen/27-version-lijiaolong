#include <memory>

#include "rclcpp/rclcpp.hpp"

#include "decision_process/decision_process_node.hpp"

int main(int argc, char * argv[])
{
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<decision_process::DecisionProcessNode>());
  rclcpp::shutdown();
  return 0;
}
