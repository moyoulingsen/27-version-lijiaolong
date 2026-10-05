#include "decision_process/decision_process_node.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <exception>
#include <functional>
#include <iomanip>
#include <sstream>
#include <type_traits>

#include "ament_index_cpp/get_package_share_directory.hpp"

#include "decision_process/behavior_tree_nodes.hpp"

namespace
{

template<typename SourceType, typename TargetType, std::size_t Size>
void copyVectorToArray(
  const std::vector<SourceType> & source,
  std::array<TargetType, Size> & target)
{
  target.fill(TargetType{});
  const std::size_t copy_size = std::min(source.size(), target.size());
  for (std::size_t index = 0; index < copy_size; ++index) {
    target[index] = static_cast<TargetType>(source[index]);
  }
}

template<typename Type, std::size_t Size>
std::string arrayToString(const std::array<Type, Size> & values)
{
  std::ostringstream stream;
  stream << '[';
  for (std::size_t index = 0; index < values.size(); ++index) {
    if (index != 0) {
      stream << ", ";
    }
    if constexpr (std::is_floating_point_v<Type>) {
      stream << std::fixed << std::setprecision(2) << values[index];
    } else {
      stream << static_cast<unsigned long long>(values[index]);
    }
  }
  stream << ']';
  return stream.str();
}

bool integerInRange(const rclcpp::Parameter & parameter, int64_t minimum, int64_t maximum)
{
  return parameter.get_type() == rclcpp::ParameterType::PARAMETER_INTEGER &&
         parameter.as_int() >= minimum && parameter.as_int() <= maximum;
}

}  // namespace

namespace decision_process
{

DecisionProcessNode::DecisionProcessNode()
: Node("decision_process")
{
  const double publish_rate_hz = declare_parameter<double>("publish_rate_hz", 20.0);
  const bool behavior_tree_enabled = declare_parameter<bool>("behavior_tree_enabled", true);
  const double behavior_tree_tick_rate_hz =
    declare_parameter<double>("behavior_tree_tick_rate_hz", 20.0);

  std::string default_tree_path;
  try {
    default_tree_path =
      ament_index_cpp::get_package_share_directory("decision_process") +
      "/behavior_trees/01_return_home.xml";
  } catch (const std::exception & error) {
    RCLCPP_WARN(
      get_logger(), "Unable to resolve default behavior tree path: %s", error.what());
  }
  std::string behavior_tree_xml =
    declare_parameter<std::string>("behavior_tree_xml", default_tree_path);
  if (behavior_tree_xml.empty()) {
    behavior_tree_xml = default_tree_path;
  }
  navigation_command_.enabled = declare_parameter<bool>("publish_goal", false);
  navigation_command_.x = declare_parameter<double>("goal_x", 0.0);
  navigation_command_.y = declare_parameter<double>("goal_y", 0.0);
  navigation_command_.yaw = declare_parameter<double>("goal_yaw", 0.0);
  navigation_command_.frame_id = declare_parameter<std::string>("goal_frame_id", "map");

  serial_command_.posture =
    static_cast<uint8_t>(declare_parameter<int>("default_posture", 3));
  serial_command_.confirm_respawn =
    static_cast<uint8_t>(declare_parameter<int>("default_confirm_respawn", 0));
  serial_command_.tripod_mode =
    static_cast<uint8_t>(declare_parameter<int>("default_tripod_mode", 1));
  serial_command_.spin_mode =
    static_cast<uint8_t>(declare_parameter<int>("default_spin_mode", 0));
  serial_command_.shoot_mode =
    static_cast<uint8_t>(declare_parameter<int>("default_shoot_mode", 0));

  autoaim_command_.color =
    static_cast<uint8_t>(declare_parameter<int>("default_target_color", 0));
  autoaim_command_.target =
    static_cast<uint8_t>(declare_parameter<int>("default_target_number", 0));
  autoaim_command_.decide_yaw =
    static_cast<float>(declare_parameter<double>("default_decide_yaw", 0.0));

  parameter_callback_handle_ = add_on_set_parameters_callback(
    std::bind(&DecisionProcessNode::parametersCallback, this, std::placeholders::_1));

  const auto sensor_qos = rclcpp::SensorDataQoS();
  const auto command_qos = rclcpp::QoS(rclcpp::KeepLast(10)).reliable();

  state_estimation_sub_ = create_subscription<Odometry>(
    "/state_estimation", sensor_qos,
    std::bind(&DecisionProcessNode::stateEstimationCallback, this, std::placeholders::_1));

  serial_receive_sub_ = create_subscription<ReceiveData>(
    "/serial_receive_data", command_qos,
    std::bind(&DecisionProcessNode::serialReceiveCallback, this, std::placeholders::_1));

  autoaim_sub_ = create_subscription<AutoaimToDecision>(
    "/autoaim_to_decision", sensor_qos,
    std::bind(&DecisionProcessNode::autoaimCallback, this, std::placeholders::_1));

  goal_pose_pub_ = create_publisher<PoseStamped>("/goal_pose", command_qos);
  serial_send_pub_ = create_publisher<DesicionSendData>("/serial_send_data", command_qos);
  autoaim_command_pub_ =
    create_publisher<DecisionToAutoaim>("/decision_to_autoaim", command_qos);

  const double safe_rate_hz = std::max(publish_rate_hz, 1.0);
  const auto period = std::chrono::duration<double>(1.0 / safe_rate_hz);
  publish_timer_ = create_wall_timer(
    std::chrono::duration_cast<std::chrono::milliseconds>(period),
    std::bind(&DecisionProcessNode::publishOutputs, this));

  if (behavior_tree_enabled) {
    initializeBehaviorTree(behavior_tree_xml, behavior_tree_tick_rate_hz);
  }

  RCLCPP_INFO(get_logger(), "Decision communication node started at %.1f Hz", safe_rate_hz);
  RCLCPP_INFO(
    get_logger(), "Goal publishing is %s",
    navigation_command_.enabled ? "enabled" : "disabled");
}

void DecisionProcessNode::stateEstimationCallback(const Odometry::SharedPtr msg)
{
  const auto & position = msg->pose.pose.position;
  const auto & orientation = msg->pose.pose.orientation;
  const double sin_yaw =
    2.0 * (orientation.w * orientation.z + orientation.x * orientation.y);
  const double cos_yaw =
    1.0 - 2.0 * (orientation.y * orientation.y + orientation.z * orientation.z);

  {
    std::lock_guard<std::mutex> lock(data_mutex_);
    localization_state_.frame_id = msg->header.frame_id;
    localization_state_.x = position.x;
    localization_state_.y = position.y;
    localization_state_.z = position.z;
    localization_state_.qx = orientation.x;
    localization_state_.qy = orientation.y;
    localization_state_.qz = orientation.z;
    localization_state_.qw = orientation.w;
    localization_state_.yaw = std::atan2(sin_yaw, cos_yaw);
    localization_state_.received = true;
  }

  RCLCPP_INFO_THROTTLE(
    get_logger(), *get_clock(), 2000,
    "RX /state_estimation: frame=%s xyz=[%.2f, %.2f, %.2f] "
    "quaternion=[%.3f, %.3f, %.3f, %.3f] yaw=%.3f",
    msg->header.frame_id.c_str(), position.x, position.y, position.z,
    orientation.x, orientation.y, orientation.z, orientation.w,
    std::atan2(sin_yaw, cos_yaw));
}

void DecisionProcessNode::serialReceiveCallback(const ReceiveData::SharedPtr msg)
{
  {
    std::lock_guard<std::mutex> lock(data_mutex_);
    const uint16_t previous_ammo = referee_state_.ammo;
    referee_state_.game_period = msg->game_period;
    referee_state_.remaining_time = msg->time;
    referee_state_.sentry_hp = msg->hp_sentry;
    referee_state_.defence_buff = msg->defence_buff;
    referee_state_.team_color = msg->color;
    referee_state_.ammo = msg->ammo;
    referee_state_.outpost_hp = msg->hp_outpost;
    referee_state_.base_hp = msg->hp_base;
    copyVectorToArray(msg->hp_enemy, referee_state_.enemy_hp);
    copyVectorToArray(msg->radar_data, referee_state_.radar_data);
    referee_state_.enemy_hp_valid = msg->hp_enemy.size() == kEnemyCount;
    referee_state_.received = true;
    match_lifecycle_.update(msg->game_period);
    ammo_reserve_tracker_.update(msg->game_period, msg->time);
    if (ammo_pickup_waiting_ && previous_ammo == 0U && msg->ammo > 0U) {
      ammo_reserve_tracker_.confirmPickup();
      ammo_pickup_waiting_ = false;
    }
  }

  if (msg->hp_enemy.size() != kEnemyCount) {
    RCLCPP_WARN_THROTTLE(
      get_logger(), *get_clock(), 2000,
      "/serial_receive_data hp_enemy length=%zu, expected=%zu",
      msg->hp_enemy.size(), kEnemyCount);
  }
  if (msg->radar_data.size() != kRadarValueCount) {
    RCLCPP_WARN_THROTTLE(
      get_logger(), *get_clock(), 2000,
      "/serial_receive_data radar_data length=%zu, expected=%zu",
      msg->radar_data.size(), kRadarValueCount);
  }

  const RefereeState state = getRefereeState();
  const std::string enemy_hp = arrayToString(state.enemy_hp);
  const std::string radar_data = arrayToString(state.radar_data);

  RCLCPP_INFO_THROTTLE(
    get_logger(), *get_clock(), 2000,
    "RX /serial_receive_data: period=%u time=%u sentry_hp=%u defence=%u "
    "color=%u ammo=%u outpost_hp=%u base_hp=%u enemy_hp=%s radar=%s",
    static_cast<unsigned int>(state.game_period),
    static_cast<unsigned int>(state.remaining_time),
    static_cast<unsigned int>(state.sentry_hp),
    static_cast<unsigned int>(state.defence_buff),
    static_cast<unsigned int>(state.team_color),
    static_cast<unsigned int>(state.ammo),
    static_cast<unsigned int>(state.outpost_hp),
    static_cast<unsigned int>(state.base_hp),
    enemy_hp.c_str(), radar_data.c_str());
}

void DecisionProcessNode::autoaimCallback(const AutoaimToDecision::SharedPtr msg)
{
  {
    std::lock_guard<std::mutex> lock(data_mutex_);
    copyVectorToArray(msg->target, autoaim_state_.target);
    copyVectorToArray(msg->target_distance, autoaim_state_.target_distance);
    copyVectorToArray(msg->target_polar_r, autoaim_state_.target_polar_r);
    copyVectorToArray(msg->target_polar_angle, autoaim_state_.target_polar_angle);
    autoaim_state_.received = true;
  }

  const std::array<std::size_t, 4> received_sizes{
    msg->target.size(), msg->target_distance.size(),
    msg->target_polar_r.size(), msg->target_polar_angle.size()};
  if (std::any_of(
      received_sizes.begin(), received_sizes.end(),
      [](std::size_t size) {return size != kAutoaimTargetCount;}))
  {
    RCLCPP_WARN_THROTTLE(
      get_logger(), *get_clock(), 2000,
      "/autoaim_to_decision array lengths target=%zu distance=%zu r=%zu angle=%zu, expected=9",
      received_sizes[0], received_sizes[1], received_sizes[2], received_sizes[3]);
  }

  const AutoaimState state = getAutoaimState();
  const std::string target = arrayToString(state.target);
  const std::string distance = arrayToString(state.target_distance);
  const std::string polar_r = arrayToString(state.target_polar_r);
  const std::string polar_angle = arrayToString(state.target_polar_angle);
  RCLCPP_INFO_THROTTLE(
    get_logger(), *get_clock(), 2000,
    "RX /autoaim_to_decision: target=%s distance=%s polar_r=%s polar_angle=%s",
    target.c_str(), distance.c_str(), polar_r.c_str(), polar_angle.c_str());
}

void DecisionProcessNode::publishOutputs()
{
  // 这里只做通信层的安全默认输出，不包含行为树或决策逻辑。
  SerialCommand serial_command;
  AutoaimCommand autoaim_command;
  NavigationCommand navigation_command;
  {
    std::lock_guard<std::mutex> lock(output_mutex_);
    serial_command = serial_command_;
    autoaim_command = autoaim_command_;
    navigation_command = navigation_command_;
  }

  DesicionSendData serial_message;
  serial_message.posture = serial_command.posture;
  serial_message.confirm_respawn = serial_command.confirm_respawn;
  serial_message.tripod_mode = serial_command.tripod_mode;
  serial_message.spin_mode = serial_command.spin_mode;
  serial_message.shoot_mode = serial_command.shoot_mode;
  serial_send_pub_->publish(serial_message);

  DecisionToAutoaim autoaim_message;
  autoaim_message.color = autoaim_command.color;
  autoaim_message.target = autoaim_command.target;
  autoaim_message.decide_yaw = autoaim_command.decide_yaw;
  autoaim_command_pub_->publish(autoaim_message);

  if (navigation_command.enabled) {
    publishGoalPose();
  }
}

void DecisionProcessNode::publishGoalPose()
{
  NavigationCommand command;
  {
    std::lock_guard<std::mutex> lock(output_mutex_);
    command = navigation_command_;
  }

  PoseStamped goal;
  goal.header.stamp = now();
  goal.header.frame_id = command.frame_id;
  goal.pose.position.x = command.x;
  goal.pose.position.y = command.y;
  goal.pose.position.z = 1.0;

  const double half_yaw = command.yaw * 0.5;
  goal.pose.orientation.x = 0.0;
  goal.pose.orientation.y = 0.0;
  goal.pose.orientation.z = std::sin(half_yaw);
  goal.pose.orientation.w = std::cos(half_yaw);

  goal_pose_pub_->publish(goal);
}

RefereeState DecisionProcessNode::getRefereeState() const
{
  std::lock_guard<std::mutex> lock(data_mutex_);
  return referee_state_;
}

AutoaimState DecisionProcessNode::getAutoaimState() const
{
  std::lock_guard<std::mutex> lock(data_mutex_);
  return autoaim_state_;
}

LocalizationState DecisionProcessNode::getLocalizationState() const
{
  std::lock_guard<std::mutex> lock(data_mutex_);
  return localization_state_;
}

SerialCommand DecisionProcessNode::getSerialCommand() const
{
  std::lock_guard<std::mutex> lock(output_mutex_);
  return serial_command_;
}

AutoaimCommand DecisionProcessNode::getAutoaimCommand() const
{
  std::lock_guard<std::mutex> lock(output_mutex_);
  return autoaim_command_;
}

NavigationCommand DecisionProcessNode::getNavigationCommand() const
{
  std::lock_guard<std::mutex> lock(output_mutex_);
  return navigation_command_;
}

bool DecisionProcessNode::hasGameStarted() const
{
  std::lock_guard<std::mutex> lock(data_mutex_);
  return match_lifecycle_.hasStarted();
}

bool DecisionProcessNode::isGameFinished() const
{
  std::lock_guard<std::mutex> lock(data_mutex_);
  return referee_state_.received && match_lifecycle_.hasFinished();
}

uint16_t DecisionProcessNode::getPendingAmmo() const
{
  std::lock_guard<std::mutex> lock(data_mutex_);
  return ammo_reserve_tracker_.pendingAmmo();
}

void DecisionProcessNode::setSerialCommand(const SerialCommand & command)
{
  std::lock_guard<std::mutex> lock(output_mutex_);
  serial_command_ = command;
}

void DecisionProcessNode::setAutoaimCommand(const AutoaimCommand & command)
{
  std::lock_guard<std::mutex> lock(output_mutex_);
  autoaim_command_ = command;
}

void DecisionProcessNode::setNavigationCommand(const NavigationCommand & command)
{
  std::lock_guard<std::mutex> lock(output_mutex_);
  navigation_command_ = command;
}

void DecisionProcessNode::beginAmmoPickupWait()
{
  std::lock_guard<std::mutex> lock(data_mutex_);
  ammo_pickup_waiting_ = true;
}

void DecisionProcessNode::cancelAmmoPickupWait()
{
  std::lock_guard<std::mutex> lock(data_mutex_);
  ammo_pickup_waiting_ = false;
}

void DecisionProcessNode::initializeBehaviorTree(
  const std::string & xml_path, double tick_rate_hz)
{
  if (xml_path.empty()) {
    RCLCPP_ERROR(get_logger(), "Behavior tree XML path is empty");
    return;
  }

  try {
    registerDecisionNodes(behavior_tree_factory_, *this);
    behavior_tree_ = std::make_unique<BT::Tree>(
      behavior_tree_factory_.createTreeFromFile(xml_path));
  } catch (const std::exception & error) {
    RCLCPP_ERROR(
      get_logger(), "Failed to load behavior tree [%s]: %s",
      xml_path.c_str(), error.what());
    behavior_tree_.reset();
    return;
  }

  const double safe_rate_hz = std::max(tick_rate_hz, 1.0);
  const auto period = std::chrono::duration<double>(1.0 / safe_rate_hz);
  behavior_tree_timer_ = create_wall_timer(
    std::chrono::duration_cast<std::chrono::milliseconds>(period),
    std::bind(&DecisionProcessNode::tickBehaviorTree, this));
  RCLCPP_INFO(
    get_logger(), "Behavior tree loaded from %s at %.1f Hz",
    xml_path.c_str(), safe_rate_hz);
}

void DecisionProcessNode::tickBehaviorTree()
{
  if (!behavior_tree_) {
    return;
  }
  try {
    behavior_tree_->tickOnce();
  } catch (const std::exception & error) {
    RCLCPP_ERROR_THROTTLE(
      get_logger(), *get_clock(), 2000,
      "Behavior tree tick failed: %s", error.what());
  }
}

rcl_interfaces::msg::SetParametersResult DecisionProcessNode::parametersCallback(
  const std::vector<rclcpp::Parameter> & parameters)
{
  rcl_interfaces::msg::SetParametersResult result;
  result.successful = true;

  std::lock_guard<std::mutex> lock(output_mutex_);
  for (const auto & parameter : parameters) {
    const std::string & name = parameter.get_name();

    if (name == "publish_goal") {
      navigation_command_.enabled = parameter.as_bool();
    } else if (name == "goal_frame_id") {
      if (parameter.as_string().empty()) {
        result.successful = false;
        result.reason = "goal_frame_id cannot be empty";
        break;
      }
      navigation_command_.frame_id = parameter.as_string();
    } else if (name == "goal_x") {
      navigation_command_.x = parameter.as_double();
    } else if (name == "goal_y") {
      navigation_command_.y = parameter.as_double();
    } else if (name == "goal_yaw") {
      navigation_command_.yaw = parameter.as_double();
    } else if (name == "default_posture") {
      if (!integerInRange(parameter, 1, 3)) {
        result.successful = false;
        result.reason = "default_posture must be 1..3";
        break;
      }
      serial_command_.posture = static_cast<uint8_t>(parameter.as_int());
    } else if (name == "default_confirm_respawn") {
      if (!integerInRange(parameter, 0, 1)) {
        result.successful = false;
        result.reason = "default_confirm_respawn must be 0 or 1";
        break;
      }
      serial_command_.confirm_respawn = static_cast<uint8_t>(parameter.as_int());
    } else if (name == "default_tripod_mode") {
      if (!integerInRange(parameter, 0, 1)) {
        result.successful = false;
        result.reason = "default_tripod_mode must be 0 or 1";
        break;
      }
      serial_command_.tripod_mode = static_cast<uint8_t>(parameter.as_int());
    } else if (name == "default_spin_mode") {
      if (!integerInRange(parameter, 0, 3)) {
        result.successful = false;
        result.reason = "default_spin_mode must be 0..3";
        break;
      }
      serial_command_.spin_mode = static_cast<uint8_t>(parameter.as_int());
    } else if (name == "default_shoot_mode") {
      if (!integerInRange(parameter, 0, 1)) {
        result.successful = false;
        result.reason = "default_shoot_mode must be 0 or 1";
        break;
      }
      serial_command_.shoot_mode = static_cast<uint8_t>(parameter.as_int());
    } else if (name == "default_target_color") {
      if (!integerInRange(parameter, 0, 2) || parameter.as_int() == 1) {
        result.successful = false;
        result.reason = "default_target_color must be 0 or 2";
        break;
      }
      autoaim_command_.color = static_cast<uint8_t>(parameter.as_int());
    } else if (name == "default_target_number") {
      if (!integerInRange(parameter, 0, 8)) {
        result.successful = false;
        result.reason = "default_target_number must be 0..8";
        break;
      }
      autoaim_command_.target = static_cast<uint8_t>(parameter.as_int());
    } else if (name == "default_decide_yaw") {
      autoaim_command_.decide_yaw = static_cast<float>(parameter.as_double());
    }
  }

  return result;
}

}  // namespace decision_process
