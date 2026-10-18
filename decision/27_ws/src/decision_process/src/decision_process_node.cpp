#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <memory>
#include <optional>
#include <sstream>
#include <string>
#include <vector>

#include "ament_index_cpp/get_package_share_directory.hpp"
#include "behaviortree_cpp/bt_factory.h"
#include "geometry_msgs/msg/pose_stamped.hpp"
#include "nav_msgs/msg/odometry.hpp"
#include "rclcpp/rclcpp.hpp"
#include "std_msgs/msg/bool.hpp"
#include "tf2/exceptions.hpp"
#include "tf2/time.hpp"
#include "tf2_ros/buffer.h"
#include "tf2_ros/transform_listener.h"

#include "decision_process/msg/autoaim_to_decision.hpp"
#include "decision_process/msg/decision_to_autoaim.hpp"
#include "decision_process/msg/desicion_send_data.hpp"
#include "decision_process/msg/receive_data.hpp"

#include "aggressive_patrol_nodes.hpp"
#include "attack_nodes.hpp"
#include "bullet_nodes.hpp"
#include "conservative_patrol_nodes.hpp"
#include "patrol_nodes.hpp"
#include "return_home_nodes.hpp"

using namespace std::chrono_literals;

namespace
{
constexpr double kAttackRange = 4.0;
constexpr double kOutpostAttackX = 17.0;
constexpr double kOutpostAttackY = 10.0;
constexpr uint32_t kMatchDurationSeconds = 420U;
constexpr uint32_t kOpeningOutpostSeconds = 300U;
constexpr uint32_t kSignificantDamageThreshold = 30U;
constexpr auto kDamageBurstWindow = 1s;

double distance(double ax, double ay, double bx, double by)
{
  return std::hypot(ax - bx, ay - by);
}

int targetNumber(const std::string & id)
{
  try
  {
    const int value = std::stoi(id);
    return value >= 1 && value <= 8 ? value : 0;
  }
  catch(...)
  {
    return 0;
  }
}

template<typename Type>
Type blackboardValue(
  const BT::Blackboard::Ptr & blackboard, const std::string & key, const Type & fallback)
{
  Type value = fallback;
  if(!blackboard->get(key, value))
  {
    return fallback;
  }
  return value;
}

std::string patrolPointsText(
  const std::vector<float> & values, const std::string & fallback)
{
  if(values.size() < 4U || values.size() % 2U != 0U)
  {
    return fallback;
  }
  std::ostringstream output;
  for(std::size_t index = 0; index < values.size(); index += 2U)
  {
    if(!std::isfinite(values[index]) || !std::isfinite(values[index + 1U]))
    {
      return fallback;
    }
    if(index > 0U)
    {
      output << ';';
    }
    output << values[index] << ',' << values[index + 1U];
  }
  return output.str();
}

}  // namespace

namespace decision_process
{

class DecisionProcessNode : public rclcpp::Node
{
public:
  DecisionProcessNode()
  : Node("decision_process"),
    tf_buffer_(get_clock()),
    tf_listener_(tf_buffer_),
    blackboard_(BT::Blackboard::create())
  {
    const double tick_rate_hz = declare_parameter<double>("tick_rate_hz", 20.0);
    goal_tolerance_ = declare_parameter<double>("goal_tolerance", 0.25);
    tree_file_ = declare_parameter<std::string>("tree_file", "");
    if(tree_file_.empty())
    {
      tree_file_ = ament_index_cpp::get_package_share_directory("decision_process") +
        "/xml/0.main.xml";
    }

    registerReturnHomeNodes(factory_);
    registerBulletNodes(factory_);
    registerPatrolNodes(factory_);
    registerConservativePatrolNodes(factory_);
    registerAggressivePatrolNodes(factory_);
    registerAttackNodes(factory_);

    initialiseBlackboard();
    tree_ = std::make_unique<BT::Tree>(factory_.createTreeFromFile(tree_file_, blackboard_));

    referee_sub_ = create_subscription<msg::ReceiveData>(
      "/serial_receive_data", 10,
      [this](const msg::ReceiveData::SharedPtr message) {handleReferee(message);});
    autoaim_sub_ = create_subscription<msg::AutoaimToDecision>(
      "/autoaim_to_decision", 10,
      [this](const msg::AutoaimToDecision::SharedPtr message) {autoaim_ = *message;});
    odom_sub_ = create_subscription<nav_msgs::msg::Odometry>(
      "/state_estimation", 10,
      [this](const nav_msgs::msg::Odometry::SharedPtr message) {
        current_x_ = message->pose.pose.position.x;
        current_y_ = message->pose.pose.position.y;
        const auto & q = message->pose.pose.orientation;
        current_yaw_ = std::atan2(
          2.0 * (q.w * q.z + q.x * q.y),
          1.0 - 2.0 * (q.y * q.y + q.z * q.z));
        localization_valid_ = true;
      });

    serial_pub_ = create_publisher<msg::DesicionSendData>("/serial_send_data", 10);
    autoaim_pub_ = create_publisher<msg::DecisionToAutoaim>("/decision_to_autoaim", 10);
    goal_pub_ = create_publisher<geometry_msgs::msg::PoseStamped>("/goal_pose", 10);
    goal_enabled_pub_ = create_publisher<std_msgs::msg::Bool>(
      "/decision_goal_enabled", 10);

    const auto period = std::chrono::duration<double>(1.0 / std::max(1.0, tick_rate_hz));
    timer_ = create_wall_timer(
      std::chrono::duration_cast<std::chrono::nanoseconds>(period),
      [this]() {tick();});
    last_damage_time_ = std::chrono::steady_clock::now() - 60s;
    last_damage_sample_time_ = std::chrono::steady_clock::now() - 60s;
    last_target_seen_time_ = std::chrono::steady_clock::now() - 60s;
    RCLCPP_INFO(get_logger(), "Loaded behavior tree: %s", tree_file_.c_str());
  }

private:
  void resetRuntimeState(bool recreate_tree)
  {
    if(tree_)
    {
      tree_->haltTree();
    }
    pursuit_started_.reset();
    in_range_started_.reset();
    death_started_.reset();
    previous_hp_.reset();
    health_decreased_ = false;
    accumulated_damage_ = 0U;
    last_selected_target_.clear();
    last_goal_enabled_ = false;
    last_target_seen_time_ = std::chrono::steady_clock::now() - 60s;
    last_damage_time_ = std::chrono::steady_clock::now() - 60s;
    last_damage_sample_time_ = std::chrono::steady_clock::now() - 60s;
    if(recreate_tree)
    {
      blackboard_ = BT::Blackboard::create();
      initialiseBlackboard();
      tree_ = std::make_unique<BT::Tree>(
        factory_.createTreeFromFile(tree_file_, blackboard_));
      RCLCPP_INFO(get_logger(), "Behavior tree state reset for a new match");
    }
  }

  void handleReferee(const msg::ReceiveData::SharedPtr & message)
  {
    const auto now = std::chrono::steady_clock::now();
    if(referee_received_)
    {
      const bool input_gap = now - last_referee_time_ > 1s;
      const bool new_match = message->game_period == 2U &&
        (referee_.game_period != 2U || message->time > referee_.time + 30U);
      if(new_match)
      {
        resetRuntimeState(true);
      }
      else if(input_gap)
      {
        resetRuntimeState(false);
      }
    }
    referee_ = *message;
    referee_received_ = true;
    last_referee_time_ = now;
  }

  void initialiseBlackboard()
  {
    blackboard_->set("waypoint_index", 0);
    blackboard_->set("tolerance", goal_tolerance_);
    blackboard_->set("economy_threshold", 400.0);
    blackboard_->set(
      "conservative_patrol_points", std::string{"5.0,5.0;9.0,5.0;9.0,9.0"});
    blackboard_->set(
      "aggressive_patrol_points", std::string{"12.0,3.0;14.0,7.5;12.3,11.7"});
    blackboard_->set("persistent_targets", std::string{});
    blackboard_->set("targets", std::string{});
    blackboard_->set("goal_frame_id", std::string{"map"});
    blackboard_->set("goal_enabled", false);
    blackboard_->set("posture_command", 3);
    blackboard_->set("gyro_mode_command", 0);
    blackboard_->set("gimbal_enabled", true);
    blackboard_->set("gimbal_rotate", true);
    blackboard_->set("target_lock", false);
    blackboard_->set("fire_command", false);
    blackboard_->set("pursuit_enabled", false);
    blackboard_->set("pursuit_target_id", std::string{});
    blackboard_->set("pursuit_direction", std::string{});
    blackboard_->set("pursuit_desired_distance", 0.0);
    blackboard_->set("selected_target_id", std::string{});
  }

  std::optional<std::pair<double, double>> visualPolarCoordinate(int target) const
  {
    if(!autoaimVisible(target))
    {
      return std::nullopt;
    }
    const std::size_t index = static_cast<std::size_t>(target);
    if(index >= autoaim_.target_polar_r.size() ||
      index >= autoaim_.target_polar_angle.size())
    {
      return std::nullopt;
    }
    const double radius = autoaim_.target_polar_r[index];
    const double angle = autoaim_.target_polar_angle[index];
    if(!std::isfinite(radius) || !std::isfinite(angle) || radius <= 0.0)
    {
      return std::nullopt;
    }
    return std::pair<double, double>{radius, angle};
  }

  std::optional<std::pair<double, double>> visualTargetPosition(int target) const
  {
    const auto polar = visualPolarCoordinate(target);
    if(!polar)
    {
      return std::nullopt;
    }
    try
    {
      // Auto-aim reports polar coordinates whose positive axis is the camera
      // direction at detection time.  The map->camera transform supplies only
      // our own sensor pose; no enemy world coordinate is consumed here.
      const auto camera = tf_buffer_.lookupTransform(
        "map", "camera_link", tf2::TimePointZero);
      const auto & q = camera.transform.rotation;
      const double camera_yaw = std::atan2(
        2.0 * (q.w * q.z + q.x * q.y),
        1.0 - 2.0 * (q.y * q.y + q.z * q.z));
      const double map_angle = camera_yaw + polar->second;
      return std::pair<double, double>{
        camera.transform.translation.x + polar->first * std::cos(map_angle),
        camera.transform.translation.y + polar->first * std::sin(map_angle)};
    }
    catch(const tf2::TransformException & error)
    {
      RCLCPP_WARN_THROTTLE(
        get_logger(), *get_clock(), 2000,
        "Cannot convert auto-aim polar target to map: %s", error.what());
      return std::nullopt;
    }
  }

  std::optional<std::pair<double, double>> radarTargetPosition(int target) const
  {
    const std::array<int, 6> ids{{1, 2, 3, 4, 5, 8}};
    const auto iterator = std::find(ids.begin(), ids.end(), target);
    if(iterator == ids.end())
    {
      return std::nullopt;
    }
    const std::size_t index = static_cast<std::size_t>(iterator - ids.begin()) * 2U;
    if(referee_.radar_data.size() <= index + 1U)
    {
      return std::nullopt;
    }
    const double x = referee_.radar_data[index];
    const double y = referee_.radar_data[index + 1U];
    if(!std::isfinite(x) || !std::isfinite(y) || (x == 0.0 && y == 0.0))
    {
      return std::nullopt;
    }
    return std::pair<double, double>{x, y};
  }

  double tacticalDistance(int target) const
  {
    if(target == 6)
    {
      return distance(current_x_, current_y_, kOutpostAttackX, kOutpostAttackY);
    }
    const auto position = targetPosition(target);
    return position ? distance(current_x_, current_y_, position->first, position->second) : 99.0;
  }

  std::optional<std::pair<double, double>> targetPosition(int target) const
  {
    if(target == 6)
    {
      return std::pair<double, double>{20.0, 7.5};
    }
    if(target == 7)
    {
      return std::pair<double, double>{27.0, 7.5};
    }
    // A visible unit must be positioned from the camera-relative observation.
    // Do not silently replace malformed/missing visual coordinates with the
    // referee/radar world coordinate, otherwise the robot gains omniscience.
    if(autoaimVisible(target))
    {
      return visualTargetPosition(target);
    }
    return radarTargetPosition(target);
  }

  uint16_t targetHealth(int target) const
  {
    const std::size_t index = target > 0 ? static_cast<std::size_t>(target - 1) : 8U;
    return index < referee_.hp_enemy.size() ? referee_.hp_enemy[index] : 0U;
  }

  bool autoaimVisible(int target) const
  {
    return target > 0 && static_cast<std::size_t>(target) < autoaim_.target.size() &&
      autoaim_.target[static_cast<std::size_t>(target)] != 0U;
  }

  double autoaimDistance(int target) const
  {
    const auto polar = visualPolarCoordinate(target);
    if(polar)
    {
      return polar->first;
    }
    if(target > 0 && static_cast<std::size_t>(target) < autoaim_.target_distance.size())
    {
      const double reported = autoaim_.target_distance[static_cast<std::size_t>(target)];
      if(std::isfinite(reported) && reported > 0.0)
      {
        return reported;
      }
    }
    return tacticalDistance(target);
  }

  std::string observedTargets() const
  {
    std::ostringstream stream;
    bool first = true;
    // Engineer robot 2 remains visible to perception but is marked invincible
    // below so it never enters the filtered attack candidate list.
    for(const int target : {1, 2, 3, 4, 5, 8})
    {
      if(!autoaimVisible(target) || targetHealth(target) == 0U)
      {
        continue;
      }
      const double range = autoaimDistance(target);
      if(!first)
      {
        stream << ';';
      }
      first = false;
      stream << target << ':' << targetHealth(target) << ':' << range << ':'
             << (range <= kAttackRange ? 1 : 0) << ':'
             << (target == 2 || targetHealth(target) == 1001U ? 1 : 0)
             << ":0";
    }
    return stream.str();
  }

  std::string persistentTargets() const
  {
    // referee_.time is the remaining match time. Keep the opening outpost in
    // the attack list for the first 300 seconds, then let normal target
    // selection take over. At exactly 300 seconds elapsed, the opening phase
    // has ended.
    const uint32_t opening_cutoff = kMatchDurationSeconds - kOpeningOutpostSeconds;
    if(referee_.time <= opening_cutoff)
    {
      return {};
    }
    const uint16_t health = targetHealth(6);
    if(health == 0U)
    {
      return {};
    }
    const double tactical_range = tacticalDistance(6);
    // Target 6 is a fixed building with a prescribed firing point at (17, 10).
    // The generic pursuit node stops 4.1 m short of a moving target, therefore
    // encode the fixed-point distance so its generated goal remains (17, 10).
    const double pursuit_range = tactical_range + 4.1;
    std::ostringstream stream;
    stream << "6:" << health << ':' << pursuit_range << ':'
           << (tactical_range <= goal_tolerance_ ? 1 : 0)
           << ':' << (health == 1001U ? 1 : 0) << ":1";
    return stream.str();
  }

  void updateInputs()
  {
    const auto now = std::chrono::steady_clock::now();
    if(previous_hp_ && *previous_hp_ > referee_.hp_sentry)
    {
      if(now - last_damage_sample_time_ > kDamageBurstWindow)
      {
        accumulated_damage_ = 0U;
      }
      accumulated_damage_ += static_cast<uint32_t>(*previous_hp_ - referee_.hp_sentry);
      last_damage_sample_time_ = now;
      if(accumulated_damage_ >= kSignificantDamageThreshold)
      {
        health_decreased_ = true;
        last_damage_time_ = now;
        accumulated_damage_ = 0U;
      }
    }
    else if(previous_hp_ && *previous_hp_ < referee_.hp_sentry)
    {
      accumulated_damage_ = 0U;
    }
    else if(now - last_damage_sample_time_ > kDamageBurstWindow)
    {
      accumulated_damage_ = 0U;
    }
    previous_hp_ = referee_.hp_sentry;

    const int selected = targetNumber(last_selected_target_);
    const bool selected_visible = autoaimVisible(selected);
    if(selected_visible)
    {
      last_target_seen_time_ = now;
    }
    const double target_lost_seconds =
      std::chrono::duration<double>(now - last_target_seen_time_).count();
    const double no_damage_seconds =
      std::chrono::duration<double>(now - last_damage_time_).count();

    const bool selected_in_range = selected > 0 &&
      (selected == 6 ? tacticalDistance(6) <= goal_tolerance_ :
      autoaimDistance(selected) <= kAttackRange);
    if(selected_in_range)
    {
      if(!in_range_started_)
      {
        in_range_started_ = now;
      }
    }
    else
    {
      in_range_started_.reset();
    }
    const double in_range_seconds = in_range_started_ ?
      std::chrono::duration<double>(now - *in_range_started_).count() : 0.0;
    const double pursuit_seconds = pursuit_started_ ?
      std::chrono::duration<double>(now - *pursuit_started_).count() : 0.0;

    int enemy_count = 0;
    double enemy_health = 0.0;
    for(const int target : {1, 2, 3, 4, 5, 8})
    {
      const uint16_t health = targetHealth(target);
      if(health > 0U && health != 1001U)
      {
        ++enemy_count;
        enemy_health += health;
      }
    }

    blackboard_->set("game_period", static_cast<int>(referee_.game_period));
    blackboard_->set("time", static_cast<int>(referee_.time));
    blackboard_->set("current_x", current_x_);
    blackboard_->set("current_y", current_y_);
    blackboard_->set("localization_valid", localization_valid_);
    blackboard_->set("ammo_count", static_cast<int>(referee_.ammo));
    blackboard_->set("pickup_ammo_count", static_cast<int>(referee_.pending_ammo));
    blackboard_->set("health", static_cast<double>(referee_.hp_sentry));
    blackboard_->set("defense_buff", static_cast<double>(referee_.defence_buff) / 100.0);
    blackboard_->set("economy", static_cast<double>(referee_.economy));
    blackboard_->set("aggressive_patrol", referee_.aggressive_patrol);
    blackboard_->set(
      "conservative_patrol_points",
      patrolPointsText(
        referee_.conservative_patrol_points,
        "5.0,5.0;9.0,5.0;9.0,9.0"));
    blackboard_->set(
      "aggressive_patrol_points",
      patrolPointsText(
        referee_.aggressive_patrol_points,
        "12.0,3.0;14.0,7.5;12.3,11.7"));
    blackboard_->set("targets", observedTargets());
    blackboard_->set("persistent_targets", persistentTargets());
    blackboard_->set("health_decreased", health_decreased_);
    blackboard_->set("at_target", last_goal_enabled_ &&
      distance(current_x_, current_y_, last_goal_x_, last_goal_y_) <= goal_tolerance_);
    blackboard_->set("no_damage_seconds", no_damage_seconds);
    blackboard_->set("target_visible", selected_visible);
    blackboard_->set("gimbal_aligned", selected_visible);
    blackboard_->set("damage_confirmed", false);
    blackboard_->set("target_destroyed", selected > 0 && targetHealth(selected) == 0U);
    blackboard_->set(
      "target_lost_seconds",
      selected == 6 && targetHealth(6) > 0U && !selected_visible ? 0.0 : target_lost_seconds);
    blackboard_->set("own_count", 8);
    blackboard_->set("enemy_count", enemy_count);
    blackboard_->set("own_health", static_cast<double>(referee_.hp_sentry));
    blackboard_->set("enemy_health", enemy_health);
    blackboard_->set("target_in_range_seconds", in_range_seconds);
    blackboard_->set("pursuit_elapsed_seconds", pursuit_seconds);

    blackboard_->set("goal_enabled", false);
    blackboard_->set("fire_command", false);
    blackboard_->set("target_lock", false);
    blackboard_->set("gimbal_enabled", false);
    blackboard_->set("gimbal_rotate", true);
    blackboard_->set("pursuit_enabled", false);
    blackboard_->set("selected_target_id", std::string{});
    health_decreased_ = false;
  }

  bool pursuitGoal(
    const std::string & target_id, const std::string & direction, double desired_distance,
    double & goal_x, double & goal_y) const
  {
    const int target = targetNumber(target_id);
    if(target == 0 || direction.empty())
    {
      return false;
    }
    if(target == 6 && direction == "approach")
    {
      goal_x = kOutpostAttackX;
      goal_y = kOutpostAttackY;
      return true;
    }
    const auto position = targetPosition(target);
    if(!position)
    {
      return false;
    }
    const double dx = position->first - current_x_;
    const double dy = position->second - current_y_;
    const double length = std::hypot(dx, dy);
    if(length < 1e-6)
    {
      return false;
    }
    if(direction == "approach")
    {
      goal_x = position->first - dx / length * desired_distance;
      goal_y = position->second - dy / length * desired_distance;
      return true;
    }
    if(direction == "retreat")
    {
      goal_x = std::clamp(current_x_ - dx / length * 1.5, 0.0, 28.0);
      goal_y = std::clamp(current_y_ - dy / length * 1.5, 0.0, 15.0);
      return true;
    }
    return false;
  }

  void publishOutputs()
  {
    msg::DesicionSendData serial;
    serial.posture = static_cast<uint8_t>(std::clamp(
      blackboardValue<int>(blackboard_, "posture_command", 3), 1, 3));
    serial.confirm_respawn = 0U;
    if(referee_.hp_sentry == 0U)
    {
      if(!death_started_)
      {
        death_started_ = std::chrono::steady_clock::now();
      }
      serial.confirm_respawn =
        std::chrono::steady_clock::now() - *death_started_ >= 5s ? 1U : 0U;
    }
    else
    {
      death_started_.reset();
    }
    const int gyro = blackboardValue<int>(blackboard_, "gyro_mode_command", 0);
    serial.spin_mode = referee_.game_period == 2U ?
      static_cast<uint8_t>(std::clamp(gyro, 0, 3)) : 0U;
    serial.shoot_mode = blackboardValue<bool>(blackboard_, "fire_command", false) ? 1U : 0U;
    serial.tripod_mode =
      blackboardValue<bool>(blackboard_, "gimbal_enabled", false) ? 1U : 0U;
    serial_pub_->publish(serial);

    std::string selected = blackboardValue<std::string>(
      blackboard_, "selected_target_id", std::string{});
    if(selected.empty())
    {
      selected = blackboardValue<std::string>(
        blackboard_, "pursuit_target_id", std::string{});
    }
    last_selected_target_ = selected;
    msg::DecisionToAutoaim autoaim_command;
    autoaim_command.color = referee_.color;
    autoaim_command.target = static_cast<uint8_t>(targetNumber(selected));
    autoaim_command.decide_yaw = static_cast<float>(current_yaw_);
    autoaim_pub_->publish(autoaim_command);

    bool goal_enabled = blackboardValue<bool>(blackboard_, "goal_enabled", false);
    double goal_x = blackboardValue<double>(blackboard_, "goal_x", current_x_);
    double goal_y = blackboardValue<double>(blackboard_, "goal_y", current_y_);
    double goal_yaw = blackboardValue<double>(blackboard_, "goal_yaw", 0.0);
    const bool pursuing = blackboardValue<bool>(blackboard_, "pursuit_enabled", false);
    if(pursuing)
    {
      if(!pursuit_started_)
      {
        pursuit_started_ = std::chrono::steady_clock::now();
      }
      goal_enabled = pursuitGoal(
        blackboardValue<std::string>(blackboard_, "pursuit_target_id", std::string{}),
        blackboardValue<std::string>(blackboard_, "pursuit_direction", std::string{}),
        blackboardValue<double>(blackboard_, "pursuit_desired_distance", 0.0),
        goal_x, goal_y);
    }
    else
    {
      pursuit_started_.reset();
    }

    std_msgs::msg::Bool enabled_message;
    enabled_message.data = goal_enabled;
    if(goal_enabled)
    {
      geometry_msgs::msg::PoseStamped goal;
      goal.header.stamp = get_clock()->now();
      goal.header.frame_id = "map";
      goal.pose.position.x = goal_x;
      goal.pose.position.y = goal_y;
      goal.pose.position.z = 1.0;
      goal.pose.orientation.z = std::sin(goal_yaw * 0.5);
      goal.pose.orientation.w = std::cos(goal_yaw * 0.5);
      goal_pub_->publish(goal);
    }
    goal_enabled_pub_->publish(enabled_message);
    last_goal_enabled_ = goal_enabled;
    last_goal_x_ = goal_x;
    last_goal_y_ = goal_y;
  }

  void tick()
  {
    if(!tree_ || !referee_received_)
    {
      return;
    }
    if(std::chrono::steady_clock::now() - last_referee_time_ > 1s)
    {
      if(!input_stale_)
      {
        resetRuntimeState(false);
        input_stale_ = true;
      }
      return;
    }
    input_stale_ = false;
    try
    {
      updateInputs();
      tree_->tickOnce();
      publishOutputs();
    }
    catch(const std::exception & error)
    {
      RCLCPP_ERROR_THROTTLE(
        get_logger(), *get_clock(), 2000, "Behavior tree tick failed: %s", error.what());
    }
  }

  BT::BehaviorTreeFactory factory_;
  tf2_ros::Buffer tf_buffer_;
  tf2_ros::TransformListener tf_listener_;
  BT::Blackboard::Ptr blackboard_;
  std::unique_ptr<BT::Tree> tree_;
  std::string tree_file_;

  msg::ReceiveData referee_;
  msg::AutoaimToDecision autoaim_;
  double current_x_{4.971};
  double current_y_{7.5};
  double current_yaw_{0.0};
  bool localization_valid_{false};
  bool referee_received_{false};
  bool input_stale_{false};
  std::chrono::steady_clock::time_point last_referee_time_{};
  double goal_tolerance_{0.25};
  std::optional<uint16_t> previous_hp_;
  bool health_decreased_{false};
  uint32_t accumulated_damage_{0U};
  std::chrono::steady_clock::time_point last_damage_time_;
  std::chrono::steady_clock::time_point last_damage_sample_time_;
  std::chrono::steady_clock::time_point last_target_seen_time_;
  std::optional<std::chrono::steady_clock::time_point> in_range_started_;
  std::optional<std::chrono::steady_clock::time_point> pursuit_started_;
  std::optional<std::chrono::steady_clock::time_point> death_started_;
  std::string last_selected_target_;
  bool last_goal_enabled_{false};
  double last_goal_x_{0.0};
  double last_goal_y_{0.0};

  rclcpp::Subscription<msg::ReceiveData>::SharedPtr referee_sub_;
  rclcpp::Subscription<msg::AutoaimToDecision>::SharedPtr autoaim_sub_;
  rclcpp::Subscription<nav_msgs::msg::Odometry>::SharedPtr odom_sub_;
  rclcpp::Publisher<msg::DesicionSendData>::SharedPtr serial_pub_;
  rclcpp::Publisher<msg::DecisionToAutoaim>::SharedPtr autoaim_pub_;
  rclcpp::Publisher<geometry_msgs::msg::PoseStamped>::SharedPtr goal_pub_;
  rclcpp::Publisher<std_msgs::msg::Bool>::SharedPtr goal_enabled_pub_;
  rclcpp::TimerBase::SharedPtr timer_;
};

}  // namespace decision_process

int main(int argc, char ** argv)
{
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<decision_process::DecisionProcessNode>());
  rclcpp::shutdown();
  return 0;
}
