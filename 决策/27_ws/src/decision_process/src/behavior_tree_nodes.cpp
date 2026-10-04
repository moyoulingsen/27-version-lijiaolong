#include "decision_process/behavior_tree_nodes.hpp"

#include <cmath>
#include <cstdint>
#include <chrono>
#include <memory>
#include <string>

#include "rclcpp/rclcpp.hpp"

#include "decision_process/attack_outpost_logic.hpp"
#include "decision_process/decision_process_node.hpp"
#include "decision_process/return_home_logic.hpp"

namespace decision_process
{

GameFinishedCondition::GameFinishedCondition(
  const std::string & name, const BT::NodeConfig & config,
  DecisionProcessNode & decision_node)
: BT::ConditionNode(name, config), decision_node_(decision_node) {}

BT::PortsList GameFinishedCondition::providedPorts() {return {};}

BT::NodeStatus GameFinishedCondition::tick()
{
  return decision_node_.isGameFinished() ?
         BT::NodeStatus::SUCCESS : BT::NodeStatus::FAILURE;
}

SentryAliveCondition::SentryAliveCondition(
  const std::string & name, const BT::NodeConfig & config,
  DecisionProcessNode & decision_node)
: BT::ConditionNode(name, config), decision_node_(decision_node) {}

BT::PortsList SentryAliveCondition::providedPorts() {return {};}

BT::NodeStatus SentryAliveCondition::tick()
{
  const RefereeState state = decision_node_.getRefereeState();
  return state.received && state.sentry_hp > 0U ?
         BT::NodeStatus::SUCCESS : BT::NodeStatus::FAILURE;
}

GameRunningCondition::GameRunningCondition(
  const std::string & name, const BT::NodeConfig & config,
  DecisionProcessNode & decision_node)
: BT::ConditionNode(name, config), decision_node_(decision_node) {}

BT::PortsList GameRunningCondition::providedPorts() {return {};}

BT::NodeStatus GameRunningCondition::tick()
{
  const RefereeState state = decision_node_.getRefereeState();
  return state.received && state.game_period == 2U && state.sentry_hp > 0U ?
         BT::NodeStatus::SUCCESS : BT::NodeStatus::FAILURE;
}

EnemyOutpostAliveCondition::EnemyOutpostAliveCondition(
  const std::string & name, const BT::NodeConfig & config,
  DecisionProcessNode & decision_node)
: BT::ConditionNode(name, config), decision_node_(decision_node) {}

BT::PortsList EnemyOutpostAliveCondition::providedPorts() {return {};}

BT::NodeStatus EnemyOutpostAliveCondition::tick()
{
  const RefereeState state = decision_node_.getRefereeState();
  const EnemyOutpostStatus status = enemyOutpostStatus(
    state.received, state.enemy_hp_valid, state.enemy_hp[kEnemyOutpostHpIndex]);
  return status == EnemyOutpostStatus::kAlive ?
         BT::NodeStatus::SUCCESS : BT::NodeStatus::FAILURE;
}

EnemyOutpostDestroyedCondition::EnemyOutpostDestroyedCondition(
  const std::string & name, const BT::NodeConfig & config,
  DecisionProcessNode & decision_node)
: BT::ConditionNode(name, config), decision_node_(decision_node) {}

BT::PortsList EnemyOutpostDestroyedCondition::providedPorts() {return {};}

BT::NodeStatus EnemyOutpostDestroyedCondition::tick()
{
  const RefereeState state = decision_node_.getRefereeState();
  const EnemyOutpostStatus status = enemyOutpostStatus(
    state.received, state.enemy_hp_valid, state.enemy_hp[kEnemyOutpostHpIndex]);
  return status == EnemyOutpostStatus::kDestroyed ?
         BT::NodeStatus::SUCCESS : BT::NodeStatus::FAILURE;
}

SetPostureAction::SetPostureAction(
  const std::string & name, const BT::NodeConfig & config,
  DecisionProcessNode & decision_node)
: BT::SyncActionNode(name, config), decision_node_(decision_node) {}

BT::PortsList SetPostureAction::providedPorts()
{
  return {BT::InputPort<int>("posture", 3, "1进攻、2防御、3移动")};
}

BT::NodeStatus SetPostureAction::tick()
{
  const auto posture = getInput<int>("posture");
  if (!posture || posture.value() < 1 || posture.value() > 3) {
    RCLCPP_ERROR(decision_node_.get_logger(), "SetPosture requires posture in range 1..3");
    return BT::NodeStatus::FAILURE;
  }
  SerialCommand command = decision_node_.getSerialCommand();
  command.posture = static_cast<uint8_t>(posture.value());
  decision_node_.setSerialCommand(command);
  return BT::NodeStatus::SUCCESS;
}

NavigateToPoseAction::NavigateToPoseAction(
  const std::string & name, const BT::NodeConfig & config,
  DecisionProcessNode & decision_node)
: BT::StatefulActionNode(name, config), decision_node_(decision_node) {}

BT::PortsList NavigateToPoseAction::providedPorts()
{
  return {
    BT::InputPort<double>("x", "目标地图x坐标"),
    BT::InputPort<double>("y", "目标地图y坐标"),
    BT::InputPort<double>("z", 1.0, "目标z坐标，任务要求恒为1.0"),
    BT::InputPort<double>("yaw", 0.0, "目标朝向角"),
    BT::InputPort<std::string>("frame_id", "map", "目标参考坐标系"),
    BT::InputPort<double>("tolerance", 0.15, "到达判定平面距离")};
}

BT::NodeStatus NavigateToPoseAction::onStart()
{
  const auto x = getInput<double>("x");
  const auto y = getInput<double>("y");
  const auto z = getInput<double>("z");
  const auto yaw = getInput<double>("yaw");
  const auto frame_id = getInput<std::string>("frame_id");
  const auto tolerance = getInput<double>("tolerance");
  if (!x || !y || !z || !yaw || !frame_id || !tolerance ||
    !std::isfinite(x.value()) || !std::isfinite(y.value()) ||
    !std::isfinite(yaw.value()) || tolerance.value() <= 0.0 ||
    frame_id.value().empty() || std::abs(z.value() - 1.0) > 1e-6)
  {
    RCLCPP_ERROR(decision_node_.get_logger(), "NavigateToPose received invalid goal ports");
    return BT::NodeStatus::FAILURE;
  }

  goal_x_ = x.value();
  goal_y_ = y.value();
  tolerance_ = tolerance.value();
  NavigationCommand command;
  command.enabled = true;
  command.frame_id = frame_id.value();
  command.x = goal_x_;
  command.y = goal_y_;
  command.yaw = yaw.value();
  decision_node_.setNavigationCommand(command);
  return evaluateGoal();
}

BT::NodeStatus NavigateToPoseAction::onRunning() {return evaluateGoal();}

void NavigateToPoseAction::onHalted() {disableNavigation();}

BT::NodeStatus NavigateToPoseAction::evaluateGoal()
{
  const LocalizationState state = decision_node_.getLocalizationState();
  if (!state.received) {
    return BT::NodeStatus::RUNNING;
  }
  if (goalReached(state.x, state.y, goal_x_, goal_y_, tolerance_)) {
    disableNavigation();
    return BT::NodeStatus::SUCCESS;
  }
  return BT::NodeStatus::RUNNING;
}

void NavigateToPoseAction::disableNavigation()
{
  NavigationCommand command = decision_node_.getNavigationCommand();
  command.enabled = false;
  decision_node_.setNavigationCommand(command);
}

ApplyPostureAction::ApplyPostureAction(
  const std::string & name, const BT::NodeConfig & config,
  DecisionProcessNode & decision_node)
: BT::SyncActionNode(name, config),
  decision_node_(decision_node),
  policy_(decision_node.getSerialCommand().posture)
{
}

BT::PortsList ApplyPostureAction::providedPorts()
{
  return {
    BT::InputPort<int>("requested_posture", 3, "1进攻、2防御、3移动"),
    BT::InputPort<double>("cooldown_sec", 5.0, "姿态切换冷却时间"),
    BT::OutputPort<int>("applied_posture", "当前实际姿态")};
}

BT::NodeStatus ApplyPostureAction::tick()
{
  const auto requested = getInput<int>("requested_posture");
  const auto cooldown = getInput<double>("cooldown_sec");
  if (!requested || !cooldown || requested.value() < 0 || requested.value() > 255) {
    return BT::NodeStatus::FAILURE;
  }

  const double now_seconds = std::chrono::duration<double>(
    std::chrono::steady_clock::now().time_since_epoch()).count();
  const PostureDecision decision = policy_.request(
    static_cast<uint8_t>(requested.value()), now_seconds, cooldown.value());
  if (decision == PostureDecision::kInvalid) {
    RCLCPP_ERROR(decision_node_.get_logger(), "ApplyPosture received invalid ports");
    return BT::NodeStatus::FAILURE;
  }
  if (decision == PostureDecision::kSwitched) {
    SerialCommand command = decision_node_.getSerialCommand();
    command.posture = policy_.currentPosture();
    decision_node_.setSerialCommand(command);
    RCLCPP_INFO(
      decision_node_.get_logger(), "Posture switched to %u",
      static_cast<unsigned int>(command.posture));
  }
  setOutput("applied_posture", static_cast<int>(policy_.currentPosture()));
  return BT::NodeStatus::SUCCESS;
}

EngageOutpostAction::EngageOutpostAction(
  const std::string & name, const BT::NodeConfig & config,
  DecisionProcessNode & decision_node)
: BT::StatefulActionNode(name, config), decision_node_(decision_node) {}

BT::PortsList EngageOutpostAction::providedPorts()
{
  return {BT::InputPort<int>("target", 6, "敌方前哨站目标编号")};
}

BT::NodeStatus EngageOutpostAction::onStart()
{
  const auto target = getInput<int>("target");
  if (!target || target.value() != static_cast<int>(kEnemyOutpostTarget)) {
    RCLCPP_ERROR(decision_node_.get_logger(), "EngageOutpost target must be 6");
    return BT::NodeStatus::FAILURE;
  }
  target_ = static_cast<uint8_t>(target.value());
  return updateCommand();
}

BT::NodeStatus EngageOutpostAction::onRunning() {return updateCommand();}

void EngageOutpostAction::onHalted() {clearCommand();}

BT::NodeStatus EngageOutpostAction::updateCommand()
{
  const RefereeState referee = decision_node_.getRefereeState();
  const EnemyOutpostStatus status = enemyOutpostStatus(
    referee.received, referee.enemy_hp_valid,
    referee.enemy_hp[kEnemyOutpostHpIndex]);
  if (status == EnemyOutpostStatus::kUnknown) {
    clearCommand();
    return BT::NodeStatus::RUNNING;
  }
  if (status == EnemyOutpostStatus::kDestroyed) {
    clearCommand();
    return BT::NodeStatus::SUCCESS;
  }

  const AutoaimState autoaim = decision_node_.getAutoaimState();
  const OutpostEngagementDecision decision = decideOutpostEngagement(
    referee.team_color, referee.ammo, autoaim.received,
    autoaim.target[kEnemyOutpostTargetIndex],
    autoaim.target_distance[kEnemyOutpostTargetIndex]);
  if (!decision.valid) {
    clearCommand();
    RCLCPP_ERROR_THROTTLE(
      decision_node_.get_logger(), *decision_node_.get_clock(), 2000,
      "EngageOutpost received invalid team color %u",
      static_cast<unsigned int>(referee.team_color));
    return BT::NodeStatus::FAILURE;
  }

  AutoaimCommand autoaim_command = decision_node_.getAutoaimCommand();
  autoaim_command.color = decision.target_color;
  autoaim_command.target = target_;
  autoaim_command.decide_yaw = 0.0F;
  decision_node_.setAutoaimCommand(autoaim_command);

  SerialCommand serial_command = decision_node_.getSerialCommand();
  serial_command.tripod_mode = decision.tripod_mode;
  serial_command.shoot_mode = decision.shoot_mode;
  decision_node_.setSerialCommand(serial_command);
  return BT::NodeStatus::RUNNING;
}

void EngageOutpostAction::clearCommand()
{
  AutoaimCommand autoaim_command = decision_node_.getAutoaimCommand();
  if (autoaim_command.target == target_) {
    autoaim_command.target = 0U;
  }
  decision_node_.setAutoaimCommand(autoaim_command);

  SerialCommand serial_command = decision_node_.getSerialCommand();
  serial_command.shoot_mode = 0U;
  serial_command.tripod_mode = 1U;
  decision_node_.setSerialCommand(serial_command);
}

void registerDecisionNodes(
  BT::BehaviorTreeFactory & factory, DecisionProcessNode & decision_node)
{
  factory.registerBuilder<GameFinishedCondition>(
    "GameFinished",
    [&decision_node](const std::string & name, const BT::NodeConfig & config) {
      return std::make_unique<GameFinishedCondition>(name, config, decision_node);
    });
  factory.registerBuilder<SentryAliveCondition>(
    "SentryAlive",
    [&decision_node](const std::string & name, const BT::NodeConfig & config) {
      return std::make_unique<SentryAliveCondition>(name, config, decision_node);
    });
  factory.registerBuilder<GameRunningCondition>(
    "GameRunning",
    [&decision_node](const std::string & name, const BT::NodeConfig & config) {
      return std::make_unique<GameRunningCondition>(name, config, decision_node);
    });
  factory.registerBuilder<EnemyOutpostAliveCondition>(
    "EnemyOutpostAlive",
    [&decision_node](const std::string & name, const BT::NodeConfig & config) {
      return std::make_unique<EnemyOutpostAliveCondition>(name, config, decision_node);
    });
  factory.registerBuilder<EnemyOutpostDestroyedCondition>(
    "EnemyOutpostDestroyed",
    [&decision_node](const std::string & name, const BT::NodeConfig & config) {
      return std::make_unique<EnemyOutpostDestroyedCondition>(name, config, decision_node);
    });
  factory.registerBuilder<SetPostureAction>(
    "SetPosture",
    [&decision_node](const std::string & name, const BT::NodeConfig & config) {
      return std::make_unique<SetPostureAction>(name, config, decision_node);
    });
  factory.registerBuilder<NavigateToPoseAction>(
    "NavigateToPose",
    [&decision_node](const std::string & name, const BT::NodeConfig & config) {
      return std::make_unique<NavigateToPoseAction>(name, config, decision_node);
    });
  factory.registerBuilder<ApplyPostureAction>(
    "ApplyPosture",
    [&decision_node](const std::string & name, const BT::NodeConfig & config) {
      return std::make_unique<ApplyPostureAction>(name, config, decision_node);
    });
  factory.registerBuilder<EngageOutpostAction>(
    "EngageOutpost",
    [&decision_node](const std::string & name, const BT::NodeConfig & config) {
      return std::make_unique<EngageOutpostAction>(name, config, decision_node);
    });
}

}  // namespace decision_process
