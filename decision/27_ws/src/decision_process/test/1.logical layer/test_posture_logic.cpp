#include <gtest/gtest.h>

#include "decision_process/posture_logic.hpp"

namespace decision_process
{

/*
- 测试对象：ApplyPosture 动作节点内部使用的 PostureSwitchPolicy 姿态切换策略。
- 检验内容：默认移动姿态；
- 首次请求立即切换；
- 冷却时间内禁止快速切换；
- 请求保持当前姿态时不重复切换；
- 超出合法范围的姿态请求被拒绝。
 */

// 验证策略初始化后默认处于移动姿态。
TEST(PostureLogic, DefaultPostureIsMobile)
{
  PostureSwitchPolicy policy;
  EXPECT_EQ(policy.currentPosture(), 3U);
}

// 验证首次收到合法姿态请求时可以立即完成切换。
TEST(PostureLogic, FirstSwitchIsImmediate)
{
  PostureSwitchPolicy policy;
  EXPECT_EQ(policy.request(1U, 10.0, 5.0), PostureDecision::kSwitched);
  EXPECT_EQ(policy.currentPosture(), 1U);
}

// 验证冷却时间内拒绝连续切换，冷却结束后允许切换。
TEST(PostureLogic, CooldownPreventsRapidSwitch)
{
  PostureSwitchPolicy policy;
  ASSERT_EQ(policy.request(1U, 10.0, 5.0), PostureDecision::kSwitched);
  EXPECT_EQ(policy.request(2U, 12.0, 5.0), PostureDecision::kWaitingForCooldown);
  EXPECT_EQ(policy.currentPosture(), 1U);
  EXPECT_EQ(policy.request(2U, 15.0, 5.0), PostureDecision::kSwitched);
  EXPECT_EQ(policy.currentPosture(), 2U);
}

// 验证请求的姿态与当前姿态一致时保持原状态。
TEST(PostureLogic, SamePostureIsHeld)
{
  PostureSwitchPolicy policy;
  EXPECT_EQ(policy.request(3U, 1.0, 5.0), PostureDecision::kHold);
}

// 验证不在合法取值范围内的姿态请求会被拒绝。
TEST(PostureLogic, InvalidPostureIsRejected)
{
  PostureSwitchPolicy policy;
  EXPECT_EQ(policy.request(0U, 1.0, 5.0), PostureDecision::kInvalid);
  EXPECT_EQ(policy.request(4U, 1.0, 5.0), PostureDecision::kInvalid);
}

}  // namespace decision_process
