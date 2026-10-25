"""选择、控制、快照等应用级交互。

键盘和面板按钮最终都调用这里的命令方法，减少事件循环中的业务分支。
"""

from __future__ import annotations

from .main import *


class ControlsMixin:
    def _handle_mouse_click(self, position: tuple[int, int]) -> bool:
        for rect, action, target_id, direction in reversed(self.click_regions):
            if not rect.collidepoint(position):
                continue
            if self.replay_mode and action not in {
                "replay_toggle",
                "replay_previous",
                "replay_next",
                "robot_team_tab",
                "robot_property",
                "unpin_robot_property",
                "toggle_subsystem_panel",
                "close_subsystem",
                "subsystem_modal",
                "toggle_map_layers_panel",
                "toggle_map_layer",
                "show_all_map_layers",
                "hide_all_map_layers",
            }:
                # Historical state is read-only.  Selection and modal
                # navigation remain interactive; referee adjustment buttons do
                # not mutate a replay frame.
                return True
            if action == "replay_toggle":
                self.replay_player.toggle()
            elif action == "replay_previous":
                self._open_replay_match(self.replay_match_index - 1)
            elif action == "replay_next":
                self._open_replay_match(self.replay_match_index + 1)
            elif action == "reset_time":
                self._reset_entire_match()
            elif action == "adjust_time":
                self.task.adjust_match_time(direction)
            elif action == "enemy_health":
                self.task.adjust_enemy_health(target_id, direction)
            elif action == "sentry_health":
                self.task.adjust_sentry_health(
                    direction,
                    self.sentry,
                    unseen_damage=direction < 0 and not self._self_detects_enemy(),
                )
            elif action == "ammo":
                self.task.adjust_ammo(direction)
            elif action == "pending_ammo":
                self.task.adjust_pending_ammo(direction)
            elif action == "economy":
                self.task.adjust_economy(direction)
            elif action == "exchange_remote_ammo":
                self.task.exchange_17mm(remote=True, sentry=self.sentry)
            elif action == "exchange_local_ammo":
                self.task.exchange_17mm(remote=False, sentry=self.sentry)
            elif action == "exchange_remote_heal":
                self.task.exchange_remote_heal()
            elif action == "exchange_instant_revive":
                self.task.exchange_instant_revive()
            elif action == "toggle_posture_reinforced":
                self.task.toggle_posture_reinforced(self.sentry)
            elif action == "cycle_hero_mode":
                self.task.cycle_hero_mode()
            elif action == "cycle_infantry_chassis":
                self.task.cycle_infantry_chassis()
            elif action == "cycle_infantry_launcher":
                self.task.cycle_infantry_launcher()
            elif action == "toggle_collision_volumes":
                self._toggle_map_layer("collision_volumes")
            elif action == "toggle_field_zones":
                self._toggle_all_field_zones()
            elif action == "toggle_map_layers_panel":
                self.map_layers_panel_open = not self.map_layers_panel_open
            elif action == "toggle_map_layer":
                self._toggle_map_layer(target_id)
            elif action == "map_editor_tab":
                self.map_editor_tab = str(target_id)
            elif action == "toggle_map_region_editor":
                self.map_region_editor_open = not getattr(
                    self, "map_region_editor_open", False
                )
            elif action == "toggle_map_extra_list":
                self.map_extra_list_open = not getattr(
                    self, "map_extra_list_open", True
                )
            elif action == "new_wall":
                self._start_wall_edit()
            elif action == "edit_wall":
                self._start_wall_edit(str(target_id))
            elif action == "new_special":
                self._start_special_edit()
            elif action == "edit_special":
                self._start_special_edit(str(target_id))
            elif action == "new_slow":
                self._start_slow_edit()
            elif action == "edit_slow":
                self._start_slow_edit(str(target_id))
            elif action == "delete_editable_geometry":
                self._delete_editable_geometry(*target_id)
            elif action == "show_all_map_layers":
                self._set_all_map_layers(True)
            elif action == "hide_all_map_layers":
                self._set_all_map_layers(False)
            elif action == "new_custom_region":
                self._start_custom_region()
            elif action == "edit_patrol_route":
                self._start_patrol_route_edit(str(target_id))
            elif action == "new_region_instance":
                self._start_custom_region(str(target_id))
            elif action == "region_editor_new_instance":
                self._start_custom_region(
                    str(target_id) if target_id else self.region_edit_kind
                )
            elif action == "edit_zone_region":
                self._start_region_edit(str(target_id))
            elif action == "edit_custom_region":
                self._start_custom_edit(str(target_id))
            elif action == "delete_map_region":
                self._delete_region(target_id)
            elif action == "region_editor_save":
                self._save_region_edit()
            elif action == "region_editor_cancel":
                self._cancel_region_edit()
            elif action == "region_editor_clear":
                self._clear_region_edit()
            elif action == "toggle_subsystem_panel":
                self.subsystem_panel_open = not self.subsystem_panel_open
            elif action == "close_subsystem":
                self.subsystem_panel_open = False
            elif action == "subsystem_modal":
                return True
            elif action.startswith("assembly_difficulty_"):
                self.task.select_assembly_difficulty(
                    int(action.rsplit("_", 1)[1])
                )
            elif action == "start_assembly":
                self.task.start_assembly()
            elif action == "cancel_assembly":
                self.task.cancel_assembly(failed=True)
            elif action == "move_engineer_to_assembly":
                position = self.task.assembly_zone_position("red")
                if position is None:
                    self.task.notify("请先在地图中标注己方装配区增益点")
                else:
                    self.task.own_robot_positions[2] = [position[0], position[1]]
                    self.task.notify("工程机器人已移到装配区")
            elif action == "cycle_dart_target":
                self.task.cycle_dart_target()
            elif action == "open_dart_gate":
                self.task.open_dart_gate()
            elif action == "fire_dart":
                self.task.fire_dart()
            elif action == "radar_scan":
                self.task.radar_scan(target_id)
            elif action == "radar_double":
                self.task.trigger_radar_double()
            elif action == "radar_parse_info":
                self.task.parse_radar_information_wave()
            elif action == "radar_parse_interference":
                self.task.parse_radar_interference_key()
            elif action == "radar_air_support":
                self.task.set_radar_air_support(
                    not self.task.radar_air_support_active
                )
            elif action == "radar_air_countermeasure":
                self.task.attempt_radar_air_countermeasure()
            elif action == "activate_small_rune":
                self.task.activate_rune("small")
            elif action == "activate_large_rune":
                self.task.activate_rune("large")
            elif action == "hit_rune":
                self.task.hit_rune(self.sentry)
            elif action == "fire_rate":
                self.task.adjust_fire_rate(direction)
            elif action == "cycle_robot_turntable":
                team = "red" if direction > 0 else "blue"
                self.task.cycle_robot_turntable_mode(target_id, team=team)
            elif action == "own_robot_health":
                if target_id == 8:
                    self.task.adjust_sentry_health(
                        direction,
                        self.sentry,
                        unseen_damage=direction < 0 and not self._self_detects_enemy(),
                    )
                else:
                    self.task.adjust_own_robot_health(target_id, direction)
            elif action == "own_robot_ammo":
                self.task.adjust_own_robot_ammunition(target_id, direction)
            elif action == "enemy_robot_ammo":
                self.task.adjust_robot_ammunition(
                    target_id,
                    direction,
                    team="blue",
                )
            elif action == "own_robot_exp":
                self.task.adjust_own_robot_experience(target_id, 100.0)
            elif action == "enemy_robot_exp":
                self.task.award_experience(target_id, 100.0, team="blue")
            elif action == "robot_fire":
                team = "red" if direction > 0 else "blue"
                self.pending_fire_shooter = (team, target_id)
                self.task.notify(
                    f"已选择 {team.upper()} {target_id} 号为射手，请点击对方目标"
                )
            elif action == "toggle_hero_deploy":
                team = "red" if direction > 0 else "blue"
                self.task.toggle_hero_deployment(team)
            elif action == "control_own_robot":
                if target_id == 8:
                    self._select_sentry()
                else:
                    self._select_own_robot(target_id)
            elif action == "control_enemy_robot":
                self._select_enemy_robot(getattr(self.pg, f"K_{target_id}"))
            elif action == "defence_buff":
                self.task.adjust_defence_buff(direction)
            elif action == "own_outpost_health":
                self.task.adjust_own_outpost_health(direction)
            elif action == "own_base_health":
                self.task.adjust_own_base_health(direction)
            elif action == "auto_control":
                self._switch_to_auto_control()
            elif action == "restart_validation":
                self._restart_validation()
            elif action == "save_snapshot":
                self._save_snapshot()
            elif action == "load_snapshot":
                self._load_snapshot(target_id)
            elif action == "delete_snapshot":
                self._delete_snapshot(target_id)
            elif action == "robot_team_tab":
                self.robot_property_team = target_id
                self.hovered_robot_key = None
                self.pinned_robot_key = None
            elif action == "robot_property":
                target_key = tuple(target_id)
                if not self._fire_selected_robot_at(*target_key):
                    self.pinned_robot_key = target_key
            elif action == "unpin_robot_property":
                self.pinned_robot_key = None
            return True
        if getattr(self, "robot_property_popup_rect", None) is not None:
            if self.robot_property_popup_rect.collidepoint(position):
                return True
        return False

    def _select_sentry(self) -> None:
        self.controlled_robot_id = None
        self.controlled_robot_team = None
        self.sentry.enable_manual_control()
        self.navigator.clear()

    def _select_enemy_robot(self, key: int) -> None:
        key_to_target = {
            self.pg.K_1: 1,
            self.pg.K_2: 2,
            self.pg.K_3: 3,
            self.pg.K_4: 4,
            self.pg.K_5: 5,
            self.pg.K_8: 8,
            self.pg.K_KP1: 1,
            self.pg.K_KP2: 2,
            self.pg.K_KP3: 3,
            self.pg.K_KP4: 4,
            self.pg.K_KP5: 5,
            self.pg.K_KP8: 8,
        }
        target_id = key_to_target.get(key)
        if target_id is None:
            return
        self.controlled_robot_id = target_id
        self.controlled_robot_team = "blue"
        self._manual_fire_held = False
        self.sentry.cancel_manual_control()

    def _select_own_robot(self, target_id: int) -> None:
        if target_id == 8:
            self._select_sentry()
            return
        if target_id not in self.task.own_robot_positions:
            return
        self.controlled_robot_id = target_id
        self.controlled_robot_team = "red"
        self._manual_fire_held = False
        self.manual_fire_active = False
        self.sentry.cancel_manual_control()
        self.navigator.clear()

    def _select_own_robot_key(self, key: int) -> None:
        key_to_target = {
            self.pg.K_1: 1,
            self.pg.K_KP1: 1,
            self.pg.K_2: 2,
            self.pg.K_KP2: 2,
            self.pg.K_3: 3,
            self.pg.K_KP3: 3,
            self.pg.K_4: 4,
            self.pg.K_KP4: 4,
            self.pg.K_5: 5,
            self.pg.K_KP5: 5,
            self.pg.K_8: 8,
            self.pg.K_KP8: 8,
        }
        self._select_own_robot(key_to_target[key])

    def _release_manual_control(self) -> None:
        self._switch_to_auto_control()

    def _switch_to_auto_control(self, *, notify: bool = True) -> None:
        self.controlled_robot_id = None
        self.controlled_robot_team = None
        self._manual_fire_held = False
        self.manual_fire_active = False
        self.sentry.cancel_manual_control()
        self.navigator.clear()
        if notify:
            self.task.notify("已切换为自动控制")

    def _reset_entire_match(self) -> None:
        self.task.reset_match_time()
        self.sentry = SentryState()
        self.robot_chassis_dynamics = {}
        self.controlled_robot_id = None
        self.controlled_robot_team = None
        self.active_snapshot_index = None
        self._manual_fire_held = False
        self.manual_fire_active = False
        self.hit_target_id = None
        self.pending_fire_shooter = None
        self._restart_signal_remaining = 0.20
        self.bridge.clear_output()
        self.navigator.clear()
        self._normalize_robot_positions()
        self._planning_robot_signature = None
        self._refresh_dynamic_planning_grid(force=True)
        self.decision = self.task.evaluate(self.sentry)
        self.task.notify("比赛时间、位置和全部属性已复位")

    def _restart_validation(self) -> None:
        missing = self._missing_required_regions()
        if missing:
            self.task.notify("请先重新添加：" + "、".join(missing[:4]))
            return
        self._switch_to_auto_control(notify=False)
        was_finished = self.task.game_finished
        self.task.game_running = True
        self.task.game_finished = False
        self.task.game_paused = False
        self.task.winner_team = None
        self.task.end_reason = ""
        if was_finished:
            self.task.remaining_time = MATCH_DURATION
        self._restart_signal_remaining = 0.20
        self.hit_target_id = None
        self.bridge.clear_output()
        self.navigator.clear()
        self.decision = self.task.evaluate(self.sentry)
        self.task.notify("验证已重新启动，行为树正在复位")

    def _save_snapshot(self) -> None:
        missing = self._missing_required_regions()
        if missing:
            self.task.notify("场景不能保存，需重新添加：" + "、".join(missing[:4]))
            return
        existing_names = {str(snapshot.get("name") or "") for snapshot in self.snapshots}
        number = 1
        while f"场景 {number}" in existing_names:
            number += 1
        name = f"场景 {number}"
        snapshot = capture_snapshot(
            name,
            self.task,
            self.sentry,
            self.controlled_robot_id,
            self.controlled_robot_team,
            geometry_payload(
                self.map_zone_overrides,
                self.custom_map_polygons,
                self.patrol_routes,
                self.wall_polygons,
                self.special_regions,
                self.slow_regions,
            ),
        )
        self.snapshots.append(snapshot)
        self.active_snapshot_index = len(self.snapshots) - 1
        try:
            self.scenario_store.save(self.snapshots)
        except OSError:
            self.snapshots.pop()
            self.active_snapshot_index = None
            self.task.notify("场景保存失败，请检查目录权限")
            return
        self.task.notify(f"已保存{name}，点击底部标签可恢复")

    def _load_snapshot(self, index: int) -> None:
        if not 0 <= index < len(self.snapshots):
            return
        if not hasattr(self, "map_layer_visibility"):
            self.map_layer_visibility = {
                f"zone:{kind}": False for kind, _ in FIELD_ZONE_KIND_LABELS
            }
            self.map_layer_visibility.update(
                {name: False for name, _ in MAP_OVERLAY_LABELS}
            )
        if not hasattr(self, "custom_map_polygons"):
            self.custom_map_polygons = []
        if not hasattr(self, "wall_polygons"):
            self.wall_polygons = []
        if not hasattr(self, "special_regions"):
            self.special_regions = []
        if not hasattr(self, "slow_regions"):
            self.slow_regions = []
        if not hasattr(self, "map_zone_overrides"):
            self.map_zone_overrides = {}
        if not hasattr(self, "patrol_routes"):
            self.patrol_routes = {
                "conservative": normalize_points(
                    getattr(self.task, "conservative_patrol_route", CONSERVATIVE_PATROL_POINTS)
                ),
                "aggressive": normalize_points(
                    getattr(self.task, "aggressive_patrol_route", AGGRESSIVE_PATROL_POINTS)
                ),
            }
        try:
            task, sentry, controlled_robot_id = restore_snapshot(
                self.snapshots[index]
            )
        except (KeyError, TypeError, ValueError):
            self.task.notify("场景存档损坏，无法载入")
            return
        self.task = task
        self.sentry = sentry
        self.pending_fire_shooter = None
        raw_geometry = self.snapshots[index].get("map_geometry")
        geometry_path = getattr(self, "map_geometry_path", None)
        if (
            getattr(self, "_persistent_geometry_loaded", False)
            and geometry_path is not None
            and geometry_path.is_file()
        ):
            # Region annotations are global configuration, not per-scene
            # state. Loading a scene must not erase them.
            self.map_zone_overrides, self.custom_map_polygons = load_geometry_file(
                geometry_path
            )
            try:
                raw_file_geometry = json.loads(
                    geometry_path.read_text(encoding="utf-8")
                )
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                raw_file_geometry = {}
            self.wall_polygons, self.special_regions = restore_extra_geometry_payload(
                raw_file_geometry
            )
            self.slow_regions = restore_slow_regions_payload(raw_file_geometry)
            self.patrol_routes = load_patrol_routes_file(
                geometry_path,
                {
                    "conservative": CONSERVATIVE_PATROL_POINTS,
                    "aggressive": AGGRESSIVE_PATROL_POINTS,
                },
            )
        elif isinstance(raw_geometry, dict) and raw_geometry:
            self.map_zone_overrides, self.custom_map_polygons = restore_geometry_payload(
                raw_geometry
            )
            self.wall_polygons, self.special_regions = restore_extra_geometry_payload(
                raw_geometry
            )
            self.slow_regions = restore_slow_regions_payload(raw_geometry)
            self.patrol_routes = restore_patrol_routes(
                raw_geometry,
                {
                    "conservative": CONSERVATIVE_PATROL_POINTS,
                    "aggressive": AGGRESSIVE_PATROL_POINTS,
                },
            )
        else:
            self.map_zone_overrides = {
                canonical_region_id(name): normalize_points(points)
                for name, points in getattr(self.task, "field_zone_overrides", {}).items()
                if canonical_region_id(name) in {identifier for identifier, _ in REGION_TYPES}
            }
            self.custom_map_polygons = []
            self.wall_polygons = []
            self.special_regions = []
            self.slow_regions = []
        self._sync_task_zone_overrides()
        self._sync_task_patrol_routes()
        self._rebuild_collision_grids()
        self.map_layer_visibility = {
            key: value
            for key, value in self.map_layer_visibility.items()
            if not key.startswith("custom:")
        }
        for item in self.custom_map_polygons:
            identifier = str(item.get("id"))
            self.map_layer_visibility[f"custom:{identifier}"] = bool(item.get("visible", False))
            if item.get("visible", False):
                kind = str(item.get("kind") or REGION_TYPES[0][0])
                self.map_layer_visibility[f"zone:{kind}"] = True
        self.region_edit_target = None
        self.region_edit_custom_id = None
        self.region_edit_kind = None
        self.region_edit_patrol_kind = None
        self.region_edit_new_custom = False
        self.region_edit_points = []
        self.region_edit_drag_index = None
        self.region_edit_error = ""
        self._cancel_region_edit()
        self.controlled_robot_id = controlled_robot_id
        restored_team = self.snapshots[index].get("controlled_robot_team")
        self.controlled_robot_team = (
            str(restored_team) if restored_team in ("red", "blue") else "blue"
        ) if controlled_robot_id is not None else None
        self.active_snapshot_index = index
        self._manual_fire_held = False
        self.manual_fire_active = False
        self.hit_target_id = None
        self._restart_signal_remaining = 0.0
        self.robot_chassis_dynamics = {}
        self.bridge.clear_output()
        self.navigator.clear()
        self._normalize_robot_positions()
        self._planning_robot_signature = None
        self._refresh_dynamic_planning_grid(force=True)
        self.decision = self.task.evaluate(self.sentry)
        self.task.notify(
            f"已载入{self.snapshots[index].get('name', f'场景 {index + 1}')}"
        )

    def _delete_snapshot(self, index: int) -> None:
        if not 0 <= index < len(self.snapshots):
            return
        previous_snapshots = self.snapshots
        previous_active = self.active_snapshot_index
        self.snapshots, removed = delete_snapshot(self.snapshots, index)
        if self.active_snapshot_index == index:
            self.active_snapshot_index = None
        elif self.active_snapshot_index is not None and self.active_snapshot_index > index:
            self.active_snapshot_index -= 1
        try:
            self.scenario_store.save(self.snapshots)
        except OSError:
            self.snapshots = previous_snapshots
            self.active_snapshot_index = previous_active
            self.task.notify("场景删除失败，请检查目录权限")
            return
        name = str(removed.get("name") or f"场景 {index + 1}")
        self.task.notify(f"已删除{name}")
