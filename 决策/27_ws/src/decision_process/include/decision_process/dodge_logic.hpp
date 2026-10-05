#ifndef DECISION_PROCESS__DODGE_LOGIC_HPP_
#define DECISION_PROCESS__DODGE_LOGIC_HPP_

#include <algorithm>
#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>

#include "decision_process/communication_data.hpp"

namespace decision_process
{

class DamageTracker
{
public:
  void update(uint16_t current_hp, double now_seconds)
  {
    if (!initialized_) {
      previous_hp_ = current_hp;
      initialized_ = true;
      return;
    }
    if (current_hp < previous_hp_ && std::isfinite(now_seconds)) {
      last_damage_seconds_ = now_seconds;
      has_damage_event_ = true;
    }
    previous_hp_ = current_hp;
  }

  bool recentlyDamaged(double now_seconds, double quiet_period_seconds) const
  {
    return has_damage_event_ && std::isfinite(now_seconds) &&
           std::isfinite(quiet_period_seconds) && quiet_period_seconds >= 0.0 &&
           now_seconds >= last_damage_seconds_ &&
           now_seconds - last_damage_seconds_ <= quiet_period_seconds;
  }

private:
  bool initialized_{false};
  bool has_damage_event_{false};
  uint16_t previous_hp_{0U};
  double last_damage_seconds_{0.0};
};

inline bool noVisibleEnemy(const AutoaimState & state)
{
  return state.received && std::none_of(
    state.target.begin(), state.target.end(),
    [](uint8_t visible) {return visible != 0U;});
}

struct EvasionGoal
{
  bool valid{false};
  double x{0.0};
  double y{0.0};
};

inline EvasionGoal makeEvasionGoal(
  double current_x, double current_y, double step, std::size_t direction_index,
  double min_x, double max_x, double min_y, double max_y)
{
  EvasionGoal goal;
  if (!std::isfinite(current_x) || !std::isfinite(current_y) ||
    !std::isfinite(step) || step <= 0.0 ||
    !std::isfinite(min_x) || !std::isfinite(max_x) ||
    !std::isfinite(min_y) || !std::isfinite(max_y) ||
    min_x >= max_x || min_y >= max_y)
  {
    return goal;
  }

  static constexpr std::array<double, 4> kDirectionX{0.0, 1.0, 0.0, -1.0};
  static constexpr std::array<double, 4> kDirectionY{1.0, 0.0, -1.0, 0.0};
  const std::size_t index = direction_index % kDirectionX.size();
  goal.x = std::clamp(current_x + step * kDirectionX[index], min_x, max_x);
  goal.y = std::clamp(current_y + step * kDirectionY[index], min_y, max_y);
  goal.valid = std::hypot(goal.x - current_x, goal.y - current_y) > 1e-6;
  return goal;
}

}  // namespace decision_process

#endif  // DECISION_PROCESS__DODGE_LOGIC_HPP_
