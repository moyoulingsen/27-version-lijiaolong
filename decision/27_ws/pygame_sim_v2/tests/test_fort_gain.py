from __future__ import annotations

import json
import unittest

from rm2026_sim.core import SentryState
from rm2026_sim.scenario_store import capture_snapshot, restore_snapshot
from rm2026_sim.task_state import (
    FORT_GAIN_DEFENCE,
    FORT_GAIN_RESERVE_CAP,
    FORT_GAIN_COOLING_CAP,
    TaskScenario,
)


RED_FORT_ZONE = [[5.0, 5.0], [10.0, 5.0], [10.0, 10.0], [5.0, 10.0]]
BLUE_FORT_ZONE = [[18.0, 5.0], [23.0, 5.0], [23.0, 10.0], [18.0, 10.0]]


class FortGainTests(unittest.TestCase):
    def configured_scenario(self, **kwargs) -> TaskScenario:
        return TaskScenario(
            field_zone_overrides={
                "region_07_fort_red": RED_FORT_ZONE,
                "region_07_fort_blue": BLUE_FORT_ZONE,
            },
            **kwargs,
        )

    def move_eligible_outside(self, scenario: TaskScenario, *, team: str) -> None:
        for target_id in (1, 3, 4, 8):
            if team == "red" and target_id == 8:
                continue
            scenario.set_robot_position(target_id, (13.0, 13.0), team=team)

    def test_fort_is_inactive_before_own_outpost_first_destroyed(self) -> None:
        scenario = self.configured_scenario()
        sentry = SentryState(x=7.0, y=7.0)
        scenario.set_robot_position(1, (6.0, 7.0), team="red")

        scenario.update(0.0, sentry)

        self.assertEqual(scenario.fort_own_occupants["red"], [])
        self.assertEqual(scenario.fort_reserve_ammo["red"], 0)

    def test_only_first_friendly_robot_gets_gain_but_enemies_can_share(self) -> None:
        scenario = self.configured_scenario(
            own_outpost_hp=0,
            own_outpost_destroyed_ever=True,
            remaining_time=240.0,
        )
        sentry = SentryState(x=7.0, y=7.0)
        scenario.set_robot_position(1, (6.0, 7.0), team="red")
        scenario.set_robot_position(3, (8.0, 7.0), team="red")
        scenario.set_robot_position(1, (6.5, 7.5), team="blue")
        scenario.set_robot_position(3, (8.5, 7.5), team="blue")

        scenario.update(0.0, sentry)

        self.assertEqual(scenario.fort_own_occupants["red"], [1])
        self.assertEqual(scenario.fort_enemy_occupants["blue"], [1, 3])
        self.assertFalse(scenario.robot_in_own_fort_gain("red", 3))
        self.assertTrue(scenario.robot_in_enemy_fort_gain("blue", 1))

        scenario.set_robot_position(1, (13.0, 13.0), team="red")
        scenario.update(1.9, sentry)
        self.assertEqual(scenario.fort_own_occupants["red"], [1])
        scenario.update(0.2, sentry)
        self.assertEqual(scenario.fort_own_occupants["red"], [3])

    def test_enemy_occupation_requires_three_minutes_and_destroyed_outpost(self) -> None:
        sentry = SentryState()
        too_early = self.configured_scenario(
            enemy_outpost_hp=0.0,
            remaining_time=240.1,
        )
        too_early.set_robot_position(3, (20.0, 7.0), team="red")
        too_early.update(0.0, sentry)
        self.assertEqual(too_early.fort_enemy_occupants["red"], [])

        available = self.configured_scenario(
            enemy_outpost_hp=0.0,
            remaining_time=240.0,
        )
        available.set_robot_position(3, (20.0, 7.0), team="red")
        available.update(0.0, sentry)
        self.assertEqual(available.fort_enemy_occupants["red"], [3])

    def test_delta_controls_cooling_and_reserve_caps(self) -> None:
        scenario = self.configured_scenario(
            own_base_hp=3500,
            own_base_min_hp=3500,
        )
        self.assertEqual(scenario.fortress_damage_delta("red"), 1500)
        self.assertEqual(scenario.fortress_cooling_bonus("red"), 37)
        self.assertEqual(scenario.fortress_reserve_limit("red"), 300)

        capped = self.configured_scenario(own_base_hp=0, own_base_min_hp=0)
        self.assertEqual(capped.fortress_cooling_bonus("red"), FORT_GAIN_COOLING_CAP)
        self.assertEqual(capped.fortress_reserve_limit("red"), FORT_GAIN_RESERVE_CAP)

    def test_friendly_occupant_gets_defence_and_best_cooling_effect(self) -> None:
        scenario = self.configured_scenario(
            own_outpost_hp=0,
            own_base_hp=3500,
            own_base_min_hp=3500,
            defence_buff=0,
        )
        sentry = SentryState(x=13.0, y=13.0)
        self.move_eligible_outside(scenario, team="red")
        scenario.set_robot_position(3, (7.0, 7.0), team="red")
        scenario.update(0.0, sentry)

        self.assertEqual(
            scenario.robot_effective_defence(3, team="red"), FORT_GAIN_DEFENCE
        )
        base = 12.0
        self.assertEqual(scenario.robot_heat_cooling_rate(3, team="red"), base + 37)
        scenario.add_buff("test-rune", "heat_cooling", 5.0, 30.0)
        self.assertEqual(scenario.robot_heat_cooling_rate(3, team="red"), base * 5.0)

    def test_reserve_ammo_is_consumed_before_robot_ammo(self) -> None:
        scenario = self.configured_scenario(
            own_outpost_hp=0,
            own_base_hp=3500,
            own_base_min_hp=3500,
        )
        sentry = SentryState(x=13.0, y=13.0)
        self.move_eligible_outside(scenario, team="red")
        scenario.set_robot_position(3, (7.0, 7.0), team="red")
        scenario.own_robot_ammo[3] = 2
        scenario.update(0.0, sentry)
        self.assertEqual(scenario.fort_reserve_ammo["red"], 300)

        self.assertEqual(scenario.record_robot_fire(3, 5, team="red"), 5)

        self.assertEqual(scenario.fort_reserve_ammo["red"], 295)
        self.assertEqual(scenario.own_robot_ammo[3], 2)

        scenario.fort_reserve_ammo["red"] = 1
        scenario.own_robot_heat[3] = 0.0
        scenario.own_robot_heat_locked[3] = False
        self.assertEqual(scenario.record_robot_fire(3, 3, team="red"), 3)
        self.assertEqual(scenario.fort_reserve_ammo["red"], 0)
        self.assertEqual(scenario.own_robot_ammo[3], 0)

    def test_hero_shot_consumes_ten_reserve_ammo(self) -> None:
        scenario = self.configured_scenario(own_outpost_hp=0)
        sentry = SentryState(x=13.0, y=13.0)
        self.move_eligible_outside(scenario, team="red")
        scenario.set_robot_position(1, (7.0, 7.0), team="red")
        scenario.update(0.0, sentry)
        before = scenario.fort_reserve_ammo["red"]

        self.assertEqual(scenario.record_robot_fire(1, 2, team="red"), 2)
        self.assertEqual(scenario.fort_reserve_ammo["red"], before - 20)

    def test_enemy_occupant_has_vulnerability_until_armor_deploys(self) -> None:
        scenario = self.configured_scenario(
            enemy_outpost_hp=0.0,
            remaining_time=240.0,
        )
        sentry = SentryState()
        scenario.set_robot_position(3, (20.0, 7.0), team="red")
        scenario.update(0.0, sentry)

        self.assertEqual(scenario.robot_effective_defence(3, team="red"), -1.0)
        before = scenario.own_robot_health(3)
        self.assertEqual(scenario.apply_attack_damage(3, "17mm", team="red"), 40)
        self.assertEqual(scenario.own_robot_health(3), before - 40)

        scenario.update(20.0, sentry)
        self.assertTrue(scenario.enemy_base_armor_deployed)
        self.assertEqual(scenario.robot_effective_defence(3, team="red"), 0.0)

    def test_enemy_fort_vulnerability_uses_highest_negative_effect(self) -> None:
        scenario = self.configured_scenario(
            enemy_outpost_hp=0.0,
            remaining_time=240.0,
            assembly_defence=0.50,
            defence_buff=0,
        )
        sentry = SentryState(x=20.0, y=7.0)
        self.move_eligible_outside(scenario, team="red")

        scenario.update(0.0, sentry)

        self.assertIn(8, scenario.fort_enemy_occupants["red"])
        self.assertEqual(scenario.effective_sentry_defence, -0.50)

    def test_enemy_capture_timer_pauses_for_three_second_grace(self) -> None:
        scenario = self.configured_scenario(
            enemy_outpost_hp=0.0,
            remaining_time=240.0,
        )
        sentry = SentryState()
        scenario.set_robot_position(3, (20.0, 7.0), team="red")
        scenario.update(10.0, sentry)
        self.assertEqual(scenario.fort_enemy_capture_elapsed["red"][3], 10.0)

        scenario.set_robot_position(3, (13.0, 13.0), team="red")
        scenario.update(2.0, sentry)
        self.assertEqual(scenario.fort_enemy_capture_elapsed["red"][3], 12.0)
        scenario.set_robot_position(3, (20.0, 7.0), team="red")
        scenario.update(10.0, sentry)
        self.assertTrue(scenario.enemy_base_armor_deployed)

    def test_enemy_capture_timer_resets_after_grace_expires(self) -> None:
        scenario = self.configured_scenario(
            enemy_outpost_hp=0.0,
            remaining_time=240.0,
        )
        sentry = SentryState()
        scenario.set_robot_position(3, (20.0, 7.0), team="red")
        scenario.update(10.0, sentry)
        scenario.set_robot_position(3, (13.0, 13.0), team="red")
        scenario.update(3.1, sentry)
        self.assertEqual(scenario.fort_enemy_capture_elapsed["red"][3], 12.0)
        scenario.update(2.0, sentry)
        self.assertNotIn(3, scenario.fort_enemy_capture_elapsed["red"])

        scenario.set_robot_position(3, (20.0, 7.0), team="red")
        scenario.update(10.0, sentry)
        self.assertFalse(scenario.enemy_base_armor_deployed)
        self.assertEqual(scenario.fort_enemy_capture_elapsed["red"][3], 10.0)

    def test_snapshot_preserves_fort_state(self) -> None:
        scenario = self.configured_scenario()
        sentry = SentryState()
        scenario.fort_own_occupants = {"red": [3], "blue": []}
        scenario.fort_enemy_occupants = {"red": [], "blue": [1, 4]}
        scenario.fort_reserve_ammo = {"red": 222, "blue": 0}
        scenario.fort_reserve_capacity = {"red": 300, "blue": 0}
        scenario.fort_enemy_capture_elapsed = {"red": {}, "blue": {1: 12.5}}
        scenario.fort_enemy_capture_grace = {"red": {}, "blue": {1: 2.0}}

        payload = json.loads(json.dumps(capture_snapshot("fort", scenario, sentry, None)))
        restored, _, _ = restore_snapshot(payload)

        self.assertEqual(restored.fort_own_occupants["red"], [3])
        self.assertEqual(restored.fort_enemy_occupants["blue"], [1, 4])
        self.assertEqual(restored.fort_reserve_ammo["red"], 222)
        self.assertEqual(restored.fort_enemy_capture_elapsed["blue"][1], 12.5)


if __name__ == "__main__":
    unittest.main()
