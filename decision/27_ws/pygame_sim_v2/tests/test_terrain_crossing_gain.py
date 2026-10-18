"""Rule 5.5.3.5 terrain-crossing gain regression tests."""

from __future__ import annotations

import unittest

from rm2026_sim.app import SimulatorApp
from rm2026_sim.core import SentryState
from rm2026_sim.scenario_store import capture_snapshot, restore_snapshot
from rm2026_sim.task_state import TaskScenario


def square(x: float, y: float, radius: float = 0.12) -> list[list[float]]:
    return [
        [x - radius, y - radius],
        [x + radius, y - radius],
        [x + radius, y + radius],
        [x - radius, y + radius],
    ]


def card(
    identifier: str,
    kind: str,
    field_team: str,
    route: int,
    order: int,
    x: float,
    y: float,
) -> dict:
    return {
        "id": identifier,
        "kind": kind,
        "field_team": field_team,
        "route": route,
        "order": order,
        "points": square(x, y),
    }


class TerrainCrossingGainTests(unittest.TestCase):
    def scenario(self, cards: list[dict]) -> TaskScenario:
        scenario = TaskScenario(defence_buff=0)
        scenario.set_terrain_crossing_cards(cards)
        return scenario

    def move_red(
        self,
        scenario: TaskScenario,
        target_id: int,
        position: tuple[float, float],
        elapsed: float,
        sentry: SentryState,
    ) -> None:
        if target_id == 8:
            sentry.x, sentry.y = position
        else:
            scenario.set_robot_position(target_id, position, team="red")
        scenario.update(elapsed, sentry)

    def test_map_editor_polygons_are_grouped_into_ordered_routes(self) -> None:
        app = SimulatorApp.__new__(SimulatorApp)
        app.task = TaskScenario()
        app.map_zone_overrides = {"region_03_tunnel": square(2.0, 2.0)}
        app.custom_map_polygons = [
            {
                "id": f"tunnel-{index}",
                "kind": "region_03_tunnel",
                "name": f"红方隧道卡 {index}",
                "points": square(2.0 + index, 2.0),
            }
            for index in range(1, 6)
        ]
        app._sync_task_zone_overrides()
        cards = app.task.terrain_crossing_cards
        self.assertEqual(len(cards), 6)
        self.assertEqual(
            [(item["route"], item["order"]) for item in cards],
            [(0, 0), (0, 1), (0, 2), (1, 0), (1, 1), (1, 2)],
        )

    def test_road_requires_low_then_high_and_has_robot_local_cooldown(self) -> None:
        cards = [
            card("road-low", "road", "red", 0, 0, 5.0, 5.0),
            card("road-high", "road", "red", 0, 1, 7.0, 5.0),
        ]
        scenario = self.scenario(cards)
        sentry = SentryState()
        self.move_red(scenario, 2, (5.0, 5.0), 0.0, sentry)
        self.move_red(scenario, 2, (7.0, 5.0), 0.1, sentry)

        self.assertEqual(scenario.terrain_crossing_defence(2, team="red"), 0.25)
        self.assertAlmostEqual(scenario.terrain_standard_remaining["red"][2], 5.0)
        self.assertAlmostEqual(scenario.terrain_road_cooldown["red"][2], 15.0)

        self.move_red(scenario, 2, (5.0, 5.0), 0.1, sentry)
        remaining = scenario.terrain_standard_remaining["red"][2]
        self.move_red(scenario, 2, (7.0, 5.0), 0.1, sentry)
        self.assertLess(scenario.terrain_standard_remaining["red"][2], remaining)
        self.assertEqual(scenario.terrain_crossing_defence(2, team="red"), 0.25)

    def test_crossing_two_cards_in_one_tick_and_both_teams_are_independent(self) -> None:
        cards = [
            card("road-low", "road", "red", 0, 0, 5.0, 4.0),
            card("road-high", "road", "red", 0, 1, 7.0, 4.0),
        ]
        scenario = self.scenario(cards)
        sentry = SentryState(x=4.0, y=4.0)
        scenario.set_robot_position(3, (4.0, 4.0), team="blue")
        scenario.update(0.0, sentry)
        sentry.x = 8.0
        scenario.set_robot_position(3, (8.0, 4.0), team="blue")
        scenario.update(0.2, sentry)

        self.assertEqual(scenario.terrain_crossing_defence(8, team="red"), 0.25)
        self.assertEqual(scenario.terrain_crossing_defence(3, team="blue"), 0.25)

    def test_one_long_movement_tick_still_obeys_the_sequence_window(self) -> None:
        cards = [
            card("road-low", "road", "red", 0, 0, 5.0, 6.0),
            card("road-high", "road", "red", 0, 1, 7.0, 6.0),
        ]
        scenario = self.scenario(cards)
        sentry = SentryState()
        scenario.set_robot_position(2, (4.0, 6.0), team="red")
        scenario.update(0.0, sentry)
        scenario.set_robot_position(2, (8.0, 6.0), team="red")
        scenario.update(10.0, sentry)
        self.assertEqual(scenario.terrain_crossing_defence(2, team="red"), 0.0)

    def test_order_timeout_and_other_card_interrupt_sequence(self) -> None:
        cards = [
            card("hill-low", "highland", "red", 0, 0, 5.0, 8.0),
            card("hill-high", "highland", "red", 0, 1, 7.0, 8.0),
            card("fly-a", "fly_slope", "red", 0, 0, 6.0, 9.0),
            card("fly-b", "fly_slope", "red", 0, 1, 8.0, 9.0),
        ]
        scenario = self.scenario(cards)
        sentry = SentryState()

        self.move_red(scenario, 1, (7.0, 8.0), 0.0, sentry)
        self.assertEqual(scenario.terrain_sequence_cards["red"][1], [])
        self.move_red(scenario, 1, (5.0, 8.0), 0.1, sentry)
        self.move_red(scenario, 1, (5.0, 7.0), 5.1, sentry)
        self.move_red(scenario, 1, (7.0, 8.0), 0.1, sentry)
        self.assertEqual(scenario.terrain_crossing_defence(1, team="red"), 0.0)

        self.move_red(scenario, 1, (5.0, 8.0), 0.1, sentry)
        self.move_red(scenario, 1, (6.0, 9.0), 0.1, sentry)
        self.move_red(scenario, 1, (7.0, 8.0), 0.1, sentry)
        self.assertEqual(scenario.terrain_crossing_defence(1, team="red"), 0.0)

    def test_fly_then_road_upgrades_shared_defence_and_keeps_longer_time(self) -> None:
        cards = [
            card("fly-a", "fly_slope", "red", 0, 0, 3.0, 11.0),
            card("fly-b", "fly_slope", "red", 0, 1, 5.0, 11.0),
            card("road-low", "road", "red", 0, 0, 8.0, 11.0),
            card("road-high", "road", "red", 0, 1, 10.0, 11.0),
        ]
        scenario = self.scenario(cards)
        sentry = SentryState()
        self.move_red(scenario, 4, (3.0, 11.0), 0.0, sentry)
        self.move_red(scenario, 4, (5.0, 11.0), 0.1, sentry)
        self.assertEqual(scenario.terrain_crossing_defence(4, team="red"), 0.25)

        self.move_red(scenario, 4, (8.0, 11.0), 0.1, sentry)
        self.move_red(scenario, 4, (10.0, 11.0), 0.1, sentry)
        self.assertEqual(scenario.terrain_crossing_defence(4, team="red"), 0.50)
        self.assertGreater(scenario.terrain_standard_remaining["red"][4], 29.0)

    def test_tunnel_requires_end_middle_other_end_and_splits_durations(self) -> None:
        cards = [
            card("tunnel-a", "tunnel", "blue", 0, 0, 20.0, 5.0),
            card("tunnel-mid", "tunnel", "blue", 0, 1, 21.0, 5.0),
            card("tunnel-b", "tunnel", "blue", 0, 2, 22.0, 5.0),
        ]
        scenario = self.scenario(cards)
        sentry = SentryState()
        scenario.set_robot_position(1, (22.0, 5.0), team="blue")
        scenario.update(0.0, sentry)
        scenario.set_robot_position(1, (21.0, 5.0), team="blue")
        scenario.update(0.1, sentry)
        scenario.set_robot_position(1, (20.0, 5.0), team="blue")
        scenario.update(0.1, sentry)

        self.assertEqual(scenario.terrain_crossing_defence(1, team="blue"), 0.50)
        self.assertEqual(scenario.terrain_crossing_cooling(1, team="blue"), 2.0)
        self.assertEqual(scenario.robot_heat_cooling_rate(1, team="blue"), 40.0)

        scenario.set_robot_position(1, (19.0, 6.0), team="blue")
        scenario.update(10.1, sentry)
        self.assertEqual(scenario.terrain_crossing_defence(1, team="blue"), 0.0)
        self.assertEqual(scenario.terrain_crossing_cooling(1, team="blue"), 2.0)

    def test_death_clears_gains_and_snapshot_restores_progress(self) -> None:
        cards = [
            card("hill-low", "highland", "red", 0, 0, 4.0, 3.0),
            card("hill-high", "highland", "red", 0, 1, 6.0, 3.0),
        ]
        scenario = self.scenario(cards)
        sentry = SentryState()
        self.move_red(scenario, 3, (4.0, 3.0), 0.0, sentry)
        snapshot = capture_snapshot("terrain", scenario, sentry, None)
        restored, restored_sentry, _ = restore_snapshot(snapshot)
        self.assertEqual(restored.terrain_sequence_cards["red"][3], ["hill-low"])

        self.move_red(restored, 3, (6.0, 3.0), 0.1, restored_sentry)
        self.assertEqual(restored.terrain_crossing_defence(3, team="red"), 0.25)
        restored._mark_robot_death(3, team="red")
        self.assertEqual(restored.terrain_crossing_defence(3, team="red"), 0.0)
        self.assertEqual(restored.terrain_crossing_cooling(3, team="red"), 1.0)


if __name__ == "__main__":
    unittest.main()
