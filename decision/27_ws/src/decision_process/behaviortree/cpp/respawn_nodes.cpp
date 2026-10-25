#include "respawn_nodes.hpp"

#include <cmath>

namespace decision_process
{

RespawnActiveCondition::RespawnActiveCondition(
  const std::string & name, const BT::NodeConfig & config)
: BT::ConditionNode(name, config)
{
}

BT::PortsList RespawnActiveCondition::providedPorts()
{
  return {
    BT::InputPort<double>("health", 0.0, "Current sentry health"),
    BT::InputPort<double>("current_x", 0.0, "Current map x coordinate"),
    BT::InputPort<double>("current_y", 0.0, "Current map y coordinate"),
    BT::InputPort<double>("supply_x", 2.10, "Supply point x coordinate"),
    BT::InputPort<double>("supply_y", 1.30, "Supply point y coordinate"),
    BT::InputPort<double>("tolerance", 0.25, "Supply arrival tolerance"),
    BT::InputPort<bool>("localization_valid", false, "Whether the pose is valid")};
}

BT::NodeStatus RespawnActiveCondition::tick()
{
  const auto health = getInput<double>("health");
  const auto current_x = getInput<double>("current_x");
  const auto current_y = getInput<double>("current_y");
  const auto supply_x = getInput<double>("supply_x");
  const auto supply_y = getInput<double>("supply_y");
  const auto tolerance = getInput<double>("tolerance");
  const auto localization_valid = getInput<bool>("localization_valid");
  if(!health || !current_x || !current_y || !supply_x || !supply_y || !tolerance ||
    !localization_valid || !std::isfinite(health.value()) ||
    !std::isfinite(current_x.value()) || !std::isfinite(current_y.value()) ||
    !std::isfinite(supply_x.value()) || !std::isfinite(supply_y.value()) ||
    !std::isfinite(tolerance.value()) || health.value() < 0.0 ||
    tolerance.value() <= 0.0)
  {
    return BT::NodeStatus::FAILURE;
  }

  if(health.value() <= 0.0)
  {
    active_ = true;
    return BT::NodeStatus::SUCCESS;
  }
  if(!active_)
  {
    return BT::NodeStatus::FAILURE;
  }

  const double supply_distance = std::hypot(
    current_x.value() - supply_x.value(), current_y.value() - supply_y.value());
  if(localization_valid.value() && supply_distance <= tolerance.value())
  {
    active_ = false;
    return BT::NodeStatus::FAILURE;
  }
  return BT::NodeStatus::SUCCESS;
}

WaitForRespawnAction::WaitForRespawnAction(
  const std::string & name, const BT::NodeConfig & config)
: BT::StatefulActionNode(name, config)
{
}

BT::PortsList WaitForRespawnAction::providedPorts()
{
  return {
    BT::InputPort<double>("health", 0.0, "Current sentry health"),
    BT::InputPort<double>("wait_seconds", 5.0, "Delay before confirming respawn"),
    BT::OutputPort<bool>("confirm_respawn")};
}

void WaitForRespawnAction::publishConfirmation(bool enabled)
{
  setOutput("confirm_respawn", enabled);
}

BT::NodeStatus WaitForRespawnAction::evaluate()
{
  const auto health = getInput<double>("health");
  const auto wait_seconds = getInput<double>("wait_seconds");
  if(!health || !wait_seconds || !std::isfinite(health.value()) ||
    !std::isfinite(wait_seconds.value()) || health.value() < 0.0 ||
    wait_seconds.value() < 0.0)
  {
    publishConfirmation(false);
    return BT::NodeStatus::FAILURE;
  }
  if(health.value() > 0.0)
  {
    publishConfirmation(false);
    return BT::NodeStatus::SUCCESS;
  }

  const double elapsed = std::chrono::duration<double>(
    std::chrono::steady_clock::now() - started_at_).count();
  publishConfirmation(elapsed >= wait_seconds.value());
  return BT::NodeStatus::RUNNING;
}

BT::NodeStatus WaitForRespawnAction::onStart()
{
  started_at_ = std::chrono::steady_clock::now();
  return evaluate();
}

BT::NodeStatus WaitForRespawnAction::onRunning()
{
  return evaluate();
}

void WaitForRespawnAction::onHalted()
{
  publishConfirmation(false);
}

void registerRespawnNodes(BT::BehaviorTreeFactory & factory)
{
  factory.registerNodeType<RespawnActiveCondition>("RespawnActive");
  factory.registerNodeType<WaitForRespawnAction>("WaitForRespawn");
}

}  // namespace decision_process
