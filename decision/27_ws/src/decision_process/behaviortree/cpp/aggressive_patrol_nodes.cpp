#include "aggressive_patrol_nodes.hpp"

#include <cmath>

namespace decision_process
{

AggressivePatrolModeAction::AggressivePatrolModeAction(
  const std::string & name, const BT::NodeConfig & config)
: BT::SyncActionNode(name, config)
{
}

BT::PortsList AggressivePatrolModeAction::providedPorts()
{
  return {
    BT::InputPort<int>("posture", 2, "Defense posture"),
    BT::InputPort<double>("gyro_mode", 2.2, "Low-speed small gyro mode"),
    BT::InputPort<bool>("gimbal_enabled", true, "Whether the gimbal is enabled"),
    BT::OutputPort<int>("posture_command"),
    BT::OutputPort<double>("gyro_mode_command"),
    BT::OutputPort<bool>("gimbal_enabled_command")};
}

BT::NodeStatus AggressivePatrolModeAction::tick()
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

void registerAggressivePatrolNodes(BT::BehaviorTreeFactory & factory)
{
  factory.registerNodeType<AggressivePatrolModeAction>("ConfigureAggressivePatrol");
}

}  // namespace decision_process
