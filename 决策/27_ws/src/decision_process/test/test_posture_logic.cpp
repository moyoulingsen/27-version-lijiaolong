#include <gtest/gtest.h>

#include "decision_process/posture_logic.hpp"

namespace decision_process
{

TEST(PostureLogic, DefaultPostureIsMobile)
{
  PostureSwitchPolicy policy;
  EXPECT_EQ(policy.currentPosture(), 3U);
}

TEST(PostureLogic, FirstSwitchIsImmediate)
{
  PostureSwitchPolicy policy;
  EXPECT_EQ(policy.request(1U, 10.0, 5.0), PostureDecision::kSwitched);
  EXPECT_EQ(policy.currentPosture(), 1U);
}

TEST(PostureLogic, CooldownPreventsRapidSwitch)
{
  PostureSwitchPolicy policy;
  ASSERT_EQ(policy.request(1U, 10.0, 5.0), PostureDecision::kSwitched);
  EXPECT_EQ(policy.request(2U, 12.0, 5.0), PostureDecision::kWaitingForCooldown);
  EXPECT_EQ(policy.currentPosture(), 1U);
  EXPECT_EQ(policy.request(2U, 15.0, 5.0), PostureDecision::kSwitched);
  EXPECT_EQ(policy.currentPosture(), 2U);
}

TEST(PostureLogic, SamePostureIsHeld)
{
  PostureSwitchPolicy policy;
  EXPECT_EQ(policy.request(3U, 1.0, 5.0), PostureDecision::kHold);
}

TEST(PostureLogic, InvalidPostureIsRejected)
{
  PostureSwitchPolicy policy;
  EXPECT_EQ(policy.request(0U, 1.0, 5.0), PostureDecision::kInvalid);
  EXPECT_EQ(policy.request(4U, 1.0, 5.0), PostureDecision::kInvalid);
}

}  // namespace decision_process
