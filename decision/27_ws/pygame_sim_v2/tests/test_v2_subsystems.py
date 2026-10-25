"""Engineering assembly, dart, and radar regression tests."""

from __future__ import annotations

import unittest

from rm2026_sim.core import SentryState
from rm2026_sim.task_state import TaskScenario


RED_ASSEMBLY_ZONE = [[0.0, 5.0], [5.0, 5.0], [5.0, 10.0], [0.0, 10.0]]


class EngineeringAssemblyTests(unittest.TestCase):
    def _scenario(self, **kwargs) -> TaskScenario:
        return TaskScenario(
            field_zone_overrides={"region_12_assembly_red": RED_ASSEMBLY_ZONE},
            **kwargs,
        )

    def _place_engineer_in_zone(self, scenario: TaskScenario) -> None:
        scenario.own_robot_positions[2] = [2.5, 7.5]

    def _complete(self, scenario: TaskScenario, difficulty: int) -> None:
        # Effect-specific regression tests should not depend on the calibrated
        # random success table.  Probability behavior is covered separately.
        scenario.assembly_success_probability[difficulty] = 1.0
        self.assertTrue(scenario.select_assembly_difficulty(difficulty))
        self.assertTrue(scenario.start_assembly())
        scenario.update(scenario.assembly_required + 0.1, SentryState())

    def test_fixed_success_probability_table_is_calibrated_per_difficulty(self) -> None:
        scenario = self._scenario()
        self.assertEqual(
            scenario.assembly_success_probability,
            {1: 0.95, 2: 0.80, 3: 0.40, 4: 0.05},
        )

    def test_zero_probability_fails_without_applying_effect(self) -> None:
        scenario = self._scenario(
            assembly_success_probability={1: 0.0, 2: 1.0, 3: 1.0, 4: 1.0}
        )
        self._place_engineer_in_zone(scenario)
        self.assertTrue(scenario.select_assembly_difficulty(1))
        self.assertTrue(scenario.start_assembly())
        scenario.update(scenario.assembly_required + 0.1, SentryState())

        self.assertEqual(scenario.assembly_last_result, "失败")
        self.assertNotIn(1, scenario.assembly_completed)
        self.assertEqual(scenario.assembly_bonus_per_10s, 0)

    def test_unmarked_zone_blocks_assembly(self) -> None:
        scenario = TaskScenario()
        scenario.own_robot_positions[2] = [2.5, 7.5]

        self.assertFalse(scenario.select_assembly_difficulty(1))
        self.assertIn("标注己方装配区", scenario.event_message)

    def test_difficulty_one_completes_and_grants_income(self) -> None:
        scenario = self._scenario(economy=400)
        self._place_engineer_in_zone(scenario)
        self._complete(scenario, 1)
        self.assertIn(1, scenario.assembly_completed)
        self.assertEqual(scenario.assembly_bonus_per_10s, 50)
        before = scenario.economy
        scenario.update(10.0, SentryState())
        self.assertEqual(scenario.economy, before + 50)

    def test_difficulty_two_needs_previous_and_time_window(self) -> None:
        scenario = self._scenario(remaining_time=420.0)
        self._place_engineer_in_zone(scenario)
        self.assertFalse(scenario.select_assembly_difficulty(2))
        scenario.remaining_time = 360.0
        self.assertFalse(scenario.select_assembly_difficulty(2))
        scenario.assembly_completed.add(1)
        self.assertTrue(scenario.select_assembly_difficulty(2))
        self.assertEqual(scenario.assembly_difficulty, 2)

    def test_difficulty_two_first_and_repeat_rewards_and_own_level_cap(self) -> None:
        scenario = self._scenario(remaining_time=360.0)
        self._place_engineer_in_zone(scenario)
        scenario.assembly_completed.add(1)

        self._complete(scenario, 2)
        self.assertEqual(scenario.level_cap, 7)
        self.assertEqual(scenario.enemy_level_cap, 5)
        self.assertEqual(scenario.assembly_bonus_per_10s, 25)

        self._complete(scenario, 2)
        self.assertEqual(scenario.assembly_bonus_per_10s, 35)

    def test_difficulty_three_defends_ground_robots_outpost_and_base(self) -> None:
        scenario = self._scenario(remaining_time=300.0)
        self._place_engineer_in_zone(scenario)
        scenario.assembly_completed.update((1, 2))
        self._complete(scenario, 3)

        self.assertEqual(scenario.level_cap, 10)
        self.assertEqual(scenario.assembly_bonus_per_10s, 25)
        self.assertEqual(scenario.apply_attack_damage(1, "17mm", team="red"), 15)
        self.assertEqual(scenario.apply_attack_damage(1, "17mm", team="blue"), 20)
        self.assertEqual(scenario.apply_attack_damage(6, "17mm", team="red"), 15)
        scenario.own_outpost_hp = 0
        self.assertEqual(scenario.apply_attack_damage(7, "17mm", team="red"), 15)

    def test_difficulty_four_adds_base_hp_overflow_to_shield_and_is_once_only(self) -> None:
        scenario = self._scenario(
            remaining_time=240.0,
            own_base_hp=4000,
            own_base_shield=150,
        )
        self._place_engineer_in_zone(scenario)
        scenario.assembly_completed.update((1, 2, 3))
        self._complete(scenario, 4)

        self.assertEqual(scenario.own_base_max_hp, 5000)
        self.assertEqual(scenario.own_base_hp, 5000)
        self.assertEqual(scenario.own_base_shield, 1150)
        self.assertAlmostEqual(scenario.assembly_defence, 0.50)
        self.assertEqual(scenario.assembly_bonus_per_10s, 50)
        self.assertFalse(scenario.select_assembly_difficulty(4))

    def test_engineer_must_leave_for_fifteen_seconds_to_fail(self) -> None:
        scenario = self._scenario()
        self._place_engineer_in_zone(scenario)
        scenario.select_assembly_difficulty(1)
        scenario.start_assembly()
        scenario.own_robot_positions[2] = [10.0, 10.0]

        scenario.update(14.9, SentryState())
        self.assertTrue(scenario.assembly_active)
        scenario.update(0.2, SentryState())
        self.assertFalse(scenario.assembly_active)

    def test_failed_fourth_level_has_ninety_second_cooldown(self) -> None:
        scenario = self._scenario(remaining_time=240.0)
        self._place_engineer_in_zone(scenario)
        scenario.assembly_completed.update((1, 2, 3))
        self.assertTrue(scenario.select_assembly_difficulty(4))
        self.assertTrue(scenario.start_assembly())
        scenario.own_robot_positions[2] = [10.0, 10.0]

        scenario.update(15.0, SentryState())

        self.assertFalse(scenario.assembly_active)
        self.assertEqual(scenario.assembly_level4_cooldown_remaining, 90.0)
        self._place_engineer_in_zone(scenario)
        self.assertFalse(scenario.start_assembly())


class DartSystemTests(unittest.TestCase):
    def _open_gate(self, scenario: TaskScenario) -> None:
        self.assertTrue(scenario.open_dart_gate())
        scenario.update(7.1, SentryState())

    def test_dart_hits_outpost_for_750(self) -> None:
        scenario = TaskScenario()
        self._open_gate(scenario)
        self.assertEqual(scenario.dart_gate_state, "open")
        self.assertTrue(scenario.fire_dart())
        scenario.update(1.1, SentryState())
        self.assertEqual(scenario.enemy_outpost_hp, 750.0)
        self.assertEqual(scenario.darts_remaining, 3)

    def test_dart_uses_base_damage_after_outpost_destroyed(self) -> None:
        scenario = TaskScenario(
            enemy_outpost_hp=0.0,
            enemy_outpost_destroyed_ever=True,
            enemy_base_shield=150,
            enemy_base_hp=5000,
        )
        self._open_gate(scenario)
        scenario.dart_target_type = "fixed"
        self.assertTrue(scenario.fire_dart())
        scenario.update(1.1, SentryState())
        self.assertEqual(scenario.enemy_base_shield, 0.0)
        self.assertEqual(scenario.enemy_base_hp, 4950.0)

    def test_gate_has_two_windows(self) -> None:
        scenario = TaskScenario()
        self._open_gate(scenario)
        scenario.dart_gate_state = "closed"
        self._open_gate(scenario)
        self.assertFalse(scenario.open_dart_gate())
        self.assertEqual(scenario.dart_gate_windows, 0)


class RadarTests(unittest.TestCase):
    def test_mark_thresholds_and_double_vulnerability(self) -> None:
        scenario = TaskScenario()
        scenario.radar_mark(1, 100)
        self.assertAlmostEqual(scenario.radar_vulnerability(1), 0.15)
        scenario.radar_mark(1, 20)
        self.assertAlmostEqual(scenario.radar_vulnerability(1), 0.20)
        scenario.radar_double_charges = 1
        self.assertTrue(scenario.trigger_radar_double())
        self.assertAlmostEqual(scenario.radar_vulnerability(1), 0.40)
        self.assertEqual(scenario.radar_vulnerability(6), 0.0)

    def test_radar_double_expires(self) -> None:
        scenario = TaskScenario()
        scenario.radar_double_remaining = 0.1
        scenario.update(0.2, SentryState())
        self.assertEqual(scenario.radar_double_remaining, 0.0)

    def test_radar_scan_uses_configured_accuracy_and_updates_estimate(self) -> None:
        scenario = TaskScenario()
        scenario.radar_accuracy_probability = {
            "accurate": 1.0,
            "half_accurate": 0.0,
            "error": 0.0,
        }
        scenario.radar_data_loss_probability = 0.0

        self.assertEqual(scenario.radar_scan(2), "accurate")
        self.assertEqual(scenario.radar_last_report_quality[2], "accurate")
        self.assertEqual(scenario.radar_marks[2], 1.0)
        self.assertEqual(
            scenario.radar_estimated_positions[2],
            list(scenario.robot_position(2, team="blue")),
        )

    def test_radar_information_wave_builds_team_packet(self) -> None:
        scenario = TaskScenario()
        scenario.radar_info_wave_probability = 1.0

        self.assertTrue(scenario.parse_radar_information_wave())
        packet = scenario.radar_team_packet
        self.assertTrue(packet["valid"])
        self.assertIn(2, packet["targets"])
        self.assertIn("health", packet["targets"][2])
        self.assertIn("ammo", packet["targets"][2])
        self.assertIn("team_economy", packet)

    def test_radar_air_countermeasure_locks_for_forty_five_seconds(self) -> None:
        scenario = TaskScenario()
        scenario.radar_air_lock_probability = {1: 1.0, 2: 1.0, 3: 1.0}
        scenario.set_radar_air_support(True)

        self.assertTrue(scenario.attempt_radar_air_countermeasure())
        self.assertEqual(scenario.radar_air_lock_count, 1)
        self.assertEqual(scenario.radar_air_lock_remaining, 45.0)
        self.assertFalse(scenario.robot_can_fire(5, team="blue")[0])
        self.assertEqual(
            scenario.robot_can_fire(5, team="blue")[1],
            "radar_countermeasure_locked",
        )
        scenario.update(45.1, SentryState())
        self.assertEqual(scenario.radar_air_lock_remaining, 0.0)

    def test_interference_level_can_suppress_radar_vulnerability(self) -> None:
        scenario = TaskScenario()
        scenario.radar_mark(1, 120)
        self.assertAlmostEqual(scenario.radar_vulnerability(1), 0.20)

        scenario.enemy_radar_interference_level = 2
        self.assertEqual(scenario.radar_vulnerability(1), 0.0)

        scenario.radar_interference_parse_probability = 1.0
        self.assertTrue(scenario.parse_radar_interference_key())
        self.assertEqual(scenario.radar_interference_level, 2)
        self.assertAlmostEqual(scenario.radar_vulnerability(1), 0.20)


if __name__ == "__main__":
    unittest.main()
