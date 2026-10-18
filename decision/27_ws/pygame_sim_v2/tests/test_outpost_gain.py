from __future__ import annotations

import json
import unittest

from rm2026_sim.core import SentryState
from rm2026_sim.scenario_store import capture_snapshot, restore_snapshot
from rm2026_sim.task_state import OUTPOST_GAIN_DEFENCE, TaskScenario


RED_OUTPOST_ZONE = [[0.0, 5.0], [5.0, 5.0], [5.0, 10.0], [0.0, 10.0]]
BLUE_OUTPOST_ZONE = [[23.0, 5.0], [28.0, 5.0], [28.0, 10.0], [23.0, 10.0]]


class OutpostGainTests(unittest.TestCase):
    def configured_scenario(self, **kwargs) -> TaskScenario:
        return TaskScenario(
            field_zone_overrides={
                "region_09_outpost_red": RED_OUTPOST_ZONE,
                "region_09_outpost_blue": BLUE_OUTPOST_ZONE,
            },
            **kwargs,
        )

    def test_multiple_ground_robots_occupy_living_own_outpost(self) -> None:
        scenario = self.configured_scenario(defence_buff=0, active_posture=1)
        sentry = SentryState(x=3.0, y=7.5)
        scenario.set_robot_position(1, (2.0, 7.0), team="red")
        scenario.set_robot_position(3, (4.0, 8.0), team="red")
        scenario.set_robot_position(4, (8.0, 8.0), team="red")
        scenario.set_robot_position(5, (2.5, 7.5), team="red")

        scenario.update(0.1, sentry)

        self.assertEqual(scenario.outpost_gain_occupants["red"], [1, 2, 3, 8])
        self.assertNotIn(5, scenario.outpost_gain_occupants["red"])
        self.assertEqual(
            scenario.robot_effective_defence(1, team="red"), OUTPOST_GAIN_DEFENCE
        )
        self.assertEqual(scenario.robot_effective_defence(4, team="red"), 0.0)
        self.assertEqual(scenario.effective_sentry_defence, OUTPOST_GAIN_DEFENCE)

    def test_destroyed_own_outpost_disables_occupation(self) -> None:
        scenario = self.configured_scenario(own_outpost_hp=0, defence_buff=0)
        sentry = SentryState(x=3.0, y=7.5)

        scenario.update(0.1, sentry)

        self.assertEqual(scenario.outpost_gain_occupants["red"], [])
        self.assertEqual(scenario.effective_sentry_defence, -0.25)

    def test_outpost_destruction_immediately_removes_existing_gain(self) -> None:
        scenario = self.configured_scenario(defence_buff=0, active_posture=1)
        sentry = SentryState(x=3.0, y=7.5)
        scenario.update(0.1, sentry)
        self.assertIn(8, scenario.outpost_gain_occupants["red"])

        scenario.apply_attack_damage(
            6,
            "42mm",
            shots=8,
            team="red",
            defence_buff=0.0,
        )

        self.assertEqual(scenario.own_outpost_hp, 0)
        self.assertNotIn(8, scenario.outpost_gain_occupants["red"])
        self.assertEqual(scenario.effective_sentry_defence, -0.25)

    def test_enemy_outpost_requires_destroyed_target_and_first_five_minutes(self) -> None:
        sentry = SentryState(x=25.0, y=7.5)
        unavailable = self.configured_scenario(defence_buff=0)
        unavailable.update(0.0, sentry)
        self.assertNotIn(8, unavailable.outpost_gain_occupants["red"])

        available = self.configured_scenario(
            enemy_outpost_hp=0.0,
            remaining_time=120.0,
            defence_buff=0,
            active_posture=1,
        )
        available.update(0.0, sentry)
        self.assertIn(8, available.outpost_gain_occupants["red"])
        self.assertEqual(available.effective_sentry_defence, OUTPOST_GAIN_DEFENCE)

        expired = self.configured_scenario(
            enemy_outpost_hp=0.0,
            remaining_time=119.9,
            defence_buff=0,
        )
        expired.update(0.0, sentry)
        self.assertNotIn(8, expired.outpost_gain_occupants["red"])

    def test_enemy_outpost_capture_is_symmetric_for_blue_team(self) -> None:
        scenario = self.configured_scenario(
            own_outpost_hp=0,
            remaining_time=200.0,
        )
        sentry = SentryState(x=10.0, y=12.0)
        scenario.set_robot_position(1, (2.0, 7.0), team="blue")
        scenario.set_robot_position(4, (4.0, 8.0), team="blue")

        scenario.update(0.0, sentry)

        self.assertIn(1, scenario.outpost_gain_occupants["blue"])
        self.assertIn(4, scenario.outpost_gain_occupants["blue"])
        self.assertEqual(
            scenario.robot_effective_defence(1, team="blue"), OUTPOST_GAIN_DEFENCE
        )

    def test_enemy_point_still_requires_own_outpost_alive(self) -> None:
        scenario = self.configured_scenario(
            own_outpost_hp=0,
            enemy_outpost_hp=0.0,
            remaining_time=200.0,
            defence_buff=0,
        )
        sentry = SentryState(x=25.0, y=7.5)

        scenario.update(0.0, sentry)

        self.assertNotIn(8, scenario.outpost_gain_occupants["red"])

    def test_outpost_gain_reduces_projectile_damage_by_twenty_five_percent(self) -> None:
        scenario = self.configured_scenario(defence_buff=0, active_posture=1)
        sentry = SentryState(x=3.0, y=7.5)
        scenario.update(0.1, sentry)
        before = scenario.sentry_hp

        damage = scenario.apply_attack_damage(8, "42mm", team="red")

        self.assertEqual(damage, 150)
        self.assertEqual(scenario.sentry_hp, before - 150)

    def test_outpost_clears_weakness_and_corresponding_invincibility(self) -> None:
        scenario = self.configured_scenario(defence_buff=0)
        sentry = SentryState(x=3.0, y=7.5)
        scenario.weak_state = True
        scenario.respawn_fire_locked = True
        scenario.invincible_remaining = 20.0
        scenario.robot_weak_state[3] = True
        scenario.robot_invincible_remaining[3] = 15.0
        scenario.set_robot_position(3, (25.0, 7.5), team="blue")

        scenario.update(0.1, sentry)

        self.assertFalse(scenario.weak_state)
        self.assertFalse(scenario.respawn_fire_locked)
        self.assertEqual(scenario.invincible_remaining, 0.0)
        self.assertFalse(scenario.robot_weak_state[3])
        self.assertEqual(scenario.robot_invincible_remaining[3], 0.0)

    def test_outpost_allows_local_ammunition_exchange(self) -> None:
        own = self.configured_scenario(ammo=300, economy=400)
        own_sentry = SentryState(x=3.0, y=7.5)
        self.assertTrue(own.exchange_17mm(remote=False, sentry=own_sentry))

        enemy = self.configured_scenario(
            enemy_outpost_hp=0.0,
            remaining_time=200.0,
            ammo=300,
            economy=400,
        )
        enemy_sentry = SentryState(x=25.0, y=7.5)
        self.assertTrue(enemy.exchange_17mm(remote=False, sentry=enemy_sentry))

    def test_snapshot_preserves_outpost_occupants(self) -> None:
        scenario = self.configured_scenario()
        sentry = SentryState()
        scenario.outpost_gain_occupants = {"red": [1, 8], "blue": [3]}

        payload = json.loads(
            json.dumps(capture_snapshot("outpost", scenario, sentry, None))
        )
        restored, _, _ = restore_snapshot(payload)

        self.assertEqual(restored.outpost_gain_occupants["red"], [1, 8])
        self.assertEqual(restored.outpost_gain_occupants["blue"], [3])


if __name__ == "__main__":
    unittest.main()
