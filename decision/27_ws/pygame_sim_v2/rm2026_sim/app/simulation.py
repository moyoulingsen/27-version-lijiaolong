"""实时仿真更新、碰撞检测和行为树桥接。

这里放的是状态推进逻辑，UI 绘制不应直接修改规则状态。
"""

from __future__ import annotations

from .main import *


class SimulationMixin:
    def _viewport(self) -> Viewport:
        width, height = self.screen.get_size()
        left = SIDE_PANEL_WIDTH + 24
        right = width - RIGHT_PANEL_WIDTH - 24
        top = HEADER_HEIGHT + 18
        bottom = height - SNAPSHOT_BAR_HEIGHT - 18 - self._map_layer_panel_height()
        available_width = max(1.0, right - left)
        available_height = max(1.0, bottom - top)
        scale = min(
            available_width / self.arena.width,
            available_height / self.arena.height,
        )
        map_width = self.arena.width * scale
        map_height = self.arena.height * scale
        return Viewport(
            left + (available_width - map_width) / 2.0,
            top + (available_height - map_height) / 2.0,
            map_width,
            map_height,
            self.arena,
        )

    def _map_layer_panel_height(self) -> int:
        """Return the bottom panel height reserved outside the map viewport."""
        if not self.map_layers_panel_open:
            return MAP_LAYER_PANEL_COLLAPSED_HEIGHT
        width = max(
            280,
            self.screen.get_width() - SIDE_PANEL_WIDTH - RIGHT_PANEL_WIDTH - 16,
        )
        columns = max(2, min(8, width // 150))
        button_count = 2 + len(FIELD_ZONE_KIND_LABELS) + len(MAP_OVERLAY_LABELS)
        rows = math.ceil(button_count / columns)
        region_count = len(REGION_DEFINITIONS) + len(self.custom_map_polygons)
        region_columns = max(1, min(3, width // 360))
        region_rows = math.ceil(max(1, region_count) / region_columns)
        visible_region_rows = min(region_rows, MAP_REGION_VISIBLE_ROWS)
        editor_tab = getattr(self, "map_editor_tab", "layers")
        region_editor_open = getattr(self, "map_region_editor_open", False)
        if editor_tab == "layers" and not region_editor_open:
            return max(MAP_LAYER_PANEL_EXPANDED_HEIGHT, 150 + rows * 38)
        editor_height = 84 if (
            self.region_edit_new_custom
            or self.region_edit_new_wall
            or self.region_edit_new_special
            or self.region_edit_new_slow
            or
            self.region_edit_target is not None
            or self.region_edit_custom_id is not None
            or self.region_edit_wall_id is not None
            or self.region_edit_special_id is not None
            or self.region_edit_slow_id is not None
            or self.region_edit_patrol_kind is not None
            or self.region_edit_points
        ) else 0
        if editor_tab == "walls":
            item_rows = (
                min(len(self.wall_polygons), MAP_EXTRA_VISIBLE_ROWS)
                if getattr(self, "map_extra_list_open", True)
                else 0
            )
            return max(MAP_LAYER_PANEL_EXPANDED_HEIGHT, 132 + item_rows * 34 + editor_height)
        if editor_tab == "special":
            item_rows = (
                min(len(self.special_regions), MAP_EXTRA_VISIBLE_ROWS)
                if getattr(self, "map_extra_list_open", True)
                else 0
            )
            return max(MAP_LAYER_PANEL_EXPANDED_HEIGHT, 160 + item_rows * 34 + editor_height)
        if editor_tab == "slow":
            item_rows = (
                min(len(self.slow_regions), MAP_EXTRA_VISIBLE_ROWS)
                if getattr(self, "map_extra_list_open", True)
                else 0
            )
            return max(MAP_LAYER_PANEL_EXPANDED_HEIGHT, 160 + item_rows * 34 + editor_height)
        return max(
            MAP_LAYER_PANEL_EXPANDED_HEIGHT,
            150 + rows * 38 + editor_height + visible_region_rows * 34,
        )

    def _movement_input(self) -> tuple[float, float]:
        keys = self.pg.key.get_pressed()
        control_held = keys[self.pg.K_LCTRL] or keys[self.pg.K_RCTRL]
        move_right = keys[self.pg.K_d] or keys[self.pg.K_RIGHT]
        move_left = keys[self.pg.K_a] or keys[self.pg.K_LEFT]
        move_up = keys[self.pg.K_w] or keys[self.pg.K_UP]
        move_down = (keys[self.pg.K_s] and not control_held) or keys[self.pg.K_DOWN]
        x = float(move_right) - float(move_left)
        y = float(move_up) - float(move_down)
        return x, y

    def _update_sentry_motion(
        self,
        elapsed_seconds: float,
        manual_x: float,
        manual_y: float,
        decision: DecisionView,
    ) -> None:
        if getattr(self, "replay_mode", False):
            return
        self._refresh_dynamic_planning_grid()
        power_cut = self.task.sentry_chassis_power_cut
        if self.sentry.manual_control:
            start = (self.sentry.x, self.sentry.y)
            move_x = 0.0 if power_cut else manual_x
            move_y = 0.0 if power_cut else manual_y
            terrain_multiplier = self._terrain_speed_multiplier(start)
            command_length = math.hypot(move_x, move_y)
            physical_move_x = move_x
            physical_move_y = move_y
            if command_length > 1.0:
                physical_move_x /= command_length
                physical_move_y /= command_length
            self.sentry.update(
                elapsed_seconds,
                physical_move_x * terrain_multiplier,
                physical_move_y * terrain_multiplier,
                self.arena,
                spin_enabled=decision.spin_mode > 0 and not power_cut,
                spin_speed_scale=self._spin_speed_scale(decision.spin_mode),
                turret_enabled=not self._manual_fire_held,
                # Terrain limits actual travel only. Power continues to use
                # the unmodified driver command.
                chassis_move_x=move_x,
                chassis_move_y=move_y,
            )
            proposed = self._apply_fly_slope_one_way(
                start,
                (self.sentry.x, self.sentry.y),
            )
            bodies = self._collision_bodies("red", 8)
            self.sentry.x, self.sentry.y = self.collision_grid.move_with_collision(
                start,
                proposed,
                collision_bodies=bodies,
                moving_radius=ROBOT_ENTITY_COLLISION_RADIUS,
            )
            self._check_robot_collision(
                "red",
                8,
                start,
                proposed,
                (self.sentry.x, self.sentry.y),
                moving_radius=ROBOT_ENTITY_COLLISION_RADIUS,
            )
            self.navigator.clear()
            return

        current = (self.sentry.x, self.sentry.y)
        self.navigator.update_goal(current, decision.goal)
        waypoint = self.navigator.next_waypoint(current)
        proposed = current
        auto_move_x = 0.0
        auto_move_y = 0.0
        terrain_multiplier = self._terrain_speed_multiplier(current)
        if waypoint is not None and not power_cut:
            delta_x = waypoint[0] - self.sentry.x
            delta_y = waypoint[1] - self.sentry.y
            distance = math.hypot(delta_x, delta_y)
            if distance > 0.08:
                travel = min(
                    distance,
                    self.sentry.movement_speed * terrain_multiplier * elapsed_seconds,
                )
                proposed = self.arena.clamp(
                    self.sentry.x + delta_x / distance * travel,
                    self.sentry.y + delta_y / distance * travel,
                )
                proposed = self._apply_fly_slope_one_way(current, proposed)
                bodies = self._collision_bodies("red", 8)
                self.sentry.x, self.sentry.y = self.collision_grid.move_with_collision(
                    current,
                    proposed,
                    collision_bodies=bodies,
                    moving_radius=ROBOT_ENTITY_COLLISION_RADIUS,
                )
                self._check_robot_collision(
                    "red",
                    8,
                    current,
                    proposed,
                    (self.sentry.x, self.sentry.y),
                    moving_radius=ROBOT_ENTITY_COLLISION_RADIUS,
                )

        tracking = self._track_selected_target(decision, elapsed_seconds)
        terrain_command_distance = (
            self.sentry.movement_speed * terrain_multiplier * elapsed_seconds
        )
        if terrain_command_distance > 0.0:
            # Divide out the terrain multiplier so chassis power sees the
            # same command level it would receive on normal ground.
            auto_move_x = (proposed[0] - current[0]) / terrain_command_distance
            auto_move_y = (proposed[1] - current[1]) / terrain_command_distance
        self.sentry.update(
            elapsed_seconds,
            0.0,
            0.0,
            self.arena,
            spin_enabled=decision.spin_mode > 0 and not power_cut,
            spin_speed_scale=self._spin_speed_scale(decision.spin_mode),
            turret_enabled=decision.tripod_mode > 0 and not tracking,
            chassis_move_x=auto_move_x,
            chassis_move_y=auto_move_y,
        )

    def _normalize_robot_positions(self) -> None:
        """Repair initial/legacy positions inside walls or overlapping robots."""
        # Ground and aerial robots live on different collision layers.  They
        # may share the same world position without forcing either one away.
        placed: list[tuple[float, float, float, bool]] = []
        entries = [
            ("sentry", 8),
            *(("blue", target_id) for target_id in self.task.robot_positions),
            *(("red", target_id) for target_id in self.task.own_robot_positions),
        ]
        for team, target_id in entries:
            position = (
                (self.sentry.x, self.sentry.y)
                if team == "sentry"
                else self.task.robot_position(target_id, team=team)
            )
            robot_radius = (
                ROBOT_ENTITY_COLLISION_RADIUS
                if team == "sentry"
                else self._robot_collision_radius(team, target_id)
            )
            is_aerial = target_id == 5
            overlaps = any(
                math.hypot(position[0] - x, position[1] - y)
                < robot_radius + radius
                for x, y, radius, placed_is_aerial in placed
                if placed_is_aerial == is_aerial
            )
            movement_grid = self._movement_collision_grid(target_id)
            if not movement_grid.is_free_world(*position) or overlaps:
                collision_layer = tuple(
                    (x, y, radius)
                    for x, y, radius, placed_is_aerial in placed
                    if placed_is_aerial == is_aerial
                )
                grid = movement_grid.with_dynamic_obstacles(collision_layer)
                nearest = grid.nearest_free_cell(grid.world_to_cell(*position))
                if nearest is not None:
                    position = grid.cell_to_world(nearest)
                    if team == "sentry":
                        self.sentry.x, self.sentry.y = position
                    else:
                        self.task.set_robot_position(target_id, position, team=team)
            placed.append((*position, robot_radius, is_aerial))

    def _movement_collision_grid(self, target_id: int) -> OccupancyGrid:
        """Return the normal-wall-only grid for traversable robot classes."""
        if target_id == 5:
            return getattr(self, "aerial_collision_grid", self.collision_grid)
        if target_id in (2, 3, 4):
            return getattr(self, "infantry_collision_grid", self.collision_grid)
        return self.collision_grid

    def _move_with_special_wall_delay(
        self,
        team: str,
        target_id: int,
        start: tuple[float, float],
        proposed: tuple[float, float],
        *,
        elapsed_seconds: float,
        collision_bodies,
        moving_radius: float,
    ) -> tuple[float, float]:
        """Require either team's robot 2/3/4 to press for one continuous second."""
        robot_key = (team, target_id)
        timers = self.special_wall_traverse_timers
        active = self.special_wall_traverse_active
        if target_id == 5:
            for pending_key in tuple(timers):
                if pending_key[:2] == robot_key:
                    timers.pop(pending_key, None)
            for active_key in tuple(active):
                if active_key[:2] == robot_key:
                    active.discard(active_key)
            aerial_grid = getattr(self, "aerial_collision_grid", None)
            if aerial_grid is None:
                aerial_grid = OccupancyGrid.empty(
                    self.arena,
                    collision_radius=AERIAL_COLLISION_RADIUS,
                )
            return aerial_grid.move_with_collision(
                start,
                proposed,
                collision_bodies=collision_bodies,
                moving_radius=moving_radius,
            )
        blocked = self.collision_grid.move_with_collision(
            start,
            proposed,
            collision_bodies=collision_bodies,
            moving_radius=moving_radius,
        )
        # Only continuous input from the same selected robot and the same
        # wall counts toward that wall's one-second requirement.
        for pending_key in tuple(timers):
            if pending_key[:2] != robot_key:
                timers.pop(pending_key, None)
        if target_id not in SPECIAL_WALL_TRAVERSAL_ROBOT_IDS:
            for pending_key in tuple(timers):
                if pending_key[:2] == robot_key:
                    timers.pop(pending_key, None)
            for active_key in tuple(active):
                if active_key[:2] == robot_key:
                    active.discard(active_key)
            return blocked

        base_grid = getattr(
            self,
            "infantry_collision_grid",
            self.collision_grid,
        )
        base_result = base_grid.move_with_collision(
            start,
            proposed,
            collision_bodies=collision_bodies,
            moving_radius=moving_radius,
        )
        wall_entries = getattr(self, "special_wall_collision_polygons", ())
        individual_grids = getattr(self, "special_wall_individual_grids", {})
        wall_only_grids = getattr(self, "special_wall_only_grids", {})

        # Once the robot has fully left one wall, that wall loses its pass and
        # will require another second if approached again later.
        for active_key in tuple(active):
            if active_key[:2] != robot_key:
                continue
            wall_grid = wall_only_grids.get(active_key[2])
            if wall_grid is None or wall_grid.is_free_world(*start):
                active.discard(active_key)

        unlocked_ids = {
            active_key[2]
            for active_key in active
            if active_key[:2] == robot_key
        }
        locked_polygons = [
            polygon
            for identifier, polygon in wall_entries
            if identifier not in unlocked_ids
        ]
        movement_grid = base_grid
        if locked_polygons:
            movement_grid = movement_grid.with_blocked_polygons(
                locked_polygons,
                inflation=ROBOT_ENTITY_COLLISION_RADIUS,
            )
        resolved = movement_grid.move_with_collision(
            start,
            proposed,
            collision_bodies=collision_bodies,
            moving_radius=moving_radius,
        )

        candidates: list[tuple[float, str]] = []
        for identifier, _ in wall_entries:
            if identifier in unlocked_ids:
                continue
            wall_grid = individual_grids.get(identifier)
            if wall_grid is None:
                continue
            wall_result = wall_grid.move_with_collision(
                start,
                proposed,
                collision_bodies=collision_bodies,
                moving_radius=moving_radius,
            )
            if math.hypot(
                wall_result[0] - base_result[0],
                wall_result[1] - base_result[1],
            ) <= 1e-5:
                continue
            candidates.append((
                math.hypot(wall_result[0] - start[0], wall_result[1] - start[1]),
                identifier,
            ))

        if not candidates:
            for pending_key in tuple(timers):
                if pending_key[:2] == robot_key:
                    timers.pop(pending_key, None)
            return resolved

        _, wall_id = min(candidates)
        timer_key = (team, target_id, wall_id)
        for pending_key in tuple(timers):
            if pending_key[:2] == robot_key and pending_key != timer_key:
                timers.pop(pending_key, None)
        timers[timer_key] = timers.get(timer_key, 0.0) + max(0.0, elapsed_seconds)
        if timers[timer_key] < SPECIAL_WALL_TRAVERSE_SECONDS:
            return resolved

        timers.pop(timer_key, None)
        active.add(timer_key)
        unlocked_ids.add(wall_id)
        remaining_polygons = [
            polygon
            for identifier, polygon in wall_entries
            if identifier not in unlocked_ids
        ]
        released_grid = base_grid
        if remaining_polygons:
            released_grid = released_grid.with_blocked_polygons(
                remaining_polygons,
                inflation=ROBOT_ENTITY_COLLISION_RADIUS,
            )
        return released_grid.move_with_collision(
            start,
            proposed,
            collision_bodies=collision_bodies,
            moving_radius=moving_radius,
        )

    def _collision_entries(
        self, moving_team: str, moving_id: int
    ) -> list[tuple[int, str, float, float, float]]:
        if moving_team == "sentry":
            moving_team, moving_id = "red", 8
        moving_is_aerial = moving_id == 5
        entries: list[tuple[int, str, float, float, float]] = []
        for target_id in self.task.robot_positions:
            if moving_team == "blue" and target_id == moving_id:
                continue
            if (target_id == 5) != moving_is_aerial:
                continue
            x, y = self.task.robot_position(target_id, team="blue")
            entries.append(
                (
                    target_id,
                    "blue",
                    x,
                    y,
                    self._robot_collision_radius("blue", target_id),
                )
            )
        for target_id in self.task.own_robot_positions:
            if moving_team == "red" and target_id == moving_id:
                continue
            if (target_id == 5) != moving_is_aerial:
                continue
            x, y = self.task.own_robot_position(target_id)
            entries.append(
                (
                    target_id,
                    "red",
                    x,
                    y,
                    self._robot_collision_radius("red", target_id),
                )
            )
        if not moving_is_aerial and not (moving_team == "red" and moving_id == 8):
            entries.append(
                (
                    8,
                    "red",
                    self.sentry.x,
                    self.sentry.y,
                    ROBOT_ENTITY_COLLISION_RADIUS,
                )
            )
        return entries

    def _collision_bodies(
        self, moving_team: str, moving_id: int
    ) -> tuple[tuple[float, float, float], ...]:
        return tuple(
            (x, y, radius)
            for _, _, x, y, radius in self._collision_entries(moving_team, moving_id)
        )

    def _check_robot_collision(
        self,
        mover_team: str,
        mover_id: int,
        start: tuple[float, float],
        proposed: tuple[float, float],
        actual: tuple[float, float],
        *,
        moving_radius: float = ROBOT_ENTITY_COLLISION_RADIUS,
    ) -> None:
        if getattr(self, "_collision_damage_cooldown", 0.0) > 0.0:
            return
        if math.hypot(actual[0] - proposed[0], actual[1] - proposed[1]) <= 0.02:
            return
        entries = self._collision_entries(mover_team, mover_id)
        if not entries:
            return
        bodies = tuple((x, y, radius) for _, _, x, y, radius in entries)
        index = self.collision_grid.first_collision(
            start,
            proposed,
            collision_bodies=bodies,
            moving_radius=moving_radius,
        )
        if index is None:
            return
        target_id, target_team, target_x, target_y, target_radius = entries[index]
        if math.hypot(actual[0] - target_x, actual[1] - target_y) > (
            moving_radius + target_radius + 0.06
        ):
            return
        self.task.apply_collision_contact(
            mover_team,
            mover_id,
            target_team,
            target_id,
        )
        self._collision_damage_cooldown = 0.5

    @staticmethod
    def _robot_collision_radius(team: str, target_id: int) -> float:
        if target_id == 5:
            return AERIAL_COLLISION_RADIUS
        return ROBOT_ENTITY_COLLISION_RADIUS

    def _dynamic_planning_bodies(self) -> tuple[tuple[float, float, float], ...]:
        controlled_team = getattr(self, "controlled_robot_team", None)
        controlled_id = getattr(self, "controlled_robot_id", None)
        bodies = [
            (
                x,
                y,
                self._robot_collision_radius("blue", target_id),
            )
            for target_id in self.task.robot_positions
            if target_id != 5
            if not (controlled_team == "blue" and target_id == controlled_id)
            for x, y in (self.task.robot_position(target_id, team="blue"),)
        ]
        bodies.extend(
            (
                x,
                y,
                self._robot_collision_radius("red", target_id),
            )
            for target_id in self.task.own_robot_positions
            if target_id != 5
            if not (controlled_team == "red" and target_id == controlled_id)
            for x, y in (self.task.own_robot_position(target_id),)
        )
        return tuple(bodies)

    def _refresh_dynamic_planning_grid(self, *, force: bool = False) -> None:
        bodies = self._dynamic_planning_bodies()
        signature = tuple(
            (round(x, 1), round(y, 1), round(radius, 3))
            for x, y, radius in bodies
        )
        if not force and signature == self._planning_robot_signature:
            return
        self._planning_robot_signature = signature
        self.planning_grid = self.base_planning_grid.with_dynamic_obstacles(bodies)
        self.navigator.grid = self.planning_grid
        self.navigator.clear()

    def _move_controlled_robot(
        self, move_x: float, move_y: float, elapsed_seconds: float
    ) -> None:
        if getattr(self, "replay_mode", False):
            return
        target_id = self.controlled_robot_id
        team = self.controlled_robot_team
        if target_id is None or team not in ("blue", "red"):
            return
        if self.task.robot_chassis_power_cut(target_id, team=team):
            return
        if target_id == 1 and self.task.hero_deployment_active(team):
            power_map = self.task.robot_power if team == "blue" else self.task.own_robot_power
            power_map[target_id] = 0.0
            return
        start = self.task.robot_position(target_id, team=team)
        terrain_multiplier = self._terrain_speed_multiplier(start)
        self.task.move_robot(
            target_id,
            move_x,
            move_y,
            elapsed_seconds,
            self.arena,
            speed=3.0 * terrain_multiplier,
            team=team,
        )
        proposed = self.task.robot_position(target_id, team=team)
        proposed = self._apply_fly_slope_one_way(start, proposed)
        robot_radius = self._robot_collision_radius(team, target_id)
        collision_bodies = self._collision_bodies(team, target_id)
        resolved = self._move_with_special_wall_delay(
            team,
            target_id,
            start,
            proposed,
            elapsed_seconds=elapsed_seconds,
            collision_bodies=collision_bodies,
            moving_radius=robot_radius,
        )
        self.task.set_robot_position(target_id, resolved, team=team)
        self._check_robot_collision(
            team,
            target_id,
            start,
            proposed,
            resolved,
            moving_radius=robot_radius,
        )

    def _robot_chassis_state(self, team: str, target_id: int) -> SentryState:
        states = getattr(self, "robot_chassis_dynamics", None)
        if states is None:
            states = {}
            self.robot_chassis_dynamics = states
        key = (team, target_id)
        if key not in states:
            states[key] = SentryState()
        return states[key]

    def _update_other_robot_chassis_power(
        self,
        elapsed_seconds: float,
        move_x: float,
        move_y: float,
    ) -> None:
        """Reuse the sentry wrench model for every non-red-sentry robot."""
        if elapsed_seconds <= 0.0:
            return
        movement_length = math.hypot(move_x, move_y)
        if movement_length > 1.0:
            move_x /= movement_length
            move_y /= movement_length
        for team in ("red", "blue"):
            power_values = (
                self.task.own_robot_power
                if team == "red"
                else self.task.robot_power
            )
            for target_id in ROBOT_PROFILES:
                if team == "red" and target_id == 8:
                    continue
                state = self._robot_chassis_state(team, target_id)
                power_limit = self.task.robot_power_limit(target_id, team=team)
                if power_limit is None:
                    state.reset_chassis_dynamics()
                    power_values[target_id] = 0.0
                    continue
                if self.task.robot_chassis_power_cut(target_id, team=team):
                    state.reset_chassis_dynamics()
                    power_values[target_id] = 0.0
                    continue
                is_controlled = (
                    self.controlled_robot_team == team
                    and self.controlled_robot_id == target_id
                )
                chassis_move_x = move_x if is_controlled else 0.0
                chassis_move_y = move_y if is_controlled else 0.0
                if target_id == 1 and self.task.hero_deployment_active(team):
                    chassis_move_x = 0.0
                    chassis_move_y = 0.0
                turntable_speed = self.task.robot_turntable_speed(
                    target_id,
                    team=team,
                )
                state.update_chassis_power(
                    elapsed_seconds,
                    chassis_move_x * 3.0,
                    chassis_move_y * 3.0,
                    turntable_speed,
                )
                power_values[target_id] = state.chassis_power

    def _apply_fly_slope_one_way(
        self,
        start: tuple[float, float],
        proposed: tuple[float, float],
    ) -> tuple[float, float]:
        """Block travel through a fly slope in its forbidden direction."""
        delta_x = proposed[0] - start[0]
        if math.hypot(delta_x, proposed[1] - start[1]) <= 1e-9:
            return proposed

        polygons: list[tuple[tuple[float, float], ...]] = []
        base_points = normalize_points(
            getattr(self, "map_zone_overrides", {}).get("region_04_fly_slope")
        )
        if len(base_points) < 3:
            base_zone = next(
                (
                    zone
                    for zone in REGION_DEFINITIONS
                    if zone.name == "region_04_fly_slope"
                ),
                None,
            )
            base_points = normalize_points(base_zone.polygon if base_zone else ())
        if len(base_points) >= 3:
            polygons.append(base_points)
        for item in getattr(self, "custom_map_polygons", ()):
            if canonical_region_id(item.get("kind") or "") != "region_04_fly_slope":
                continue
            points = normalize_points(item.get("points"))
            if len(points) >= 3:
                polygons.append(points)

        for points in polygons:
            if not self._movement_touches_polygon(start, proposed, points):
                continue
            centre_y = sum(point[1] for point in points) / len(points)
            moving_in_allowed_direction = (
                delta_x > 1e-9
                if centre_y < self.arena.height / 2.0
                else delta_x < -1e-9
            )
            if not moving_in_allowed_direction:
                return start
        return proposed

    @classmethod
    def _movement_touches_polygon(
        cls,
        start: tuple[float, float],
        end: tuple[float, float],
        points: tuple[tuple[float, float], ...],
    ) -> bool:
        if cls._world_point_in_polygon(start, points):
            return True
        if cls._world_point_in_polygon(end, points):
            return True
        return any(
            cls._segments_intersect(start, end, edge_start, edge_end)
            for edge_start, edge_end in zip(points, points[1:] + points[:1])
        )

    @staticmethod
    def _segments_intersect(
        first_start: tuple[float, float],
        first_end: tuple[float, float],
        second_start: tuple[float, float],
        second_end: tuple[float, float],
    ) -> bool:
        epsilon = 1e-9
        if (
            max(first_start[0], first_end[0]) + epsilon
            < min(second_start[0], second_end[0])
            or max(second_start[0], second_end[0]) + epsilon
            < min(first_start[0], first_end[0])
            or max(first_start[1], first_end[1]) + epsilon
            < min(second_start[1], second_end[1])
            or max(second_start[1], second_end[1]) + epsilon
            < min(first_start[1], first_end[1])
        ):
            return False

        def cross(
            origin: tuple[float, float],
            first: tuple[float, float],
            second: tuple[float, float],
        ) -> float:
            return (
                (first[0] - origin[0]) * (second[1] - origin[1])
                - (first[1] - origin[1]) * (second[0] - origin[0])
            )

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

    def _terrain_speed_multiplier(self, position: tuple[float, float]) -> float:
        """Return terrain-only movement scaling without affecting power."""
        multipliers: list[float] = []
        for item in getattr(self, "slow_regions", ()):
            points = normalize_points(item.get("points"))
            if len(points) < 3 or not self._world_point_in_polygon(position, points):
                continue
            try:
                multipliers.append(float(item.get("speed_multiplier", 0.50)))
            except (TypeError, ValueError):
                multipliers.append(0.50)
        return max(0.05, min(1.0, min(multipliers, default=1.0)))

    @staticmethod
    def _world_point_in_polygon(position: tuple[float, float], points) -> bool:
        x, y = position
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

    @staticmethod
    def _spin_speed_scale(spin_mode: int) -> float:
        return {1: 0.6, 2: 1.0, 3: 1.6}.get(spin_mode, 0.0)

    def _track_selected_target(
        self,
        decision: DecisionView,
        elapsed_seconds: float,
    ) -> bool:
        if decision.target <= 0:
            return False
        try:
            target_x, target_y = self.task.target_position(decision.target)
        except ValueError:
            return False
        delta_x = target_x - self.sentry.x
        delta_y = target_y - self.sentry.y
        target_angle = math.atan2(delta_y, delta_x)
        if not self.task.target_in_sensor_view(
            (self.sentry.x, self.sentry.y),
            (target_x, target_y),
            self.sentry.turret_angle,
            maximum_distance=DETECTION_RANGE,
            half_angle=AUTOAIM_HALF_VIEW,
        ):
            return False
        difference = (
            target_angle - self.sentry.turret_angle + math.pi
        ) % math.tau - math.pi
        if abs(difference) > AUTOAIM_HALF_VIEW:
            return False
        maximum_step = self.sentry.turret_speed * elapsed_seconds
        step = max(-maximum_step, min(maximum_step, difference))
        self.sentry.turret_angle = (
            self.sentry.turret_angle + step + math.pi
        ) % math.tau - math.pi
        return True

    def _manual_fire_requested(self) -> bool:
        return self.sentry.manual_control and self._manual_fire_held

    def _gate_gimbal_by_alignment(self, decision: DecisionView) -> DecisionView:
        """Keep the gimbal rotating until the barrel is inside firing tolerance.

        ``shoot_mode`` means "ready to fire", not merely "the decision selected
        this target".  The gate only waits for the 4-degree firing alignment.
        """
        if decision.target <= 0:
            return decision
        error = self.task.aim_error(self.sentry, decision.target)
        if error is None:
            return decision
        if error <= FIRE_ALIGNMENT_TOLERANCE:
            return decision
        return replace(decision, tripod_mode=1, shoot_mode=0)

    def _local_decision(self) -> DecisionView:
        base = self.task.evaluate(self.sentry)
        if (
            self.task.game_finished
            or not self.task.game_running
            or self.task.sentry_hp <= 0.0
            or self.task.respawn_fire_locked
            or self.task.ammo <= 0
        ):
            return base

        autoaim = self._simulated_autoaim(self._enemy_health_snapshot())
        candidates = []
        for target_id in (1, 3, 4, 5, 8):
            health = self.task.enemy_health(target_id)
            if (
                autoaim["target"][target_id]
                and 0.0 < health < 50.0
                and health != 1001.0
            ):
                candidates.append(
                    (autoaim["target_distance"][target_id], target_id)
                )
        if not candidates:
            return base

        distance, target_id = min(candidates)
        if distance > ATTACK_RANGE:
            polar_radius = autoaim["target_polar_r"][target_id]
            polar_angle = autoaim["target_polar_angle"][target_id]
            map_angle = self.sentry.turret_angle + polar_angle
            target_x = self.sentry.x + polar_radius * math.cos(map_angle)
            target_y = self.sentry.y + polar_radius * math.sin(map_angle)
            delta_x = target_x - self.sentry.x
            delta_y = target_y - self.sentry.y
            length = max(1e-6, math.hypot(delta_x, delta_y))
            desired_distance = 2.8
            goal = self.arena.clamp(
                target_x - delta_x / length * desired_distance,
                target_y - delta_y / length * desired_distance,
            )
            return DecisionView(
                behavior="追击残血目标",
                posture=3,
                goal=goal,
                spin_mode=1,
                tripod_mode=1,
                shoot_mode=0,
                target=target_id,
                confirm_respawn=0,
                health_threshold=base.health_threshold,
            )

        return DecisionView(
            behavior="攻击残血目标",
            posture=1,
            goal=None,
            spin_mode=0,
            tripod_mode=1,
            shoot_mode=1,
            target=target_id,
            confirm_respawn=0,
            health_threshold=base.health_threshold,
        )

    def _bridge_decision(self) -> DecisionView | None:
        if not self.bridge.connected:
            return None
        output = self.bridge.latest_output()
        if output is None:
            return None
        serial = output.get("serial", {})
        autoaim = output.get("autoaim", {})
        raw_goal = output.get("goal")
        goal = tuple(raw_goal) if raw_goal is not None else None
        target = int(autoaim.get("target", 0))
        for legacy_goal, canonical_goal in LEGACY_GOAL_ALIASES:
            if self._near_goal(goal, legacy_goal):
                # Keep older BT goal coordinates on the same dataset-backed
                # field frame as local control, including the clear firing point.
                goal = canonical_goal
                break
        for fallback_route in (
            LEGACY_AGGRESSIVE_PATROL_POINTS,
            AGGRESSIVE_PATROL_POINTS,
        ):
            for legacy_goal, configured_goal in zip(
                fallback_route,
                self.task.aggressive_patrol_route,
            ):
                if self._near_goal(goal, legacy_goal):
                    # Compatibility with an older, not-yet-rebuilt BT process.
                    # A rebuilt process consumes the configured routes directly.
                    goal = tuple(configured_goal)
                    break
            else:
                continue
            break
        return DecisionView(
            behavior=self._bridge_behavior(goal, target),
            posture=int(serial.get("posture", 3)),
            goal=goal,
            spin_mode=int(serial.get("spin_mode", 0)),
            tripod_mode=int(serial.get("tripod_mode", 1)),
            shoot_mode=int(serial.get("shoot_mode", 0)),
            target=target,
            confirm_respawn=int(serial.get("confirm_respawn", 0)),
            health_threshold=self.task.health_threshold,
        )

    def _bridge_behavior(
        self,
        goal: tuple[float, float] | None,
        target: int,
    ) -> str:
        if self.task.sentry_hp <= 0.0:
            return "行为树：等待复活"
        if self.task.game_finished and self._near_goal(goal, HOME):
            return "行为树：比赛结束归位"
        if target == 6 or self._near_goal(goal, ATTACK):
            return "行为树：攻击敌方前哨"
        if self._near_goal(goal, SUPPLY):
            if self.task.respawn_fire_locked:
                return "行为树：复活后返回补给"
            if self.task.sentry_hp < self.task.health_threshold:
                return "行为树：低血量回血"
            return "行为树：前往补给区"
        if goal is not None and any(
            self._near_goal(goal, point) for point in self.task.patrol_points
        ):
            return f"行为树：{self.task.patrol_name}"
        if goal is not None:
            return "行为树：执行导航"
        return "行为树：等待输出"

    @staticmethod
    def _near_goal(
        first: tuple[float, float] | None,
        second: tuple[float, float],
        tolerance: float = 0.08,
    ) -> bool:
        return first is not None and math.hypot(
            first[0] - second[0],
            first[1] - second[1],
        ) <= tolerance

    def _bridge_state(self) -> dict:
        # The external behavior tree still controls only the red sentry. Enemy
        # positions now enter through the sentry's radar-only communication
        # inbox instead of being read directly from global simulation state.
        enemy_hp = self._enemy_health_snapshot()
        radar_data: list[float] = []
        radar_packet = self.task.received_team_message(
            "red",
            8,
            "radar_positions",
        )
        radar_positions = (
            (radar_packet.get("payload") or {}).get("positions") or {}
            if radar_packet is not None
            else {}
        )
        for target_id in (1, 2, 3, 4, 5, 8):
            position = radar_positions.get(target_id, radar_positions.get(str(target_id)))
            if not isinstance(position, (list, tuple)) or len(position) < 2:
                position = (0.0, 0.0)
            x, y = float(position[0]), float(position[1])
            radar_data.extend((x, y))
        return {
            "game_period": 2 if self.task.game_running else 0,
            "time": max(
                0,
                round(self.task.remaining_time)
                + (60 if self._restart_signal_remaining > 0.0 else 0),
            ),
            "hp_sentry": max(0, round(self.task.sentry_hp)),
            "defence_buff": self.task.defence_buff,
            "color": 0,
            "ammo": max(0, round(self.task.ammo)),
            "hp_outpost": max(0, round(self.task.own_outpost_hp)),
            "hp_base": max(0, round(self.task.own_base_hp)),
            "hp_enemy": enemy_hp,
            "radar_data": radar_data,
            "pending_ammo": max(0, round(self.task.pending_ammo)),
            "economy": max(0, round(self.task.economy)),
            "x": self.sentry.x,
            "y": self.sentry.y,
            "yaw": self.sentry.spin_angle,
            "camera_yaw": self.sentry.turret_angle,
            "autoaim": self._simulated_autoaim(enemy_hp),
            "aggressive_patrol": self.task.patrol_is_aggressive,
            "conservative_patrol_points": [
                list(point) for point in self.task.conservative_patrol_route
            ],
            "aggressive_patrol_points": [
                list(point) for point in self.task.aggressive_patrol_route
            ],
        }

    def _enemy_health_snapshot(self) -> list[int]:
        return [
            round(self.task.enemy_health(1)),
            round(self.task.enemy_health(2)),
            round(self.task.enemy_health(3)),
            round(self.task.enemy_health(4)),
            round(self.task.enemy_health(5)),
            round(self.task.enemy_health(6)),
            round(self.task.enemy_health(7)),
            round(self.task.enemy_health(8)),
        ]

    def _self_detects_enemy(self) -> bool:
        visible = self._simulated_autoaim(self._enemy_health_snapshot())["target"]
        return any(visible)

    def _simulated_autoaim(self, enemy_hp: list[int]) -> dict:
        visible = [0] * 9
        distances = [0.0] * 9
        polar_radius = [0.0] * 9
        polar_angle = [0.0] * 9
        positions = {
            target_id: self.task.robot_position(target_id)
            for target_id in (1, 2, 3, 4, 5, 8)
        }
        positions[6] = BLUE_OUTPOST
        positions[7] = BLUE_BASE
        for target_id, position in positions.items():
            health = enemy_hp[target_id - 1]
            if health <= 0 or health == 1001:
                continue
            delta_x = position[0] - self.sentry.x
            delta_y = position[1] - self.sentry.y
            distance = math.hypot(delta_x, delta_y)
            angle = math.atan2(delta_y, delta_x)
            relative_angle = (
                angle - self.sentry.turret_angle + math.pi
            ) % math.tau - math.pi
            if self.task.target_in_sensor_view(
                (self.sentry.x, self.sentry.y),
                position,
                self.sentry.turret_angle,
                maximum_distance=DETECTION_RANGE,
                half_angle=AUTOAIM_HALF_VIEW,
            ):
                visible[target_id] = 1
                distances[target_id] = distance
                polar_radius[target_id] = distance
                polar_angle[target_id] = relative_angle
        return {
            "target": visible,
            "target_distance": distances,
            "target_polar_r": polar_radius,
            "target_polar_angle": polar_angle,
        }
