"""Regression tests for the v2 rule-fidelity changes."""

from __future__ import annotations

import math
import unittest
from pathlib import Path

from rm2026_sim.core import Arena, SentryState
from rm2026_sim.app import STATIC_COLLISION_RECTANGLES
from rm2026_sim.field_geometry import BLUE_OUTPOST, RED_OUTPOST
from rm2026_sim.field_geometry import (
    BLUE_ROAD_CROSSING_CARDS,
    RED_ROAD_CROSSING_CARDS,
)
from rm2026_sim.map_asset import load_p5_pgm
from rm2026_sim.navigation import (
    ASTAR_PLANNING_RADIUS,
    OccupancyGrid,
)
from rm2026_sim.task_state import (
    ATTACK,
    BUFFER_ENERGY_CAP,
    CRITICAL_HALF_WIDTH,
    DecisionView,
    FIRE_ALIGNMENT_TOLERANCE,
    HOME,
    PENDING_AMMO_CAP,
    SUPPLY,
    TaskScenario,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def external_attack_decision() -> DecisionView:
    return DecisionView(
        "测试外部行为树攻击命令",
        1,
        ATTACK,
        0,
        0,
        1,
        6,
        0,
        200,
    )


class V2RuleTests(unittest.TestCase):
    def test_timeout_finishes_match_and_returns_home(self) -> None:
        scenario = TaskScenario(
            remaining_time=0.1,
            own_base_hp=5000,
            enemy_base_hp=4000,
        )
        decision = scenario.update(1.0, SentryState())
        self.assertTrue(scenario.game_finished)
        self.assertFalse(scenario.game_running)
        self.assertEqual(scenario.winner_team, "red")
        self.assertEqual(scenario.result_label, "己方获胜")
        self.assertIsNone(decision.goal)
        self.assertEqual(scenario.remaining_time, 0.0)

    def test_winner_tiebreak_uses_outposts_then_damage(self) -> None:
        outpost_lead = TaskScenario(
            remaining_time=0.1,
            own_outpost_hp=1500,
            enemy_outpost_hp=1000,
        )
        outpost_lead.update(0.2, SentryState())
        self.assertEqual(outpost_lead.winner_team, "red")

        one_destroyed = TaskScenario(
            remaining_time=0.1,
            own_outpost_destroyed_ever=True,
            own_outpost_hp=0,
            enemy_outpost_hp=1500,
        )
        one_destroyed.update(0.2, SentryState())
        self.assertEqual(one_destroyed.winner_team, "blue")

        damage_lead = TaskScenario(
            remaining_time=0.1,
            own_outpost_hp=0,
            enemy_outpost_hp=0,
            own_outpost_destroyed_ever=True,
            enemy_outpost_destroyed_ever=True,
            own_team_damage=300,
            enemy_team_damage=200,
        )
        damage_lead.update(0.2, SentryState())
        self.assertEqual(damage_lead.winner_team, "red")

    def test_building_damage_tiers_are_reachable(self) -> None:
        scenario = TaskScenario()
        self.assertEqual(
            scenario.rule_damage("17mm", 7, armor_zone="upper_front"), 5
        )
        self.assertEqual(
            scenario.rule_damage(
                "17mm", 7, armor_zone="upper_front", critical_zone=True
            ),
            8,
        )
        self.assertEqual(scenario.rule_damage("17mm", 7), 20)
        self.assertEqual(
            scenario.rule_damage("17mm", 7, critical_zone=True), 30
        )
        self.assertEqual(scenario.rule_damage("17mm", 6), 20)
        self.assertEqual(
            scenario.rule_damage("17mm", 6, critical_zone=True), 30
        )
        self.assertEqual(scenario.rule_damage("42mm", 7), 200)
        self.assertEqual(
            scenario.rule_damage("42mm", 7, critical_zone=True), 300
        )

    def test_live_shot_does_not_auto_award_building_critical(self) -> None:
        scenario = TaskScenario()
        target_x, target_y = scenario.target_position(6)
        sentry = SentryState(x=ATTACK[0], y=ATTACK[1])
        sentry.turret_angle = math.atan2(target_y - sentry.y, target_x - sentry.x)
        shot = scenario.resolve_fire_shot(sentry, preferred_target=6)
        self.assertIsNotNone(shot)
        assert shot is not None
        self.assertTrue(scenario.is_center_hit(shot))
        self.assertEqual(scenario.armor_zone_for_shot(shot, sentry), "normal")

        scenario.update(
            0.5,
            sentry,
            decision_override=external_attack_decision(),
            fire_request=True,
            hit_target_id=shot.target_id,
            critical_zone=False,
            target_armor_zone=scenario.armor_zone_for_shot(shot, sentry),
        )
        self.assertEqual(scenario.enemy_outpost_hp, 1400.0)

    def test_line_of_sight_blocks_raw_wall_cells(self) -> None:
        arena = Arena(
            width=3.0,
            height=1.0,
            map_resolution=0.5,
            map_origin_x=0.0,
            map_origin_y=0.0,
        )
        width, height = 6, 2
        blocked = bytearray(width * height)
        # Wall in the middle of the row that contains y=0.5.
        blocked[1 * width + 3] = 1
        grid = OccupancyGrid(
            arena=arena,
            width=width,
            height=height,
            blocked=bytes(blocked),
            collision_radius=0.0,
        )
        self.assertFalse(grid.line_of_sight((0.25, 0.5), (2.75, 0.5)))
        self.assertTrue(grid.line_of_sight((0.25, 0.5), (1.25, 0.5)))

    def test_line_of_sight_is_used_by_fire_solution(self) -> None:
        scenario = TaskScenario()
        target_x, target_y = scenario.target_position(6)
        sentry = SentryState(x=ATTACK[0], y=ATTACK[1])
        sentry.turret_angle = math.atan2(target_y - sentry.y, target_x - sentry.x)
        shot = scenario.resolve_fire_shot(
            sentry,
            preferred_target=6,
            line_of_sight=lambda _start, _end: False,
        )
        self.assertIsNone(shot)

    def test_outpost_fire_point_is_free_and_has_line_of_sight(self) -> None:
        image = load_p5_pgm(PROJECT_ROOT / "assets" / "rmuc2026.pgm")
        arena = Arena()
        collision_grid = OccupancyGrid.from_pgm(image, arena)
        los_grid = OccupancyGrid.from_pgm(image, arena, collision_radius=0.0)
        planning_grid = OccupancyGrid.from_pgm(
            image,
            arena,
            collision_radius=ASTAR_PLANNING_RADIUS,
        )
        target = BLUE_OUTPOST
        self.assertTrue(collision_grid.is_free_world(*ATTACK))
        self.assertTrue(los_grid.line_of_sight(ATTACK, target))
        self.assertLess(math.dist(ATTACK, target), 4.0)
        path = planning_grid.find_path(HOME, ATTACK)
        self.assertTrue(path)
        self.assertLess(math.dist(path[-1], ATTACK), 0.15)

    def test_static_building_rectangles_block_building_centres(self) -> None:
        image = load_p5_pgm(PROJECT_ROOT / "assets" / "rmuc2026.pgm")
        grid = OccupancyGrid.from_pgm(image, Arena()).with_blocked_rectangles(
            STATIC_COLLISION_RECTANGLES,
            inflation=0.39,
        )
        self.assertFalse(grid.is_free_world(*BLUE_OUTPOST))
        self.assertFalse(grid.is_free_world(*RED_OUTPOST))
        self.assertFalse(grid.is_free_world(0.3, 7.5))
        self.assertFalse(grid.is_free_world(27.8, 7.5))
        self.assertTrue(grid.is_free_world(*ATTACK))

    def test_outpost_aim_error_tracks_barrel_alignment(self) -> None:
        scenario = TaskScenario()
        sentry = SentryState(x=ATTACK[0], y=ATTACK[1])
        target_x, target_y = scenario.target_position(6)
        bearing = math.atan2(target_y - sentry.y, target_x - sentry.x)

        sentry.turret_angle = bearing + math.radians(20.0)
        self.assertGreater(
            scenario.aim_error(sentry, 6),
            FIRE_ALIGNMENT_TOLERANCE,
        )

        sentry.turret_angle = bearing
        self.assertLessEqual(
            scenario.aim_error(sentry, 6),
            FIRE_ALIGNMENT_TOLERANCE,
        )

    def test_supply_heals_ten_percent_and_transfers_ammo(self) -> None:
        scenario = TaskScenario(
            enemy_outpost_hp=0.0,
            sentry_hp=100.0,
            ammo=50,
            pending_ammo=100,
            respawn_fire_locked=True,
        )
        sentry = SentryState(x=SUPPLY[0], y=SUPPLY[1])
        scenario.update(0.5, sentry)
        self.assertEqual(scenario.sentry_hp, 120.0)
        self.assertEqual(scenario.ammo, 150)
        self.assertEqual(scenario.pending_ammo, 0)
        self.assertFalse(scenario.respawn_fire_locked)

    def test_supply_heals_twenty_five_percent_after_four_minutes_out_of_combat(self) -> None:
        scenario = TaskScenario(
            enemy_outpost_hp=0.0,
            remaining_time=180.0,
            sentry_hp=100.0,
            sentry_out_of_combat_seconds=6.0,
        )
        sentry = SentryState(x=SUPPLY[0], y=SUPPLY[1])
        scenario.update(0.5, sentry)
        self.assertEqual(scenario.sentry_hp, 150.0)

    def test_damage_resets_out_of_combat_supply_bonus(self) -> None:
        scenario = TaskScenario(
            enemy_outpost_hp=0.0,
            remaining_time=180.0,
            sentry_hp=100.0,
            sentry_out_of_combat_seconds=6.0,
        )
        sentry = SentryState(x=SUPPLY[0], y=SUPPLY[1])
        scenario.adjust_sentry_health(-1, sentry)
        self.assertEqual(scenario.sentry_out_of_combat_seconds, 0.0)
        scenario.update(0.5, sentry)
        self.assertLessEqual(scenario.sentry_hp, 120.0)

    def test_economy_starts_at_400_and_awards_table_5_5_ticks(self) -> None:
        scenario = TaskScenario(remaining_time=358.9)
        scenario.update(0.2, SentryState())
        self.assertEqual(scenario.economy, 450)

        last_tick = TaskScenario(remaining_time=58.9)
        last_tick._economy_tick = 5
        last_tick.update(0.2, SentryState())
        self.assertEqual(last_tick.economy, 550)

    def test_pending_ammo_cap_is_above_rulebook_example(self) -> None:
        scenario = TaskScenario()
        for _ in range(100):
            scenario.adjust_pending_ammo(1)
        self.assertEqual(scenario.pending_ammo, PENDING_AMMO_CAP)
        self.assertGreaterEqual(PENDING_AMMO_CAP, 600)

    def test_respawn_always_uses_rulebook_readbar_and_keeps_ammo(self) -> None:
        scenario = TaskScenario(
            enemy_outpost_hp=0.0,
            ammo=77,
        )
        sentry = SentryState(heat=200.0)
        scenario.kill_sentry()
        scenario.update(5.1, sentry)
        self.assertEqual(scenario.sentry_hp, 0.0)
        self.assertEqual(scenario.ammo, 77)

        scenario.update(5.0, sentry)
        self.assertEqual(scenario.sentry_hp, 40.0)
        self.assertEqual(scenario.ammo, 77)
        self.assertEqual(sentry.heat, 0.0)
        self.assertEqual(scenario.sentry_buffer_energy, BUFFER_ENERGY_CAP)
        self.assertTrue(scenario.respawn_fire_locked)

    def test_heat_lock_and_permanent_q2_lock(self) -> None:
        scenario = TaskScenario(
            enemy_outpost_hp=0.0,
            ammo=300,
            fire_rate=20,
        )
        sentry = SentryState()
        scenario.update(1.5, sentry, fire_request=True)
        self.assertGreater(sentry.heat, 260.0)
        self.assertTrue(scenario.sentry_heat_locked)
        self.assertFalse(scenario.sentry_heat_permanent_lock)

        scenario.update(30.0, sentry, fire_request=False)
        self.assertFalse(scenario.sentry_heat_locked)
        self.assertEqual(sentry.heat, 0.0)

        long_frame = TaskScenario(
            enemy_outpost_hp=0.0,
            ammo=300,
            fire_rate=20,
        )
        long_frame_sentry = SentryState()
        long_frame.update(2.0, long_frame_sentry, fire_request=True)
        self.assertEqual(long_frame_sentry.heat, 270.0)
        self.assertTrue(long_frame.sentry_heat_locked)
        self.assertFalse(long_frame.sentry_heat_permanent_lock)

    def test_experience_level_up_adds_health_immediately(self) -> None:
        scenario = TaskScenario()
        before_max = scenario.robot_max_hp(1)
        before_hp = scenario.robot_hp[1]
        scenario.award_experience(1, 550.0)
        self.assertEqual(scenario.robot_level[1], 2)
        self.assertEqual(scenario.robot_max_hp(1), 220.0)
        self.assertEqual(scenario.robot_hp[1], before_hp + 20.0)
        self.assertGreater(scenario.robot_max_hp(1), before_max)

    def test_level_up_does_not_apply_to_sentry_or_engineer(self) -> None:
        scenario = TaskScenario()
        self.assertEqual(scenario.award_experience(8, 550.0), 0)
        self.assertEqual(scenario.award_experience(2, 550.0), 0)
        self.assertEqual(scenario.robot_level[8], 1)
        self.assertEqual(scenario.robot_level[2], 1)

    def test_hero_and_infantry_performance_modes_change_max_health(self) -> None:
        scenario = TaskScenario()
        self.assertEqual(scenario.robot_max_hp(1), 200.0)
        scenario.cycle_hero_mode()
        self.assertEqual(scenario.hero_mode, "melee")
        self.assertEqual(scenario.robot_max_hp(1), 260.0)

        self.assertEqual(scenario.robot_max_hp(3), 200.0)
        scenario.cycle_infantry_chassis()
        self.assertEqual(scenario.infantry_chassis_mode, "power")
        self.assertEqual(scenario.robot_max_hp(3), 150.0)

    def test_central_highland_and_tunnel_buffs(self) -> None:
        highland = TaskScenario(defence_buff=0, active_posture=1, enemy_outpost_hp=0)
        sentry = SentryState(x=14.0, y=7.5)
        highland.update(0.1, sentry)
        self.assertAlmostEqual(highland.buff_value("defence"), 0.25)
        self.assertAlmostEqual(highland.effective_sentry_defence, 0.0)

        tunnel = TaskScenario(defence_buff=0, active_posture=3, enemy_outpost_hp=0)
        tunnel_sentry = SentryState(x=3.5, y=10.5)
        tunnel.update(0.1, tunnel_sentry)
        self.assertAlmostEqual(tunnel.buff_value("defence"), 0.50)
        self.assertAlmostEqual(tunnel.buff_value("heat_cooling"), 2.0)
        self.assertAlmostEqual(tunnel.effective_sentry_heat_cooling, 20.0)

    def test_road_gain_requires_low_then_high_card(self) -> None:
        low, high = RED_ROAD_CROSSING_CARDS
        scenario = TaskScenario(defence_buff=0)
        sentry = SentryState(x=low[0], y=low[1])

        scenario.update(0.0, sentry)
        self.assertEqual(scenario.buff_value("defence"), 0.0)
        sentry.x, sentry.y = high
        scenario.update(0.1, sentry)

        self.assertAlmostEqual(scenario.buff_value("defence"), 0.25)
        self.assertAlmostEqual(scenario.zone_cooldowns["terrain_road"], 15.0 - 0.036)
        self.assertAlmostEqual(scenario.active_buffs[-1].remaining, 5.0)

    def test_road_gain_rejects_high_card_without_low_card(self) -> None:
        low, high = RED_ROAD_CROSSING_CARDS
        scenario = TaskScenario(defence_buff=0)
        sentry = SentryState(x=high[0], y=high[1])
        scenario.update(0.1, sentry)
        self.assertEqual(scenario.buff_value("defence"), 0.0)

        sentry.x, sentry.y = low
        scenario.update(0.1, sentry)
        sentry.x, sentry.y = high
        scenario.update(0.1, sentry)
        self.assertAlmostEqual(scenario.buff_value("defence"), 0.25)

    def test_road_gain_detects_both_cards_crossed_in_one_update(self) -> None:
        low, high = RED_ROAD_CROSSING_CARDS
        scenario = TaskScenario(defence_buff=0)
        sentry = SentryState(x=low[0], y=low[1] - 0.4)
        scenario.update(0.0, sentry)
        sentry.x, sentry.y = low[0], high[1] + 0.4
        scenario.update(0.2, sentry)
        self.assertAlmostEqual(scenario.buff_value("defence"), 0.25)

    def test_blue_road_uses_its_own_low_to_high_order(self) -> None:
        low, high = BLUE_ROAD_CROSSING_CARDS
        scenario = TaskScenario(defence_buff=0)
        sentry = SentryState(x=low[0], y=low[1])
        scenario.update(0.0, sentry)
        sentry.x, sentry.y = high
        scenario.update(0.1, sentry)
        self.assertAlmostEqual(scenario.buff_value("defence"), 0.25)

    def test_road_gain_sequence_expires_after_three_seconds(self) -> None:
        low, high = RED_ROAD_CROSSING_CARDS
        scenario = TaskScenario(defence_buff=0)
        sentry = SentryState(x=low[0], y=low[1])
        scenario.update(0.0, sentry)
        sentry.x, sentry.y = low[0], (low[1] + high[1]) / 2.0
        scenario.update(3.1, sentry)
        sentry.x, sentry.y = high
        scenario.update(0.1, sentry)
        self.assertEqual(scenario.buff_value("defence"), 0.0)

    def test_other_field_card_interrupts_road_sequence(self) -> None:
        low, high = RED_ROAD_CROSSING_CARDS
        scenario = TaskScenario(defence_buff=0)
        sentry = SentryState(x=low[0], y=low[1])
        scenario.update(0.0, sentry)
        sentry.x, sentry.y = 2.1, 1.3
        scenario.update(0.5, sentry)
        sentry.x, sentry.y = high
        scenario.update(0.5, sentry)
        self.assertEqual(scenario.buff_value("defence"), 0.0)

    def test_road_sequence_cannot_mix_sides_and_cooldown_is_shared(self) -> None:
        low, high = RED_ROAD_CROSSING_CARDS
        scenario = TaskScenario(defence_buff=0)
        sentry = SentryState(x=low[0], y=low[1])
        scenario.update(0.0, sentry)
        sentry.x, sentry.y = 19.75, 12.5
        scenario.update(0.1, sentry)
        self.assertEqual(scenario.buff_value("defence"), 0.0)

        sentry.x, sentry.y = low
        scenario.update(0.1, sentry)
        sentry.x, sentry.y = high
        scenario.update(0.1, sentry)
        self.assertAlmostEqual(scenario.buff_value("defence"), 0.25)
        sentry.x, sentry.y = low
        scenario.update(0.1, sentry)
        sentry.x, sentry.y = high
        scenario.update(0.1, sentry)
        self.assertLess(scenario.active_buffs[-1].remaining, 5.0)

    def test_small_rune_grants_defence_buff(self) -> None:
        scenario = TaskScenario()
        sentry = SentryState(x=7.0, y=7.5)
        scenario.activate_rune("small")
        self.assertEqual(scenario.rune_state, "activating")
        for _ in range(5):
            self.assertTrue(scenario.hit_rune(sentry))
        self.assertEqual(scenario.rune_state, "active")
        self.assertAlmostEqual(scenario.buff_value("defence"), 0.25)
        self.assertGreater(scenario.rune_timer, 40.0)

    def test_large_rune_table_and_attack_buff(self) -> None:
        from rm2026_sim.field_rules import large_rune_profile

        low = large_rune_profile(2.0, 5)
        high = large_rune_profile(9.5, 10)
        self.assertEqual(low[0][0], "attack")
        self.assertAlmostEqual(low[0][1], 1.50)
        self.assertAlmostEqual(high[0][1], 3.00)
        self.assertAlmostEqual(high[1][1], 0.50)
        self.assertEqual(high[2][1], 5.0)

    def test_attack_buff_reaches_damage_calculation(self) -> None:
        scenario = TaskScenario()
        scenario.add_buff("大能量机关", "attack", 2.0, 30.0)
        self.assertEqual(scenario.effective_attack_buff, 2.0)
        self.assertEqual(
            scenario.rule_damage("17mm", 1, attack_buff=scenario.effective_attack_buff),
            40,
        )

    def test_buff_expires(self) -> None:
        scenario = TaskScenario()
        scenario.add_buff("test", "defence", 0.5, 0.1)
        scenario.update(0.2, SentryState())
        self.assertEqual(scenario.active_buffs, [])

    def test_posture_effects_change_defence_cooling_and_power(self) -> None:
        scenario = TaskScenario(defence_buff=0, active_posture=2)
        self.assertAlmostEqual(scenario.effective_sentry_defence, 0.50)
        self.assertAlmostEqual(scenario.effective_sentry_heat_cooling, 10.0)
        self.assertEqual(scenario.effective_sentry_power_limit, 50.0)

        scenario.active_posture = 1
        self.assertAlmostEqual(scenario.effective_sentry_defence, -0.25)
        self.assertAlmostEqual(scenario.effective_sentry_heat_cooling, 90.0)
        self.assertEqual(scenario.effective_sentry_power_limit, 50.0)

        scenario.active_posture = 3
        self.assertAlmostEqual(scenario.effective_sentry_defence, -0.25)
        self.assertEqual(scenario.effective_sentry_power_limit, 150.0)

    def test_reinforced_and_decayed_posture_effects(self) -> None:
        scenario = TaskScenario(defence_buff=0, active_posture=2)
        self.assertAlmostEqual(scenario.effective_sentry_defence, 0.50)
        scenario.posture_reinforced = True
        self.assertAlmostEqual(scenario.effective_sentry_defence, 0.99)
        scenario.posture_reinforced = False
        scenario.posture_time[2] = 180.0
        self.assertAlmostEqual(scenario.effective_sentry_defence, 0.25)

        scenario.active_posture = 1
        scenario.posture_reinforced = True
        scenario.reinforced_time[1] = 0.0
        self.assertEqual(scenario.posture_heat_gain_multiplier, 0.0)

        scenario.active_posture = 3
        scenario.posture_reinforced = True
        self.assertEqual(scenario.effective_sentry_power_limit, 200.0)

    def test_reinforced_posture_auto_exits_after_fifteen_seconds(self) -> None:
        scenario = TaskScenario(active_posture=2)
        scenario.posture_reinforced = True
        scenario._update_posture(2, 15.1)
        self.assertFalse(scenario.posture_reinforced)
        self.assertGreaterEqual(scenario.reinforced_time[2], 15.0)

    def test_posture_time_accumulates_while_switch_is_cooling(self) -> None:
        scenario = TaskScenario(active_posture=2)
        scenario.posture_cooldown_remaining = 5.0
        scenario._update_posture(3, 1.0)
        self.assertAlmostEqual(scenario.posture_time[2], 1.0)
        self.assertEqual(scenario.active_posture, 2)

    def test_posture_switch_has_five_second_cooldown(self) -> None:
        scenario = TaskScenario(active_posture=3)
        scenario._update_posture(1, 0.1)
        self.assertEqual(scenario.active_posture, 1)
        self.assertAlmostEqual(scenario.posture_cooldown_remaining, 5.0)
        scenario._update_posture(2, 1.0)
        self.assertEqual(scenario.active_posture, 1)
        scenario._update_posture(2, 4.0)
        self.assertEqual(scenario.active_posture, 1)
        scenario._update_posture(2, 0.1)
        self.assertEqual(scenario.active_posture, 2)

    def test_collision_contact_applies_two_point_rule_damage(self) -> None:
        scenario = TaskScenario(defence_buff=0, active_posture=2)
        before_sentry = scenario.sentry_hp
        before_infantry = scenario.enemy_health(3)
        total = scenario.apply_collision_contact("red", 8, "blue", 3)
        self.assertGreater(total, 0)
        self.assertLess(scenario.sentry_hp, before_sentry)
        self.assertLess(scenario.enemy_health(3), before_infantry)
        self.assertGreater(scenario.enemy_team_damage, 0)
        self.assertGreater(scenario.own_team_damage, 0)

    def test_aerial_and_buildings_are_excluded_from_collision_damage(self) -> None:
        scenario = TaskScenario()
        self.assertEqual(
            scenario.apply_collision_contact("red", 5, "blue", 6),
            0,
        )
        self.assertEqual(
            scenario.apply_collision_contact("red", 6, "blue", 5),
            0,
        )

    def test_critical_half_width_constant_is_ten_mm_zone(self) -> None:
        self.assertAlmostEqual(CRITICAL_HALF_WIDTH, 0.005)


if __name__ == "__main__":
    unittest.main()
