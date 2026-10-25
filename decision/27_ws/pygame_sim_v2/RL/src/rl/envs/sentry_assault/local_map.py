"""Local spatial observation for end-to-end path learning."""

from __future__ import annotations

import math

import numpy as np

from rm2026_sim.field_geometry import BLUE_BASE, BLUE_OUTPOST

from rl.config import AssaultConfig
from .field import AssaultField


LOCAL_MAP_CHANNELS = 6


class LocalMapEncoder:
    """Build a world-aligned local crop without path or waypoint information."""

    def __init__(self, field: AssaultField, config: AssaultConfig) -> None:
        self.field = field
        self.config = config
        self.explored = bytearray(
            field.collision_grid.width * field.collision_grid.height
        )
        grid = field.collision_grid
        self._explored_grid = np.frombuffer(self.explored, dtype=np.uint8).reshape(
            grid.height, grid.width
        )
        radius = max(
            1,
            round(
                config.local_map_cells
                * config.local_map_resolution
                / grid.arena.map_resolution
                / 2.0
            ),
        )
        radius_squared = radius * radius
        self._exploration_spans = tuple(
            (
                row_offset,
                math.isqrt(radius_squared - row_offset * row_offset),
            )
            for row_offset in range(-radius, radius + 1)
        )
        half = config.local_map_cells // 2
        offsets = (
            np.arange(config.local_map_cells, dtype=np.float64) - half
        ) * config.local_map_resolution
        self._local_x_offsets = offsets
        self._local_y_offsets = -offsets
        rows = np.arange(config.local_map_cells, dtype=np.float64)
        columns = np.arange(config.local_map_cells, dtype=np.float64)
        self._local_rows = rows[:, None]
        self._local_columns = columns[None, :]
        self._blocked = np.frombuffer(grid.blocked, dtype=np.uint8).reshape(
            grid.height, grid.width
        )

    def reset(self) -> None:
        self.explored[:] = bytes(len(self.explored))

    def _mark_explored(self, x: float, y: float) -> None:
        grid = self.field.collision_grid
        center_row, center_column = grid.world_to_cell(x, y)
        for row_offset, half_span in self._exploration_spans:
            row = center_row + row_offset
            if not 0 <= row < grid.height:
                continue
            start = max(0, center_column - half_span)
            end = min(grid.width, center_column + half_span + 1)
            self._explored_grid[row, start:end] = 1

    def encode(
        self,
        x: float,
        y: float,
        chassis_angle: float,
        *,
        outpost_alive: bool,
        base_alive: bool,
    ) -> np.ndarray:
        self._mark_explored(x, y)
        cells = self.config.local_map_cells
        resolution = self.config.local_map_resolution
        half = cells // 2
        grid = self.field.collision_grid
        result = np.zeros((LOCAL_MAP_CHANNELS, cells, cells), dtype=np.float32)
        world_x = x + self._local_x_offsets[None, :]
        world_y = y + self._local_y_offsets[:, None]
        inside_arena = (
            (world_x >= 0.0)
            & (world_x <= grid.arena.width)
            & (world_y >= 0.0)
            & (world_y <= grid.arena.height)
        )
        inside_collision_bounds = (
            (world_x >= grid.collision_radius)
            & (world_x <= grid.arena.width - grid.collision_radius)
            & (world_y >= grid.collision_radius)
            & (world_y <= grid.arena.height - grid.collision_radius)
        )
        world_columns = np.trunc(world_x / grid.arena.map_resolution).astype(np.intp)
        world_rows = np.trunc(
            (grid.arena.height - world_y) / grid.arena.map_resolution
        ).astype(np.intp)
        world_columns = np.clip(world_columns, 0, grid.width - 1)
        world_rows = np.clip(world_rows, 0, grid.height - 1)
        blocked = self._blocked[world_rows, world_columns] != 0
        free = inside_arena & inside_collision_bounds & ~blocked
        explored = self._explored_grid[world_rows, world_columns] != 0
        result[0] = ~free
        result[1] = free & explored
        result[2] = free & ~explored

        def mark(channel: int, position: tuple[float, float], enabled: bool) -> None:
            if not enabled:
                return
            column = round((position[0] - x) / resolution) + half
            row = half - round((position[1] - y) / resolution)
            if 0 <= row < cells and 0 <= column < cells:
                result[channel, row, column] = 1.0

        mark(3, BLUE_OUTPOST, outpost_alive)
        mark(4, BLUE_BASE, base_alive)
        result[5, half, half] = 1.0
        direction_length = max(1, cells // 10)
        direction_column = half + round(math.cos(chassis_angle) * direction_length)
        direction_row = half - round(math.sin(chassis_angle) * direction_length)
        if 0 <= direction_row < cells and 0 <= direction_column < cells:
            result[5, direction_row, direction_column] = 0.5
        return result


__all__ = ["LOCAL_MAP_CHANNELS", "LocalMapEncoder"]
