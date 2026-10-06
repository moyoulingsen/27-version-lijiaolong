#ifndef DECISION_PROCESS__GIMBAL_CONTROL_LOGIC_HPP_
#define DECISION_PROCESS__GIMBAL_CONTROL_LOGIC_HPP_

#include <cstdint>

namespace decision_process
{

inline uint8_t decideTripodMode(uint8_t shoot_mode, uint8_t target)
{
  return shoot_mode != 0U && target != 0U ? 0U : 1U;
}

}  // namespace decision_process

#endif  // DECISION_PROCESS__GIMBAL_CONTROL_LOGIC_HPP_
