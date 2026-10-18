from __future__ import annotations

import json
import unittest

from rm2026_sim.core import SentryState
from rm2026_sim.scenario_store import capture_snapshot, restore_snapshot
from rm2026_sim.task_state import (
    BASE_GAIN_DEFENCE,
    RULEBOOK_REVIVE_INVINCIBLE,
    RULEBOOK_REVIVE_WEAK_INVINCIBLE_MIN,
    TaskScenario,
)


RED_BASE_ZONE = [[0.0, 5.0], [5.0, 5.0], [5.0, 10.0], [0.0, 10.0]]
BLUE_BASE_ZONE = [[23.0, 5.0], [28.0, 5.0], [28.0, 10.0], [23.0, 10.0]]


class BaseGainAndRespawnTests(unittest.TestCase):
    def configured_scenario(self, **kwargs) -> TaskScenario:
        overrides = {
            "region_06_base_red": RED_BASE_ZONE,
            "region_06_base_blue": BLUE_BASE_ZONE,
        }
        return TaskScenario(field_zone_overrides=overrides, **kwargs)

    def test_unmarked_base_slots_have_no_effect(self) -> None:
        scenario = TaskScenario(defence_buff=0)
        sentry = SentryState(x=1.0, y=7.5)
        scenario.update(0.1, sentry)

        self.assertEqual(scenario.base_gain_occupants, {"red": [], "blue": []})
        self.assertFalse(scenario.exchange_17mm(remote=False, sentry=sentry))

    def test_multiple_ground_robots_can_occupy_same_base_gain_point(self) -> None:
        scenario = self.configured_scenario(defence_buff=0)
        sentry = SentryState(x=3.0, y=7.5)
        scenario.set_robot_position(1, (2.0, 7.0), team="red")
        scenario.set_robot_position(3, (4.0, 8.0), team="red")
        scenario.set_robot_position(4, (8.0, 8.0), team="red")

        scenario.update(0.1, sentry)

        self.assertEqual(scenario.base_gain_occupants["red"], [1, 2, 3, 8])
        self.assertEqual(scenario.robot_effective_defence(1, team="red"), BASE_GAIN_DEFENCE)
        self.assertEqual(scenario.robot_effective_defence(3, team="red"), BASE_GAIN_DEFENCE)
        self.assertEqual(scenario.robot_effective_defence(4, team="red"), 0.0)
        self.assertEqual(scenario.effective_sentry_defence, BASE_GAIN_DEFENCE)

        scenario.set_robot_position(3, (8.0, 8.0), team="red")
        scenario.update(0.1, sentry)
        self.assertNotIn(3, scenario.base_gain_occupants["red"])
        self.assertEqual(scenario.robot_effective_defence(3, team="red"), 0.0)

    def test_base_gain_halves_projectile_damage(self) -> None:
        scenario = self.configured_scenario(defence_buff=0)
        sentry = SentryState(x=3.0, y=7.5)
        scenario.update(0.1, sentry)
        before = scenario.sentry_hp

        damage = scenario.apply_attack_damage(8, "17mm", team="red")

        self.assertEqual(damage, 10)
        self.assertEqual(scenario.sentry_hp, before - 10)

    def test_rulebook_revive_is_invincible_then_base_clears_weakness(self) -> None:
        scenario = self.configured_scenario(
            revive_mode="rulebook",
            remaining_time=420.0,
            defence_buff=0,
        )
        sentry = SentryState(x=10.0, y=12.0)
        scenario.kill_sentry()

        scenario.update(10.1, sentry)

        self.assertEqual(scenario.sentry_hp, 40.0)
        self.assertTrue(scenario.weak_state)
        self.assertGreaterEqual(
            scenario.invincible_remaining,
            RULEBOOK_REVIVE_INVINCIBLE - 0.2,
        )
        self.assertEqual(scenario.apply_attack_damage(8, "42mm", team="red"), 0)

        sentry.x, sentry.y = 3.0, 7.5
        scenario.update(0.1, sentry)

        self.assertFalse(scenario.weak_state)
        self.assertFalse(scenario.respawn_fire_locked)
        self.assertLessEqual(
            scenario.invincible_remaining,
            RULEBOOK_REVIVE_WEAK_INVINCIBLE_MIN,
        )
        self.assertIn(8, scenario.base_gain_occupants["red"])

    def test_other_ground_robot_uses_same_weak_and_invincible_flow(self) -> None:
        scenario = self.configured_scenario(
            revive_mode="rulebook",
            remaining_time=420.0,
        )
        sentry = SentryState(x=10.0, y=12.0)
        scenario.set_robot_position(3, (10.0, 10.0), team="blue")
        scenario.apply_attack_damage(3, "42mm", team="blue")
        self.assertEqual(scenario.enemy_health(3), 0.0)

        scenario.update(10.1, sentry)

        self.assertEqual(scenario.enemy_health(3), 20.0)
        self.assertTrue(scenario.robot_is_weak(3, team="blue"))
        before = scenario.enemy_health(3)
        self.assertEqual(scenario.apply_attack_damage(3, "17mm", team="blue"), 0)
        self.assertEqual(scenario.enemy_health(3), before)

        scenario.set_robot_position(3, (25.0, 7.5), team="blue")
        scenario.update(0.1, sentry)

        self.assertFalse(scenario.robot_is_weak(3, team="blue"))
        self.assertEqual(
            scenario.robot_effective_defence(3, team="blue"), BASE_GAIN_DEFENCE
        )

    def test_base_gain_allows_local_ammo_exchange(self) -> None:
        scenario = self.configured_scenario(ammo=300, economy=400)
        sentry = SentryState(x=3.0, y=7.5)
        scenario.update(0.1, sentry)

        self.assertTrue(scenario.exchange_17mm(remote=False, sentry=sentry))
        self.assertEqual(scenario.ammo, 310)
        self.assertEqual(scenario.economy, 390)

    def test_snapshot_round_trip_preserves_robot_rule_states(self) -> None:
        scenario = self.configured_scenario(revive_mode="rulebook")
        sentry = SentryState(x=3.0, y=7.5)
        scenario.robot_weak_state[3] = True
        scenario.robot_invincible_remaining[3] = 12.5
        scenario.base_gain_occupants = {"red": [1, 8], "blue": [3]}

        payload = json.loads(
            json.dumps(
                capture_snapshot("base-rule-state", scenario, sentry, None),
                ensure_ascii=False,
            )
        )
        restored, _, _ = restore_snapshot(payload)

        self.assertTrue(restored.robot_weak_state[3])
        self.assertEqual(restored.robot_invincible_remaining[3], 12.5)
        self.assertEqual(restored.base_gain_occupants["red"], [1, 8])


if __name__ == "__main__":
    unittest.main()
