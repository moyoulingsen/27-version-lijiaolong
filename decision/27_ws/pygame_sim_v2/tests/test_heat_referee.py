"""Referee-system tests for dynamic heat and launcher locking."""

from __future__ import annotations

import unittest

from rm2026_sim.core import SentryState
from rm2026_sim.scenario_store import capture_snapshot, restore_snapshot
from rm2026_sim.task_state import TaskScenario


class HeatRefereeTests(unittest.TestCase):
    def test_level_and_performance_tables_drive_referee_limits(self) -> None:
        scenario = TaskScenario()
        self.assertEqual(scenario.robot_resource_limits(1), (160, 50))
        self.assertEqual(scenario.robot_heat_cooling_rate(1), 20.0)

        scenario.robot_level[1] = 10
        scenario.cycle_hero_mode()
        self.assertEqual(scenario.robot_resource_limits(1), (300, 120))
        self.assertEqual(scenario.robot_heat_cooling_rate(1), 30.0)
        self.assertEqual(scenario.robot_q2_limit(1), 500)

        scenario.robot_level[3] = 2
        self.assertEqual(scenario.robot_resource_limits(3), (48, 50))
        self.assertEqual(scenario.robot_heat_cooling_rate(3), 14.0)
        scenario.cycle_infantry_chassis()
        scenario.cycle_infantry_launcher()
        self.assertEqual(scenario.robot_resource_limits(3), (180, 65))
        self.assertEqual(scenario.robot_heat_cooling_rate(3), 7.0)

        scenario.robot_level[5] = 10
        self.assertEqual(scenario.robot_heat_limit(5), 200)
        self.assertEqual(scenario.robot_heat_cooling_rate(5), 120.0)

    def test_42mm_q2_uses_q0_plus_200(self) -> None:
        scenario = TaskScenario()
        self.assertEqual(scenario.robot_heat_limit(1), 160)
        self.assertEqual(scenario.robot_q2_limit(1), 360)
        scenario.robot_heat[1] = 300.0
        scenario.robot_ammo[1] = 1
        self.assertEqual(scenario.record_robot_fire(1, 1, team="blue"), 1)
        self.assertEqual(scenario.robot_heat[1], 400.0)
        self.assertEqual(scenario.robot_heat_lock_state(1, team="blue"), "q2")

    def test_all_weapon_profiles_can_gain_heat_and_lock(self) -> None:
        scenario = TaskScenario()
        for target_id in (1, 3, 4, 5, 8):
            scenario.robot_ammo[target_id] = 100
            self.assertEqual(
                scenario.record_robot_fire(target_id, 1, team="blue"),
                1,
            )
            self.assertGreater(scenario.robot_heat[target_id], 0.0)

        scenario.own_robot_ammo[3] = 100
        self.assertEqual(scenario.record_robot_fire(3, 5, team="red"), 5)
        self.assertEqual(scenario.own_robot_heat[3], 50.0)
        self.assertEqual(scenario.robot_heat_lock_state(3, team="red"), "q1")
        self.assertEqual(scenario.record_robot_fire(3, 1, team="red"), 0)

    def test_q2_boundary_is_permanent_for_red_sentry(self) -> None:
        scenario = TaskScenario(ammo=1)
        sentry = SentryState(heat=350.0)
        self.assertEqual(
            scenario.record_robot_fire(8, team="red", sentry=sentry),
            1,
        )
        self.assertEqual(sentry.heat, 360.0)
        self.assertEqual(scenario.robot_heat_lock_state(8, team="red"), "q2")

    def test_default_sentry_rate_reaches_q1_in_attack_posture(self) -> None:
        scenario = TaskScenario(active_posture=1)
        sentry = SentryState()
        elapsed = 0.0
        while not scenario.sentry_heat_locked and elapsed < 3.0:
            scenario.update(
                0.05,
                sentry,
                fire_request=True,
                hit_target_id=6,
                critical_zone=False,
            )
            elapsed += 0.05
        self.assertTrue(scenario.sentry_heat_locked)
        self.assertLess(elapsed, 2.5)
        self.assertGreater(sentry.heat, 260.0)

    def test_entering_reinforced_attack_posture_clears_heat_immediately(self) -> None:
        scenario = TaskScenario(active_posture=1, sentry_heat_locked=True)
        sentry = SentryState(heat=200.0)
        scenario.toggle_posture_reinforced(sentry)
        self.assertEqual(sentry.heat, 0.0)
        self.assertFalse(scenario.sentry_heat_locked)

    def test_heat_cooling_runs_on_100ms_ticks(self) -> None:
        scenario = TaskScenario()
        sentry = SentryState()
        scenario.robot_heat[3] = 10.0
        scenario.update(0.09, sentry, fire_request=False)
        self.assertEqual(scenario.robot_heat[3], 10.0)
        scenario.update(0.01, sentry, fire_request=False)
        self.assertAlmostEqual(scenario.robot_heat[3], 8.8)

        scenario.robot_heat[3] = 1.0
        scenario.robot_heat_locked[3] = True
        scenario.update(0.1, sentry, fire_request=False)
        self.assertEqual(scenario.robot_heat[3], 0.0)
        self.assertEqual(scenario.robot_heat_lock_state(3, team="blue"), "normal")

    def test_heat_lock_state_round_trips_in_snapshot(self) -> None:
        scenario = TaskScenario()
        sentry = SentryState()
        scenario.robot_heat[1] = 400.0
        scenario.robot_heat_locked[1] = True
        scenario.robot_heat_permanent_lock[1] = True
        scenario.own_robot_heat[3] = 50.0
        scenario.own_robot_heat_locked[3] = True
        snapshot = capture_snapshot("heat", scenario, sentry, None)
        restored, _, _ = restore_snapshot(snapshot)
        self.assertEqual(restored.robot_heat_lock_state(1), "q2")
        self.assertEqual(restored.robot_heat_lock_state(3, team="red"), "q1")


if __name__ == "__main__":
    unittest.main()
