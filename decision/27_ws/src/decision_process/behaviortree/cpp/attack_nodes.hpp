#ifndef DECISION_PROCESS_BEHAVIORTREE_ATTACK_NODES_HPP_
#define DECISION_PROCESS_BEHAVIORTREE_ATTACK_NODES_HPP_

#include <string>

#include "behaviortree_cpp/action_node.h"
#include "behaviortree_cpp/bt_factory.h"
#include "behaviortree_cpp/condition_node.h"

namespace decision_process
{

/** Publishes the movement posture used while scanning for targets. */
class ConfigureAttackAction : public BT::SyncActionNode
{
public:
  ConfigureAttackAction(const std::string & name, const BT::NodeConfig & config);

  static BT::PortsList providedPorts();

  BT::NodeStatus tick() override;
};

/**
 * Filters observed and persistent targets.
 *
 * A target list is encoded as:
 *   id:health:distance:in_range:invincible:persistent;...
 * where the last three fields are 0 or 1.  The same id in targets replaces
 * the entry from persistent_targets, which lets fresh observations win.
 */
class BuildAttackTargetListAction : public BT::SyncActionNode
{
public:
  BuildAttackTargetListAction(const std::string & name, const BT::NodeConfig & config);

  static BT::PortsList providedPorts();

  BT::NodeStatus tick() override;
};

/** Selects the lowest-health target first, then the nearest target. */
class SelectAttackTargetAction : public BT::SyncActionNode
{
public:
  SelectAttackTargetAction(const std::string & name, const BT::NodeConfig & config);

  static BT::PortsList providedPorts();

  BT::NodeStatus tick() override;
};

/** Returns SUCCESS when at least one valid target exists. */
class HasAttackTargetsCondition : public BT::ConditionNode
{
public:
  HasAttackTargetsCondition(const std::string & name, const BT::NodeConfig & config);

  static BT::PortsList providedPorts();

  BT::NodeStatus tick() override;
};

/** Returns SUCCESS when at least one valid target is inside weapon range. */
class HasInRangeTargetCondition : public BT::ConditionNode
{
public:
  HasInRangeTargetCondition(const std::string & name, const BT::NodeConfig & config);

  static BT::PortsList providedPorts();

  BT::NodeStatus tick() override;
};

/** Latches unexplained damage while no enemy is visible until recovery. */
class EvadeEligibleCondition : public BT::ConditionNode
{
public:
  EvadeEligibleCondition(const std::string & name, const BT::NodeConfig & config);

  static BT::PortsList providedPorts();

  BT::NodeStatus tick() override;

private:
  bool damage_latched_{false};
};

/**
 * A stateful aim/fire loop.  The transport layer supplies visibility,
 * alignment, damage feedback, and the time since the target was lost.
 */
class AimAndFireAction : public BT::StatefulActionNode
{
public:
  AimAndFireAction(const std::string & name, const BT::NodeConfig & config);

  static BT::PortsList providedPorts();

  BT::NodeStatus onStart() override;
  BT::NodeStatus onRunning() override;
  void onHalted() override;

private:
  BT::NodeStatus evaluate();
  void publishSafeOutputs();
};

/** Returns SUCCESS when any of the configured pursue criteria is met. */
class PursuitEligibilityCondition : public BT::ConditionNode
{
public:
  PursuitEligibilityCondition(const std::string & name, const BT::NodeConfig & config);

  static BT::PortsList providedPorts();

  BT::NodeStatus tick() override;
};

/** Drives the low-speed pursuit until range is held or the timeout expires. */
class PursueAction : public BT::StatefulActionNode
{
public:
  PursueAction(const std::string & name, const BT::NodeConfig & config);

  static BT::PortsList providedPorts();

  BT::NodeStatus onStart() override;
  BT::NodeStatus onRunning() override;
  void onHalted() override;

private:
  enum class Direction
  {
    NONE,
    APPROACH,
    RETREAT
  };

  BT::NodeStatus evaluate();
  void publishSafeOutputs();
  void resetPursuitState();

  std::string active_target_id_;
  Direction direction_{Direction::NONE};
};

void registerAttackNodes(BT::BehaviorTreeFactory & factory);

}  // namespace decision_process

#endif  // DECISION_PROCESS_BEHAVIORTREE_ATTACK_NODES_HPP_
