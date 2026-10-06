#include <gtest/gtest.h>

#include <limits>

#include "decision_process/attack_outpost_logic.hpp"

namespace decision_process
{

/*
- 测试对象：EnemyOutpostAlive、EnemyOutpostDestroyed 条件节点和 EngageOutpost 动作节点。
- 检验内容：前哨站血量数据有效性与存活状态判定；
- 敌方装甲颜色选择；
- 目标不可见时的扫描策略；
- 锁定目标且有弹药时的射击策略；
- 无弹药、距离非法或队伍颜色非法时的安全处理。
 */

// 验证只有收到有效敌方血量数据后，才能判定前哨站存活或被摧毁。
TEST(AttackOutpostLogic, RequiresValidEnemyHpBeforeCompletion)
{
  EXPECT_EQ(
    enemyOutpostStatus(false, false, 0U),
    EnemyOutpostStatus::kUnknown);
  EXPECT_EQ(
    enemyOutpostStatus(true, false, 0U),
    EnemyOutpostStatus::kUnknown);
  EXPECT_EQ(
    enemyOutpostStatus(true, true, 500U),
    EnemyOutpostStatus::kAlive);
  EXPECT_EQ(
    enemyOutpostStatus(true, true, 0U),
    EnemyOutpostStatus::kDestroyed);
}

// 验证根据己方颜色选择相反的敌方装甲颜色，并拒绝非法队伍颜色。
TEST(AttackOutpostLogic, SelectsOppositeArmorColor)
{
  uint8_t color = 99U;
  EXPECT_TRUE(enemyArmorColor(0U, color));
  EXPECT_EQ(color, 2U);
  EXPECT_TRUE(enemyArmorColor(1U, color));
  EXPECT_EQ(color, 0U);
  EXPECT_FALSE(enemyArmorColor(2U, color));
}

// 验证前哨站不可见时进入扫描状态，而不会直接开火。
TEST(AttackOutpostLogic, ScansWhenOutpostIsNotVisible)
{
  const auto decision = decideOutpostEngagement(0U, 200U, true, 0U, 0.0);
  ASSERT_TRUE(decision.valid);
  EXPECT_EQ(decision.target, 6U);
  EXPECT_EQ(decision.target_color, 2U);
  EXPECT_EQ(decision.tripod_mode, 1U);
  EXPECT_EQ(decision.shoot_mode, 0U);
}

// 验证仅在有效锁定前哨站且弹药充足时允许射击。
TEST(AttackOutpostLogic, ShootsOnlyWithValidLockAndAmmo)
{
  auto decision = decideOutpostEngagement(1U, 20U, true, 1U, 4.5);
  ASSERT_TRUE(decision.valid);
  EXPECT_EQ(decision.target_color, 0U);
  EXPECT_EQ(decision.tripod_mode, 0U);
  EXPECT_EQ(decision.shoot_mode, 1U);

  decision = decideOutpostEngagement(1U, 0U, true, 1U, 4.5);
  EXPECT_EQ(decision.tripod_mode, 0U);
  EXPECT_EQ(decision.shoot_mode, 0U);
}

// 验证距离或队伍颜色非法时，动作节点采用安全输出或拒绝决策。
TEST(AttackOutpostLogic, RejectsInvalidDistanceAndTeamColor)
{
  auto decision = decideOutpostEngagement(
    0U, 20U, true, 1U, std::numeric_limits<double>::quiet_NaN());
  ASSERT_TRUE(decision.valid);
  EXPECT_EQ(decision.tripod_mode, 1U);
  EXPECT_EQ(decision.shoot_mode, 0U);

  decision = decideOutpostEngagement(3U, 20U, true, 1U, 4.5);
  EXPECT_FALSE(decision.valid);
}

}  // namespace decision_process
