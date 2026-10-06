#include <gtest/gtest.h>

#include "decision_process/health_recovery_logic.hpp"

namespace decision_process
{

TEST(HealthRecoveryLogic, TriggersStrictlyBelowTwoHundred)
{
  EXPECT_TRUE(needsHealthRecovery(true, 2U, 199U, 200));
  EXPECT_FALSE(needsHealthRecovery(true, 2U, 200U, 200));
  EXPECT_FALSE(needsHealthRecovery(true, 2U, 201U, 200));
}

TEST(HealthRecoveryLogic, RequiresRunningAliveAndReceivedState)
{
  EXPECT_FALSE(needsHealthRecovery(false, 2U, 100U, 200));
  EXPECT_FALSE(needsHealthRecovery(true, 1U, 100U, 200));
  EXPECT_FALSE(needsHealthRecovery(true, 2U, 0U, 200));
}

}  // namespace decision_process
