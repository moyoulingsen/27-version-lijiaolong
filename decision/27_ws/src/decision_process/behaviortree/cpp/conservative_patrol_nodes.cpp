#include "conservative_patrol_nodes.hpp"

#include <cmath>

namespace decision_process
{

ConservativePatrolModeAction::ConservativePatrolModeAction(
  const std::string & name, const BT::NodeConfig & config)
: BT::SyncActionNode(name, config)
{
}

BT::PortsList ConservativePatrolModeAction::providedPorts()
{
  return {
    BT::InputPort<int>("posture", 2, "Defense posture"),
    BT::InputPort<double>("gyro_mode", 2.4, "High-speed small gyro mode"),
    BT::InputPort<bool>("gimbal_enabled", false, "Whether the gimbal is enabled"),
    BT::OutputPort<int>("posture_command"),
    BT::OutputPort<double>("gyro_mode_command"),
    BT::OutputPort<bool>("gimbal_enabled_command")};
}

BT::NodeStatus ConservativePatrolModeAction::tick()
{
  const auto posture = getInput<int>("posture");
  const auto gyro_mode = getInput<double>("gyro_mode");
  const auto gimbal_enabled = getInput<bool>("gimbal_enabled");
  if(!posture || !gyro_mode || !gimbal_enabled || posture.value() < 1 ||
    posture.value() > 3 || !std::isfinite(gyro_mode.value()))
  {
    return BT::NodeStatus::FAILURE;
  }

  setOutput("posture_command", posture.value());
  setOutput("gyro_mode_command", gyro_mode.value());
  setOutput("gimbal_enabled_command", gimbal_enabled.value());
  return BT::NodeStatus::SUCCESS;
}

void registerConservativePatrolNodes(BT::BehaviorTreeFactory & factory)
{
  factory.registerNodeType<ConservativePatrolModeAction>("ConfigureConservativePatrol");
}

}  // namespace decision_process
