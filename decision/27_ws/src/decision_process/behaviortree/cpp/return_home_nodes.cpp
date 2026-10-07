#include "return_home_nodes.hpp"

#include <cmath>

namespace decision_process
{
namespace
{

bool finite(double value)
{
  return std::isfinite(value);
}

}  // namespace

PositionReachedCondition::PositionReachedCondition(
  const std::string & name, const BT::NodeConfig & config)
: BT::ConditionNode(name, config)
{
}

BT::PortsList PositionReachedCondition::providedPorts()
{
  return {
    BT::InputPort<double>("current_x", 0.0, "Current map x coordinate"),
    BT::InputPort<double>("current_y", 0.0, "Current map y coordinate"),
    BT::InputPort<double>("target_x", 0.0, "Target map x coordinate"),
    BT::InputPort<double>("target_y", 0.0, "Target map y coordinate"),
    BT::InputPort<double>("tolerance", 0.25, "Planar arrival tolerance in meters"),
    BT::InputPort<bool>("localization_valid", false, "Whether the pose is valid")};
}

BT::NodeStatus PositionReachedCondition::tick()
{
  const auto current_x = getInput<double>("current_x");
  const auto current_y = getInput<double>("current_y");
  const auto target_x = getInput<double>("target_x");
  const auto target_y = getInput<double>("target_y");
  const auto tolerance = getInput<double>("tolerance");
  const auto localization_valid = getInput<bool>("localization_valid");

  if(!current_x || !current_y || !target_x || !target_y || !tolerance ||
    !localization_valid || !finite(current_x.value()) || !finite(current_y.value()) ||
    !finite(target_x.value()) || !finite(target_y.value()) ||
    !finite(tolerance.value()) || tolerance.value() <= 0.0 || !localization_valid.value())
  {
    return BT::NodeStatus::FAILURE;
  }

  const double distance = std::hypot(
    current_x.value() - target_x.value(), current_y.value() - target_y.value());
  return finite(distance) && distance <= tolerance.value() ?
           BT::NodeStatus::SUCCESS : BT::NodeStatus::FAILURE;
}

MatchFinishedCondition::MatchFinishedCondition(
  const std::string & name, const BT::NodeConfig & config)
: BT::ConditionNode(name, config)
{
}

BT::PortsList MatchFinishedCondition::providedPorts()
{
  return {
    BT::InputPort<int>("game_period", 0, "0 before/after match, 1 preparation, 2 playing"),
    BT::InputPort<int>("time", 0, "Remaining time in the current phase")};
}

BT::NodeStatus MatchFinishedCondition::tick()
{
  const auto game_period = getInput<int>("game_period");
  const auto remaining_time = getInput<int>("time");
  if(!game_period || !remaining_time || game_period.value() < 0 ||
    game_period.value() > 2 || remaining_time.value() < 0)
  {
    return BT::NodeStatus::FAILURE;
  }

  const int current_period = game_period.value();
  const int current_time = remaining_time.value();
  const bool transitioned_to_zero =
    have_previous_period_ && previous_period_ == 2 && current_period == 0;

  if(current_period == 2)
  {
    has_started_ = true;
  }

  // time == 0 is meaningful only after the playing phase has been observed.
  const bool playing_time_expired =
    has_started_ && current_period == 2 && current_time == 0;
  if(has_started_ && (playing_time_expired || transitioned_to_zero))
  {
    match_finished_ = true;
  }

  previous_period_ = current_period;
  have_previous_period_ = true;

  return match_finished_ ? BT::NodeStatus::SUCCESS : BT::NodeStatus::FAILURE;
}

SetPostureAction::SetPostureAction(
  const std::string & name, const BT::NodeConfig & config)
: BT::SyncActionNode(name, config)
{
}

BT::PortsList SetPostureAction::providedPorts()
{
  return {
    BT::InputPort<int>("posture", 3, "1 attack, 2 defense, 3 movement"),
    BT::OutputPort<int>("posture_command")};
}

BT::NodeStatus SetPostureAction::tick()
{
  const auto posture = getInput<int>("posture");
  if(!posture || posture.value() < 1 || posture.value() > 3)
  {
    return BT::NodeStatus::FAILURE;
  }
  setOutput("posture_command", posture.value());
  return BT::NodeStatus::SUCCESS;
}

DisableGoalAction::DisableGoalAction(
  const std::string & name, const BT::NodeConfig & config)
: BT::SyncActionNode(name, config)
{
}

BT::PortsList DisableGoalAction::providedPorts()
{
  return {BT::OutputPort<bool>("goal_enabled")};
}

BT::NodeStatus DisableGoalAction::tick()
{
  setOutput("goal_enabled", false);
  return BT::NodeStatus::SUCCESS;
}

SendGoalPoseAction::SendGoalPoseAction(
  const std::string & name, const BT::NodeConfig & config)
: BT::StatefulActionNode(name, config)
{
}

BT::PortsList SendGoalPoseAction::providedPorts()
{
  return {
    BT::InputPort<double>("target_x"),
    BT::InputPort<double>("target_y"),
    BT::InputPort<double>("target_z", 1.0, "PoseStamped z; the task requires 1.0"),
    BT::InputPort<double>("target_yaw", 0.0, "Target yaw in radians"),
    BT::InputPort<std::string>("frame_id", "map", "Target reference frame"),
    BT::OutputPort<double>("goal_x"),
    BT::OutputPort<double>("goal_y"),
    BT::OutputPort<double>("goal_z"),
    BT::OutputPort<double>("goal_yaw"),
    BT::OutputPort<std::string>("goal_frame_id"),
    BT::OutputPort<bool>("goal_enabled")};
}

bool SendGoalPoseAction::readGoal()
{
  const auto target_x = getInput<double>("target_x");
  const auto target_y = getInput<double>("target_y");
  const auto target_z = getInput<double>("target_z");
  const auto target_yaw = getInput<double>("target_yaw");
  const auto frame_id = getInput<std::string>("frame_id");
  if(!target_x || !target_y || !target_z || !target_yaw || !frame_id ||
    !finite(target_x.value()) || !finite(target_y.value()) ||
    !finite(target_z.value()) || !finite(target_yaw.value()) ||
    std::abs(target_z.value() - 1.0) > 1e-9 || frame_id.value().empty())
  {
    return false;
  }

  target_x_ = target_x.value();
  target_y_ = target_y.value();
  target_z_ = target_z.value();
  target_yaw_ = target_yaw.value();
  frame_id_ = frame_id.value();
  return true;
}

void SendGoalPoseAction::publishGoal(bool enabled)
{
  setOutput("goal_x", target_x_);
  setOutput("goal_y", target_y_);
  setOutput("goal_z", target_z_);
  setOutput("goal_yaw", target_yaw_);
  setOutput("goal_frame_id", frame_id_);
  setOutput("goal_enabled", enabled);
}

BT::NodeStatus SendGoalPoseAction::onStart()
{
  if(!readGoal())
  {
    return BT::NodeStatus::FAILURE;
  }
  publishGoal(true);
  return BT::NodeStatus::RUNNING;
}

BT::NodeStatus SendGoalPoseAction::onRunning()
{
  // Re-publish on every tick so a transport adapter can publish the current
  // goal at its normal cadence without depending on action start callbacks.
  publishGoal(true);
  return BT::NodeStatus::RUNNING;
}

void SendGoalPoseAction::onHalted()
{
  publishGoal(false);
}

void registerNavigationNodes(BT::BehaviorTreeFactory & factory)
{
  factory.registerNodeType<PositionReachedCondition>("PositionReached");
  factory.registerNodeType<SetPostureAction>("SetPosture");
  factory.registerNodeType<DisableGoalAction>("DisableGoal");
  factory.registerNodeType<SendGoalPoseAction>("SendGoalPose");
}

void registerReturnHomeNodes(BT::BehaviorTreeFactory & factory)
{
  registerNavigationNodes(factory);
  factory.registerNodeType<MatchFinishedCondition>("MatchFinished");
}

}  // namespace decision_process
