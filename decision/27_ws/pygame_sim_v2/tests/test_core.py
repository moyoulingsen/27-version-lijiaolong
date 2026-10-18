from __future__ import annotations

import math
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from rm2026_sim.core import Arena, SentryState, Viewport
from rm2026_sim.field_geometry import RED_HOME, RED_START_POSITIONS
from rm2026_sim.map_asset import load_p5_pgm
from rm2026_sim.scenario_store import (
    ScenarioStore,
    capture_snapshot,
    delete_snapshot,
    restore_snapshot,
)
from rm2026_sim.task_state import (
    AGGRESSIVE_PATROL_POINTS,
    ATTACK,
    ATTACK_RANGE,
    CONSERVATIVE_PATROL_POINTS,
    DETECTION_RANGE,
    HOME,
    PATROL_POINTS,
    ROBOT_PROFILES,
    RULE_BASE_HP,
    RULE_BASE_SHIELD,
    RULE_OUTPOST_HP,
    RULE_DAMAGE_PER_SHOT,
    RULE_FIRE_RATE_MAX,
    SUPPLY,
    TaskScenario,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent


class CoordinateTests(unittest.TestCase):
    def test_world_screen_round_trip_and_y_axis_direction(self) -> None:
        arena = Arena()
        viewport = Viewport.fit(1280, 800, arena)

        self.assertAlmostEqual(viewport.width / 28.0, viewport.height / 15.0)
        self.assertEqual(viewport.world_to_screen(0.0, 15.0), (viewport.left, viewport.top))
        self.assertAlmostEqual(
            viewport.world_to_screen(28.0, 0.0)[0],
            viewport.left + viewport.width,
        )
        world = viewport.screen_to_world(*viewport.world_to_screen(*RED_HOME))
        self.assertAlmostEqual(world[0], RED_HOME[0])
        self.assertAlmostEqual(world[1], RED_HOME[1])

    def test_source_map_crop_matches_task_coordinates(self) -> None:
        image = load_p5_pgm(PROJECT_ROOT / "assets" / "rmuc2026.pgm")
        self.assertEqual((image.width, image.height), (584, 301))
        self.assertEqual(Arena().map_crop(image.width, image.height), (11, 1, 560, 300))
        self.assertIn(0, image.pixels)
        self.assertIn(254, image.pixels)


class SentryStateTests(unittest.TestCase):
    def test_movement_requires_manual_control(self) -> None:
        arena = Arena()
        sentry = SentryState()
        sentry.update(1.0, 1.0, 0.0, arena)
        self.assertEqual((sentry.x, sentry.y), RED_HOME)

        sentry.enable_manual_control()
        sentry.update(1.0, 1.0, 0.0, arena)
        self.assertAlmostEqual(sentry.x, RED_HOME[0] + 3.0)
        sentry.cancel_manual_control()
        sentry.update(1.0, 1.0, 0.0, arena)
        self.assertAlmostEqual(sentry.x, RED_HOME[0] + 3.0)

    def test_diagonal_speed_is_normalized_and_bounds_are_clamped(self) -> None:
        arena = Arena()
        sentry = SentryState(x=27.9, y=14.9, manual_control=True)
        sentry.update(10.0, 1.0, 1.0, arena)
        self.assertEqual((sentry.x, sentry.y), (28.0, 15.0))

    def test_turret_rotates_automatically_without_manual_control(self) -> None:
        sentry = SentryState(turret_speed=math.radians(90.0))
        sentry.update(1.0, 0.0, 0.0, Arena())
        self.assertAlmostEqual(math.degrees(sentry.turret_angle), 90.0)
        self.assertFalse(sentry.manual_control)

    def test_disabled_spin_and_gimbal_hold_their_angles(self) -> None:
        sentry = SentryState(spin_angle=0.4, turret_angle=0.7)
        sentry.update(
            1.0,
            0.0,
            0.0,
            Arena(),
            spin_enabled=False,
            turret_enabled=False,
        )
        self.assertAlmostEqual(sentry.spin_angle, 0.4)
        self.assertAlmostEqual(sentry.turret_angle, 0.7)

    def test_high_speed_gyro_rotates_faster_than_low_speed(self) -> None:
        low_speed = SentryState(spin_angle=0.0)
        high_speed = SentryState(spin_angle=0.0)
        low_speed.update(0.1, 0.0, 0.0, Arena(), spin_speed_scale=0.6)
        high_speed.update(0.1, 0.0, 0.0, Arena(), spin_speed_scale=1.6)
        self.assertGreater(high_speed.spin_angle, low_speed.spin_angle)


class TaskScenarioTests(unittest.TestCase):
    def test_ground_robot_manual_movement_uses_world_coordinates(self) -> None:
        scenario = TaskScenario()
        start_x, start_y = scenario.robot_position(3)
        scenario.move_robot(3, 1.0, 0.0, 0.5, Arena())
        moved_x, moved_y = scenario.robot_position(3)
        self.assertAlmostEqual(moved_x, start_x + 1.5)
        self.assertAlmostEqual(moved_y, start_y)

        scenario.move_robot(3, 1.0, 1.0, 10.0, Arena())
        self.assertEqual(scenario.robot_position(3), (28.0, 15.0))

    def test_aerial_robot_is_not_manually_controllable(self) -> None:
        scenario = TaskScenario()
        with self.assertRaises(ValueError):
            scenario.move_robot(5, 1.0, 0.0, 1.0, Arena())

    def test_friendly_robots_have_independent_positions_health_and_ammo(self) -> None:
        scenario = TaskScenario()
        self.assertEqual(scenario.robot_position(1, team="red"), RED_START_POSITIONS[1])
        self.assertEqual(scenario.own_robot_health(1), 200.0)
        self.assertEqual(scenario.own_robot_ammunition(1), 0)
        self.assertEqual(scenario.own_robot_ammunition(2), 0)

        scenario.move_robot(1, 1.0, 0.0, 0.5, Arena(), team="red")
        self.assertEqual(
            scenario.robot_position(1, team="red"),
            (RED_START_POSITIONS[1][0] + 1.5, RED_START_POSITIONS[1][1]),
        )
        scenario.adjust_own_robot_health(1, -1)
        scenario.adjust_own_robot_ammunition(1, 1)
        self.assertEqual(scenario.own_robot_health(1), 180.0)
        self.assertEqual(scenario.own_robot_ammunition(1), 20)

    def test_friendly_aerial_robot_can_move_in_the_2d_simulation(self) -> None:
        scenario = TaskScenario()
        scenario.move_robot(5, 1.0, 0.0, 0.5, Arena(), team="red")
        self.assertEqual(
            scenario.robot_position(5, team="red"),
            (RED_START_POSITIONS[5][0] + 1.5, RED_START_POSITIONS[5][1]),
        )

    def test_other_friendly_robots_do_not_change_decision_output(self) -> None:
        scenario = TaskScenario()
        sentry = SentryState()
        before = scenario.evaluate(sentry)
        scenario.own_robot_positions[1] = [17.0, 10.0]
        scenario.own_robot_hp[1] = 1.0
        scenario.own_robot_ammo[1] = 0
        self.assertEqual(scenario.evaluate(sentry), before)

    def test_initial_priority_is_attack_outpost(self) -> None:
        decision = TaskScenario().evaluate(SentryState())
        self.assertEqual(decision.behavior, "攻击敌方前哨")
        self.assertEqual(decision.goal, ATTACK)
        self.assertEqual(decision.target, 6)
        self.assertEqual(decision.spin_mode, 1)
        self.assertEqual(decision.tripod_mode, 1)

    def test_behavior_selects_spin_mode_without_outpost_gate(self) -> None:
        scenario = TaskScenario()
        scenario.destroy_enemy_outpost()
        self.assertEqual(scenario.evaluate(SentryState()).spin_mode, 1)
        self.assertEqual(scenario.evaluate(SentryState()).tripod_mode, 1)
        scenario.toggle_patrol_mode()
        self.assertEqual(scenario.patrol_name, "保守巡逻")
        self.assertEqual(scenario.evaluate(SentryState()).behavior, "低血量回血")

    def test_patrol_boundary_requires_both_health_and_economy_low(self) -> None:
        scenario = TaskScenario(
            enemy_outpost_hp=0.0,
            sentry_hp=400.0,
            economy=399,
        )
        decision = scenario.evaluate(SentryState())
        self.assertEqual(scenario.patrol_name, "激进巡逻")
        self.assertEqual(decision.spin_mode, 1)
        self.assertEqual(decision.tripod_mode, 1)

        scenario.sentry_hp = 149
        scenario.economy = 399
        self.assertEqual(scenario.patrol_name, "保守巡逻")

        scenario.economy = 400
        self.assertEqual(scenario.patrol_name, "激进巡逻")

        scenario.sentry_hp = 150
        scenario.economy = 399
        self.assertEqual(scenario.patrol_name, "激进巡逻")

        scenario.sentry_hp = 149
        scenario.economy = 399
        decision = scenario.evaluate(SentryState())
        self.assertEqual(decision.behavior, "低血量回血")

    def test_attack_lock_stops_gimbal_and_enables_shooting(self) -> None:
        scenario = TaskScenario()
        sentry = SentryState(x=ATTACK[0], y=ATTACK[1])
        target_x, target_y = scenario.target_position(6)
        sentry.turret_angle = math.atan2(target_y - sentry.y, target_x - sentry.x)
        decision = scenario.evaluate(sentry)
        self.assertEqual(decision.shoot_mode, 1)
        self.assertEqual(decision.tripod_mode, 0)

    def test_fire_request_without_barrel_alignment_does_not_deal_damage(self) -> None:
        scenario = TaskScenario()
        sentry = SentryState(x=ATTACK[0], y=ATTACK[1], turret_angle=0.0)
        decision = scenario.evaluate(sentry)
        original_health = scenario.enemy_outpost_hp

        scenario.update(
            0.5,
            sentry,
            decision_override=decision,
            fire_request=True,
            hit_target_id=scenario.resolve_fire_target(sentry, preferred_target=6),
        )

        self.assertEqual(scenario.enemy_outpost_hp, original_health)
        self.assertEqual(scenario.ammo, 290)

    def test_detection_range_can_select_target_before_attack_range(self) -> None:
        scenario = TaskScenario(enemy_outpost_hp=0.0)
        scenario.robot_positions[3] = [15.0, 10.0]
        sentry = SentryState(x=10.0, y=10.0, turret_angle=0.0)

        self.assertLess(ATTACK_RANGE, 5.0)
        self.assertGreaterEqual(DETECTION_RANGE, 5.0)
        self.assertIsNone(scenario.resolve_fire_target(sentry))
        self.assertEqual(
            scenario.resolve_fire_target(
                sentry,
                maximum_distance=DETECTION_RANGE,
                preferred_target=3,
            ),
            3,
        )

    def test_aligned_barrel_hit_deals_damage_to_outpost(self) -> None:
        scenario = TaskScenario()
        target_x, target_y = scenario.target_position(6)
        sentry = SentryState(x=ATTACK[0], y=ATTACK[1])
        sentry.turret_angle = math.atan2(target_y - sentry.y, target_x - sentry.x)
        shot = scenario.resolve_fire_shot(sentry, preferred_target=6)
        self.assertIsNotNone(shot)
        scenario.update(
            0.5,
            sentry,
            decision_override=scenario.evaluate(sentry),
            fire_request=True,
            hit_target_id=shot.target_id,
            critical_zone=scenario.is_center_hit(shot),
            target_armor_zone=scenario.armor_zone_for_shot(shot, sentry),
        )

        self.assertEqual(shot.target_id, 6)
        self.assertEqual(scenario.enemy_outpost_hp, 1200.0)

    def test_manual_fire_hits_enemy_under_barrel_without_bt_target(self) -> None:
        scenario = TaskScenario()
        target_x, target_y = scenario.target_position(6)
        sentry = SentryState(x=ATTACK[0], y=ATTACK[1], manual_control=True)
        sentry.turret_angle = math.atan2(target_y - sentry.y, target_x - sentry.x)

        shot = scenario.resolve_fire_shot(sentry)
        self.assertIsNotNone(shot)
        scenario.update(
            0.25,
            sentry,
            decision_override=scenario.evaluate(sentry),
            fire_request=True,
            hit_target_id=shot.target_id,
            critical_zone=scenario.is_center_hit(shot),
            target_armor_zone=scenario.armor_zone_for_shot(shot, sentry),
        )

        self.assertEqual(shot.target_id, 6)
        self.assertEqual(scenario.enemy_outpost_hp, 1350.0)

    def test_live_fire_uses_rule_damage_even_with_legacy_debug_value(self) -> None:
        scenario = TaskScenario(fire_rate=10, damage_per_shot=7, ammo=20)
        target_x, target_y = scenario.target_position(6)
        sentry = SentryState(x=ATTACK[0], y=ATTACK[1])
        sentry.turret_angle = math.atan2(target_y - sentry.y, target_x - sentry.x)

        scenario.update(
            0.5,
            sentry,
            decision_override=scenario.evaluate(sentry),
            fire_request=True,
            hit_target_id=6,
        )

        self.assertEqual(scenario.ammo, 15)
        self.assertEqual(scenario.enemy_outpost_hp, 1400.0)

    def test_fire_rate_and_damage_adjustments_are_rule_clamped(self) -> None:
        scenario = TaskScenario()
        for _ in range(100):
            scenario.adjust_fire_rate(1)
            scenario.adjust_damage_per_shot(1)
        self.assertEqual(scenario.fire_rate, RULE_FIRE_RATE_MAX)
        self.assertEqual(scenario.damage_per_shot, RULE_DAMAGE_PER_SHOT)

        for _ in range(100):
            scenario.adjust_fire_rate(-1)
            scenario.adjust_damage_per_shot(-1)
        self.assertEqual(scenario.fire_rate, 1)
        self.assertEqual(scenario.damage_per_shot, 1)

    def test_rule_damage_matches_v220_armor_and_buff_examples(self) -> None:
        scenario = TaskScenario()
        self.assertEqual(scenario.rule_damage("17mm", 1), 20)
        self.assertEqual(scenario.rule_damage("42mm", 1), 200)
        self.assertEqual(scenario.rule_damage("17mm", 7, armor_zone="upper_front"), 5)
        self.assertEqual(scenario.rule_damage("17mm", 6, critical_zone=True), 30)
        self.assertEqual(scenario.rule_damage("42mm", 6, critical_zone=True), 300)
        # Same-type attack gains take the maximum, rather than multiplying.
        self.assertEqual(
            scenario.rule_damage("42mm", 7, attack_buff=2, critical_zone=True), 400
        )
        # Rulebook page 109: 25% defense offset by 15% vulnerability.
        self.assertEqual(
            scenario.rule_damage("42mm", 1, attack_buff=2, defence_buff=0.10), 360
        )
        self.assertEqual(
            scenario.rule_damage("42mm", 1, attack_buff=2, defence_buff=-0.15), 460
        )
        self.assertEqual(
            scenario.rule_damage("17mm", 7, armor_zone="upper_front", critical_zone=True), 8
        )
        self.assertEqual(scenario.rule_damage("collision", 1, attack_buff=2), 2)
        self.assertEqual(scenario.rule_damage("collision", 1, defence_buff=0.25), 2)
        self.assertEqual(scenario.rule_damage("17mm", 5), 0)
        self.assertEqual(scenario.rule_damage("collision", 5), 0)
        self.assertEqual(scenario.rule_damage("collision", 7), 0)
        self.assertEqual(scenario.rule_damage("17mm", 1, defence_buff=1), 0)

    def test_base_virtual_shield_is_consumed_before_hp_for_both_teams(self) -> None:
        for team in ("red", "blue"):
            with self.subTest(team=team):
                scenario = TaskScenario(own_outpost_hp=0, enemy_outpost_hp=0)
                scenario.apply_attack_damage(7, "17mm", shots=7, team=team)
                self.assertEqual(getattr(scenario, "own_base_shield" if team == "red" else "enemy_base_shield"), 10)
                self.assertEqual(getattr(scenario, "own_base_hp" if team == "red" else "enemy_base_hp"), 5000)
                scenario.apply_attack_damage(7, "42mm", team=team)
                self.assertEqual(getattr(scenario, "own_base_shield" if team == "red" else "enemy_base_shield"), 0)
                self.assertEqual(getattr(scenario, "own_base_hp" if team == "red" else "enemy_base_hp"), 4810)

    def test_rule_damage_rounds_each_hit_before_accumulating(self) -> None:
        scenario = TaskScenario(enemy_outpost_hp=0)
        damage = scenario.apply_attack_damage(
            7, "17mm", armor_zone="upper_front", critical_zone=True, shots=2
        )
        self.assertEqual(damage, 16)
        self.assertEqual(scenario.enemy_base_shield, 134)

    def test_rule_damage_can_update_local_friendly_hp_and_sentry_death(self) -> None:
        scenario = TaskScenario()
        scenario.apply_attack_damage(1, "17mm", team="red")
        self.assertEqual(scenario.own_robot_health(1), 180)
        scenario.apply_attack_damage(8, "42mm", shots=2, team="red", defence_buff=0.0)
        self.assertEqual(scenario.sentry_hp, 0)
        self.assertEqual(scenario.death_elapsed, 0)
        self.assertEqual(scenario.own_robot_health(3), 200)

    def test_live_fire_uses_target_armor_and_defence_settings(self) -> None:
        scenario = TaskScenario(enemy_outpost_hp=0)
        scenario.update(
            0.05, SentryState(), fire_request=True, hit_target_id=7,
            critical_zone=True, target_armor_zone="upper_front", target_defence_buff=0.25,
        )
        self.assertEqual(scenario.ammo, 299)
        self.assertEqual(scenario.enemy_base_shield, 144)

    def test_base_is_invulnerable_while_its_outpost_survives(self) -> None:
        scenario = TaskScenario()
        for team in ("red", "blue"):
            self.assertEqual(scenario.apply_attack_damage(7, "42mm", team=team), 0)
        self.assertEqual(scenario.enemy_base_shield, 150)
        self.assertEqual(scenario.own_base_shield, 150)
        self.assertEqual(scenario.enemy_base_hp, 5000)
        self.assertEqual(scenario.own_base_hp, 5000)

    def test_defence_buff_uses_lower_recovery_threshold(self) -> None:
        scenario = TaskScenario(defence_buff=60, sentry_hp=170.0)
        scenario.enemy_outpost_hp = 0.0
        self.assertEqual(scenario.evaluate(SentryState()).behavior, "巡逻")
        scenario.sentry_hp = 150.0
        decision = scenario.evaluate(SentryState())
        self.assertEqual(decision.behavior, "低血量回血")
        self.assertEqual(decision.goal, SUPPLY)
        self.assertEqual(decision.health_threshold, 160)

        scenario.sentry_hp = 250.0
        self.assertEqual(scenario.evaluate(SentryState()).behavior, "低血量回血")
        scenario.sentry_hp = 399.0
        self.assertEqual(scenario.evaluate(SentryState()).behavior, "低血量回血")
        scenario.sentry_hp = 400.0
        self.assertEqual(scenario.evaluate(SentryState()).behavior, "巡逻")

    def test_respawn_requires_supply_before_firing_unlocks(self) -> None:
        scenario = TaskScenario(enemy_outpost_hp=0.0)
        sentry = SentryState()
        scenario.kill_sentry()
        scenario.update(5.6, sentry, confirm_respawn=True)
        decision = scenario.evaluate(sentry)
        self.assertEqual(decision.behavior, "复活后补给解锁")
        self.assertEqual(decision.goal, SUPPLY)
        self.assertTrue(scenario.respawn_fire_locked)

        sentry.x, sentry.y = SUPPLY
        scenario.update(0.1, sentry)
        self.assertFalse(scenario.respawn_fire_locked)

    def test_any_position_inside_supply_zone_can_recover_and_receive_ammo(self) -> None:
        scenario = TaskScenario(
            enemy_outpost_hp=0.0,
            sentry_hp=150.0,
            ammo=0,
            pending_ammo=100,
            respawn_fire_locked=True,
        )
        sentry = SentryState(x=3.5, y=2.0)

        scenario.update(0.5, sentry)

        self.assertEqual(scenario.sentry_hp, 170.0)
        self.assertEqual(scenario.ammo, 100)
        self.assertEqual(scenario.pending_ammo, 0)
        self.assertFalse(scenario.respawn_fire_locked)

    def test_position_outside_supply_zone_does_not_trigger_supply(self) -> None:
        scenario = TaskScenario(
            enemy_outpost_hp=0.0,
            sentry_hp=150.0,
            ammo=0,
            pending_ammo=100,
            respawn_fire_locked=True,
        )
        sentry = SentryState(x=4.1, y=2.0)

        scenario.update(0.5, sentry)

        self.assertEqual(scenario.sentry_hp, 150.0)
        self.assertEqual(scenario.ammo, 0)
        self.assertEqual(scenario.pending_ammo, 100)
        self.assertTrue(scenario.respawn_fire_locked)

    def test_patrol_mode_switches_between_conservative_and_aggressive_routes(self) -> None:
        scenario = TaskScenario(enemy_outpost_hp=0.0)
        sentry = SentryState()
        self.assertEqual(scenario.patrol_name, "激进巡逻")
        self.assertEqual(scenario.patrol_points, AGGRESSIVE_PATROL_POINTS)
        self.assertEqual(scenario.evaluate(sentry).goal, AGGRESSIVE_PATROL_POINTS[0])

        scenario.toggle_patrol_mode()
        self.assertEqual(scenario.patrol_name, "保守巡逻")
        self.assertEqual(scenario.patrol_points, CONSERVATIVE_PATROL_POINTS)

        scenario.toggle_patrol_mode()
        self.assertEqual(scenario.patrol_name, "激进巡逻")
        self.assertEqual(scenario.patrol_points, AGGRESSIVE_PATROL_POINTS)
        self.assertEqual(scenario.evaluate(sentry).goal, AGGRESSIVE_PATROL_POINTS[0])

    def test_patrol_route_loops_from_last_point_back_to_first(self) -> None:
        scenario = TaskScenario(
            enemy_outpost_hp=0.0,
            sentry_hp=125.0,
            economy=350,
        )
        sentry = SentryState()

        for expected_index, point in enumerate(CONSERVATIVE_PATROL_POINTS):
            sentry.x, sentry.y = point
            scenario.update(0.0, sentry)
            self.assertEqual(
                scenario.patrol_index,
                (expected_index + 1) % len(CONSERVATIVE_PATROL_POINTS),
            )

        self.assertEqual(scenario.patrol_name, "保守巡逻")
        self.assertEqual(scenario.patrol_points[scenario.patrol_index], CONSERVATIVE_PATROL_POINTS[0])

    def test_match_time_reset_restores_complete_match_state(self) -> None:
        scenario = TaskScenario(
            remaining_time=12.0,
            sentry_hp=150.0,
            ammo=20,
            pending_ammo=125,
            economy=850,
            own_outpost_hp=0,
            own_base_hp=500,
            enemy_outpost_hp=0.0,
            enemy_base_hp=500.0,
            game_paused=True,
        )
        scenario.robot_positions[3] = [18.0, 9.0]
        scenario.game_finished = True
        scenario.game_running = False

        scenario.reset_match_time()

        self.assertEqual(scenario.remaining_time, 420.0)
        self.assertTrue(scenario.game_running)
        self.assertFalse(scenario.game_finished)
        self.assertFalse(scenario.game_paused)
        self.assertEqual(scenario.sentry_hp, 400.0)
        self.assertEqual(scenario.ammo, 300)
        self.assertEqual(scenario.pending_ammo, 0)
        self.assertEqual(scenario.economy, 400)
        self.assertEqual(scenario.fire_rate, RULE_FIRE_RATE_MAX)
        self.assertEqual(scenario.damage_per_shot, RULE_DAMAGE_PER_SHOT)
        self.assertEqual(scenario.own_outpost_hp, 1500)
        self.assertEqual(scenario.own_base_hp, 5000)
        self.assertEqual(scenario.enemy_outpost_hp, 1500.0)
        self.assertEqual(scenario.enemy_base_hp, 5000.0)
        self.assertNotEqual(scenario.robot_position(3), (18.0, 9.0))

    def test_either_base_destroyed_finishes_match(self) -> None:
        own_base_destroyed = TaskScenario(own_base_hp=0)
        own_decision = own_base_destroyed.update(0.0, SentryState())
        self.assertTrue(own_base_destroyed.game_finished)
        self.assertFalse(own_base_destroyed.game_running)
        self.assertEqual(own_base_destroyed.evaluate(SentryState()).goal, HOME)
        self.assertEqual(own_decision.goal, HOME)

        enemy_base_destroyed = TaskScenario(enemy_base_hp=0.0)
        enemy_decision = enemy_base_destroyed.update(0.0, SentryState())
        self.assertTrue(enemy_base_destroyed.game_finished)
        self.assertFalse(enemy_base_destroyed.game_running)
        self.assertEqual(enemy_base_destroyed.evaluate(SentryState()).goal, HOME)
        self.assertEqual(enemy_decision.goal, HOME)

    def test_match_time_can_be_adjusted_and_is_clamped(self) -> None:
        scenario = TaskScenario(remaining_time=200.0)

        scenario.adjust_match_time(1)
        self.assertEqual(scenario.remaining_time, 210.0)
        scenario.adjust_match_time(-1)
        self.assertEqual(scenario.remaining_time, 200.0)

        scenario.remaining_time = 418.0
        scenario.adjust_match_time(1)
        self.assertEqual(scenario.remaining_time, 420.0)
        scenario.remaining_time = 3.0
        scenario.adjust_match_time(-1)
        self.assertEqual(scenario.remaining_time, 0.0)

    def test_pause_freezes_time_ammo_and_damage(self) -> None:
        scenario = TaskScenario(remaining_time=200.0)
        target_x, target_y = scenario.target_position(6)
        sentry = SentryState(x=ATTACK[0], y=ATTACK[1])
        sentry.turret_angle = math.atan2(target_y - sentry.y, target_x - sentry.x)
        hit_target = scenario.resolve_fire_target(sentry, preferred_target=6)

        scenario.toggle_pause()
        scenario.update(
            1.0,
            sentry,
            decision_override=scenario.evaluate(sentry),
            fire_request=True,
            hit_target_id=hit_target,
        )

        self.assertTrue(scenario.game_paused)
        self.assertEqual(scenario.remaining_time, 200.0)
        self.assertEqual(scenario.ammo, 300)
        self.assertEqual(scenario.enemy_outpost_hp, 1500.0)

        scenario.toggle_pause()
        scenario.update(
            1.0,
            sentry,
            decision_override=scenario.evaluate(sentry),
            fire_request=True,
            hit_target_id=hit_target,
        )
        self.assertFalse(scenario.game_paused)
        self.assertEqual(scenario.remaining_time, 199.0)
        self.assertEqual(scenario.ammo, 280)
        self.assertEqual(scenario.enemy_outpost_hp, 1100.0)

    def test_enemy_health_adjustment_is_clamped(self) -> None:
        scenario = TaskScenario(enemy_outpost_hp=0.0)
        scenario.adjust_enemy_health(6, 1)
        self.assertEqual(scenario.enemy_health(6), 100.0)

        for _ in range(20):
            scenario.adjust_enemy_health(1, -1)
        self.assertEqual(scenario.enemy_health(1), 0.0)

        for _ in range(20):
            scenario.adjust_enemy_health(1, 1)
        self.assertEqual(scenario.enemy_health(1), 200.0)

    def test_sentry_health_adjustment_controls_death_state_and_is_clamped(self) -> None:
        scenario = TaskScenario(sentry_hp=25.0)
        scenario.adjust_sentry_health(-1)
        self.assertEqual(scenario.sentry_hp, 0.0)
        self.assertEqual(scenario.death_elapsed, 0.0)

        scenario.adjust_sentry_health(1)
        self.assertEqual(scenario.sentry_hp, 25.0)
        self.assertIsNone(scenario.death_elapsed)

        for _ in range(20):
            scenario.adjust_sentry_health(1)
        self.assertEqual(scenario.sentry_hp, 400.0)

    def test_own_attributes_can_be_adjusted_and_are_clamped(self) -> None:
        scenario = TaskScenario(
            ammo=120,
            pending_ammo=100,
            economy=300,
            defence_buff=60,
            own_outpost_hp=1000,
            own_base_hp=5000,
        )

        scenario.adjust_ammo(1)
        scenario.adjust_pending_ammo(1)
        scenario.adjust_economy(1)
        scenario.adjust_defence_buff(-1)
        scenario.adjust_own_outpost_health(-1)
        scenario.adjust_own_base_health(-1)
        self.assertEqual(scenario.ammo, 140)
        self.assertEqual(scenario.pending_ammo, 125)
        self.assertEqual(scenario.economy, 350)
        self.assertEqual(scenario.defence_buff, 50)
        self.assertEqual(scenario.own_outpost_hp, 900)
        self.assertEqual(scenario.own_base_hp, 4500)

        for _ in range(100):
            scenario.adjust_ammo(-1)
            scenario.adjust_pending_ammo(-1)
            scenario.adjust_economy(-1)
            scenario.adjust_defence_buff(-1)
            scenario.adjust_own_outpost_health(-1)
            scenario.adjust_own_base_health(-1)
        self.assertEqual(scenario.ammo, 0)
        self.assertEqual(scenario.pending_ammo, 0)
        self.assertEqual(scenario.economy, 0)
        self.assertEqual(scenario.defence_buff, 0)
        self.assertEqual(scenario.own_outpost_hp, 0)
        self.assertEqual(scenario.own_base_hp, 0)

        for _ in range(100):
            scenario.adjust_pending_ammo(1)
            scenario.adjust_economy(1)
        self.assertEqual(scenario.pending_ammo, 1000)
        self.assertEqual(scenario.economy, 1000)

    def test_significant_unseen_damage_starts_irregular_defensive_evasion(self) -> None:
        scenario = TaskScenario(enemy_outpost_hp=0.0)
        moving_sentry = SentryState()
        scenario.inject_unseen_damage(moving_sentry)
        self.assertGreater(scenario.dodge_remaining, 0.0)
        first_goal = scenario.dodge_goal
        decision = scenario.evaluate(moving_sentry)
        self.assertEqual(decision.behavior, "视野外显著受伤不规则回避")
        self.assertEqual(decision.posture, 2)
        self.assertEqual(decision.spin_mode, 3)
        self.assertEqual(decision.tripod_mode, 1)

        scenario.update(0.8, moving_sentry)
        self.assertNotEqual(scenario.dodge_goal, first_goal)
        scenario.update(5.0, moving_sentry)
        self.assertEqual(scenario.dodge_remaining, 0.0)
        self.assertNotIn("回避", scenario.evaluate(moving_sentry).behavior)

    def test_two_manual_25_health_drops_trigger_accumulated_evasion(self) -> None:
        scenario = TaskScenario(enemy_outpost_hp=0.0, sentry_hp=400.0)
        sentry = SentryState()
        scenario.adjust_sentry_health(-1, sentry, unseen_damage=True)
        self.assertEqual(scenario.sentry_hp, 375.0)
        self.assertEqual(scenario.dodge_remaining, 0.0)

        scenario.adjust_sentry_health(-1, sentry, unseen_damage=True)
        self.assertEqual(scenario.sentry_hp, 350.0)
        self.assertGreater(scenario.dodge_remaining, 0.0)

    def test_manual_damage_accumulation_expires_after_one_second(self) -> None:
        scenario = TaskScenario(enemy_outpost_hp=0.0, sentry_hp=400.0)
        sentry = SentryState()
        scenario.adjust_sentry_health(-1, sentry, unseen_damage=True)
        scenario.update(1.1, sentry)
        scenario.adjust_sentry_health(-1, sentry, unseen_damage=True)

        self.assertEqual(scenario.sentry_hp, 350.0)
        self.assertEqual(scenario.dodge_remaining, 0.0)


class ScenarioStoreTests(unittest.TestCase):
    def test_snapshot_round_trip_preserves_positions_and_properties(self) -> None:
        scenario = TaskScenario(
            remaining_time=188.0,
            sentry_hp=240.0,
            ammo=80,
            economy=650,
            fire_rate=12,
            damage_per_shot=18,
            aggressive_patrol=True,
            game_paused=True,
        )
        scenario.robot_positions[3] = [17.2, 6.4]
        scenario.robot_hp[3] = 135.0
        scenario.own_robot_positions[3] = [7.2, 6.4]
        scenario.own_robot_hp[3] = 85.0
        scenario.own_robot_ammo[3] = 125
        sentry = SentryState(
            x=12.3,
            y=8.7,
            manual_control=True,
            spin_angle=0.6,
            turret_angle=-0.4,
        )
        snapshot = capture_snapshot("场景 1", scenario, sentry, 3, "red")

        with TemporaryDirectory() as directory:
            save_path = Path(directory) / "scenarios.json"
            store = ScenarioStore(save_path)
            store.save([snapshot])
            self.assertTrue(save_path.is_file())
            loaded = ScenarioStore(save_path).load()

        restored_task, restored_sentry, controlled = restore_snapshot(loaded[0])
        self.assertEqual(restored_task.remaining_time, 188.0)
        self.assertEqual(restored_task.robot_position(3), (17.2, 6.4))
        self.assertEqual(restored_task.robot_hp[3], 135.0)
        self.assertEqual(restored_task.robot_position(3, team="red"), (7.2, 6.4))
        self.assertEqual(restored_task.own_robot_hp[3], 85.0)
        self.assertEqual(restored_task.own_robot_ammo[3], 125)
        self.assertEqual(restored_task.economy, 650)
        self.assertEqual(restored_task.fire_rate, 12)
        self.assertEqual(restored_task.damage_per_shot, 18)
        self.assertTrue(restored_task.aggressive_patrol)
        self.assertTrue(restored_task.game_paused)
        self.assertEqual((restored_sentry.x, restored_sentry.y), (12.3, 8.7))
        self.assertAlmostEqual(restored_sentry.turret_angle, -0.4)
        self.assertEqual(controlled, 3)
        self.assertEqual(loaded[0]["controlled_robot_team"], "red")

    def test_delete_snapshot_removes_only_selected_entry(self) -> None:
        snapshots = [
            {"name": "场景 1"},
            {"name": "场景 2"},
            {"name": "场景 3"},
        ]
        remaining, removed = delete_snapshot(snapshots, 1)

        self.assertEqual(removed["name"], "场景 2")
        self.assertEqual(
            [snapshot["name"] for snapshot in remaining],
            ["场景 1", "场景 3"],
        )
        self.assertEqual(len(snapshots), 3)

        with TemporaryDirectory() as directory:
            store = ScenarioStore(Path(directory) / "scenarios.json")
            store.save(remaining)
            persisted = store.load()
        self.assertEqual(
            [snapshot["name"] for snapshot in persisted],
            ["场景 1", "场景 3"],
        )


if __name__ == "__main__":
    unittest.main()
