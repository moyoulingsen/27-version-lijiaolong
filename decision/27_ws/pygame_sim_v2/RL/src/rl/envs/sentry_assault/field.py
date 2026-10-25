"""Shared static field assets; no path planner is defined here."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from rm2026_sim.core import Arena
from rm2026_sim.field_geometry import AGGRESSIVE_PATROL_POINTS
from rm2026_sim.map_asset import load_p5_pgm
from rm2026_sim.map_regions import load_geometry_file, load_patrol_routes_file
from rm2026_sim.navigation import OccupancyGrid
from rl import PROJECT_ROOT


MAP_PATH = PROJECT_ROOT / "assets" / "rmuc2026.pgm"
GEOMETRY_PATH = PROJECT_ROOT / "map_regions.json"


@dataclass(frozen=True, slots=True)
class AssaultField:
    arena: Arena
    collision_grid: OccupancyGrid
    zone_overrides: Mapping[str, tuple[tuple[float, float], ...]]
    patrol_routes: Mapping[str, tuple[tuple[float, float], ...]]

    @classmethod
    def load(cls) -> "AssaultField":
        arena = Arena()
        image = load_p5_pgm(MAP_PATH)
        zones, _ = load_geometry_file(GEOMETRY_PATH)
        routes = load_patrol_routes_file(
            GEOMETRY_PATH,
            {
                "conservative": ((5.0, 5.0), (9.0, 5.0), (9.0, 9.0)),
                "aggressive": AGGRESSIVE_PATROL_POINTS,
            },
        )
        return cls(
            arena=arena,
            collision_grid=OccupancyGrid.from_pgm(image, arena),
            zone_overrides=zones,
            patrol_routes=routes,
        )


__all__ = ["AssaultField"]
