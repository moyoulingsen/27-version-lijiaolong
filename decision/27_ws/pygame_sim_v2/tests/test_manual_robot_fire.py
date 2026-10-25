from __future__ import annotations

import unittest
from types import SimpleNamespace

from rm2026_sim.app import SimulatorApp
from rm2026_sim.core import SentryState
from rm2026_sim.scenario_store import capture_snapshot, restore_snapshot
from rm2026_sim.task_state import (
    OUTPOST_HIT_PROBABILITY,
    ROBOT_PROFILES,
    TaskScenario,
)


class ManualRobotFireTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = SimulatorApp.__new__(SimulatorApp)
        self.app.task = TaskScenario()
        self.app.sentry = SentryState()
        self.app.controlled_robot_team = "red"
        self.app.controlled_robot_id = 3
        self.app.pending_fire_shooter = None

    def test_robot_mechanisms_follow_rulebook_launcher_exception(self) -> None:
        for target_id, profile in ROBOT_PROFILES.items():
            with self.subTest(target_id=target_id):
                self.assertTrue(profile.has_turntable)
                if target_id == 2:
                    self.assertFalse(profile.has_gimbal)
                    self.assertEqual(profile.projectile, "无")
                    self.assertIsNone(profile.heat_per_shot)
                else:
                    self.assertTrue(profile.has_gimbal)
                    self.assertIn(profile.projectile, ("17mm", "42mm"))
                    self.assertIsNotNone(profile.heat_per_shot)

    def test_selected_robot_aims_and_fires_toward_left_click(self) -> None:
        self.app.task.own_robot_positions[3] = [5.0, 5.0]
        self.app.task.robot_positions[1] = [6.0, 5.0]
        self.app.task.own_robot_ammo[3] = 1
        health_before = self.app.task.enemy_health(1)

        self.app._viewport = lambda: SimpleNamespace(
            contains=lambda x, y: True,
            screen_to_world=lambda x, y: (6.0, 5.0),
        )
        fired = self.app._fire_controlled_robot_at((100, 100))

        self.assertTrue(fired)
        self.assertLess(self.app.task.enemy_health(1), health_before)
        self.assertAlmostEqual(
            self.app.task.robot_view_angle(3, team="red"),
            0.0,
        )

    def test_selected_robot_gimbal_and_turntable_keep_moving(self) -> None:
        self.app.task.set_robot_view_angle(3, 0.75, team="red")
        gimbal_before = self.app.task.robot_view_angle(3, team="red")
        turntable_before = self.app.task.robot_turntable_angle(3, team="red")

        self.app.task.update(0.1, self.app.sentry, fire_request=False)

        self.assertNotEqual(
            self.app.task.robot_view_angle(3, team="red"),
            gimbal_before,
        )
        self.assertNotEqual(
            self.app.task.robot_turntable_angle(3, team="red"),
            turntable_before,
        )

    def test_engineer_has_no_launcher_or_shooting_heat(self) -> None:
        self.app.controlled_robot_id = 2
        self.app.task.own_robot_positions[2] = [5.0, 5.0]
        self.app.task.robot_positions[3] = [6.0, 5.0]
        self.app.task.own_robot_ammo[2] = 1

        result = self.app._fire_controlled_robot_toward((6.0, 5.0))

        self.assertIsNotNone(result)
        self.assertEqual(result.reason, "no_launcher")
        self.assertIsNone(self.app.task.robot_heat_limit(2, team="red"))

    def test_turntable_modes_define_requested_hit_probabilities(self) -> None:
        expected = {1: 0.90, 2: 0.75, 3: 0.50}
        for mode, probability in expected.items():
            with self.subTest(mode=mode):
                self.app.task.set_robot_turntable_mode(3, mode, team="blue")
                self.assertEqual(
                    self.app.task.shooting_hit_probability(3, team="blue"),
                    probability,
                )
        self.assertEqual(
            self.app.task.shooting_hit_probability(
                3,
                team="blue",
                target_id=6,
            ),
            OUTPOST_HIT_PROBABILITY,
        )

    def test_high_speed_turntable_can_turn_aligned_shot_into_miss(self) -> None:
        self.app.task.own_robot_positions[3] = [5.0, 5.0]
        self.app.task.robot_positions[1] = [6.0, 5.0]
        self.app.task.own_robot_ammo[3] = 1
        self.app.task.set_robot_turntable_mode(3, 3, team="red")
        self.app.task.hit_random_seed = 1

        result = self.app._fire_controlled_robot_toward((6.0, 5.0))

        self.assertIsNotNone(result)
        self.assertEqual(result.reason, "fired_miss")
        self.assertEqual(self.app.task.last_hit_probability, 0.50)
        self.assertGreaterEqual(self.app.task.last_hit_roll, 0.50)

    def test_translation_and_turntable_both_contribute_to_power(self) -> None:
        self.app.robot_chassis_dynamics = {}
        self.app.task.set_robot_turntable_mode(3, 1, team="red")
        self.app._update_other_robot_chassis_power(0.1, 0.0, 0.0)
        low_spin_power = self.app.task.own_robot_power[3]

        self.app.robot_chassis_dynamics = {}
        self.app._update_other_robot_chassis_power(0.1, 1.0, 0.0)
        moving_power = self.app.task.own_robot_power[3]

        self.app.robot_chassis_dynamics = {}
        self.app.task.set_robot_turntable_mode(3, 3, team="red")
        self.app._update_other_robot_chassis_power(0.1, 0.0, 0.0)
        high_spin_power = self.app.task.own_robot_power[3]

        self.assertGreater(low_spin_power, 0.0)
        self.assertGreater(moving_power, low_spin_power)
        self.assertGreater(high_spin_power, low_spin_power)
        self.assertEqual(self.app.task.own_robot_power[5], 0.0)

    def test_other_ground_robot_uses_buffer_and_five_second_cut(self) -> None:
        self.app.task.own_robot_buffer_energy[3] = 1.0
        self.app.task.own_robot_power[3] = 100.0

        self.app.task._update_other_robot_power(0.1)

        self.assertTrue(
            self.app.task.robot_chassis_power_cut(3, team="red")
        )
        self.assertEqual(self.app.task.own_robot_buffer_energy[3], 0.0)
        self.assertEqual(self.app.task.own_robot_power[3], 0.0)
        self.assertEqual(
            self.app.task.own_robot_chassis_power_cut_remaining[3],
            5.0,
        )

    def test_turntable_and_power_state_round_trip_in_snapshot(self) -> None:
        self.app.task.set_robot_turntable_mode(4, 3, team="red")
        self.app.task.robot_turntable_angles["red"][4] = 1.25
        self.app.task.own_robot_buffer_energy[4] = 22.0
        self.app.task.own_robot_chassis_power_cut_remaining[4] = 2.5

        snapshot = capture_snapshot(
            "转盘状态",
            self.app.task,
            self.app.sentry,
            4,
            "red",
        )
        restored, _, _ = restore_snapshot(snapshot)

        self.assertEqual(restored.robot_turntable_mode(4, team="red"), 3)
        self.assertEqual(restored.robot_turntable_angles["red"][4], 1.25)
        self.assertEqual(restored.own_robot_buffer_energy[4], 22.0)
        self.assertEqual(
            restored.own_robot_chassis_power_cut_remaining[4],
            2.5,
        )


if __name__ == "__main__":
    unittest.main()
