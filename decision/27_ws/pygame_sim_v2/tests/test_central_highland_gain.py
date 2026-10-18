"""Rule 5.5.3.3 central-highland gain regression tests."""

from __future__ import annotations

import unittest

from rm2026_sim.app import SimulatorApp
from rm2026_sim.core import SentryState
from rm2026_sim.scenario_store import capture_snapshot, restore_snapshot
from rm2026_sim.task_state import CENTRAL_HIGHLAND_DEFENCE, TaskScenario


def square(x: float, y: float, radius: float = 0.5) -> list[list[float]]:
    return [
        [x - radius, y - radius],
        [x + radius, y - radius],
        [x + radius, y + radius],
        [x - radius, y + radius],
    ]


ZONE_A = {"id": "central-a", "points": square(12.0, 5.0)}
ZONE_B = {"id": "central-b", "points": square(16.0, 10.0)}


class CentralHighlandGainTests(unittest.TestCase):
    def scenario(self) -> TaskScenario:
        scenario = TaskScenario(defence_buff=0)
        scenario.set_central_highland_zones([ZONE_A, ZONE_B])
        return scenario

    def test_hero_infantry_and_sentry_share_point_but_engineer_cannot(self) -> None:
        scenario = self.scenario()
        sentry = SentryState(x=12.0, y=5.0)
        scenario.set_robot_position(1, (12.0, 5.0), team="red")
        scenario.set_robot_position(2, (12.0, 5.0), team="red")
        scenario.set_robot_position(3, (12.2, 5.0), team="red")
        scenario.update(0.1, sentry)

        self.assertEqual(scenario.central_highland_owners["central-a"], "red")
        self.assertEqual(scenario.central_highland_occupants["red"], [1, 3, 8])
        self.assertNotIn(2, scenario.central_highland_occupants["red"])
        self.assertEqual(
            scenario.robot_effective_defence(1, team="red"),
            CENTRAL_HIGHLAND_DEFENCE,
        )
        self.assertEqual(scenario.effective_sentry_defence, CENTRAL_HIGHLAND_DEFENCE)
        self.assertEqual(scenario.robot_effective_defence(2, team="red"), 0.0)

    def test_each_disconnected_point_has_independent_exclusive_owner(self) -> None:
        scenario = self.scenario()
        sentry = SentryState(x=1.0, y=1.0)
        scenario.set_robot_position(1, (12.0, 5.0), team="red")
        scenario.update(0.1, sentry)

        scenario.set_robot_position(1, (12.1, 5.0), team="blue")
        scenario.set_robot_position(3, (16.0, 10.0), team="blue")
        scenario.update(0.1, sentry)

        self.assertEqual(scenario.central_highland_owners["central-a"], "red")
        self.assertEqual(scenario.central_highland_owners["central-b"], "blue")
        self.assertIn(1, scenario.central_highland_occupants["red"])
        self.assertNotIn(1, scenario.central_highland_occupants["blue"])
        self.assertIn(3, scenario.central_highland_occupants["blue"])
        self.assertEqual(scenario.robot_effective_defence(1, team="blue"), 0.0)

    def test_exit_keeps_ownership_two_seconds_then_waiting_team_takes_over(self) -> None:
        scenario = self.scenario()
        sentry = SentryState(x=1.0, y=1.0)
        scenario.set_robot_position(1, (12.0, 5.0), team="red")
        scenario.update(0.1, sentry)

        scenario.set_robot_position(1, (2.0, 2.0), team="red")
        scenario.set_robot_position(1, (12.0, 5.0), team="blue")
        scenario.update(1.9, sentry)
        self.assertEqual(scenario.central_highland_owners["central-a"], "red")
        self.assertIn(1, scenario.central_highland_occupants["red"])
        self.assertNotIn(1, scenario.central_highland_occupants["blue"])

        scenario.update(0.2, sentry)
        self.assertEqual(scenario.central_highland_owners["central-a"], "blue")
        self.assertNotIn(1, scenario.central_highland_occupants["red"])
        self.assertIn(1, scenario.central_highland_occupants["blue"])

    def test_death_clears_occupation_immediately(self) -> None:
        scenario = self.scenario()
        sentry = SentryState(x=1.0, y=1.0)
        scenario.set_robot_position(3, (12.0, 5.0), team="red")
        scenario.update(0.1, sentry)
        self.assertIn(3, scenario.central_highland_occupants["red"])

        scenario._mark_robot_death(3, team="red")
        self.assertNotIn(3, scenario.central_highland_occupants["red"])
        self.assertNotIn("central-a", scenario.central_highland_owners)
        self.assertEqual(scenario.robot_effective_defence(3, team="red"), 0.0)

    def test_snapshot_restores_owners_occupants_and_exit_grace(self) -> None:
        scenario = self.scenario()
        sentry = SentryState(x=1.0, y=1.0)
        scenario.set_robot_position(4, (16.0, 10.0), team="blue")
        scenario.update(0.1, sentry)
        scenario.set_robot_position(4, (20.0, 10.0), team="blue")
        scenario.update(0.5, sentry)

        restored, _, _ = restore_snapshot(
            capture_snapshot("central-highland", scenario, sentry, None)
        )
        self.assertEqual(restored.central_highland_owners["central-b"], "blue")
        self.assertIn(4, restored.central_highland_occupants["blue"])
        self.assertGreater(
            restored.central_highland_exit_grace["central-b"]["blue"][4], 1.0
        )

    def test_map_editor_pairs_lower_and_upper_highland_cards_by_route(self) -> None:
        app = SimulatorApp.__new__(SimulatorApp)
        app.task = TaskScenario()
        app.map_zone_overrides = {
            "region_08_highland": square(10.0, 4.0),
            "region_11_central_highland": square(12.0, 4.0),
        }
        app.custom_map_polygons = [
            {
                "id": "low-2",
                "kind": "region_08_highland",
                "name": "红方高地低处 2",
                "points": square(10.0, 8.0),
            },
            {
                "id": "high-2",
                "kind": "region_11_central_highland",
                "name": "红方中央高地 2",
                "points": square(12.0, 8.0),
            },
        ]
        app._sync_task_zone_overrides()

        highland_cards = [
            item
            for item in app.task.terrain_crossing_cards
            if item["kind"] == "highland"
        ]
        self.assertEqual(
            [(item["route"], item["order"]) for item in highland_cards],
            [(0, 0), (1, 0), (0, 1), (1, 1)],
        )
        self.assertEqual(len(app.task.central_highland_zones), 2)


if __name__ == "__main__":
    unittest.main()
