#ifndef DECISION_PROCESS__DECISION_PROCESS_NODE_HPP_
#define DECISION_PROCESS__DECISION_PROCESS_NODE_HPP_

#include <chrono>
#include <cstdint>
#include <memory>
#include <mutex>
#include <string>
#include <vector>

#include "behaviortree_cpp/bt_factory.h"
#include "geometry_msgs/msg/pose_stamped.hpp"
#include "nav_msgs/msg/odometry.hpp"
#include "rcl_interfaces/msg/set_parameters_result.hpp"
#include "rclcpp/rclcpp.hpp"

#include "decision_process/ammo_reserve_logic.hpp"
#include "decision_process/communication_data.hpp"
#include "decision_process/dodge_logic.hpp"
#include "decision_process/msg/autoaim_to_decision.hpp"
#include "decision_process/msg/decision_to_autoaim.hpp"
#include "decision_process/msg/desicion_send_data.hpp"
#include "decision_process/msg/receive_data.hpp"
#include "decision_process/return_home_logic.hpp"

namespace decision_process
{

class DecisionProcessNode : public rclcpp::Node
{
public:
  DecisionProcessNode();

  RefereeState getRefereeState() const;
  AutoaimState getAutoaimState() const;
  LocalizationState getLocalizationState() const;
  SerialCommand getSerialCommand() const;
  AutoaimCommand getAutoaimCommand() const;
  NavigationCommand getNavigationCommand() const;
  bool hasGameStarted() const;
  bool isGameFinished() const;
  uint16_t getPendingAmmo() const;
  bool hasRecentDamage(double quiet_period_seconds) const;

  void setSerialCommand(const SerialCommand & command);
  void setAutoaimCommand(const AutoaimCommand & command);
  void setNavigationCommand(const NavigationCommand & command);
  void beginAmmoPickupWait();
  void cancelAmmoPickupWait();

private:
  using ReceiveData = decision_process::msg::ReceiveData;
  using DesicionSendData = decision_process::msg::DesicionSendData;
  using AutoaimToDecision = decision_process::msg::AutoaimToDecision;
  using DecisionToAutoaim = decision_process::msg::DecisionToAutoaim;
  using Odometry = nav_msgs::msg::Odometry;
  using PoseStamped = geometry_msgs::msg::PoseStamped;

  void stateEstimationCallback(const Odometry::SharedPtr msg);
  void serialReceiveCallback(const ReceiveData::SharedPtr msg);
  void autoaimCallback(const AutoaimToDecision::SharedPtr msg);
  void publishOutputs();
  void publishGoalPose();
  void initializeBehaviorTree(const std::string & xml_path, double tick_rate_hz);
  void tickBehaviorTree();
  rcl_interfaces::msg::SetParametersResult parametersCallback(
    const std::vector<rclcpp::Parameter> & parameters);

  mutable std::mutex data_mutex_;
  mutable std::mutex output_mutex_;
  RefereeState referee_state_;
  AutoaimState autoaim_state_;
  LocalizationState localization_state_;
  MatchLifecycle match_lifecycle_;
  AmmoReserveTracker ammo_reserve_tracker_;
  DamageTracker damage_tracker_;
  bool ammo_pickup_waiting_{false};

  SerialCommand serial_command_;
  AutoaimCommand autoaim_command_;
  NavigationCommand navigation_command_;

  rclcpp::Subscription<Odometry>::SharedPtr state_estimation_sub_;
  rclcpp::Subscription<ReceiveData>::SharedPtr serial_receive_sub_;
  rclcpp::Subscription<AutoaimToDecision>::SharedPtr autoaim_sub_;

  rclcpp::Publisher<PoseStamped>::SharedPtr goal_pose_pub_;
  rclcpp::Publisher<DesicionSendData>::SharedPtr serial_send_pub_;
  rclcpp::Publisher<DecisionToAutoaim>::SharedPtr autoaim_command_pub_;

  rclcpp::TimerBase::SharedPtr publish_timer_;
  rclcpp::TimerBase::SharedPtr behavior_tree_timer_;
  rclcpp::node_interfaces::OnSetParametersCallbackHandle::SharedPtr parameter_callback_handle_;

  BT::BehaviorTreeFactory behavior_tree_factory_;
  std::unique_ptr<BT::Tree> behavior_tree_;
};

}  // namespace decision_process

#endif  // DECISION_PROCESS__DECISION_PROCESS_NODE_HPP_
