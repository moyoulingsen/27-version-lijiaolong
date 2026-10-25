"""Shared static field assets; no path planner is defined here."""

from __future__ import annotations

from dataclasses import dataclass
import heapq
import math
from typing import Mapping

import numpy as np

from rm2026_sim.core import Arena
from rm2026_sim.field_geometry import AGGRESSIVE_PATROL_POINTS, BLUE_BASE, BLUE_OUTPOST
from rm2026_sim.map_regions import (
    load_complete_geometry_file,
    traversable_tunnel_corridors,
    wall_collision_polygons,
)
from rm2026_sim.navigation import OccupancyGrid, ROBOT_ENTITY_COLLISION_RADIUS
from rl import PROJECT_ROOT


GEOMETRY_PATH = PROJECT_ROOT / "map_regions.json"
TUNNEL_CURRICULUM_STARTS = ((11.70, 13.05), (18.40, 14.00))


@dataclass(frozen=True, slots=True)
class TacticalFields:
    """Static reward-only fields; none of these values enter Actor observations."""

    outpost_distance: np.ndarray
    base_distance: np.ndarray
    wall_clearance: np.ndarray


@dataclass(frozen=True, slots=True)
class AssaultField:
    arena: Arena
    collision_grid: OccupancyGrid
    zone_overrides: Mapping[str, tuple[tuple[float, float], ...]]
    patrol_routes: Mapping[str, tuple[tuple[float, float], ...]]
    tunnel_corridors: Mapping[str, tuple[tuple[float, float], ...]]
    custom_polygons: tuple[dict, ...]
    slow_regions: tuple[dict, ...]
    fly_slope_polygons: tuple[tuple[tuple[float, float], ...], ...]

    @staticmethod
    def _point_in_polygon(
        x: float,
        y: float,
        points: tuple[tuple[float, float], ...],
    ) -> bool:
        inside = False
        previous_x, previous_y = points[-1]
        for current_x, current_y in points:
            if (current_y > y) != (previous_y > y):
                edge_x = previous_x + (y - previous_y) * (
                    current_x - previous_x
                ) / (current_y - previous_y)
                if x < edge_x:
                    inside = not inside
            previous_x, previous_y = current_x, current_y
        return inside

    def terrain_speed_multiplier(self, x: float, y: float) -> float:
        multipliers: list[float] = []
        for item in self.slow_regions:
            points = tuple(
                (float(point[0]), float(point[1]))
                for point in item.get("points", ())
                if isinstance(point, (list, tuple)) and len(point) >= 2
            )
            if len(points) < 3 or not self._point_in_polygon(x, y, points):
                continue
            try:
                multipliers.append(float(item.get("speed_multiplier", 0.5)))
            except (TypeError, ValueError):
                multipliers.append(0.5)
        return max(0.05, min(1.0, min(multipliers, default=1.0)))

    @staticmethod
    def _segments_intersect(
        first_start: tuple[float, float],
        first_end: tuple[float, float],
        second_start: tuple[float, float],
        second_end: tuple[float, float],
    ) -> bool:
        def cross(a, b, c) -> float:
            return (b[0] - a[0]) * (c[1] - a[1]) - (
                b[1] - a[1]
            ) * (c[0] - a[0])

        epsilon = 1e-9
        first_side_a = cross(first_start, first_end, second_start)
        first_side_b = cross(first_start, first_end, second_end)
        second_side_a = cross(second_start, second_end, first_start)
        second_side_b = cross(second_start, second_end, first_end)
        return (
            min(first_side_a, first_side_b) <= epsilon
            and max(first_side_a, first_side_b) >= -epsilon
            and min(second_side_a, second_side_b) <= epsilon
            and max(second_side_a, second_side_b) >= -epsilon
        )

    def apply_fly_slope_one_way(
        self,
        start: tuple[float, float],
        proposed: tuple[float, float],
    ) -> tuple[float, float]:
        delta_x = proposed[0] - start[0]
        if math.hypot(delta_x, proposed[1] - start[1]) <= 1e-9:
            return proposed
        for points in self.fly_slope_polygons:
            touches = (
                self._point_in_polygon(*start, points)
                or self._point_in_polygon(*proposed, points)
                or any(
                    self._segments_intersect(start, proposed, edge_start, edge_end)
                    for edge_start, edge_end in zip(
                        points,
                        points[1:] + points[:1],
                    )
                )
            )
            if not touches:
                continue
            centre_y = sum(point[1] for point in points) / len(points)
            allowed = delta_x > 1e-9 if centre_y < self.arena.height / 2.0 else delta_x < -1e-9
            if not allowed:
                return start
        return proposed

    def tactical_fields(
        self,
        *,
        minimum_fire_range: float,
        maximum_fire_range: float,
        minimum_clearance: float,
        base_minimum_x: float | None = None,
    ) -> TacticalFields:
        """Build shortest-path distance to any open, valid firing position."""
        grid = self.collision_grid
        blocked = np.frombuffer(grid.blocked, dtype=np.uint8).reshape(
            grid.height,
            grid.width,
        ).astype(bool, copy=True)
        clearance = self._clearance_field(blocked, grid.arena.map_resolution)

        rows = np.arange(grid.height, dtype=np.float32).reshape(-1, 1)
        columns = np.arange(grid.width, dtype=np.float32).reshape(1, -1)
        world_x = (columns + 0.5) * grid.arena.map_resolution
        world_y = grid.arena.height - (rows + 0.5) * grid.arena.map_resolution
        terrain_speed = np.ones((grid.height, grid.width), dtype=np.float32)
        for row in range(grid.height):
            for column in range(grid.width):
                terrain_speed[row, column] = self.terrain_speed_multiplier(
                    float(world_x[0, column]),
                    float(world_y[row, 0]),
                )
        fly_slope_direction = np.zeros(
            (grid.height, grid.width),
            dtype=np.int8,
        )
        for points in self.fly_slope_polygons:
            centre_y = sum(point[1] for point in points) / len(points)
            direction = 1 if centre_y < grid.arena.height / 2.0 else -1
            for row in range(grid.height):
                for column in range(grid.width):
                    if self._point_in_polygon(
                        float(world_x[0, column]),
                        float(world_y[row, 0]),
                        points,
                    ):
                        fly_slope_direction[row, column] = direction

        def target_field(
            target: tuple[float, float],
            extra_goals: np.ndarray | None = None,
        ) -> np.ndarray:
            direct = np.hypot(world_x - target[0], world_y - target[1])
            goals = (
                ~blocked
                & (direct >= minimum_fire_range)
                & (direct <= maximum_fire_range)
                & (clearance >= minimum_clearance)
            )
            if extra_goals is not None:
                goals &= extra_goals
            if not bool(goals.any()):
                goals = (
                    ~blocked
                    & (direct >= minimum_fire_range)
                    & (direct <= maximum_fire_range)
                )
                if extra_goals is not None:
                    goals &= extra_goals
            return self._geodesic_distance_field(
                blocked,
                goals,
                grid.arena.map_resolution,
                terrain_speed,
                fly_slope_direction,
            )

        base_goals = (
            world_x >= base_minimum_x
            if base_minimum_x is not None
            else None
        )
        return TacticalFields(
            outpost_distance=target_field(BLUE_OUTPOST),
            base_distance=target_field(BLUE_BASE, base_goals),
            wall_clearance=clearance,
        )

    @staticmethod
    def _clearance_field(blocked: np.ndarray, resolution: float) -> np.ndarray:
        """Approximate Euclidean distance to collision using a chamfer pass."""
        height, width = blocked.shape
        distance = np.where(blocked, 0.0, np.inf).astype(np.float32)
        diagonal = math.sqrt(2.0)
        for row in range(height):
            for column in range(width):
                if distance[row, column] == 0.0:
                    continue
                best = distance[row, column]
                if row > 0:
                    best = min(best, distance[row - 1, column] + 1.0)
                    if column > 0:
                        best = min(best, distance[row - 1, column - 1] + diagonal)
                    if column + 1 < width:
                        best = min(best, distance[row - 1, column + 1] + diagonal)
                if column > 0:
                    best = min(best, distance[row, column - 1] + 1.0)
                distance[row, column] = best
        for row in range(height - 1, -1, -1):
            for column in range(width - 1, -1, -1):
                if distance[row, column] == 0.0:
                    continue
                best = distance[row, column]
                if row + 1 < height:
                    best = min(best, distance[row + 1, column] + 1.0)
                    if column > 0:
                        best = min(best, distance[row + 1, column - 1] + diagonal)
                    if column + 1 < width:
                        best = min(best, distance[row + 1, column + 1] + diagonal)
                if column + 1 < width:
                    best = min(best, distance[row, column + 1] + 1.0)
                distance[row, column] = best
        return distance * resolution

    @staticmethod
    def _geodesic_distance_field(
        blocked: np.ndarray,
        goals: np.ndarray,
        resolution: float,
        terrain_speed: np.ndarray,
        fly_slope_direction: np.ndarray,
    ) -> np.ndarray:
        height, width = blocked.shape
        distance = np.full((height, width), np.inf, dtype=np.float32)
        heap: list[tuple[float, int, int]] = []
        for row, column in np.argwhere(goals):
            distance[row, column] = 0.0
            heap.append((0.0, int(row), int(column)))
        heapq.heapify(heap)
        neighbours = (
            (-1, 0, resolution),
            (1, 0, resolution),
            (0, -1, resolution),
            (0, 1, resolution),
            (-1, -1, resolution * math.sqrt(2.0)),
            (-1, 1, resolution * math.sqrt(2.0)),
            (1, -1, resolution * math.sqrt(2.0)),
            (1, 1, resolution * math.sqrt(2.0)),
        )
        while heap:
            current, row, column = heapq.heappop(heap)
            if current > float(distance[row, column]) + 1e-6:
                continue
            for row_offset, column_offset, cost in neighbours:
                candidate_row = row + row_offset
                candidate_column = column + column_offset
                if not (
                    0 <= candidate_row < height
                    and 0 <= candidate_column < width
                    and not blocked[candidate_row, candidate_column]
                ):
                    continue
                if row_offset and column_offset:
                    if (
                        blocked[row, candidate_column]
                        or blocked[candidate_row, column]
                    ):
                        continue
                # Dijkstra expands backwards from the goal.  Check whether a
                # forward move from the candidate predecessor into the current
                # cell respects the same one-way fly-slope rule as simulation.
                slope_direction = (
                    fly_slope_direction[row, column]
                    if fly_slope_direction[row, column] != 0
                    else fly_slope_direction[candidate_row, candidate_column]
                )
                delta_x = (column - candidate_column) * resolution
                if (
                    (slope_direction > 0 and delta_x <= 1e-9)
                    or (slope_direction < 0 and delta_x >= -1e-9)
                ):
                    continue
                speed = max(
                    0.05,
                    float(terrain_speed[candidate_row, candidate_column]),
                )
                candidate = current + cost / speed
                if candidate + 1e-6 >= float(
                    distance[candidate_row, candidate_column]
                ):
                    continue
                distance[candidate_row, candidate_column] = candidate
                heapq.heappush(
                    heap,
                    (candidate, candidate_row, candidate_column),
                )
        finite = np.isfinite(distance)
        replacement = (
            float(distance[finite].max())
            + math.hypot(width, height) * resolution
            if bool(finite.any())
            else math.hypot(width, height) * resolution
        )
        distance[~finite] = replacement
        return distance

    @classmethod
    def load(cls) -> "AssaultField":
        arena = Arena()
        (
            zones,
            custom_polygons,
            routes,
            walls,
            special_walls,
            slow_regions,
        ) = load_complete_geometry_file(
            GEOMETRY_PATH,
            {
                "conservative": ((5.0, 5.0), (9.0, 5.0), (9.0, 9.0)),
                "aggressive": AGGRESSIVE_PATROL_POINTS,
            },
        )
        tunnel_corridors = traversable_tunnel_corridors(custom_polygons)
        fly_slope_polygons: list[tuple[tuple[float, float], ...]] = []
        base_fly_slope = zones.get("region_04_fly_slope", ())
        if len(base_fly_slope) >= 3:
            fly_slope_polygons.append(tuple(base_fly_slope))
        for item in custom_polygons:
            if str(item.get("kind", "")) != "region_04_fly_slope":
                continue
            points = tuple(
                (float(point[0]), float(point[1]))
                for point in item.get("points", ())
                if isinstance(point, (list, tuple)) and len(point) >= 2
            )
            if len(points) >= 3:
                fly_slope_polygons.append(points)
        collision_polygons = (
            wall_collision_polygons(walls)
            + wall_collision_polygons(special_walls)
        )
        collision_grid = OccupancyGrid.empty(arena).with_blocked_polygons(
            collision_polygons,
            inflation=ROBOT_ENTITY_COLLISION_RADIUS,
        ).with_cleared_polygons(tunnel_corridors.values())
        return cls(
            arena=arena,
            collision_grid=collision_grid,
            zone_overrides=zones,
            patrol_routes=routes,
            tunnel_corridors=tunnel_corridors,
            custom_polygons=tuple(custom_polygons),
            slow_regions=tuple(slow_regions),
            fly_slope_polygons=tuple(fly_slope_polygons),
        )


__all__ = [
    "AssaultField",
    "TacticalFields",
    "TUNNEL_CURRICULUM_STARTS",
]
