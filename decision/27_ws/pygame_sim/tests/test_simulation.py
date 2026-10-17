from __future__ import annotations

import math
from pathlib import Path
from types import SimpleNamespace
import unittest

from rm2026_sim.app import SimulatorApp
from rm2026_sim.core import Arena, SentryState
from rm2026_sim.map_asset import load_p5_pgm
from rm2026_sim.navigation import (
    ASTAR_PLANNING_RADIUS,
    ROBOT_ENTITY_COLLISION_RADIUS,
    AStarNavigator,
    OccupancyGrid,
)
from rm2026_sim.scenario_store import capture_snapshot
from rm2026_sim.task_state import ATTACK, TaskScenario


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
        decision = self.app.task.evaluate(self.app.sentry)
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
        self.app._move_controlled_robot(0.0, 1.0, 0.01)
        self.assertGreater(self.app.task.own_robot_position(3)[1], 7.0)

    def test_friendly_scene_changes_do_not_enter_bridge_or_target_selection(self) -> None:
        self.app._restart_signal_remaining = 0.0
        before_bridge = self.app._bridge_state()
        before_decision = self.app._local_decision()
        before_target = self.app.task.resolve_fire_target(self.app.sentry)

        # Put a low-health friendly robot directly in the sentry's camera view.
        self.app.task.own_robot_positions[1] = [self.app.sentry.x + 1.0, self.app.sentry.y]
        self.app.task.own_robot_hp[1] = 1.0
        self.app.task.own_robot_ammo[1] = 0

        self.assertEqual(self.app._bridge_state(), before_bridge)
        self.assertEqual(self.app._local_decision(), before_decision)
        self.assertEqual(self.app.task.resolve_fire_target(self.app.sentry), before_target)


if __name__ == "__main__":
    unittest.main()
