#include "decision_process/behavior_tree_nodes.hpp"

#include <cmath>
#include <cstdint>
#include <chrono>
#include <memory>
#include <string>

#include "rclcpp/rclcpp.hpp"

#include "decision_process/attack_outpost_logic.hpp"
#include "decision_process/decision_process_node.hpp"
#include "decision_process/dodge_logic.hpp"
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

OutOfAmmoCondition::OutOfAmmoCondition(
  const std::string & name, const BT::NodeConfig & config,
  DecisionProcessNode & decision_node)
: BT::ConditionNode(name, config), decision_node_(decision_node) {}

BT::PortsList OutOfAmmoCondition::providedPorts() {return {};}

BT::NodeStatus OutOfAmmoCondition::tick()
{
  const RefereeState state = decision_node_.getRefereeState();
  return state.received && state.game_period == 2U &&
         state.sentry_hp > 0U && state.ammo == 0U ?
         BT::NodeStatus::SUCCESS : BT::NodeStatus::FAILURE;
}

PendingAmmoAvailableCondition::PendingAmmoAvailableCondition(
  const std::string & name, const BT::NodeConfig & config,
  DecisionProcessNode & decision_node)
: BT::ConditionNode(name, config), decision_node_(decision_node) {}

BT::PortsList PendingAmmoAvailableCondition::providedPorts()
{
  return {BT::OutputPort<int>("pending_ammo", "当前估算待领弹量")};
}

BT::NodeStatus PendingAmmoAvailableCondition::tick()
{
  const uint16_t pending_ammo = decision_node_.getPendingAmmo();
  setOutput("pending_ammo", static_cast<int>(pending_ammo));
  return pending_ammo > 0U ?
         BT::NodeStatus::SUCCESS : BT::NodeStatus::FAILURE;
}

NoEnemyVisibleCondition::NoEnemyVisibleCondition(
  const std::string & name, const BT::NodeConfig & config,
  DecisionProcessNode & decision_node)
: BT::ConditionNode(name, config), decision_node_(decision_node) {}

BT::PortsList NoEnemyVisibleCondition::providedPorts() {return {};}

BT::NodeStatus NoEnemyVisibleCondition::tick()
{
  return noVisibleEnemy(decision_node_.getAutoaimState()) ?
         BT::NodeStatus::SUCCESS : BT::NodeStatus::FAILURE;
}

RecentDamageCondition::RecentDamageCondition(
  const std::string & name, const BT::NodeConfig & config,
  DecisionProcessNode & decision_node)
: BT::ConditionNode(name, config), decision_node_(decision_node) {}

BT::PortsList RecentDamageCondition::providedPorts()
{
  return {BT::InputPort<double>("quiet_period_sec", 2.0, "停止受伤后的保持时间")};
}

BT::NodeStatus RecentDamageCondition::tick()
{
  const auto quiet_period = getInput<double>("quiet_period_sec");
  if (!quiet_period || quiet_period.value() < 0.0 ||
    !std::isfinite(quiet_period.value()))
  {
    return BT::NodeStatus::FAILURE;
  }
  return decision_node_.hasRecentDamage(quiet_period.value()) ?
         BT::NodeStatus::SUCCESS : BT::NodeStatus::FAILURE;
}

NavigationGoalReachedCondition::NavigationGoalReachedCondition(
  const std::string & name, const BT::NodeConfig & config,
  DecisionProcessNode & decision_node)
: BT::ConditionNode(name, config), decision_node_(decision_node) {}

BT::PortsList NavigationGoalReachedCondition::providedPorts() {return {};}

BT::NodeStatus NavigationGoalReachedCondition::tick()
{
  const NavigationCommand command = decision_node_.getNavigationCommand();
  return command.has_goal && command.reached ?
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
  command.has_goal = true;
  command.reached = false;
  command.frame_id = frame_id.value();
  command.x = goal_x_;
  command.y = goal_y_;
  command.yaw = yaw.value();
  decision_node_.setNavigationCommand(command);
  return evaluateGoal();
}

BT::NodeStatus NavigateToPoseAction::onRunning() {return evaluateGoal();}

void NavigateToPoseAction::onHalted()
{
  // A reactive control node may start a new navigation action before halting
  // this one. Do not clear the replacement command while cleaning up the old
  // goal.
  const NavigationCommand command = decision_node_.getNavigationCommand();
  if (command.enabled &&
    std::abs(command.x - goal_x_) <= 1e-9 &&
    std::abs(command.y - goal_y_) <= 1e-9)
  {
    disableNavigation(false);
  }
}

BT::NodeStatus NavigateToPoseAction::evaluateGoal()
{
  const LocalizationState state = decision_node_.getLocalizationState();
  if (!state.received) {
    return BT::NodeStatus::RUNNING;
  }
  if (goalReached(state.x, state.y, goal_x_, goal_y_, tolerance_)) {
    disableNavigation(true);
    return BT::NodeStatus::SUCCESS;
  }
  return BT::NodeStatus::RUNNING;
}

void NavigateToPoseAction::disableNavigation(bool reached)
{
  NavigationCommand command = decision_node_.getNavigationCommand();
  command.enabled = false;
  command.reached = reached;
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

SetCombatIdleAction::SetCombatIdleAction(
  const std::string & name, const BT::NodeConfig & config,
  DecisionProcessNode & decision_node)
: BT::SyncActionNode(name, config), decision_node_(decision_node) {}

BT::PortsList SetCombatIdleAction::providedPorts() {return {};}

BT::NodeStatus SetCombatIdleAction::tick()
{
  SerialCommand serial_command = decision_node_.getSerialCommand();
  serial_command.shoot_mode = 0U;
  serial_command.tripod_mode = 1U;
  decision_node_.setSerialCommand(serial_command);

  AutoaimCommand autoaim_command = decision_node_.getAutoaimCommand();
  autoaim_command.target = 0U;
  decision_node_.setAutoaimCommand(autoaim_command);
  return BT::NodeStatus::SUCCESS;
}

CollectPendingAmmoAction::CollectPendingAmmoAction(
  const std::string & name, const BT::NodeConfig & config,
  DecisionProcessNode & decision_node)
: BT::StatefulActionNode(name, config), decision_node_(decision_node) {}

BT::PortsList CollectPendingAmmoAction::providedPorts()
{
  return {
    BT::InputPort<double>("x", 2.0, "补给点x坐标"),
    BT::InputPort<double>("y", 1.0, "补给点y坐标"),
    BT::InputPort<double>("z", 1.0, "导航目标z坐标"),
    BT::InputPort<double>("yaw", 0.0, "补给点目标朝向"),
    BT::InputPort<std::string>("frame_id", "map", "导航参考坐标系"),
    BT::InputPort<double>("tolerance", 0.15, "补给点到达容差")};
}

BT::NodeStatus CollectPendingAmmoAction::onStart()
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
    RCLCPP_ERROR(decision_node_.get_logger(), "CollectPendingAmmo received invalid ports");
    return BT::NodeStatus::FAILURE;
  }

  supply_x_ = x.value();
  supply_y_ = y.value();
  supply_yaw_ = yaw.value();
  frame_id_ = frame_id.value();
  tolerance_ = tolerance.value();
  reached_supply_ = false;
  decision_node_.cancelAmmoPickupWait();
  publishSupplyGoal();
  return updatePickup();
}

BT::NodeStatus CollectPendingAmmoAction::onRunning() {return updatePickup();}

void CollectPendingAmmoAction::onHalted()
{
  decision_node_.cancelAmmoPickupWait();
  disableNavigation(reached_supply_);
}

BT::NodeStatus CollectPendingAmmoAction::updatePickup()
{
  const RefereeState referee = decision_node_.getRefereeState();
  if (referee.received && referee.ammo > 0U) {
    decision_node_.cancelAmmoPickupWait();
    disableNavigation(reached_supply_);
    return BT::NodeStatus::SUCCESS;
  }

  const LocalizationState localization = decision_node_.getLocalizationState();
  if (localization.received && goalReached(
      localization.x, localization.y, supply_x_, supply_y_, tolerance_))
  {
    if (!reached_supply_) {
      reached_supply_ = true;
      decision_node_.beginAmmoPickupWait();
      disableNavigation(true);
    }
    return BT::NodeStatus::RUNNING;
  }

  if (reached_supply_) {
    reached_supply_ = false;
    decision_node_.cancelAmmoPickupWait();
    publishSupplyGoal();
  }
  return BT::NodeStatus::RUNNING;
}

void CollectPendingAmmoAction::publishSupplyGoal()
{
  NavigationCommand command;
  command.enabled = true;
  command.has_goal = true;
  command.reached = false;
  command.frame_id = frame_id_;
  command.x = supply_x_;
  command.y = supply_y_;
  command.yaw = supply_yaw_;
  decision_node_.setNavigationCommand(command);
}

void CollectPendingAmmoAction::disableNavigation(bool reached)
{
  NavigationCommand command = decision_node_.getNavigationCommand();
  command.enabled = false;
  command.reached = reached;
  decision_node_.setNavigationCommand(command);
}

EvadeUntilSafeAction::EvadeUntilSafeAction(
  const std::string & name, const BT::NodeConfig & config,
  DecisionProcessNode & decision_node)
: BT::StatefulActionNode(name, config), decision_node_(decision_node) {}

BT::PortsList EvadeUntilSafeAction::providedPorts()
{
  return {
    BT::InputPort<double>("quiet_period_sec", 2.0, "最后一次受伤后的躲避保持时间"),
    BT::InputPort<double>("step", 0.8, "单次躲避移动距离"),
    BT::InputPort<double>("tolerance", 0.15, "躲避目标到达容差"),
    BT::InputPort<double>("min_x", 0.2, "允许目标最小x"),
    BT::InputPort<double>("max_x", 27.8, "允许目标最大x"),
    BT::InputPort<double>("min_y", 0.2, "允许目标最小y"),
    BT::InputPort<double>("max_y", 14.8, "允许目标最大y"),
    BT::InputPort<std::string>("frame_id", "map", "导航参考坐标系")};
}

BT::NodeStatus EvadeUntilSafeAction::onStart()
{
  const auto quiet_period = getInput<double>("quiet_period_sec");
  const auto step = getInput<double>("step");
  const auto tolerance = getInput<double>("tolerance");
  const auto min_x = getInput<double>("min_x");
  const auto max_x = getInput<double>("max_x");
  const auto min_y = getInput<double>("min_y");
  const auto max_y = getInput<double>("max_y");
  const auto frame_id = getInput<std::string>("frame_id");
  if (!quiet_period || !step || !tolerance || !min_x || !max_x ||
    !min_y || !max_y || !frame_id ||
    !std::isfinite(quiet_period.value()) || !std::isfinite(step.value()) ||
    !std::isfinite(tolerance.value()) || !std::isfinite(min_x.value()) ||
    !std::isfinite(max_x.value()) || !std::isfinite(min_y.value()) ||
    !std::isfinite(max_y.value()) || quiet_period.value() < 0.0 ||
    step.value() <= 0.0 || tolerance.value() <= 0.0 ||
    min_x.value() >= max_x.value() || min_y.value() >= max_y.value() ||
    frame_id.value().empty())
  {
    RCLCPP_ERROR(decision_node_.get_logger(), "EvadeUntilSafe received invalid ports");
    return BT::NodeStatus::FAILURE;
  }

  quiet_period_seconds_ = quiet_period.value();
  step_ = step.value();
  tolerance_ = tolerance.value();
  min_x_ = min_x.value();
  max_x_ = max_x.value();
  min_y_ = min_y.value();
  max_y_ = max_y.value();
  frame_id_ = frame_id.value();
  goal_active_ = false;
  return updateEvasion();
}

BT::NodeStatus EvadeUntilSafeAction::onRunning() {return updateEvasion();}

void EvadeUntilSafeAction::onHalted() {disableNavigation();}

BT::NodeStatus EvadeUntilSafeAction::updateEvasion()
{
  const RefereeState referee = decision_node_.getRefereeState();
  const AutoaimState autoaim = decision_node_.getAutoaimState();
  const bool should_continue =
    referee.received && referee.game_period == 2U && referee.sentry_hp > 0U &&
    noVisibleEnemy(autoaim) &&
    decision_node_.hasRecentDamage(quiet_period_seconds_);
  if (!should_continue) {
    disableNavigation();
    return BT::NodeStatus::FAILURE;
  }

  const LocalizationState localization = decision_node_.getLocalizationState();
  if (!localization.received) {
    return BT::NodeStatus::RUNNING;
  }

  if (!goal_active_ || goalReached(
      localization.x, localization.y, goal_x_, goal_y_, tolerance_))
  {
    if (!publishNextGoal(localization)) {
      RCLCPP_ERROR_THROTTLE(
        decision_node_.get_logger(), *decision_node_.get_clock(), 2000,
        "Unable to find a valid evasion goal inside map bounds");
      disableNavigation();
      return BT::NodeStatus::FAILURE;
    }
  }
  return BT::NodeStatus::RUNNING;
}

bool EvadeUntilSafeAction::publishNextGoal(const LocalizationState & localization)
{
  for (std::size_t attempt = 0U; attempt < 4U; ++attempt) {
    const EvasionGoal candidate = makeEvasionGoal(
      localization.x, localization.y, step_, direction_index_,
      min_x_, max_x_, min_y_, max_y_);
    ++direction_index_;
    if (!candidate.valid) {
      continue;
    }

    goal_x_ = candidate.x;
    goal_y_ = candidate.y;
    goal_active_ = true;
    NavigationCommand command;
    command.enabled = true;
    command.has_goal = true;
    command.reached = false;
    command.frame_id = frame_id_;
    command.x = goal_x_;
    command.y = goal_y_;
    command.yaw = localization.yaw;
    decision_node_.setNavigationCommand(command);
    return true;
  }
  return false;
}

void EvadeUntilSafeAction::disableNavigation()
{
  NavigationCommand command = decision_node_.getNavigationCommand();
  command.enabled = false;
  command.reached = false;
  decision_node_.setNavigationCommand(command);
  goal_active_ = false;
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
  factory.registerBuilder<OutOfAmmoCondition>(
    "OutOfAmmo",
    [&decision_node](const std::string & name, const BT::NodeConfig & config) {
      return std::make_unique<OutOfAmmoCondition>(name, config, decision_node);
    });
  factory.registerBuilder<PendingAmmoAvailableCondition>(
    "PendingAmmoAvailable",
    [&decision_node](const std::string & name, const BT::NodeConfig & config) {
      return std::make_unique<PendingAmmoAvailableCondition>(name, config, decision_node);
    });
  factory.registerBuilder<NoEnemyVisibleCondition>(
    "NoEnemyVisible",
    [&decision_node](const std::string & name, const BT::NodeConfig & config) {
      return std::make_unique<NoEnemyVisibleCondition>(name, config, decision_node);
    });
  factory.registerBuilder<RecentDamageCondition>(
    "RecentDamage",
    [&decision_node](const std::string & name, const BT::NodeConfig & config) {
      return std::make_unique<RecentDamageCondition>(name, config, decision_node);
    });
  factory.registerBuilder<NavigationGoalReachedCondition>(
    "NavigationGoalReached",
    [&decision_node](const std::string & name, const BT::NodeConfig & config) {
      return std::make_unique<NavigationGoalReachedCondition>(name, config, decision_node);
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
  factory.registerBuilder<SetCombatIdleAction>(
    "SetCombatIdle",
    [&decision_node](const std::string & name, const BT::NodeConfig & config) {
      return std::make_unique<SetCombatIdleAction>(name, config, decision_node);
    });
  factory.registerBuilder<CollectPendingAmmoAction>(
    "CollectPendingAmmo",
    [&decision_node](const std::string & name, const BT::NodeConfig & config) {
      return std::make_unique<CollectPendingAmmoAction>(name, config, decision_node);
    });
  factory.registerBuilder<EvadeUntilSafeAction>(
    "EvadeUntilSafe",
    [&decision_node](const std::string & name, const BT::NodeConfig & config) {
      return std::make_unique<EvadeUntilSafeAction>(name, config, decision_node);
    });
}

}  // namespace decision_process
