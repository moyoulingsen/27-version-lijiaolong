#include <gtest/gtest.h>

#include "decision_process/ammo_reserve_logic.hpp"

namespace decision_process
{

/*
- 测试对象：DecisionProcessNode 内的弹药储备统计逻辑，以及依赖该结果的
- PendingAmmoAvailable 条件节点和 CollectPendingAmmo 动作节点。
- 检验内容：首分钟结束前不增加储备；
- 每满一分钟增加 100 发；
- 领取后仅清除已累计弹药；
- 时间抖动不回退累计值；
- 新比赛重置领取记录；
- 节点中途启动时可重建应累计的弹药。
 */

// 验证比赛首个一分钟尚未结束时，不会提前获得储备弹药。
TEST(AmmoReserveLogic, NoGrantBeforeFirstMinuteEnds)
{
  AmmoReserveTracker tracker;
  tracker.update(2U, 420U);
  EXPECT_EQ(tracker.pendingAmmo(), 0U);
  tracker.update(2U, 361U);
  EXPECT_EQ(tracker.pendingAmmo(), 0U);
}

// 验证比赛每经过一个完整一分钟，储备弹药增加 100 发。
TEST(AmmoReserveLogic, AddsOneHundredEachCompletedMinute)
{
  AmmoReserveTracker tracker;
  tracker.update(2U, 360U);
  EXPECT_EQ(tracker.pendingAmmo(), 100U);
  tracker.update(2U, 300U);
  EXPECT_EQ(tracker.pendingAmmo(), 200U);
  tracker.update(2U, 30U);
  EXPECT_EQ(tracker.pendingAmmo(), 600U);
}

// 验证确认领取后清空已累计弹药，并继续统计后续新增份额。
TEST(AmmoReserveLogic, PickupClearsOnlyEarnedAmmo)
{
  AmmoReserveTracker tracker;
  tracker.update(2U, 300U);
  ASSERT_EQ(tracker.pendingAmmo(), 200U);
  tracker.confirmPickup();
  EXPECT_EQ(tracker.pendingAmmo(), 0U);
  tracker.update(2U, 240U);
  EXPECT_EQ(tracker.pendingAmmo(), 100U);
}

// 验证剩余时间短暂回跳时，不会扣除已经获得的储备弹药。
TEST(AmmoReserveLogic, TimeJitterDoesNotRemoveEarnedAmmo)
{
  AmmoReserveTracker tracker;
  tracker.update(2U, 300U);
  ASSERT_EQ(tracker.pendingAmmo(), 200U);
  tracker.update(2U, 305U);
  EXPECT_EQ(tracker.pendingAmmo(), 200U);
}

// 验证新一局比赛开始后会清除上一局的领取历史。
TEST(AmmoReserveLogic, NewMatchResetsPickupHistory)
{
  AmmoReserveTracker tracker;
  tracker.update(2U, 300U);
  tracker.confirmPickup();
  ASSERT_EQ(tracker.pendingAmmo(), 0U);
  tracker.update(0U, 0U);
  tracker.update(2U, 360U);
  EXPECT_EQ(tracker.pendingAmmo(), 100U);
}

// 验证节点延迟启动时，可根据当前剩余时间恢复此前应累计的弹药。
TEST(AmmoReserveLogic, LateStartupReconstructsAccumulatedAmmo)
{
  AmmoReserveTracker tracker;
  tracker.update(2U, 30U);
  EXPECT_EQ(tracker.earnedGrants(), 6U);
  EXPECT_EQ(tracker.pendingAmmo(), 600U);
}

}  // namespace decision_process
