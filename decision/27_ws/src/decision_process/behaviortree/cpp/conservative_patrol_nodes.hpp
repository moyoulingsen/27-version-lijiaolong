#ifndef DECISION_PROCESS_BEHAVIORTREE_CONSERVATIVE_PATROL_NODES_HPP_
#define DECISION_PROCESS_BEHAVIORTREE_CONSERVATIVE_PATROL_NODES_HPP_

#include <string>

#include "behaviortree_cpp/action_node.h"
#include "behaviortree_cpp/bt_factory.h"

namespace decision_process
{

class ConservativePatrolModeAction : public BT::SyncActionNode
{
public:
  ConservativePatrolModeAction(const std::string & name, const BT::NodeConfig & config);

  static BT::PortsList providedPorts();

  BT::NodeStatus tick() override;
};

void registerConservativePatrolNodes(BT::BehaviorTreeFactory & factory);

}  // namespace decision_process

#endif  // DECISION_PROCESS_BEHAVIORTREE_CONSERVATIVE_PATROL_NODES_HPP_
