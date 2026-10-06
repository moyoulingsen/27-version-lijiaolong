#include <gtest/gtest.h>

#include "decision_process/spin_control_logic.hpp"

namespace decision_process
{

TEST(SpinControlLogic, KeepsSpinOffWithoutValidRunningState)
{
  EXPECT_EQ(decideSpinMode(false, 2U, 400U, 0U, 1).spin_mode, 0U);
  EXPECT_EQ(decideSpinMode(true, 1U, 400U, 0U, 1).spin_mode, 0U);
  EXPECT_EQ(decideSpinMode(true, 2U, 0U, 0U, 1).spin_mode, 0U);
}

TEST(SpinControlLogic, KeepsSpinOffWhileOwnOutpostLives)
{
  const auto decision = decideSpinMode(true, 2U, 400U, 1000U, 1);
  ASSERT_TRUE(decision.valid);
  EXPECT_EQ(decision.spin_mode, 0U);
}

TEST(SpinControlLogic, EnablesConfiguredModeAfterOwnOutpostDestroyed)
{
  EXPECT_EQ(decideSpinMode(true, 2U, 400U, 0U, 1).spin_mode, 1U);
  EXPECT_EQ(decideSpinMode(true, 2U, 400U, 0U, 2).spin_mode, 2U);
  EXPECT_EQ(decideSpinMode(true, 2U, 400U, 0U, 3).spin_mode, 3U);
}

TEST(SpinControlLogic, RejectsInvalidEnabledMode)
{
  EXPECT_FALSE(decideSpinMode(true, 2U, 400U, 0U, 0).valid);
  EXPECT_FALSE(decideSpinMode(true, 2U, 400U, 0U, 4).valid);
}

}  // namespace decision_process
