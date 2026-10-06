#include <gtest/gtest.h>

#include <limits>

#include "decision_process/dodge_logic.hpp"

namespace decision_process
{

/*
- 测试对象：DecisionProcessNode 的受伤跟踪逻辑，以及 RecentDamage、NoEnemyVisible 条件节点
- 和 EvadeUntilSafe 动作节点。
- 检验内容：首次血量采样、掉血触发与静默窗口；
- 回血和连续受伤对窗口的影响；
- 自瞄目标可见性判断；
- 躲避目标的方向、地图边界约束和非法参数处理。
 */

// 验证首次血量采样只用于建立基准，不会被误判为受到伤害。
TEST(DodgeLogic, FirstHpSampleDoesNotCountAsDamage)
{
  DamageTracker tracker;
  tracker.update(400U, 10.0);
  EXPECT_FALSE(tracker.recentlyDamaged(10.0, 2.0));
}

// 验证血量下降会触发近期受伤状态，并在静默时间结束后失效。
TEST(DodgeLogic, HpDropTriggersAndThenExpires)
{
  DamageTracker tracker;
  tracker.update(400U, 10.0);
  tracker.update(350U, 11.0);
  EXPECT_TRUE(tracker.recentlyDamaged(12.5, 2.0));
  EXPECT_FALSE(tracker.recentlyDamaged(13.1, 2.0));
}

// 验证回血不会延长最后一次受伤所对应的躲避时间窗口。
TEST(DodgeLogic, HealingDoesNotExtendDamageWindow)
{
  DamageTracker tracker;
  tracker.update(400U, 10.0);
  tracker.update(350U, 11.0);
  tracker.update(400U, 12.0);
  EXPECT_FALSE(tracker.recentlyDamaged(13.1, 2.0));
}

// 验证连续受到伤害会以最近一次掉血时间重新计算躲避窗口。
TEST(DodgeLogic, RepeatedDamageExtendsWindow)
{
  DamageTracker tracker;
  tracker.update(400U, 10.0);
  tracker.update(380U, 11.0);
  tracker.update(360U, 12.5);
  EXPECT_TRUE(tracker.recentlyDamaged(14.0, 2.0));
}

// 验证必须已收到自瞄数据且所有目标均不可见，才判定为无可见敌人。
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

// 验证躲避目标按指定方向生成，并被限制在地图边界范围内。
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

// 验证移动步长、地图边界或数值非法时，不生成有效躲避目标。
TEST(DodgeLogic, RejectsInvalidEvasionParameters)
{
  EXPECT_FALSE(makeEvasionGoal(5.0, 5.0, 0.0, 0U, 0.2, 27.8, 0.2, 14.8).valid);
  EXPECT_FALSE(makeEvasionGoal(5.0, 5.0, 0.8, 0U, 1.0, 1.0, 0.2, 14.8).valid);
  EXPECT_FALSE(makeEvasionGoal(
    5.0, 5.0, std::numeric_limits<double>::quiet_NaN(),
    0U, 0.2, 27.8, 0.2, 14.8).valid);
}

}  // namespace decision_process
