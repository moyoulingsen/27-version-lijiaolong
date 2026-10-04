#include <gtest/gtest.h>

#include <limits>

#include "decision_process/attack_outpost_logic.hpp"

namespace decision_process
{

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

TEST(AttackOutpostLogic, SelectsOppositeArmorColor)
{
  uint8_t color = 99U;
  EXPECT_TRUE(enemyArmorColor(0U, color));
  EXPECT_EQ(color, 2U);
  EXPECT_TRUE(enemyArmorColor(1U, color));
  EXPECT_EQ(color, 0U);
  EXPECT_FALSE(enemyArmorColor(2U, color));
}

TEST(AttackOutpostLogic, ScansWhenOutpostIsNotVisible)
{
  const auto decision = decideOutpostEngagement(0U, 200U, true, 0U, 0.0);
  ASSERT_TRUE(decision.valid);
  EXPECT_EQ(decision.target, 6U);
  EXPECT_EQ(decision.target_color, 2U);
  EXPECT_EQ(decision.tripod_mode, 1U);
  EXPECT_EQ(decision.shoot_mode, 0U);
}

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
