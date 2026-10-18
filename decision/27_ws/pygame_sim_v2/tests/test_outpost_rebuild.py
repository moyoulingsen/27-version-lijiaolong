from __future__ import annotations

import json
import unittest

from rm2026_sim.core import SentryState
from rm2026_sim.scenario_store import capture_snapshot, restore_snapshot
from rm2026_sim.task_state import OUTPOST_REBUILD_HP, TaskScenario


RED_OUTPOST_ZONE = [[0.0, 5.0], [5.0, 5.0], [5.0, 10.0], [0.0, 10.0]]
BLUE_OUTPOST_ZONE = [[23.0, 5.0], [28.0, 5.0], [28.0, 10.0], [23.0, 10.0]]


class OutpostRebuildTests(unittest.TestCase):
    def configured_scenario(self, **kwargs) -> TaskScenario:
        return TaskScenario(
            field_zone_overrides={
                "region_09_outpost_red": RED_OUTPOST_ZONE,
                "region_09_outpost_blue": BLUE_OUTPOST_ZONE,
            },
            **kwargs,
        )

    def test_each_thousand_base_hp_damage_awards_a_stored_chance(self) -> None:
        scenario = self.configured_scenario(
            own_outpost_hp=0,
            own_outpost_destroyed_ever=True,
            own_base_shield=0,
        )

        scenario.apply_attack_damage(
            7, "42mm", shots=5, team="red", defence_buff=0.0
        )
        self.assertEqual(scenario.base_hp_damage_taken["red"], 1000.0)
        self.assertEqual(scenario.outpost_rebuild_chances["red"], 1)

        scenario.apply_attack_damage(
            7, "42mm", shots=10, team="red", defence_buff=0.0
        )
        self.assertEqual(scenario.outpost_rebuild_chances["red"], 3)

    def test_engineer_rebuilds_in_five_seconds_and_consumes_one_chance(self) -> None:
        scenario = self.configured_scenario(
            own_outpost_hp=0,
            own_outpost_destroyed_ever=True,
            outpost_rebuild_chances={"red": 1, "blue": 0},
        )
        sentry = SentryState(x=10.0, y=12.0)
        scenario.set_robot_position(2, (2.0, 7.0), team="red")

        scenario.update(4.9, sentry)
        self.assertEqual(scenario.own_outpost_hp, 0)
        self.assertAlmostEqual(scenario.outpost_rebuild_progress["red"][2], 4.9)
        scenario.update(0.1, sentry)

        self.assertEqual(scenario.own_outpost_hp, OUTPOST_REBUILD_HP)
        self.assertEqual(scenario.outpost_rebuild_chances["red"], 0)
        self.assertTrue(scenario.own_outpost_destroyed_ever)

    def test_non_engineer_requires_ten_continuous_seconds(self) -> None:
        scenario = self.configured_scenario(
            own_outpost_hp=0,
            own_outpost_destroyed_ever=True,
            outpost_rebuild_chances={"red": 1, "blue": 0},
        )
        sentry = SentryState(x=10.0, y=12.0)
        scenario.set_robot_position(1, (2.0, 7.0), team="red")
        scenario.set_robot_position(2, (10.0, 12.0), team="red")
        scenario.set_robot_position(3, (10.0, 12.0), team="red")
        scenario.set_robot_position(4, (10.0, 12.0), team="red")

        scenario.update(6.0, sentry)
        scenario.set_robot_position(1, (10.0, 12.0), team="red")
        scenario.update(1.0, sentry)
        self.assertEqual(scenario.outpost_rebuild_progress["red"][1], 0.0)

        scenario.set_robot_position(1, (2.0, 7.0), team="red")
        scenario.update(9.9, sentry)
        self.assertEqual(scenario.own_outpost_hp, 0)
        scenario.update(0.1, sentry)
        self.assertEqual(scenario.own_outpost_hp, OUTPOST_REBUILD_HP)

    def test_rebuild_is_disabled_after_five_minutes(self) -> None:
        scenario = self.configured_scenario(
            own_outpost_hp=0,
            own_outpost_destroyed_ever=True,
            remaining_time=119.9,
            outpost_rebuild_chances={"red": 1, "blue": 0},
        )
        sentry = SentryState(x=10.0, y=12.0)
        scenario.set_robot_position(2, (2.0, 7.0), team="red")

        scenario.update(10.0, sentry)

        self.assertEqual(scenario.own_outpost_hp, 0)
        self.assertEqual(scenario.outpost_rebuild_progress["red"][2], 0.0)
        self.assertEqual(scenario.outpost_rebuild_chances["red"], 1)

    def test_rebuilt_outpost_disables_enemy_gain_after_exit_delay(self) -> None:
        scenario = self.configured_scenario(
            enemy_outpost_hp=0,
            enemy_outpost_destroyed_ever=True,
            remaining_time=200.0,
        )
        sentry = SentryState(x=25.0, y=7.5)
        scenario.update(0.1, sentry)
        self.assertIn(8, scenario.outpost_gain_occupants["red"])

        scenario.enemy_outpost_hp = OUTPOST_REBUILD_HP
        scenario.update(1.9, sentry)
        self.assertIn(8, scenario.outpost_gain_occupants["red"])
        scenario.update(0.2, sentry)
        self.assertNotIn(8, scenario.outpost_gain_occupants["red"])

    def test_snapshot_preserves_rebuild_and_exit_grace_state(self) -> None:
        scenario = self.configured_scenario()
        sentry = SentryState()
        scenario.base_hp_damage_taken = {"red": 1750.0, "blue": 800.0}
        scenario.outpost_rebuild_chances = {"red": 1, "blue": 0}
        scenario.outpost_rebuild_progress["red"][2] = 3.5
        scenario.gain_exit_grace = {
            "region_09_outpost_red": {"red": {2: 1.25}, "blue": {}}
        }

        payload = json.loads(
            json.dumps(capture_snapshot("rebuild", scenario, sentry, None))
        )
        restored, _, _ = restore_snapshot(payload)

        self.assertEqual(restored.base_hp_damage_taken["red"], 1750.0)
        self.assertEqual(restored.outpost_rebuild_chances["red"], 1)
        self.assertEqual(restored.outpost_rebuild_progress["red"][2], 3.5)
        self.assertEqual(
            restored.gain_exit_grace["region_09_outpost_red"]["red"][2],
            1.25,
        )


if __name__ == "__main__":
    unittest.main()
