#include "attack_nodes.hpp"

#include <algorithm>
#include <cmath>
#include <iomanip>
#include <limits>
#include <sstream>
#include <string>
#include <unordered_map>
#include <vector>

namespace decision_process
{
namespace
{

struct Target
{
  std::string id;
  double health{0.0};
  double distance{0.0};
  bool in_range{false};
  bool invincible{false};
  bool persistent{false};
};

bool finite(double value)
{
  return std::isfinite(value);
}

bool parseBool(const std::string & text, bool & value)
{
  if(text == "0" || text == "false")
  {
    value = false;
    return true;
  }
  if(text == "1" || text == "true")
  {
    value = true;
    return true;
  }
  return false;
}

bool parseDouble(const std::string & text, double & value)
{
  try
  {
    std::size_t consumed = 0;
    value = std::stod(text, &consumed);
    return consumed == text.size() && finite(value);
  }
  catch(...)
  {
    return false;
  }
}

std::vector<std::string> split(const std::string & text, char separator)
{
  std::vector<std::string> result;
  std::size_t begin = 0;
  while(begin <= text.size())
  {
    const auto end = text.find(separator, begin);
    result.push_back(text.substr(begin, end == std::string::npos ? std::string::npos : end - begin));
    if(end == std::string::npos)
    {
      break;
    }
    begin = end + 1;
  }
  return result;
}

bool parseTarget(const std::string & text, Target & target)
{
  const auto fields = split(text, ':');
  if(fields.size() != 6 || fields[0].empty() || !parseDouble(fields[1], target.health) ||
    !parseDouble(fields[2], target.distance) || !parseBool(fields[3], target.in_range) ||
    !parseBool(fields[4], target.invincible) || !parseBool(fields[5], target.persistent) ||
    target.health < 0.0 || target.distance < 0.0)
  {
    return false;
  }
  target.id = fields[0];
  return true;
}

bool parseTargets(const std::string & text, std::vector<Target> & targets)
{
  if(text.empty())
  {
    return true;
  }
  for(const auto & item : split(text, ';'))
  {
    if(item.empty())
    {
      return false;
    }
    Target target;
    if(!parseTarget(item, target))
    {
      return false;
    }
    targets.push_back(target);
  }
  return true;
}

std::string serializeTargets(const std::vector<Target> & targets)
{
  std::ostringstream stream;
  stream << std::setprecision(15);
  for(std::size_t index = 0; index < targets.size(); ++index)
  {
    if(index != 0)
    {
      stream << ';';
    }
    const auto & target = targets[index];
    stream << target.id << ':' << target.health << ':' << target.distance << ':'
           << (target.in_range ? 1 : 0) << ':' << (target.invincible ? 1 : 0) << ':'
           << (target.persistent ? 1 : 0);
  }
  return stream.str();
}

bool readTargetList(BT::TreeNode & node, const char * port, std::vector<Target> & targets)
{
  const auto text = node.getInput<std::string>(port);
  return text && parseTargets(text.value(), targets);
}

}  // namespace

ConfigureAttackAction::ConfigureAttackAction(
  const std::string & name, const BT::NodeConfig & config)
: BT::SyncActionNode(name, config)
{
}

BT::PortsList ConfigureAttackAction::providedPorts()
{
  return {
    BT::InputPort<int>("posture", 1, "Attack posture"),
    BT::InputPort<int>("gyro_mode", 2, "0 off, 1 low, 2 medium, 3 high"),
    BT::InputPort<bool>("gimbal_enabled", false, "Whether the gimbal is enabled"),
    BT::OutputPort<int>("posture_command"),
    BT::OutputPort<int>("gyro_mode_command"),
    BT::OutputPort<bool>("gimbal_enabled_command")};
}

BT::NodeStatus ConfigureAttackAction::tick()
{
  const auto posture = getInput<int>("posture");
  const auto gyro_mode = getInput<int>("gyro_mode");
  const auto gimbal_enabled = getInput<bool>("gimbal_enabled");
  if(!posture || !gyro_mode || !gimbal_enabled || posture.value() < 1 || posture.value() > 3 ||
    gyro_mode.value() < 0 || gyro_mode.value() > 3)
  {
    return BT::NodeStatus::FAILURE;
  }
  setOutput("posture_command", posture.value());
  setOutput("gyro_mode_command", gyro_mode.value());
  setOutput("gimbal_enabled_command", gimbal_enabled.value());
  return BT::NodeStatus::SUCCESS;
}

BuildAttackTargetListAction::BuildAttackTargetListAction(
  const std::string & name, const BT::NodeConfig & config)
: BT::SyncActionNode(name, config)
{
}

BT::PortsList BuildAttackTargetListAction::providedPorts()
{
  return {
    BT::InputPort<std::string>("targets", "Observed targets"),
    BT::InputPort<std::string>("persistent_targets", "Persistent or preset targets"),
    BT::OutputPort<std::string>("attack_targets"),
    BT::OutputPort<int>("target_count"),
    BT::OutputPort<int>("visible_target_count"),
    BT::OutputPort<int>("in_range_count"),
    BT::OutputPort<bool>("has_in_range"),
    BT::OutputPort<bool>("all_out_of_range")};
}

BT::NodeStatus BuildAttackTargetListAction::tick()
{
  const auto observed = getInput<std::string>("targets");
  const auto persistent = getInput<std::string>("persistent_targets");
  if(!observed || !persistent)
  {
    return BT::NodeStatus::FAILURE;
  }

  std::vector<Target> parsed;
  if(!parseTargets(persistent.value(), parsed))
  {
    return BT::NodeStatus::FAILURE;
  }
  std::unordered_map<std::string, std::size_t> positions;
  for(std::size_t index = 0; index < parsed.size(); ++index)
  {
    positions[parsed[index].id] = index;
  }

  std::vector<Target> observed_targets;
  if(!parseTargets(observed.value(), observed_targets))
  {
    return BT::NodeStatus::FAILURE;
  }
  const int visible_target_count = static_cast<int>(observed_targets.size());
  for(const auto & target : observed_targets)
  {
    const auto position = positions.find(target.id);
    if(position == positions.end())
    {
      positions[target.id] = parsed.size();
      parsed.push_back(target);
    }
    else
    {
      parsed[position->second] = target;
    }
  }

  std::vector<Target> valid;
  int in_range_count = 0;
  for(const auto & target : parsed)
  {
    if(target.invincible)
    {
      continue;
    }
    valid.push_back(target);
    if(target.in_range)
    {
      ++in_range_count;
    }
  }

  setOutput("attack_targets", serializeTargets(valid));
  setOutput("target_count", static_cast<int>(valid.size()));
  setOutput("visible_target_count", visible_target_count);
  setOutput("in_range_count", in_range_count);
  setOutput("has_in_range", in_range_count > 0);
  setOutput("all_out_of_range", !valid.empty() && in_range_count == 0);
  return BT::NodeStatus::SUCCESS;
}

SelectAttackTargetAction::SelectAttackTargetAction(
  const std::string & name, const BT::NodeConfig & config)
: BT::SyncActionNode(name, config)
{
}

BT::PortsList SelectAttackTargetAction::providedPorts()
{
  return {
    BT::InputPort<std::string>("attack_targets"),
    BT::InputPort<double>("low_health_threshold", 50.0, "Low-health priority threshold"),
    BT::InputPort<bool>("require_in_range", true, "Only select targets in weapon range"),
    BT::OutputPort<std::string>("selected_target_id"),
    BT::OutputPort<double>("selected_health"),
    BT::OutputPort<double>("selected_distance"),
    BT::OutputPort<bool>("selected_in_range"),
    BT::OutputPort<bool>("target_selected")};
}

BT::NodeStatus SelectAttackTargetAction::tick()
{
  const auto threshold = getInput<double>("low_health_threshold");
  const auto require_in_range = getInput<bool>("require_in_range");
  if(!threshold || !require_in_range || !finite(threshold.value()) || threshold.value() < 0.0)
  {
    return BT::NodeStatus::FAILURE;
  }
  std::vector<Target> targets;
  if(!readTargetList(*this, "attack_targets", targets))
  {
    return BT::NodeStatus::FAILURE;
  }

  const Target * selected = nullptr;
  for(const auto & target : targets)
  {
    if(target.invincible || (require_in_range.value() && !target.in_range))
    {
      continue;
    }
    if(selected == nullptr)
    {
      selected = &target;
      continue;
    }
    const bool target_is_low = target.health < threshold.value();
    const bool selected_is_low = selected->health < threshold.value();
    if(target_is_low != selected_is_low ? target_is_low : target.distance < selected->distance)
    {
      selected = &target;
    }
  }

  if(selected == nullptr)
  {
    setOutput("target_selected", false);
    return BT::NodeStatus::FAILURE;
  }
  setOutput("selected_target_id", selected->id);
  setOutput("selected_health", selected->health);
  setOutput("selected_distance", selected->distance);
  setOutput("selected_in_range", selected->in_range);
  setOutput("target_selected", true);
  return BT::NodeStatus::SUCCESS;
}

HasAttackTargetsCondition::HasAttackTargetsCondition(
  const std::string & name, const BT::NodeConfig & config)
: BT::ConditionNode(name, config)
{
}

BT::PortsList HasAttackTargetsCondition::providedPorts()
{
  return {BT::InputPort<int>("target_count", 0, "Number of valid targets")};
}

BT::NodeStatus HasAttackTargetsCondition::tick()
{
  const auto count = getInput<int>("target_count");
  return count && count.value() > 0 ? BT::NodeStatus::SUCCESS : BT::NodeStatus::FAILURE;
}

HasInRangeTargetCondition::HasInRangeTargetCondition(
  const std::string & name, const BT::NodeConfig & config)
: BT::ConditionNode(name, config)
{
}

BT::PortsList HasInRangeTargetCondition::providedPorts()
{
  return {BT::InputPort<int>("in_range_count", 0, "Number of targets in range")};
}

BT::NodeStatus HasInRangeTargetCondition::tick()
{
  const auto count = getInput<int>("in_range_count");
  return count && count.value() > 0 ? BT::NodeStatus::SUCCESS : BT::NodeStatus::FAILURE;
}

EvadeEligibleCondition::EvadeEligibleCondition(
  const std::string & name, const BT::NodeConfig & config)
: BT::ConditionNode(name, config)
{
}

BT::PortsList EvadeEligibleCondition::providedPorts()
{
  return {
    BT::InputPort<int>("visible_enemy_count", 0, "Number of visible enemy units"),
    BT::InputPort<bool>("health_decreased", false, "Whether a new health drop was observed"),
    BT::InputPort<bool>("at_target", false, "Whether the robot is stationary at a goal"),
    BT::InputPort<double>("no_damage_seconds", 0.0, "Time since the last damage event"),
    BT::InputPort<double>("recovery_seconds", 5.0, "Time without damage required to recover")};
}

BT::NodeStatus EvadeEligibleCondition::tick()
{
  const auto visible_enemy_count = getInput<int>("visible_enemy_count");
  const auto health_decreased = getInput<bool>("health_decreased");
  const auto at_target = getInput<bool>("at_target");
  const auto no_damage_seconds = getInput<double>("no_damage_seconds");
  const auto recovery_seconds = getInput<double>("recovery_seconds");
  if(!visible_enemy_count || !health_decreased || !at_target || !no_damage_seconds ||
    !recovery_seconds || visible_enemy_count.value() < 0 ||
    !finite(no_damage_seconds.value()) || !finite(recovery_seconds.value()) ||
    no_damage_seconds.value() < 0.0 || recovery_seconds.value() <= 0.0)
  {
    return BT::NodeStatus::FAILURE;
  }

  if(health_decreased.value())
  {
    damage_latched_ = true;
  }
  if(no_damage_seconds.value() >= recovery_seconds.value())
  {
    damage_latched_ = false;
  }

  return damage_latched_ && visible_enemy_count.value() == 0 && at_target.value() ?
           BT::NodeStatus::SUCCESS : BT::NodeStatus::FAILURE;
}

AimAndFireAction::AimAndFireAction(
  const std::string & name, const BT::NodeConfig & config)
: BT::StatefulActionNode(name, config)
{
}

BT::PortsList AimAndFireAction::providedPorts()
{
  return {
    BT::InputPort<std::string>("target_id"),
    BT::InputPort<bool>("target_visible", false, "Whether the selected target is visible"),
    BT::InputPort<bool>("gimbal_aligned", false, "Whether the gimbal is aligned"),
    BT::InputPort<bool>("damage_confirmed", false, "Whether the latest shot caused damage"),
    BT::InputPort<bool>("target_destroyed", false, "Whether the selected target is destroyed"),
    BT::InputPort<double>("target_lost_seconds", 0.0, "Seconds since target was lost"),
    BT::InputPort<double>("lost_timeout_seconds", 5.0, "Target loss timeout"),
    BT::OutputPort<int>("posture_command"),
    BT::OutputPort<int>("gyro_mode_command"),
    BT::OutputPort<bool>("gimbal_enabled_command"),
    BT::OutputPort<bool>("gimbal_rotate_command"),
    BT::OutputPort<bool>("target_lock_command"),
    BT::OutputPort<bool>("fire_command")};
}

void AimAndFireAction::publishSafeOutputs()
{
  setOutput("posture_command", 1);
  setOutput("gyro_mode_command", 0);
  setOutput("gimbal_enabled_command", false);
  setOutput("gimbal_rotate_command", false);
  setOutput("target_lock_command", false);
  setOutput("fire_command", false);
}

BT::NodeStatus AimAndFireAction::evaluate()
{
  const auto target_id = getInput<std::string>("target_id");
  const auto visible = getInput<bool>("target_visible");
  const auto aligned = getInput<bool>("gimbal_aligned");
  const auto damage = getInput<bool>("damage_confirmed");
  const auto destroyed = getInput<bool>("target_destroyed");
  const auto lost_seconds = getInput<double>("target_lost_seconds");
  const auto timeout = getInput<double>("lost_timeout_seconds");
  if(!target_id || !visible || !aligned || !damage || !destroyed || !lost_seconds || !timeout ||
    target_id.value().empty() || !finite(lost_seconds.value()) || !finite(timeout.value()) ||
    lost_seconds.value() < 0.0 || timeout.value() <= 0.0)
  {
    publishSafeOutputs();
    return BT::NodeStatus::FAILURE;
  }

  publishSafeOutputs();
  if(destroyed.value())
  {
    return BT::NodeStatus::SUCCESS;
  }
  if(lost_seconds.value() >= timeout.value())
  {
    return BT::NodeStatus::FAILURE;
  }
  if(!visible.value() || !aligned.value())
  {
    setOutput("gimbal_enabled_command", true);
    setOutput("gimbal_rotate_command", true);
    return BT::NodeStatus::RUNNING;
  }

  setOutput("target_lock_command", true);
  setOutput("fire_command", true);
  if(!damage.value())
  {
    // A shot with no observed damage causes a fresh gimbal search.
    setOutput("gimbal_enabled_command", true);
    setOutput("gimbal_rotate_command", true);
  }
  return BT::NodeStatus::RUNNING;
}

BT::NodeStatus AimAndFireAction::onStart()
{
  return evaluate();
}

BT::NodeStatus AimAndFireAction::onRunning()
{
  return evaluate();
}

void AimAndFireAction::onHalted()
{
  publishSafeOutputs();
}

PursuitEligibilityCondition::PursuitEligibilityCondition(
  const std::string & name, const BT::NodeConfig & config)
: BT::ConditionNode(name, config)
{
}

BT::PortsList PursuitEligibilityCondition::providedPorts()
{
  return {
    BT::InputPort<std::string>("attack_targets"),
    BT::InputPort<int>("own_count", 0, "Number of friendly robots"),
    BT::InputPort<int>("enemy_count", 0, "Number of enemy robots"),
    BT::InputPort<double>("own_health", 0.0, "Friendly health"),
    BT::InputPort<double>("enemy_health", 0.0, "Enemy health"),
    BT::InputPort<double>("health_advantage", 200.0, "Required health advantage"),
    BT::InputPort<double>("weak_enemy_health", 30.0, "Weak enemy threshold")};
}

BT::NodeStatus PursuitEligibilityCondition::tick()
{
  const auto own_count = getInput<int>("own_count");
  const auto enemy_count = getInput<int>("enemy_count");
  const auto own_health = getInput<double>("own_health");
  const auto enemy_health = getInput<double>("enemy_health");
  const auto health_advantage = getInput<double>("health_advantage");
  const auto weak_health = getInput<double>("weak_enemy_health");
  if(!own_count || !enemy_count || !own_health || !enemy_health || !health_advantage ||
    !weak_health || own_count.value() < 0 || enemy_count.value() < 0 ||
    !finite(own_health.value()) || !finite(enemy_health.value()) ||
    !finite(health_advantage.value()) || !finite(weak_health.value()) ||
    health_advantage.value() < 0.0 || weak_health.value() < 0.0)
  {
    return BT::NodeStatus::FAILURE;
  }
  std::vector<Target> targets;
  if(!readTargetList(*this, "attack_targets", targets))
  {
    return BT::NodeStatus::FAILURE;
  }
  const bool weak_target = std::any_of(
    targets.begin(), targets.end(), [&](const Target & target) {
      return !target.invincible && target.health < weak_health.value();
    });
  const bool eligible = own_count.value() > enemy_count.value() ||
    own_health.value() > enemy_health.value() + health_advantage.value() || weak_target;
  return eligible ? BT::NodeStatus::SUCCESS : BT::NodeStatus::FAILURE;
}

PursueAction::PursueAction(const std::string & name, const BT::NodeConfig & config)
: BT::StatefulActionNode(name, config)
{
}

BT::PortsList PursueAction::providedPorts()
{
  return {
    BT::InputPort<std::string>("target_id"),
    BT::InputPort<double>(
      "target_distance", -1.0,
      "Latest target distance in meters; negative means use the legacy range input"),
    BT::InputPort<bool>("target_in_range", false, "Whether the target is in weapon range"),
    BT::InputPort<double>("in_range_seconds", 0.0, "Continuous time in range"),
    BT::InputPort<double>("pursuit_elapsed_seconds", 0.0, "Elapsed pursuit time"),
    BT::InputPort<double>("range_hold_seconds", 2.0, "Required continuous range time"),
    BT::InputPort<double>("pursuit_timeout_seconds", 5.0, "Pursuit timeout"),
    BT::InputPort<double>(
      "approach_trigger_distance", 4.0,
      "Start approaching when the target is farther than this distance"),
    BT::InputPort<double>(
      "approach_stop_distance", 2.8,
      "Stop approaching at or below this distance"),
    BT::InputPort<double>(
      "retreat_trigger_distance", 1.2,
      "Start retreating when the target is closer than this distance"),
    BT::InputPort<double>(
      "retreat_stop_distance", 1.8,
      "Stop retreating at or above this distance"),
    BT::OutputPort<int>("posture_command"),
    BT::OutputPort<int>("gyro_mode_command"),
    BT::OutputPort<bool>("gimbal_enabled_command"),
    BT::OutputPort<bool>("pursuit_enabled_command"),
    BT::OutputPort<std::string>("pursuit_target_id"),
    BT::OutputPort<std::string>(
      "pursuit_direction",
      "approach, retreat, or empty when no navigation command is active"),
    BT::OutputPort<double>(
      "pursuit_desired_distance",
      "Desired target separation for the navigation adapter")};
}

void PursueAction::resetPursuitState()
{
  active_target_id_.clear();
  direction_ = Direction::NONE;
}

void PursueAction::publishSafeOutputs()
{
  setOutput("posture_command", 3);
  setOutput("gyro_mode_command", 1);
  setOutput("gimbal_enabled_command", false);
  setOutput("pursuit_enabled_command", false);
  setOutput("pursuit_target_id", std::string{});
  setOutput("pursuit_direction", std::string{});
  setOutput("pursuit_desired_distance", 0.0);
}

BT::NodeStatus PursueAction::evaluate()
{
  const auto target_id = getInput<std::string>("target_id");
  const auto target_distance = getInput<double>("target_distance");
  const auto target_in_range = getInput<bool>("target_in_range");
  const auto in_range_seconds = getInput<double>("in_range_seconds");
  const auto elapsed = getInput<double>("pursuit_elapsed_seconds");
  const auto hold = getInput<double>("range_hold_seconds");
  const auto timeout = getInput<double>("pursuit_timeout_seconds");
  const auto approach_trigger = getInput<double>("approach_trigger_distance");
  const auto approach_stop = getInput<double>("approach_stop_distance");
  const auto retreat_trigger = getInput<double>("retreat_trigger_distance");
  const auto retreat_stop = getInput<double>("retreat_stop_distance");
  if(!target_id || !target_distance || !target_in_range || !in_range_seconds || !elapsed ||
    !hold || !timeout || !approach_trigger || !approach_stop || !retreat_trigger ||
    !retreat_stop || target_id.value().empty() || !finite(in_range_seconds.value()) ||
    !finite(elapsed.value()) || !finite(hold.value()) || !finite(timeout.value()) ||
    !finite(target_distance.value()) || target_distance.value() < -1.0 ||
    !finite(approach_trigger.value()) || !finite(approach_stop.value()) ||
    !finite(retreat_trigger.value()) || !finite(retreat_stop.value()) ||
    in_range_seconds.value() < 0.0 || elapsed.value() < 0.0 || hold.value() <= 0.0 ||
    timeout.value() <= 0.0 || approach_trigger.value() <= approach_stop.value() ||
    retreat_trigger.value() >= retreat_stop.value() || retreat_trigger.value() < 0.0)
  {
    resetPursuitState();
    publishSafeOutputs();
    return BT::NodeStatus::FAILURE;
  }

  if(active_target_id_ != target_id.value())
  {
    active_target_id_ = target_id.value();
    direction_ = Direction::NONE;
  }

  // Distance is refreshed by the perception input on every tree tick. Keep
  // the selected direction latched until its stop threshold is crossed; this
  // hysteresis prevents alternating approach/retreat commands around a limit.
  const bool has_distance = target_distance.value() >= 0.0 && finite(target_distance.value());
  if(has_distance)
  {
    const double distance = target_distance.value();
    if(direction_ == Direction::APPROACH && distance < retreat_trigger.value())
    {
      // A stale or sparse sensor update can skip over the approach stop
      // band. Treat the new close observation as a retreat request.
      direction_ = Direction::RETREAT;
    }
    else if(direction_ == Direction::RETREAT && distance > approach_trigger.value())
    {
      direction_ = Direction::APPROACH;
    }
    if(distance < retreat_trigger.value() && direction_ == Direction::NONE)
    {
      direction_ = Direction::RETREAT;
    }
    else if(distance > approach_trigger.value() && direction_ == Direction::NONE)
    {
      direction_ = Direction::APPROACH;
    }

    if(direction_ == Direction::APPROACH && distance <= approach_stop.value())
    {
      resetPursuitState();
      publishSafeOutputs();
      return BT::NodeStatus::SUCCESS;
    }
    if(direction_ == Direction::RETREAT && distance >= retreat_stop.value())
    {
      resetPursuitState();
      publishSafeOutputs();
      return BT::NodeStatus::SUCCESS;
    }
    if(direction_ == Direction::NONE)
    {
      publishSafeOutputs();
      return BT::NodeStatus::SUCCESS;
    }
  }

  if(elapsed.value() >= timeout.value())
  {
    resetPursuitState();
    publishSafeOutputs();
    return BT::NodeStatus::FAILURE;
  }

  publishSafeOutputs();
  if(!has_distance && target_in_range.value() && in_range_seconds.value() >= hold.value())
  {
    resetPursuitState();
    return BT::NodeStatus::SUCCESS;
  }

  std::string direction;
  double desired_distance = 0.0;
  if(direction_ == Direction::APPROACH)
  {
    direction = "approach";
    desired_distance = approach_stop.value();
  }
  else if(direction_ == Direction::RETREAT)
  {
    direction = "retreat";
    desired_distance = retreat_stop.value();
  }
  else if(!has_distance)
  {
    // Compatibility path for integrations that have not yet supplied a
    // numeric distance. It preserves the original range/timeout contract.
    direction = "approach";
    desired_distance = approach_stop.value();
  }
  else
  {
    return BT::NodeStatus::SUCCESS;
  }

  setOutput("pursuit_enabled_command", true);
  setOutput("pursuit_target_id", target_id.value());
  setOutput("pursuit_direction", direction);
  setOutput("pursuit_desired_distance", desired_distance);
  return BT::NodeStatus::RUNNING;
}

BT::NodeStatus PursueAction::onStart()
{
  return evaluate();
}

BT::NodeStatus PursueAction::onRunning()
{
  return evaluate();
}

void PursueAction::onHalted()
{
  resetPursuitState();
  publishSafeOutputs();
}

void registerAttackNodes(BT::BehaviorTreeFactory & factory)
{
  factory.registerNodeType<ConfigureAttackAction>("ConfigureAttack");
  factory.registerNodeType<BuildAttackTargetListAction>("BuildAttackTargetList");
  factory.registerNodeType<SelectAttackTargetAction>("SelectAttackTarget");
  factory.registerNodeType<HasAttackTargetsCondition>("HasAttackTargets");
  factory.registerNodeType<HasInRangeTargetCondition>("HasInRangeTarget");
  factory.registerNodeType<EvadeEligibleCondition>("EvadeEligible");
  factory.registerNodeType<AimAndFireAction>("AimAndFire");
  factory.registerNodeType<PursuitEligibilityCondition>("PursuitEligible");
  factory.registerNodeType<PursueAction>("DrivePursuit");
}

}  // namespace decision_process
