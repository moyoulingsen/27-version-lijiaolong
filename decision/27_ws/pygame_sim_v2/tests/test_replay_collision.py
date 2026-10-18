from __future__ import annotations

from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from rm2026_sim.app import SimulatorApp
from rm2026_sim.core import Arena
from rm2026_sim.task_state import TaskScenario


class ReplayCollisionIsolationTests(unittest.TestCase):
    def test_sentry_replay_does_not_enter_collision_motion(self) -> None:
        app = SimulatorApp.__new__(SimulatorApp)
        app.replay_mode = True
        app.sentry = SimpleNamespace(
            x=2.809,
            y=6.435,
            manual_control=True,
            update=Mock(),
        )
        app.task = SimpleNamespace(sentry_chassis_power_cut=False)
        app._refresh_dynamic_planning_grid = Mock()
        app._collision_bodies = Mock(return_value=())
        app._check_robot_collision = Mock()
        app._manual_fire_held = False
        app.navigator = SimpleNamespace(clear=Mock())
        app.collision_grid = SimpleNamespace(
            move_with_collision=Mock(side_effect=AssertionError("replay used collision"))
        )

        app._update_sentry_motion(
            1.0,
            1.0,
            0.0,
            SimpleNamespace(spin_mode=0, tripod_mode=0),
        )

        app.sentry.update.assert_not_called()
        app.collision_grid.move_with_collision.assert_not_called()
        app._refresh_dynamic_planning_grid.assert_not_called()

    def test_controlled_robot_replay_preserves_dataset_position(self) -> None:
        app = SimulatorApp.__new__(SimulatorApp)
        app.replay_mode = True
        app.arena = Arena()
        app.task = TaskScenario()
        dataset_position = (2.809, 6.435)
        app.task.own_robot_positions[1] = list(dataset_position)
        app.controlled_robot_id = 1
        app.controlled_robot_team = "red"
        app._collision_bodies = Mock(return_value=())
        app._check_robot_collision = Mock()
        app.collision_grid = SimpleNamespace(
            move_with_collision=Mock(side_effect=AssertionError("replay used collision"))
        )

        app._move_controlled_robot(1.0, 0.0, 1.0)

        self.assertEqual(app.task.own_robot_position(1), dataset_position)
        app.collision_grid.move_with_collision.assert_not_called()
        app._collision_bodies.assert_not_called()


if __name__ == "__main__":
    unittest.main()
