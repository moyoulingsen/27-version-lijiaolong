#include <gtest/gtest.h>

#include "decision_process/health_recovery_logic.hpp"

namespace decision_process
{

TEST(HealthThresholdParameter, AcceptsRuleRange)
{
  EXPECT_TRUE(validRecoveryThreshold(1));
  EXPECT_TRUE(validRecoveryThreshold(200));
  EXPECT_TRUE(validRecoveryThreshold(400));
  EXPECT_FALSE(validRecoveryThreshold(0));
  EXPECT_FALSE(validRecoveryThreshold(401));
}

TEST(HealthThresholdParameter, ChangesDecisionAtRuntime)
{
  EXPECT_FALSE(needsHealthRecovery(true, 2U, 250U, 200));
  EXPECT_TRUE(needsHealthRecovery(true, 2U, 250U, 260));
  EXPECT_FALSE(needsHealthRecovery(true, 2U, 260U, 260));
}

}  // namespace decision_process
