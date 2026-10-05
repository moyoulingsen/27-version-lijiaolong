#include <gtest/gtest.h>

#include <limits>

#include "decision_process/dodge_logic.hpp"

namespace decision_process
{

TEST(DodgeLogic, FirstHpSampleDoesNotCountAsDamage)
{
  DamageTracker tracker;
  tracker.update(400U, 10.0);
  EXPECT_FALSE(tracker.recentlyDamaged(10.0, 2.0));
}

TEST(DodgeLogic, HpDropTriggersAndThenExpires)
{
  DamageTracker tracker;
  tracker.update(400U, 10.0);
  tracker.update(350U, 11.0);
  EXPECT_TRUE(tracker.recentlyDamaged(12.5, 2.0));
  EXPECT_FALSE(tracker.recentlyDamaged(13.1, 2.0));
}

TEST(DodgeLogic, HealingDoesNotExtendDamageWindow)
{
  DamageTracker tracker;
  tracker.update(400U, 10.0);
  tracker.update(350U, 11.0);
  tracker.update(400U, 12.0);
  EXPECT_FALSE(tracker.recentlyDamaged(13.1, 2.0));
}

TEST(DodgeLogic, RepeatedDamageExtendsWindow)
{
  DamageTracker tracker;
  tracker.update(400U, 10.0);
  tracker.update(380U, 11.0);
  tracker.update(360U, 12.5);
  EXPECT_TRUE(tracker.recentlyDamaged(14.0, 2.0));
}

TEST(DodgeLogic, RequiresReceivedAutoaimWithNoVisibleTarget)
{
  AutoaimState state;
  EXPECT_FALSE(noVisibleEnemy(state));
  state.received = true;
  EXPECT_TRUE(noVisibleEnemy(state));
  state.target[0] = 1U;
  EXPECT_FALSE(noVisibleEnemy(state));
  state.target[0] = 0U;
  state.target[6] = 1U;
  EXPECT_FALSE(noVisibleEnemy(state));
}

TEST(DodgeLogic, EvasionGoalUsesDirectionAndMapBounds)
{
  auto goal = makeEvasionGoal(5.0, 5.0, 0.8, 0U, 0.2, 27.8, 0.2, 14.8);
  ASSERT_TRUE(goal.valid);
  EXPECT_DOUBLE_EQ(goal.x, 5.0);
  EXPECT_DOUBLE_EQ(goal.y, 5.8);

  goal = makeEvasionGoal(27.7, 5.0, 0.8, 1U, 0.2, 27.8, 0.2, 14.8);
  ASSERT_TRUE(goal.valid);
  EXPECT_DOUBLE_EQ(goal.x, 27.8);
  EXPECT_DOUBLE_EQ(goal.y, 5.0);
}

TEST(DodgeLogic, RejectsInvalidEvasionParameters)
{
  EXPECT_FALSE(makeEvasionGoal(5.0, 5.0, 0.0, 0U, 0.2, 27.8, 0.2, 14.8).valid);
  EXPECT_FALSE(makeEvasionGoal(5.0, 5.0, 0.8, 0U, 1.0, 1.0, 0.2, 14.8).valid);
  EXPECT_FALSE(makeEvasionGoal(
    5.0, 5.0, std::numeric_limits<double>::quiet_NaN(),
    0U, 0.2, 27.8, 0.2, 14.8).valid);
}

}  // namespace decision_process
