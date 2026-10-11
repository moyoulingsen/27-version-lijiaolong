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
    BT::InputPort<int>("gyro_mode", 3, "0 off, 1 low, 2 medium, 3 high"),
    BT::InputPort<bool>("gimbal_enabled", false, "Whether the gimbal is enabled"),
    BT::OutputPort<int>("posture_command"),
    BT::OutputPort<int>("gyro_mode_command"),
    BT::OutputPort<bool>("gimbal_enabled_command")};
}

BT::NodeStatus ConservativePatrolModeAction::tick()
{
  const auto posture = getInput<int>("posture");
  const auto gyro_mode = getInput<int>("gyro_mode");
  const auto gimbal_enabled = getInput<bool>("gimbal_enabled");
  if(!posture || !gyro_mode || !gimbal_enabled || posture.value() < 1 ||
    posture.value() > 3 || gyro_mode.value() < 0 || gyro_mode.value() > 3)
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
