#include <gtest/gtest.h>

#include "decision_process/ammo_reserve_logic.hpp"

namespace decision_process
{

TEST(AmmoReserveLogic, NoGrantBeforeFirstMinuteEnds)
{
  AmmoReserveTracker tracker;
  tracker.update(2U, 420U);
  EXPECT_EQ(tracker.pendingAmmo(), 0U);
  tracker.update(2U, 361U);
  EXPECT_EQ(tracker.pendingAmmo(), 0U);
}

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

TEST(AmmoReserveLogic, TimeJitterDoesNotRemoveEarnedAmmo)
{
  AmmoReserveTracker tracker;
  tracker.update(2U, 300U);
  ASSERT_EQ(tracker.pendingAmmo(), 200U);
  tracker.update(2U, 305U);
  EXPECT_EQ(tracker.pendingAmmo(), 200U);
}

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

TEST(AmmoReserveLogic, LateStartupReconstructsAccumulatedAmmo)
{
  AmmoReserveTracker tracker;
  tracker.update(2U, 30U);
  EXPECT_EQ(tracker.earnedGrants(), 6U);
  EXPECT_EQ(tracker.pendingAmmo(), 600U);
}

}  // namespace decision_process
