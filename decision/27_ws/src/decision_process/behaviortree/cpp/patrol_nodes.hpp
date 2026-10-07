#ifndef DECISION_PROCESS_BEHAVIORTREE_PATROL_NODES_HPP_
#define DECISION_PROCESS_BEHAVIORTREE_PATROL_NODES_HPP_

#include <string>

#include "behaviortree_cpp/action_node.h"
#include "behaviortree_cpp/bt_factory.h"

namespace decision_process
{

/** Selects one point from an XML string formatted as x,y;x,y;... . */
class SelectPatrolPointAction : public BT::SyncActionNode
{
public:
  SelectPatrolPointAction(const std::string & name, const BT::NodeConfig & config);

  static BT::PortsList providedPorts();

  BT::NodeStatus tick() override;
};

/** Advances the point index and wraps it back to zero at the end. */
class AdvancePatrolPointAction : public BT::SyncActionNode
{
public:
  AdvancePatrolPointAction(const std::string & name, const BT::NodeConfig & config);

  static BT::PortsList providedPorts();

  BT::NodeStatus tick() override;
};

void registerPatrolNodes(BT::BehaviorTreeFactory & factory);

}  // namespace decision_process

#endif  // DECISION_PROCESS_BEHAVIORTREE_PATROL_NODES_HPP_
