#include <gtest/gtest.h>

#include <vector>

#include "decision_process/patrol_logic.hpp"

namespace decision_process
{

TEST(PatrolLogic, ParsesArbitraryPointCount)
{
  std::vector<PatrolPoint> points;
  ASSERT_TRUE(parsePatrolPoints(" 1,2 ; 3.5, 4 ; 5,6 ; 7,8 ", points));
  ASSERT_EQ(points.size(), 4U);
  EXPECT_DOUBLE_EQ(points[0].x, 1.0);
  EXPECT_DOUBLE_EQ(points[1].y, 4.0);
  EXPECT_DOUBLE_EQ(points[3].x, 7.0);
}

TEST(PatrolLogic, RejectsMalformedPointList)
{
  std::vector<PatrolPoint> points;
  EXPECT_FALSE(parsePatrolPoints("", points));
  EXPECT_FALSE(parsePatrolPoints("1,2;", points));
  EXPECT_FALSE(parsePatrolPoints("1;2,3", points));
  EXPECT_FALSE(parsePatrolPoints("1,2,3", points));
  EXPECT_FALSE(parsePatrolPoints("nan,2", points));
}

TEST(PatrolLogic, AdvancesBackAndForth)
{
  PatrolStep step{0U, true};
  const std::vector<std::size_t> expected{1U, 2U, 1U, 0U, 1U, 2U};
  for (const std::size_t index : expected) {
    step = advancePatrolStep(step.index, step.forward, 3U);
    EXPECT_EQ(step.index, index);
  }
}

TEST(PatrolLogic, SinglePointRemainsStable)
{
  const PatrolStep step = advancePatrolStep(0U, false, 1U);
  EXPECT_EQ(step.index, 0U);
  EXPECT_TRUE(step.forward);
}

}  // namespace decision_process
