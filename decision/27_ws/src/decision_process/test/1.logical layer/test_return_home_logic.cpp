#include <gtest/gtest.h>

#include "decision_process/return_home_logic.hpp"

namespace decision_process
{

/*
- 测试对象：DecisionProcessNode 的比赛生命周期跟踪逻辑，以及返航行为树中的
- GameFinished 条件节点和 NavigateToPose 动作节点。
- 检验内容：赛前阶段不误判结束；
- 比赛离开进行阶段后判定结束；
- 新比赛开始时清除结束状态；
- 导航目标是否到达采用二维平面距离和正数容差判断。
 */

// 验证赛前 game_period 为 0 时，既不认为比赛已开始，也不认为比赛已结束。
TEST(ReturnHomeLogic, PregameZeroDoesNotMeanFinished)
{
  MatchLifecycle lifecycle;
  lifecycle.update(0U);
  EXPECT_FALSE(lifecycle.hasStarted());
  EXPECT_FALSE(lifecycle.hasFinished());
}

// 验证比赛进入进行阶段后再退出该阶段，会被判定为比赛结束。
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

// 验证新一轮比赛重新进入进行阶段时，会清除上一轮的结束状态。
TEST(ReturnHomeLogic, NewActivePeriodClearsFinishedState)
{
  MatchLifecycle lifecycle;
  lifecycle.update(2U);
  lifecycle.update(0U);
  ASSERT_TRUE(lifecycle.hasFinished());
  lifecycle.update(2U);
  EXPECT_FALSE(lifecycle.hasFinished());
}

// 验证导航到达判定使用二维平面距离，并要求容差为正数。
TEST(ReturnHomeLogic, GoalReachedUsesPlanarTolerance)
{
  EXPECT_TRUE(goalReached(4.971, 7.5, 4.971, 7.5, 0.15));
  EXPECT_TRUE(goalReached(5.071, 7.5, 4.971, 7.5, 0.15));
  EXPECT_FALSE(goalReached(5.2, 7.5, 4.971, 7.5, 0.15));
  EXPECT_FALSE(goalReached(4.971, 7.5, 4.971, 7.5, 0.0));
}

}  // namespace decision_process
