#ifndef DECISION_PROCESS__BEHAVIOR_TREE_NODES_HPP_
#define DECISION_PROCESS__BEHAVIOR_TREE_NODES_HPP_

#include <string>

#include "behaviortree_cpp/action_node.h"
#include "behaviortree_cpp/bt_factory.h"
#include "behaviortree_cpp/condition_node.h"

#include "decision_process/posture_logic.hpp"

namespace decision_process
{

class DecisionProcessNode;

class GameFinishedCondition : public BT::ConditionNode
{
public:
  GameFinishedCondition(
    const std::string & name, const BT::NodeConfig & config,
    DecisionProcessNode & decision_node);
  static BT::PortsList providedPorts();
  BT::NodeStatus tick() override;

private:
  DecisionProcessNode & decision_node_;
};

class SentryAliveCondition : public BT::ConditionNode
{
public:
  SentryAliveCondition(
    const std::string & name, const BT::NodeConfig & config,
    DecisionProcessNode & decision_node);
  static BT::PortsList providedPorts();
  BT::NodeStatus tick() override;

private:
  DecisionProcessNode & decision_node_;
};

class GameRunningCondition : public BT::ConditionNode
{
public:
  GameRunningCondition(
    const std::string & name, const BT::NodeConfig & config,
    DecisionProcessNode & decision_node);
  static BT::PortsList providedPorts();
  BT::NodeStatus tick() override;

private:
  DecisionProcessNode & decision_node_;
};

class EnemyOutpostAliveCondition : public BT::ConditionNode
{
public:
  EnemyOutpostAliveCondition(
    const std::string & name, const BT::NodeConfig & config,
    DecisionProcessNode & decision_node);
  static BT::PortsList providedPorts();
  BT::NodeStatus tick() override;

private:
  DecisionProcessNode & decision_node_;
};

class EnemyOutpostDestroyedCondition : public BT::ConditionNode
{
public:
  EnemyOutpostDestroyedCondition(
    const std::string & name, const BT::NodeConfig & config,
    DecisionProcessNode & decision_node);
  static BT::PortsList providedPorts();
  BT::NodeStatus tick() override;

private:
  DecisionProcessNode & decision_node_;
};

class SetPostureAction : public BT::SyncActionNode
{
public:
  SetPostureAction(
    const std::string & name, const BT::NodeConfig & config,
    DecisionProcessNode & decision_node);
  static BT::PortsList providedPorts();
  BT::NodeStatus tick() override;

private:
  DecisionProcessNode & decision_node_;
};

class NavigateToPoseAction : public BT::StatefulActionNode
{
public:
  NavigateToPoseAction(
    const std::string & name, const BT::NodeConfig & config,
    DecisionProcessNode & decision_node);
  static BT::PortsList providedPorts();
  BT::NodeStatus onStart() override;
  BT::NodeStatus onRunning() override;
  void onHalted() override;

private:
  BT::NodeStatus evaluateGoal();
  void disableNavigation();

  DecisionProcessNode & decision_node_;
  double goal_x_{0.0};
  double goal_y_{0.0};
  double tolerance_{0.15};
};

class ApplyPostureAction : public BT::SyncActionNode
{
public:
  ApplyPostureAction(
    const std::string & name, const BT::NodeConfig & config,
    DecisionProcessNode & decision_node);
  static BT::PortsList providedPorts();
  BT::NodeStatus tick() override;

private:
  DecisionProcessNode & decision_node_;
  PostureSwitchPolicy policy_;
};

class EngageOutpostAction : public BT::StatefulActionNode
{
public:
  EngageOutpostAction(
    const std::string & name, const BT::NodeConfig & config,
    DecisionProcessNode & decision_node);
  static BT::PortsList providedPorts();
  BT::NodeStatus onStart() override;
  BT::NodeStatus onRunning() override;
  void onHalted() override;

private:
  BT::NodeStatus updateCommand();
  void clearCommand();

  DecisionProcessNode & decision_node_;
  uint8_t target_{6U};
};

void registerDecisionNodes(
  BT::BehaviorTreeFactory & factory, DecisionProcessNode & decision_node);

}  // namespace decision_process

#endif  // DECISION_PROCESS__BEHAVIOR_TREE_NODES_HPP_
