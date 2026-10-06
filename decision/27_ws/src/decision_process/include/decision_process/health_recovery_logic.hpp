#ifndef DECISION_PROCESS__HEALTH_RECOVERY_LOGIC_HPP_
#define DECISION_PROCESS__HEALTH_RECOVERY_LOGIC_HPP_

#include <cstdint>

namespace decision_process
{

constexpr uint16_t kFixedRecoveryThreshold = 200U;

inline bool validRecoveryThreshold(int threshold)
{
  return threshold >= 1 && threshold <= 400;
}

inline bool needsHealthRecovery(
  bool referee_received, uint8_t game_period, uint16_t sentry_hp,
  int health_threshold)
{
  return validRecoveryThreshold(health_threshold) && referee_received &&
         game_period == 2U && sentry_hp > 0U &&
         sentry_hp < static_cast<uint16_t>(health_threshold);
}

}  // namespace decision_process

#endif  // DECISION_PROCESS__HEALTH_RECOVERY_LOGIC_HPP_
