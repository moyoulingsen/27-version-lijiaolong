from __future__ import annotations

import json
import unittest

from rm2026_sim.core import SentryState
from rm2026_sim.scenario_store import capture_snapshot, restore_snapshot
from rm2026_sim.task_state import ASSEMBLY_GAIN_MAX_SECONDS, TaskScenario


RED_ASSEMBLY_ZONE = [[0.0, 5.0], [5.0, 5.0], [5.0, 10.0], [0.0, 10.0]]
BLUE_ASSEMBLY_ZONE = [[23.0, 5.0], [28.0, 5.0], [28.0, 10.0], [23.0, 10.0]]


class AssemblyGainTests(unittest.TestCase):
    def configured_scenario(self, **kwargs) -> TaskScenario:
        return TaskScenario(
            field_zone_overrides={
                "region_12_assembly_red": RED_ASSEMBLY_ZONE,
                "region_12_assembly_blue": BLUE_ASSEMBLY_ZONE,
            },
            **kwargs,
        )

    def test_unmarked_assembly_slots_have_no_effect(self) -> None:
        scenario = TaskScenario()
        sentry = SentryState()
        scenario.set_robot_position(2, (3.0, 7.0), team="red")

        scenario.update(10.0, sentry)

        self.assertEqual(scenario.assembly_gain_occupants["red"], [])
        self.assertEqual(scenario.assembly_gain_elapsed["red"], 0.0)

    def test_only_own_engineer_occupies_assembly_gain(self) -> None:
        scenario = self.configured_scenario()
        sentry = SentryState(x=3.0, y=7.5)
        scenario.set_robot_position(1, (2.0, 7.0), team="red")
        scenario.set_robot_position(2, (3.0, 7.0), team="red")
        scenario.set_robot_position(3, (4.0, 8.0), team="red")
        scenario.set_robot_position(2, (3.0, 7.0), team="blue")

        scenario.update(0.1, sentry)

        self.assertEqual(scenario.assembly_gain_occupants["red"], [2])
        self.assertEqual(scenario.assembly_gain_occupants["blue"], [])
        self.assertFalse(scenario.robot_in_assembly_gain("red", 1))
        self.assertFalse(scenario.robot_in_assembly_gain("red", 3))

    def test_occupying_engineer_is_invincible(self) -> None:
        scenario = self.configured_scenario()
        sentry = SentryState()
        scenario.set_robot_position(2, (3.0, 7.0), team="red")
        scenario.update(0.1, sentry)
        before = scenario.own_robot_health(2)

        damage = scenario.apply_attack_damage(2, "42mm", team="red")

        self.assertEqual(damage, 0)
        self.assertEqual(scenario.own_robot_health(2), before)

    def test_leaving_pauses_elapsed_and_reentering_does_not_reset(self) -> None:
        scenario = self.configured_scenario()
        sentry = SentryState()
        scenario.set_robot_position(2, (3.0, 7.0), team="red")

        scenario.update(60.0, sentry)
        self.assertEqual(scenario.assembly_gain_elapsed["red"], 60.0)
        scenario.set_robot_position(2, (10.0, 10.0), team="red")
        scenario.update(20.0, sentry)
        self.assertEqual(scenario.assembly_gain_elapsed["red"], 60.0)
        self.assertEqual(scenario.apply_attack_damage(2, "42mm", team="red"), 200)
        scenario.set_robot_position(2, (3.0, 7.0), team="red")
        scenario.update(30.0, sentry)

        self.assertEqual(scenario.assembly_gain_elapsed["red"], 90.0)
        self.assertIn(2, scenario.assembly_gain_occupants["red"])

    def test_invincibility_expires_after_180_cumulative_seconds(self) -> None:
        scenario = self.configured_scenario()
        sentry = SentryState()
        scenario.set_robot_position(2, (3.0, 7.0), team="red")

        scenario.update(179.0, sentry)
        self.assertIn(2, scenario.assembly_gain_occupants["red"])
        scenario.update(1.0, sentry)

        self.assertEqual(
            scenario.assembly_gain_elapsed["red"], ASSEMBLY_GAIN_MAX_SECONDS
        )
        self.assertNotIn(2, scenario.assembly_gain_occupants["red"])
        self.assertEqual(scenario.apply_attack_damage(2, "42mm", team="red"), 200)

    def test_blue_engineer_has_independent_assembly_quota(self) -> None:
        scenario = self.configured_scenario()
        sentry = SentryState()
        scenario.set_robot_position(2, (10.0, 10.0), team="red")
        scenario.set_robot_position(2, (25.0, 7.0), team="blue")

        scenario.update(12.5, sentry)

        self.assertEqual(scenario.assembly_gain_elapsed["red"], 0.0)
        self.assertEqual(scenario.assembly_gain_elapsed["blue"], 12.5)
        self.assertIn(2, scenario.assembly_gain_occupants["blue"])
        self.assertEqual(scenario.apply_attack_damage(2, "42mm", team="blue"), 0)

    def test_engineer_cannot_occupy_enemy_assembly_zone(self) -> None:
        scenario = self.configured_scenario()
        sentry = SentryState()
        scenario.set_robot_position(2, (25.0, 7.0), team="red")

        scenario.update(10.0, sentry)

        self.assertEqual(scenario.assembly_gain_occupants["red"], [])
        self.assertEqual(scenario.assembly_gain_elapsed["red"], 0.0)

    def test_snapshot_preserves_cumulative_time(self) -> None:
        scenario = self.configured_scenario()
        sentry = SentryState()
        scenario.assembly_gain_occupants = {"red": [2], "blue": []}
        scenario.assembly_gain_elapsed = {"red": 75.5, "blue": 12.0}

        payload = json.loads(
            json.dumps(capture_snapshot("assembly-gain", scenario, sentry, None))
        )
        restored, _, _ = restore_snapshot(payload)

        self.assertEqual(restored.assembly_gain_occupants["red"], [2])
        self.assertEqual(restored.assembly_gain_elapsed["red"], 75.5)
        self.assertEqual(restored.assembly_gain_elapsed["blue"], 12.0)


if __name__ == "__main__":
    unittest.main()
