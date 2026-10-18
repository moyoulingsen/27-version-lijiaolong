"""Coordinate regressions for the canonical 28 x 15 field layout."""

from __future__ import annotations

import unittest
import sqlite3
from pathlib import Path
import statistics

from rm2026_sim.field_geometry import (
    BLUE_START_POSITIONS,
    BLUE_OUTPOST,
    BLUE_FLY_SLOPE_POLYGON,
    BLUE_SUPPLY_POLYGON,
    BLUE_TRAPEZOID_HIGHLAND_POLYGON,
    CENTRAL_HIGHLAND_POLYGON,
    FIELD_HEIGHT,
    FIELD_WIDTH,
    RED_OUTPOST,
    RED_HOME,
    RED_START_POSITIONS,
    RED_FLY_SLOPE_POLYGON,
    RED_SUPPLY_POLYGON,
    RED_TRAPEZOID_HIGHLAND_POLYGON,
    RUNE_POSITIONS,
)
from rm2026_sim.field_rules import FIELD_ZONES


class FieldGeometryTests(unittest.TestCase):
    @staticmethod
    def _dataset_connection() -> sqlite3.Connection:
        path = Path(__file__).resolve().parents[3] / "data" / "rmuc_2026_region_dataset.sqlite"
        if not path.is_file():
            raise unittest.SkipTest(f"dataset not found: {path}")
        return sqlite3.connect(path)

    def test_functional_zones_use_dataset_field_bounds(self) -> None:
        for zone in FIELD_ZONES:
            self.assertLessEqual(0.0, zone.min_x, zone.name)
            self.assertLess(zone.min_x, zone.max_x, zone.name)
            self.assertLessEqual(zone.max_x, FIELD_WIDTH, zone.name)
            self.assertLessEqual(0.0, zone.min_y, zone.name)
            self.assertLess(zone.min_y, zone.max_y, zone.name)
            self.assertLessEqual(zone.max_y, FIELD_HEIGHT, zone.name)

    def test_dataset_robot_start_positions_share_the_field_frame(self) -> None:
        for positions in (RED_START_POSITIONS, BLUE_START_POSITIONS):
            self.assertEqual(set(positions), {1, 2, 3, 4, 5, 8})
            for x, y in positions.values():
                self.assertTrue(0.0 <= x <= FIELD_WIDTH)
                self.assertTrue(0.0 <= y <= FIELD_HEIGHT)
        self.assertLess(
            ((RED_HOME[0] - RED_START_POSITIONS[8][0]) ** 2
             + (RED_HOME[1] - RED_START_POSITIONS[8][1]) ** 2) ** 0.5,
            0.2,
        )

    def test_robot_starts_match_three_region_dataset_medians(self) -> None:
        connection = self._dataset_connection()
        try:
            rows = connection.execute(
                """
                SELECT 赛区, 阵营, robot_id, avg(x), avg(y)
                FROM timeseries
                WHERE 时刻秒 BETWEEN 0 AND 2
                  AND robot_id IN (1, 2, 3, 4, 6, 7, 101, 102, 103, 104, 106, 107)
                  AND 机器人类型 NOT IN ('基地', '前哨站')
                  AND x BETWEEN 0 AND 28 AND y BETWEEN 0 AND 15
                GROUP BY 赛区, 阵营, robot_id
                """
            ).fetchall()
        finally:
            connection.close()

        expected_ids = {
            "red": {1: 1, 2: 2, 3: 3, 4: 4, 5: 6, 8: 7},
            "blue": {1: 101, 2: 102, 3: 103, 4: 104, 5: 106, 8: 107},
        }
        for team, side in (("red", "红"), ("blue", "蓝")):
            positions = RED_START_POSITIONS if team == "red" else BLUE_START_POSITIONS
            for local_id, dataset_id in expected_ids[team].items():
                regional = [
                    (x, y)
                    for _, row_side, robot_id, x, y in rows
                    if row_side == side and robot_id == dataset_id
                ]
                self.assertEqual(len(regional), 3)
                median = (
                    round(statistics.median(x for x, _ in regional), 3),
                    round(statistics.median(y for _, y in regional), 3),
                )
                self.assertEqual(positions[local_id], median)

    def test_dataset_observed_functional_anchors_are_inside_zones(self) -> None:
        zones = {zone.name: zone for zone in FIELD_ZONES}
        self.assertTrue(zones["red_assembly"].contains(13.1, 8.4))
        self.assertTrue(zones["blue_assembly"].contains(15.0, 6.8))
        self.assertTrue(zones["red_road"].contains(8.2615, 2.5615))
        self.assertTrue(zones["blue_road"].contains(19.8375, 12.584))
        self.assertTrue(zones["red_fly_slope"].contains(15.0, 0.5))
        self.assertTrue(zones["blue_fly_slope"].contains(13.5, 14.5))

    def test_road_zones_are_narrow_symmetrical_event_regions(self) -> None:
        zones = {zone.name: zone for zone in FIELD_ZONES}
        red = zones["red_road"]
        blue = zones["blue_road"]
        self.assertFalse(red.contains(7.6, 3.9))
        self.assertFalse(blue.contains(20.4, 11.1))
        self.assertAlmostEqual(red.min_x, FIELD_WIDTH - blue.max_x)
        self.assertAlmostEqual(red.max_x, FIELD_WIDTH - blue.min_x)
        self.assertAlmostEqual(red.min_y, FIELD_HEIGHT - blue.max_y)
        self.assertAlmostEqual(red.max_y, FIELD_HEIGHT - blue.min_y)

    def test_fort_zones_match_the_hexagonal_field_modules(self) -> None:
        zones = {zone.name: zone for zone in FIELD_ZONES}
        red = zones["red_fort"]
        blue = zones["blue_fort"]

        self.assertEqual(len(red.polygon), 6)
        self.assertEqual(len(blue.polygon), 6)
        self.assertTrue(red.contains(6.6, 7.5))
        self.assertTrue(blue.contains(21.4, 7.5))
        self.assertFalse(red.contains(5.15, 9.55))
        self.assertFalse(red.contains(5.35, 8.42))
        self.assertEqual(
            {(round(FIELD_WIDTH - x, 2), y) for x, y in red.polygon},
            {(round(x, 2), y) for x, y in blue.polygon},
        )

    def test_outposts_are_mirrored_at_the_rulebook_positions(self) -> None:
        self.assertEqual(RED_OUTPOST, (8.7, 7.5))
        self.assertEqual(BLUE_OUTPOST, (19.3, 7.5))
        self.assertAlmostEqual(RED_OUTPOST[0] + BLUE_OUTPOST[0], FIELD_WIDTH)

    def test_functional_zone_anchors_contain_sqlite_event_medians(self) -> None:
        connection = self._dataset_connection()
        try:
            assembly = connection.execute(
                """
                SELECT e.阵营, t.x, t.y
                FROM events e
                JOIN timeseries t
                  ON t.game_id=e.game_id AND t.时刻秒=e.时刻秒
                 AND t.阵营=e.阵营 AND t.机器人类型='工程'
                WHERE e.事件类型='装配成功'
                  AND t.x BETWEEN 0 AND 28 AND t.y BETWEEN 0 AND 15
                """
            ).fetchall()
            gains = connection.execute(
                """
                SELECT e.类别, e.阵营, t.x, t.y
                FROM events e
                JOIN timeseries t
                  ON t.game_id=e.game_id AND t.时刻秒=e.时刻秒
                 AND t.robot_id=e.robot_id AND t.阵营=e.阵营
                WHERE e.事件类型='增益'
                  AND e.类别 IN ('台阶跨越', '飞坡')
                  AND t.x BETWEEN 0 AND 28 AND t.y BETWEEN 0 AND 15
                """
            ).fetchall()
        finally:
            connection.close()

        zones = {zone.name: zone for zone in FIELD_ZONES}
        anchors = (
            (zones["red_assembly"], [(x, y) for side, x, y in assembly if side == "红"]),
            (zones["blue_assembly"], [(x, y) for side, x, y in assembly if side == "蓝"]),
            (zones["red_road"], [(x, y) for kind, side, x, y in gains if kind == "台阶跨越" and side == "红"]),
            (zones["blue_road"], [(x, y) for kind, side, x, y in gains if kind == "台阶跨越" and side == "蓝"]),
            (zones["red_fly_slope"], [(x, y) for kind, side, x, y in gains if kind == "飞坡" and side == "红"]),
            (zones["blue_fly_slope"], [(x, y) for kind, side, x, y in gains if kind == "飞坡" and side == "蓝"]),
        )
        for zone, positions in anchors:
            self.assertTrue(positions, zone.name)
            median = (
                statistics.median(x for x, _ in positions),
                statistics.median(y for _, y in positions),
            )
            self.assertTrue(zone.contains(*median), (zone.name, median))

    def test_energy_mechanism_is_centered_on_the_central_highland(self) -> None:
        red_x, red_y = RUNE_POSITIONS["red"]
        blue_x, blue_y = RUNE_POSITIONS["blue"]
        self.assertAlmostEqual((red_x + blue_x) / 2.0, FIELD_WIDTH / 2.0)
        self.assertAlmostEqual((red_y + blue_y) / 2.0, FIELD_HEIGHT / 2.0)
        central = next(zone for zone in FIELD_ZONES if zone.name == "central_highland")
        self.assertTrue(central.contains(red_x, red_y))
        self.assertTrue(central.contains(blue_x, blue_y))

    def test_supply_and_central_highland_follow_vector_polygons(self) -> None:
        zones = {zone.name: zone for zone in FIELD_ZONES}
        red_supply = zones["red_supply"]
        blue_supply = zones["blue_supply"]
        central = zones["central_highland"]

        self.assertEqual(red_supply.polygon, RED_SUPPLY_POLYGON)
        self.assertEqual(blue_supply.polygon, BLUE_SUPPLY_POLYGON)
        self.assertEqual(len(red_supply.polygon), 6)
        self.assertTrue(red_supply.contains(2.10, 1.30))
        self.assertFalse(red_supply.contains(1.20, 1.30))
        self.assertFalse(red_supply.contains(4.10, 2.00))
        self.assertEqual(
            {(round(FIELD_WIDTH - x, 3), round(FIELD_HEIGHT - y, 3)) for x, y in red_supply.polygon},
            {(round(x, 3), round(y, 3)) for x, y in blue_supply.polygon},
        )

        self.assertEqual(central.polygon, CENTRAL_HIGHLAND_POLYGON)
        self.assertGreaterEqual(len(central.polygon), 12)
        self.assertTrue(central.contains(14.0, 7.5))
        self.assertTrue(central.contains(13.5, 12.0))
        self.assertFalse(central.contains(14.0, 1.80))
        self.assertFalse(central.contains(20.0, 8.0))

        blue_trapezoid = zones["blue_trapezoid"]
        red_trapezoid = zones["red_trapezoid"]
        self.assertEqual(blue_trapezoid.polygon, BLUE_TRAPEZOID_HIGHLAND_POLYGON)
        self.assertEqual(red_trapezoid.polygon, RED_TRAPEZOID_HIGHLAND_POLYGON)
        self.assertEqual(len(blue_trapezoid.polygon), 9)
        self.assertTrue(blue_trapezoid.contains(22.0, 4.0))
        self.assertTrue(blue_trapezoid.contains(23.8, 2.0))
        self.assertFalse(blue_trapezoid.contains(17.0, 2.0))
        self.assertFalse(blue_trapezoid.contains(23.0, 4.5))
        self.assertEqual(
            {
                (round(FIELD_WIDTH - x, 3), round(FIELD_HEIGHT - y, 3))
                for x, y in blue_trapezoid.polygon
            },
            {(round(x, 3), round(y, 3)) for x, y in red_trapezoid.polygon},
        )

        red_fly = zones["red_fly_slope"]
        blue_fly = zones["blue_fly_slope"]
        self.assertEqual(red_fly.polygon, RED_FLY_SLOPE_POLYGON)
        self.assertEqual(blue_fly.polygon, BLUE_FLY_SLOPE_POLYGON)
        self.assertEqual(len(red_fly.polygon), 4)
        self.assertTrue(red_fly.contains(15.0, 0.5))
        self.assertTrue(blue_fly.contains(13.5, 14.5))
        self.assertFalse(red_fly.contains(9.5, 1.0))
        self.assertFalse(blue_fly.contains(18.5, 14.0))


if __name__ == "__main__":
    unittest.main()
