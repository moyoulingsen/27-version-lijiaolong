#ifndef DECISION_PROCESS_BEHAVIORTREE_RESPAWN_NODES_HPP_
#define DECISION_PROCESS_BEHAVIORTREE_RESPAWN_NODES_HPP_

#include <chrono>
#include <string>

#include "behaviortree_cpp/action_node.h"
#include "behaviortree_cpp/bt_factory.h"
#include "behaviortree_cpp/condition_node.h"

namespace decision_process
{

class RespawnActiveCondition : public BT::ConditionNode
{
public:
  RespawnActiveCondition(const std::string & name, const BT::NodeConfig & config);

  static BT::PortsList providedPorts();
  BT::NodeStatus tick() override;

private:
  bool active_{false};
};

class WaitForRespawnAction : public BT::StatefulActionNode
{
public:
  WaitForRespawnAction(const std::string & name, const BT::NodeConfig & config);

  static BT::PortsList providedPorts();
  BT::NodeStatus onStart() override;
  BT::NodeStatus onRunning() override;
  void onHalted() override;

private:
  BT::NodeStatus evaluate();
  void publishConfirmation(bool enabled);

  std::chrono::steady_clock::time_point started_at_{};
};

void registerRespawnNodes(BT::BehaviorTreeFactory & factory);

}  // namespace decision_process

#endif  // DECISION_PROCESS_BEHAVIORTREE_RESPAWN_NODES_HPP_
