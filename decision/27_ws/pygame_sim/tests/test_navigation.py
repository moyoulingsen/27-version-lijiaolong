from __future__ import annotations

import math
from pathlib import Path
import unittest

from rm2026_sim.core import Arena
from rm2026_sim.map_asset import load_p5_pgm
from rm2026_sim.navigation import (
    ASTAR_PLANNING_CLEARANCE,
    ASTAR_PLANNING_RADIUS,
    AStarNavigator,
    OccupancyGrid,
    ROBOT_COLLISION_LENGTH,
    ROBOT_COLLISION_RADIUS,
    ROBOT_COLLISION_WIDTH,
)
from rm2026_sim.task_state import (
    AGGRESSIVE_PATROL_POINTS,
    ATTACK,
    CONSERVATIVE_PATROL_POINTS,
    HOME,
    SUPPLY,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent


class OccupancyGridTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.arena = Arena()
        image = load_p5_pgm(PROJECT_ROOT / "assets" / "rmuc2026.pgm")
        cls.collision_grid = OccupancyGrid.from_pgm(image, cls.arena)
        cls.grid = OccupancyGrid.from_pgm(
            image,
            cls.arena,
            collision_radius=ASTAR_PLANNING_RADIUS,
        )

    def test_official_collision_volume_is_used_for_inflation(self) -> None:
        self.assertAlmostEqual(ROBOT_COLLISION_LENGTH, 0.52)
        self.assertAlmostEqual(ROBOT_COLLISION_WIDTH, 0.5196)
        self.assertGreater(
            ROBOT_COLLISION_RADIUS,
            math.hypot(ROBOT_COLLISION_LENGTH, ROBOT_COLLISION_WIDTH) * 0.5,
        )
        self.assertAlmostEqual(ASTAR_PLANNING_CLEARANCE, 0.07)
        self.assertAlmostEqual(
            ASTAR_PLANNING_RADIUS,
            ROBOT_COLLISION_RADIUS + ASTAR_PLANNING_CLEARANCE,
        )
        self.assertGreater(sum(self.grid.blocked), sum(self.collision_grid.blocked))
        self.assertEqual((self.grid.width, self.grid.height), (560, 300))

    def test_required_navigation_goals_are_free_after_map_inflation(self) -> None:
        goals = (
            HOME,
            SUPPLY,
            ATTACK,
            *CONSERVATIVE_PATROL_POINTS,
            *AGGRESSIVE_PATROL_POINTS,
        )
        self.assertTrue(all(self.grid.is_free_world(*goal) for goal in goals))
        self.assertFalse(self.grid.is_free_world(0.1, 7.5))

    def test_astar_finds_collision_free_route_across_the_arena(self) -> None:
        path = self.grid.find_path(HOME, ATTACK)
        self.assertTrue(path)
        self.assertEqual(path[-1], ATTACK)

        segment_start = HOME
        for waypoint in path:
            self.assertTrue(self.grid.is_free_world(*waypoint))
            reached = self.grid.trace_free_motion(segment_start, waypoint)
            self.assertAlmostEqual(reached[0], waypoint[0], places=6)
            self.assertAlmostEqual(reached[1], waypoint[1], places=6)
            segment_start = waypoint

    def test_blocked_goal_uses_nearest_free_endpoint(self) -> None:
        blocked_goal = (12.0, 12.0)
        self.assertFalse(self.grid.is_free_world(*blocked_goal))
        path = self.grid.find_path(HOME, blocked_goal)
        self.assertTrue(path)
        self.assertNotEqual(path[-1], blocked_goal)
        self.assertTrue(self.grid.is_free_world(*path[-1]))

    def test_swept_collision_stops_direct_motion_through_an_obstacle(self) -> None:
        target = (12.0, 7.5)
        self.assertTrue(self.grid.is_free_world(*target))
        reached = self.grid.move_with_collision(HOME, target)
        self.assertNotEqual(reached, target)
        self.assertTrue(self.grid.is_free_world(*reached))


class AStarNavigatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        image = load_p5_pgm(PROJECT_ROOT / "assets" / "rmuc2026.pgm")
        cls.collision_grid = OccupancyGrid.from_pgm(image, Arena())
        cls.grid = OccupancyGrid.from_pgm(
            image,
            Arena(),
            collision_radius=ASTAR_PLANNING_RADIUS,
        )

    def test_route_is_reused_until_goal_changes_materially(self) -> None:
        navigator = AStarNavigator(self.grid)
        navigator.update_goal(HOME, ATTACK)
        first_path = navigator.path
        navigator.update_goal(HOME, (ATTACK[0] + 0.1, ATTACK[1]))
        self.assertIs(navigator.path, first_path)
        navigator.update_goal(HOME, (ATTACK[0] + 0.5, ATTACK[1]))
        self.assertIsNot(navigator.path, first_path)

    def test_planning_clearance_prevents_corner_stall(self) -> None:
        navigator = AStarNavigator(self.grid)
        navigator.update_goal(HOME, ATTACK)
        position = HOME

        for _ in range(2000):
            waypoint = navigator.next_waypoint(position)
            if waypoint is None:
                break
            delta_x = waypoint[0] - position[0]
            delta_y = waypoint[1] - position[1]
            distance = math.hypot(delta_x, delta_y)
            travel = min(0.10, distance)
            proposed = (
                position[0] + delta_x / distance * travel,
                position[1] + delta_y / distance * travel,
            )
            moved = self.collision_grid.move_with_collision(position, proposed)
            self.assertGreater(
                math.hypot(moved[0] - position[0], moved[1] - position[1]),
                1e-8,
                f"navigation stalled near {position} while turning toward {waypoint}",
            )
            position = moved
        else:
            self.fail("navigation did not finish within the step limit")

        self.assertLess(math.hypot(position[0] - ATTACK[0], position[1] - ATTACK[1]), 0.15)


if __name__ == "__main__":
    unittest.main()
