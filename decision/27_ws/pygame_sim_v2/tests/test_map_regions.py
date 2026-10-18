from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace

from rm2026_sim.app import SimulatorApp
from rm2026_sim.core import SentryState
from rm2026_sim.field_rules import REGION_DEFINITIONS, REGION_TYPES
from rm2026_sim.map_regions import (
    geometry_payload,
    load_geometry_file,
    normalize_points,
    polygon_area,
    restore_geometry_payload,
    save_geometry_file,
    validate_polygon,
)
from rm2026_sim.task_state import TaskScenario


class MapRegionGeometryTests(unittest.TestCase):
    def test_side_specific_gain_points_have_red_and_blue_slots(self) -> None:
        slots = dict(REGION_TYPES)
        for family in (
            "supply",
            "trapezoid_highland",
            "base",
            "fort",
            "outpost",
            "assembly",
        ):
            matching = [
                identifier
                for identifier, _ in REGION_TYPES
                if f"_{family}_" in identifier
            ]
            self.assertEqual(len(matching), 2)
            self.assertTrue(any("红方" in slots[identifier] for identifier in matching))
            self.assertTrue(any("蓝方" in slots[identifier] for identifier in matching))
        definitions = {definition.name: definition for definition in REGION_DEFINITIONS}
        self.assertEqual(definitions["region_01_supply_red"].team, "red")
        self.assertEqual(definitions["region_01_supply_blue"].team, "blue")

    def test_polygon_validation_requires_three_non_collinear_points(self) -> None:
        self.assertEqual(validate_polygon(((1.0, 1.0), (2.0, 2.0))), "至少需要 3 个点")
        self.assertEqual(
            validate_polygon(((1.0, 1.0), (2.0, 2.0), (3.0, 3.0))),
            "点不能共线",
        )
        polygon = ((1.0, 1.0), (4.0, 1.0), (4.0, 4.0), (1.0, 4.0))
        self.assertIsNone(validate_polygon(polygon))
        self.assertAlmostEqual(abs(polygon_area(polygon)), 9.0)

    def test_annotation_polygon_does_not_activate_area_attributes(self) -> None:
        replacement = [[10.0, 10.0], [12.0, 10.0], [12.0, 12.0], [10.0, 12.0]]
        scenario = TaskScenario(
            field_zone_overrides={"region_11_central_highland": replacement}
        )
        scenario.update(0.1, SentryState(x=11.0, y=11.0))
        self.assertEqual(scenario.active_buffs, [])
        self.assertFalse(
            scenario.exchange_17mm(
                remote=False,
                sentry=SentryState(x=11.0, y=11.0),
            )
        )
        scenario.reset_match_time()
        self.assertEqual(
            scenario.field_zone_overrides["region_11_central_highland"],
            replacement,
        )

    def test_multiple_custom_polygons_round_trip_as_json(self) -> None:
        payload = geometry_payload(
            {"region_11_central_highland": ((1.0, 1.0), (2.0, 1.0), (2.0, 2.0))},
            [
                {
                    "id": "custom_1",
                    "name": "测试区域 1",
                    "points": [[3.0, 3.0], [4.0, 3.0], [4.0, 4.0]],
                    "color": [230, 160, 70],
                    "visible": True,
                },
                {
                    "id": "custom_2",
                    "name": "测试区域 2",
                    "points": [[5.0, 5.0], [6.0, 5.0], [6.0, 6.0]],
                    "color": [70, 160, 230],
                    "visible": False,
                },
            ],
        )
        restored_overrides, restored_custom = restore_geometry_payload(
            json.loads(json.dumps(payload, ensure_ascii=False))
        )
        self.assertEqual(restored_overrides["region_11_central_highland"], ((1.0, 1.0), (2.0, 1.0), (2.0, 2.0)))
        self.assertEqual([item["id"] for item in restored_custom], ["custom_1", "custom_2"])
        self.assertEqual(restored_custom[1]["visible"], False)
        self.assertEqual(normalize_points([[30.0, -1.0]]), ((28.0, 0.0),))

    def test_delete_custom_polygon_removes_every_polygon_of_the_same_type(self) -> None:
        messages: list[str] = []
        app = SimulatorApp.__new__(SimulatorApp)
        app.task = SimpleNamespace(
            field_zone_overrides={},
            notify=messages.append,
        )
        app.map_zone_overrides = {
            "region_01_supply_red": ((1.0, 1.0), (2.0, 1.0), (2.0, 2.0)),
            "region_01_supply_blue": ((20.0, 1.0), (21.0, 1.0), (21.0, 2.0)),
        }
        app.custom_map_polygons = [
            {"id": "custom_1", "kind": "region_01_supply_red"},
            {"id": "custom_2", "kind": "region_01_supply_red"},
            {"id": "custom_3", "kind": "region_01_supply_blue"},
        ]
        app.map_layer_visibility = {
            "zone:region_01_supply_red": True,
            "zone:region_01_supply_blue": True,
            "custom:custom_1": True,
            "custom:custom_2": True,
            "custom:custom_3": True,
        }
        app.region_edit_target = None
        app.region_edit_custom_id = None

        app._delete_region(("custom", "custom_1"))

        self.assertEqual(app.map_zone_overrides["region_01_supply_red"], ())
        self.assertEqual(
            [item["id"] for item in app.custom_map_polygons], ["custom_3"]
        )
        self.assertTrue(app.map_zone_overrides["region_01_supply_blue"])
        self.assertEqual(app.task.field_zone_overrides["region_01_supply_red"], [])
        self.assertTrue(messages)

    def test_extra_polygon_can_replace_a_deleted_empty_slot(self) -> None:
        app = SimulatorApp.__new__(SimulatorApp)
        app.map_zone_overrides = {"region_01_supply_red": ()}
        app.custom_map_polygons = [
            {
                "id": "custom_1",
                "kind": "region_01_supply_red",
                "points": [[1.0, 1.0], [2.0, 1.0], [2.0, 2.0]],
            }
        ]

        self.assertTrue(app._region_type_configured("region_01_supply_red"))
        self.assertEqual(app._missing_required_regions(), [])

    def test_permanent_geometry_file_round_trip(self) -> None:
        overrides = {
            "region_11_central_highland": ((10.0, 10.0), (12.0, 10.0), (12.0, 12.0))
        }
        custom = [
            {
                "id": "custom_7",
                "kind": "region_01_supply_blue",
                "name": "补给区增益点（蓝方） 2",
                "points": [[20.0, 10.0], [22.0, 10.0], [22.0, 12.0]],
                "color": [45, 130, 220],
                "visible": True,
            }
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "map_regions.json"
            save_geometry_file(path, overrides, custom)
            restored_overrides, restored_custom = load_geometry_file(path)

        self.assertEqual(restored_overrides, overrides)
        self.assertEqual(restored_custom[0]["id"], "custom_7")
        self.assertEqual(restored_custom[0]["kind"], "region_01_supply_blue")
        self.assertTrue(restored_custom[0]["visible"])


if __name__ == "__main__":
    unittest.main()
