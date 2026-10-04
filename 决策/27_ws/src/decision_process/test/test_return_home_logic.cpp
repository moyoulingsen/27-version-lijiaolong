#include <gtest/gtest.h>

#include "decision_process/return_home_logic.hpp"

namespace decision_process
{

TEST(ReturnHomeLogic, PregameZeroDoesNotMeanFinished)
{
  MatchLifecycle lifecycle;
  lifecycle.update(0U);
  EXPECT_FALSE(lifecycle.hasStarted());
  EXPECT_FALSE(lifecycle.hasFinished());
}

TEST(ReturnHomeLogic, LeavingActivePeriodMeansFinished)
{
  MatchLifecycle lifecycle;
  lifecycle.update(1U);
  lifecycle.update(2U);
  EXPECT_TRUE(lifecycle.hasStarted());
  EXPECT_FALSE(lifecycle.hasFinished());
  lifecycle.update(0U);
  EXPECT_TRUE(lifecycle.hasFinished());
}

TEST(ReturnHomeLogic, NewActivePeriodClearsFinishedState)
{
  MatchLifecycle lifecycle;
  lifecycle.update(2U);
  lifecycle.update(0U);
  ASSERT_TRUE(lifecycle.hasFinished());
  lifecycle.update(2U);
  EXPECT_FALSE(lifecycle.hasFinished());
}

TEST(ReturnHomeLogic, GoalReachedUsesPlanarTolerance)
{
  EXPECT_TRUE(goalReached(4.971, 7.5, 4.971, 7.5, 0.15));
  EXPECT_TRUE(goalReached(5.071, 7.5, 4.971, 7.5, 0.15));
  EXPECT_FALSE(goalReached(5.2, 7.5, 4.971, 7.5, 0.15));
  EXPECT_FALSE(goalReached(4.971, 7.5, 4.971, 7.5, 0.0));
}

}  // namespace decision_process
