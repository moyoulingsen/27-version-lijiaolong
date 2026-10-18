from __future__ import annotations

import json
import unittest

from rm2026_sim.core import SentryState
from rm2026_sim.scenario_store import capture_snapshot, restore_snapshot
from rm2026_sim.task_state import TRAPEZOID_GAIN_DEFENCE, TaskScenario


RED_TRAPEZOID_ZONE = [[0.0, 5.0], [5.0, 5.0], [5.0, 10.0], [0.0, 10.0]]
BLUE_TRAPEZOID_ZONE = [[23.0, 5.0], [28.0, 5.0], [28.0, 10.0], [23.0, 10.0]]


class TrapezoidGainTests(unittest.TestCase):
    def configured_scenario(self, **kwargs) -> TaskScenario:
        return TaskScenario(
            field_zone_overrides={
                "region_05_trapezoid_highland_red": RED_TRAPEZOID_ZONE,
                "region_05_trapezoid_highland_blue": BLUE_TRAPEZOID_ZONE,
            },
            **kwargs,
        )

    def test_unmarked_trapezoid_slots_have_no_effect(self) -> None:
        scenario = TaskScenario(defence_buff=0)
        sentry = SentryState(x=1.0, y=7.5)

        scenario.update(0.1, sentry)

        self.assertEqual(
            scenario.trapezoid_gain_occupants, {"red": [], "blue": []}
        )
        self.assertEqual(scenario.effective_sentry_defence, -0.25)

    def test_multiple_ground_robots_occupy_own_trapezoid_gain(self) -> None:
        scenario = self.configured_scenario(defence_buff=0, active_posture=1)
        sentry = SentryState(x=3.0, y=7.5)
        scenario.set_robot_position(1, (2.0, 7.0), team="red")
        scenario.set_robot_position(3, (4.0, 8.0), team="red")
        scenario.set_robot_position(4, (8.0, 8.0), team="red")
        scenario.set_robot_position(5, (2.5, 7.5), team="red")

        scenario.update(0.1, sentry)

        self.assertEqual(
            scenario.trapezoid_gain_occupants["red"], [1, 2, 3, 8]
        )
        self.assertNotIn(5, scenario.trapezoid_gain_occupants["red"])
        self.assertEqual(
            scenario.robot_effective_defence(1, team="red"),
            TRAPEZOID_GAIN_DEFENCE,
        )
        self.assertEqual(scenario.robot_effective_defence(4, team="red"), 0.0)
        self.assertEqual(scenario.effective_sentry_defence, TRAPEZOID_GAIN_DEFENCE)

    def test_robot_cannot_occupy_enemy_trapezoid_gain(self) -> None:
        scenario = self.configured_scenario(defence_buff=0)
        sentry = SentryState(x=25.0, y=7.5)
        scenario.set_robot_position(1, (25.0, 7.0), team="red")

        scenario.update(0.1, sentry)

        self.assertNotIn(1, scenario.trapezoid_gain_occupants["red"])
        self.assertEqual(scenario.effective_sentry_defence, -0.25)

    def test_trapezoid_gain_halves_projectile_and_collision_damage(self) -> None:
        scenario = self.configured_scenario(defence_buff=0, active_posture=1)
        sentry = SentryState(x=3.0, y=7.5)
        scenario.set_robot_position(3, (25.0, 7.5), team="blue")
        scenario.update(0.1, sentry)

        sentry_hp = scenario.sentry_hp
        infantry_hp = scenario.enemy_health(3)

        self.assertEqual(scenario.apply_attack_damage(8, "17mm", team="red"), 10)
        self.assertEqual(scenario.apply_attack_damage(3, "collision", team="blue"), 1)
        self.assertEqual(scenario.sentry_hp, sentry_hp - 10)
        self.assertEqual(scenario.enemy_health(3), infantry_hp - 1)

    def test_dead_robot_is_removed_and_snapshot_preserves_occupants(self) -> None:
        scenario = self.configured_scenario(defence_buff=0)
        sentry = SentryState(x=10.0, y=12.0)
        scenario.set_robot_position(3, (25.0, 7.5), team="blue")
        scenario.update(0.1, sentry)
        self.assertIn(3, scenario.trapezoid_gain_occupants["blue"])

        scenario.apply_attack_damage(
            3, "42mm", team="blue", defence_buff=0.0
        )
        self.assertNotIn(3, scenario.trapezoid_gain_occupants["blue"])

        scenario.trapezoid_gain_occupants = {"red": [1, 8], "blue": [4]}
        payload = json.loads(
            json.dumps(capture_snapshot("trapezoid", scenario, sentry, None))
        )
        restored, _, _ = restore_snapshot(payload)
        self.assertEqual(restored.trapezoid_gain_occupants["red"], [1, 8])
        self.assertEqual(restored.trapezoid_gain_occupants["blue"], [4])

    def test_dead_sentry_immediately_loses_trapezoid_gain(self) -> None:
        scenario = self.configured_scenario(defence_buff=0)
        sentry = SentryState(x=3.0, y=7.5)
        scenario.update(0.1, sentry)
        self.assertIn(8, scenario.trapezoid_gain_occupants["red"])

        scenario.apply_attack_damage(
            8, "42mm", shots=2, team="red", defence_buff=0.0
        )

        self.assertNotIn(8, scenario.trapezoid_gain_occupants["red"])
        self.assertEqual(scenario.effective_sentry_defence, -0.25)


if __name__ == "__main__":
    unittest.main()
