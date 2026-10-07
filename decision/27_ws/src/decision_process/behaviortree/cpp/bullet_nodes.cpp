#include "bullet_nodes.hpp"

#include <cmath>

namespace decision_process
{

HasAmmoCondition::HasAmmoCondition(const std::string & name, const BT::NodeConfig & config)
: BT::ConditionNode(name, config)
{
}

BT::PortsList HasAmmoCondition::providedPorts()
{
  return {BT::InputPort<int>("ammo_count", 0, "Current number of rounds")};
}

BT::NodeStatus HasAmmoCondition::tick()
{
  const auto ammo_count = getInput<int>("ammo_count");
  if(!ammo_count || ammo_count.value() < 0)
  {
    return BT::NodeStatus::FAILURE;
  }
  return ammo_count.value() > 0 ? BT::NodeStatus::SUCCESS : BT::NodeStatus::FAILURE;
}

HasPickupAmmoCondition::HasPickupAmmoCondition(
  const std::string & name, const BT::NodeConfig & config)
: BT::ConditionNode(name, config)
{
}

BT::PortsList HasPickupAmmoCondition::providedPorts()
{
  return {BT::InputPort<int>("pickup_ammo_count", 0, "Ammunition available at the pickup point")};
}

BT::NodeStatus HasPickupAmmoCondition::tick()
{
  const auto pickup_ammo_count = getInput<int>("pickup_ammo_count");
  if(!pickup_ammo_count || pickup_ammo_count.value() < 0)
  {
    return BT::NodeStatus::FAILURE;
  }
  return pickup_ammo_count.value() > 0 ? BT::NodeStatus::SUCCESS : BT::NodeStatus::FAILURE;
}

RememberAmmoAction::RememberAmmoAction(
  const std::string & name, const BT::NodeConfig & config)
: BT::SyncActionNode(name, config)
{
}

BT::PortsList RememberAmmoAction::providedPorts()
{
  return {
    BT::InputPort<int>("ammo_count", 0, "Current own ammunition"),
    BT::OutputPort<int>("ammo_before")};
}

BT::NodeStatus RememberAmmoAction::tick()
{
  const auto ammo_count = getInput<int>("ammo_count");
  if(!ammo_count || ammo_count.value() < 0)
  {
    return BT::NodeStatus::FAILURE;
  }
  setOutput("ammo_before", ammo_count.value());
  return BT::NodeStatus::SUCCESS;
}

RememberPositionAction::RememberPositionAction(
  const std::string & name, const BT::NodeConfig & config)
: BT::SyncActionNode(name, config)
{
}

BT::PortsList RememberPositionAction::providedPorts()
{
  return {
    BT::InputPort<double>("current_x", 0.0, "Current map x coordinate"),
    BT::InputPort<double>("current_y", 0.0, "Current map y coordinate"),
    BT::OutputPort<double>("return_x"),
    BT::OutputPort<double>("return_y")};
}

BT::NodeStatus RememberPositionAction::tick()
{
  const auto current_x = getInput<double>("current_x");
  const auto current_y = getInput<double>("current_y");
  if(!current_x || !current_y || !std::isfinite(current_x.value()) ||
    !std::isfinite(current_y.value()))
  {
    return BT::NodeStatus::FAILURE;
  }
  setOutput("return_x", current_x.value());
  setOutput("return_y", current_y.value());
  return BT::NodeStatus::SUCCESS;
}

AmmoIncreasedCondition::AmmoIncreasedCondition(
  const std::string & name, const BT::NodeConfig & config)
: BT::ConditionNode(name, config)
{
}

BT::PortsList AmmoIncreasedCondition::providedPorts()
{
  return {
    BT::InputPort<int>("ammo_count", 0, "Current own ammunition"),
    BT::InputPort<int>("ammo_before", 0, "Own ammunition before pickup")};
}

BT::NodeStatus AmmoIncreasedCondition::tick()
{
  const auto ammo_count = getInput<int>("ammo_count");
  const auto ammo_before = getInput<int>("ammo_before");
  if(!ammo_count || !ammo_before || ammo_count.value() < 0 || ammo_before.value() < 0)
  {
    return BT::NodeStatus::FAILURE;
  }
  return ammo_count.value() > ammo_before.value() ? BT::NodeStatus::SUCCESS :
                                                    BT::NodeStatus::FAILURE;
}

ResourcesLowCondition::ResourcesLowCondition(
  const std::string & name, const BT::NodeConfig & config)
: BT::ConditionNode(name, config)
{
}

BT::PortsList ResourcesLowCondition::providedPorts()
{
  return {
    BT::InputPort<double>("health", 0.0, "Current health value"),
    BT::InputPort<double>("health_threshold", 0.0, "Health threshold"),
    BT::InputPort<double>("economy", 0.0, "Current economy value"),
    BT::InputPort<double>("economy_threshold", 0.0, "Economy threshold")};
}

BT::NodeStatus ResourcesLowCondition::tick()
{
  const auto health = getInput<double>("health");
  const auto health_threshold = getInput<double>("health_threshold");
  const auto economy = getInput<double>("economy");
  const auto economy_threshold = getInput<double>("economy_threshold");

  if(!health || !health_threshold || !economy || !economy_threshold ||
    !std::isfinite(health.value()) || !std::isfinite(health_threshold.value()) ||
    !std::isfinite(economy.value()) || !std::isfinite(economy_threshold.value()) ||
    health_threshold.value() < 0.0 || economy_threshold.value() < 0.0)
  {
    return BT::NodeStatus::FAILURE;
  }

  return health.value() < health_threshold.value() ||
             economy.value() < economy_threshold.value() ?
           BT::NodeStatus::SUCCESS : BT::NodeStatus::FAILURE;
}

void registerBulletNodes(BT::BehaviorTreeFactory & factory)
{
  factory.registerNodeType<HasAmmoCondition>("HasAmmo");
  factory.registerNodeType<HasPickupAmmoCondition>("HasPickupAmmo");
  factory.registerNodeType<RememberAmmoAction>("RememberAmmo");
  factory.registerNodeType<RememberPositionAction>("RememberPosition");
  factory.registerNodeType<AmmoIncreasedCondition>("AmmoIncreased");
  factory.registerNodeType<ResourcesLowCondition>("ResourcesLow");
}

}  // namespace decision_process
