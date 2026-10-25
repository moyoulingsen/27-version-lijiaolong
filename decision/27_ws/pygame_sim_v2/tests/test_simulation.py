from __future__ import annotations

import math
from pathlib import Path
from types import SimpleNamespace
import unittest

from rm2026_sim.app import SimulatorApp
from rm2026_sim.core import Arena, SentryState
from rm2026_sim.field_geometry import BLUE_BASE
from rm2026_sim.map_asset import load_p5_pgm
from rm2026_sim.navigation import (
    ASTAR_PLANNING_RADIUS,
    ROBOT_ENTITY_COLLISION_RADIUS,
    AStarNavigator,
    OccupancyGrid,
)
from rm2026_sim.scenario_store import capture_snapshot
from rm2026_sim.task_state import (
    AGGRESSIVE_PATROL_POINTS,
    ATTACK,
    DecisionView,
    HOME,
    PURSUIT_COST_ZONE_ID,
    SUPPLY,
    TaskScenario,
)


def external_decision(
    *,
    goal=None,
    posture: int = 3,
    spin_mode: int = 0,
    tripod_mode: int = 1,
    shoot_mode: int = 0,
    target: int = 0,
) -> DecisionView:
    return DecisionView(
        "测试外部行为树命令",
        posture,
        goal,
        spin_mode,
        tripod_mode,
        shoot_mode,
        target,
        0,
        200,
    )


class RobotSimulationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        image = load_p5_pgm(
            Path(__file__).resolve().parent.parent / "assets" / "rmuc2026.pgm"
        )
        cls.collision_grid = OccupancyGrid.from_pgm(image, Arena())
        cls.planning_grid = OccupancyGrid.from_pgm(
            image, Arena(), collision_radius=ASTAR_PLANNING_RADIUS
        )

    def setUp(self) -> None:
        # Exercise simulation logic without requiring a Pygame display.
        self.app = SimulatorApp.__new__(SimulatorApp)
        self.app.arena = Arena()
        self.app.task = TaskScenario()
        self.app.sentry = SentryState()
        self.app.controlled_robot_id = None
        self.app.controlled_robot_team = None
        self.app.collision_grid = self.collision_grid
        self.app.base_planning_grid = self.planning_grid
        self.app.navigator = AStarNavigator(self.planning_grid)
        self.app._planning_robot_signature = None
        self.app._manual_fire_held = False
        self.app.special_wall_traverse_timers = {}
        self.app.special_wall_traverse_active = set()
        self.app.robot_chassis_dynamics = {}
        self.app.region_edit_target = None
        self.app.region_edit_custom_id = None
        self.app.region_edit_kind = None
        self.app.region_edit_patrol_kind = None
        self.app.region_edit_new_custom = False
        self.app.region_edit_points = []
        self.app.region_edit_drag_index = None
        self.app.region_edit_error = ""
        self.app.region_edit_wall_id = None
        self.app.region_edit_special_id = None
        self.app.region_edit_slow_id = None
        self.app.region_edit_new_wall = False
        self.app.region_edit_new_special = False
        self.app.region_edit_new_slow = False
        self.app._normalize_robot_positions()

    def test_spawn_positions_are_free_and_do_not_overlap(self) -> None:
        positions = [
            (self.app.sentry.x, self.app.sentry.y),
            *(self.app.task.robot_position(i) for i in self.app.task.robot_positions),
            *(self.app.task.own_robot_position(i) for i in self.app.task.own_robot_positions),
        ]
        for index, position in enumerate(positions):
            self.assertTrue(self.collision_grid.is_free_world(*position))
            for other in positions[index + 1:]:
                self.assertGreaterEqual(
                    math.dist(position, other), 2 * ROBOT_ENTITY_COLLISION_RADIUS
                )

    def test_sentry_can_reach_attack_point_with_both_teams_present(self) -> None:
        decision = external_decision(goal=ATTACK, posture=1, spin_mode=1, target=6)
        for _ in range(1000):
            self.app._update_sentry_motion(0.033, 0.0, 0.0, decision)
            position = (self.app.sentry.x, self.app.sentry.y)
            for x, y, radius in self.app._collision_bodies("sentry", 8):
                self.assertGreaterEqual(
                    math.dist(position, (x, y)), radius + ROBOT_ENTITY_COLLISION_RADIUS
                )
            if math.dist(position, ATTACK) < 0.15:
                break
        self.assertLess(math.dist(position, ATTACK), 0.15)

    def test_automatic_motion_uses_same_chassis_power_limit_as_manual(self) -> None:
        self.app.task.active_posture = 1
        self.app.task.sentry_buffer_energy = 1.0
        decision = DecisionView(
            "自动移动测试",
            1,
            ATTACK,
            1,
            0,
            0,
            0,
            0,
            200,
        )

        peak_power = 0.0
        for _ in range(20):
            self.app._update_sentry_motion(0.1, 0.0, 0.0, decision)
            peak_power = max(peak_power, self.app.sentry.chassis_power)
            self.app.task.update(
                0.1,
                self.app.sentry,
                decision_override=decision,
                fire_request=False,
            )
            if self.app.task.sentry_chassis_power_cut:
                break

        self.assertGreater(peak_power, self.app.task.effective_sentry_power_limit)
        self.assertTrue(self.app.task.sentry_chassis_power_cut)

    def test_match_end_return_home_overrides_manual_control(self) -> None:
        self.app.sentry.x, self.app.sentry.y = ATTACK
        self.app.sentry.enable_manual_control()
        self.app.task.finish_game("比赛时间结束")
        decision = external_decision(goal=HOME)
        before = math.dist((self.app.sentry.x, self.app.sentry.y), HOME)

        self.app._update_sentry_motion(0.1, 0.0, 0.0, decision)

        after = math.dist((self.app.sentry.x, self.app.sentry.y), HOME)
        self.assertLess(after, before)

    def test_match_end_return_home_clears_chassis_power_cut(self) -> None:
        self.app.sentry.x, self.app.sentry.y = ATTACK
        self.app.task.sentry_chassis_power_cut_remaining = 5.0
        self.app.task.sentry_buffer_energy = 0.0

        self.app.task.finish_game("比赛时间结束")
        decision = external_decision(goal=HOME)
        before = math.dist((self.app.sentry.x, self.app.sentry.y), HOME)
        self.app._update_sentry_motion(0.1, 0.0, 0.0, decision)
        after = math.dist((self.app.sentry.x, self.app.sentry.y), HOME)

        self.assertFalse(self.app.task.sentry_chassis_power_cut)
        self.assertGreater(self.app.task.sentry_buffer_energy, 0.0)
        self.assertLess(after, before)

    def test_match_end_still_uses_behavior_tree_output(self) -> None:
        self.app.task.finish_game("比赛时间结束")
        self.app.bridge = SimpleNamespace(
            connected=True,
            latest_output=lambda: {
                "serial": {},
                "autoaim": {"target": 6},
                "goal": list(ATTACK),
            },
        )

        decision = self.app._bridge_decision()
        self.assertIsNotNone(decision)
        self.assertEqual(decision.goal, ATTACK)
        self.assertEqual(decision.target, 6)

    def test_manual_control_collides_with_either_team(self) -> None:
        for team in ("red", "blue"):
            with self.subTest(team=team):
                self.app.task = TaskScenario()
                self.app.task.set_robot_position(1, (1.5, 4.0), team=team)
                self.app.task.set_robot_position(3, (3.0, 4.0), team="red")
                self.app.controlled_robot_id = 1
                self.app.controlled_robot_team = team
                self.app._move_controlled_robot(1.0, 0.0, 1.0)
                x, y = self.app.task.robot_position(1, team=team)
                self.assertGreater(x, 1.5)
                self.assertLessEqual(x, 3.0 - 2 * ROBOT_ENTITY_COLLISION_RADIUS)
                self.assertAlmostEqual(y, 4.0)

    def test_manual_sentry_control_has_priority_over_pause(self) -> None:
        self.app.task.game_paused = True
        self.app.sentry.enable_manual_control()
        decision = external_decision()
        before = (self.app.sentry.x, self.app.sentry.y)
        remaining_time = self.app.task.remaining_time

        simulation_elapsed = self.app._advance_live_motion(
            0.1,
            1.0,
            0.0,
            decision,
            restarting=False,
        )
        self.app.task.update(
            0.1,
            self.app.sentry,
            decision_override=decision,
            fire_request=False,
        )

        self.assertEqual(simulation_elapsed, 0.0)
        self.assertGreater(self.app.sentry.x, before[0])
        self.assertEqual(self.app.sentry.y, before[1])
        self.assertEqual(self.app.task.remaining_time, remaining_time)

    def test_manual_other_robot_control_has_priority_over_pause(self) -> None:
        self.app.task.game_paused = True
        self.app.controlled_robot_id = 3
        self.app.controlled_robot_team = "red"
        decision = external_decision()
        sentry_before = (self.app.sentry.x, self.app.sentry.y)
        robot_before = self.app.task.own_robot_position(3)

        simulation_elapsed = self.app._advance_live_motion(
            0.1,
            0.0,
            1.0,
            decision,
            restarting=False,
        )

        robot_after = self.app.task.own_robot_position(3)
        self.assertEqual(simulation_elapsed, 0.0)
        self.assertGreater(robot_after[1], robot_before[1])
        self.assertEqual((self.app.sentry.x, self.app.sentry.y), sentry_before)

    def test_pause_still_freezes_automatic_sentry_motion(self) -> None:
        self.app.task.game_paused = True
        decision = external_decision(goal=ATTACK)
        before = (self.app.sentry.x, self.app.sentry.y)

        self.app._advance_live_motion(
            0.1,
            1.0,
            0.0,
            decision,
            restarting=False,
        )

        self.assertEqual((self.app.sentry.x, self.app.sentry.y), before)

    def test_paused_manual_collision_blocks_without_damage(self) -> None:
        self.app.task = TaskScenario(game_paused=True)
        self.app.task.set_robot_position(1, (1.5, 4.0), team="red")
        self.app.task.set_robot_position(3, (3.0, 4.0), team="blue")
        self.app.controlled_robot_id = 1
        self.app.controlled_robot_team = "red"
        decision = external_decision()
        own_hp = self.app.task.own_robot_health(1)
        enemy_hp = self.app.task.enemy_health(3)

        self.app._advance_live_motion(
            1.0,
            1.0,
            0.0,
            decision,
            restarting=False,
        )

        x, _ = self.app.task.own_robot_position(1)
        self.assertLessEqual(x, 3.0 - 2 * ROBOT_ENTITY_COLLISION_RADIUS)
        self.assertEqual(self.app.task.own_robot_health(1), own_hp)
        self.assertEqual(self.app.task.enemy_health(3), enemy_hp)

    def test_enemy_robots_two_three_four_cross_special_wall_after_one_second(self) -> None:
        base_grid = OccupancyGrid.empty(self.app.arena)
        polygon = ((2.0, 4.0), (2.2, 4.0), (2.2, 6.0), (2.0, 6.0))
        self.app.collision_grid = base_grid
        self.app.infantry_collision_grid = base_grid
        self.app.special_wall_collision_polygons = (("enemy_test_wall", polygon),)
        self.app.special_wall_individual_grids = {
            "enemy_test_wall": base_grid.with_blocked_polygons(
                (polygon,),
                inflation=ROBOT_ENTITY_COLLISION_RADIUS,
            )
        }
        self.app.special_wall_only_grids = {
            "enemy_test_wall": OccupancyGrid.empty(
                self.app.arena,
                collision_radius=0.0,
            ).with_blocked_polygons(
                (polygon,),
                inflation=ROBOT_ENTITY_COLLISION_RADIUS,
            )
        }
        start = (1.5, 5.0)
        proposed = (2.7, 5.0)

        for target_id in (2, 3, 4):
            with self.subTest(target_id=target_id):
                self.app.special_wall_traverse_timers = {}
                self.app.special_wall_traverse_active = set()
                halfway = self.app._move_with_special_wall_delay(
                    "blue",
                    target_id,
                    start,
                    proposed,
                    elapsed_seconds=0.5,
                    collision_bodies=(),
                    moving_radius=ROBOT_ENTITY_COLLISION_RADIUS,
                )
                released = self.app._move_with_special_wall_delay(
                    "blue",
                    target_id,
                    start,
                    proposed,
                    elapsed_seconds=0.5,
                    collision_bodies=(),
                    moving_radius=ROBOT_ENTITY_COLLISION_RADIUS,
                )

                self.assertLess(halfway[0], 2.0)
                self.assertEqual(released, proposed)
                self.assertIn(
                    ("blue", target_id, "enemy_test_wall"),
                    self.app.special_wall_traverse_active,
                )

    def test_selecting_friendly_sentry_reuses_existing_sentry_state(self) -> None:
        self.app._select_own_robot(3)
        self.assertEqual(self.app.controlled_robot_team, "red")
        self.assertEqual(self.app.controlled_robot_id, 3)
        self.assertFalse(self.app.sentry.manual_control)
        self.app._select_own_robot(8)
        self.assertTrue(self.app.sentry.manual_control)
        self.assertIsNone(self.app.controlled_robot_id)

    def test_loading_snapshot_restores_friendly_control_team(self) -> None:
        self.app.snapshots = [
            capture_snapshot("己方场景", self.app.task, self.app.sentry, 3, "red")
        ]
        self.app.bridge = SimpleNamespace(clear_output=lambda: None)
        self.app._load_snapshot(0)
        self.assertEqual(self.app.controlled_robot_team, "red")
        self.assertEqual(self.app.controlled_robot_id, 3)
        start_y = self.app.task.own_robot_position(3)[1]
        self.app._move_controlled_robot(0.0, 1.0, 0.01)
        self.assertGreater(self.app.task.own_robot_position(3)[1], start_y)

    def test_loading_snapshot_reuses_unchanged_collision_grids(self) -> None:
        self.app.snapshots = [
            capture_snapshot("不改地图", self.app.task, self.app.sentry, None)
        ]
        self.app.bridge = SimpleNamespace(clear_output=lambda: None)
        rebuild_calls = []
        self.app._rebuild_collision_grids = lambda: rebuild_calls.append(True)

        self.app._load_snapshot(0)

        self.assertEqual(rebuild_calls, [])

    def test_ros_bridge_maps_legacy_navigation_goals_to_field_geometry(self) -> None:
        self.app.bridge = SimpleNamespace(
            connected=True,
            latest_output=lambda: {
                "serial": {},
                "autoaim": {"target": 0},
                "goal": [0.0, 0.0],
            },
        )
        aliases = (
            ((17.0, 10.0), ATTACK),
            ((4.971, 7.5), HOME),
            ((2.0, 1.0), SUPPLY),
            ((16.0, 7.5), AGGRESSIVE_PATROL_POINTS[1]),
        )
        for legacy_goal, expected_goal in aliases:
            self.app.bridge.latest_output = lambda point=legacy_goal: {
                "serial": {},
                "autoaim": {"target": 0},
                "goal": point,
            }
            decision = self.app._bridge_decision()
            self.assertIsNotNone(decision)
            self.assertEqual(decision.goal, expected_goal)

    def test_manual_patrol_routes_are_published_and_map_legacy_bt_goals(self) -> None:
        aggressive = [[11.0, 3.0], [15.0, 7.5], [11.0, 12.0]]
        conservative = [[3.0, 4.0], [7.0, 4.0]]
        self.app.task.configure_patrol_routes(conservative, aggressive)
        self.app._restart_signal_remaining = 0.0

        state = self.app._bridge_state()

        self.assertNotIn("aggressive_patrol", state)
        self.assertEqual(state["aggressive_patrol_points"], aggressive)
        self.assertEqual(state["conservative_patrol_points"], conservative)
        self.app.bridge = SimpleNamespace(
            connected=True,
            latest_output=lambda: {
                "serial": {},
                "autoaim": {"target": 0},
                "goal": list(AGGRESSIVE_PATROL_POINTS[1]),
            },
        )
        decision = self.app._bridge_decision()
        self.assertEqual(decision.goal, tuple(aggressive[1]))
        self.assertEqual(decision.behavior, "行为树：激进巡逻")
        self.assertTrue(self.app.task.patrol_is_aggressive)

        self.app.bridge.latest_output = lambda: {
            "serial": {},
            "autoaim": {"target": 0},
            "goal": list(conservative[0]),
        }
        decision = self.app._bridge_decision()
        self.assertEqual(decision.behavior, "行为树：保守巡逻")
        self.assertFalse(self.app.task.patrol_is_aggressive)

    def test_disconnected_behavior_tree_holds_all_automatic_actuators(self) -> None:
        self.app.bridge = SimpleNamespace(connected=False, latest_output=lambda: None)

        self.assertIsNone(self.app._bridge_decision())
        decision = self.app._behavior_tree_unavailable_decision()
        self.assertIsNone(decision.goal)
        self.assertEqual(decision.spin_mode, 0)
        self.assertEqual(decision.shoot_mode, 0)
        self.assertEqual(decision.target, 0)

    def test_bridge_state_exposes_pursuit_support_inputs(self) -> None:
        self.app._restart_signal_remaining = 0.0
        self.app.task.enemy_outpost_hp = 0.0
        self.app.task.robot_hp[3] = 40.0
        self.app.sentry.x, self.app.sentry.y = (20.5, 8.0)
        autoaim = {
            "target": [0] * 9,
            "target_distance": [0.0] * 9,
            "target_polar_r": [0.0] * 9,
            "target_polar_angle": [0.0] * 9,
        }
        autoaim["target"][3] = 1
        autoaim["target_distance"][3] = 5.0
        autoaim["target_polar_r"][3] = 5.0
        self.app._simulated_autoaim = lambda _health: autoaim
        self.app.task.field_zone_overrides[PURSUIT_COST_ZONE_ID] = [
            [19.0, 10.0],
            [23.0, 10.0],
            [23.0, 6.0],
            [19.0, 6.0],
        ]
        self.app.task.own_robot_positions[1] = [21.0, 8.0]
        self.app.task.own_robot_positions[3] = [22.0, 8.0]
        self.app.task.own_robot_positions[2] = [5.0, 5.0]
        self.app.task.own_robot_positions[4] = [5.0, 6.0]

        self.assertEqual(self.app.task.pursuit_cost_friendly_count(self.app.sentry), 3)
        self.assertEqual(self.app._bridge_state()["hp_friend"][2], 200)

        self.app.task.own_robot_hp[3] = 0.0
        self.assertEqual(self.app.task.pursuit_cost_friendly_count(self.app.sentry), 2)
        self.assertEqual(self.app._bridge_state()["hp_friend"][2], 0)

    def test_friendly_referee_state_enters_bridge_but_not_enemy_selection(self) -> None:
        self.app._restart_signal_remaining = 0.0
        before_bridge = self.app._bridge_state()
        before_target = self.app.task.resolve_fire_target(self.app.sentry)

        # Put a low-health friendly robot directly in the sentry's camera view.
        self.app.task.own_robot_positions[1] = [self.app.sentry.x + 1.0, self.app.sentry.y]
        self.app.task.own_robot_hp[1] = 1.0
        self.app.task.own_robot_ammo[1] = 0

        after_bridge = self.app._bridge_state()
        self.assertNotEqual(after_bridge, before_bridge)
        self.assertEqual(after_bridge["hp_friend"][0], 1)
        self.assertEqual(
            after_bridge["friendly_ground_positions"][:2],
            [self.app.sentry.x + 1.0, self.app.sentry.y],
        )
        self.assertEqual(self.app.task.resolve_fire_target(self.app.sentry), before_target)

if __name__ == "__main__":
    unittest.main()
