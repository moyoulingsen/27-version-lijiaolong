#ifndef DECISION_PROCESS__AMMO_RESERVE_LOGIC_HPP_
#define DECISION_PROCESS__AMMO_RESERVE_LOGIC_HPP_

#include <algorithm>
#include <cstdint>
#include <limits>

namespace decision_process
{

constexpr uint16_t kMatchDurationSeconds = 420U;
constexpr uint16_t kAmmoGrantIntervalSeconds = 60U;
constexpr uint16_t kAmmoPerGrant = 100U;

class AmmoReserveTracker
{
public:
  void update(uint8_t game_period, uint16_t remaining_time)
  {
    if (game_period != 2U) {
      active_period_ = false;
      return;
    }

    if (!active_period_) {
      active_period_ = true;
      earned_grants_ = 0U;
      claimed_grants_ = 0U;
    }

    const uint16_t bounded_remaining =
      std::min(remaining_time, kMatchDurationSeconds);
    const uint16_t elapsed = kMatchDurationSeconds - bounded_remaining;
    const uint16_t current_grants = elapsed / kAmmoGrantIntervalSeconds;
    earned_grants_ = std::max(earned_grants_, current_grants);
  }

  uint16_t pendingAmmo() const
  {
    const uint32_t unclaimed_grants = earned_grants_ - claimed_grants_;
    const uint32_t pending = unclaimed_grants * kAmmoPerGrant;
    return static_cast<uint16_t>(std::min<uint32_t>(
      pending, std::numeric_limits<uint16_t>::max()));
  }

  void confirmPickup() {claimed_grants_ = earned_grants_;}

  uint16_t earnedGrants() const {return earned_grants_;}
  uint16_t claimedGrants() const {return claimed_grants_;}

private:
  bool active_period_{false};
  uint16_t earned_grants_{0U};
  uint16_t claimed_grants_{0U};
};

}  // namespace decision_process

#endif  // DECISION_PROCESS__AMMO_RESERVE_LOGIC_HPP_
