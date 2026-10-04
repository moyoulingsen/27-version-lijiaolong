#ifndef DECISION_PROCESS__ATTACK_OUTPOST_LOGIC_HPP_
#define DECISION_PROCESS__ATTACK_OUTPOST_LOGIC_HPP_

#include <cmath>
#include <cstddef>
#include <cstdint>

namespace decision_process
{

constexpr std::size_t kEnemyOutpostHpIndex = 5U;
constexpr std::size_t kEnemyOutpostTargetIndex = 6U;
constexpr uint8_t kAttackPosture = 1U;
constexpr uint8_t kEnemyOutpostTarget = 6U;

enum class EnemyOutpostStatus
{
  kUnknown,
  kAlive,
  kDestroyed
};

struct OutpostEngagementDecision
{
  bool valid{false};
  uint8_t target_color{0U};
  uint8_t target{kEnemyOutpostTarget};
  uint8_t tripod_mode{1U};
  uint8_t shoot_mode{0U};
};

inline EnemyOutpostStatus enemyOutpostStatus(
  bool referee_received, bool enemy_hp_valid, uint16_t enemy_outpost_hp)
{
  if (!referee_received || !enemy_hp_valid) {
    return EnemyOutpostStatus::kUnknown;
  }
  return enemy_outpost_hp == 0U ?
         EnemyOutpostStatus::kDestroyed : EnemyOutpostStatus::kAlive;
}

inline bool enemyArmorColor(uint8_t own_team_color, uint8_t & enemy_color)
{
  if (own_team_color == 0U) {
    enemy_color = 2U;
    return true;
  }
  if (own_team_color == 1U) {
    enemy_color = 0U;
    return true;
  }
  return false;
}

inline OutpostEngagementDecision decideOutpostEngagement(
  uint8_t own_team_color, uint16_t ammo, bool autoaim_received,
  uint8_t outpost_visible, double outpost_distance)
{
  OutpostEngagementDecision decision;
  if (!enemyArmorColor(own_team_color, decision.target_color)) {
    return decision;
  }

  decision.valid = true;
  const bool has_valid_lock =
    autoaim_received && outpost_visible != 0U &&
    std::isfinite(outpost_distance) && outpost_distance > 0.0;
  decision.tripod_mode = has_valid_lock ? 0U : 1U;
  decision.shoot_mode = has_valid_lock && ammo > 0U ? 1U : 0U;
  return decision;
}

}  // namespace decision_process

#endif  // DECISION_PROCESS__ATTACK_OUTPOST_LOGIC_HPP_
