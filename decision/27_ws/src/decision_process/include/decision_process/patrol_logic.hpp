#ifndef DECISION_PROCESS__PATROL_LOGIC_HPP_
#define DECISION_PROCESS__PATROL_LOGIC_HPP_

#include <cmath>
#include <cstddef>
#include <sstream>
#include <string>
#include <vector>

namespace decision_process
{

struct PatrolPoint
{
  double x{0.0};
  double y{0.0};
};

struct PatrolStep
{
  std::size_t index{0U};
  bool forward{true};
};

inline std::string trimPatrolToken(const std::string & value)
{
  const std::size_t first = value.find_first_not_of(" \t\r\n");
  if (first == std::string::npos) {
    return {};
  }
  const std::size_t last = value.find_last_not_of(" \t\r\n");
  return value.substr(first, last - first + 1U);
}

inline bool parsePatrolNumber(const std::string & text, double & value)
{
  const std::string token = trimPatrolToken(text);
  if (token.empty()) {
    return false;
  }
  try {
    std::size_t consumed = 0U;
    value = std::stod(token, &consumed);
    return consumed == token.size() && std::isfinite(value);
  } catch (...) {
    return false;
  }
}

inline bool parsePatrolPoints(const std::string & text, std::vector<PatrolPoint> & points)
{
  points.clear();
  const std::string normalized = trimPatrolToken(text);
  if (normalized.empty() || normalized.front() == ';' || normalized.back() == ';') {
    return false;
  }
  std::stringstream stream(normalized);
  std::string point_token;
  while (std::getline(stream, point_token, ';')) {
    point_token = trimPatrolToken(point_token);
    if (point_token.empty()) {
      points.clear();
      return false;
    }
    const std::size_t comma = point_token.find(',');
    if (comma == std::string::npos || point_token.find(',', comma + 1U) != std::string::npos) {
      points.clear();
      return false;
    }
    PatrolPoint point;
    if (!parsePatrolNumber(point_token.substr(0U, comma), point.x) ||
      !parsePatrolNumber(point_token.substr(comma + 1U), point.y))
    {
      points.clear();
      return false;
    }
    points.push_back(point);
  }
  return !points.empty();
}

inline PatrolStep advancePatrolStep(std::size_t index, bool forward, std::size_t point_count)
{
  if (point_count <= 1U || index >= point_count) {
    return {0U, true};
  }
  if (forward) {
    if (index + 1U < point_count) {
      return {index + 1U, true};
    }
    return {point_count - 2U, false};
  }
  if (index > 0U) {
    return {index - 1U, false};
  }
  return {1U, true};
}

}  // namespace decision_process

#endif  // DECISION_PROCESS__PATROL_LOGIC_HPP_
