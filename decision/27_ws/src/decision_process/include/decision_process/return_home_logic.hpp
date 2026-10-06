#ifndef DECISION_PROCESS__RETURN_HOME_LOGIC_HPP_
#define DECISION_PROCESS__RETURN_HOME_LOGIC_HPP_

#include <cmath>
#include <cstdint>

namespace decision_process
{

class MatchLifecycle
{
public:
  void update(uint8_t game_period)
  {
    if (game_period == 2U) {
      has_started_ = true;
      has_finished_ = false;
    } else if (has_started_) {
      has_finished_ = true;
    }
  }

  bool hasStarted() const {return has_started_;}
  bool hasFinished() const {return has_finished_;}

private:
  bool has_started_{false};
  bool has_finished_{false};
};

inline double planarDistance(double x1, double y1, double x2, double y2)
{
  return std::hypot(x2 - x1, y2 - y1);
}

inline bool goalReached(
  double current_x, double current_y,
  double goal_x, double goal_y, double tolerance)
{
  return tolerance > 0.0 &&
         planarDistance(current_x, current_y, goal_x, goal_y) <= tolerance;
}

}  // namespace decision_process

#endif  // DECISION_PROCESS__RETURN_HOME_LOGIC_HPP_
