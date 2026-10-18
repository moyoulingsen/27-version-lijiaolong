"""Engineering assembly, dart, and radar regression tests."""

from __future__ import annotations

import unittest

from rm2026_sim.core import SentryState
from rm2026_sim.field_geometry import RED_ASSEMBLY
from rm2026_sim.task_state import TaskScenario


class EngineeringAssemblyTests(unittest.TestCase):
    def _place_engineer_in_zone(self, scenario: TaskScenario) -> None:
        scenario.own_robot_positions[2] = [
            (RED_ASSEMBLY[0] + RED_ASSEMBLY[1]) / 2.0,
            (RED_ASSEMBLY[2] + RED_ASSEMBLY[3]) / 2.0,
        ]

    def test_difficulty_one_completes_and_grants_income(self) -> None:
        scenario = TaskScenario(economy=400)
        self._place_engineer_in_zone(scenario)
        self.assertTrue(scenario.select_assembly_difficulty(1))
        self.assertTrue(scenario.start_assembly())
        scenario.update(scenario.assembly_required + 0.1, SentryState())
        self.assertIn(1, scenario.assembly_completed)
        self.assertEqual(scenario.assembly_bonus_per_10s, 50)
        before = scenario.economy
        scenario.update(10.0, SentryState())
        self.assertGreater(scenario.economy, before)

    def test_difficulty_two_needs_previous_and_time_window(self) -> None:
        scenario = TaskScenario(remaining_time=420.0)
        self.assertFalse(scenario.select_assembly_difficulty(2))
        scenario.remaining_time = 360.0
        self.assertFalse(scenario.select_assembly_difficulty(2))
        scenario.assembly_completed.add(1)
        self.assertTrue(scenario.select_assembly_difficulty(2))
        self.assertEqual(scenario.assembly_difficulty, 2)

    def test_difficulty_four_raises_base_hp_and_defence(self) -> None:
        scenario = TaskScenario(
            remaining_time=240.0,
            own_base_hp=5000,
            own_base_shield=150,
        )
        self._place_engineer_in_zone(scenario)
        scenario.assembly_completed.update((1, 2, 3))
        self.assertTrue(scenario.select_assembly_difficulty(4))
        self.assertTrue(scenario.start_assembly())
        scenario.update(scenario.assembly_required + 0.1, SentryState())
        self.assertEqual(scenario.own_base_max_hp, 7000)
        self.assertEqual(scenario.own_base_hp, 7000)
        self.assertAlmostEqual(scenario.assembly_defence, 0.50)

    def test_engineer_leaving_zone_cancels_assembly(self) -> None:
        scenario = TaskScenario()
        self._place_engineer_in_zone(scenario)
        scenario.select_assembly_difficulty(1)
        scenario.start_assembly()
        scenario.own_robot_positions[2] = [10.0, 10.0]
        scenario.update(0.1, SentryState())
        self.assertFalse(scenario.assembly_active)


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


if __name__ == "__main__":
    unittest.main()
