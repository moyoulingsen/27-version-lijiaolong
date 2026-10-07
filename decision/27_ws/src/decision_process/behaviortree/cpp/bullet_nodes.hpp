#ifndef DECISION_PROCESS_BEHAVIORTREE_BULLET_NODES_HPP_
#define DECISION_PROCESS_BEHAVIORTREE_BULLET_NODES_HPP_

#include <string>

#include "behaviortree_cpp/bt_factory.h"
#include "behaviortree_cpp/condition_node.h"

namespace decision_process
{

/** Returns SUCCESS when the robot has at least one round in its own magazine. */
class HasAmmoCondition : public BT::ConditionNode
{
public:
  HasAmmoCondition(const std::string & name, const BT::NodeConfig & config);

  static BT::PortsList providedPorts();

  BT::NodeStatus tick() override;
};

/** Returns SUCCESS when a positive amount of ammunition is available to pick up. */
class HasPickupAmmoCondition : public BT::ConditionNode
{
public:
  HasPickupAmmoCondition(const std::string & name, const BT::NodeConfig & config);

  static BT::PortsList providedPorts();

  BT::NodeStatus tick() override;
};

/** Stores the current own-ammunition count before a pickup attempt. */
class RememberAmmoAction : public BT::SyncActionNode
{
public:
  RememberAmmoAction(const std::string & name, const BT::NodeConfig & config);

  static BT::PortsList providedPorts();

  BT::NodeStatus tick() override;
};

/** Stores the robot position before it leaves for a pickup point. */
class RememberPositionAction : public BT::SyncActionNode
{
public:
  RememberPositionAction(const std::string & name, const BT::NodeConfig & config);

  static BT::PortsList providedPorts();

  BT::NodeStatus tick() override;
};

/** Returns SUCCESS only after own ammunition is greater than the saved baseline. */
class AmmoIncreasedCondition : public BT::ConditionNode
{
public:
  AmmoIncreasedCondition(const std::string & name, const BT::NodeConfig & config);

  static BT::PortsList providedPorts();

  BT::NodeStatus tick() override;
};

/** Returns SUCCESS when either health or economy is below its configured limit. */
class ResourcesLowCondition : public BT::ConditionNode
{
public:
  ResourcesLowCondition(const std::string & name, const BT::NodeConfig & config);

  static BT::PortsList providedPorts();

  BT::NodeStatus tick() override;
};

void registerBulletNodes(BT::BehaviorTreeFactory & factory);

}  // namespace decision_process

#endif  // DECISION_PROCESS_BEHAVIORTREE_BULLET_NODES_HPP_
