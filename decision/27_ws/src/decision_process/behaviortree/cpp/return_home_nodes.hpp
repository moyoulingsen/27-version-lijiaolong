#ifndef DECISION_PROCESS_BEHAVIORTREE_RETURN_HOME_NODES_HPP_
#define DECISION_PROCESS_BEHAVIORTREE_RETURN_HOME_NODES_HPP_

#include <string>

#include "behaviortree_cpp/action_node.h"
#include "behaviortree_cpp/bt_factory.h"
#include "behaviortree_cpp/condition_node.h"

namespace decision_process
{

/**
 * Returns SUCCESS when the current localization is inside the requested
 * planar distance from the target. The node deliberately has no navigation
 * side effects, so it can be reused by any behavior that needs a position
 * check.
 */
class PositionReachedCondition : public BT::ConditionNode
{
public:
  PositionReachedCondition(const std::string & name, const BT::NodeConfig & config);

  static BT::PortsList providedPorts();

  BT::NodeStatus tick() override;
};

/**
 * Latches the end of a match after observing the playing phase. A startup
 * message with game_period == 0 therefore cannot trigger return-home.
 */
class MatchFinishedCondition : public BT::ConditionNode
{
public:
  MatchFinishedCondition(const std::string & name, const BT::NodeConfig & config);

  static BT::PortsList providedPorts();

  BT::NodeStatus tick() override;

private:
  bool have_previous_period_{false};
  int previous_period_{0};
  bool has_started_{false};
  bool match_finished_{false};
};

/** Sets the requested chassis posture through a blackboard output. */
class SetPostureAction : public BT::SyncActionNode
{
public:
  SetPostureAction(const std::string & name, const BT::NodeConfig & config);

  static BT::PortsList providedPorts();

  BT::NodeStatus tick() override;
};

/** Clears the navigation-enable output when the target is already reached. */
class DisableGoalAction : public BT::SyncActionNode
{
public:
  DisableGoalAction(const std::string & name, const BT::NodeConfig & config);

  static BT::PortsList providedPorts();

  BT::NodeStatus tick() override;
};

/**
 * Publishes a navigation goal through output ports and stays RUNNING until a
 * sibling position condition reports arrival. A ROS adapter can consume the
 * output ports and construct geometry_msgs::msg::PoseStamped.
 */
class SendGoalPoseAction : public BT::StatefulActionNode
{
public:
  SendGoalPoseAction(const std::string & name, const BT::NodeConfig & config);

  static BT::PortsList providedPorts();

  BT::NodeStatus onStart() override;
  BT::NodeStatus onRunning() override;
  void onHalted() override;

private:
  bool readGoal();
  void publishGoal(bool enabled);

  double target_x_{0.0};
  double target_y_{0.0};
  double target_z_{1.0};
  double target_yaw_{0.0};
  std::string frame_id_{"map"};
};

/** Register nodes shared by any tree that publishes navigation goals. */
void registerNavigationNodes(BT::BehaviorTreeFactory & factory);

/** Register navigation nodes and the match-finished condition. */
void registerReturnHomeNodes(BT::BehaviorTreeFactory & factory);

}  // namespace decision_process

#endif  // DECISION_PROCESS_BEHAVIORTREE_RETURN_HOME_NODES_HPP_
