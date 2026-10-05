#ifndef DECISION_PROCESS__COMMUNICATION_DATA_HPP_
#define DECISION_PROCESS__COMMUNICATION_DATA_HPP_

#include <array>
#include <cstddef>
#include <cstdint>
#include <string>

namespace decision_process
{

constexpr std::size_t kEnemyCount = 8;
constexpr std::size_t kRadarValueCount = 12;
constexpr std::size_t kAutoaimTargetCount = 9;

struct RefereeState
{
  uint8_t game_period{0};
  uint16_t remaining_time{0};
  uint16_t sentry_hp{0};
  uint8_t defence_buff{0};
  uint8_t team_color{0};
  uint16_t ammo{0};
  uint16_t outpost_hp{0};
  uint16_t base_hp{0};
  std::array<uint16_t, kEnemyCount> enemy_hp{};
  std::array<float, kRadarValueCount> radar_data{};
  bool enemy_hp_valid{false};
  bool received{false};
};

struct AutoaimState
{
  std::array<uint8_t, kAutoaimTargetCount> target{};
  std::array<double, kAutoaimTargetCount> target_distance{};
  std::array<double, kAutoaimTargetCount> target_polar_r{};
  std::array<double, kAutoaimTargetCount> target_polar_angle{};
  bool received{false};
};

struct LocalizationState
{
  std::string frame_id;
  double x{0.0};
  double y{0.0};
  double z{0.0};
  double qx{0.0};
  double qy{0.0};
  double qz{0.0};
  double qw{1.0};
  double yaw{0.0};
  bool received{false};
};

struct SerialCommand
{
  uint8_t posture{3};
  uint8_t confirm_respawn{0};
  uint8_t tripod_mode{1};
  uint8_t spin_mode{0};
  uint8_t shoot_mode{0};
};

struct AutoaimCommand
{
  uint8_t color{0};
  uint8_t target{0};
  float decide_yaw{0.0F};
};

struct NavigationCommand
{
  bool enabled{false};
  bool has_goal{false};
  bool reached{false};
  std::string frame_id{"map"};
  double x{0.0};
  double y{0.0};
  double yaw{0.0};
};

}  // namespace decision_process

#endif  // DECISION_PROCESS__COMMUNICATION_DATA_HPP_
