"""Pygame UI for RMUC 2026 sentry motion verification."""

from __future__ import annotations

import math
from pathlib import Path

from .core import Arena, SentryState, Viewport
from .map_asset import load_p5_pgm
from .ros_bridge import BehaviorTreeBridgeClient
from .task_state import (
    ATTACK,
    HOME,
    SUPPLY,
    SUPPLY_ZONE,
    DecisionView,
    FIELD_ENTITIES,
    TaskScenario,
)


APP_ROOT = Path(__file__).resolve().parent.parent
MAP_PATH = APP_ROOT / "assets" / "rmuc2026.pgm"
WINDOW_SIZE = (1440, 820)
MINIMUM_WINDOW_SIZE = (1180, 700)
HEADER_HEIGHT = 76
SIDE_PANEL_WIDTH = 250


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
        self.title_font = self.pg.font.Font(_font_path(True), 25)
        self.data_font = self.pg.font.Font(_font_path(False), 17)
        self.small_font = self.pg.font.Font(_font_path(False), 14)
        self.panel_title_font = self.pg.font.Font(_font_path(True), 18)
        self.panel_label_font = self.pg.font.Font(_font_path(False), 13)
        self.map_surface = self._load_map_surface()
        self.scaled_map = None
        self.scaled_map_size = None
        self.click_regions: list[tuple[object, str, int, int]] = []

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
                        if event.key == self.pg.K_ESCAPE:
                            running = False
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
                            self._release_manual_control()
                        else:
                            self._handle_task_key(event.key)
                    elif event.type == self.pg.VIDEORESIZE:
                        size = (
                            max(event.w, MINIMUM_WINDOW_SIZE[0]),
                            max(event.h, MINIMUM_WINDOW_SIZE[1]),
                        )
                        self.screen = self.pg.display.set_mode(size, self.pg.RESIZABLE)
                    elif event.type == self.pg.MOUSEBUTTONDOWN and event.button == 1:
                        self._handle_mouse_click(event.pos)

                viewport = self._viewport()
                move_x, move_y = self._movement_input()
                bridge_decision = self._bridge_decision()
                self.decision = self.task.update(
                    elapsed_seconds,
                    self.sentry,
                    decision_override=bridge_decision,
                )
                if self.controlled_robot_id is not None:
                    self.task.move_robot(
                        self.controlled_robot_id,
                        move_x,
                        move_y,
                        elapsed_seconds,
                        self.arena,
                    )
                self._update_sentry_motion(elapsed_seconds, move_x, move_y)
                self.bridge.publish_state(self._bridge_state())
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
        bottom = height - 18
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
        x = float(keys[self.pg.K_d]) - float(keys[self.pg.K_a])
        y = float(keys[self.pg.K_w]) - float(keys[self.pg.K_s])
        return x, y

    def _update_sentry_motion(
        self,
        elapsed_seconds: float,
        manual_x: float,
        manual_y: float,
    ) -> None:
        if self.sentry.manual_control:
            self.sentry.update(
                elapsed_seconds,
                manual_x,
                manual_y,
                self.arena,
                spin_enabled=self.decision.spin_mode > 0,
                turret_enabled=self.decision.tripod_mode > 0,
            )
            return

        if self.bridge.connected and self.decision.goal is not None:
            goal_x, goal_y = self.decision.goal
            delta_x = goal_x - self.sentry.x
            delta_y = goal_y - self.sentry.y
            distance = math.hypot(delta_x, delta_y)
            if distance > 0.08:
                travel = min(distance, self.sentry.movement_speed * elapsed_seconds)
                self.sentry.x, self.sentry.y = self.arena.clamp(
                    self.sentry.x + delta_x / distance * travel,
                    self.sentry.y + delta_y / distance * travel,
                )

        self.sentry.update(
            elapsed_seconds,
            0.0,
            0.0,
            self.arena,
            spin_enabled=self.decision.spin_mode > 0,
            turret_enabled=self.decision.tripod_mode > 0,
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
            "time": max(0, round(self.task.remaining_time)),
            "hp_sentry": max(0, round(self.task.sentry_hp)),
            "defence_buff": self.task.defence_buff,
            "color": 0,
            "ammo": max(0, round(self.task.ammo)),
            "hp_outpost": max(0, round(self.task.own_outpost_hp)),
            "hp_base": 5000,
            "hp_enemy": enemy_hp,
            "radar_data": radar_data,
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
        half_view = math.radians(24.0)
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
            if distance <= 6.2 and abs(relative_angle) <= half_view:
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

    def _handle_mouse_click(self, position: tuple[int, int]) -> None:
        for rect, action, target_id, direction in reversed(self.click_regions):
            if not rect.collidepoint(position):
                continue
            if action == "reset_time":
                self.task.reset_match_time()
            elif action == "enemy_health":
                self.task.adjust_enemy_health(target_id, direction)
            elif action == "sentry_health":
                self.task.adjust_sentry_health(direction)
            return

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
        self.sentry.cancel_manual_control()

    def _release_manual_control(self) -> None:
        self.controlled_robot_id = None
        self.sentry.cancel_manual_control()

    def _render(self, viewport: Viewport) -> None:
        self.click_regions.clear()
        self.screen.fill((22, 25, 28))
        self._draw_header()
        self._draw_side_panels()
        self._draw_arena(viewport)

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
        self.screen.blit(title, (28, 12))

        if self.sentry.manual_control:
            mode = "人工控制｜己方哨兵 9"
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
        self.pg.draw.circle(self.screen, mode_color, (36, 55), 5)
        mode_text = self.data_font.render(f"控制状态：{mode}", True, (202, 209, 212))
        self.screen.blit(mode_text, (49, 45))

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
        position_rect = position.get_rect(midright=(width - 28, 23))
        self.screen.blit(position, position_rect)

        angles = self.small_font.render(
            f"哨兵底盘 {math.degrees(self.sentry.spin_angle) % 360:06.1f}°    "
            f"云台 {math.degrees(self.sentry.turret_angle) % 360:06.1f}°",
            True,
            (155, 166, 171),
        )
        angles_rect = angles.get_rect(midright=(width - 28, 53))
        self.screen.blit(angles, angles_rect)

    def _draw_side_panels(self) -> None:
        width, height = self.screen.get_size()
        left_rect = self.pg.Rect(0, HEADER_HEIGHT, SIDE_PANEL_WIDTH, height - HEADER_HEIGHT)
        right_rect = self.pg.Rect(
            width - SIDE_PANEL_WIDTH,
            HEADER_HEIGHT,
            SIDE_PANEL_WIDTH,
            height - HEADER_HEIGHT,
        )
        for rect in (left_rect, right_rect):
            self.pg.draw.rect(self.screen, (27, 31, 34), rect)
        self.pg.draw.line(
            self.screen,
            (62, 70, 74),
            (SIDE_PANEL_WIDTH, HEADER_HEIGHT),
            (SIDE_PANEL_WIDTH, height),
            1,
        )
        self.pg.draw.line(
            self.screen,
            (62, 70, 74),
            (width - SIDE_PANEL_WIDTH - 1, HEADER_HEIGHT),
            (width - SIDE_PANEL_WIDTH - 1, height),
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
            "WSL 行为树在线" if self.bridge.connected else "Python 本地回退",
            bar_width,
        )
        y = self._draw_key_value(x, y, "当前行为", self.decision.behavior, bar_width)
        y = self._draw_key_value(
            x,
            y,
            "哨兵坐标",
            f"{self.sentry.x:.2f}，{self.sentry.y:.2f}",
            bar_width,
        )
        y = self._draw_key_value(x, y, "导航目标", self._goal_name(), bar_width)
        y = self._draw_key_value(x, y, "巡逻模式", self.task.patrol_name, bar_width)

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
        y = self._draw_progress_bar(
            x, y, bar_width, "当前弹量", self.task.ammo, ammo_maximum, (225, 166, 58)
        )
        y = self._draw_progress_bar(
            x, y, bar_width, "防御增益", self.task.defence_buff, 100, (56, 169, 195), "%"
        )
        y = self._draw_progress_bar(
            x, y, bar_width, "己方前哨", self.task.own_outpost_hp, 1000, (205, 75, 82)
        )
        y = self._draw_progress_bar(
            x, y, bar_width, "己方基地", 5000, 5000, (177, 105, 190)
        )

        y = self._draw_section_title(x, y + 3, "裁判与决策参数")
        y = self._draw_match_time_control(x, y, bar_width)
        y = self._draw_key_value(
            x, y, "待领弹药", str(self.task.pending_ammo), bar_width
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
            "低速旋转" if self.decision.spin_mode else "关闭",
            bar_width,
        )
        y = self._draw_key_value(
            x, y, "射击状态", "射击" if self.decision.shoot_mode else "停止", bar_width
        )
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
        line_y = y + 27
        self.pg.draw.line(self.screen, (76, 85, 90), (x, line_y), (x + width, line_y), 1)
        return y + 36

    def _draw_section_title(self, x: int, y: int, text: str) -> int:
        rendered = self.panel_label_font.render(text, True, (118, 177, 191))
        self.screen.blit(rendered, (x, y))
        return y + 23

    def _draw_key_value(self, x: int, y: int, key: str, value: str, width: int) -> int:
        key_text = self.panel_label_font.render(key, True, (151, 161, 166))
        value_text = self.panel_label_font.render(value, True, (226, 230, 231))
        self.screen.blit(key_text, (x, y))
        self.screen.blit(value_text, value_text.get_rect(topright=(x + width, y)))
        return y + 22

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
        bar_y = y + 18
        bar_height = 6 if compact else 9
        self.pg.draw.rect(self.screen, (48, 54, 58), (x, bar_y, width, bar_height))
        if ratio > 0.0:
            self.pg.draw.rect(
                self.screen,
                color,
                (x, bar_y, max(1, round(width * ratio)), bar_height),
            )
        return y + (29 if compact else 34)

    def _draw_match_time_control(self, x: int, y: int, width: int) -> int:
        key_text = self.panel_label_font.render("比赛剩余", True, (151, 161, 166))
        self.screen.blit(key_text, (x, y))

        button = self.pg.Rect(x + width - 42, y - 2, 42, 20)
        value_text = self.panel_label_font.render(
            f"{round(self.task.remaining_time)} 秒", True, (226, 230, 231)
        )
        self.screen.blit(value_text, value_text.get_rect(topright=(button.left - 7, y)))
        self._draw_click_button(button, "重置")
        self.click_regions.append((button, "reset_time", 0, 0))
        return y + 24

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
        compact: bool = False,
        action: str = "enemy_health",
    ) -> int:
        numeric_value = max(0.0, min(float(value), float(maximum)))
        ratio = numeric_value / maximum if maximum > 0 else 0.0
        label_text = self.panel_label_font.render(label, True, (190, 198, 201))
        self.screen.blit(label_text, (x, y))

        button_size = 18
        plus_button = self.pg.Rect(x + width - button_size, y - 2, button_size, button_size)
        minus_button = self.pg.Rect(plus_button.left - button_size - 4, y - 2, button_size, button_size)
        value_text = self.panel_label_font.render(
            f"{round(value)}/{round(maximum)}", True, (224, 228, 230)
        )
        self.screen.blit(value_text, value_text.get_rect(topright=(minus_button.left - 6, y)))
        self._draw_click_button(minus_button, "-")
        self._draw_click_button(plus_button, "+")
        self.click_regions.append((minus_button, action, target_id, -1))
        self.click_regions.append((plus_button, action, target_id, 1))

        bar_y = y + 20
        bar_height = 6 if compact else 9
        self.pg.draw.rect(self.screen, (48, 54, 58), (x, bar_y, width, bar_height))
        if ratio > 0.0:
            self.pg.draw.rect(
                self.screen,
                color,
                (x, bar_y, max(1, round(width * ratio)), bar_height),
            )
        return y + (31 if compact else 36)

    def _draw_click_button(self, rect, text: str) -> None:
        hovered = rect.collidepoint(self.pg.mouse.get_pos())
        background = (75, 86, 92) if hovered else (50, 58, 63)
        self.pg.draw.rect(self.screen, background, rect)
        self.pg.draw.rect(self.screen, (104, 117, 123), rect, 1)
        rendered = self.panel_label_font.render(text, True, (236, 239, 240))
        self.screen.blit(rendered, rendered.get_rect(center=rect.center))

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
            self.screen.blit(rendered, (x, y + 21 + index * 18))

    def _control_name(self) -> str:
        if self.sentry.manual_control:
            return "己方哨兵"
        if self.controlled_robot_id is not None:
            return f"蓝方 {self.controlled_robot_id} 号"
        return "决策自动"

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
        points = [viewport.world_to_screen(x, y) for x, y in self.task.patrol_points]
        route_color = (218, 92, 55) if self.task.aggressive_patrol else (93, 121, 130)
        label_prefix = "激进" if self.task.aggressive_patrol else "保守"
        self.pg.draw.lines(self.screen, route_color, True, points, 2)
        for index, point in enumerate(points, start=1):
            self.pg.draw.circle(self.screen, (248, 249, 249), point, 6)
            self.pg.draw.circle(self.screen, route_color, point, 6, 2)
            label = self.small_font.render(f"{label_prefix} {index}", True, route_color)
            self.screen.blit(label, (round(point[0] + 7), round(point[1] + 3)))

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
    SimulatorApp(pygame).run()
