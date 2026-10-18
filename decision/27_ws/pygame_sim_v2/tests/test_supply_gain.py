from __future__ import annotations

import json
import unittest

from rm2026_sim.core import SentryState
from rm2026_sim.scenario_store import capture_snapshot, restore_snapshot
from rm2026_sim.task_state import (
    OUT_OF_COMBAT_SECONDS,
    RULEBOOK_REVIVE_INVINCIBLE,
    SUPPLY_GAIN_HEAL,
    SUPPLY_GAIN_HEAL_LATE,
    TaskScenario,
)


RED_SUPPLY_ZONE = [[5.0, 5.0], [10.0, 5.0], [10.0, 10.0], [5.0, 10.0]]
BLUE_SUPPLY_ZONE = [[18.0, 5.0], [23.0, 5.0], [23.0, 10.0], [18.0, 10.0]]


class SupplyGainTests(unittest.TestCase):
    def configured_scenario(self, **kwargs) -> TaskScenario:
        return TaskScenario(
            field_zone_overrides={
                "region_01_supply_red": RED_SUPPLY_ZONE,
                "region_01_supply_blue": BLUE_SUPPLY_ZONE,
            },
            **kwargs,
        )

    def test_multiple_ground_robots_occupy_only_own_supply(self) -> None:
        scenario = self.configured_scenario()
        sentry = SentryState(x=7.0, y=7.0)
        for target_id, position in {
            1: (6.0, 7.0),
            2: (7.0, 7.0),
            3: (8.0, 7.0),
            4: (12.0, 7.0),
            5: (9.0, 7.0),
        }.items():
            scenario.set_robot_position(target_id, position, team="red")

        scenario.update(0.0, sentry)

        self.assertEqual(scenario.supply_gain_occupants["red"], [1, 2, 3, 8])
        self.assertNotIn(5, scenario.supply_gain_occupants["red"])

    def test_supply_heals_ten_percent_even_while_in_combat(self) -> None:
        scenario = self.configured_scenario(remaining_time=420.0)
        sentry = SentryState(x=7.0, y=7.0)
        scenario.sentry_hp = 100.0
        scenario.sentry_out_of_combat_seconds = 0.0
        scenario.own_robot_hp[3] = 100.0
        scenario.own_robot_out_of_combat_seconds[3] = 0.0
        scenario.set_robot_position(3, (8.0, 7.0), team="red")

        scenario.update(1.0, sentry)

        self.assertEqual(scenario.sentry_hp, 100.0 + 400.0 * SUPPLY_GAIN_HEAL)
        self.assertEqual(scenario.own_robot_hp[3], 100.0 + 200.0 * SUPPLY_GAIN_HEAL)

    def test_late_supply_heals_twenty_five_percent_only_out_of_combat(self) -> None:
        scenario = self.configured_scenario(remaining_time=180.0)
        sentry = SentryState(x=7.0, y=7.0)
        scenario.sentry_hp = 100.0
        scenario.sentry_out_of_combat_seconds = OUT_OF_COMBAT_SECONDS
        scenario.own_robot_hp[3] = 100.0
        scenario.own_robot_out_of_combat_seconds[3] = 0.0
        scenario.set_robot_position(3, (8.0, 7.0), team="red")

        scenario.update(1.0, sentry)

        self.assertEqual(
            scenario.sentry_hp, 100.0 + 400.0 * SUPPLY_GAIN_HEAL_LATE
        )
        self.assertEqual(scenario.own_robot_hp[3], 100.0 + 200.0 * SUPPLY_GAIN_HEAL)

    def test_firing_and_damage_reset_out_of_combat(self) -> None:
        scenario = self.configured_scenario()
        sentry = SentryState()
        scenario.robot_ammo[3] = 10
        scenario.robot_out_of_combat_seconds[3] = OUT_OF_COMBAT_SECONDS

        self.assertEqual(scenario.record_robot_fire(3, team="blue"), 1)
        self.assertEqual(scenario.robot_out_of_combat_seconds[3], 0.0)
        scenario.robot_out_of_combat_seconds[3] = OUT_OF_COMBAT_SECONDS
        scenario.apply_attack_damage(3, "17mm", team="blue")
        self.assertEqual(scenario.robot_out_of_combat_seconds[3], 0.0)

    def test_supply_engineer_is_invincible_only_while_occupying(self) -> None:
        scenario = self.configured_scenario()
        sentry = SentryState()
        scenario.set_robot_position(2, (7.0, 7.0), team="red")
        scenario.update(0.0, sentry)

        self.assertEqual(scenario.apply_attack_damage(2, "42mm", team="red"), 0)
        scenario.set_robot_position(2, (12.0, 12.0), team="red")
        scenario.update(0.0, sentry)
        self.assertEqual(scenario.apply_attack_damage(2, "42mm", team="red"), 200)

    def test_supply_accelerates_other_robot_revive_read_bar(self) -> None:
        scenario = self.configured_scenario(revive_mode="rulebook")
        sentry = SentryState()
        scenario.set_robot_position(3, (7.0, 7.0), team="red")
        scenario.apply_attack_damage(3, "42mm", team="red")
        self.assertEqual(scenario.own_robot_health(3), 0.0)

        scenario.update(2.5, sentry)

        self.assertGreater(scenario.own_robot_health(3), 0.0)
        self.assertFalse(scenario.own_robot_weak_state[3])
        self.assertLessEqual(scenario.own_robot_invincible_remaining[3], 10.0)

    def test_low_base_health_accelerates_revive_outside_supply(self) -> None:
        scenario = self.configured_scenario(
            revive_mode="rulebook",
            own_base_hp=1900,
        )
        sentry = SentryState()
        scenario.set_robot_position(3, (12.0, 12.0), team="red")
        scenario.apply_attack_damage(3, "42mm", team="red")

        scenario.update(2.5, sentry)

        self.assertGreater(scenario.own_robot_health(3), 0.0)
        self.assertTrue(scenario.own_robot_weak_state[3])
        self.assertEqual(
            scenario.own_robot_invincible_remaining[3], RULEBOOK_REVIVE_INVINCIBLE
        )

    def test_gain_card_enforces_ten_total_seconds_of_readbar_invincibility(self) -> None:
        scenario = self.configured_scenario(revive_mode="rulebook")
        sentry = SentryState(x=12.0, y=12.0)
        scenario.kill_sentry()
        scenario.update(10.0, sentry)
        scenario.update(5.0, sentry)
        self.assertAlmostEqual(scenario.invincible_remaining, 25.0)

        sentry.x, sentry.y = 7.0, 7.0
        scenario.update(0.0, sentry)

        self.assertFalse(scenario.weak_state)
        self.assertAlmostEqual(scenario.invincible_remaining, 5.0)

    def test_instant_revive_keeps_three_second_invincibility_at_supply(self) -> None:
        scenario = self.configured_scenario(economy=1000)
        sentry = SentryState(x=7.0, y=7.0)
        scenario.kill_sentry()
        self.assertTrue(scenario.exchange_instant_revive())

        scenario.update(0.0, sentry)

        self.assertFalse(scenario.weak_state)
        self.assertEqual(scenario.invincible_remaining, 3.0)

    def test_blue_supply_has_independent_occupancy_and_healing(self) -> None:
        scenario = self.configured_scenario()
        sentry = SentryState()
        scenario.robot_hp[1] = 100.0
        scenario.set_robot_position(1, (20.0, 7.0), team="blue")

        scenario.update(1.0, sentry)

        self.assertIn(1, scenario.supply_gain_occupants["blue"])
        self.assertEqual(scenario.robot_hp[1], 120.0)

    def test_snapshot_preserves_supply_rule_state(self) -> None:
        scenario = self.configured_scenario()
        sentry = SentryState()
        scenario.supply_gain_occupants = {"red": [2, 8], "blue": [1]}
        scenario.robot_out_of_combat_seconds[1] = 2.5
        scenario.own_robot_revive_invincibility_source[3] = "readbar"

        payload = json.loads(
            json.dumps(capture_snapshot("supply", scenario, sentry, None))
        )
        restored, _, _ = restore_snapshot(payload)

        self.assertEqual(restored.supply_gain_occupants["red"], [2, 8])
        self.assertEqual(restored.robot_out_of_combat_seconds[1], 2.5)
        self.assertEqual(
            restored.own_robot_revive_invincibility_source[3], "readbar"
        )


if __name__ == "__main__":
    unittest.main()
