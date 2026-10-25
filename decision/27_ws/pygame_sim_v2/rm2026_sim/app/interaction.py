"""地图图层、地图编辑器和鼠标交互。

编辑器状态仍然属于应用对象，但具体操作集中在此模块，主类只负责组装。
"""

from __future__ import annotations

from .main import *


class InteractionMixin:
    def _select_own_robot_function_key(self, key: int) -> None:
        """Select the friendly robot whose id matches the function key."""
        key_to_target = {
            self.pg.K_F1: 1,
            self.pg.K_F2: 2,
            self.pg.K_F3: 3,
            self.pg.K_F4: 4,
            self.pg.K_F5: 5,
            self.pg.K_F8: 8,
        }
        target_id = key_to_target.get(key)
        if target_id is not None:
            self._select_own_robot(target_id)

    def _toggle_map_layer(self, layer: str) -> None:
        """Toggle one map overlay and keep legacy flags in sync."""
        if layer not in self.map_layer_visibility:
            return
        visible = not self.map_layer_visibility[layer]
        self.map_layer_visibility[layer] = visible
        if layer == "collision_volumes":
            self.show_collision_volumes = visible
        if layer.startswith("custom:"):
            identifier = layer.split(":", 1)[1]
            for item in self.custom_map_polygons:
                if item.get("id") == identifier:
                    item["visible"] = visible
                    break
            self._save_persistent_geometry()
        if layer.startswith("zone:"):
            kind = canonical_region_id(layer.split(":", 1)[1])
            # A numbered region can consist of several separate polygons.
            # The family switch controls all of its parts together, while the
            # per-part buttons below can still hide one part independently.
            for item in self.custom_map_polygons:
                if canonical_region_id(item.get("kind") or "") != kind:
                    continue
                identifier = str(item.get("id"))
                self.map_layer_visibility[f"custom:{identifier}"] = visible
                item["visible"] = visible
            self.show_field_zones = any(
                self.map_layer_visibility.get(f"zone:{kind}", False)
                for kind, _ in FIELD_ZONE_KIND_LABELS
            )
            self._save_persistent_geometry()

    def _set_all_map_layers(self, visible: bool) -> None:
        for layer in self.map_layer_visibility:
            self.map_layer_visibility[layer] = visible
        for item in self.custom_map_polygons:
            item["visible"] = visible
        self.show_collision_volumes = visible
        self.show_field_zones = visible
        self._save_persistent_geometry()

    def _toggle_all_field_zones(self) -> None:
        show_zones = not self.show_field_zones
        for kind, _ in FIELD_ZONE_KIND_LABELS:
            self.map_layer_visibility[f"zone:{kind}"] = show_zones
        self.show_field_zones = show_zones

    def _scroll_map_editor_list(
        self,
        wheel_y: int,
        position: tuple[int, int],
    ) -> bool:
        """Scroll whichever map-editor list is under the mouse pointer."""
        if not self.map_layers_panel_open:
            return False
        tab = getattr(self, "map_editor_tab", "layers")
        if tab == "layers":
            if not getattr(self, "map_region_editor_open", False):
                return False
            scroll_rect = getattr(self, "map_region_scroll_rect", None)
            if scroll_rect is None or not scroll_rect.collidepoint(position):
                return False
            width = max(
                280,
                self.screen.get_width() - SIDE_PANEL_WIDTH - RIGHT_PANEL_WIDTH - 16,
            )
            columns = max(1, min(3, width // 360))
            item_count = len(REGION_DEFINITIONS) + len(self.custom_map_polygons)
            total_rows = math.ceil(item_count / columns) if item_count else 0
            maximum = max(0, total_rows - MAP_REGION_VISIBLE_ROWS)
            current = max(
                0,
                min(maximum, int(getattr(self, "map_region_scroll_offset", 0))),
            )
            self.map_region_scroll_offset = max(
                0,
                min(maximum, current - int(wheel_y)),
            )
            return True
        if (
            not getattr(self, "map_extra_list_open", True)
            or tab not in ("walls", "special", "slow")
        ):
            return False
        scroll_rect = getattr(self, "map_extra_scroll_rect", None)
        if scroll_rect is None or not scroll_rect.collidepoint(position):
            return False
        items = (
            self.wall_polygons
            if tab == "walls"
            else self.special_regions
            if tab == "special"
            else self.slow_regions
        )
        maximum = max(0, len(items) - MAP_EXTRA_VISIBLE_ROWS)
        offsets = getattr(
            self,
            "map_extra_scroll_offsets",
            {"walls": 0, "special": 0, "slow": 0},
        )
        current = max(0, min(maximum, int(offsets.get(tab, 0))))
        offsets[tab] = max(0, min(maximum, current - int(wheel_y) * 2))
        self.map_extra_scroll_offsets = offsets
        return True

    # Compatibility alias for older callers.
    def _scroll_map_extra_list(
        self,
        wheel_y: int,
        position: tuple[int, int],
    ) -> bool:
        return self._scroll_map_editor_list(wheel_y, position)

    def _zone_named(self, name: str):
        canonical_name = canonical_region_id(name)
        return next(
            (zone for zone in REGION_DEFINITIONS if zone.name == canonical_name),
            None,
        )

    def _zone_points(self, zone) -> tuple[tuple[float, float], ...]:
        """Return the currently configured world polygon for a field zone."""
        if zone.name in self.map_zone_overrides:
            return normalize_points(self.map_zone_overrides[zone.name])
        if zone.polygon:
            return tuple((float(x), float(y)) for x, y in zone.polygon)
        return ()

    def _sync_task_zone_overrides(self) -> None:
        self.task.field_zone_overrides = {
            name: [[float(x), float(y)] for x, y in points]
            for name, points in self.map_zone_overrides.items()
        }
        terrain_kinds = {
            "region_02_road": "road",
            "region_03_tunnel": "tunnel",
            "region_04_fly_slope": "fly_slope",
            "region_08_highland": "highland",
            "region_11_central_highland": "highland",
        }
        raw_cards: list[dict] = []

        def append_terrain_card(
            card_id: str,
            kind: str,
            source_region: str,
            name: str,
            points,
        ) -> None:
            """Append one card, expanding a full tunnel route into three cards."""
            payload = {
                "id": card_id,
                "kind": kind,
                "source_region": source_region,
                "name": name,
                "points": points,
            }
            if kind != "tunnel":
                raw_cards.append(payload)
                return

            min_x = min(point[0] for point in points)
            max_x = max(point[0] for point in points)
            min_y = min(point[1] for point in points)
            max_y = max(point[1] for point in points)
            width = max_x - min_x
            height = max_y - min_y
            short_side = max(1e-6, min(width, height))
            # Existing tunnel annotations outline the complete physical route
            # containing an end card, a narrow middle card and the other end.
            # Compact annotations remain individual cards for compatibility.
            if max(width, height) / short_side < 1.8:
                raw_cards.append(payload)
                return

            route_team = "red" if (min_x + max_x) / 2.0 < FIELD_WIDTH / 2.0 else "blue"
            spans = ((0.00, 0.36), (0.43, 0.57), (0.64, 1.00))
            for part_index, (start_ratio, end_ratio) in enumerate(spans):
                if width >= height:
                    start = min_x + width * start_ratio
                    end = min_x + width * end_ratio
                    part_points = (
                        (start, max_y),
                        (start, min_y),
                        (end, min_y),
                        (end, max_y),
                    )
                else:
                    start = min_y + height * start_ratio
                    end = min_y + height * end_ratio
                    part_points = (
                        (min_x, end),
                        (min_x, start),
                        (max_x, start),
                        (max_x, end),
                    )
                raw_cards.append(
                    {
                        "id": f"{card_id}:part{part_index}",
                        "kind": kind,
                        "source_region": source_region,
                        "name": name,
                        "points": part_points,
                        "field_team": route_team,
                    }
                )

        for region_id, kind in terrain_kinds.items():
            points = normalize_points(self.map_zone_overrides.get(region_id))
            if validate_polygon(points) is None:
                append_terrain_card(
                    f"zone:{region_id}",
                    kind,
                    region_id,
                    region_id,
                    points,
                )
            for item in getattr(self, "custom_map_polygons", []):
                if canonical_region_id(item.get("kind") or "") != region_id:
                    continue
                points = normalize_points(item.get("points"))
                if validate_polygon(points) is not None:
                    continue
                append_terrain_card(
                    f"custom:{item.get('id')}",
                    kind,
                    region_id,
                    str(item.get("name") or ""),
                    points,
                )

        grouped: dict[tuple[str, str], list[dict]] = {}
        for card in raw_cards:
            name = str(card.get("name") or "").lower()
            # The two fly-slope strips form one neutral crossing pair.  Their
            # centres may fall on opposite sides of midfield, so assigning a
            # field team by X would split the pair and make the gain
            # impossible to complete.
            preset_team = str(card.get("field_team") or "")
            if preset_team in ("red", "blue", "neutral"):
                field_team = preset_team
            elif card.get("kind") == "fly_slope":
                field_team = "neutral"
            elif "红" in name or "red" in name:
                field_team = "red"
            elif "蓝" in name or "blue" in name:
                field_team = "blue"
            else:
                average_x = sum(point[0] for point in card["points"]) / len(card["points"])
                field_team = "red" if average_x < FIELD_WIDTH / 2.0 else "blue"
            card["field_team"] = field_team
            grouped.setdefault((str(card["kind"]), field_team), []).append(card)

        central_zones = [
            {"id": card["id"], "points": card["points"]}
            for card in raw_cards
            if card.get("source_region") == "region_11_central_highland"
        ]
        configure_central = getattr(self.task, "set_central_highland_zones", None)
        if callable(configure_central):
            configure_central(central_zones)

        terrain_cards: list[dict] = []
        card_counts = {"road": 2, "highland": 2, "fly_slope": 2, "tunnel": 3}
        for (kind, field_team), cards in grouped.items():
            if kind == "fly_slope":
                # A fly-slope route is the nearest pair of green interaction
                # cards on the same physical slope.  Do not pair cards merely
                # by creation order, because that can incorrectly join the
                # upper and lower slopes.
                remaining = list(cards)
                route = 0
                while remaining:
                    first = remaining.pop(0)
                    pair = [first]
                    if remaining:
                        first_x = sum(point[0] for point in first["points"]) / len(first["points"])
                        first_y = sum(point[1] for point in first["points"]) / len(first["points"])
                        partner_index = min(
                            range(len(remaining)),
                            key=lambda index: (
                                (
                                    sum(point[0] for point in remaining[index]["points"])
                                    / len(remaining[index]["points"])
                                    - first_x
                                ) ** 2
                                + (
                                    sum(point[1] for point in remaining[index]["points"])
                                    / len(remaining[index]["points"])
                                    - first_y
                                ) ** 2
                            ),
                        )
                        pair.append(remaining.pop(partner_index))
                    for order, card in enumerate(pair):
                        terrain_cards.append(
                            {
                                "id": card["id"],
                                "kind": kind,
                                "field_team": field_team,
                                "route": route,
                                "order": order,
                                "points": card["points"],
                            }
                        )
                    route += 1
                continue
            if kind == "highland":
                lower_cards = [
                    card
                    for card in cards
                    if card.get("source_region") == "region_08_highland"
                ]
                upper_cards = [
                    card
                    for card in cards
                    if card.get("source_region") == "region_11_central_highland"
                ]
                for route, card in enumerate(lower_cards):
                    terrain_cards.append(
                        {
                            "id": card["id"],
                            "kind": kind,
                            "field_team": field_team,
                            "route": route,
                            "order": 0,
                            "points": card["points"],
                        }
                    )
                for route, card in enumerate(upper_cards):
                    terrain_cards.append(
                        {
                            "id": card["id"],
                            "kind": kind,
                            "field_team": field_team,
                            "route": route,
                            "order": 1,
                            "points": card["points"],
                        }
                    )
                continue
            required = card_counts[kind]
            for index, card in enumerate(cards):
                terrain_cards.append(
                    {
                        "id": card["id"],
                        "kind": kind,
                        "field_team": field_team,
                        "route": index // required,
                        "order": index % required,
                        "points": card["points"],
                    }
                )
        configure_cards = getattr(self.task, "set_terrain_crossing_cards", None)
        if callable(configure_cards):
            configure_cards(terrain_cards)

    def _sync_task_patrol_routes(self) -> None:
        """Apply the globally edited routes to local and bridged decisions."""
        self.task.configure_patrol_routes(
            self.patrol_routes["conservative"],
            self.patrol_routes["aggressive"],
        )

    def _save_persistent_geometry(self) -> bool:
        """Persist map annotations independently of the currently selected scene."""
        path = getattr(self, "map_geometry_path", None)
        if path is None:
            # Deliberately refuse to guess the production path.  This protects
            # the real annotations when unit tests construct a partial app via
            # SimulatorApp.__new__(SimulatorApp).
            return False
        try:
            save_geometry_file(
                path,
                self.map_zone_overrides,
                self.custom_map_polygons,
                patrol_routes=self.patrol_routes,
                wall_polygons=getattr(self, "wall_polygons", ()),
                special_regions=getattr(self, "special_regions", ()),
                slow_regions=getattr(self, "slow_regions", ()),
            )
        except OSError:
            self.task.notify("区域已更新，但永久配置写入失败，请检查目录权限")
            return False
        self._persistent_geometry_loaded = True
        return True

    def _rebuild_collision_grids(self) -> None:
        """Rebuild map collision layers after editable walls change."""
        wall_points = self._wall_collision_polygons(self.wall_polygons)
        special_wall_entries: list[
            tuple[str, tuple[tuple[float, float], ...]]
        ] = []
        for index, item in enumerate(self.special_regions, start=1):
            polygons = self._wall_collision_polygons((item,))
            if not polygons:
                continue
            special_wall_entries.append((
                str(item.get("id") or f"special_{index}"),
                polygons[0],
            ))
        special_wall_points = [polygon for _, polygon in special_wall_entries]
        all_wall_points = wall_points + special_wall_points
        self.collision_grid = OccupancyGrid.empty(
            self.arena,
        ).with_blocked_rectangles(
            STATIC_COLLISION_RECTANGLES,
            inflation=ROBOT_ENTITY_COLLISION_RADIUS,
        ).with_blocked_polygons(
            all_wall_points,
            inflation=ROBOT_ENTITY_COLLISION_RADIUS,
        )
        # Engineer and 3/4 infantry use this grid after their one-second
        # traverse delay; they still collide with every normal wall.
        self.infantry_collision_grid = OccupancyGrid.empty(
            self.arena,
        ).with_blocked_rectangles(
            STATIC_COLLISION_RECTANGLES,
            inflation=ROBOT_ENTITY_COLLISION_RADIUS,
        ).with_blocked_polygons(
            wall_points,
            inflation=ROBOT_ENTITY_COLLISION_RADIUS,
        )
        # Aerial robots ignore every authored wall. This grid deliberately
        # contains only the arena boundary.
        self.aerial_collision_grid = OccupancyGrid.empty(
            self.arena,
            collision_radius=AERIAL_COLLISION_RADIUS,
        )
        self.special_wall_collision_polygons = tuple(special_wall_entries)
        self.special_wall_individual_grids = {
            identifier: self.infantry_collision_grid.with_blocked_polygons(
                (polygon,),
                inflation=ROBOT_ENTITY_COLLISION_RADIUS,
            )
            for identifier, polygon in special_wall_entries
        }
        self.special_wall_only_grids = {
            identifier: OccupancyGrid.empty(
                self.arena,
                collision_radius=0.0,
            ).with_blocked_polygons(
                (polygon,),
                inflation=ROBOT_ENTITY_COLLISION_RADIUS,
            )
            for identifier, polygon in special_wall_entries
        }
        self.los_grid = OccupancyGrid.empty(
            self.arena,
            collision_radius=0.0,
        ).with_blocked_rectangles(
            STATIC_COLLISION_RECTANGLES,
            inflation=0.0,
        ).with_blocked_polygons(all_wall_points, inflation=0.0)
        self.planning_grid = OccupancyGrid.empty(
            self.arena,
            collision_radius=ASTAR_PLANNING_RADIUS,
        ).with_blocked_rectangles(
            STATIC_COLLISION_RECTANGLES,
            inflation=ASTAR_PLANNING_RADIUS,
        ).with_blocked_polygons(
            all_wall_points,
            inflation=ASTAR_PLANNING_RADIUS,
        )
        self.base_planning_grid = self.planning_grid
        if hasattr(self, "navigator"):
            self.navigator.grid = self.planning_grid
            self.navigator.clear()
        getattr(self, "special_wall_traverse_timers", {}).clear()
        getattr(self, "special_wall_traverse_active", set()).clear()

    def _wall_collision_polygons(
        self,
        wall_items,
    ) -> list[tuple[tuple[float, float], ...]]:
        """Convert editable wall segments into thick collision rectangles."""
        polygons: list[tuple[tuple[float, float], ...]] = []
        for item in wall_items:
            if not isinstance(item, dict):
                continue
            points = normalize_points(item.get("points"))
            if len(points) < 2:
                continue
            start, end = points[0], points[1]
            delta_x = end[0] - start[0]
            delta_y = end[1] - start[1]
            length = math.hypot(delta_x, delta_y)
            if length <= 1e-6:
                continue
            try:
                thickness = float(item.get("thickness", DEFAULT_WALL_THICKNESS))
            except (TypeError, ValueError):
                thickness = DEFAULT_WALL_THICKNESS
            half = max(0.025, min(1.0, thickness * 0.5))
            direction_x = delta_x / length
            direction_y = delta_y / length
            normal_x = -direction_y * half
            normal_y = direction_x * half
            start_x = start[0] - direction_x * half
            start_y = start[1] - direction_y * half
            end_x = end[0] + direction_x * half
            end_y = end[1] + direction_y * half
            polygons.append((
                (start_x + normal_x, start_y + normal_y),
                (end_x + normal_x, end_y + normal_y),
                (end_x - normal_x, end_y - normal_y),
                (start_x - normal_x, start_y - normal_y),
            ))
        return polygons

    def _region_type_configured(self, kind: str) -> bool:
        """Return whether a type has at least one valid polygon."""
        if len(normalize_points(self.map_zone_overrides.get(kind))) >= 3:
            return True
        return any(
            canonical_region_id(item.get("kind") or REGION_TYPES[0][0]) == kind
            and validate_polygon(normalize_points(item.get("points"))) is None
            for item in self.custom_map_polygons
        )

    def _missing_required_regions(self) -> list[str]:
        missing: list[str] = []
        for zone in REGION_DEFINITIONS:
            if zone.name in self.map_zone_overrides and not self._region_type_configured(zone.name):
                missing.append(zone.label or zone.name)
        return missing

    def _start_region_edit(self, target: str) -> None:
        target = canonical_region_id(target)
        zone = self._zone_named(target)
        if zone is None:
            return
        self.region_edit_target = target
        self.region_edit_custom_id = None
        self.region_edit_patrol_kind = None
        self.region_edit_kind = target
        self.region_edit_new_custom = False
        self.region_edit_points = list(self._zone_points(zone))
        self.region_edit_drag_index = None
        self.region_edit_error = ""
        self.task.notify(f"正在编辑{zone.label or zone.name}：拖动顶点或点击边线添加点")

    def _start_patrol_route_edit(self, route_kind: str) -> None:
        if route_kind not in ("conservative", "aggressive"):
            return
        self.region_edit_target = None
        self.region_edit_custom_id = None
        self.region_edit_kind = None
        self.region_edit_patrol_kind = route_kind
        self.region_edit_new_custom = False
        self.region_edit_points = list(self.patrol_routes[route_kind])
        self.region_edit_drag_index = None
        self.region_edit_error = ""
        label = "保守" if route_kind == "conservative" else "激进"
        self.map_layer_visibility["patrol_route"] = True
        self.task.notify(f"正在编辑{label}巡逻路线：按顺序点击添加点，右键撤销末点")

    def _start_custom_region(self, kind: str | None = None) -> None:
        self.region_edit_target = None
        self.region_edit_custom_id = None
        self.region_edit_patrol_kind = None
        candidate = canonical_region_id(kind or REGION_TYPES[0][0])
        allowed = {identifier for identifier, _ in REGION_TYPES}
        self.region_edit_kind = candidate if candidate in allowed else REGION_TYPES[0][0]
        self.region_edit_new_custom = True
        self.region_edit_points = []
        self.region_edit_drag_index = None
        self.region_edit_error = ""
        self.task.notify("正在新建自定义区域：左键添加点，右键撤销")

    def _start_wall_edit(self, identifier: str | None = None) -> None:
        item = next(
            (item for item in self.wall_polygons if str(item.get("id")) == str(identifier)),
            None,
        ) if identifier is not None else None
        self.region_edit_target = None
        self.region_edit_custom_id = None
        self.region_edit_kind = None
        self.region_edit_patrol_kind = None
        self.region_edit_wall_id = str(identifier) if item is not None else None
        self.region_edit_special_id = None
        self.region_edit_slow_id = None
        self.region_edit_new_wall = item is None
        self.region_edit_new_special = False
        self.region_edit_new_slow = False
        self.region_edit_points = list(normalize_points(item.get("points"))) if item else []
        self.region_edit_drag_index = None
        self.region_edit_error = ""
        self.map_editor_tab = "walls"
        # Give the map maximum space while placing or dragging wall endpoints.
        self.map_extra_list_open = False
        self.map_layer_visibility["editable_walls"] = True
        self.task.notify("正在绘制墙体线段：依次点击起点和终点，默认厚度 0.20 米")

    def _start_special_edit(self, identifier: str | None = None) -> None:
        item = next(
            (item for item in self.special_regions if str(item.get("id")) == str(identifier)),
            None,
        ) if identifier is not None else None
        self.region_edit_target = None
        self.region_edit_custom_id = None
        self.region_edit_kind = None
        self.region_edit_patrol_kind = None
        self.region_edit_wall_id = None
        self.region_edit_special_id = str(identifier) if item is not None else None
        self.region_edit_slow_id = None
        self.region_edit_new_wall = False
        self.region_edit_new_special = item is None
        self.region_edit_new_slow = False
        self.region_edit_points = list(normalize_points(item.get("points"))) if item else []
        self.region_edit_drag_index = None
        self.region_edit_error = ""
        self.map_editor_tab = "special"
        # Hide the long object list while the line itself is being edited.
        self.map_extra_list_open = False
        self.map_layer_visibility["special_regions"] = True
        self.task.notify("正在绘制特殊墙体：双方工程、3/4 号步兵持续接触 1 秒后可翻越")

    def _start_slow_edit(self, identifier: str | None = None) -> None:
        item = next(
            (item for item in self.slow_regions if str(item.get("id")) == str(identifier)),
            None,
        ) if identifier is not None else None
        self.region_edit_target = None
        self.region_edit_custom_id = None
        self.region_edit_kind = None
        self.region_edit_patrol_kind = None
        self.region_edit_wall_id = None
        self.region_edit_special_id = None
        self.region_edit_slow_id = str(identifier) if item is not None else None
        self.region_edit_new_wall = False
        self.region_edit_new_special = False
        self.region_edit_new_slow = item is None
        self.region_edit_points = list(normalize_points(item.get("points"))) if item else []
        self.region_edit_drag_index = None
        self.region_edit_error = ""
        self.map_editor_tab = "slow"
        self.map_extra_list_open = False
        self.map_layer_visibility["slow_regions"] = True
        self.task.notify("正在绘制减速区域：区域内移动速度为 50%，底盘功率不变")

    def _start_custom_edit(self, identifier: str) -> None:
        item = next(
            (item for item in self.custom_map_polygons if item.get("id") == identifier),
            None,
        )
        if item is None:
            return
        self.region_edit_target = None
        self.region_edit_patrol_kind = None
        self.region_edit_custom_id = identifier
        candidate = canonical_region_id(item.get("kind") or REGION_TYPES[0][0])
        allowed = {identifier for identifier, _ in REGION_TYPES}
        self.region_edit_kind = candidate if candidate in allowed else REGION_TYPES[0][0]
        self.region_edit_new_custom = False
        self.region_edit_points = list(normalize_points(item.get("points")))
        self.region_edit_drag_index = None
        self.region_edit_error = ""
        self.task.notify(f"正在编辑{item.get('name', '自定义区域')}：拖动顶点或点击边线添加点")

    def _cancel_region_edit(self) -> None:
        was_extra_geometry_edit = (
            self.region_edit_new_wall
            or self.region_edit_wall_id is not None
            or self.region_edit_new_special
            or self.region_edit_special_id is not None
            or self.region_edit_new_slow
            or self.region_edit_slow_id is not None
        )
        self.region_edit_target = None
        self.region_edit_custom_id = None
        self.region_edit_kind = None
        self.region_edit_patrol_kind = None
        self.region_edit_new_custom = False
        self.region_edit_points = []
        self.region_edit_drag_index = None
        self.region_edit_error = ""
        self.region_edit_wall_id = None
        self.region_edit_special_id = None
        self.region_edit_slow_id = None
        self.region_edit_new_wall = False
        self.region_edit_new_special = False
        self.region_edit_new_slow = False
        if was_extra_geometry_edit:
            self.map_extra_list_open = True

    def _clear_region_edit(self) -> None:
        self.region_edit_points = []
        self.region_edit_drag_index = None
        self.region_edit_error = ""

    def _save_region_edit(self) -> bool:
        points = normalize_points(self.region_edit_points)
        if self.region_edit_patrol_kind is not None:
            if len(points) < 2:
                self.region_edit_error = "巡逻路线至少需要 2 个点"
                self.task.notify("巡逻路线不能保存：至少需要 2 个点")
                return False
            route_kind = self.region_edit_patrol_kind
            self.patrol_routes[route_kind] = points
            self._sync_task_patrol_routes()
            self._save_persistent_geometry()
            label = "保守" if route_kind == "conservative" else "激进"
            self.task.notify(f"已保存{label}巡逻路线，并同步到行为树输入")
            self._cancel_region_edit()
            return True
        if self.region_edit_new_wall or self.region_edit_wall_id is not None:
            if len(points) != 2:
                self.region_edit_error = "墙体线段需要起点和终点"
                self.task.notify("墙体不能保存：请设置两个端点")
                return False
            if self.region_edit_wall_id is None:
                wall_number = len(self.wall_polygons) + 1
                identifier = f"wall_{wall_number}"
                while any(str(item.get("id")) == identifier for item in self.wall_polygons):
                    wall_number += 1
                    identifier = f"wall_{wall_number}"
                self.wall_polygons.append({
                    "id": identifier,
                    "name": f"墙体 {wall_number}",
                    "points": [[x, y] for x, y in points[:2]],
                    "thickness": DEFAULT_WALL_THICKNESS,
                    "color": [225, 72, 72],
                    "visible": True,
                })
            else:
                item = next(
                    item for item in self.wall_polygons
                    if str(item.get("id")) == self.region_edit_wall_id
                )
                item["points"] = [[x, y] for x, y in points[:2]]
                item.setdefault("thickness", DEFAULT_WALL_THICKNESS)
            self._save_persistent_geometry()
            self._rebuild_collision_grids()
            self._refresh_dynamic_planning_grid(force=True)
            self.task.notify("墙体已保存，已更新碰撞和导航栅格")
            self._cancel_region_edit()
            return True
        if self.region_edit_new_special or self.region_edit_special_id is not None:
            if len(points) != 2:
                self.region_edit_error = "特殊墙体需要起点和终点"
                self.task.notify("特殊墙体不能保存：请设置两个端点")
                return False
            if self.region_edit_special_id is None:
                special_number = len(self.special_regions) + 1
                identifier = f"special_{special_number}"
                while any(str(item.get("id")) == identifier for item in self.special_regions):
                    special_number += 1
                    identifier = f"special_{special_number}"
                self.special_regions.append({
                    "id": identifier,
                    "name": f"特殊墙体 {special_number}",
                    "points": [[x, y] for x, y in points[:2]],
                    "thickness": DEFAULT_WALL_THICKNESS,
                    "color": [235, 180, 70],
                    "visible": True,
                })
            else:
                item = next(
                    item for item in self.special_regions
                    if str(item.get("id")) == self.region_edit_special_id
                )
                item["points"] = [[x, y] for x, y in points[:2]]
                item.setdefault("thickness", DEFAULT_WALL_THICKNESS)
            self._save_persistent_geometry()
            self._rebuild_collision_grids()
            self._refresh_dynamic_planning_grid(force=True)
            self.task.notify("特殊墙体已保存：工程、3/4 号步兵需持续翻越 1 秒")
            self._cancel_region_edit()
            return True
        if self.region_edit_new_slow or self.region_edit_slow_id is not None:
            error = validate_polygon(points)
            if error is not None:
                self.region_edit_error = error
                self.task.notify(f"减速区域不能保存：{error}")
                return False
            if self.region_edit_slow_id is None:
                slow_number = len(self.slow_regions) + 1
                identifier = f"slow_{slow_number}"
                while any(str(item.get("id")) == identifier for item in self.slow_regions):
                    slow_number += 1
                    identifier = f"slow_{slow_number}"
                self.slow_regions.append({
                    "id": identifier,
                    "name": f"减速区域 {slow_number}",
                    "points": [[x, y] for x, y in points],
                    "speed_multiplier": DEFAULT_SLOW_REGION_MULTIPLIER,
                    "color": [86, 174, 220],
                    "visible": True,
                })
            else:
                item = next(
                    item for item in self.slow_regions
                    if str(item.get("id")) == self.region_edit_slow_id
                )
                item["points"] = [[x, y] for x, y in points]
                item["speed_multiplier"] = DEFAULT_SLOW_REGION_MULTIPLIER
            self._save_persistent_geometry()
            self.task.notify("减速区域已保存：速度 50%，底盘功率不变")
            self._cancel_region_edit()
            return True
        error = validate_polygon(points)
        if error is not None:
            self.region_edit_error = error
            self.task.notify(f"区域不能保存：{error}")
            return False
        if self.region_edit_target is not None:
            self.map_zone_overrides[self.region_edit_target] = points
            self.map_layer_visibility[f"zone:{self.region_edit_target}"] = True
            self._sync_task_zone_overrides()
            zone = self._zone_named(self.region_edit_target)
            self.task.notify(f"已保存{zone.label if zone else self.region_edit_target}")
        else:
            if self.region_edit_custom_id is None:
                identifier = f"custom_{self.region_edit_counter}"
                while any(item.get("id") == identifier for item in self.custom_map_polygons):
                    self.region_edit_counter += 1
                    identifier = f"custom_{self.region_edit_counter}"
                self.region_edit_counter += 1
                definition = next(
                    (item for item in REGION_DEFINITIONS
                     if item.name == self.region_edit_kind),
                    REGION_DEFINITIONS[0],
                )
                self.custom_map_polygons.append({
                    "id": identifier,
                    "kind": canonical_region_id(definition.name),
                    "name": f"{definition.label} {len(self.custom_map_polygons) + 1}",
                    "points": [[x, y] for x, y in points],
                    "color": list(definition.color),
                    "visible": True,
                })
                self.map_layer_visibility[f"custom:{identifier}"] = True
                self.map_layer_visibility[f"zone:{definition.name}"] = True
                self.task.notify(f"已添加{definition.label}")
            else:
                item = next(
                    (item for item in self.custom_map_polygons
                     if item.get("id") == self.region_edit_custom_id),
                    None,
                )
                if item is None:
                    self.region_edit_error = "区域已不存在"
                    return False
                item["points"] = [[x, y] for x, y in points]
                if self.region_edit_kind:
                    item["kind"] = canonical_region_id(self.region_edit_kind)
                self.task.notify(f"已保存{item.get('name', '自定义区域')}")
        self._save_persistent_geometry()
        self._cancel_region_edit()
        return True

    def _delete_region(self, target: tuple[str, str]) -> None:
        kind, identifier = target
        if kind == "zone":
            region_kind = canonical_region_id(identifier)
            if self._zone_named(region_kind) is None:
                return
            # Delete only the base polygon. Extra parts of the same numbered
            # region remain intact and continue to participate in rules.
            self.map_zone_overrides[region_kind] = ()
            self._sync_task_zone_overrides()
            self._save_persistent_geometry()
            if self.region_edit_target == region_kind:
                self._cancel_region_edit()
            zone = self._zone_named(region_kind)
            self.task.notify(
                f"已删除{zone.label if zone else region_kind}的基础部分，其他分段已保留"
            )
            return
        elif kind == "custom":
            item = next(
                (item for item in self.custom_map_polygons
                 if str(item.get("id")) == str(identifier)),
                None,
            )
            if item is None:
                return
            region_kind = canonical_region_id(item.get("kind") or REGION_TYPES[0][0])
            # Custom polygons are independent parts. Remove only the selected
            # part instead of erasing every polygon in the same family.
            self.custom_map_polygons = [
                candidate for candidate in self.custom_map_polygons
                if str(candidate.get("id")) != str(identifier)
            ]
            self.map_layer_visibility.pop(f"custom:{identifier}", None)
            self._sync_task_zone_overrides()
            self._save_persistent_geometry()
            if self.region_edit_custom_id == str(identifier):
                self._cancel_region_edit()
            self.task.notify(
                f"已删除{item.get('name', identifier)}，同类型其他分段已保留"
            )
            return
        else:
            return

    def _delete_editable_geometry(self, kind: str, identifier: str) -> None:
        if kind == "wall":
            self.wall_polygons = [
                item for item in self.wall_polygons
                if str(item.get("id")) != str(identifier)
            ]
            self._rebuild_collision_grids()
            self._refresh_dynamic_planning_grid(force=True)
            message = "墙体已删除，已更新碰撞和导航栅格"
        elif kind == "special":
            self.special_regions = [
                item for item in self.special_regions
                if str(item.get("id")) != str(identifier)
            ]
            self._rebuild_collision_grids()
            self._refresh_dynamic_planning_grid(force=True)
            message = "特殊墙体已删除"
        elif kind == "slow":
            self.slow_regions = [
                item for item in self.slow_regions
                if str(item.get("id")) != str(identifier)
            ]
            message = "减速区域已删除"
        else:
            return
        self._save_persistent_geometry()
        if (
            self.region_edit_wall_id == str(identifier)
            or self.region_edit_special_id == str(identifier)
            or self.region_edit_slow_id == str(identifier)
        ):
            self._cancel_region_edit()
        self.task.notify(message)

    def _region_editor_click(self, position: tuple[int, int]) -> bool:
        if not (
            self.region_edit_new_custom
            or self.region_edit_new_wall
            or self.region_edit_new_special
            or self.region_edit_new_slow
            or self.region_edit_target is not None
            or self.region_edit_custom_id is not None
            or self.region_edit_wall_id is not None
            or self.region_edit_special_id is not None
            or self.region_edit_slow_id is not None
            or self.region_edit_patrol_kind is not None
        ):
            return False
        viewport = self._viewport()
        if not viewport.contains(*position):
            return False
        world = viewport.screen_to_world(*position)
        world = self.arena.clamp(*world)
        screen_points = [viewport.world_to_screen(*point) for point in self.region_edit_points]
        nearest_index = None
        nearest_distance = float("inf")
        for index, point in enumerate(screen_points):
            distance = math.hypot(point[0] - position[0], point[1] - position[1])
            if distance < nearest_distance:
                nearest_index, nearest_distance = index, distance

        is_new_custom = (
            self.region_edit_new_custom
            or self.region_edit_new_wall
            or self.region_edit_new_special
            or self.region_edit_new_slow
        )
        if (
            self.region_edit_new_wall
            or self.region_edit_wall_id is not None
            or self.region_edit_new_special
            or self.region_edit_special_id is not None
        ):
            if nearest_index is not None and nearest_distance <= MAP_EDITOR_HIT_RADIUS:
                self.region_edit_drag_index = nearest_index
                return True
            if len(self.region_edit_points) < 2:
                self.region_edit_points.append(world)
            return True
        if self.region_edit_patrol_kind is not None:
            if nearest_index is not None and nearest_distance <= MAP_EDITOR_HIT_RADIUS:
                self.region_edit_drag_index = nearest_index
                return True
            self.region_edit_points.append(world)
            return True
        if is_new_custom:
            if (
                len(self.region_edit_points) >= 3
                and nearest_index == 0
                and nearest_distance <= MAP_EDITOR_HIT_RADIUS
            ):
                self._save_region_edit()
                return True
            if nearest_index is not None and nearest_distance <= MAP_EDITOR_HIT_RADIUS:
                self.region_edit_drag_index = nearest_index
                return True
            self.region_edit_points.append(world)
            return True

        if nearest_index is not None and nearest_distance <= MAP_EDITOR_HIT_RADIUS:
            self.region_edit_drag_index = nearest_index
            return True
        if len(self.region_edit_points) >= 2:
            insert_after = nearest_segment_index(world, self.region_edit_points)
            self.region_edit_points.insert(insert_after + 1, world)
        else:
            self.region_edit_points.append(world)
        return True

    def _region_editor_right_click(self, position: tuple[int, int]) -> bool:
        active = (
            self.region_edit_new_custom
            or self.region_edit_new_wall
            or self.region_edit_new_special
            or self.region_edit_new_slow
            or self.region_edit_target is not None
            or self.region_edit_custom_id is not None
            or self.region_edit_wall_id is not None
            or self.region_edit_special_id is not None
            or self.region_edit_slow_id is not None
            or self.region_edit_patrol_kind is not None
        )
        if not active or not self._viewport().contains(*position):
            return False
        if self.region_edit_points:
            self.region_edit_points.pop()
            self.region_edit_drag_index = None
            self.region_edit_error = ""
        return True

    def _region_editor_motion(self, position: tuple[int, int]) -> None:
        index = self.region_edit_drag_index
        if index is None or not 0 <= index < len(self.region_edit_points):
            return
        viewport = self._viewport()
        if not viewport.contains(*position):
            return
        world = self.arena.clamp(*viewport.screen_to_world(*position))
        self.region_edit_points[index] = world

    def _region_editor_release(self) -> None:
        self.region_edit_drag_index = None

    def _fire_controlled_robot_at(self, position: tuple[int, int]) -> bool:
        """Aim the selected non-sentry robot at the cursor and fire once."""
        if (
            self.controlled_robot_id is None
            or self.controlled_robot_team not in ("red", "blue")
            or self.pending_fire_shooter is not None
        ):
            return False
        viewport = self._viewport()
        if not viewport.contains(*position):
            return False
        return self._fire_controlled_robot_toward(
            viewport.screen_to_world(*position)
        ) is not None

    def _fire_controlled_robot_toward(
        self,
        target_position: tuple[float, float],
    ):
        """Run one manual shot for the selected robot toward a world point."""
        shooter_id = self.controlled_robot_id
        shooter_team = self.controlled_robot_team
        if shooter_id is None or shooter_team not in ("red", "blue"):
            return None
        try:
            shooter_position = self.task.combatant_position(
                shooter_team,
                shooter_id,
                sentry=self.sentry,
            )
        except ValueError as exc:
            self.task.notify(str(exc))
            return None
        delta_x = float(target_position[0]) - shooter_position[0]
        delta_y = float(target_position[1]) - shooter_position[1]
        aim_angle = (
            self.task.robot_view_angle(
                shooter_id,
                team=shooter_team,
                sentry=self.sentry,
            )
            if math.hypot(delta_x, delta_y) <= 1e-9
            else math.atan2(delta_y, delta_x)
        )
        self.task.set_robot_view_angle(
            shooter_id,
            aim_angle,
            team=shooter_team,
        )
        result = self.task.execute_robot_fire(
            shooter_id,
            aim_angle,
            team=shooter_team,
            sentry=self.sentry,
            attack_buff=(
                self.task.effective_attack_buff if shooter_team == "red" else 1.0
            ),
        )
        self._notify_robot_fire_result(result)
        return result

    def _notify_robot_fire_result(self, result) -> None:
        shooter = f"{result.shooter_team.upper()} {result.shooter_id} 号"
        if result.reason == "fired" and result.target_team is not None:
            probability = self.task.last_hit_probability * 100.0
            self.task.notify(
                f"{shooter}命中 {result.target_team.upper()} "
                f"{result.target_id} 号，造成 {result.damage} 伤害"
                f"（命中率 {probability:.0f}%）"
            )
            return
        if result.reason == "fired_miss":
            probability = self.task.last_hit_probability * 100.0
            self.task.notify(
                f"{shooter}已发射，未命中目标"
                f"（命中率 {probability:.0f}%）"
            )
            return
        reason_labels = {
            "no_launcher": "无发射机构",
            "match_inactive": "比赛未进行",
            "match_paused": "比赛已暂停",
            "robot_destroyed": "机器人已损毁",
            "weak_state": "机器人处于虚弱状态",
            "respawn_fire_locked": "复活阶段禁止开火",
            "heat_locked": "发射机构已被热量锁定",
            "no_ammo": "允许发弹量不足",
            "missing_sentry_state": "缺少哨兵状态",
        }
        self.task.notify(
            f"{shooter}射击失败："
            f"{reason_labels.get(result.reason, '射击被裁判系统拒绝')}"
        )

    def _fire_selected_robot_at(self, target_team: str, target_id: int) -> bool:
        shooter = self.pending_fire_shooter
        if shooter is None:
            return False
        shooter_team, shooter_id = shooter
        if target_team == shooter_team:
            self.task.notify("射击目标必须属于对方")
            return True
        try:
            shooter_position = self.task.combatant_position(
                shooter_team,
                shooter_id,
                sentry=self.sentry,
            )
            target_position = self.task.combatant_position(
                target_team,
                target_id,
                sentry=self.sentry,
            )
        except ValueError as exc:
            self.task.notify(str(exc))
            self.pending_fire_shooter = None
            return True
        aim_angle = math.atan2(
            target_position[1] - shooter_position[1],
            target_position[0] - shooter_position[0],
        )
        if shooter_team == "red" and shooter_id == 8:
            self.sentry.turret_angle = aim_angle
        else:
            self.task.set_robot_view_angle(
                shooter_id,
                aim_angle,
                team=shooter_team,
            )
        result = self.task.execute_robot_fire(
            shooter_id,
            aim_angle,
            team=shooter_team,
            sentry=self.sentry,
            preferred_target=target_id,
            attack_buff=(
                self.task.effective_attack_buff if shooter_team == "red" else 1.0
            ),
        )
        self.pending_fire_shooter = None
        self._notify_robot_fire_result(result)
        return True
