"""Pygame UI for RMUC 2026 sentry motion verification."""

from __future__ import annotations

import math
from pathlib import Path

from .core import Arena, SentryState, Viewport
from .map_asset import load_p5_pgm
from .navigation import (
    ASTAR_PLANNING_RADIUS,
    ROBOT_ENTITY_COLLISION_RADIUS,
    AStarNavigator,
    OccupancyGrid,
)
from .ros_bridge import BehaviorTreeBridgeClient
from .scenario_store import (
    ScenarioStore,
    capture_snapshot,
    delete_snapshot,
    restore_snapshot,
)
from .task_state import (
    AGGRESSIVE_PATROL_POINTS,
    ATTACK,
    ATTACK_RANGE,
    CONSERVATIVE_PATROL_POINTS,
    DETECTION_RANGE,
    HOME,
    RULE_FIRE_RATE_MAX,
    SUPPLY,
    SUPPLY_ZONE,
    ROBOT_PROFILES,
    RULE_BASE_HP,
    RULE_BASE_SHIELD,
    RULE_DAMAGE_17MM,
    RULE_DAMAGE_42MM,
    RULE_OUTPOST_HP,
    DecisionView,
    FIELD_ENTITIES,
    OWN_FIELD_ENTITIES,
    TaskScenario,
)


APP_ROOT = Path(__file__).resolve().parent.parent
MAP_PATH = APP_ROOT / "assets" / "rmuc2026.pgm"
SNAPSHOT_PATH = APP_ROOT / "scenario_saves.json"
WINDOW_SIZE = (2240, 1260)
HEADER_HEIGHT = 112
SIDE_PANEL_WIDTH = 390
RIGHT_PANEL_WIDTH = 520
SNAPSHOT_BAR_HEIGHT = 62
AUTOAIM_HALF_VIEW = math.radians(24.0)


def _font_path(bold: bool = False) -> str | None:
    candidates = (
        (
            "C:/Windows/Fonts/msyhbd.ttc" if bold else "C:/Windows/Fonts/msyh.ttc"
        ),
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
        if bold
        else "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    )
    return next((path for path in candidates if Path(path).is_file()), None)


class SimulatorApp:
    def __init__(self, pygame_module) -> None:
        self.pg = pygame_module
        self.pg.init()
        self.pg.display.set_caption("RMUC 2026 二维哨兵验证")
        self.screen = self.pg.display.set_mode(WINDOW_SIZE, self.pg.RESIZABLE)
        self.clock = self.pg.time.Clock()
        self.arena = Arena()
        self.sentry = SentryState()
        self.controlled_robot_id: int | None = None
        self.controlled_robot_team: str | None = None
        self.task = TaskScenario()
        self.decision = self.task.evaluate(self.sentry)
        self.bridge = BehaviorTreeBridgeClient()
        self.scenario_store = ScenarioStore(SNAPSHOT_PATH)
        self.snapshots = self.scenario_store.load()
        self.active_snapshot_index: int | None = None
        self.title_font = self.pg.font.Font(_font_path(True), 40)
        self.data_font = self.pg.font.Font(_font_path(False), 26)
        self.small_font = self.pg.font.Font(_font_path(False), 21)
        self.panel_title_font = self.pg.font.Font(_font_path(True), 28)
        self.panel_label_font = self.pg.font.Font(_font_path(False), 20)
        map_image = load_p5_pgm(MAP_PATH)
        self.map_surface = self._load_map_surface(map_image)
        self.collision_grid = OccupancyGrid.from_pgm(map_image, self.arena)
        self.planning_grid = OccupancyGrid.from_pgm(
            map_image,
            self.arena,
            collision_radius=ASTAR_PLANNING_RADIUS,
        )
        self.base_planning_grid = self.planning_grid
        self.navigator = AStarNavigator(self.planning_grid)
        self._planning_robot_signature = None
        self._normalize_robot_positions()
        self._refresh_dynamic_planning_grid(force=True)
        self.scaled_map = None
        self.scaled_map_size = None
        self.click_regions: list[tuple[object, str, object, int]] = []
        self.robot_property_regions: list[tuple[object, str, int]] = []
        self.robot_property_team = "red"
        self.hovered_robot_key: tuple[str, int] | None = None
        self.pinned_robot_key: tuple[str, int] | None = None
        self.manual_fire_active = False
        self.hit_target_id: int | None = None
        self._manual_fire_held = False
        self._restart_signal_remaining = 0.0

    def _load_map_surface(self, image):
        source = self.pg.image.frombytes(image.pixels, (image.width, image.height), "P")
        source.set_palette([(value, value, value) for value in range(256)])
        source = source.convert()
        left, top, width, height = self.arena.map_crop(image.width, image.height)
        return source.subsurface((left, top, width, height)).copy()

    def run(
        self,
        *,
        max_frames: int | None = None,
        screenshot_path: Path | None = None,
    ) -> None:
        frame_count = 0
        running = True
        try:
            while running:
                elapsed_seconds = min(self.clock.tick(60) / 1000.0, 0.05)
                for event in self.pg.event.get():
                    if event.type == self.pg.QUIT:
                        running = False
                    elif event.type == self.pg.KEYDOWN:
                        if (
                            event.key == self.pg.K_s
                            and event.mod & self.pg.KMOD_CTRL
                        ):
                            self._save_snapshot()
                        elif event.key == self.pg.K_ESCAPE:
                            running = False
                        elif event.key == self.pg.K_SPACE:
                            self.task.toggle_pause()
                        elif event.key == self.pg.K_p:
                            self.task.toggle_pause()
                        elif event.key in (self.pg.K_0, self.pg.K_KP0):
                            self._switch_to_auto_control()
                        elif event.key == self.pg.K_r:
                            self._restart_validation()
                        elif event.key in (
                            self.pg.K_F1,
                            self.pg.K_F2,
                            self.pg.K_F3,
                            self.pg.K_F4,
                            self.pg.K_F5,
                            self.pg.K_F6,
                            self.pg.K_F7,
                            self.pg.K_F8,
                            self.pg.K_F9,
                            self.pg.K_F10,
                        ):
                            self._select_own_robot_function_key(event.key)
                        elif event.key in (self.pg.K_9, self.pg.K_KP9):
                            self._select_sentry()
                        elif event.key in (
                            self.pg.K_1,
                            self.pg.K_2,
                            self.pg.K_3,
                            self.pg.K_4,
                            self.pg.K_5,
                            self.pg.K_8,
                            self.pg.K_KP1,
                            self.pg.K_KP2,
                            self.pg.K_KP3,
                            self.pg.K_KP4,
                            self.pg.K_KP5,
                            self.pg.K_KP8,
                        ):
                            if event.mod & self.pg.KMOD_CTRL:
                                self._select_own_robot_key(event.key)
                            else:
                                self._select_enemy_robot(event.key)
                        elif event.key in (self.pg.K_LSHIFT, self.pg.K_RSHIFT):
                            self._switch_to_auto_control()
                    elif event.type in (
                        self.pg.VIDEORESIZE,
                        self.pg.WINDOWSIZECHANGED,
                    ):
                        # Pygame 2/SDL2 resizes a RESIZABLE display surface
                        # automatically. Calling set_mode() again here can
                        # generate another resize event on X11 and make the
                        # window continuously flash.
                        resized_surface = self.pg.display.get_surface()
                        if resized_surface is not None:
                            self.screen = resized_surface
                    elif event.type == self.pg.MOUSEBUTTONDOWN and event.button == 1:
                        handled = self._handle_mouse_click(event.pos)
                        if not handled:
                            self._manual_fire_held = self.sentry.manual_control
                    elif event.type == self.pg.MOUSEBUTTONUP and event.button == 1:
                        self._manual_fire_held = False

                viewport = self._viewport()
                move_x, move_y = self._movement_input()
                bridge_decision = self._bridge_decision()
                local_decision = self._local_decision()
                motion_decision = bridge_decision or local_decision
                restarting = self._restart_signal_remaining > 0.0
                simulation_elapsed = (
                    0.0
                    if self.task.game_paused or restarting
                    else elapsed_seconds
                )
                if self.controlled_robot_id is not None:
                    self._move_controlled_robot(move_x, move_y, elapsed_seconds)
                self._update_sentry_motion(
                    elapsed_seconds
                    if self.sentry.manual_control
                    else simulation_elapsed,
                    move_x,
                    move_y,
                    motion_decision,
                )
                self.manual_fire_active = self._manual_fire_requested()
                if restarting:
                    fire_request = False
                    preferred_target = 0
                elif self.sentry.manual_control:
                    fire_request = self.manual_fire_active
                    preferred_target = 0
                else:
                    fire_request = bool(motion_decision.shoot_mode)
                    preferred_target = motion_decision.target
                self.hit_target_id = (
                    self.task.resolve_fire_target(
                        self.sentry,
                        preferred_target=preferred_target,
                    )
                    if fire_request
                    else None
                )
                self.decision = self.task.update(
                    0.0 if restarting else elapsed_seconds,
                    self.sentry,
                    decision_override=motion_decision,
                    fire_request=fire_request,
                    hit_target_id=self.hit_target_id,
                    # Targets are point proxies in the 2-D scene. A confirmed
                    # building hit therefore represents an aimed center hit.
                    critical_zone=self.hit_target_id in (6, 7),
                )
                self.bridge.publish_state(self._bridge_state())
                self._restart_signal_remaining = max(
                    0.0,
                    self._restart_signal_remaining - elapsed_seconds,
                )
                self._render(viewport)
                self.pg.display.flip()

                frame_count += 1
                if max_frames is not None and frame_count >= max_frames:
                    if screenshot_path is not None:
                        self.pg.image.save(self.screen, str(screenshot_path))
                    running = False
        finally:
            self.bridge.close()
            self.pg.quit()

    def _viewport(self) -> Viewport:
        width, height = self.screen.get_size()
        left = SIDE_PANEL_WIDTH + 24
        right = width - RIGHT_PANEL_WIDTH - 24
        top = HEADER_HEIGHT + 18
        bottom = height - SNAPSHOT_BAR_HEIGHT - 18
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
        self._refresh_dynamic_planning_grid()
        if self.sentry.manual_control:
            start = (self.sentry.x, self.sentry.y)
            self.sentry.update(
                elapsed_seconds,
                manual_x,
                manual_y,
                self.arena,
                spin_enabled=decision.spin_mode > 0,
                spin_speed_scale=self._spin_speed_scale(decision.spin_mode),
                turret_enabled=not self._manual_fire_held,
            )
            self.sentry.x, self.sentry.y = self.collision_grid.move_with_collision(
                start,
                (self.sentry.x, self.sentry.y),
                collision_bodies=self._collision_bodies("sentry", 8),
                moving_radius=ROBOT_ENTITY_COLLISION_RADIUS,
            )
            self.navigator.clear()
            return

        current = (self.sentry.x, self.sentry.y)
        self.navigator.update_goal(current, decision.goal)
        waypoint = self.navigator.next_waypoint(current)
        if waypoint is not None:
            delta_x = waypoint[0] - self.sentry.x
            delta_y = waypoint[1] - self.sentry.y
            distance = math.hypot(delta_x, delta_y)
            if distance > 0.08:
                travel = min(distance, self.sentry.movement_speed * elapsed_seconds)
                proposed = self.arena.clamp(
                    self.sentry.x + delta_x / distance * travel,
                    self.sentry.y + delta_y / distance * travel,
                )
                self.sentry.x, self.sentry.y = self.collision_grid.move_with_collision(
                    current,
                    proposed,
                    collision_bodies=self._collision_bodies("sentry", 8),
                    moving_radius=ROBOT_ENTITY_COLLISION_RADIUS,
                )

        tracking = self._track_selected_target(decision, elapsed_seconds)
        self.sentry.update(
            elapsed_seconds,
            0.0,
            0.0,
            self.arena,
            spin_enabled=decision.spin_mode > 0,
            spin_speed_scale=self._spin_speed_scale(decision.spin_mode),
            turret_enabled=decision.tripod_mode > 0 and not tracking,
        )

    def _normalize_robot_positions(self) -> None:
        """Repair initial/legacy positions inside walls or overlapping robots."""
        placed: list[tuple[float, float, float]] = []
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
            overlaps = any(
                math.hypot(position[0] - x, position[1] - y)
                < ROBOT_ENTITY_COLLISION_RADIUS + radius
                for x, y, radius in placed
            )
            if not self.collision_grid.is_free_world(*position) or overlaps:
                grid = self.collision_grid.with_dynamic_obstacles(tuple(placed))
                nearest = grid.nearest_free_cell(grid.world_to_cell(*position))
                if nearest is not None:
                    position = grid.cell_to_world(nearest)
                    if team == "sentry":
                        self.sentry.x, self.sentry.y = position
                    else:
                        self.task.set_robot_position(target_id, position, team=team)
            placed.append((*position, ROBOT_ENTITY_COLLISION_RADIUS))

    def _collision_bodies(
        self, moving_team: str, moving_id: int
    ) -> tuple[tuple[float, float, float], ...]:
        bodies: list[tuple[float, float, float]] = []
        for target_id in self.task.robot_positions:
            if moving_team == "blue" and target_id == moving_id:
                continue
            x, y = self.task.robot_position(target_id, team="blue")
            bodies.append((x, y, ROBOT_ENTITY_COLLISION_RADIUS))
        for target_id in self.task.own_robot_positions:
            if moving_team == "red" and target_id == moving_id:
                continue
            x, y = self.task.own_robot_position(target_id)
            bodies.append((x, y, ROBOT_ENTITY_COLLISION_RADIUS))
        if not (moving_team == "sentry" and moving_id == 8):
            bodies.append(
                (self.sentry.x, self.sentry.y, ROBOT_ENTITY_COLLISION_RADIUS)
            )
        return tuple(bodies)

    def _dynamic_planning_bodies(self) -> tuple[tuple[float, float, float], ...]:
        bodies = [
            (x, y, ROBOT_ENTITY_COLLISION_RADIUS)
            for target_id in self.task.robot_positions
            for x, y in (self.task.robot_position(target_id, team="blue"),)
        ]
        bodies.extend(
            (x, y, ROBOT_ENTITY_COLLISION_RADIUS)
            for target_id in self.task.own_robot_positions
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
        target_id = self.controlled_robot_id
        team = self.controlled_robot_team
        if target_id is None or team not in ("blue", "red"):
            return
        start = self.task.robot_position(target_id, team=team)
        self.task.move_robot(
            target_id,
            move_x,
            move_y,
            elapsed_seconds,
            self.arena,
            team=team,
        )
        proposed = self.task.robot_position(target_id, team=team)
        resolved = self.collision_grid.move_with_collision(
            start,
            proposed,
            collision_bodies=self._collision_bodies(team, target_id),
            moving_radius=ROBOT_ENTITY_COLLISION_RADIUS,
        )
        self.task.set_robot_position(target_id, resolved, team=team)
        profile = ROBOT_PROFILES.get(target_id)
        if profile is not None and profile.power_limit is not None:
            movement = min(1.0, math.hypot(move_x, move_y))
            power = movement * float(profile.power_limit)
            power_map = self.task.robot_power if team == "blue" else self.task.own_robot_power
            power_map[target_id] = power

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
        if math.hypot(delta_x, delta_y) > DETECTION_RANGE:
            return False
        target_angle = math.atan2(delta_y, delta_x)
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
        if self.task.game_finished and self._near_goal(goal, HOME):
            return "行为树：比赛结束归位"
        if target == 6 or self._near_goal(goal, ATTACK):
            return "行为树：攻击敌方前哨"
        if self._near_goal(goal, SUPPLY):
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
        # Deliberately publish only the existing sentry/enemy referee inputs.
        # Other friendly robots are local visualization/collision entities and
        # must not become behavior-tree or ROS decision inputs.
        enemy_hp = self._enemy_health_snapshot()
        radar_data: list[float] = []
        for target_id in (1, 2, 3, 4, 5, 8):
            x, y = self.task.robot_position(target_id)
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
        positions[6] = (20.0, 7.5)
        positions[7] = (27.0, 7.5)
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
            if distance <= DETECTION_RANGE and abs(relative_angle) <= AUTOAIM_HALF_VIEW:
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

    def _handle_mouse_click(self, position: tuple[int, int]) -> bool:
        for rect, action, target_id, direction in reversed(self.click_regions):
            if not rect.collidepoint(position):
                continue
            if action == "reset_time":
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
            elif action == "fire_rate":
                self.task.adjust_fire_rate(direction)
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
                self.pinned_robot_key = tuple(target_id)
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
            self.pg.K_8: 8,
            self.pg.K_KP1: 1,
            self.pg.K_KP2: 2,
            self.pg.K_KP3: 3,
            self.pg.K_KP4: 4,
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
        self.controlled_robot_id = None
        self.controlled_robot_team = None
        self.active_snapshot_index = None
        self._manual_fire_held = False
        self.manual_fire_active = False
        self.hit_target_id = None
        self._restart_signal_remaining = 0.20
        self.bridge.clear_output()
        self.navigator.clear()
        self._normalize_robot_positions()
        self._planning_robot_signature = None
        self._refresh_dynamic_planning_grid(force=True)
        self.decision = self.task.evaluate(self.sentry)
        self.task.notify("比赛时间、位置和全部属性已复位")

    def _restart_validation(self) -> None:
        self._switch_to_auto_control(notify=False)
        self.task.game_running = True
        self.task.game_finished = False
        self.task.game_paused = False
        self._restart_signal_remaining = 0.20
        self.hit_target_id = None
        self.bridge.clear_output()
        self.navigator.clear()
        self.decision = self.task.evaluate(self.sentry)
        self.task.notify("验证已重新启动，行为树正在复位")

    def _save_snapshot(self) -> None:
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
        try:
            task, sentry, controlled_robot_id = restore_snapshot(
                self.snapshots[index]
            )
        except (KeyError, TypeError, ValueError):
            self.task.notify("场景存档损坏，无法载入")
            return
        self.task = task
        self.sentry = sentry
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

    def _render(self, viewport: Viewport) -> None:
        self.click_regions.clear()
        self.robot_property_regions.clear()
        self.screen.fill((22, 25, 28))
        self._draw_header()
        self._draw_side_panels()
        self._draw_arena(viewport)
        self._draw_snapshot_bar()
        self._draw_robot_property_popup()

    def _draw_header(self) -> None:
        width, _ = self.screen.get_size()
        self.pg.draw.rect(self.screen, (31, 36, 40), (0, 0, width, HEADER_HEIGHT))
        self.pg.draw.line(
            self.screen,
            (67, 75, 80),
            (0, HEADER_HEIGHT - 1),
            (width, HEADER_HEIGHT - 1),
            1,
        )

        title = self.title_font.render("RMUC 2026｜二维哨兵验证", True, (240, 243, 244))
        self.screen.blit(title, (34, 12))

        if self.sentry.manual_control:
            mode = "人工控制｜己方哨兵 9｜鼠标左键射击"
            mode_color = (66, 208, 132)
        elif self.controlled_robot_id is not None:
            team_name = "己方" if self.controlled_robot_team == "red" else "蓝方"
            mode = f"人工控制｜{team_name} {self.controlled_robot_id} 号"
            mode_color = (62, 184, 112) if self.controlled_robot_team == "red" else (74, 143, 224)
        else:
            mode = (
                "行为树自动控制"
                if self.bridge.connected
                else "本地决策自动控制"
            )
            mode_color = (245, 180, 65)
        if self.task.game_paused:
            mode = f"比赛暂停｜{mode}"
            mode_color = (224, 83, 83)
        self.pg.draw.circle(self.screen, mode_color, (42, 82), 7)
        mode_text = self.data_font.render(f"控制状态：{mode}", True, (202, 209, 212))
        self.screen.blit(mode_text, (59, 66))

        if self.controlled_robot_id is None:
            position_label = "己方哨兵"
            position_x, position_y = self.sentry.x, self.sentry.y
        else:
            team_name = "己方" if self.controlled_robot_team == "red" else "蓝方"
            position_label = f"{team_name} {self.controlled_robot_id} 号"
            position_x, position_y = self.task.robot_position(
                self.controlled_robot_id,
                team=self.controlled_robot_team or "blue",
            )
        position = self.data_font.render(
            f"{position_label}    横坐标 {position_x:06.3f} 米    纵坐标 {position_y:06.3f} 米",
            True,
            (222, 228, 230),
        )
        position_rect = position.get_rect(midright=(width - 34, 32))
        self.screen.blit(position, position_rect)

        angles = self.small_font.render(
            f"哨兵底盘 {math.degrees(self.sentry.spin_angle) % 360:06.1f}°    "
            f"云台 {math.degrees(self.sentry.turret_angle) % 360:06.1f}°",
            True,
            (155, 166, 171),
        )
        angles_rect = angles.get_rect(midright=(width - 34, 79))
        self.screen.blit(angles, angles_rect)

    def _draw_side_panels(self) -> None:
        width, height = self.screen.get_size()
        panel_height = height - HEADER_HEIGHT - SNAPSHOT_BAR_HEIGHT
        left_rect = self.pg.Rect(0, HEADER_HEIGHT, SIDE_PANEL_WIDTH, panel_height)
        right_rect = self.pg.Rect(
            width - RIGHT_PANEL_WIDTH,
            HEADER_HEIGHT,
            RIGHT_PANEL_WIDTH,
            panel_height,
        )
        for rect in (left_rect, right_rect):
            self.pg.draw.rect(self.screen, (27, 31, 34), rect)
        self.pg.draw.line(
            self.screen,
            (62, 70, 74),
            (SIDE_PANEL_WIDTH, HEADER_HEIGHT),
            (SIDE_PANEL_WIDTH, height - SNAPSHOT_BAR_HEIGHT),
            1,
        )
        self.pg.draw.line(
            self.screen,
            (62, 70, 74),
            (width - RIGHT_PANEL_WIDTH - 1, HEADER_HEIGHT),
            (width - RIGHT_PANEL_WIDTH - 1, height - SNAPSHOT_BAR_HEIGHT),
            1,
        )
        self._draw_left_panel(left_rect)
        self._draw_right_panel(right_rect)

    def _draw_left_panel(self, rect) -> None:
        x = rect.left + 16
        bar_width = rect.width - 32
        y = rect.top + 15
        y = self._draw_panel_title(x, y, "己方哨兵与裁判系统", bar_width)

        y = self._draw_section_title(x, y, "任务状态")
        y = self._draw_key_value(x, y, "当前控制", self._control_name(), bar_width)
        y = self._draw_key_value(
            x,
            y,
            "决策来源",
            "ROS 行为树在线" if self.bridge.connected else "Python 本地回退",
            bar_width,
        )
        y = self._draw_key_value(x, y, "当前行为", self.decision.behavior, bar_width)
        y = self._draw_key_value(
            x,
            y,
            "比赛状态",
            "已暂停（空格继续）" if self.task.game_paused else "进行中（空格暂停）",
            bar_width,
        )
        y = self._draw_key_value(
            x,
            y,
            "哨兵坐标",
            f"{self.sentry.x:.2f}，{self.sentry.y:.2f}",
            bar_width,
        )
        y = self._draw_key_value(x, y, "导航目标", self._goal_name(), bar_width)
        y = self._draw_key_value(x, y, "巡逻模式", self.task.patrol_name, bar_width)
        y = self._draw_control_buttons(x, y + 3, bar_width)

        y = self._draw_section_title(x, y + 3, "基本属性")
        y = self._draw_adjustable_progress_bar(
            x,
            y,
            bar_width,
            "哨兵血量",
            self.task.sentry_hp,
            400,
            (62, 184, 112),
            9,
            action="sentry_health",
        )
        ammo_maximum = max(200, self.task.ammo + self.task.pending_ammo)
        y = self._draw_adjustable_progress_bar(
            x,
            y,
            bar_width,
            "当前弹量",
            self.task.ammo,
            ammo_maximum,
            (225, 166, 58),
            0,
            action="ammo",
        )
        y = self._draw_progress_bar(
            x,
            y,
            bar_width,
            "当前热量",
            self.sentry.heat,
            ROBOT_PROFILES[8].heat_capacity or 0,
            (218, 92, 53),
        )
        y = self._draw_progress_bar(
            x,
            y,
            bar_width,
            "底盘功率",
            self.sentry.chassis_power,
            ROBOT_PROFILES[8].power_limit or 0,
            (96, 151, 210),
        )
        y = self._draw_adjustable_progress_bar(
            x,
            y,
            bar_width,
            "防御增益",
            self.task.defence_buff,
            100,
            (56, 169, 195),
            0,
            suffix="%",
            action="defence_buff",
        )
        y = self._draw_section_title(x, y + 3, "裁判与决策参数")
        y = self._draw_match_time_control(x, y, bar_width)
        y = self._draw_adjustable_progress_bar(
            x,
            y,
            bar_width,
            "待领弹药",
            self.task.pending_ammo,
            500,
            (225, 166, 58),
            0,
            compact=True,
            action="pending_ammo",
        )
        y = self._draw_adjustable_progress_bar(
            x,
            y,
            bar_width,
            "经济",
            self.task.economy,
            1000,
            (88, 183, 102),
            0,
            compact=True,
            action="economy",
        )
        y = self._draw_adjustable_progress_bar(
            x,
            y,
            bar_width,
            "射速",
            self.task.fire_rate,
            RULE_FIRE_RATE_MAX,
            (221, 137, 52),
            0,
            suffix=" 发/秒",
            compact=True,
            action="fire_rate",
        )
        posture_name = {1: "进攻", 2: "防御", 3: "移动"}.get(
            self.decision.posture, "未知"
        )
        y = self._draw_key_value(x, y, "当前姿态", posture_name, bar_width)
        y = self._draw_key_value(
            x, y, "回血阈值", str(self.decision.health_threshold), bar_width
        )
        self._draw_wrapped_status(x, y + 5, bar_width, "最近事件", self.task.event_message)

    def _draw_right_panel(self, rect) -> None:
        self.robot_property_panel_rect = rect
        x = rect.left + 14
        width = rect.width - 28
        y = rect.top + 14
        y = self._draw_panel_title(x, y, "己方控制与机器人属性", width)

        y = self._draw_section_title(x, y, "己方建筑血量（规则值）")
        y = self._draw_adjustable_progress_bar(
            x,
            y,
            width,
            "己方前哨",
            self.task.own_outpost_hp,
            RULE_OUTPOST_HP,
            (205, 75, 82),
            6,
            action="own_outpost_health",
        )
        y = self._draw_adjustable_progress_bar(
            x,
            y,
            width,
            "己方基地",
            self.task.own_base_hp,
            RULE_BASE_HP,
            (177, 105, 190),
            7,
            action="own_base_health",
        )
        y = self._draw_key_value(
            x,
            y,
            "基地虚拟护盾",
            f"{round(self.task.own_base_shield)}/{RULE_BASE_SHIELD}",
            width,
        )

        y = self._draw_section_title(x, y + 3, "机器人属性列表")
        y = self._draw_robot_team_tabs(x, y, width)
        y = self._draw_robot_property_list(x, y, width)
        self._draw_wrapped_status(
            x,
            min(y + 4, rect.bottom - 52),
            width,
            "提示",
            "悬停机器人名称查看属性；点击名称固定属性面板。己方其他机器人不接入决策。",
        )

    def _draw_robot_team_tabs(self, x: int, y: int, width: int) -> int:
        gap = 6
        tab_width = (width - gap) // 2
        tab_height = 34
        tabs = (("red", "己方"), ("blue", "敌方"))
        for index, (team, label) in enumerate(tabs):
            tab = self.pg.Rect(
                x + index * (tab_width + gap),
                y,
                tab_width,
                tab_height,
            )
            active = team == self.robot_property_team
            background = (236, 240, 241) if active else (50, 58, 63)
            border = (166, 180, 184) if active else (91, 101, 106)
            color = (24, 111, 74) if active else (220, 228, 230)
            self.pg.draw.rect(self.screen, background, tab, border_radius=3)
            self.pg.draw.rect(self.screen, border, tab, 1, border_radius=3)
            rendered = self.panel_label_font.render(label, True, color)
            self.screen.blit(rendered, rendered.get_rect(center=tab.center))
            self.click_regions.append((tab, "robot_team_tab", team, 0))
        return y + tab_height + 8

    def _draw_robot_property_list(self, x: int, y: int, width: int) -> int:
        rows: list[tuple[str, int, str, float, float, tuple[int, int, int]]] = []
        names = {1: "英雄", 2: "工程", 3: "步兵 3", 4: "步兵 4", 5: "空中", 8: "哨兵"}
        team = self.robot_property_team
        team_name = "己方" if team == "red" else "蓝方"
        team_color = (62, 184, 112) if team == "red" else (68, 133, 217)
        for target_id in (1, 2, 3, 4, 5, 8):
            profile = ROBOT_PROFILES[target_id]
            health = (
                self.task.own_robot_health(target_id)
                if team == "red"
                else self.task.enemy_health(target_id)
            )
            rows.append(
                (
                    team,
                    target_id,
                    f"{team_name} {target_id}号 {names[target_id]}",
                    health,
                    profile.max_hp,
                    team_color,
                )
            )
        building_color = (193, 60, 67) if team == "red" else team_color
        rows.extend(
            (
                team,
                target_id,
                label,
                value,
                maximum,
                building_color,
            )
            for target_id, label, value, maximum in (
                (
                    6,
                    f"{team_name}前哨",
                    self.task.own_outpost_hp if team == "red" else self.task.enemy_health(6),
                    RULE_OUTPOST_HP,
                ),
                (
                    7,
                    f"{team_name}基地",
                    self.task.own_base_hp if team == "red" else self.task.enemy_health(7),
                    RULE_BASE_HP,
                ),
            )
        )
        row_height = 49
        for index, (team, target_id, label, value, maximum, color) in enumerate(rows):
            row = self.pg.Rect(x, y + index * row_height, width, row_height - 3)
            selected = self.pinned_robot_key == (team, target_id)
            hovered = row.collidepoint(self.pg.mouse.get_pos())
            background = (58, 68, 72) if selected else (42, 48, 52) if hovered else (32, 37, 40)
            self.pg.draw.rect(self.screen, background, row, border_radius=3)
            self.pg.draw.rect(self.screen, color, row, 1, border_radius=3)
            self.robot_property_regions.append((row, team, target_id))
            self.click_regions.append((row, "robot_property", (team, target_id), 0))
            name_text = self.panel_label_font.render(label, True, color)
            self.screen.blit(name_text, (row.left + 8, row.top + 3))
            value_label = (
                "不适用装甲扣血"
                if target_id == 5
                else f"{round(value)}/{round(maximum)}"
            )
            value_text = self.small_font.render(value_label, True, (220, 226, 228))
            if target_id == 5:
                value_right = row.right - 8
            else:
                plus_button = self.pg.Rect(row.right - 34, row.top + 2, 26, 26)
                minus_button = self.pg.Rect(
                    plus_button.left - 30, row.top + 2, 26, 26
                )
                self._draw_click_button(minus_button, "-")
                self._draw_click_button(plus_button, "+")
                adjustment_action = self._robot_health_adjustment_action(
                    team, target_id
                )
                self.click_regions.append(
                    (minus_button, adjustment_action, target_id, -1)
                )
                self.click_regions.append(
                    (plus_button, adjustment_action, target_id, 1)
                )
                value_right = minus_button.left - 6
            self.screen.blit(
                value_text,
                value_text.get_rect(topright=(value_right, row.top + 3)),
            )
            bar = self.pg.Rect(row.left + 8, row.top + 31, row.width - 16, 9)
            self.pg.draw.rect(self.screen, (48, 54, 58), bar, border_radius=2)
            if target_id != 5 and maximum > 0:
                ratio = max(0.0, min(1.0, float(value) / float(maximum)))
                if ratio > 0.0:
                    self.pg.draw.rect(
                        self.screen,
                        color,
                        (bar.left, bar.top, max(1, round(bar.width * ratio)), bar.height),
                        border_radius=2,
                    )
        mouse_position = self.pg.mouse.get_pos()
        self.hovered_robot_key = next(
            (
                (team, target_id)
                for row, team, target_id in self.robot_property_regions
                if row.collidepoint(mouse_position)
            ),
            None,
        )
        return y + len(rows) * row_height

    @staticmethod
    def _robot_health_adjustment_action(team: str, target_id: int) -> str:
        if team == "blue":
            return "enemy_health"
        if target_id == 6:
            return "own_outpost_health"
        if target_id == 7:
            return "own_base_health"
        if target_id == 8:
            return "sentry_health"
        return "own_robot_health"

    def _draw_robot_property_popup(self) -> None:
        active = self.pinned_robot_key or self.hovered_robot_key
        self.robot_property_popup_rect = None
        if active is None:
            return
        team, target_id = active
        if not hasattr(self, "robot_property_panel_rect"):
            return
        panel = self.robot_property_panel_rect
        popup_width = min(430, max(330, panel.width - 20))
        popup_height = 760 if target_id in ROBOT_PROFILES else 350
        popup = self.pg.Rect(
            max(8, panel.left - popup_width - 10),
            max(HEADER_HEIGHT + 8, panel.top + 52),
            popup_width,
            min(popup_height, self.screen.get_height() - SNAPSHOT_BAR_HEIGHT - HEADER_HEIGHT - 16),
        )
        self.robot_property_popup_rect = popup
        overlay = self.pg.Surface(popup.size, self.pg.SRCALPHA)
        overlay.fill((20, 25, 28, 246))
        self.screen.blit(overlay, popup)
        self.pg.draw.rect(self.screen, (120, 137, 143), popup, 2, border_radius=6)
        x = popup.left + 14
        y = popup.top + 12
        title, profile, health, maximum, ammo = self._property_target_values(team, target_id)
        self.screen.blit(self.panel_title_font.render(title, True, (240, 243, 244)), (x, y))
        y += 38
        if profile is None:
            y = self._draw_key_value(x, y, "类型", "场地建筑", popup.width - 28)
            y = self._draw_key_value(x, y, "血量", f"{round(health)}/{round(maximum)}", popup.width - 28)
            if target_id == 7:
                shield = self.task.enemy_base_shield if team == "blue" else self.task.own_base_shield
                y = self._draw_key_value(x, y, "虚拟护盾", f"{round(shield)}/{RULE_BASE_SHIELD}", popup.width - 28)
                outpost = self.task.enemy_outpost_hp if team == "blue" else self.task.own_outpost_hp
                y = self._draw_key_value(x, y, "无敌状态", "前哨存活，无敌" if outpost > 0 else "可受到伤害", popup.width - 28)
            damage_label = "5（上方前装甲）/20" if target_id == 7 else "20"
            y = self._draw_key_value(x, y, "17mm 原始伤害", damage_label, popup.width - 28)
            y = self._draw_key_value(x, y, "42mm 原始伤害", str(RULE_DAMAGE_42MM), popup.width - 28)
            y = self._draw_key_value(x, y, "中心区域攻击增益", "150%", popup.width - 28)
        else:
            configuration = {
                1: "1级·远程优先", 2: "固定性能", 3: "1级·血量/冷却优先",
                4: "1级·血量/冷却优先", 5: "1级", 8: "自动哨兵",
            }[target_id]
            y = self._draw_key_value(x, y, "规则配置", configuration, popup.width - 28)
            y = self._draw_key_value(
                x, y, "云台", "有" if profile.has_gimbal else "无", popup.width - 28
            )
            y = self._draw_key_value(
                x, y, "小转盘", "有" if profile.has_turntable else "无", popup.width - 28
            )
            health_label = f"{round(health)}/{profile.max_hp}" if target_id != 5 else "不适用地面装甲扣血"
            if target_id == 5:
                y = self._draw_key_value(x, y, "血量", health_label, popup.width - 28)
            else:
                y = self._draw_adjustable_progress_bar(
                    x, y, popup.width - 28, "血量", health, profile.max_hp,
                    (62, 184, 112) if team == "red" else (68, 133, 217),
                    target_id, compact=True,
                    action="own_robot_health" if team == "red" else "enemy_health",
                )
            y = self._draw_key_value(x, y, "弹丸", profile.projectile, popup.width - 28)
            y = self._draw_key_value(x, y, "初始允许发弹量", str(profile.initial_ammo), popup.width - 28)
            y = self._draw_key_value(x, y, "射击初速度上限", self._format_rule_value(profile.muzzle_speed_limit, "m/s"), popup.width - 28)
            power_limit = self._format_rule_value(profile.power_limit, "W")
            heat_limit = self._format_rule_value(profile.heat_capacity, "")
            current_power = (
                self.task.robot_power_value(
                    target_id,
                    team=team,
                    sentry=self.sentry if team == "red" and target_id == 8 else None,
                )
            )
            current_heat = (
                self.task.robot_heat_value(
                    target_id,
                    team=team,
                    sentry=self.sentry if team == "red" and target_id == 8 else None,
                )
            )
            y = self._draw_key_value(x, y, "底盘功率", f"{current_power:.1f} W / {power_limit}", popup.width - 28)
            y = self._draw_key_value(x, y, "底盘功率上限", power_limit, popup.width - 28)
            heat_value = "不适用" if profile.heat_capacity is None else f"{current_heat:.1f} / {heat_limit}"
            y = self._draw_key_value(x, y, "当前热量", heat_value, popup.width - 28)
            y = self._draw_key_value(x, y, "射击热量上限", heat_limit, popup.width - 28)
            y = self._draw_key_value(x, y, "热量冷却", self._format_rule_value(profile.heat_cooling_per_second, "/秒"), popup.width - 28)
            y = self._draw_key_value(x, y, "单发热量", self._format_rule_value(profile.heat_per_shot, ""), popup.width - 28)
            y = self._draw_key_value(x, y, "弹丸单发原始伤害", str(profile.raw_projectile_damage or "—"), popup.width - 28)
            y = self._draw_key_value(x, y, "撞击扣血", str(profile.collision_damage or "不适用"), popup.width - 28)
            y = self._draw_key_value(x, y, "二维碰撞半径", f"{ROBOT_ENTITY_COLLISION_RADIUS:.2f} 米", popup.width - 28)
            y = self._draw_key_value(x, y, "受攻击/撞击扣血", "适用" if profile.collision_applies else "不适用", popup.width - 28)
            if ammo is not None:
                if team == "red" and target_id != 2:
                    y = self._draw_adjustable_progress_bar(
                        x, y, popup.width - 28, "当前弹量", ammo,
                        self.task.own_robot_ammunition_limit(target_id),
                        (225, 166, 58), target_id, compact=True,
                        action="own_robot_ammo",
                    )
                else:
                    y = self._draw_key_value(x, y, "当前弹量", str(ammo), popup.width - 28)
            position = self.task.robot_position(target_id) if team == "blue" else self.task.own_robot_position(target_id, self.sentry)
            y = self._draw_key_value(x, y, "坐标（米）", f"{position[0]:.2f}，{position[1]:.2f}", popup.width - 28)
            y = self._draw_key_value(x, y, "控制方式", "哨兵决策" if team == "red" and target_id == 8 else "场景手动控制", popup.width - 28)
        button_y = popup.bottom - 42
        if target_id in ROBOT_PROFILES and (team == "red" or target_id != 5):
            drive = self.pg.Rect(x, button_y, 86, 30)
            self._draw_click_button(drive, "驾驶")
            action = "control_own_robot" if team == "red" else "control_enemy_robot"
            self.click_regions.append((drive, action, target_id, 0))
        elif target_id in (6, 7):
            health_action = (
                "enemy_health" if team == "blue" else
                "own_outpost_health" if target_id == 6 else "own_base_health"
            )
            for index, direction in enumerate((-1, 1)):
                button = self.pg.Rect(x + index * 80, button_y, 72, 30)
                self._draw_click_button(button, "血量 −" if direction < 0 else "血量 +")
                self.click_regions.append((button, health_action, target_id, direction))
        unpin = self.pg.Rect(popup.right - 102, button_y, 88, 30)
        pinned = self.pinned_robot_key is not None
        self._draw_click_button(unpin, "取消固定" if pinned else "固定")
        self.click_regions.append((unpin, "unpin_robot_property" if pinned else "robot_property", active, 0))

    def _property_target_values(self, team: str, target_id: int):
        if target_id in ROBOT_PROFILES:
            profile = ROBOT_PROFILES[target_id]
            health = (
                self.task.enemy_health(target_id)
                if team == "blue"
                else self.task.own_robot_health(target_id)
            )
            ammo = self.task.robot_ammunition(target_id, team=team)
            side = "蓝方" if team == "blue" else "己方"
            return f"{side} {target_id}号 {profile.role}", profile, health, profile.max_hp, ammo
        side = "蓝方" if team == "blue" else "己方"
        if target_id == 6:
            return f"{side}前哨", None, self.task.enemy_health(6) if team == "blue" else self.task.own_outpost_hp, RULE_OUTPOST_HP, None
        return f"{side}基地", None, self.task.enemy_health(7) if team == "blue" else self.task.own_base_hp, RULE_BASE_HP, None

    @staticmethod
    def _format_rule_value(value, suffix: str) -> str:
        return "不适用" if value is None else f"{value}{suffix}"

    def _draw_enemy_panel(self, rect) -> None:
        x = rect.left + 16
        bar_width = rect.width - 32
        y = rect.top + 15
        y = self._draw_panel_title(x, y, "敌方单位与执行状态", bar_width)

        y = self._draw_section_title(x, y, "敌方建筑")
        y = self._draw_adjustable_progress_bar(
            x, y, bar_width, "蓝方前哨", self.task.enemy_health(6), RULE_OUTPOST_HP, (57, 124, 210), 6
        )
        y = self._draw_adjustable_progress_bar(
            x, y, bar_width, "蓝方基地", self.task.enemy_health(7), 5000, (74, 145, 222), 7
        )

        y = self._draw_section_title(x, y + 3, "蓝方机器人血量")
        robot_names = {
            1: "英雄",
            2: "工程",
            3: "步兵",
            4: "步兵",
            5: "空中",
            8: "哨兵",
        }
        for entity in (item for item in FIELD_ENTITIES if item.kind == "robot"):
            selected = (
                self.controlled_robot_team == "blue"
                and entity.target_id == self.controlled_robot_id
            )
            color = (238, 183, 61) if selected else (68, 133, 217)
            y = self._draw_adjustable_progress_bar(
                x,
                y,
                bar_width,
                f"{entity.target_id} 号 {robot_names[entity.target_id]}",
                self.task.enemy_health(entity.target_id),
                entity.max_hp,
                color,
                entity.target_id,
                compact=True,
            )

        y = self._draw_section_title(x, y + 3, "执行输出")
        y = self._draw_key_value(
            x,
            y,
            "选定目标",
            f"{self.decision.target} 号" if self.decision.target else "无",
            bar_width,
        )
        y = self._draw_key_value(
            x,
            y,
            "云台状态",
            "自动旋转" if self.decision.tripod_mode else "锁定停止",
            bar_width,
        )
        y = self._draw_key_value(
            x,
            y,
            "小陀螺",
            {0: "关闭", 1: "低速旋转", 2: "中速旋转", 3: "高速旋转"}.get(
                self.decision.spin_mode, "未知模式"
            ),
            bar_width,
        )
        y = self._draw_key_value(x, y, "射击状态", self._shooting_status(), bar_width)
        y = self._draw_key_value(
            x,
            y,
            "确认复活",
            "是" if self.decision.confirm_respawn else "否",
            bar_width,
        )
        self._draw_key_value(
            x,
            y,
            "人工控制",
            f"{('己方' if self.controlled_robot_team == 'red' else '蓝方')} "
            f"{self.controlled_robot_id} 号"
            if self.controlled_robot_id is not None
            else "未选择",
            bar_width,
        )

    def _draw_own_panel(self, rect) -> None:
        x = rect.left + 14
        width = rect.width - 28
        y = rect.top + 15
        y = self._draw_panel_title(x, y, "己方机器人属性与控制", width)
        y = self._draw_section_title(x, y, "血量、弹量、位置")

        names = {1: "英雄", 2: "工程", 3: "步兵", 4: "步兵", 5: "空中", 8: "哨兵"}
        for target_id in (1, 2, 3, 4, 5, 8):
            y = self._draw_own_robot_card(
                x,
                y,
                width,
                target_id,
                names[target_id],
            )

        y = self._draw_section_title(x, y + 2, "碰撞与操作")
        y = self._draw_key_value(
            x,
            y,
            "底盘碰撞半径",
            f"{ROBOT_ENTITY_COLLISION_RADIUS:.2f} 米",
            width,
        )
        y = self._draw_key_value(
            x,
            y,
            "当前驾驶",
            self._control_name(),
            width,
        )
        self._draw_wrapped_status(
            x,
            y + 2,
            width,
            "移动",
            "选择单位后使用 W/A/S/D 或方向键；碰撞场地障碍和其他机器人",
        )

    def _draw_own_robot_card(
        self, x: int, y: int, width: int, target_id: int, name: str
    ) -> int:
        selected = (
            self.sentry.manual_control and target_id == 8
        ) or (
            self.controlled_robot_team == "red"
            and self.controlled_robot_id == target_id
        )
        color = (244, 190, 67) if selected else (62, 184, 112)
        label = self.panel_label_font.render(
            f"{target_id} 号 {name}", True, color
        )
        self.screen.blit(label, (x, y))

        control_button = self.pg.Rect(x + width - 66, y - 1, 66, 25)
        self._draw_click_button(control_button, "驾驶中" if selected else "驾驶")
        self.click_regions.append((control_button, "control_own_robot", target_id, 0))

        health = self.task.own_robot_health(target_id)
        maximum = next(
            entity.max_hp
            for entity in OWN_FIELD_ENTITIES
            if entity.target_id == target_id
        )
        ammo = self.task.own_robot_ammunition(target_id)
        ammo_maximum = self.task.own_robot_ammunition_limit(target_id)
        stat_y = y + 26
        self.screen.blit(
            self.panel_label_font.render(
                f"血量 {round(health)}/{maximum}", True, (214, 220, 222)
            ),
            (x, stat_y),
        )
        health_minus = self.pg.Rect(x + width - 58, stat_y - 1, 24, 23)
        health_plus = self.pg.Rect(x + width - 30, stat_y - 1, 24, 23)
        self._draw_click_button(health_minus, "−")
        self._draw_click_button(health_plus, "+")
        self.click_regions.append((health_minus, "own_robot_health", target_id, -1))
        self.click_regions.append((health_plus, "own_robot_health", target_id, 1))

        ammo_y = stat_y + 36
        ammo_minus = self.pg.Rect(x + width - 58, ammo_y - 1, 24, 23)
        ammo_plus = self.pg.Rect(x + width - 30, ammo_y - 1, 24, 23)
        self._draw_click_button(ammo_minus, "−")
        self._draw_click_button(ammo_plus, "+")
        self.click_regions.append((ammo_minus, "own_robot_ammo", target_id, -1))
        self.click_regions.append((ammo_plus, "own_robot_ammo", target_id, 1))

        ratio = max(0.0, min(1.0, health / maximum if maximum else 0.0))
        bar = self.pg.Rect(x, stat_y + 29, width, 4)
        self.pg.draw.rect(self.screen, (48, 54, 58), bar)
        if ratio:
            self.pg.draw.rect(
                self.screen,
                color,
                (bar.x, bar.y, max(1, round(bar.width * ratio)), bar.height),
            )
        self.screen.blit(
            self.panel_label_font.render(
                f"弹量 {ammo}/{ammo_maximum}", True, (178, 188, 192)
            ),
            (x, ammo_y),
        )

        position = self.task.own_robot_position(target_id, self.sentry)
        position_text = self.small_font.render(
            f"坐标 {position[0]:05.2f}，{position[1]:05.2f}",
            True,
            (151, 164, 169),
        )
        self.screen.blit(position_text, (x, stat_y + 66))
        return y + 126

    def _draw_panel_title(self, x: int, y: int, text: str, width: int) -> int:
        rendered = self.panel_title_font.render(text, True, (239, 242, 243))
        self.screen.blit(rendered, (x, y))
        line_y = y + 39
        self.pg.draw.line(self.screen, (76, 85, 90), (x, line_y), (x + width, line_y), 1)
        return y + 50

    def _draw_section_title(self, x: int, y: int, text: str) -> int:
        rendered = self.panel_label_font.render(text, True, (118, 177, 191))
        self.screen.blit(rendered, (x, y))
        return y + 32

    def _draw_key_value(self, x: int, y: int, key: str, value: str, width: int) -> int:
        key_text = self.panel_label_font.render(key, True, (151, 161, 166))
        value_text = self.panel_label_font.render(value, True, (226, 230, 231))
        self.screen.blit(key_text, (x, y))
        self.screen.blit(value_text, value_text.get_rect(topright=(x + width, y)))
        return y + 31

    def _draw_progress_bar(
        self,
        x: int,
        y: int,
        width: int,
        label: str,
        value: float,
        maximum: float,
        color,
        suffix: str = "",
        *,
        compact: bool = False,
    ) -> int:
        numeric_value = max(0.0, min(float(value), float(maximum)))
        ratio = numeric_value / maximum if maximum > 0 else 0.0
        label_text = self.panel_label_font.render(label, True, (190, 198, 201))
        shown_value = (
            f"{round(value)}{suffix}"
            if suffix
            else f"{round(value)}/{round(maximum)}"
        )
        value_text = self.panel_label_font.render(shown_value, True, (224, 228, 230))
        self.screen.blit(label_text, (x, y))
        self.screen.blit(value_text, value_text.get_rect(topright=(x + width, y)))
        bar_y = y + 27
        bar_height = 8 if compact else 12
        self.pg.draw.rect(self.screen, (48, 54, 58), (x, bar_y, width, bar_height))
        if ratio > 0.0:
            self.pg.draw.rect(
                self.screen,
                color,
                (x, bar_y, max(1, round(width * ratio)), bar_height),
            )
        return y + (43 if compact else 49)

    def _draw_match_time_control(self, x: int, y: int, width: int) -> int:
        key_text = self.panel_label_font.render("比赛剩余", True, (151, 161, 166))
        self.screen.blit(key_text, (x, y))

        reset_button = self.pg.Rect(x + width - 58, y - 2, 58, 29)
        plus_button = self.pg.Rect(reset_button.left - 30, y - 2, 26, 29)
        minus_button = self.pg.Rect(plus_button.left - 30, y - 2, 26, 29)
        value_text = self.panel_label_font.render(
            f"{round(self.task.remaining_time)} 秒", True, (226, 230, 231)
        )
        self.screen.blit(
            value_text,
            value_text.get_rect(topright=(minus_button.left - 7, y)),
        )
        self._draw_click_button(minus_button, "-")
        self._draw_click_button(plus_button, "+")
        self._draw_click_button(reset_button, "重置")
        self.click_regions.append((minus_button, "adjust_time", 0, -1))
        self.click_regions.append((plus_button, "adjust_time", 0, 1))
        self.click_regions.append((reset_button, "reset_time", 0, 0))
        return y + 35

    def _draw_control_buttons(self, x: int, y: int, width: int) -> int:
        gap = 8
        button_width = (width - gap) // 2
        auto_button = self.pg.Rect(x, y, button_width, 34)
        restart_button = self.pg.Rect(
            x + button_width + gap,
            y,
            width - button_width - gap,
            34,
        )
        self._draw_click_button(auto_button, "自动控制 0")
        self._draw_click_button(restart_button, "重新启动 R")
        self.click_regions.append((auto_button, "auto_control", 0, 0))
        self.click_regions.append((restart_button, "restart_validation", 0, 0))
        return y + 43

    def _draw_adjustable_progress_bar(
        self,
        x: int,
        y: int,
        width: int,
        label: str,
        value: float,
        maximum: float,
        color,
        target_id: int,
        *,
        suffix: str = "",
        compact: bool = False,
        action: str = "enemy_health",
    ) -> int:
        numeric_value = max(0.0, min(float(value), float(maximum)))
        ratio = numeric_value / maximum if maximum > 0 else 0.0
        label_text = self.panel_label_font.render(label, True, (190, 198, 201))
        self.screen.blit(label_text, (x, y))

        button_size = 26
        plus_button = self.pg.Rect(x + width - button_size, y - 2, button_size, button_size)
        minus_button = self.pg.Rect(plus_button.left - button_size - 4, y - 2, button_size, button_size)
        shown_value = (
            f"{round(value)}{suffix}"
            if suffix
            else f"{round(value)}/{round(maximum)}"
        )
        value_text = self.panel_label_font.render(
            shown_value, True, (224, 228, 230)
        )
        self.screen.blit(value_text, value_text.get_rect(topright=(minus_button.left - 6, y)))
        self._draw_click_button(minus_button, "-")
        self._draw_click_button(plus_button, "+")
        self.click_regions.append((minus_button, action, target_id, -1))
        self.click_regions.append((plus_button, action, target_id, 1))

        bar_y = y + 29
        bar_height = 8 if compact else 12
        self.pg.draw.rect(self.screen, (48, 54, 58), (x, bar_y, width, bar_height))
        if ratio > 0.0:
            self.pg.draw.rect(
                self.screen,
                color,
                (x, bar_y, max(1, round(width * ratio)), bar_height),
            )
        return y + (46 if compact else 51)

    def _draw_click_button(self, rect, text: str) -> None:
        hovered = rect.collidepoint(self.pg.mouse.get_pos())
        background = (75, 86, 92) if hovered else (50, 58, 63)
        self.pg.draw.rect(self.screen, background, rect)
        self.pg.draw.rect(self.screen, (104, 117, 123), rect, 1)
        rendered = self.panel_label_font.render(text, True, (236, 239, 240))
        self.screen.blit(rendered, rendered.get_rect(center=rect.center))

    def _draw_snapshot_bar(self) -> None:
        width, height = self.screen.get_size()
        top = height - SNAPSHOT_BAR_HEIGHT
        self.pg.draw.rect(
            self.screen,
            (35, 39, 42),
            (0, top, width, SNAPSHOT_BAR_HEIGHT),
        )
        self.pg.draw.line(
            self.screen,
            (79, 88, 93),
            (0, top),
            (width, top),
            1,
        )

        x = 20
        tab_height = 44
        tab_top = top + 9
        maximum_right = width - 260
        for index, snapshot in enumerate(self.snapshots):
            name = str(snapshot.get("name") or f"场景 {index + 1}")
            tab_width = max(140, min(210, self.panel_label_font.size(name)[0] + 70))
            if x + tab_width > maximum_right:
                break
            rect = self.pg.Rect(x, tab_top, tab_width, tab_height)
            active = index == self.active_snapshot_index
            background = (244, 246, 247) if active else (55, 62, 66)
            border = (186, 194, 198) if active else (91, 101, 106)
            color = (18, 142, 76) if active else (224, 230, 232)
            self.pg.draw.rect(self.screen, background, rect, border_radius=8)
            self.pg.draw.rect(
                self.screen,
                border,
                rect,
                1,
                border_radius=8,
            )
            close_size = 26
            close_rect = self.pg.Rect(
                rect.right - close_size - 8,
                rect.centery - close_size // 2,
                close_size,
                close_size,
            )
            label_rect = self.pg.Rect(
                rect.left + 10,
                rect.top,
                rect.width - close_size - 24,
                rect.height,
            )
            rendered = self.panel_label_font.render(name, True, color)
            self.screen.blit(rendered, rendered.get_rect(center=label_rect.center))
            close_hovered = close_rect.collidepoint(self.pg.mouse.get_pos())
            close_color = (218, 72, 72) if close_hovered else (156, 164, 168)
            close_text = self.panel_label_font.render("×", True, close_color)
            self.screen.blit(close_text, close_text.get_rect(center=close_rect.center))
            self.click_regions.append((rect, "load_snapshot", index, 0))
            self.click_regions.append((close_rect, "delete_snapshot", index, 0))
            x += tab_width + 7

        plus_button = self.pg.Rect(x, tab_top, 48, tab_height)
        self.pg.draw.rect(
            self.screen,
            (55, 62, 66),
            plus_button,
            border_radius=8,
        )
        self.pg.draw.rect(
            self.screen,
            (91, 101, 106),
            plus_button,
            1,
            border_radius=8,
        )
        plus = self.title_font.render("+", True, (231, 235, 237))
        self.screen.blit(plus, plus.get_rect(center=plus_button.center))
        self.click_regions.append((plus_button, "save_snapshot", 0, 0))

        hint = self.small_font.render(
            "Ctrl+S 保存｜点击标签恢复｜× 删除｜R 重新启动",
            True,
            (170, 180, 185),
        )
        self.screen.blit(
            hint,
            hint.get_rect(midright=(width - 20, top + SNAPSHOT_BAR_HEIGHT // 2)),
        )

    def _draw_wrapped_status(
        self, x: int, y: int, width: int, label: str, value: str
    ) -> None:
        label_text = self.panel_label_font.render(label, True, (151, 161, 166))
        self.screen.blit(label_text, (x, y))
        words = list(value)
        lines: list[str] = []
        current = ""
        for word in words:
            candidate = current + word
            if self.panel_label_font.size(candidate)[0] <= width:
                current = candidate
            else:
                lines.append(current)
                current = word
        if current:
            lines.append(current)
        for index, line in enumerate(lines[:2]):
            rendered = self.panel_label_font.render(line, True, (226, 230, 231))
            self.screen.blit(rendered, (x, y + 31 + index * 27))

    def _control_name(self) -> str:
        if self.sentry.manual_control:
            return "己方哨兵"
        if self.controlled_robot_id is not None:
            team_name = "己方" if self.controlled_robot_team == "red" else "蓝方"
            return f"{team_name} {self.controlled_robot_id} 号"
        return "决策自动"

    def _shooting_status(self) -> str:
        requested = (
            self.manual_fire_active
            if self.sentry.manual_control
            else bool(self.decision.shoot_mode)
        )
        if not requested:
            return "停止"
        if self.hit_target_id is None:
            return "开火｜枪口未对准"
        return f"开火｜命中 {self.hit_target_id} 号"

    def _goal_name(self) -> str:
        goal = self.decision.goal
        if goal is None:
            return "无"
        if goal == HOME:
            return "归位点"
        if goal == SUPPLY:
            return "补给区"
        if goal == ATTACK:
            return "攻击点"
        return f"{goal[0]:.1f}，{goal[1]:.1f}"

    def _draw_arena(self, viewport: Viewport) -> None:
        rect = self.pg.Rect(
            round(viewport.left),
            round(viewport.top),
            round(viewport.width),
            round(viewport.height),
        )
        if self.scaled_map_size != rect.size:
            self.scaled_map = self.pg.transform.smoothscale(self.map_surface, rect.size)
            self.scaled_map_size = rect.size
        self.screen.blit(self.scaled_map, rect)

        previous_clip = self.screen.get_clip()
        self.screen.set_clip(rect)
        self._draw_grid(viewport)
        self._draw_supply_zone(viewport)
        self._draw_sensor_view(viewport)
        self._draw_patrol_route(viewport)
        self._draw_entities(viewport)
        self._draw_objectives(viewport)
        self._draw_navigation(viewport)
        self._draw_sentry(viewport)
        self.screen.set_clip(previous_clip)

        self.pg.draw.rect(self.screen, (103, 114, 120), rect, 2)
        self._draw_axes(viewport)

    def _draw_grid(self, viewport: Viewport) -> None:
        for x in range(1, int(self.arena.width)):
            start = viewport.world_to_screen(x, 0.0)
            end = viewport.world_to_screen(x, self.arena.height)
            color = (170, 178, 181) if x % 5 == 0 else (220, 224, 225)
            self.pg.draw.line(self.screen, color, start, end, 1)
        for y in range(1, int(self.arena.height)):
            start = viewport.world_to_screen(0.0, y)
            end = viewport.world_to_screen(self.arena.width, y)
            color = (170, 178, 181) if y % 5 == 0 else (220, 224, 225)
            self.pg.draw.line(self.screen, color, start, end, 1)

    def _draw_axes(self, viewport: Viewport) -> None:
        for x in range(0, 29, 2):
            screen_x, screen_y = viewport.world_to_screen(x, 0.0)
            label = self.small_font.render(str(x), True, (173, 182, 186))
            self.screen.blit(label, label.get_rect(midtop=(round(screen_x), round(screen_y) + 5)))
        for y in range(0, 16, 5):
            screen_x, screen_y = viewport.world_to_screen(0.0, y)
            label = self.small_font.render(str(y), True, (173, 182, 186))
            self.screen.blit(label, label.get_rect(midright=(round(screen_x) - 7, round(screen_y))))

    def _draw_supply_zone(self, viewport: Viewport) -> None:
        minimum_x, maximum_x, minimum_y, maximum_y = SUPPLY_ZONE
        left, top = viewport.world_to_screen(minimum_x, maximum_y)
        right, bottom = viewport.world_to_screen(maximum_x, minimum_y)
        zone_rect = self.pg.Rect(
            round(left),
            round(top),
            max(1, round(right - left)),
            max(1, round(bottom - top)),
        )

        overlay = self.pg.Surface(zone_rect.size, self.pg.SRCALPHA)
        overlay.fill((37, 174, 99, 58))
        self.screen.blit(overlay, zone_rect)
        self.pg.draw.rect(self.screen, (35, 165, 93), zone_rect, 2)

        label = self.small_font.render("补给区", True, (20, 112, 62))
        label_background = label.get_rect(topleft=(zone_rect.left + 5, zone_rect.top + 4)).inflate(8, 4)
        self.pg.draw.rect(self.screen, (231, 247, 237), label_background)
        self.screen.blit(label, (zone_rect.left + 9, zone_rect.top + 6))

    def _draw_objectives(self, viewport: Viewport) -> None:
        objectives = (
            (4.971, 7.5, "归位点", (38, 160, 218)),
            (*ATTACK, "攻击点", (215, 74, 73)),
        )
        for x, y, name, color in objectives:
            center = self.pg.Vector2(viewport.world_to_screen(x, y))
            radius = 8
            self.pg.draw.circle(self.screen, (247, 249, 249), center, radius + 2)
            self.pg.draw.circle(self.screen, color, center, radius, 2)
            self.pg.draw.line(
                self.screen,
                color,
                (center.x - radius - 4, center.y),
                (center.x + radius + 4, center.y),
                1,
            )
            self.pg.draw.line(
                self.screen,
                color,
                (center.x, center.y - radius - 4),
                (center.x, center.y + radius + 4),
                1,
            )
            label = self.small_font.render(name, True, color)
            self.screen.blit(label, (round(center.x + 12), round(center.y - 21)))

    def _draw_sensor_view(self, viewport: Viewport) -> None:
        center = self.pg.Vector2(viewport.world_to_screen(self.sentry.x, self.sentry.y))
        half_angle = AUTOAIM_HALF_VIEW

        def sector_points(distance: float):
            radius = viewport.scale * distance
            points = [center]
            for index in range(17):
                angle = (
                    self.sentry.turret_angle
                    - half_angle
                    + 2.0 * half_angle * index / 16.0
                )
                points.append(
                    center
                    + self.pg.Vector2(
                        math.cos(angle) * radius,
                        -math.sin(angle) * radius,
                    )
                )
            return points

        detection_points = sector_points(DETECTION_RANGE)
        attack_points = sector_points(ATTACK_RANGE)
        overlay = self.pg.Surface(self.screen.get_size(), self.pg.SRCALPHA)
        detection_color = (47, 177, 197, 28) if self.decision.tripod_mode else (195, 82, 96, 28)
        self.pg.draw.polygon(overlay, detection_color, detection_points)
        self.pg.draw.polygon(overlay, (242, 158, 54, 46), attack_points)
        self.screen.blit(overlay, (0, 0))

        detection_edge = (55, 154, 172) if self.decision.tripod_mode else (184, 72, 84)
        attack_edge = (225, 126, 36)
        self.pg.draw.line(
            self.screen, detection_edge, detection_points[0], detection_points[1], 1
        )
        self.pg.draw.line(
            self.screen, detection_edge, detection_points[0], detection_points[-1], 1
        )
        self.pg.draw.line(self.screen, attack_edge, attack_points[0], attack_points[1], 2)
        self.pg.draw.line(self.screen, attack_edge, attack_points[0], attack_points[-1], 2)

        direction = self.pg.Vector2(
            math.cos(self.sentry.turret_angle),
            -math.sin(self.sentry.turret_angle),
        )
        detection_label = self.small_font.render(
            f"探测 {DETECTION_RANGE:.1f}m", True, detection_edge
        )
        attack_label = self.small_font.render(
            f"攻击 {ATTACK_RANGE:.1f}m", True, attack_edge
        )
        detection_anchor = center + direction * (viewport.scale * DETECTION_RANGE)
        attack_anchor = center + direction * (viewport.scale * ATTACK_RANGE)
        self.screen.blit(
            detection_label,
            detection_label.get_rect(midleft=(detection_anchor.x + 4, detection_anchor.y)),
        )
        self.screen.blit(
            attack_label,
            attack_label.get_rect(midleft=(attack_anchor.x + 4, attack_anchor.y)),
        )

    def _draw_patrol_route(self, viewport: Viewport) -> None:
        routes = (
            (
                CONSERVATIVE_PATROL_POINTS,
                "保守",
                (68, 116, 132) if not self.task.patrol_is_aggressive else (137, 151, 157),
                not self.task.patrol_is_aggressive,
            ),
            (
                AGGRESSIVE_PATROL_POINTS,
                "激进",
                (222, 86, 48) if self.task.patrol_is_aggressive else (190, 126, 101),
                self.task.patrol_is_aggressive,
            ),
        )
        for route_points, label_prefix, route_color, active in sorted(
            routes,
            key=lambda route: route[3],
        ):
            points = [
                viewport.world_to_screen(x, y) for x, y in route_points
            ]
            self.pg.draw.lines(
                self.screen,
                route_color,
                True,
                points,
                4 if active else 2,
            )
            for index, point in enumerate(points, start=1):
                radius = 7 if active else 5
                self.pg.draw.circle(self.screen, (248, 249, 249), point, radius)
                self.pg.draw.circle(
                    self.screen,
                    route_color,
                    point,
                    radius,
                    3 if active else 2,
                )
                label = self.small_font.render(
                    f"{label_prefix} {index}",
                    True,
                    route_color,
                )
                self.screen.blit(
                    label,
                    (round(point[0] + 8), round(point[1] + 3)),
                )

    def _draw_entities(self, viewport: Viewport) -> None:
        robot_labels = []
        robot_names = {
            1: "1号 英雄",
            2: "2号 工程",
            3: "3号 步兵",
            4: "4号 步兵",
            5: "5号 空中",
            8: "8号 哨兵",
        }
        for entity in FIELD_ENTITIES:
            entity_x, entity_y = entity.x, entity.y
            if entity.kind == "robot":
                entity_x, entity_y = self.task.robot_position(entity.target_id)
            center = self.pg.Vector2(viewport.world_to_screen(entity_x, entity_y))
            color = (193, 60, 67) if entity.team == "red" else (46, 104, 190)
            hp = entity.hp
            if entity.team == "blue":
                hp = self.task.enemy_health(entity.target_id)
            elif entity.name == "RED OUTPOST":
                hp = self.task.own_outpost_hp
            elif entity.name == "RED BASE":
                hp = self.task.own_base_hp
            if hp <= 0:
                color = (116, 121, 124)

            if entity.kind == "base":
                rect = self.pg.Rect(0, 0, 18, 18)
                rect.center = center
                self.pg.draw.rect(self.screen, (247, 249, 249), rect.inflate(4, 4))
                self.pg.draw.rect(self.screen, color, rect, 3)
            elif entity.kind == "outpost":
                self.pg.draw.circle(self.screen, (247, 249, 249), center, 11)
                self.pg.draw.circle(self.screen, color, center, 9, 3)
            else:
                collider_radius = max(
                    8,
                    round(ROBOT_ENTITY_COLLISION_RADIUS * viewport.scale),
                )
                profile = ROBOT_PROFILES.get(entity.target_id)
                if profile is not None:
                    self._draw_robot_mechanism(
                        viewport,
                        center,
                        collider_radius,
                        profile,
                        entity.target_id,
                        entity.team,
                    )
                self.pg.draw.circle(self.screen, (247, 249, 249), center, collider_radius)
                self.pg.draw.circle(
                    self.screen,
                    (92, 105, 111),
                    center,
                    collider_radius,
                    1,
                )
                if (
                    self.controlled_robot_team == "blue"
                    and entity.target_id == self.controlled_robot_id
                ):
                    self.pg.draw.circle(
                        self.screen, (35, 39, 42), center, collider_radius + 4
                    )
                    self.pg.draw.circle(
                        self.screen, (244, 190, 67), center, collider_radius + 3, 3
                    )
                self.pg.draw.circle(self.screen, (247, 249, 249), center, 8)
                self.pg.draw.circle(self.screen, color, center, 7, 2)
                number = self.small_font.render(str(entity.target_id), True, color)
                self.screen.blit(number, number.get_rect(center=center))
                robot_labels.append(
                    (center, robot_names.get(entity.target_id, entity.name), color)
                )

        for entity in OWN_FIELD_ENTITIES:
            if entity.target_id == 8:
                continue
            entity_x, entity_y = self.task.own_robot_position(entity.target_id)
            center = self.pg.Vector2(viewport.world_to_screen(entity_x, entity_y))
            color = (193, 60, 67)
            if self.task.own_robot_health(entity.target_id) <= 0:
                color = (116, 121, 124)
            collider_radius = max(
                8,
                round(ROBOT_ENTITY_COLLISION_RADIUS * viewport.scale),
            )
            self._draw_robot_mechanism(
                viewport,
                center,
                collider_radius,
                ROBOT_PROFILES[entity.target_id],
                entity.target_id,
                "red",
            )
            self.pg.draw.circle(self.screen, (247, 249, 249), center, collider_radius)
            self.pg.draw.circle(
                self.screen,
                (92, 105, 111),
                center,
                collider_radius,
                1,
            )
            if (
                self.controlled_robot_team == "red"
                and entity.target_id == self.controlled_robot_id
            ):
                self.pg.draw.circle(
                    self.screen, (35, 39, 42), center, collider_radius + 4
                )
                self.pg.draw.circle(
                    self.screen, (244, 190, 67), center, collider_radius + 3, 3
                )
            self.pg.draw.circle(self.screen, (247, 249, 249), center, 8)
            self.pg.draw.circle(self.screen, color, center, 7, 2)
            number = self.small_font.render(str(entity.target_id), True, color)
            self.screen.blit(number, number.get_rect(center=center))
            robot_labels.append(
                (center, f"己方 {robot_names[entity.target_id]}", color)
            )

        occupied = []
        for center, name, color in robot_labels:
            rendered = self.small_font.render(name, True, color)
            label_rect = rendered.get_rect(midbottom=(center.x, center.y - 13))
            while any(label_rect.colliderect(other) for other in occupied):
                label_rect.y -= label_rect.height + 3
            background = label_rect.inflate(8, 4)
            self.pg.draw.line(
                self.screen,
                color,
                center,
                (label_rect.centerx, label_rect.bottom + 2),
                1,
            )
            self.pg.draw.rect(self.screen, (247, 249, 249), background, border_radius=4)
            self.pg.draw.rect(self.screen, color, background, 1, border_radius=4)
            self.screen.blit(rendered, label_rect)
            occupied.append(background)

    def _draw_robot_mechanism(
        self,
        viewport: Viewport,
        center,
        collider_radius: int,
        profile,
        target_id: int,
        team: str,
    ) -> None:
        """Draw the reusable chassis turntable and weapon/camera gimbal.

        The full 3-D mechanisms are intentionally represented as compact
        top-down cues: a rotating outer platform, a gimbal ring, and a barrel
        direction.  This keeps every robot legible at the map zoom while
        preserving the rulebook distinction between chassis and gimbal motion.
        """
        if not (profile.has_gimbal or profile.has_turntable):
            return
        phase = (self.task.remaining_time * 0.18) + target_id * 0.73
        if team == "red":
            phase += math.pi
        if profile.has_turntable:
            ring_color = (184, 65, 70) if team == "red" else (48, 105, 185)
            self.pg.draw.circle(self.screen, ring_color, center, collider_radius + 2, 2)
            for offset in (0.0, math.tau / 3.0, 2.0 * math.tau / 3.0):
                angle = phase + offset
                marker = center + self.pg.Vector2(
                    math.cos(angle) * (collider_radius + 1),
                    -math.sin(angle) * (collider_radius + 1),
                )
                self.pg.draw.circle(self.screen, ring_color, marker, 2)
        if profile.has_gimbal:
            gimbal_angle = phase * 0.35 + target_id * 0.21
            direction = self.pg.Vector2(math.cos(gimbal_angle), -math.sin(gimbal_angle))
            perpendicular = self.pg.Vector2(-direction.y, direction.x)
            mount_radius = max(4, collider_radius // 3)
            self.pg.draw.circle(self.screen, (38, 45, 50), center, mount_radius + 2)
            self.pg.draw.circle(self.screen, (232, 179, 65), center, mount_radius, 1)
            barrel_start = center + direction * (mount_radius * 0.35)
            barrel_end = center + direction * max(13, collider_radius + 7)
            self.pg.draw.line(self.screen, (36, 50, 57), barrel_start, barrel_end, 4)
            self.pg.draw.line(self.screen, (224, 228, 223), barrel_start, barrel_end, 1)
            self.pg.draw.line(
                self.screen,
                (232, 179, 65),
                center - perpendicular * mount_radius,
                center + perpendicular * mount_radius,
                1,
            )

    def _draw_navigation(self, viewport: Viewport) -> None:
        if self.decision.goal is None:
            return
        path_points = [
            viewport.world_to_screen(self.sentry.x, self.sentry.y),
            *(
                viewport.world_to_screen(x, y)
                for x, y in self.navigator.remaining_path
            ),
        ]
        if len(path_points) >= 2:
            self.pg.draw.lines(
                self.screen,
                (245, 191, 70),
                False,
                path_points,
                3,
            )
        goal = self.pg.Vector2(viewport.world_to_screen(*self.decision.goal))
        diamond = (
            (goal.x, goal.y - 9),
            (goal.x + 9, goal.y),
            (goal.x, goal.y + 9),
            (goal.x - 9, goal.y),
        )
        self.pg.draw.polygon(self.screen, (255, 247, 227), diamond)
        self.pg.draw.polygon(self.screen, (184, 125, 34), diamond, 2)

    def _draw_sentry(self, viewport: Viewport) -> None:
        center = self.pg.Vector2(viewport.world_to_screen(self.sentry.x, self.sentry.y))
        ring_radius = max(
            17,
            round(self.collision_grid.collision_radius * viewport.scale),
        )
        ring_color = (223, 139, 49) if self.decision.spin_mode else (128, 135, 138)
        self.pg.draw.circle(self.screen, (248, 248, 246), center, ring_radius + 3)
        self.pg.draw.circle(self.screen, ring_color, center, ring_radius, 3)

        for offset in (0.0, math.tau / 3.0, 2.0 * math.tau / 3.0):
            angle = self.sentry.spin_angle + offset
            marker = center + self.pg.Vector2(
                math.cos(angle) * ring_radius,
                -math.sin(angle) * ring_radius,
            )
            self.pg.draw.circle(self.screen, (74, 82, 87), marker, 4)
            self.pg.draw.circle(self.screen, ring_color, marker, 2)

        direction = self.pg.Vector2(
            math.cos(self.sentry.turret_angle),
            -math.sin(self.sentry.turret_angle),
        )
        perpendicular = self.pg.Vector2(-direction.y, direction.x)
        body_half_length = max(8.0, viewport.scale * 0.20)
        body_half_width = max(5.0, viewport.scale * 0.12)
        body = (
            center + direction * body_half_length + perpendicular * body_half_width,
            center + direction * body_half_length - perpendicular * body_half_width,
            center - direction * body_half_length - perpendicular * body_half_width,
            center - direction * body_half_length + perpendicular * body_half_width,
        )
        barrel_end = center + direction * max(34.0, viewport.scale * 0.90)
        self.pg.draw.line(self.screen, (29, 77, 94), center, barrel_end, 7)
        self.pg.draw.line(self.screen, (77, 200, 220), center, barrel_end, 3)
        self.pg.draw.polygon(self.screen, (46, 118, 137), body)
        self.pg.draw.polygon(self.screen, (19, 58, 70), body, 2)
        self.pg.draw.circle(self.screen, (220, 54, 69), center, 6)
        self.pg.draw.circle(self.screen, (255, 245, 235), center, 2)

def main() -> None:
    try:
        import pygame
    except ModuleNotFoundError as error:
        raise SystemExit(
            "尚未安装 Pygame，请执行：python -m pip install -r requirements.txt"
        ) from error
    try:
        SimulatorApp(pygame).run()
    except KeyboardInterrupt:
        pass
