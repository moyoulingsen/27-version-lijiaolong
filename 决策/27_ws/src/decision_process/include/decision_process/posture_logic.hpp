#ifndef DECISION_PROCESS__POSTURE_LOGIC_HPP_
#define DECISION_PROCESS__POSTURE_LOGIC_HPP_

#include <cmath>
#include <cstdint>

namespace decision_process
{

enum class PostureDecision
{
  kInvalid,
  kHold,
  kWaitingForCooldown,
  kSwitched
};

class PostureSwitchPolicy
{
public:
  explicit PostureSwitchPolicy(uint8_t initial_posture = 3U)
  : current_posture_(initial_posture)
  {
  }

  PostureDecision request(uint8_t requested, double now_seconds, double cooldown_seconds)
  {
    if (requested < 1U || requested > 3U || !std::isfinite(now_seconds) ||
      !std::isfinite(cooldown_seconds) || cooldown_seconds < 0.0)
    {
      return PostureDecision::kInvalid;
    }
    if (requested == current_posture_) {
      return PostureDecision::kHold;
    }
    if (!has_switched_ || now_seconds - last_switch_seconds_ >= cooldown_seconds) {
      current_posture_ = requested;
      last_switch_seconds_ = now_seconds;
      has_switched_ = true;
      return PostureDecision::kSwitched;
    }
    return PostureDecision::kWaitingForCooldown;
  }

  uint8_t currentPosture() const {return current_posture_;}

private:
  uint8_t current_posture_{3U};
  double last_switch_seconds_{0.0};
  bool has_switched_{false};
};

}  // namespace decision_process

#endif  // DECISION_PROCESS__POSTURE_LOGIC_HPP_
