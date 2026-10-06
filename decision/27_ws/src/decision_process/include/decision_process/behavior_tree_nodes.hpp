#ifndef DECISION_PROCESS__BEHAVIOR_TREE_NODES_HPP_
#define DECISION_PROCESS__BEHAVIOR_TREE_NODES_HPP_

#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

#include "behaviortree_cpp/action_node.h"
#include "behaviortree_cpp/bt_factory.h"
#include "behaviortree_cpp/condition_node.h"

#include "decision_process/communication_data.hpp"
#include "decision_process/patrol_logic.hpp"
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

class OutOfAmmoCondition : public BT::ConditionNode
{
public:
  OutOfAmmoCondition(
    const std::string & name, const BT::NodeConfig & config,
    DecisionProcessNode & decision_node);
  static BT::PortsList providedPorts();
  BT::NodeStatus tick() override;

private:
  DecisionProcessNode & decision_node_;
};

class PendingAmmoAvailableCondition : public BT::ConditionNode
{
public:
  PendingAmmoAvailableCondition(
    const std::string & name, const BT::NodeConfig & config,
    DecisionProcessNode & decision_node);
  static BT::PortsList providedPorts();
  BT::NodeStatus tick() override;

private:
  DecisionProcessNode & decision_node_;
};

class NoEnemyVisibleCondition : public BT::ConditionNode
{
public:
  NoEnemyVisibleCondition(
    const std::string & name, const BT::NodeConfig & config,
    DecisionProcessNode & decision_node);
  static BT::PortsList providedPorts();
  BT::NodeStatus tick() override;

private:
  DecisionProcessNode & decision_node_;
};

class RecentDamageCondition : public BT::ConditionNode
{
public:
  RecentDamageCondition(
    const std::string & name, const BT::NodeConfig & config,
    DecisionProcessNode & decision_node);
  static BT::PortsList providedPorts();
  BT::NodeStatus tick() override;

private:
  DecisionProcessNode & decision_node_;
};

class NavigationGoalReachedCondition : public BT::ConditionNode
{
public:
  NavigationGoalReachedCondition(
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
  void disableNavigation(bool reached);

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

class SetCombatIdleAction : public BT::SyncActionNode
{
public:
  SetCombatIdleAction(
    const std::string & name, const BT::NodeConfig & config,
    DecisionProcessNode & decision_node);
  static BT::PortsList providedPorts();
  BT::NodeStatus tick() override;

private:
  DecisionProcessNode & decision_node_;
};

class CollectPendingAmmoAction : public BT::StatefulActionNode
{
public:
  CollectPendingAmmoAction(
    const std::string & name, const BT::NodeConfig & config,
    DecisionProcessNode & decision_node);
  static BT::PortsList providedPorts();
  BT::NodeStatus onStart() override;
  BT::NodeStatus onRunning() override;
  void onHalted() override;

private:
  BT::NodeStatus updatePickup();
  void publishSupplyGoal();
  void disableNavigation(bool reached);

  DecisionProcessNode & decision_node_;
  double supply_x_{2.0};
  double supply_y_{1.0};
  double supply_yaw_{0.0};
  double tolerance_{0.15};
  std::string frame_id_{"map"};
  bool reached_supply_{false};
};

class EvadeUntilSafeAction : public BT::StatefulActionNode
{
public:
  EvadeUntilSafeAction(
    const std::string & name, const BT::NodeConfig & config,
    DecisionProcessNode & decision_node);
  static BT::PortsList providedPorts();
  BT::NodeStatus onStart() override;
  BT::NodeStatus onRunning() override;
  void onHalted() override;

private:
  BT::NodeStatus updateEvasion();
  bool publishNextGoal(const LocalizationState & localization);
  void disableNavigation();

  DecisionProcessNode & decision_node_;
  double quiet_period_seconds_{2.0};
  double step_{0.8};
  double tolerance_{0.15};
  double min_x_{0.2};
  double max_x_{27.8};
  double min_y_{0.2};
  double max_y_{14.8};
  std::string frame_id_{"map"};
  std::size_t direction_index_{0U};
  double goal_x_{0.0};
  double goal_y_{0.0};
  bool goal_active_{false};
};

class PatrolRouteAction : public BT::StatefulActionNode
{
public:
  PatrolRouteAction(
    const std::string & name, const BT::NodeConfig & config,
    DecisionProcessNode & decision_node);
  static BT::PortsList providedPorts();
  BT::NodeStatus onStart() override;
  BT::NodeStatus onRunning() override;
  void onHalted() override;

private:
  BT::NodeStatus updatePatrol();
  void publishCurrentGoal();
  void disableNavigation();

  DecisionProcessNode & decision_node_;
  std::vector<PatrolPoint> points_;
  std::size_t point_index_{0U};
  bool forward_{true};
  double yaw_{0.0};
  double tolerance_{0.15};
  std::string frame_id_{"map"};
  bool goal_active_{false};
};

class UpdateSpinModeAction : public BT::SyncActionNode
{
public:
  UpdateSpinModeAction(
    const std::string & name, const BT::NodeConfig & config,
    DecisionProcessNode & decision_node);
  static BT::PortsList providedPorts();
  BT::NodeStatus tick() override;

private:
  DecisionProcessNode & decision_node_;
};

class UpdateGimbalModeAction : public BT::SyncActionNode
{
public:
  UpdateGimbalModeAction(
    const std::string & name, const BT::NodeConfig & config,
    DecisionProcessNode & decision_node);
  static BT::PortsList providedPorts();
  BT::NodeStatus tick() override;

private:
  DecisionProcessNode & decision_node_;
};

class KeepRunningAction : public BT::StatefulActionNode
{
public:
  KeepRunningAction(const std::string & name, const BT::NodeConfig & config);
  static BT::PortsList providedPorts();
  BT::NodeStatus onStart() override;
  BT::NodeStatus onRunning() override;
  void onHalted() override;
};

class LowHealthCondition : public BT::ConditionNode
{
public:
  LowHealthCondition(
    const std::string & name, const BT::NodeConfig & config,
    DecisionProcessNode & decision_node);
  static BT::PortsList providedPorts();
  BT::NodeStatus tick() override;

private:
  DecisionProcessNode & decision_node_;
};

class RecoverAtSupplyAction : public BT::StatefulActionNode
{
public:
  RecoverAtSupplyAction(
    const std::string & name, const BT::NodeConfig & config,
    DecisionProcessNode & decision_node);
  static BT::PortsList providedPorts();
  BT::NodeStatus onStart() override;
  BT::NodeStatus onRunning() override;
  void onHalted() override;

private:
  BT::NodeStatus updateRecovery();
  void publishSupplyGoal();
  void disableNavigation(bool reached);

  DecisionProcessNode & decision_node_;
  double supply_x_{2.0};
  double supply_y_{1.0};
  double supply_yaw_{0.0};
  double tolerance_{0.15};
  int health_threshold_{200};
  std::string frame_id_{"map"};
  bool waiting_at_supply_{false};
};

void registerDecisionNodes(
  BT::BehaviorTreeFactory & factory, DecisionProcessNode & decision_node);

}  // namespace decision_process

#endif  // DECISION_PROCESS__BEHAVIOR_TREE_NODES_HPP_
