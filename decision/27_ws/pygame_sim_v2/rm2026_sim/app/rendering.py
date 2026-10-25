"""Pygame 绘制层。

绘制方法只读取应用状态并登记点击区域，不推进比赛规则，方便独立调整视觉布局。
"""

from __future__ import annotations

from .main import *


class RenderingMixin:
    def _render(self, viewport: Viewport) -> None:
        self.click_regions.clear()
        self.robot_property_regions.clear()
        self.screen.fill((22, 25, 28))
        self._draw_header()
        self._draw_side_panels()
        self._draw_arena(viewport)
        self._draw_snapshot_bar()
        self._draw_map_layer_panel()
        self._draw_robot_property_popup()
        self._draw_subsystem_panel()

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

        title = self.title_font.render("RMUC 2026｜二维哨兵验证 v2", True, (240, 243, 244))
        self.screen.blit(title, (34, 12))
        subsystem_button = self.pg.Rect(560, 14, 128, 34)
        self._draw_click_button(
            subsystem_button,
            "子系统面板",
        )
        self.click_regions.append((subsystem_button, "toggle_subsystem_panel", 0, 0))

        if self.replay_mode:
            mode = "SQLite 数据集回放｜原 SimulatorApp"
            mode_color = (66, 170, 206)
        elif self.task.game_finished:
            mode = f"比赛结束｜{self.task.result_label}"
            mode_color = (245, 180, 65)
        elif self.sentry.manual_control:
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
        y = self._draw_key_value(
            x,
            y,
            "决策来源",
            "SQLite 时间序列（只读回放）"
            if self.replay_mode
            else ("ROS 行为树在线" if self.bridge.connected else "Python 本地回退"),
            bar_width,
        )
        if not self.replay_mode:
            y = self._draw_key_value(x, y, "当前行为", self.decision.behavior, bar_width)
        if self.task.game_finished:
            match_state = f"已结束｜{self.task.result_label}"
        elif self.task.game_paused:
            match_state = "已暂停（空格继续）"
        else:
            match_state = "进行中（空格暂停）"
        y = self._draw_key_value(x, y, "比赛状态", match_state, bar_width)
        y = self._draw_key_value(
            x,
            y,
            "哨兵坐标",
            f"{self.sentry.x:.2f}，{self.sentry.y:.2f}",
            bar_width,
        )
        if not self.replay_mode:
            y = self._draw_key_value(x, y, "导航目标", self._goal_name(), bar_width)
        y = self._draw_control_buttons(x, y + 3, bar_width)

        if self.replay_mode:
            y = self._draw_section_title(x, y + 3, "SQLite 回放与推断")
            replay_time = self.replay_player.time_seconds
            duration = self.replay_player.replay.duration_seconds
            y = self._draw_key_value(
                x, y, "回放进度",
                f"{replay_time:.1f}/{duration:.0f}s｜"
                f"{'播放' if self.replay_player.playing else '暂停'}｜{self.replay_player.speed:g}x",
                bar_width,
            )
            y = self._draw_key_value(
                x, y, "红方金币",
                f"总 {self.replay_total_coins['red'] if self.replay_total_coins['red'] is not None else '—'}"
                f"｜余 {self.replay_remaining_coins['red'] if self.replay_remaining_coins['red'] is not None else '—'}",
                bar_width,
            )
            y = self._draw_key_value(
                x, y, "蓝方金币",
                f"总 {self.replay_total_coins['blue'] if self.replay_total_coins['blue'] is not None else '—'}"
                f"｜余 {self.replay_remaining_coins['blue'] if self.replay_remaining_coins['blue'] is not None else '—'}",
                bar_width,
            )
            latest = self.replay_economy_log[-1] if self.replay_economy_log else None
            y = self._draw_key_value(
                x, y, "经济推断",
                (self._inferred_economy_text(latest) if latest else "暂无可确认行为"),
                bar_width,
            )
            event = self.replay_event_log[-1] if self.replay_event_log else None
            y = self._draw_key_value(
                x, y, "最近数据事件",
                (f"{event.time_seconds:.1f}s {event.event_type}" if event else "暂无"),
                bar_width,
            )

        y = self._draw_section_title(x, y + 3, "基本属性")
        y = self._draw_adjustable_progress_bar(
            x,
            y,
            bar_width,
            "哨兵血量",
            self.task.sentry_hp,
            self._replay_max_health("red", 8, 400),
            (62, 184, 112),
            9,
            action="sentry_health",
        )
        if self.replay_mode:
            y = self._draw_key_value(
                x, y, "SQLite剩余弹量", "数据集未提供（不以累计发弹代替）", bar_width
            )
        else:
            ammo_maximum = AMMO_CAP
            y = self._draw_adjustable_progress_bar(
                x,
                y,
                bar_width,
                "规则剩余弹量",
                self.task.ammo,
                ammo_maximum,
                (225, 166, 58),
                0,
                action="ammo",
                marker=float(ROBOT_PROFILES[8].initial_ammo),
            )
        y = self._draw_progress_bar(
            x,
            y,
            bar_width,
            "当前热量",
            self.sentry.heat,
            (
                self.replay_sentry_heat_limit
                or ROBOT_PROFILES[8].heat_capacity
                or 0
            )
            if self.replay_mode
            else (ROBOT_PROFILES[8].heat_capacity or 0) + HEAT_PERMANENT_EXTRA,
            (218, 92, 53),
        )
        if self.replay_mode:
            shots_17, shots_42 = self._replay_shots("red", 8)
            y = self._draw_key_value(
                x, y, "累计发弹",
                f"17 {self._shot_text(shots_17)}｜42 {self._shot_text(shots_42)}",
                bar_width,
            )
        if self.replay_mode:
            y = self._draw_key_value(x, y, "发射锁定", "数据集未提供", bar_width)
        else:
            if self.task.sentry_heat_permanent_lock:
                heat_lock = "Q2 永久锁定"
            elif self.task.sentry_heat_locked:
                heat_lock = "Q1 锁定"
            else:
                heat_lock = "未锁定"
            y = self._draw_key_value(
                x,
                y,
                "发射锁定",
                f"{heat_lock}{self._aim_status()}",
                bar_width,
            )
        if self.replay_mode:
            y = self._draw_key_value(
                x, y, "SQLite底盘功率", f"{self.sentry.chassis_power:.1f} W", bar_width
            )
            y = self._draw_key_value(
                x, y, "易伤状态", "是" if self.replay_sentry_vulnerable else "否",
                bar_width,
            )
            y = self._draw_section_title(x, y + 3, "比赛时间")
            self._draw_match_time_control(x, y, bar_width)
            return
        y = self._draw_progress_bar(
            x,
            y,
            bar_width,
            "底盘机械功率",
            self.sentry.chassis_power,
            self.task.effective_sentry_power_limit,
            (96, 151, 210),
        )
        chassis_note = (
            f"{self.sentry.chassis_power:.0f}/{self.task.effective_sentry_power_limit:.0f} W"
            f"｜缓冲 {self.task.sentry_buffer_energy:.0f}J"
        )
        if self.task.sentry_chassis_power_cut:
            chassis_note += f"｜断电 {self.task.sentry_chassis_power_cut_remaining:.1f}s"
        y = self._draw_key_value(x, y, "底盘状态", chassis_note, bar_width)
        y = self._draw_adjustable_progress_bar(
            x,
            y,
            bar_width,
            "防御增益",
            self.task.effective_sentry_defence * 100.0,
            100,
            (56, 169, 195),
            0,
            suffix="%",
            action="defence_buff",
            marker=self.task.defence_buff,
        )
        y = self._draw_section_title(x, y + 3, "裁判与决策参数")
        y = self._draw_match_time_control(x, y, bar_width)
        y = self._draw_adjustable_progress_bar(
            x,
            y,
            bar_width,
            "待领弹药",
            self.task.pending_ammo,
            PENDING_AMMO_CAP,
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
            self.task.active_posture, "未知"
        )
        posture_mode_short = {
            "default": "默认",
            "reinforced": "强化",
            "decayed": "衰减",
        }.get(self.task.posture_mode, "默认")
        y = self._draw_key_value(
            x,
            y,
            "当前姿态",
            f"{posture_name}·{posture_mode_short}"
            f"（冷却 {self.task.posture_cooldown_remaining:.1f}s）",
            bar_width,
        )
        y = self._draw_key_value(
            x,
            y,
            "姿态效果",
            f"冷却 {self.task.effective_sentry_heat_cooling:.0f}/秒"
            f"｜功率 {self.task.effective_sentry_power_limit:.0f}W",
            bar_width,
        )
        y = self._draw_key_value(
            x, y, "回血阈值", str(self.decision.health_threshold), bar_width
        )
        self._draw_wrapped_status(x, y + 5, bar_width, "最近事件", self.task.event_message)

    def _draw_rule_operations(self, x: int, y: int, width: int) -> int:
        y = self._draw_section_title(x, y + 4, "规则操作")

        if self.task.death_elapsed is not None:
            required = self.task.revive_required or self.task.revive_seconds_required
            y = self._draw_progress_bar(
                x,
                y,
                width,
                "复活读条",
                self.task.revive_progress,
                max(0.1, required),
                (198, 154, 62),
                suffix=" 秒",
            )
        else:
            status: list[str] = []
            if self.task.invincible_remaining > 0.0:
                status.append(f"无敌 {self.task.invincible_remaining:.1f}s")
            if self.task.weak_state:
                status.append("虚弱")
            if self.task.remote_heal_remaining is not None:
                status.append(f"远程回血 {self.task.remote_heal_remaining:.1f}s")
            if self.task.remote_ammo_remaining is not None:
                status.append(f"远程弹 {self.task.remote_ammo_remaining:.1f}s")
            if status:
                y = self._draw_key_value(x, y, "当前状态", "｜".join(status), width)

        if self.task.sentry_hp > 0.0:
            combat_status = (
                "已脱战"
                if self.task.sentry_is_out_of_combat
                else f"{self.task.sentry_out_of_combat_seconds:.1f}/6.0 秒"
            )
        else:
            combat_status = "已阵亡"
        y = self._draw_key_value(x, y, "远程兑换条件", combat_status, width)
        y = self._draw_key_value(x, y, "远程生效延迟", "6 秒", width)
        y = self._draw_key_value(x, y, "本地弹药条件", "补给/基地/可用前哨点内", width)
        y = self._draw_key_value(x, y, "立即复活条件", "仅阵亡读条中", width)

        gap = 8
        button_width = (width - gap) // 2
        button_height = 32
        remote_ammo_enabled, _ = self.task.can_exchange_17mm(
            remote=True, sentry=self.sentry
        )
        local_ammo_enabled, _ = self.task.can_exchange_17mm(
            remote=False, sentry=self.sentry
        )
        remote_heal_enabled, _ = self.task.can_exchange_remote_heal()
        instant_revive_enabled, _ = self.task.can_exchange_instant_revive()
        actions = (
            (
                "远程弹 +100 / -150",
                "exchange_remote_ammo",
                remote_ammo_enabled,
            ),
            (
                "补给/基地/前哨 +10 / -10",
                "exchange_local_ammo",
                local_ammo_enabled,
            ),
            (
                f"远程回血 -{self.task.remote_heal_cost}",
                "exchange_remote_heal",
                remote_heal_enabled,
            ),
            (
                f"立即复活 -{self.task.instant_revive_cost}",
                "exchange_instant_revive",
                instant_revive_enabled,
            ),
        )
        for index, (label, action, enabled) in enumerate(actions):
            column = index % 2
            row = index // 2
            rect = self.pg.Rect(
                x + column * (button_width + gap),
                y + row * (button_height + 6),
                button_width,
                button_height,
            )
            self._draw_click_button(rect, label, enabled=enabled)
            if enabled:
                self.click_regions.append((rect, action, 0, 0))
        y += 2 * (button_height + 6)

        posture_rect = self.pg.Rect(x, y, width, button_height)
        posture_text = (
            "退出强化姿态"
            if self.task.posture_reinforced
            else "进入强化姿态"
        )
        self._draw_click_button(posture_rect, posture_text)
        self.click_regions.append((posture_rect, "toggle_posture_reinforced", 0, 0))
        y += button_height + 6

        hero_label = "近战优先" if self.task.hero_mode == "melee" else "远程优先"
        chassis_label = (
            "功率优先" if self.task.infantry_chassis_mode == "power" else "血量优先"
        )
        launcher_label = (
            "爆发优先" if self.task.infantry_launcher_mode == "burst" else "冷却优先"
        )
        config_gap = 5
        config_width = (width - config_gap * 2) // 3
        config_buttons = (
            (f"英雄 {'近战' if self.task.hero_mode == 'melee' else '远程'}", "cycle_hero_mode"),
            (f"底盘 {'功率' if self.task.infantry_chassis_mode == 'power' else '血量'}", "cycle_infantry_chassis"),
            (f"发射 {'爆发' if self.task.infantry_launcher_mode == 'burst' else '冷却'}", "cycle_infantry_launcher"),
        )
        for index, (label, action) in enumerate(config_buttons):
            rect = self.pg.Rect(
                x + index * (config_width + config_gap),
                y,
                config_width,
                button_height,
            )
            self._draw_click_button(rect, label)
            self.click_regions.append((rect, action, 0, 0))
        y += button_height + 6
        y = self._draw_key_value(
            x,
            y,
            "当前性能配置",
            f"英雄{hero_label}｜步兵{chassis_label}｜发射{launcher_label}",
            width,
        )
        return y + 14

    def _buff_summary(self) -> str:
        values: dict[str, float] = {}
        for buff in self.task.active_buffs:
            values[buff.kind] = max(values.get(buff.kind, 0.0), buff.value)
        parts: list[str] = []
        if "attack" in values:
            parts.append(f"攻击×{values['attack']:.1f}")
        if "defence" in values:
            parts.append(f"防御{values['defence'] * 100:.0f}%")
        if "heat_cooling" in values:
            parts.append(f"冷却×{values['heat_cooling']:.1f}")
        if "buffer_energy" in values:
            parts.append(f"缓冲+{values['buffer_energy']:.0f}J")
        if "vulnerability" in values:
            parts.append(f"易伤{values['vulnerability'] * 100:.0f}%")
        return "｜".join(parts) if parts else "无"

    def _draw_rune_panel(self, x: int, y: int, width: int) -> int:
        y = self._draw_section_title(x, y + 4, "能量机关与场地增益")
        status = {
            "inactive": "未激活",
            "activating": f"激活中 {self.task.rune_timer:.1f}s｜{self.task.rune_hits}/5",
            "active": f"已激活 {self.task.rune_timer:.1f}s",
        }.get(self.task.rune_state, self.task.rune_state)
        y = self._draw_key_value(
            x,
            y,
            "机关状态",
            f"{'大' if self.task.rune_kind == 'large' else '小'}｜{status}",
            width,
        )
        y = self._draw_key_value(x, y, "场地增益", self._buff_summary(), width)

        gap = 6
        button_width = (width - 2 * gap) // 3
        button_height = 30
        buttons = (
            ("激活小", "activate_small_rune"),
            ("激活大", "activate_large_rune"),
            ("击打装甲", "hit_rune"),
        )
        for index, (label, action) in enumerate(buttons):
            rect = self.pg.Rect(
                x + index * (button_width + gap),
                y,
                button_width,
                button_height,
            )
            self._draw_click_button(rect, label)
            self.click_regions.append((rect, action, 0, 0))
        return y + button_height + 6

    def _draw_right_panel(self, rect) -> None:
        self.robot_property_panel_rect = rect
        x = rect.left + 14
        width = rect.width - 28
        y = rect.top + 14
        y = self._draw_panel_title(x, y, "己方控制与机器人属性", width)

        y = self._draw_section_title(x, y, "己方建筑血量")
        y = self._draw_adjustable_progress_bar(
            x,
            y,
            width,
            "己方前哨",
            self.task.own_outpost_hp,
            self._replay_max_health("red", 6, RULE_OUTPOST_HP),
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
            self._replay_max_health("red", 7, self.task.own_base_max_hp),
            (177, 105, 190),
            7,
            action="own_base_health",
        )
        y = self._draw_key_value(
            x,
            y,
            "基地虚拟护盾",
            f"{round(self.task.own_base_shield)}（开局 {RULE_BASE_SHIELD}）",
            width,
        )
        rebuild_progress = self.task.outpost_rebuild_progress.get("red", {})
        rebuild_id, rebuild_value = max(
            rebuild_progress.items(), key=lambda item: item[1], default=(2, 0.0)
        )
        rebuild_required = OUTPOST_REBUILD_SECONDS.get(rebuild_id, 10.0)
        y = self._draw_key_value(
            x,
            y,
            "前哨重建",
            f"机会 {self.task.outpost_rebuild_chances.get('red', 0)}｜"
            f"{rebuild_id}号 {rebuild_value:.1f}/{rebuild_required:.0f}s",
            width,
        )

        y = self._draw_section_title(x, y + 3, "机器人属性列表")
        y = self._draw_robot_team_tabs(x, y, width)
        y = self._draw_robot_property_list(x, y, width)
        if self.replay_mode:
            y = self._draw_section_title(x, y + 3, "SQLite 事件与经济推断")
            rows = [
                (f"{event.time_seconds:5.1f}s  {event.event_type} {event.category}".strip(), (220, 226, 228))
                for event in self.replay_event_log[-3:]
            ]
            rows.extend(
                (f"{item.time_seconds:5.1f}s  {item.team} {self._inferred_economy_text(item)}",
                 (219, 188, 115))
                for item in self.replay_economy_log[-3:]
            )
            for label, color in rows[-6:]:
                rendered = self.small_font.render(label[:54], True, color)
                self.screen.blit(rendered, (x, y))
                y += 24
        else:
            y = self._draw_rule_operations(x, y, width)
            self._draw_rune_panel(x, y, width)

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
            level = self.task.robot_level_value(target_id, team=team)
            level_suffix = (
                f" Lv.{level}" if target_id in (1, 3, 4, 5) else ""
            )
            maximum = (
                self.task.robot_max_hp(target_id, team=team)
                if target_id in (1, 3, 4, 5)
                else profile.max_hp
            )
            maximum = self._replay_max_health(team, target_id, maximum)
            rows.append(
                (
                    team,
                    target_id,
                    f"{team_name} {target_id}号 {names[target_id]}{level_suffix}",
                    health,
                    maximum,
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
        rows = [
            (
                row_team,
                target_id,
                label,
                value,
                self._replay_max_health(row_team, target_id, maximum),
                color,
            )
            for row_team, target_id, label, value, maximum, color in rows
        ]
        row_height = 40
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
            if target_id == 5 or self.replay_mode:
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

    def _draw_map_layer_panel(self) -> None:
        """Draw the foldable, bottom-aligned controls for map overlays."""
        self.map_region_scroll_rect = None
        screen_width, screen_height = self.screen.get_size()
        panel_width = max(
            280,
            screen_width - SIDE_PANEL_WIDTH - RIGHT_PANEL_WIDTH - 16,
        )
        panel_left = SIDE_PANEL_WIDTH + 8
        panel_bottom = screen_height - SNAPSHOT_BAR_HEIGHT
        panel_height = self._map_layer_panel_height()
        panel = self.pg.Rect(
            panel_left,
            panel_bottom - panel_height,
            panel_width,
            panel_height,
        )
        self.pg.draw.rect(self.screen, (25, 31, 35), panel)
        self.pg.draw.rect(self.screen, (109, 123, 129), panel, 1)

        header = self.pg.Rect(panel.left + 10, panel.top + 7, panel.width - 20, 30)
        title = self.panel_title_font.render("地图区域显示", True, (236, 241, 242))
        self.screen.blit(title, (header.left, header.top - 1))
        toggle_width = 74
        toggle = self.pg.Rect(header.right - toggle_width, header.top, toggle_width, header.height)
        self._draw_click_button(toggle, "收起" if self.map_layers_panel_open else "展开")
        self.click_regions.append((toggle, "toggle_map_layers_panel", 0, 0))

        if not self.map_layers_panel_open:
            visible_count = sum(self.map_layer_visibility.values())
            hint = self.small_font.render(
                f"已显示 {visible_count} 项｜点击“展开”选择地图区域和路线",
                True,
                (170, 181, 185),
            )
            self.screen.blit(hint, hint.get_rect(midright=(toggle.left - 12, toggle.centery)))
            return

        tab_top = panel.top + 43
        tab_width = 110
        for index, (tab_id, tab_label) in enumerate(
            (
                ("layers", "地图图层"),
                ("walls", "墙体编辑"),
                ("special", "特殊墙体"),
                ("slow", "减速区域"),
            )
        ):
            tab = self.pg.Rect(panel.left + 10 + index * (tab_width + 6), tab_top, tab_width, 28)
            active = self.map_editor_tab == tab_id
            self.pg.draw.rect(self.screen, (42, 117, 87) if active else (50, 58, 63), tab)
            self.pg.draw.rect(self.screen, (104, 117, 123), tab, 1)
            text = self.small_font.render(tab_label, True, (238, 241, 242))
            self.screen.blit(text, text.get_rect(center=tab.center))
            self.click_regions.append((tab, "map_editor_tab", tab_id, 0))

        if self.map_editor_tab != "layers":
            self._draw_extra_geometry_editor(panel, tab_top + 38)
            return

        entries = [
            ("show_all_map_layers", "全部显示", True, 0),
            ("hide_all_map_layers", "全部隐藏", False, 0),
        ]
        entries.extend(
            ("toggle_map_layer", label, self.map_layer_visibility[f"zone:{kind}"], f"zone:{kind}")
            for kind, label in FIELD_ZONE_KIND_LABELS
        )
        entries.extend(
            ("toggle_map_layer", label, self.map_layer_visibility[name], name)
            for name, label in MAP_OVERLAY_LABELS
        )

        content_top = panel.top + 78
        gap = 6
        columns = max(2, min(8, panel.width // 150))
        button_width = (panel.width - 20 - gap * (columns - 1)) // columns
        button_height = 30
        for index, (action, label, active, target) in enumerate(entries):
            row, column = divmod(index, columns)
            rect = self.pg.Rect(
                panel.left + 10 + column * (button_width + gap),
                content_top + row * (button_height + 6),
                button_width,
                button_height,
            )
            hovered = rect.collidepoint(self.pg.mouse.get_pos())
            if action == "toggle_map_layer":
                background = (40, 117, 87) if active else (50, 58, 63)
                if hovered:
                    background = (54, 137, 103) if active else (75, 86, 92)
                self.pg.draw.rect(self.screen, background, rect)
                self.pg.draw.rect(self.screen, (104, 117, 123), rect, 1)
                suffix = f"：{'开' if active else '关'}"
                display_label = label
                while (
                    self.panel_label_font.size(display_label + suffix)[0] > rect.width - 8
                    and len(display_label) > 3
                ):
                    display_label = display_label[:-1]
                if display_label != label:
                    display_label = display_label[:-1] + "..."
                button_label = display_label + suffix
                rendered = self.small_font.render(button_label, True, (236, 239, 240))
                self.screen.blit(rendered, rendered.get_rect(center=rect.center))
            else:
                self._draw_click_button(rect, label)
            self.click_regions.append((rect, action, target, 0))

        overlay_rows = math.ceil(len(entries) / columns)
        editor_top = content_top + overlay_rows * (button_height + 6) + 4
        editor_toggle = self.pg.Rect(panel.left + 10, editor_top, panel.width - 20, 30)
        self._draw_click_button(
            editor_toggle,
            "收起编辑区域"
            if getattr(self, "map_region_editor_open", False)
            else "展开编辑区域",
        )
        self.click_regions.append(
            (editor_toggle, "toggle_map_region_editor", 0, 0)
        )
        editor_top += 36
        if not getattr(self, "map_region_editor_open", False):
            return
        editor_active = (
            self.region_edit_new_custom
            or
            self.region_edit_target is not None
            or self.region_edit_custom_id is not None
            or self.region_edit_patrol_kind is not None
            or bool(self.region_edit_points)
        )
        if editor_active:
            definition = next(
                (item for item in REGION_DEFINITIONS
                 if item.name == self.region_edit_kind),
                None,
            )
            status = f"正在新建：{definition.label}" if definition else "正在新建区域"
            if self.region_edit_target is not None:
                zone = self._zone_named(self.region_edit_target)
                status = f"正在编辑：{zone.label if zone else self.region_edit_target}"
            elif self.region_edit_custom_id is not None:
                item = next(
                    (item for item in self.custom_map_polygons
                     if item.get("id") == self.region_edit_custom_id),
                    None,
                )
                status = f"正在编辑：{item.get('name', '自定义区域') if item else '自定义区域'}"
            elif self.region_edit_patrol_kind is not None:
                route_label = "保守" if self.region_edit_patrol_kind == "conservative" else "激进"
                status = f"正在编辑：{route_label}巡逻路线"
            status_text = self.panel_label_font.render(status, True, (244, 211, 115))
            self.screen.blit(status_text, (panel.left + 12, editor_top + 3))
            editor_buttons = (
                (
                    "保存路线" if self.region_edit_patrol_kind else "保存区域",
                    "region_editor_save",
                    82,
                ),
                ("清空重画", "region_editor_clear", 82),
                ("取消", "region_editor_cancel", 68),
            )
            if self.region_edit_kind and self.region_edit_patrol_kind is None:
                editor_buttons = (
                    ("再画一个", "region_editor_new_instance", 96),
                    *editor_buttons,
                )
            button_x = panel.right - 12
            for label, action, width in reversed(editor_buttons):
                button_x -= width
                rect = self.pg.Rect(button_x, editor_top, width - 4, 28)
                self._draw_click_button(rect, label)
                action_target = self.region_edit_kind if action == "region_editor_new_instance" else 0
                self.click_regions.append((rect, action, action_target, 0))
                button_x -= 5
            if self.region_edit_error:
                error = self.panel_label_font.render(self.region_edit_error, True, (236, 103, 103))
                self.screen.blit(error, (panel.left + 12, editor_top + 32))
            editor_top += 56

        route_section = self.panel_label_font.render("可编辑巡逻路线", True, (191, 202, 206))
        self.screen.blit(route_section, (panel.left + 12, editor_top + 2))
        route_button_x = panel.left + 142
        for route_kind, label in (("conservative", "编辑保守路线"), ("aggressive", "编辑激进路线")):
            rect = self.pg.Rect(route_button_x, editor_top, 116, 26)
            self._draw_click_button(rect, label)
            self.click_regions.append((rect, "edit_patrol_route", route_kind, 0))
            route_button_x += 122
        editor_top += 34

        section = self.panel_label_font.render("可编辑区域", True, (191, 202, 206))
        self.screen.blit(section, (panel.left + 12, editor_top + 2))
        editor_top += 27
        region_items: list[tuple[str, str, str, bool, str]] = []
        for zone in REGION_DEFINITIONS:
            missing = zone.name in self.map_zone_overrides and not self._region_type_configured(zone.name)
            region_items.append(("zone", zone.name, zone.label or zone.name, not missing, zone.name))
        for item in self.custom_map_polygons:
            identifier = str(item.get("id"))
            region_items.append((
                "custom", identifier, str(item.get("name", identifier)), True,
                str(item.get("kind") or REGION_TYPES[0][0]),
            ))
        region_columns = max(1, min(3, panel.width // 360))
        region_gap = 8
        cell_width = (panel.width - 20 - region_gap * (region_columns - 1)) // region_columns
        total_region_rows = math.ceil(len(region_items) / region_columns) if region_items else 0
        maximum_region_offset = max(0, total_region_rows - MAP_REGION_VISIBLE_ROWS)
        region_offset = max(
            0,
            min(
                maximum_region_offset,
                int(getattr(self, "map_region_scroll_offset", 0)),
            ),
        )
        self.map_region_scroll_offset = region_offset
        first_item = region_offset * region_columns
        visible_region_items = region_items[
            first_item : first_item + MAP_REGION_VISIBLE_ROWS * region_columns
        ]
        visible_region_rows = min(
            MAP_REGION_VISIBLE_ROWS,
            max(0, total_region_rows - region_offset),
        )
        if visible_region_rows:
            self.map_region_scroll_rect = self.pg.Rect(
                panel.left + 10,
                editor_top,
                panel.width - 20,
                visible_region_rows * 32,
            )
        if total_region_rows > MAP_REGION_VISIBLE_ROWS:
            range_text = self.small_font.render(
                f"{first_item + 1}-{min(len(region_items), first_item + len(visible_region_items))} / {len(region_items)}",
                True,
                (167, 179, 183),
            )
            self.screen.blit(
                range_text,
                range_text.get_rect(bottomright=(panel.right - 12, editor_top - 4)),
            )
        for index, (kind, identifier, label, configured, region_kind) in enumerate(visible_region_items):
            row, column = divmod(index, region_columns)
            cell = self.pg.Rect(
                panel.left + 10 + column * (cell_width + region_gap),
                editor_top + row * 32,
                cell_width,
                28,
            )
            self.pg.draw.rect(self.screen, (42, 49, 53), cell)
            self.pg.draw.rect(self.screen, (83, 95, 100), cell, 1)
            state = "未设置" if not configured else "已设置"
            label_area = self.pg.Rect(cell.left + 6, cell.top, max(1, cell.width - 174), cell.height)
            display_label = f"{label}｜{state}"
            while (
                self.small_font.size(display_label)[0] > label_area.width - 4
                and len(display_label) > 4
            ):
                display_label = display_label[:-1]
            if display_label != f"{label}｜{state}":
                display_label = display_label[:-1] + "..."
            label_text = self.small_font.render(
                display_label,
                True,
                (235, 112, 112) if not configured else (218, 226, 228),
            )
            self.screen.blit(label_text, label_text.get_rect(midleft=label_area.midleft))
            edit_rect = self.pg.Rect(cell.right - 168, cell.top + 3, 52, 22)
            delete_rect = self.pg.Rect(cell.right - 112, cell.top + 3, 52, 22)
            visibility_rect = self.pg.Rect(cell.right - 56, cell.top + 3, 50, 22)
            self._draw_click_button(edit_rect, "编辑")
            self._draw_click_button(delete_rect, "删除")
            self._draw_click_button(
                visibility_rect,
                "隐藏" if self.map_layer_visibility.get(
                    f"custom:{identifier}" if kind == "custom" else f"zone:{next((z.kind for z in REGION_DEFINITIONS if z.name == identifier), '')}",
                    False,
                ) else "显示",
            )
            self.click_regions.append((
                edit_rect,
                "edit_custom_region" if kind == "custom" else "edit_zone_region",
                identifier,
                0,
            ))
            self.click_regions.append((delete_rect, "delete_map_region", (kind, identifier), 0))
            visibility_target = (
                f"custom:{identifier}"
                if kind == "custom"
                else f"zone:{next((z.kind for z in REGION_DEFINITIONS if z.name == identifier), '')}"
            )
            self.click_regions.append((visibility_rect, "toggle_map_layer", visibility_target, 0))
        if (
            self.map_region_scroll_rect is not None
            and total_region_rows > MAP_REGION_VISIBLE_ROWS
        ):
            track = self.pg.Rect(
                panel.right - 7,
                self.map_region_scroll_rect.top,
                4,
                self.map_region_scroll_rect.height,
            )
            self.pg.draw.rect(self.screen, (65, 75, 80), track, border_radius=2)
            thumb_height = max(
                20,
                round(track.height * MAP_REGION_VISIBLE_ROWS / total_region_rows),
            )
            travel = max(0, track.height - thumb_height)
            ratio = (
                region_offset / maximum_region_offset
                if maximum_region_offset > 0
                else 0.0
            )
            thumb = self.pg.Rect(
                track.left,
                track.top + round(travel * ratio),
                track.width,
                thumb_height,
            )
            self.pg.draw.rect(self.screen, (70, 155, 116), thumb, border_radius=2)

    def _draw_extra_geometry_editor(self, panel, top: int) -> None:
        """Draw compact wall and terrain editors in their own tabs."""
        self.map_extra_scroll_rect = None
        editor_kind = self.map_editor_tab
        is_wall = editor_kind == "walls"
        is_special = editor_kind == "special"
        is_slow = editor_kind == "slow"
        if is_wall:
            items = self.wall_polygons
            title = "墙体线段（地面机器人不可通过，空中机器人忽略）"
            color = (225, 100, 100)
            layer_key = "editable_walls"
            add_label, add_action = "添加墙体", "new_wall"
            edit_action, delete_kind = "edit_wall", "wall"
            item_name = "墙体"
        elif is_special:
            items = self.special_regions
            title = "特殊墙体（空中忽略；工程、3/4 号步兵每段需 1 秒）"
            color = (235, 180, 70)
            layer_key = "special_regions"
            add_label, add_action = "添加特殊墙体", "new_special"
            edit_action, delete_kind = "edit_special", "special"
            item_name = "特殊墙体"
        else:
            items = self.slow_regions
            title = "减速区域（区域内速度 50%，底盘功率不变）"
            color = (86, 174, 220)
            layer_key = "slow_regions"
            add_label, add_action = "添加减速区域", "new_slow"
            edit_action, delete_kind = "edit_slow", "slow"
            item_name = "减速区域"
        title_text = self.panel_label_font.render(title, True, color)
        self.screen.blit(title_text, (panel.left + 12, top + 4))
        list_button = self.pg.Rect(panel.right - 410, top, 132, 28)
        list_open = getattr(self, "map_extra_list_open", True)
        self._draw_click_button(
            list_button,
            "收起墙体列表" if list_open and (is_wall or is_special)
            else "展开墙体列表" if (is_wall or is_special)
            else "收起区域列表" if list_open
            else "展开区域列表",
        )
        self.click_regions.append(
            (list_button, "toggle_map_extra_list", 0, 0)
        )
        layer_button = self.pg.Rect(panel.right - 270, top, 122, 28)
        self._draw_click_button(
            layer_button,
            "隐藏图层" if self.map_layer_visibility.get(layer_key, False) else "显示图层",
        )
        self.click_regions.append((layer_button, "toggle_map_layer", layer_key, 0))
        add_rect = self.pg.Rect(panel.right - 140, top, 126, 28)
        self._draw_click_button(add_rect, add_label)
        self.click_regions.append((add_rect, add_action, 0, 0))
        top += 38
        offsets = getattr(
            self,
            "map_extra_scroll_offsets",
            {"walls": 0, "special": 0, "slow": 0},
        )
        maximum_offset = max(0, len(items) - MAP_EXTRA_VISIBLE_ROWS)
        offset = max(0, min(maximum_offset, int(offsets.get(self.map_editor_tab, 0))))
        offsets[self.map_editor_tab] = offset
        self.map_extra_scroll_offsets = offsets
        displayed_items = (
            items[offset : offset + MAP_EXTRA_VISIBLE_ROWS]
            if list_open else []
        )
        if not list_open:
            editing_name = "区域顶点" if is_slow else "墙体端点"
            hint = self.panel_label_font.render(
                f"列表已自动收起，可在上方地图编辑{editing_name}",
                True,
                (190, 201, 205),
            )
            self.screen.blit(hint, (panel.left + 12, top))
        elif not items:
            empty = self.panel_label_font.render(
                f"暂无{item_name}，点击右上角开始绘制",
                True,
                (177, 188, 192),
            )
            self.screen.blit(empty, (panel.left + 12, top))
        elif items:
            visible_height = min(len(items), MAP_EXTRA_VISIBLE_ROWS) * 34
            self.map_extra_scroll_rect = self.pg.Rect(
                panel.left + 10,
                top,
                panel.width - 20,
                visible_height,
            )
            range_text = self.small_font.render(
                f"{offset + 1}-{min(len(items), offset + MAP_EXTRA_VISIBLE_ROWS)} / {len(items)}",
                True,
                (167, 179, 183),
            )
            self.screen.blit(
                range_text,
                range_text.get_rect(bottomright=(panel.right - 430, top - 5)),
            )
        for index, item in enumerate(displayed_items):
            row = self.pg.Rect(panel.left + 10, top + index * 34, panel.width - 20, 28)
            self.pg.draw.rect(self.screen, (42, 49, 53), row)
            self.pg.draw.rect(self.screen, color, row, 1)
            label = str(item.get("name") or item_name)
            if is_slow:
                label += "｜速度 50%｜功率不变"
            else:
                try:
                    label += f"｜厚度 {float(item.get('thickness', DEFAULT_WALL_THICKNESS)):.2f}m"
                except (TypeError, ValueError):
                    label += f"｜厚度 {DEFAULT_WALL_THICKNESS:.2f}m"
            if is_special:
                label += "｜工程/步兵3/4｜需1秒"
            text = self.small_font.render(label[:34], True, (226, 232, 234))
            self.screen.blit(text, (row.left + 8, row.top + 3))
            edit = self.pg.Rect(row.right - 118, row.top + 3, 52, 22)
            delete = self.pg.Rect(row.right - 62, row.top + 3, 52, 22)
            self._draw_click_button(edit, "编辑")
            self._draw_click_button(delete, "删除")
            self.click_regions.append((edit, edit_action, str(item.get("id")), 0))
            self.click_regions.append((delete, "delete_editable_geometry", (delete_kind, str(item.get("id"))), 0))
            top += 0
        if list_open and len(items) > MAP_EXTRA_VISIBLE_ROWS:
            track = self.pg.Rect(
                panel.right - 7,
                self.map_extra_scroll_rect.top,
                4,
                self.map_extra_scroll_rect.height,
            )
            self.pg.draw.rect(self.screen, (65, 75, 80), track, border_radius=2)
            thumb_height = max(
                20,
                round(track.height * MAP_EXTRA_VISIBLE_ROWS / len(items)),
            )
            travel = max(0, track.height - thumb_height)
            ratio = offset / maximum_offset if maximum_offset > 0 else 0.0
            thumb = self.pg.Rect(
                track.left,
                track.top + round(travel * ratio),
                track.width,
                thumb_height,
            )
            self.pg.draw.rect(self.screen, color, thumb, border_radius=2)
        editor_active = (
            self.region_edit_new_wall
            or self.region_edit_wall_id is not None
            or self.region_edit_new_special
            or self.region_edit_special_id is not None
            or self.region_edit_new_slow
            or self.region_edit_slow_id is not None
        )
        if editor_active:
            save = self.pg.Rect(panel.right - 220, panel.bottom - 42, 64, 28)
            clear = self.pg.Rect(panel.right - 150, panel.bottom - 42, 64, 28)
            cancel = self.pg.Rect(panel.right - 80, panel.bottom - 42, 64, 28)
            self._draw_click_button(save, "保存")
            self._draw_click_button(clear, "重画")
            self._draw_click_button(cancel, "取消")
            self.click_regions.extend(
                ((save, "region_editor_save", 0, 0), (clear, "region_editor_clear", 0, 0), (cancel, "region_editor_cancel", 0, 0))
            )

    def _draw_subsystem_panel(self) -> None:
        if not self.subsystem_panel_open:
            return
        screen_width, screen_height = self.screen.get_size()
        panel_width = min(820, screen_width - 120)
        panel_height = min(760, screen_height - 160)
        panel = self.pg.Rect(
            (screen_width - panel_width) // 2,
            HEADER_HEIGHT + 20,
            panel_width,
            panel_height,
        )
        shadow = self.pg.Surface((screen_width, screen_height), self.pg.SRCALPHA)
        shadow.fill((0, 0, 0, 150))
        self.screen.blit(shadow, (0, 0))
        self.click_regions.append(
            (self.pg.Rect(0, 0, screen_width, screen_height), "subsystem_modal", 0, 0)
        )
        self.pg.draw.rect(self.screen, (24, 30, 34), panel, border_radius=8)
        self.pg.draw.rect(self.screen, (150, 168, 174), panel, 2, border_radius=8)
        self.click_regions.append((panel, "subsystem_modal", 0, 0))

        x = panel.left + 24
        y = panel.top + 18
        title = self.title_font.render("工程 / 飞镖 / 雷达子系统", True, (242, 245, 246))
        self.screen.blit(title, (x, y))
        close = self.pg.Rect(panel.right - 96, panel.top + 16, 76, 32)
        self._draw_click_button(close, "关闭")
        self.click_regions.append((close, "close_subsystem", 0, 0))
        y += 54

        y = self._draw_section_title(x, y, "工程装配 / 科技核心")
        y = self._draw_key_value(
            x,
            y,
            "工程位置",
            "装配区" if self._engineer_in_assembly_zone() else "装配区外",
            panel.width - 48,
        )
        status = "未开始"
        if self.task.assembly_active:
            status = f"{self.task.assembly_progress:.1f}/{self.task.assembly_required:.1f}s"
        elif self.task.assembly_completed:
            status = "已完成 " + "、".join(
                str(item) for item in sorted(self.task.assembly_completed)
            )
        elif self.task.assembly_last_result != "未判定":
            status = self.task.assembly_last_result
        display_difficulty = (
            self.task.assembly_difficulty or self.task.assembly_last_difficulty
        )
        success_rate = self.task.assembly_success_rate(display_difficulty)
        y = self._draw_key_value(
            x,
            y,
            "装配状态",
            f"难度 {display_difficulty or '—'}｜{status}"
            f"｜固定成功率 {success_rate * 100:.0f}%"
            f"｜等级上限 {self.task.level_cap}"
            f"｜每10秒 +{self.task.assembly_bonus_per_10s} 金"
            f"｜全队防御 {self.task.assembly_defence * 100:.0f}%",
            panel.width - 48,
        )
        if self.task.assembly_last_roll is not None:
            y = self._draw_key_value(
                x,
                y,
                "装配判定",
                f"随机值 {self.task.assembly_last_roll:.3f}｜"
                f"{self.task.assembly_last_result}",
                panel.width - 48,
            )
        if self.task.assembly_outside_seconds > 0.0:
            y = self._draw_key_value(
                x,
                y,
                "装配区丢失",
                f"{self.task.assembly_outside_seconds:.1f}/15.0 秒",
                panel.width - 48,
            )
        if self.task.assembly_level4_cooldown_remaining > 0.0:
            y = self._draw_key_value(
                x,
                y,
                "四级失败冷却",
                f"{self.task.assembly_level4_cooldown_remaining:.1f} 秒",
                panel.width - 48,
            )
        difficulty_width = (panel.width - 48 - 3 * 6) // 4
        for index in range(4):
            rect = self.pg.Rect(
                x + index * (difficulty_width + 6),
                y,
                difficulty_width,
                30,
            )
            self._draw_click_button(rect, f"{index + 1} 级")
            self.click_regions.append((rect, f"assembly_difficulty_{index + 1}", 0, 0))
        y += 36
        assembly_actions = (
            ("开始装配", "start_assembly"),
            ("取消装配", "cancel_assembly"),
            ("工程到装配区", "move_engineer_to_assembly"),
        )
        action_width = (panel.width - 48 - 2 * 6) // 3
        for index, (label, action) in enumerate(assembly_actions):
            rect = self.pg.Rect(
                x + index * (action_width + 6),
                y,
                action_width,
                32,
            )
            self._draw_click_button(rect, label)
            self.click_regions.append((rect, action, 0, 0))
        y += 44

        y = self._draw_section_title(x, y, "飞镖系统")
        y = self._draw_key_value(
            x,
            y,
            "飞镖状态",
            f"剩余 {self.task.darts_remaining} 枚｜闸门 {self.task.dart_gate_state}"
            f"｜发射窗口 {self.task.dart_fire_window:.0f}s"
            f"｜目标 {self.task.dart_target_type}",
            panel.width - 48,
        )
        dart_actions = (
            ("切换目标", "cycle_dart_target"),
            ("开启闸门", "open_dart_gate"),
            ("发射飞镖", "fire_dart"),
        )
        for index, (label, action) in enumerate(dart_actions):
            rect = self.pg.Rect(
                x + index * (action_width + 6),
                y,
                action_width,
                32,
            )
            self._draw_click_button(rect, label)
            self.click_regions.append((rect, action, 0, 0))
        y += 44

        y = self._draw_section_title(x, y, "雷达标记")
        radar_target = self.decision.target
        if radar_target not in (1, 2, 3, 4, 5, 8):
            radar_target = 1
        progress = self.task.radar_marks.get(radar_target, 0.0)
        quality = {
            "accurate": "准确",
            "half_accurate": "半准确",
            "error": "错误",
            "中断": "中断",
        }.get(
            self.task.radar_last_report_quality.get(radar_target, "未发送"),
            "未发送",
        )
        y = self._draw_key_value(
            x,
            y,
            "标记对象",
            f"{radar_target} 号｜P={progress:.0f}｜易伤 "
            f"{self.task.radar_vulnerability(radar_target) * 100:.0f}%"
            f"｜双倍 {self.task.radar_double_remaining:.0f}s"
            f"｜机会 {self.task.radar_double_charges}｜本次 {quality}",
            panel.width - 48,
        )
        radar_actions = (
            ("雷达扫描", "radar_scan"),
            ("双倍易伤", "radar_double"),
            ("解析信息波", "radar_parse_info"),
        )
        radar_action_width = (panel.width - 48 - 2 * 6) // 3
        for index, (label, action) in enumerate(radar_actions):
            rect = self.pg.Rect(
                x + index * (radar_action_width + 6),
                y,
                radar_action_width,
                32,
            )
            self._draw_click_button(rect, label)
            self.click_regions.append((rect, action, radar_target, 0))
        y += 44
        packet_valid = bool(
            self.task.radar_team_packet.get("valid", False)
            and self.task.radar_info_wave_age <= self.task.radar_info_wave_ttl
        )
        y = self._draw_key_value(
            x,
            y,
            "全队信息包",
            f"{'有效' if packet_valid else '未解析/已过期'}｜"
            f"年龄 {self.task.radar_info_wave_age:.1f}s｜"
            f"干扰等级 己方{self.task.radar_interference_level}/"
            f"敌方{self.task.enemy_radar_interference_level}",
            panel.width - 48,
        )
        packet_target = (self.task.radar_team_packet.get("targets") or {}).get(
            radar_target,
            {},
        )
        if packet_valid and packet_target:
            position = packet_target.get("position", (0.0, 0.0))
            y = self._draw_key_value(
                x,
                y,
                "目标态势",
                f"位置 ({position[0]:.1f},{position[1]:.1f})｜"
                f"血量 {packet_target.get('health', 0):.0f}｜"
                f"弹量 {packet_target.get('ammo', 0)}｜"
                f"防御 {float(packet_target.get('defence', 0.0)) * 100:.0f}%",
                panel.width - 48,
            )
        radar_extra_actions = (
            ("解析干扰密钥", "radar_parse_interference"),
            (
                "暂停空中支援" if self.task.radar_air_support_active else "启动空中支援",
                "radar_air_support",
            ),
            ("尝试反制空中", "radar_air_countermeasure"),
        )
        for index, (label, action) in enumerate(radar_extra_actions):
            rect = self.pg.Rect(
                x + index * (radar_action_width + 6),
                y,
                radar_action_width,
                32,
            )
            self._draw_click_button(rect, label)
            self.click_regions.append((rect, action, radar_target, 0))
        y += 44
        y = self._draw_key_value(
            x,
            y,
            "空中反制",
            f"支援 {'中' if self.task.radar_air_support_active else '未启动'}｜"
            f"锁定 {self.task.radar_air_lock_remaining:.1f}s｜"
            f"成功次数 {self.task.radar_air_lock_count}/5｜"
            f"{self.task.radar_air_last_result}",
            panel.width - 48,
        )
        self._draw_wrapped_status(
            x,
            y,
            panel.width - 48,
            "说明",
            "二维简化：装配用计时模拟科技核心步骤；飞镖用按钮模拟发射；"
            "雷达报告质量、信息波和空中反制使用可复现概率；P/易伤/锁定时长"
            "仍按裁判规则结算，不改变行为树接口。",
        )

    def _engineer_in_assembly_zone(self) -> bool:
        return self.task.assembly_engineer_in_zone("red")

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
        popup_height = 900 if target_id in ROBOT_PROFILES else 350
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
            y = self._draw_key_value(
                x,
                y,
                "有效防御增益",
                f"{self.task.building_effective_defence(target_id, team=team) * 100:.0f}%",
                popup.width - 28,
            )
            if target_id == 7:
                shield = self.task.enemy_base_shield if team == "blue" else self.task.own_base_shield
                y = self._draw_key_value(
                    x, y, "虚拟护盾",
                    f"{round(shield)}（开局 {RULE_BASE_SHIELD}）", popup.width - 28,
                )
                outpost = self.task.enemy_outpost_hp if team == "blue" else self.task.own_outpost_hp
                y = self._draw_key_value(x, y, "无敌状态", "前哨存活，无敌" if outpost > 0 else "可受到伤害", popup.width - 28)
            damage_label = "5（上方前装甲）/20" if target_id == 7 else "20"
            y = self._draw_key_value(x, y, "17mm 原始伤害", damage_label, popup.width - 28)
            y = self._draw_key_value(x, y, "42mm 原始伤害", str(RULE_DAMAGE_42MM), popup.width - 28)
            y = self._draw_key_value(x, y, "中心区域攻击增益", "150%", popup.width - 28)
            if target_id == 6:
                y = self._draw_key_value(
                    x,
                    y,
                    "二维模拟命中率",
                    f"{OUTPOST_HIT_PROBABILITY * 100:.0f}%",
                    popup.width - 28,
                )
        else:
            level = self.task.robot_level_value(target_id, team=team)
            configuration = {
                1: (
                    f"{level}级·{'近战' if self.task.hero_mode == 'melee' else '远程'}优先"
                    + ("·已部署" if self.task.hero_deployment_active(team) else "")
                ),
                2: "固定性能",
                3: f"{level}级·{'功率' if self.task.infantry_chassis_mode == 'power' else '血量'}/"
                   f"{'爆发' if self.task.infantry_launcher_mode == 'burst' else '冷却'}优先",
                4: f"{level}级·{'功率' if self.task.infantry_chassis_mode == 'power' else '血量'}/"
                   f"{'爆发' if self.task.infantry_launcher_mode == 'burst' else '冷却'}优先",
                5: f"{level}级",
                8: "自动哨兵",
            }[target_id]
            y = self._draw_key_value(x, y, "规则配置", configuration, popup.width - 28)
            y = self._draw_key_value(
                x, y, "易伤状态",
                "是" if self.replay_vulnerability.get((team, target_id), False) else "否",
                popup.width - 28,
            )
            if target_id in (1, 3, 4, 5):
                next_threshold = LEVEL_EXP_THRESHOLDS[min(level, 9)]
                y = self._draw_key_value(
                    x,
                    y,
                    "等级/经验",
                    f"Lv.{level}｜{self.task.robot_experience_value(target_id, team=team):.0f}"
                    f"/{next_threshold}",
                    popup.width - 28,
                )
            y = self._draw_key_value(
                x, y, "云台", "有" if profile.has_gimbal else "无", popup.width - 28
            )
            y = self._draw_key_value(
                x, y, "小转盘", "有" if profile.has_turntable else "无", popup.width - 28
            )
            turntable_mode = self.task.robot_turntable_mode(target_id, team=team)
            turntable_labels = {0: "停止", 1: "低速", 2: "中速", 3: "高速"}
            turntable_angle = self.task.robot_turntable_angle(
                target_id,
                team=team,
                sentry=self.sentry,
            )
            y = self._draw_key_value(
                x,
                y,
                "小转盘档位",
                f"{turntable_labels[turntable_mode]}｜"
                f"{math.degrees(turntable_angle) % 360:.1f}°",
                popup.width - 28,
            )
            y = self._draw_key_value(
                x,
                y,
                "小转盘角速度",
                f"{math.degrees(self.task.robot_turntable_speed(target_id, team=team)):.0f}°/s",
                popup.width - 28,
            )
            y = self._draw_key_value(
                x,
                y,
                "当前射击命中率",
                f"{self.task.shooting_hit_probability(target_id, team=team) * 100:.0f}%",
                popup.width - 28,
            )
            view_angle = self.task.robot_view_angle(
                target_id,
                team=team,
                sentry=self.sentry,
            )
            visible_count = len(
                self.task.robot_visible_enemy_positions(target_id, team=team)
            )
            y = self._draw_key_value(
                x,
                y,
                "视野方向",
                f"{math.degrees(view_angle) % 360:.1f}°",
                popup.width - 28,
            )
            y = self._draw_key_value(
                x,
                y,
                "本机发现",
                f"{visible_count} 个敌方机器人",
                popup.width - 28,
            )
            health_label = (
                f"{round(health)}/{round(maximum)}"
                if target_id != 5
                else "不适用地面装甲扣血"
            )
            if target_id == 5:
                y = self._draw_key_value(x, y, "血量", health_label, popup.width - 28)
                y = self._draw_key_value(
                    x, y, "有效防御增益", "不适用", popup.width - 28
                )
            else:
                y = self._draw_adjustable_progress_bar(
                    x, y, popup.width - 28, "血量", health, maximum,
                    (62, 184, 112) if team == "red" else (68, 133, 217),
                    target_id, compact=True,
                    action="own_robot_health" if team == "red" else "enemy_health",
                )
                y = self._draw_key_value(
                    x,
                    y,
                    "有效防御增益",
                    f"{self.task.robot_effective_defence(target_id, team=team) * 100:.0f}%",
                    popup.width - 28,
                )
            y = self._draw_key_value(x, y, "弹丸", profile.projectile, popup.width - 28)
            initial_ammo_label = (
                "不适用" if target_id == 2 else str(profile.initial_ammo)
            )
            y = self._draw_key_value(
                x,
                y,
                "初始允许发弹量",
                initial_ammo_label,
                popup.width - 28,
            )
            if self.replay_mode:
                shots_17, shots_42 = self._replay_shots(team, target_id)
                y = self._draw_key_value(
                    x, y, "累计17mm发弹（SQLite）", self._shot_text(shots_17), popup.width - 28
                )
                y = self._draw_key_value(
                    x, y, "累计42mm发弹（SQLite）", self._shot_text(shots_42), popup.width - 28
                )
            y = self._draw_key_value(
                x,
                y,
                "射击初速度上限",
                self._format_rule_value(
                    self.task.robot_muzzle_speed_limit(target_id, team=team),
                    "m/s",
                ),
                popup.width - 28,
            )
            dynamic_power_limit = self.task.robot_power_limit(target_id, team=team)
            power_limit = self._format_rule_value(dynamic_power_limit, "W")
            heat_capacity = (
                self.replay_heat_limits.get(
                    (team, target_id),
                    self.task.robot_heat_limit(target_id, team=team),
                )
                if self.replay_mode
                else self.task.robot_heat_limit(target_id, team=team)
            )
            heat_limit = self._format_rule_value(heat_capacity, "")
            q2_limit = self.task.robot_q2_limit(target_id, team=team)
            cooling_rate = self.task.robot_heat_cooling_rate(target_id, team=team)
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
            y = self._draw_key_value(x, y, "底盘机械功率", f"{current_power:.1f} W / {power_limit}", popup.width - 28)
            y = self._draw_key_value(x, y, "底盘功率上限", power_limit, popup.width - 28)
            buffer_label = (
                "不适用"
                if dynamic_power_limit is None
                else f"{self.task.robot_buffer_energy_value(target_id, team=team):.1f} J"
            )
            y = self._draw_key_value(
                x,
                y,
                "底盘缓冲能量",
                buffer_label,
                popup.width - 28,
            )
            y = self._draw_key_value(
                x,
                y,
                "底盘供电",
                "断电"
                if self.task.robot_chassis_power_cut(target_id, team=team)
                else "正常",
                popup.width - 28,
            )
            heat_value = "不适用" if heat_capacity is None else f"{current_heat:.1f} / {heat_limit}"
            y = self._draw_key_value(x, y, "当前热量", heat_value, popup.width - 28)
            y = self._draw_key_value(x, y, "射击热量上限", heat_limit, popup.width - 28)
            y = self._draw_key_value(x, y, "Q2 永久锁定阈值", self._format_rule_value(q2_limit, ""), popup.width - 28)
            lock_state = self.task.robot_heat_lock_state(target_id, team=team)
            lock_label = {"normal": "正常", "q1": "Q1 锁定至热量为 0", "q2": "Q2 当局永久锁定"}[lock_state]
            y = self._draw_key_value(x, y, "发射机构热量状态", lock_label, popup.width - 28)
            y = self._draw_key_value(x, y, "热量冷却", self._format_rule_value(cooling_rate, "/秒（10Hz）"), popup.width - 28)
            y = self._draw_key_value(x, y, "单发热量", self._format_rule_value(profile.heat_per_shot, ""), popup.width - 28)
            y = self._draw_key_value(x, y, "弹丸单发原始伤害", str(profile.raw_projectile_damage or "—"), popup.width - 28)
            y = self._draw_key_value(x, y, "撞击扣血", str(profile.collision_damage or "不适用"), popup.width - 28)
            y = self._draw_key_value(x, y, "二维碰撞半径", f"{ROBOT_ENTITY_COLLISION_RADIUS:.2f} 米", popup.width - 28)
            y = self._draw_key_value(x, y, "受攻击/撞击扣血", "适用" if profile.collision_applies else "不适用", popup.width - 28)
            if self.replay_mode:
                y = self._draw_key_value(
                    x, y, "SQLite剩余弹量", "数据集未提供", popup.width - 28
                )
            elif ammo is not None:
                if target_id != 2:
                    y = self._draw_adjustable_progress_bar(
                        x, y, popup.width - 28, "当前弹量", ammo,
                        self.task.robot_ammunition_limit(target_id),
                        (225, 166, 58), target_id, compact=True,
                        action="own_robot_ammo" if team == "red" else "enemy_robot_ammo",
                    )
                else:
                    y = self._draw_key_value(
                        x, y, "当前弹量", "不适用", popup.width - 28
                    )
            if self.task.robot_in_own_fort_gain(team, target_id):
                y = self._draw_key_value(
                    x,
                    y,
                    "堡垒储备允许发弹量",
                    f"{self.task.fort_reserve_ammo[team]}/"
                    f"{self.task.fort_reserve_capacity[team]}",
                    popup.width - 28,
                )
            position = self.task.robot_position(target_id) if team == "blue" else self.task.own_robot_position(target_id, self.sentry)
            y = self._draw_key_value(x, y, "坐标（米）", f"{position[0]:.2f}，{position[1]:.2f}", popup.width - 28)
            y = self._draw_key_value(x, y, "控制方式", "哨兵决策" if team == "red" and target_id == 8 else "场景手动控制", popup.width - 28)
        button_y = popup.bottom - 42
        if not self.replay_mode and target_id in ROBOT_PROFILES:
            if not (team == "red" and target_id == 8):
                turntable_button = self.pg.Rect(x + 112, button_y - 34, 116, 30)
                turntable_mode = self.task.robot_turntable_mode(target_id, team=team)
                turntable_labels = {0: "停止", 1: "低速", 2: "中速", 3: "高速"}
                self._draw_click_button(
                    turntable_button,
                    f"转盘：{turntable_labels[turntable_mode]}",
                )
                self.click_regions.append(
                    (
                        turntable_button,
                        "cycle_robot_turntable",
                        target_id,
                        1 if team == "red" else -1,
                    )
                )
            if target_id == 1:
                deploy_button = self.pg.Rect(x, button_y - 34, 104, 30)
                deploy_enabled = self.task.hero_mode == "ranged"
                deploy_label = (
                    "退出部署"
                    if self.task.hero_deployment_active(team)
                    else "进入部署"
                )
                self._draw_click_button(
                    deploy_button,
                    deploy_label if deploy_enabled else "部署需远程",
                    enabled=deploy_enabled,
                )
                if deploy_enabled:
                    self.click_regions.append(
                        (
                            deploy_button,
                            "toggle_hero_deploy",
                            target_id,
                            1 if team == "red" else -1,
                        )
                    )
            next_button_x = x
            if team == "red" or target_id != 5:
                drive = self.pg.Rect(next_button_x, button_y, 56, 30)
                self._draw_click_button(drive, "驾驶")
                action = "control_own_robot" if team == "red" else "control_enemy_robot"
                self.click_regions.append((drive, action, target_id, 0))
                next_button_x += 60
            if profile is not None and profile.heat_per_shot is not None:
                fire_button = self.pg.Rect(next_button_x, button_y, 72, 30)
                self._draw_click_button(fire_button, "选择射击")
                self.click_regions.append(
                    (fire_button, "robot_fire", target_id, 1 if team == "red" else -1)
                )
                next_button_x += 76
            if target_id in (1, 3, 4, 5):
                exp_button = self.pg.Rect(next_button_x, button_y, 74, 30)
                self._draw_click_button(exp_button, "经验+100")
                exp_action = "own_robot_exp" if team == "red" else "enemy_robot_exp"
                self.click_regions.append((exp_button, exp_action, target_id, 0))
        elif not self.replay_mode and target_id in (6, 7):
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
            maximum = self._replay_max_health(
                team, target_id, self.task.robot_max_hp(target_id, team=team)
            )
            return f"{side} {target_id}号 {profile.role}", profile, health, maximum, ammo
        side = "蓝方" if team == "blue" else "己方"
        if target_id == 6:
            maximum = self._replay_max_health(team, target_id, RULE_OUTPOST_HP)
            return f"{side}前哨", None, self.task.enemy_health(6) if team == "blue" else self.task.own_outpost_hp, maximum, None
        base_fallback = RULE_BASE_HP if team == "blue" else self.task.own_base_max_hp
        base_max = self._replay_max_health(team, target_id, base_fallback)
        return f"{side}基地", None, self.task.enemy_health(7) if team == "blue" else self.task.own_base_hp, base_max, None

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
            x, y, bar_width, "蓝方前哨", self.task.enemy_health(6),
            self._replay_max_health("blue", 6, RULE_OUTPOST_HP), (57, 124, 210), 6
        )
        y = self._draw_adjustable_progress_bar(
            x, y, bar_width, "蓝方基地", self.task.enemy_health(7),
            self._replay_max_health("blue", 7, 5000), (74, 145, 222), 7
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
                self._replay_max_health("blue", entity.target_id, entity.max_hp),
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
            "选择单位后使用 W/A/S/D 或方向键；在地图内左键朝光标方向射击",
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

        if not self.replay_mode:
            control_button = self.pg.Rect(x + width - 66, y - 1, 66, 25)
            self._draw_click_button(control_button, "驾驶中" if selected else "驾驶")
            self.click_regions.append((control_button, "control_own_robot", target_id, 0))

        health = self.task.own_robot_health(target_id)
        maximum = next(
            entity.max_hp
            for entity in OWN_FIELD_ENTITIES
            if entity.target_id == target_id
        )
        maximum = self._replay_max_health("red", target_id, maximum)
        ammo = self.task.own_robot_ammunition(target_id)
        ammo_maximum = self.task.own_robot_ammunition_limit(target_id)
        stat_y = y + 26
        self.screen.blit(
            self.panel_label_font.render(
                f"血量 {round(health)}/{maximum}", True, (214, 220, 222)
            ),
            (x, stat_y),
        )
        if not self.replay_mode:
            health_minus = self.pg.Rect(x + width - 58, stat_y - 1, 24, 23)
            health_plus = self.pg.Rect(x + width - 30, stat_y - 1, 24, 23)
            self._draw_click_button(health_minus, "−")
            self._draw_click_button(health_plus, "+")
            self.click_regions.append((health_minus, "own_robot_health", target_id, -1))
            self.click_regions.append((health_plus, "own_robot_health", target_id, 1))

        ammo_y = stat_y + 36
        if not self.replay_mode:
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
        if self.replay_mode:
            shots_17, shots_42 = self._replay_shots("red", target_id)
            ammo_text = "SQLite剩余弹量 未提供"
        else:
            ammo_text = f"弹量 {ammo}/{ammo_maximum}"
        self.screen.blit(
            self.panel_label_font.render(ammo_text, True, (178, 188, 192)),
            (x, ammo_y),
        )
        if self.replay_mode:
            self.screen.blit(
                self.small_font.render(
                    f"累计发弹 17mm {self._shot_text(shots_17)}｜42mm {self._shot_text(shots_42)}",
                    True, (151, 164, 169),
                ),
                (x, stat_y + 88),
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

        if self.replay_mode:
            value_text = self.panel_label_font.render(
                f"{round(self.task.remaining_time)} 秒", True, (226, 230, 231)
            )
            self.screen.blit(value_text, value_text.get_rect(topright=(x + width, y)))
            return y + 35

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
        if self.replay_mode:
            gap = 5
            button_width = (width - 2 * gap) // 3
            actions = (
                ("播放/暂停", "replay_toggle"),
                ("上一局", "replay_previous"),
                ("下一局", "replay_next"),
            )
            for index, (label, action) in enumerate(actions):
                rect = self.pg.Rect(x + index * (button_width + gap), y, button_width, 34)
                self._draw_click_button(rect, label)
                self.click_regions.append((rect, action, 0, 0))
            return y + 43
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
        marker: float | None = None,
    ) -> int:
        numeric_value = max(0.0, min(float(value), float(maximum)))
        ratio = numeric_value / maximum if maximum > 0 else 0.0
        label_text = self.panel_label_font.render(label, True, (190, 198, 201))
        self.screen.blit(label_text, (x, y))

        if self.replay_mode:
            value_text = self.panel_label_font.render(
                f"{round(value)}{suffix}" if suffix else f"{round(value)}/{round(maximum)}",
                True, (224, 228, 230),
            )
            self.screen.blit(value_text, value_text.get_rect(topright=(x + width, y)))
            bar_y = y + 27
            bar_height = 8 if compact else 12
            self.pg.draw.rect(self.screen, (48, 54, 58), (x, bar_y, width, bar_height))
            if ratio > 0.0:
                self.pg.draw.rect(self.screen, color, (x, bar_y, max(1, round(width * ratio)), bar_height))
            return y + (43 if compact else 49)

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
        if marker is not None and maximum > 0:
            marker_x = x + round(
                width * min(max(float(marker) / float(maximum), 0.0), 1.0)
            )
            self.pg.draw.line(
                self.screen,
                (235, 240, 242),
                (marker_x, bar_y - 2),
                (marker_x, bar_y + bar_height + 2),
                2,
            )
        return y + (46 if compact else 51)

    def _draw_click_button(self, rect, text: str, *, enabled: bool = True) -> None:
        hovered = enabled and rect.collidepoint(self.pg.mouse.get_pos())
        if enabled:
            background = (75, 86, 92) if hovered else (50, 58, 63)
            border = (104, 117, 123)
            foreground = (236, 239, 240)
        else:
            background = (38, 43, 46)
            border = (69, 76, 80)
            foreground = (116, 124, 128)
        self.pg.draw.rect(self.screen, background, rect)
        self.pg.draw.rect(self.screen, border, rect, 1)
        font = self.panel_label_font
        if font.size(text)[0] > rect.width - 8:
            font = self.small_font
        rendered = font.render(text, True, foreground)
        self.screen.blit(rendered, rendered.get_rect(center=rect.center))

    def _draw_snapshot_bar(self) -> None:
        width, height = self.screen.get_size()
        top = height - SNAPSHOT_BAR_HEIGHT
        if self.replay_mode:
            self.pg.draw.rect(self.screen, (35, 39, 42), (0, top, width, SNAPSHOT_BAR_HEIGHT))
            self.pg.draw.line(self.screen, (79, 88, 93), (0, top), (width, top), 1)
            left = 24
            self.replay_timeline_rect = self.pg.Rect(left, top + 17, width - 48, 13)
            self.pg.draw.rect(self.screen, (78, 94, 101), self.replay_timeline_rect, border_radius=6)
            duration = self.replay_player.replay.duration_seconds
            ratio = self.replay_player.time_seconds / duration if duration else 0.0
            progress = self.pg.Rect(
                left, top + 17,
                max(1, round(self.replay_timeline_rect.width * max(0.0, min(1.0, ratio)))),
                13,
            )
            self.pg.draw.rect(self.screen, (68, 176, 153), progress, border_radius=6)
            self.pg.draw.circle(self.screen, (244, 247, 246), (progress.right, self.replay_timeline_rect.centery), 7)
            text = self.small_font.render(
                f"SQLite 回放  {self.replay_player.time_seconds:06.1f}/{duration:.0f}s  "
                f"{'播放中' if self.replay_player.playing else '已暂停'}  {self.replay_player.speed:g}x  "
                "空格播放｜←→单步｜Shift十秒｜拖动时间轴｜N/B切换局",
                True, (205, 214, 217),
            )
            self.screen.blit(text, (left, top + 39))
            return
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

    def _aim_status(self) -> str:
        if self.decision.target <= 0:
            return ""
        error = self.task.aim_error(self.sentry, self.decision.target)
        if error is None:
            return ""
        return f"｜误差 {math.degrees(error):.1f}°"

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
        self._draw_field_zones(viewport)
        self._draw_custom_map_polygons(viewport)
        self._draw_editable_walls(viewport)
        self._draw_special_regions(viewport)
        self._draw_slow_regions(viewport)
        self._draw_region_editor(viewport)
        if self.map_layer_visibility["energy_rune"]:
            self._draw_energy_rune(viewport)
        if self.map_layer_visibility["sensor_view"]:
            self._draw_sensor_view(viewport)
        if self.map_layer_visibility["patrol_route"]:
            self._draw_patrol_route(viewport)
        self._draw_entities(viewport)
        self._draw_collision_volumes(viewport)
        if self.map_layer_visibility["objectives"]:
            self._draw_objectives(viewport)
        if self.map_layer_visibility["navigation"]:
            self._draw_navigation(viewport)
        self._draw_sentry(viewport)
        self.screen.set_clip(previous_clip)

        self.pg.draw.rect(self.screen, (103, 114, 120), rect, 2)
        self._draw_axes(viewport)

    def _draw_grid(self, viewport: Viewport) -> None:
        for x in range(1, int(self.arena.width)):
            start = viewport.world_to_screen(x, 0.0)
            end = viewport.world_to_screen(x, self.arena.height)
            color = (126, 137, 143) if x % 5 == 0 else (82, 93, 99)
            self.pg.draw.line(self.screen, color, start, end, 1)
        for y in range(1, int(self.arena.height)):
            start = viewport.world_to_screen(0.0, y)
            end = viewport.world_to_screen(self.arena.width, y)
            color = (126, 137, 143) if y % 5 == 0 else (82, 93, 99)
            self.pg.draw.line(self.screen, color, start, end, 1)

    def _draw_axes(self, viewport: Viewport) -> None:
        for x in range(0, 29, 2):
            screen_x, screen_y = viewport.world_to_screen(x, 0.0)
            label = self.small_font.render(f"{x}m", True, (173, 182, 186))
            self.screen.blit(label, label.get_rect(midtop=(round(screen_x), round(screen_y) + 5)))
        for y in range(0, 16, 5):
            screen_x, screen_y = viewport.world_to_screen(0.0, y)
            label = self.small_font.render(f"{y}m", True, (173, 182, 186))
            self.screen.blit(label, label.get_rect(midright=(round(screen_x) - 7, round(screen_y))))

    def _draw_field_zones(self, viewport: Viewport) -> None:
        visible_kinds = {
            kind
            for kind, _ in FIELD_ZONE_KIND_LABELS
            if self.map_layer_visibility.get(f"zone:{kind}", False)
        }
        if self.show_field_zones and not visible_kinds:
            # Preserve the old public flag for callers that set it directly.
            visible_kinds = {kind for kind, _ in FIELD_ZONE_KIND_LABELS}
        if not visible_kinds:
            return
        overlay = self.pg.Surface(self.screen.get_size(), self.pg.SRCALPHA)
        regions: list[tuple[object, object, list[tuple[int, int]]]] = []
        for zone in REGION_DEFINITIONS:
            if zone.kind not in visible_kinds:
                continue
            world_points = self._zone_points(zone)
            if len(world_points) < 3:
                continue
            points = [
                tuple(round(value) for value in viewport.world_to_screen(x, y))
                for x, y in world_points
            ]
            left = min(point[0] for point in points)
            top = min(point[1] for point in points)
            right = max(point[0] for point in points)
            bottom = max(point[1] for point in points)
            rect = self.pg.Rect(left, top, max(1, right - left), max(1, bottom - top))
            self.pg.draw.polygon(overlay, (*zone.color, 28), points)
            regions.append((zone, rect, points))
        self.screen.blit(overlay, (0, 0))
        for zone, rect, points in regions:
            if points:
                self.pg.draw.polygon(self.screen, zone.color, points, 1)
            if zone.label:
                label = self.small_font.render(zone.label, True, zone.color)
                self.screen.blit(
                    label,
                    label.get_rect(midbottom=(rect.centerx, rect.top - 2)),
                )

    def _draw_custom_map_polygons(self, viewport: Viewport) -> None:
        for item in self.custom_map_polygons:
            identifier = str(item.get("id"))
            kind = str(item.get("kind") or REGION_TYPES[0][0])
            if (
                not self.map_layer_visibility.get(f"custom:{identifier}", False)
                or not self.map_layer_visibility.get(f"zone:{kind}", False)
            ):
                continue
            points = normalize_points(item.get("points"))
            if len(points) < 3:
                continue
            screen_points = [
                tuple(round(value) for value in viewport.world_to_screen(x, y))
                for x, y in points
            ]
            definition = next(
                (entry for entry in REGION_DEFINITIONS if entry.name == kind),
                REGION_DEFINITIONS[0],
            )
            color_values = item.get("color", definition.color)
            color = tuple(int(value) for value in color_values[:3])
            overlay = self.pg.Surface(self.screen.get_size(), self.pg.SRCALPHA)
            self.pg.draw.polygon(overlay, (*color, 34), screen_points)
            self.screen.blit(overlay, (0, 0))
            self.pg.draw.polygon(self.screen, color, screen_points, 2)
            bounds = self.pg.Rect(
                min(point[0] for point in screen_points),
                min(point[1] for point in screen_points),
                max(1, max(point[0] for point in screen_points) - min(point[0] for point in screen_points)),
                max(1, max(point[1] for point in screen_points) - min(point[1] for point in screen_points)),
            )
            label = self.small_font.render(str(item.get("name", identifier)), True, color)
            self.screen.blit(label, label.get_rect(midbottom=(bounds.centerx, bounds.top - 2)))

    def _draw_editable_walls(self, viewport: Viewport) -> None:
        if not self.map_layer_visibility.get("editable_walls", False):
            return
        for item in getattr(self, "wall_polygons", ()):
            points = normalize_points(item.get("points"))
            if len(points) < 2:
                continue
            start = tuple(round(value) for value in viewport.world_to_screen(*points[0]))
            end = tuple(round(value) for value in viewport.world_to_screen(*points[1]))
            color = tuple(int(value) for value in item.get("color", (225, 72, 72))[:3])
            try:
                thickness = float(item.get("thickness", DEFAULT_WALL_THICKNESS))
            except (TypeError, ValueError):
                thickness = DEFAULT_WALL_THICKNESS
            line_width = max(2, round(thickness * viewport.scale))
            self.pg.draw.line(self.screen, (255, 235, 235), start, end, max(1, line_width + 2))
            self.pg.draw.line(self.screen, color, start, end, line_width)
            self.pg.draw.circle(self.screen, color, start, max(1, line_width // 2))
            self.pg.draw.circle(self.screen, color, end, max(1, line_width // 2))
            midpoint = ((start[0] + end[0]) // 2, (start[1] + end[1]) // 2)
            label = self.small_font.render(str(item.get("name", "墙体")), True, color)
            self.screen.blit(label, label.get_rect(midbottom=(midpoint[0], midpoint[1] - line_width)))

    def _draw_special_regions(self, viewport: Viewport) -> None:
        if not self.map_layer_visibility.get("special_regions", False):
            return
        for item in getattr(self, "special_regions", ()):
            points = normalize_points(item.get("points"))
            if len(points) < 2:
                continue
            start = tuple(round(value) for value in viewport.world_to_screen(*points[0]))
            end = tuple(round(value) for value in viewport.world_to_screen(*points[1]))
            color = tuple(int(value) for value in item.get("color", (235, 180, 70))[:3])
            try:
                thickness = float(item.get("thickness", DEFAULT_WALL_THICKNESS))
            except (TypeError, ValueError):
                thickness = DEFAULT_WALL_THICKNESS
            line_width = max(2, round(thickness * viewport.scale))
            self.pg.draw.line(
                self.screen,
                (255, 249, 205),
                start,
                end,
                max(1, line_width + 2),
            )
            self.pg.draw.line(self.screen, color, start, end, line_width)
            self.pg.draw.circle(self.screen, color, start, max(1, line_width // 2))
            self.pg.draw.circle(self.screen, color, end, max(1, line_width // 2))
            midpoint = ((start[0] + end[0]) // 2, (start[1] + end[1]) // 2)
            label = self.small_font.render(
                f"{item.get('name', '特殊墙体')}｜工程/步兵3/4｜1秒",
                True,
                color,
            )
            self.screen.blit(
                label,
                label.get_rect(midbottom=(midpoint[0], midpoint[1] - line_width)),
            )

    def _draw_slow_regions(self, viewport: Viewport) -> None:
        if not self.map_layer_visibility.get("slow_regions", False):
            return
        for item in getattr(self, "slow_regions", ()):
            points = normalize_points(item.get("points"))
            if len(points) < 3:
                continue
            screen_points = [
                tuple(round(value) for value in viewport.world_to_screen(x, y))
                for x, y in points
            ]
            color = tuple(int(value) for value in item.get("color", (86, 174, 220))[:3])
            overlay = self.pg.Surface(self.screen.get_size(), self.pg.SRCALPHA)
            self.pg.draw.polygon(overlay, (*color, 52), screen_points)
            self.screen.blit(overlay, (0, 0))
            self.pg.draw.polygon(self.screen, color, screen_points, 2)
            bounds = self.pg.Rect(
                min(point[0] for point in screen_points),
                min(point[1] for point in screen_points),
                max(1, max(point[0] for point in screen_points) - min(point[0] for point in screen_points)),
                max(1, max(point[1] for point in screen_points) - min(point[1] for point in screen_points)),
            )
            label = self.small_font.render(
                f"{item.get('name', '减速区域')}｜速度 50%",
                True,
                color,
            )
            self.screen.blit(label, label.get_rect(midbottom=(bounds.centerx, bounds.top - 2)))

    def _draw_region_editor(self, viewport: Viewport) -> None:
        if (
            not self.region_edit_new_custom
            and not self.region_edit_new_wall
            and not self.region_edit_new_special
            and not self.region_edit_new_slow
            and self.region_edit_target is None
            and self.region_edit_custom_id is None
            and self.region_edit_wall_id is None
            and self.region_edit_special_id is None
            and self.region_edit_slow_id is None
            and self.region_edit_patrol_kind is None
            and not self.region_edit_points
        ):
            return
        points = [
            tuple(round(value) for value in viewport.world_to_screen(x, y))
            for x, y in self.region_edit_points
        ]
        if len(points) >= 2:
            self.pg.draw.lines(
                self.screen,
                (248, 211, 90),
                self.region_edit_patrol_kind is not None or len(points) >= 3,
                points,
                3,
            )
        if len(points) >= 3 and self.region_edit_patrol_kind is None:
            overlay = self.pg.Surface(self.screen.get_size(), self.pg.SRCALPHA)
            self.pg.draw.polygon(overlay, (248, 211, 90, 32), points)
            self.screen.blit(overlay, (0, 0))
        if points:
            mouse = self.pg.mouse.get_pos()
            if viewport.contains(*mouse):
                self.pg.draw.line(self.screen, (252, 232, 151), points[-1], mouse, 1)
        for index, point in enumerate(points, start=1):
            center = (round(point[0]), round(point[1]))
            self.pg.draw.circle(self.screen, (25, 31, 35), center, MAP_EDITOR_VERTEX_RADIUS)
            self.pg.draw.circle(self.screen, (255, 218, 90), center, MAP_EDITOR_VERTEX_RADIUS, 2)
            label = self.small_font.render(str(index), True, (255, 239, 170))
            self.screen.blit(label, label.get_rect(center=(center[0], center[1] - 20)))

    def _draw_energy_rune(self, viewport: Viewport) -> None:
        for team, (x, y) in RUNE_POSITIONS.items():
            center = self.pg.Vector2(viewport.world_to_screen(x, y))
            radius = max(8, round(0.8 * viewport.scale))
            color = (210, 75, 82) if team == "red" else (68, 133, 217)
            self.pg.draw.circle(self.screen, color, center, radius, 2)
            for index in range(5):
                angle = -math.pi / 2 + index * math.tau / 5
                start = center + self.pg.Vector2(
                    math.cos(angle) * radius * 0.35,
                    math.sin(angle) * radius * 0.35,
                )
                end = center + self.pg.Vector2(
                    math.cos(angle) * radius,
                    math.sin(angle) * radius,
                )
                active = (
                    team == "red"
                    and self.task.rune_state in ("activating", "active")
                    and index in self.task.rune_active_plates
                )
                self.pg.draw.line(
                    self.screen,
                    (245, 220, 80) if active else color,
                    start,
                    end,
                    5 if active else 2,
                )
            label = self.small_font.render(
                "能量机关", True, color
            )
            self.screen.blit(
                label,
                label.get_rect(midtop=(round(center.x), round(center.y + radius + 4))),
            )

    def _draw_collision_volumes(self, viewport: Viewport) -> None:
        if (
            not self.map_layer_visibility.get("collision_volumes", False)
            and not self.show_collision_volumes
        ):
            return
        # The map image is a visual reference only.  Movement uses the PGM
        # occupancy grid, so render that grid here to make hidden collision
        # causes (especially around gain zones) inspectable.  ``los_grid`` is
        # the uninflated PGM map; ``collision_grid`` includes the robot's
        # circumscribed footprint and the field boundary.
        raw_grid = getattr(self, "los_grid", None)
        inflated_grid = getattr(self, "collision_grid", None)
        if raw_grid is not None and inflated_grid is not None:
            wall_overlay = self.pg.Surface(self.screen.get_size(), self.pg.SRCALPHA)
            clearance_overlay = self.pg.Surface(self.screen.get_size(), self.pg.SRCALPHA)
            self._draw_occupancy_runs(
                wall_overlay,
                viewport,
                raw_grid,
                (239, 72, 72, 148),
            )
            self._draw_occupancy_runs(
                clearance_overlay,
                viewport,
                inflated_grid,
                (248, 204, 74, 72),
                subtract=raw_grid,
            )
            self.screen.blit(clearance_overlay, (0, 0))
            self.screen.blit(wall_overlay, (0, 0))

        outline = (236, 196, 82)
        overlay = self.pg.Surface(self.screen.get_size(), self.pg.SRCALPHA)
        for min_x, min_y, max_x, max_y in STATIC_COLLISION_RECTANGLES:
            left, top = viewport.world_to_screen(min_x, max_y)
            right, bottom = viewport.world_to_screen(max_x, min_y)
            rect = self.pg.Rect(
                round(left),
                round(top),
                max(1, round(right - left)),
                max(1, round(bottom - top)),
            )
            self.pg.draw.rect(overlay, (*outline, 36), rect)
            self.pg.draw.rect(self.screen, outline, rect, 2)
        self.screen.blit(overlay, (0, 0))

        bodies = [
            (
                self.task.robot_position(target_id, team="blue"),
                self._robot_collision_radius("blue", target_id),
                (74, 143, 224),
            )
            for target_id in self.task.robot_positions
        ]
        bodies.extend(
            (
                self.task.own_robot_position(target_id),
                self._robot_collision_radius("red", target_id),
                (62, 184, 112),
            )
            for target_id in self.task.own_robot_positions
        )
        bodies.append(
            ((self.sentry.x, self.sentry.y), ROBOT_ENTITY_COLLISION_RADIUS, (62, 184, 112))
        )
        for (x, y), radius, color in bodies:
            center = viewport.world_to_screen(x, y)
            self.pg.draw.circle(
                self.screen,
                color,
                (round(center[0]), round(center[1])),
                max(2, round(radius * viewport.scale)),
                1,
            )

        # Keep the legend on the arena rather than in the side panel so it
        # remains visible while editing geometry or resizing the window.
        if raw_grid is not None and inflated_grid is not None:
            legend_x = round(viewport.left + 12)
            legend_y = round(viewport.top + 12)
            legend = self.pg.Surface((244, 58), self.pg.SRCALPHA)
            self.pg.draw.rect(legend, (20, 25, 28, 205), legend.get_rect(), border_radius=4)
            self.pg.draw.rect(legend, (114, 127, 132, 220), legend.get_rect(), 1, border_radius=4)
            self.pg.draw.rect(legend, (239, 72, 72), (10, 11, 18, 10))
            self.pg.draw.rect(legend, (248, 204, 74), (10, 35, 18, 10))
            wall_label = self.small_font.render("红：自定义墙体", True, (240, 231, 231))
            clearance_label = self.small_font.render("黄：底盘安全边界", True, (245, 236, 194))
            legend.blit(wall_label, (36, 5))
            legend.blit(clearance_label, (36, 29))
            self.screen.blit(legend, (legend_x, legend_y))

    def _draw_occupancy_runs(
        self,
        target,
        viewport: Viewport,
        grid: OccupancyGrid,
        color: tuple[int, int, int, int],
        *,
        subtract: OccupancyGrid | None = None,
    ) -> None:
        """Draw blocked occupancy cells as horizontal runs.

        Drawing runs instead of individual 5 cm cells keeps the optional
        overlay responsive while preserving the exact PGM wall footprint.
        ``subtract`` is used for the inflated-only clearance band.
        """
        resolution = grid.arena.map_resolution
        for row in range(grid.height):
            row_start = row * grid.width
            column = 0
            while column < grid.width:
                index = row_start + column
                occupied = bool(grid.blocked[index])
                if occupied and subtract is not None:
                    occupied = not bool(subtract.blocked[index])
                if not occupied:
                    column += 1
                    continue
                run_start = column
                column += 1
                while column < grid.width:
                    index = row_start + column
                    occupied = bool(grid.blocked[index])
                    if occupied and subtract is not None:
                        occupied = not bool(subtract.blocked[index])
                    if not occupied:
                        break
                    column += 1
                min_x = run_start * resolution
                max_x = column * resolution
                max_y = grid.arena.height - row * resolution
                min_y = max_y - resolution
                left, top = viewport.world_to_screen(min_x, max_y)
                right, bottom = viewport.world_to_screen(max_x, min_y)
                self.pg.draw.rect(
                    target,
                    color,
                    self.pg.Rect(
                        round(left),
                        round(top),
                        max(1, round(right - left)),
                        max(1, round(bottom - top)),
                    ),
                )

    def _draw_objectives(self, viewport: Viewport) -> None:
        objectives = (
            (*HOME, "归位点", (38, 160, 218)),
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
        if self.controlled_robot_id is None:
            observer_position = (self.sentry.x, self.sentry.y)
            view_angle = self.sentry.turret_angle
            sentry_view = True
        else:
            observer_team = self.controlled_robot_team or "blue"
            observer_position = self.task.robot_position(
                self.controlled_robot_id,
                team=observer_team,
            )
            view_angle = self.task.robot_view_angle(
                self.controlled_robot_id,
                team=observer_team,
                sentry=self.sentry,
            )
            sentry_view = False
        center = self.pg.Vector2(viewport.world_to_screen(*observer_position))
        half_angle = AUTOAIM_HALF_VIEW

        def sector_points(distance: float):
            radius = viewport.scale * distance
            points = [center]
            for index in range(17):
                angle = (
                    view_angle
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
        detection_color = (
            (47, 177, 197, 28)
            if not sentry_view or self.decision.tripod_mode
            else (195, 82, 96, 28)
        )
        self.pg.draw.polygon(overlay, detection_color, detection_points)
        self.pg.draw.polygon(overlay, (242, 158, 54, 46), attack_points)
        self.screen.blit(overlay, (0, 0))

        detection_edge = (
            (55, 154, 172)
            if not sentry_view or self.decision.tripod_mode
            else (184, 72, 84)
        )
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
            math.cos(view_angle),
            -math.sin(view_angle),
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
                self.task.conservative_patrol_route,
                "保守",
                (68, 116, 132) if not self.task.patrol_is_aggressive else (137, 151, 157),
                not self.task.patrol_is_aggressive,
            ),
            (
                self.task.aggressive_patrol_route,
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
        gimbal_angle = self.task.robot_view_angle(
            target_id,
            team=team,
            sentry=self.sentry,
        )
        turntable_angle = self.task.robot_turntable_angle(
            target_id,
            team=team,
            sentry=self.sentry,
        )
        if profile.has_turntable:
            ring_color = (184, 65, 70) if team == "red" else (48, 105, 185)
            self.pg.draw.circle(self.screen, ring_color, center, collider_radius + 2, 2)
            for offset in (0.0, math.tau / 3.0, 2.0 * math.tau / 3.0):
                angle = turntable_angle + offset
                marker = center + self.pg.Vector2(
                    math.cos(angle) * (collider_radius + 1),
                    -math.sin(angle) * (collider_radius + 1),
                )
                self.pg.draw.circle(self.screen, ring_color, marker, 2)
        if profile.has_gimbal:
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
