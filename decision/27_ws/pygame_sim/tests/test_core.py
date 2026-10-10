from __future__ import annotations

import math
from pathlib import Path
import unittest

from rm2026_sim.core import Arena, SentryState, Viewport
from rm2026_sim.map_asset import load_p5_pgm
from rm2026_sim.task_state import (
    AGGRESSIVE_PATROL_POINTS,
    ATTACK,
    CONSERVATIVE_PATROL_POINTS,
    PATROL_POINTS,
    SUPPLY,
    TaskScenario,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent


class CoordinateTests(unittest.TestCase):
    def test_world_screen_round_trip_and_y_axis_direction(self) -> None:
        arena = Arena()
        viewport = Viewport.fit(1280, 800, arena)

        self.assertEqual(viewport.world_to_screen(0.0, 15.0), (viewport.left, viewport.top))
        self.assertAlmostEqual(
            viewport.world_to_screen(28.0, 0.0)[0],
            viewport.left + viewport.width,
        )
        world = viewport.screen_to_world(*viewport.world_to_screen(4.971, 7.5))
        self.assertAlmostEqual(world[0], 4.971)
        self.assertAlmostEqual(world[1], 7.5)

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
        self.assertEqual((sentry.x, sentry.y), (4.971, 7.5))

        sentry.enable_manual_control()
        sentry.update(1.0, 1.0, 0.0, arena)
        self.assertAlmostEqual(sentry.x, 7.971)
        sentry.cancel_manual_control()
        sentry.update(1.0, 1.0, 0.0, arena)
        self.assertAlmostEqual(sentry.x, 7.971)

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

    def test_initial_priority_is_attack_outpost(self) -> None:
        decision = TaskScenario().evaluate(SentryState())
        self.assertEqual(decision.behavior, "攻击敌方前哨")
        self.assertEqual(decision.goal, ATTACK)
        self.assertEqual(decision.target, 6)
        self.assertEqual(decision.spin_mode, 0)
        self.assertEqual(decision.tripod_mode, 1)

    def test_outpost_destruction_enables_spin(self) -> None:
        scenario = TaskScenario()
        scenario.destroy_own_outpost()
        decision = scenario.evaluate(SentryState())
        self.assertEqual(decision.spin_mode, 1)

    def test_attack_lock_stops_gimbal_and_enables_shooting(self) -> None:
        scenario = TaskScenario()
        sentry = SentryState(x=ATTACK[0], y=ATTACK[1])
        decision = scenario.evaluate(sentry)
        self.assertEqual(decision.shoot_mode, 1)
        self.assertEqual(decision.tripod_mode, 0)

    def test_defence_buff_uses_lower_recovery_threshold(self) -> None:
        scenario = TaskScenario(defence_buff=60, sentry_hp=170.0)
        scenario.enemy_outpost_hp = 0.0
        self.assertEqual(scenario.evaluate(SentryState()).behavior, "巡逻")
        scenario.sentry_hp = 150.0
        decision = scenario.evaluate(SentryState())
        self.assertEqual(decision.behavior, "低血量回血")
        self.assertEqual(decision.goal, SUPPLY)
        self.assertEqual(decision.health_threshold, 160)

    def test_respawn_requires_supply_before_firing_unlocks(self) -> None:
        scenario = TaskScenario(enemy_outpost_hp=0.0)
        sentry = SentryState()
        scenario.kill_sentry()
        scenario.update(5.6, sentry)
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

        self.assertEqual(scenario.sentry_hp, 200.0)
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
        sentry = SentryState(x=3.8, y=2.0)

        scenario.update(0.5, sentry)

        self.assertEqual(scenario.sentry_hp, 150.0)
        self.assertEqual(scenario.ammo, 0)
        self.assertEqual(scenario.pending_ammo, 100)
        self.assertTrue(scenario.respawn_fire_locked)

    def test_patrol_mode_switches_between_conservative_and_aggressive_routes(self) -> None:
        scenario = TaskScenario(enemy_outpost_hp=0.0)
        sentry = SentryState()
        self.assertEqual(scenario.patrol_points, CONSERVATIVE_PATROL_POINTS)
        self.assertEqual(scenario.evaluate(sentry).goal, CONSERVATIVE_PATROL_POINTS[0])

        scenario.toggle_patrol_mode()

        self.assertEqual(scenario.patrol_name, "激进巡逻")
        self.assertEqual(scenario.patrol_points, AGGRESSIVE_PATROL_POINTS)
        self.assertEqual(scenario.evaluate(sentry).goal, AGGRESSIVE_PATROL_POINTS[0])

    def test_patrol_route_loops_from_last_point_back_to_first(self) -> None:
        scenario = TaskScenario(enemy_outpost_hp=0.0)
        sentry = SentryState()

        for expected_index, point in enumerate(CONSERVATIVE_PATROL_POINTS):
            sentry.x, sentry.y = point
            scenario.update(0.0, sentry)
            self.assertEqual(
                scenario.patrol_index,
                (expected_index + 1) % len(CONSERVATIVE_PATROL_POINTS),
            )

        self.assertEqual(scenario.evaluate(sentry).goal, CONSERVATIVE_PATROL_POINTS[0])

    def test_match_time_can_be_reset_without_resetting_other_state(self) -> None:
        scenario = TaskScenario(remaining_time=12.0, sentry_hp=150.0, ammo=20)
        scenario.game_finished = True
        scenario.game_running = False

        scenario.reset_match_time()

        self.assertEqual(scenario.remaining_time, 420.0)
        self.assertTrue(scenario.game_running)
        self.assertFalse(scenario.game_finished)
        self.assertEqual(scenario.sentry_hp, 150.0)
        self.assertEqual(scenario.ammo, 20)

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
        scenario = TaskScenario(sentry_hp=40.0)
        scenario.adjust_sentry_health(-1)
        self.assertEqual(scenario.sentry_hp, 0.0)
        self.assertEqual(scenario.death_elapsed, 0.0)

        scenario.adjust_sentry_health(1)
        self.assertEqual(scenario.sentry_hp, 40.0)
        self.assertIsNone(scenario.death_elapsed)

        for _ in range(20):
            scenario.adjust_sentry_health(1)
        self.assertEqual(scenario.sentry_hp, 400.0)

    def test_dodge_requires_current_navigation_goal_to_be_reached(self) -> None:
        scenario = TaskScenario(enemy_outpost_hp=0.0)
        moving_sentry = SentryState()
        scenario.inject_unseen_damage(moving_sentry)
        self.assertEqual(scenario.dodge_remaining, 0.0)

        at_goal = SentryState(x=PATROL_POINTS[0][0], y=PATROL_POINTS[0][1])
        scenario.inject_unseen_damage(at_goal)
        self.assertGreater(scenario.dodge_remaining, 0.0)
        self.assertEqual(scenario.evaluate(at_goal).behavior, "视野外受伤躲避")


if __name__ == "__main__":
    unittest.main()
