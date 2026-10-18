"""Collision-aware occupancy grid and a minimal A* navigator."""

from __future__ import annotations

from dataclasses import dataclass, field
import heapq
import math

from .core import Arena
from .map_asset import PgmImage


# The official reference robot uses base_link.STL as its collision volume.
# Its horizontal bounds are approximately 0.5200 m x 0.5196 m.  The 2-D
# simulator uses the circumscribed radius so the footprint remains safe while
# the chassis spins, plus a small numerical clearance for the 0.05 m grid.
ROBOT_COLLISION_LENGTH = 0.5200
ROBOT_COLLISION_WIDTH = 0.5196
ROBOT_FOOTPRINT_RADIUS = math.hypot(ROBOT_COLLISION_LENGTH, ROBOT_COLLISION_WIDTH) * 0.5
ROBOT_COLLISION_CLEARANCE = 0.02
ROBOT_COLLISION_RADIUS = ROBOT_FOOTPRINT_RADIUS + ROBOT_COLLISION_CLEARANCE
ROBOT_ENTITY_COLLISION_RADIUS = ROBOT_COLLISION_RADIUS

# A* deliberately plans on a slightly larger virtual footprint than the real
# collision checker.  This keeps route centers away from obstacle corners and
# leaves continuous motion enough room to turn without sticking to a grid edge.
ASTAR_PLANNING_CLEARANCE = 0.07
ASTAR_PLANNING_RADIUS = ROBOT_COLLISION_RADIUS + ASTAR_PLANNING_CLEARANCE

# Values copied from the official rmuc2026.yaml map description.
MAP_OCCUPIED_THRESHOLD = 0.65
MAP_FREE_THRESHOLD = 0.25


@dataclass(frozen=True)
class OccupancyGrid:
    """Official PGM map converted to an inflated 2-D collision grid."""

    arena: Arena
    width: int
    height: int
    blocked: bytes
    collision_radius: float = ROBOT_COLLISION_RADIUS

    @classmethod
    def from_pgm(
        cls,
        image: PgmImage,
        arena: Arena,
        *,
        collision_radius: float = ROBOT_COLLISION_RADIUS,
    ) -> "OccupancyGrid":
        if collision_radius < 0.0:
            raise ValueError("collision_radius must be non-negative")

        left, top, width, height = arena.map_crop(image.width, image.height)
        raw_blocked = bytearray(width * height)
        for row in range(height):
            source_start = (top + row) * image.width + left
            source_row = image.pixels[source_start : source_start + width]
            target_start = row * width
            for column, value in enumerate(source_row):
                occupancy = (255.0 - value) / 255.0
                # Treat unknown cells as collision, matching conservative robot
                # navigation behavior.  This map is almost entirely binary.
                if occupancy > MAP_OCCUPIED_THRESHOLD:
                    raw_blocked[target_start + column] = 1
                elif occupancy < MAP_FREE_THRESHOLD:
                    raw_blocked[target_start + column] = 0
                else:
                    raw_blocked[target_start + column] = 1

        inflated = bytearray(raw_blocked)
        radius_cells = math.ceil(collision_radius / arena.map_resolution)
        offsets = [
            (row_offset, column_offset)
            for row_offset in range(-radius_cells, radius_cells + 1)
            for column_offset in range(-radius_cells, radius_cells + 1)
            if math.hypot(row_offset, column_offset) * arena.map_resolution
            <= collision_radius
        ]
        for index, occupied in enumerate(raw_blocked):
            if not occupied:
                continue
            row, column = divmod(index, width)
            for row_offset, column_offset in offsets:
                candidate_row = row + row_offset
                candidate_column = column + column_offset
                if 0 <= candidate_row < height and 0 <= candidate_column < width:
                    inflated[candidate_row * width + candidate_column] = 1

        # Keep the whole circular footprint inside the official 28 m x 15 m
        # field even if a border pixel in the source occupancy map is free.
        for row in range(height):
            center_y = arena.height - (row + 0.5) * arena.map_resolution
            for column in range(width):
                center_x = (column + 0.5) * arena.map_resolution
                if not (
                    collision_radius <= center_x <= arena.width - collision_radius
                    and collision_radius <= center_y <= arena.height - collision_radius
                ):
                    inflated[row * width + column] = 1

        return cls(
            arena=arena,
            width=width,
            height=height,
            blocked=bytes(inflated),
            collision_radius=collision_radius,
        )

    def world_to_cell(self, x: float, y: float) -> tuple[int, int]:
        column = int(x / self.arena.map_resolution)
        row = int((self.arena.height - y) / self.arena.map_resolution)
        return (
            min(max(row, 0), self.height - 1),
            min(max(column, 0), self.width - 1),
        )

    def cell_to_world(self, cell: tuple[int, int]) -> tuple[float, float]:
        row, column = cell
        return (
            (column + 0.5) * self.arena.map_resolution,
            self.arena.height - (row + 0.5) * self.arena.map_resolution,
        )

    def is_free_cell(self, cell: tuple[int, int]) -> bool:
        row, column = cell
        return (
            0 <= row < self.height
            and 0 <= column < self.width
            and not self.blocked[row * self.width + column]
        )

    def is_free_world(self, x: float, y: float) -> bool:
        if not (
            self.collision_radius <= x <= self.arena.width - self.collision_radius
            and self.collision_radius <= y <= self.arena.height - self.collision_radius
        ):
            return False
        return self.is_free_cell(self.world_to_cell(x, y))

    def line_of_sight(
        self,
        start: tuple[float, float],
        end: tuple[float, float],
    ) -> bool:
        """Return False when a straight 2-D segment intersects a blocked cell.

        Use a grid built with ``collision_radius=0`` for raw-map LOS; the
        inflated collision grid intentionally blocks cells near walls and is
        unsuitable here.
        """
        delta_x = end[0] - start[0]
        delta_y = end[1] - start[1]
        distance = math.hypot(delta_x, delta_y)
        if distance <= 1e-9:
            return True
        step = self.arena.map_resolution * 0.5
        steps = max(1, math.ceil(distance / step))
        for index in range(1, steps):
            ratio = index / steps
            row, column = self.world_to_cell(
                start[0] + delta_x * ratio,
                start[1] + delta_y * ratio,
            )
            if not self.is_free_cell((row, column)):
                return False
        return True

    def first_collision(
        self,
        start: tuple[float, float],
        target: tuple[float, float],
        *,
        collision_bodies: tuple[tuple[float, float, float], ...],
        moving_radius: float = ROBOT_ENTITY_COLLISION_RADIUS,
    ) -> int | None:
        """Return the index of the first robot body hit by the swept motion."""
        if moving_radius < 0.0:
            raise ValueError("moving_radius must be non-negative")
        delta_x = target[0] - start[0]
        delta_y = target[1] - start[1]
        length_squared = delta_x * delta_x + delta_y * delta_y
        if length_squared <= 1e-12:
            return None
        best_index: int | None = None
        best_projection = math.inf
        for index, (body_x, body_y, body_radius) in enumerate(collision_bodies):
            projection = (
                (body_x - start[0]) * delta_x + (body_y - start[1]) * delta_y
            ) / length_squared
            projection = min(1.0, max(0.0, projection))
            closest_x = start[0] + delta_x * projection
            closest_y = start[1] + delta_y * projection
            if math.hypot(body_x - closest_x, body_y - closest_y) < (
                moving_radius + body_radius
            ) and projection < best_projection:
                best_index = index
                best_projection = projection
        return best_index

    def with_dynamic_obstacles(
        self,
        bodies: tuple[tuple[float, float, float], ...],
    ) -> "OccupancyGrid":
        """Return a planning grid that also keeps robot centers apart."""
        if not bodies:
            return self
        blocked = bytearray(self.blocked)
        for body_x, body_y, body_radius in bodies:
            if body_radius < 0.0:
                raise ValueError("dynamic obstacle radius must be non-negative")
            clearance = self.collision_radius + body_radius
            radius_cells = math.ceil(clearance / self.arena.map_resolution)
            center_row, center_column = self.world_to_cell(body_x, body_y)
            for row in range(center_row - radius_cells, center_row + radius_cells + 1):
                if not 0 <= row < self.height:
                    continue
                for column in range(
                    center_column - radius_cells, center_column + radius_cells + 1
                ):
                    if not 0 <= column < self.width:
                        continue
                    world_x, world_y = self.cell_to_world((row, column))
                    if math.hypot(world_x - body_x, world_y - body_y) <= clearance:
                        blocked[row * self.width + column] = 1
        return OccupancyGrid(
            self.arena,
            self.width,
            self.height,
            bytes(blocked),
            self.collision_radius,
        )

    def with_blocked_rectangles(
        self,
        rectangles: tuple[tuple[float, float, float, float], ...],
        *,
        inflation: float = 0.0,
    ) -> "OccupancyGrid":
        """Paint axis-aligned world rectangles into the collision grid.

        Rectangles are given as ``(min_x, min_y, max_x, max_y)`` in metres.
        ``inflation`` expands the rectangle by the moving robot radius so a
        centre point cannot enter the footprint.
        """
        if not rectangles:
            return self
        if inflation < 0.0:
            raise ValueError("rectangle inflation must be non-negative")
        blocked = bytearray(self.blocked)
        for min_x, min_y, max_x, max_y in rectangles:
            if max_x < min_x or max_y < min_y:
                raise ValueError("rectangle max must be >= min")
            min_x -= inflation
            min_y -= inflation
            max_x += inflation
            max_y += inflation
            row_start, column_start = self.world_to_cell(min_x, max_y)
            row_end, column_end = self.world_to_cell(max_x, min_y)
            for row in range(row_start, row_end + 1):
                for column in range(column_start, column_end + 1):
                    if 0 <= row < self.height and 0 <= column < self.width:
                        blocked[row * self.width + column] = 1
        return OccupancyGrid(
            self.arena,
            self.width,
            self.height,
            bytes(blocked),
            self.collision_radius,
        )

    def nearest_free_cell(self, cell: tuple[int, int]) -> tuple[int, int] | None:
        """Return the nearest grid cell that can contain the robot footprint."""
        if self.is_free_cell(cell):
            return cell

        start_row, start_column = cell
        maximum_radius = max(self.width, self.height)
        for radius in range(1, maximum_radius + 1):
            candidates: list[tuple[int, int, int]] = []
            for row in range(start_row - radius, start_row + radius + 1):
                for column in (start_column - radius, start_column + radius):
                    if self.is_free_cell((row, column)):
                        distance_squared = (
                            (row - start_row) ** 2 + (column - start_column) ** 2
                        )
                        candidates.append((distance_squared, row, column))
            for column in range(start_column - radius + 1, start_column + radius):
                for row in (start_row - radius, start_row + radius):
                    if self.is_free_cell((row, column)):
                        distance_squared = (
                            (row - start_row) ** 2 + (column - start_column) ** 2
                        )
                        candidates.append((distance_squared, row, column))
            if candidates:
                _, row, column = min(candidates)
                return row, column
        return None

    def find_path(
        self,
        start: tuple[float, float],
        goal: tuple[float, float],
    ) -> list[tuple[float, float]]:
        """Run an 8-neighbour A* search and return collinear turn points."""
        start_cell = self.nearest_free_cell(self.world_to_cell(*start))
        goal_cell = self.nearest_free_cell(self.world_to_cell(*goal))
        if start_cell is None or goal_cell is None:
            return []
        if start_cell == goal_cell:
            endpoint = goal if self.is_free_world(*goal) else self.cell_to_world(goal_cell)
            return [endpoint]

        diagonal_cost = math.sqrt(2.0)
        neighbours = (
            (-1, 0, 1.0),
            (1, 0, 1.0),
            (0, -1, 1.0),
            (0, 1, 1.0),
            (-1, -1, diagonal_cost),
            (-1, 1, diagonal_cost),
            (1, -1, diagonal_cost),
            (1, 1, diagonal_cost),
        )

        def heuristic(cell: tuple[int, int]) -> float:
            row_distance = abs(cell[0] - goal_cell[0])
            column_distance = abs(cell[1] - goal_cell[1])
            diagonal = min(row_distance, column_distance)
            straight = max(row_distance, column_distance) - diagonal
            return diagonal * diagonal_cost + straight

        frontier: list[tuple[float, float, tuple[int, int]]] = [
            (heuristic(start_cell), 0.0, start_cell)
        ]
        costs = {start_cell: 0.0}
        previous: dict[tuple[int, int], tuple[int, int]] = {}

        while frontier:
            _, current_cost, current = heapq.heappop(frontier)
            if current == goal_cell:
                break
            if current_cost > costs.get(current, math.inf):
                continue

            current_row, current_column = current
            for row_step, column_step, movement_cost in neighbours:
                candidate = current_row + row_step, current_column + column_step
                if not self.is_free_cell(candidate):
                    continue
                if row_step and column_step:
                    # Do not cut diagonally through the corner of a collision.
                    if not self.is_free_cell((current_row + row_step, current_column)):
                        continue
                    if not self.is_free_cell((current_row, current_column + column_step)):
                        continue
                candidate_cost = current_cost + movement_cost
                if candidate_cost >= costs.get(candidate, math.inf):
                    continue
                costs[candidate] = candidate_cost
                previous[candidate] = current
                heapq.heappush(
                    frontier,
                    (candidate_cost + heuristic(candidate), candidate_cost, candidate),
                )
        else:
            return []

        cells = [goal_cell]
        while cells[-1] != start_cell:
            cells.append(previous[cells[-1]])
        cells.reverse()
        cells = self._remove_collinear_cells(cells)
        path = [self.cell_to_world(cell) for cell in cells[1:]]
        endpoint = goal if self.is_free_world(*goal) else self.cell_to_world(goal_cell)
        if not path or math.hypot(path[-1][0] - endpoint[0], path[-1][1] - endpoint[1]) > 1e-6:
            path.append(endpoint)
        else:
            path[-1] = endpoint
        return path

    @staticmethod
    def _remove_collinear_cells(
        cells: list[tuple[int, int]],
    ) -> list[tuple[int, int]]:
        if len(cells) < 3:
            return cells
        result = [cells[0]]
        previous_direction = (
            cells[1][0] - cells[0][0],
            cells[1][1] - cells[0][1],
        )
        for index in range(1, len(cells) - 1):
            direction = (
                cells[index + 1][0] - cells[index][0],
                cells[index + 1][1] - cells[index][1],
            )
            if direction != previous_direction:
                result.append(cells[index])
                previous_direction = direction
        result.append(cells[-1])
        return result

    def trace_free_motion(
        self,
        start: tuple[float, float],
        target: tuple[float, float],
        *,
        collision_bodies: tuple[tuple[float, float, float], ...] = (),
        moving_radius: float = ROBOT_ENTITY_COLLISION_RADIUS,
    ) -> tuple[float, float]:
        """Move until the map or another robot's swept collision body blocks it."""
        if moving_radius < 0.0:
            raise ValueError("moving_radius must be non-negative")
        delta_x = target[0] - start[0]
        delta_y = target[1] - start[1]
        distance = math.hypot(delta_x, delta_y)
        if distance <= 1e-9:
            return start
        step_length = self.arena.map_resolution * 0.5
        steps = max(1, math.ceil(distance / step_length))
        last_free = start
        for index in range(1, steps + 1):
            ratio = index / steps
            candidate = (
                start[0] + delta_x * ratio,
                start[1] + delta_y * ratio,
            )
            if not self.is_free_world(*candidate) or any(
                math.hypot(candidate[0] - body_x, candidate[1] - body_y)
                < moving_radius + body_radius
                for body_x, body_y, body_radius in collision_bodies
            ):
                break
            last_free = candidate
        return last_free

    def move_with_collision(
        self,
        start: tuple[float, float],
        target: tuple[float, float],
        *,
        collision_bodies: tuple[tuple[float, float, float], ...] = (),
        moving_radius: float = ROBOT_ENTITY_COLLISION_RADIUS,
    ) -> tuple[float, float]:
        """Resolve movement against walls and other robots, with axis sliding."""
        direct = self.trace_free_motion(
            start,
            target,
            collision_bodies=collision_bodies,
            moving_radius=moving_radius,
        )
        if math.hypot(direct[0] - target[0], direct[1] - target[1]) <= 1e-6:
            return direct

        x_first = self.trace_free_motion(
            start,
            (target[0], start[1]),
            collision_bodies=collision_bodies,
            moving_radius=moving_radius,
        )
        x_first = self.trace_free_motion(
            x_first,
            (x_first[0], target[1]),
            collision_bodies=collision_bodies,
            moving_radius=moving_radius,
        )
        y_first = self.trace_free_motion(
            start,
            (start[0], target[1]),
            collision_bodies=collision_bodies,
            moving_radius=moving_radius,
        )
        y_first = self.trace_free_motion(
            y_first,
            (target[0], y_first[1]),
            collision_bodies=collision_bodies,
            moving_radius=moving_radius,
        )
        return min(
            (direct, x_first, y_first),
            key=lambda point: math.hypot(point[0] - target[0], point[1] - target[1]),
        )


@dataclass
class AStarNavigator:
    """Cache a basic A* route until the requested goal materially changes."""

    grid: OccupancyGrid
    goal_replan_distance: float = 0.25
    waypoint_tolerance: float = 0.10
    requested_goal: tuple[float, float] | None = None
    path: list[tuple[float, float]] = field(default_factory=list)
    waypoint_index: int = 0

    def clear(self) -> None:
        self.requested_goal = None
        self.path = []
        self.waypoint_index = 0

    def update_goal(
        self,
        start: tuple[float, float],
        goal: tuple[float, float] | None,
    ) -> None:
        if goal is None:
            self.clear()
            return
        changed = self.requested_goal is None or math.hypot(
            goal[0] - self.requested_goal[0],
            goal[1] - self.requested_goal[1],
        ) > self.goal_replan_distance
        if not changed:
            return
        self.requested_goal = goal
        self.path = self.grid.find_path(start, goal)
        self.waypoint_index = 0

    def next_waypoint(
        self,
        current: tuple[float, float],
    ) -> tuple[float, float] | None:
        while self.waypoint_index < len(self.path):
            waypoint = self.path[self.waypoint_index]
            if math.hypot(waypoint[0] - current[0], waypoint[1] - current[1]) > self.waypoint_tolerance:
                return waypoint
            self.waypoint_index += 1
        return None

    @property
    def remaining_path(self) -> list[tuple[float, float]]:
        return self.path[self.waypoint_index :]
