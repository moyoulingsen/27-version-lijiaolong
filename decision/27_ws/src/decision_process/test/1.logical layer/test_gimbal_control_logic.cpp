#include <gtest/gtest.h>

#include "decision_process/gimbal_control_logic.hpp"

namespace decision_process
{

TEST(GimbalControlLogic, RotatesWhenThereIsNoShootableTarget)
{
  EXPECT_EQ(decideTripodMode(0U, 0U), 1U);
  EXPECT_EQ(decideTripodMode(0U, 6U), 1U);
  EXPECT_EQ(decideTripodMode(1U, 0U), 1U);
}

TEST(GimbalControlLogic, StopsOnlyWhileShootingSelectedTarget)
{
  EXPECT_EQ(decideTripodMode(1U, 1U), 0U);
  EXPECT_EQ(decideTripodMode(1U, 6U), 0U);
}

}  // namespace decision_process
