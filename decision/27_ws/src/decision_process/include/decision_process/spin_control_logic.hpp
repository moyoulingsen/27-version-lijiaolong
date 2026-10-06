#ifndef DECISION_PROCESS__SPIN_CONTROL_LOGIC_HPP_
#define DECISION_PROCESS__SPIN_CONTROL_LOGIC_HPP_

#include <cstdint>

namespace decision_process
{

struct SpinControlDecision
{
  bool valid{false};
  uint8_t spin_mode{0U};
};

inline SpinControlDecision decideSpinMode(
  bool referee_received, uint8_t game_period, uint16_t sentry_hp,
  uint16_t own_outpost_hp, int enabled_mode)
{
  if (enabled_mode < 1 || enabled_mode > 3) {
    return {};
  }
  SpinControlDecision decision;
  decision.valid = true;
  decision.spin_mode = referee_received && game_period == 2U && sentry_hp > 0U &&
    own_outpost_hp == 0U ? static_cast<uint8_t>(enabled_mode) : 0U;
  return decision;
}

}  // namespace decision_process

#endif  // DECISION_PROCESS__SPIN_CONTROL_LOGIC_HPP_
