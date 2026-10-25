"""Economy, remote heal, and rulebook respawn regression tests."""

from __future__ import annotations

import json
import unittest

from rm2026_sim.core import SentryState
from rm2026_sim.scenario_store import capture_snapshot, restore_snapshot
from rm2026_sim.task_state import (
    REMOTE_17MM_AMOUNT,
    REMOTE_17MM_COST,
    RULEBOOK_REVIVE_INVINCIBLE,
    RULEBOOK_REVIVE_WEAK_INVINCIBLE_MIN,
    SUPPLY,
    TaskScenario,
)


class EconomyExchangeTests(unittest.TestCase):
    def test_remote_ammo_exchange_deducts_gold_and_delays_six_seconds(self) -> None:
        scenario = TaskScenario(
            economy=400,
            sentry_out_of_combat_seconds=6.0,
        )
        sentry = SentryState()
        self.assertTrue(scenario.exchange_17mm(remote=True, sentry=sentry))
        self.assertEqual(scenario.economy, 400 - REMOTE_17MM_COST)
        self.assertEqual(scenario.remote_ammo_pending, REMOTE_17MM_AMOUNT)
        self.assertEqual(scenario.ammo, 300)
        scenario.update(5.9, sentry)
        self.assertEqual(scenario.ammo, 300)
        scenario.update(0.2, sentry)
        self.assertEqual(scenario.ammo, 300 + REMOTE_17MM_AMOUNT)
        self.assertEqual(scenario.remote_ammo_pending, 0)

    def test_remote_ammo_exchange_requires_out_of_combat(self) -> None:
        scenario = TaskScenario(
            economy=400,
            sentry_out_of_combat_seconds=0.0,
        )
        self.assertFalse(scenario.exchange_17mm(remote=True))
        self.assertEqual(scenario.economy, 400)
        self.assertIn("还需 6.0 秒", scenario.event_message)

    def test_firing_resets_out_of_combat_and_requires_six_new_seconds(self) -> None:
        scenario = TaskScenario(economy=400, sentry_out_of_combat_seconds=6.0)
        sentry = SentryState()
        self.assertTrue(scenario.sentry_is_out_of_combat)

        self.assertEqual(
            scenario.record_robot_fire(8, team="red", sentry=sentry),
            1,
        )
        self.assertFalse(scenario.sentry_is_out_of_combat)
        self.assertFalse(scenario.can_exchange_17mm(remote=True)[0])
        self.assertFalse(scenario.can_exchange_remote_heal()[0])

        scenario.update(5.9, sentry, fire_request=False)
        self.assertFalse(scenario.sentry_is_out_of_combat)
        scenario.update(0.1, sentry, fire_request=False)
        self.assertTrue(scenario.sentry_is_out_of_combat)
        self.assertTrue(scenario.can_exchange_17mm(remote=True)[0])

    def test_damage_resets_out_of_combat_requirement(self) -> None:
        scenario = TaskScenario(
            economy=400,
            sentry_hp=400.0,
            sentry_out_of_combat_seconds=6.0,
        )
        self.assertTrue(scenario.sentry_is_out_of_combat)

        scenario.apply_attack_damage(8, "17mm", team="red")

        self.assertFalse(scenario.sentry_is_out_of_combat)
        self.assertFalse(scenario.can_exchange_17mm(remote=True)[0])
        self.assertFalse(scenario.can_exchange_remote_heal()[0])

    def test_local_ammo_exchange_requires_supply_zone(self) -> None:
        scenario = TaskScenario(economy=400)
        self.assertFalse(
            scenario.exchange_17mm(remote=False, sentry=SentryState(x=10.0, y=7.0))
        )
        self.assertTrue(
            scenario.exchange_17mm(
                remote=False,
                sentry=SentryState(x=SUPPLY[0], y=SUPPLY[1]),
            )
        )
        self.assertEqual(scenario.economy, 390)
        self.assertEqual(scenario.ammo, 310)
        self.assertIn("剩余 390", scenario.event_message)

    def test_ammo_exchange_cap_and_ammo_cap(self) -> None:
        scenario = TaskScenario(
            economy=1000,
            sentry_out_of_combat_seconds=6.0,
            exchanged_17mm=990,
        )
        self.assertFalse(scenario.exchange_17mm(remote=True))
        self.assertEqual(scenario.economy, 1000)

    def test_remote_heal_waits_six_seconds_and_restores_sixty_percent(self) -> None:
        scenario = TaskScenario(
            economy=400,
            sentry_hp=100.0,
            sentry_out_of_combat_seconds=6.0,
        )
        sentry = SentryState()
        self.assertTrue(scenario.exchange_remote_heal())
        self.assertEqual(scenario.economy, 350)
        scenario.update(5.9, sentry)
        self.assertEqual(scenario.sentry_hp, 100.0)
        scenario.update(0.2, sentry)
        self.assertEqual(scenario.sentry_hp, 340.0)

    def test_death_cancels_pending_remote_heal(self) -> None:
        scenario = TaskScenario(
            economy=400,
            sentry_hp=100.0,
            sentry_out_of_combat_seconds=6.0,
        )
        sentry = SentryState()
        self.assertTrue(scenario.exchange_remote_heal())
        scenario.kill_sentry()
        scenario.update(6.1, sentry)
        self.assertEqual(scenario.sentry_hp, 0.0)
        self.assertIsNone(scenario.remote_heal_remaining)

    def test_instant_revive_grants_invincibility_and_power_boost(self) -> None:
        scenario = TaskScenario(economy=1000, remaining_time=420.0)
        sentry = SentryState()
        scenario.kill_sentry()
        cost = scenario.instant_revive_cost
        self.assertTrue(scenario.exchange_instant_revive())
        self.assertEqual(scenario.economy, 1000 - cost)
        self.assertEqual(scenario.sentry_hp, 400.0)
        self.assertEqual(scenario.instant_revive_count, 1)
        self.assertGreater(scenario.invincible_remaining, 0.0)
        self.assertGreater(scenario.instant_revive_power_boost_remaining, 0.0)
        self.assertTrue(scenario.weak_state)
        self.assertEqual(scenario.apply_attack_damage(8, "42mm", team="red"), 0)
        self.assertEqual(scenario.sentry_hp, 400.0)
        self.assertIn(f"剩余 {scenario.economy}", scenario.event_message)

    def test_instant_revive_is_available_only_during_dead_readbar(self) -> None:
        scenario = TaskScenario(economy=1000)
        self.assertFalse(scenario.can_exchange_instant_revive()[0])

        scenario.kill_sentry()
        self.assertTrue(scenario.can_exchange_instant_revive()[0])

        scenario.exchange_instant_revive()
        self.assertFalse(scenario.can_exchange_instant_revive()[0])


class NewStateSnapshotTests(unittest.TestCase):
    def test_json_snapshot_round_trip_restores_level_exp_and_posture(self) -> None:
        scenario = TaskScenario(
            economy=650,
            remote_heal_remaining=3.0,
            exchanged_17mm=200,
        )
        scenario.robot_level[1] = 3
        scenario.robot_exp[1] = 1200.0
        scenario.own_robot_level[3] = 2
        scenario.own_robot_exp[3] = 600.0
        scenario.posture_time[2] = 50.0
        scenario.reinforced_time[2] = 10.0
        scenario.posture_reinforced = True
        scenario.add_buff("中央高地", "defence", 0.25, 30.0)
        scenario.zone_inside.add("central_highland")
        snapshot = capture_snapshot("场景", scenario, SentryState(), None, None)
        loaded = json.loads(json.dumps(snapshot))
        loaded["task"]["revive_mode"] = "task"
        restored, _sentry, _controlled = restore_snapshot(loaded)
        self.assertEqual(restored.robot_level[1], 3)
        self.assertEqual(restored.robot_exp[1], 1200.0)
        self.assertEqual(restored.own_robot_level[3], 2)
        self.assertEqual(restored.posture_time[2], 50.0)
        self.assertEqual(restored.reinforced_time[2], 10.0)
        self.assertTrue(restored.posture_reinforced)
        self.assertEqual(restored.economy, 650)
        self.assertEqual(len(restored.active_buffs), 1)
        self.assertIn("central_highland", restored.zone_inside)


class RulebookRespawnTests(unittest.TestCase):
    def test_revive_read_time_formula(self) -> None:
        scenario = TaskScenario(remaining_time=120.0)
        scenario.instant_revive_count = 2
        # 10 + (420-120)/10 + 20*2 = 80
        self.assertEqual(scenario.revive_seconds_required, 80.0)

    def test_read_bar_revive_uses_ten_percent_hp_and_weak_state(self) -> None:
        scenario = TaskScenario(remaining_time=420.0)
        sentry = SentryState(x=17.0, y=10.0)
        scenario.kill_sentry()
        self.assertEqual(scenario.revive_required, 10.0)
        scenario.update(10.1, sentry)
        self.assertEqual(scenario.sentry_hp, 40.0)
        self.assertTrue(scenario.weak_state)
        self.assertGreaterEqual(
            scenario.invincible_remaining,
            RULEBOOK_REVIVE_INVINCIBLE - 0.2,
        )
        self.assertTrue(scenario.respawn_fire_locked)

        sentry.x, sentry.y = SUPPLY
        scenario.update(0.1, sentry)
        self.assertFalse(scenario.weak_state)
        self.assertFalse(scenario.respawn_fire_locked)
        self.assertLessEqual(
            scenario.invincible_remaining,
            RULEBOOK_REVIVE_WEAK_INVINCIBLE_MIN,
        )

    def test_supply_accelerates_revive_read_bar(self) -> None:
        scenario = TaskScenario(remaining_time=420.0)
        sentry = SentryState(x=SUPPLY[0], y=SUPPLY[1])
        scenario.kill_sentry()
        scenario.update(2.5, sentry)
        self.assertGreaterEqual(scenario.sentry_hp, 40.0)
        self.assertFalse(scenario.weak_state)

    def test_invincible_blocks_sentry_damage(self) -> None:
        scenario = TaskScenario(remaining_time=420.0)
        sentry = SentryState(x=17.0, y=10.0)
        scenario.kill_sentry()
        scenario.update(10.1, sentry)
        before = scenario.sentry_hp
        self.assertEqual(scenario.apply_attack_damage(8, "42mm", team="red"), 0)
        self.assertEqual(scenario.sentry_hp, before)


if __name__ == "__main__":
    unittest.main()
