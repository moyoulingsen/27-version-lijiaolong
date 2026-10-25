#include "patrol_nodes.hpp"

#include <cmath>
#include <cstddef>
#include <exception>
#include <sstream>
#include <string>
#include <vector>

namespace decision_process
{
namespace
{

struct Point
{
  double x;
  double y;
};

bool parseDouble(const std::string & text, double & value)
{
  try
  {
    std::size_t consumed = 0;
    value = std::stod(text, &consumed);
    return consumed == text.size() && std::isfinite(value);
  }
  catch(const std::exception &)
  {
    return false;
  }
}

bool parsePoints(const std::string & text, std::vector<Point> & points)
{
  std::stringstream point_stream(text);
  std::string point_text;
  while(std::getline(point_stream, point_text, ';'))
  {
    if(point_text.empty())
    {
      return false;
    }

    const auto comma = point_text.find(',');
    if(comma == std::string::npos || point_text.find(',', comma + 1) != std::string::npos)
    {
      return false;
    }

    Point point{};
    if(!parseDouble(point_text.substr(0, comma), point.x) ||
      !parseDouble(point_text.substr(comma + 1), point.y))
    {
      return false;
    }
    points.push_back(point);
  }
  return !points.empty();
}

}  // namespace

SelectPatrolPointAction::SelectPatrolPointAction(
  const std::string & name, const BT::NodeConfig & config)
: BT::SyncActionNode(name, config)
{
}

BT::PortsList SelectPatrolPointAction::providedPorts()
{
  return {
    BT::InputPort<std::string>("points", "Semicolon-separated x,y points"),
    BT::InputPort<int>("index", 0, "Current point index"),
    BT::OutputPort<double>("target_x"),
    BT::OutputPort<double>("target_y"),
    BT::OutputPort<int>("point_count")};
}

BT::NodeStatus SelectPatrolPointAction::tick()
{
  const auto points_text = getInput<std::string>("points");
  const auto index = getInput<int>("index");
  if(!points_text || !index || index.value() < 0)
  {
    return BT::NodeStatus::FAILURE;
  }

  std::vector<Point> points;
  if(!parsePoints(points_text.value(), points))
  {
    return BT::NodeStatus::FAILURE;
  }

  // Conservative and aggressive routes intentionally share one blackboard
  // index.  Their point counts may differ, so normalize the index whenever
  // the active route changes instead of failing on a stale larger index.
  const std::size_t normalized_index =
    static_cast<std::size_t>(index.value()) % points.size();
  setOutput("target_x", points[normalized_index].x);
  setOutput("target_y", points[normalized_index].y);
  setOutput("point_count", static_cast<int>(points.size()));
  return BT::NodeStatus::SUCCESS;
}

AdvancePatrolPointAction::AdvancePatrolPointAction(
  const std::string & name, const BT::NodeConfig & config)
: BT::SyncActionNode(name, config)
{
}

BT::PortsList AdvancePatrolPointAction::providedPorts()
{
  return {
    BT::InputPort<int>("index", 0, "Current point index"),
    BT::InputPort<int>("point_count"),
    BT::OutputPort<int>("next_index")};
}

BT::NodeStatus AdvancePatrolPointAction::tick()
{
  const auto index = getInput<int>("index");
  const auto point_count = getInput<int>("point_count");
  if(!index || !point_count || index.value() < 0 || point_count.value() <= 0)
  {
    return BT::NodeStatus::FAILURE;
  }

  setOutput("next_index", (index.value() + 1) % point_count.value());
  return BT::NodeStatus::SUCCESS;
}

void registerPatrolNodes(BT::BehaviorTreeFactory & factory)
{
  factory.registerNodeType<SelectPatrolPointAction>("SelectPatrolPoint");
  factory.registerNodeType<AdvancePatrolPointAction>("AdvancePatrolPoint");
}

}  // namespace decision_process
