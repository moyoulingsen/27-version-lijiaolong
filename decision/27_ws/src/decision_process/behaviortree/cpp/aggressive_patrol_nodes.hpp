#ifndef DECISION_PROCESS_BEHAVIORTREE_AGGRESSIVE_PATROL_NODES_HPP_
#define DECISION_PROCESS_BEHAVIORTREE_AGGRESSIVE_PATROL_NODES_HPP_

#include <string>

#include "behaviortree_cpp/action_node.h"
#include "behaviortree_cpp/bt_factory.h"

namespace decision_process
{

class AggressivePatrolModeAction : public BT::SyncActionNode
{
public:
  AggressivePatrolModeAction(const std::string & name, const BT::NodeConfig & config);

  static BT::PortsList providedPorts();

  BT::NodeStatus tick() override;
};

void registerAggressivePatrolNodes(BT::BehaviorTreeFactory & factory);

}  // namespace decision_process

#endif  // DECISION_PROCESS_BEHAVIORTREE_AGGRESSIVE_PATROL_NODES_HPP_
