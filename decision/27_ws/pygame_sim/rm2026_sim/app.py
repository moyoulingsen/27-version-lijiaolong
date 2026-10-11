"""Pygame UI for RMUC 2026 sentry motion verification."""

from __future__ import annotations

import math
from pathlib import Path

from .core import Arena, SentryState, Viewport
from .map_asset import load_p5_pgm
from .ros_bridge import BehaviorTreeBridgeClient
from .scenario_store import (
    ScenarioStore,
    capture_snapshot,
    restore_snapshot,
)
from .task_state import (
    AGGRESSIVE_PATROL_POINTS,
    ATTACK,
    CONSERVATIVE_PATROL_POINTS,
    HOME,
    SUPPLY,
    SUPPLY_ZONE,
    WEAPON_RANGE,
    DecisionView,
    FIELD_ENTITIES,
    TaskScenario,
)


APP_ROOT = Path(__file__).resolve().parent.parent
MAP_PATH = APP_ROOT / "assets" / "rmuc2026.pgm"
SNAPSHOT_PATH = APP_ROOT / "scenario_saves.json"
WINDOW_SIZE = (2240, 1260)
HEADER_HEIGHT = 112
SIDE_PANEL_WIDTH = 390
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
        self.map_surface = self._load_map_surface()
        self.scaled_map = None
        self.scaled_map_size = None
        self.click_regions: list[tuple[object, str, int, int]] = []
        self.manual_fire_active = False
        self.hit_target_id: int | None = None
        self._manual_fire_held = False
        self._restart_signal_remaining = 0.0

    def _load_map_surface(self):
        image = load_p5_pgm(MAP_PATH)
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
                        elif event.key in (self.pg.K_9, self.pg.K_KP9):
                            self._select_sentry()
                        elif event.key in (
                            self.pg.K_1,
                            self.pg.K_2,
                            self.pg.K_3,
                            self.pg.K_4,
                            self.pg.K_8,
                            self.pg.K_KP1,
                            self.pg.K_KP2,
                            self.pg.K_KP3,
                            self.pg.K_KP4,
                            self.pg.K_KP8,
                        ):
                            self._select_enemy_robot(event.key)
                        elif event.key in (self.pg.K_LSHIFT, self.pg.K_RSHIFT):
                            self._switch_to_auto_control()
                        else:
                            self._handle_task_key(event.key)
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
                motion_decision = bridge_decision or self.task.evaluate(self.sentry)
                restarting = self._restart_signal_remaining > 0.0
                simulation_elapsed = (
                    0.0
                    if self.task.game_paused or restarting
                    else elapsed_seconds
                )
                if self.controlled_robot_id is not None:
                    self.task.move_robot(
                        self.controlled_robot_id,
                        move_x,
                        move_y,
                        elapsed_seconds,
                        self.arena,
                    )
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
                    decision_override=bridge_decision,
                    fire_request=fire_request,
                    hit_target_id=self.hit_target_id,
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
        right = width - SIDE_PANEL_WIDTH - 24
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
        if self.sentry.manual_control:
            self.sentry.update(
                elapsed_seconds,
                manual_x,
                manual_y,
                self.arena,
                spin_enabled=decision.spin_mode > 0,
                spin_speed_scale=self._spin_speed_scale(decision.spin_mode),
                turret_enabled=not self._manual_fire_held,
            )
            return

        if self.bridge.connected and decision.goal is not None:
            goal_x, goal_y = decision.goal
            delta_x = goal_x - self.sentry.x
            delta_y = goal_y - self.sentry.y
            distance = math.hypot(delta_x, delta_y)
            if distance > 0.08:
                travel = min(distance, self.sentry.movement_speed * elapsed_seconds)
                self.sentry.x, self.sentry.y = self.arena.clamp(
                    self.sentry.x + delta_x / distance * travel,
                    self.sentry.y + delta_y / distance * travel,
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
        if math.hypot(delta_x, delta_y) > WEAPON_RANGE:
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
        enemy_hp = [
            round(self.task.enemy_health(1)),
            round(self.task.enemy_health(2)),
            round(self.task.enemy_health(3)),
            round(self.task.enemy_health(4)),
            round(self.task.enemy_health(5)),
            round(self.task.enemy_health(6)),
            round(self.task.enemy_health(7)),
            round(self.task.enemy_health(8)),
        ]
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
            "x": self.sentry.x,
            "y": self.sentry.y,
            "yaw": self.sentry.spin_angle,
            "autoaim": self._simulated_autoaim(enemy_hp),
            "aggressive_patrol": self.task.aggressive_patrol,
        }

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
            if distance <= WEAPON_RANGE and abs(relative_angle) <= AUTOAIM_HALF_VIEW:
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

    def _handle_task_key(self, key: int) -> None:
        if key == self.pg.K_F1:
            self.task.reset()
            self.sentry = SentryState()
            self.controlled_robot_id = None
            self._manual_fire_held = False
            self.manual_fire_active = False
            self.hit_target_id = None
            self._restart_validation()
        elif key == self.pg.K_F2:
            self.task.destroy_own_outpost()
        elif key == self.pg.K_F3:
            self.task.inject_unseen_damage(self.sentry)
        elif key == self.pg.K_F4:
            self.task.empty_ammo()
        elif key == self.pg.K_F5:
            self.task.destroy_enemy_outpost()
        elif key == self.pg.K_F6:
            self.task.set_low_health()
        elif key == self.pg.K_F7:
            self.task.finish_game()
        elif key == self.pg.K_F8:
            self.task.kill_sentry()
        elif key == self.pg.K_F9:
            self.task.toggle_patrol_mode()
        elif key == self.pg.K_F10:
            self.task.reset_match_time()

    def _handle_mouse_click(self, position: tuple[int, int]) -> bool:
        for rect, action, target_id, direction in reversed(self.click_regions):
            if not rect.collidepoint(position):
                continue
            if action == "reset_time":
                self.task.reset_match_time()
            elif action == "adjust_time":
                self.task.adjust_match_time(direction)
            elif action == "enemy_health":
                self.task.adjust_enemy_health(target_id, direction)
            elif action == "sentry_health":
                self.task.adjust_sentry_health(direction)
            elif action == "ammo":
                self.task.adjust_ammo(direction)
            elif action == "pending_ammo":
                self.task.adjust_pending_ammo(direction)
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
            return True
        return False

    def _select_sentry(self) -> None:
        self.controlled_robot_id = None
        self.sentry.enable_manual_control()

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
        self.controlled_robot_id = key_to_target[key]
        self._manual_fire_held = False
        self.sentry.cancel_manual_control()

    def _release_manual_control(self) -> None:
        self._switch_to_auto_control()

    def _switch_to_auto_control(self, *, notify: bool = True) -> None:
        self.controlled_robot_id = None
        self._manual_fire_held = False
        self.manual_fire_active = False
        self.sentry.cancel_manual_control()
        if notify:
            self.task.notify("已切换为自动控制")

    def _restart_validation(self) -> None:
        self._switch_to_auto_control(notify=False)
        self.task.game_running = True
        self.task.game_finished = False
        self.task.game_paused = False
        self._restart_signal_remaining = 0.20
        self.hit_target_id = None
        self.bridge.clear_output()
        self.decision = self.task.evaluate(self.sentry)
        self.task.notify("验证已重新启动，行为树正在复位")

    def _save_snapshot(self) -> None:
        name = f"场景 {len(self.snapshots) + 1}"
        snapshot = capture_snapshot(
            name,
            self.task,
            self.sentry,
            self.controlled_robot_id,
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
        self.active_snapshot_index = index
        self._manual_fire_held = False
        self.manual_fire_active = False
        self.hit_target_id = None
        self._restart_signal_remaining = 0.0
        self.bridge.clear_output()
        self.decision = self.task.evaluate(self.sentry)
        self.task.notify(
            f"已载入{self.snapshots[index].get('name', f'场景 {index + 1}')}"
        )

    def _render(self, viewport: Viewport) -> None:
        self.click_regions.clear()
        self.screen.fill((22, 25, 28))
        self._draw_header()
        self._draw_side_panels()
        self._draw_arena(viewport)
        self._draw_snapshot_bar()

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
            mode = f"人工控制｜蓝方 {self.controlled_robot_id} 号"
            mode_color = (74, 143, 224)
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
            position_label = f"蓝方 {self.controlled_robot_id} 号"
            position_x, position_y = self.task.robot_position(self.controlled_robot_id)
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
            width - SIDE_PANEL_WIDTH,
            HEADER_HEIGHT,
            SIDE_PANEL_WIDTH,
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
            (width - SIDE_PANEL_WIDTH - 1, HEADER_HEIGHT),
            (width - SIDE_PANEL_WIDTH - 1, height - SNAPSHOT_BAR_HEIGHT),
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
        y = self._draw_adjustable_progress_bar(
            x,
            y,
            bar_width,
            "己方前哨",
            self.task.own_outpost_hp,
            1000,
            (205, 75, 82),
            0,
            action="own_outpost_health",
        )
        y = self._draw_adjustable_progress_bar(
            x,
            y,
            bar_width,
            "己方基地",
            self.task.own_base_hp,
            5000,
            (177, 105, 190),
            0,
            action="own_base_health",
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
        posture_name = {1: "进攻", 2: "防御", 3: "移动"}.get(
            self.decision.posture, "未知"
        )
        y = self._draw_key_value(x, y, "当前姿态", posture_name, bar_width)
        y = self._draw_key_value(
            x, y, "回血阈值", str(self.decision.health_threshold), bar_width
        )
        self._draw_wrapped_status(x, y + 5, bar_width, "最近事件", self.task.event_message)

    def _draw_right_panel(self, rect) -> None:
        x = rect.left + 16
        bar_width = rect.width - 32
        y = rect.top + 15
        y = self._draw_panel_title(x, y, "敌方单位与执行状态", bar_width)

        y = self._draw_section_title(x, y, "敌方建筑")
        y = self._draw_adjustable_progress_bar(
            x, y, bar_width, "蓝方前哨", self.task.enemy_health(6), 1000, (57, 124, 210), 6
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
            selected = entity.target_id == self.controlled_robot_id
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
            f"蓝方 {self.controlled_robot_id} 号"
            if self.controlled_robot_id is not None
            else "未选择",
            bar_width,
        )

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
            tab_width = max(120, min(190, self.panel_label_font.size(name)[0] + 42))
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
            rendered = self.panel_label_font.render(name, True, color)
            self.screen.blit(rendered, rendered.get_rect(center=rect.center))
            self.click_regions.append((rect, "load_snapshot", index, 0))
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
            "Ctrl+S 保存场景｜点击标签恢复｜R 重新启动行为树",
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
            return f"蓝方 {self.controlled_robot_id} 号"
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
            (16.0, 11.0, "攻击点", (215, 74, 73)),
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
        radius = viewport.scale * 5.0
        half_angle = math.radians(24.0)
        points = [center]
        for index in range(17):
            angle = self.sentry.turret_angle - half_angle + 2.0 * half_angle * index / 16.0
            points.append(
                center
                + self.pg.Vector2(math.cos(angle) * radius, -math.sin(angle) * radius)
            )
        overlay = self.pg.Surface(self.screen.get_size(), self.pg.SRCALPHA)
        color = (47, 177, 197, 30) if self.decision.tripod_mode else (222, 74, 74, 36)
        self.pg.draw.polygon(overlay, color, points)
        self.screen.blit(overlay, (0, 0))
        edge_color = (55, 154, 172) if self.decision.tripod_mode else (210, 62, 62)
        self.pg.draw.line(self.screen, edge_color, points[0], points[1], 1)
        self.pg.draw.line(self.screen, edge_color, points[0], points[-1], 1)

    def _draw_patrol_route(self, viewport: Viewport) -> None:
        routes = (
            (
                CONSERVATIVE_PATROL_POINTS,
                "保守",
                (68, 116, 132) if not self.task.aggressive_patrol else (137, 151, 157),
                not self.task.aggressive_patrol,
            ),
            (
                AGGRESSIVE_PATROL_POINTS,
                "激进",
                (222, 86, 48) if self.task.aggressive_patrol else (190, 126, 101),
                self.task.aggressive_patrol,
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
                if entity.target_id == self.controlled_robot_id:
                    self.pg.draw.circle(self.screen, (35, 39, 42), center, 12)
                    self.pg.draw.circle(self.screen, (244, 190, 67), center, 11, 3)
                self.pg.draw.circle(self.screen, (247, 249, 249), center, 8)
                self.pg.draw.circle(self.screen, color, center, 7, 2)
                number = self.small_font.render(str(entity.target_id), True, color)
                self.screen.blit(number, number.get_rect(center=center))

    def _draw_navigation(self, viewport: Viewport) -> None:
        if self.decision.goal is None:
            return
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
        ring_radius = max(17, round(0.42 * viewport.scale))
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
