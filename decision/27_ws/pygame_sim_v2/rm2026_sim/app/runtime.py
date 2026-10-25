"""主循环与输入事件。

这个模块只负责把 Pygame 事件转成应用动作；规则计算仍由 ``TaskScenario``
负责，便于以后替换界面或增加无头测试。
"""

from __future__ import annotations

from .main import *


class RuntimeMixin:
    def _advance_live_motion(
        self,
        elapsed_seconds: float,
        move_x: float,
        move_y: float,
        motion_decision: DecisionView,
        *,
        restarting: bool,
    ) -> float:
        """Advance automatic simulation and higher-priority manual driving.

        Pause freezes referee/automatic time, but an operator who has selected
        a robot keeps direct chassis control. Restart signalling remains a hard
        freeze because it is rebuilding the live decision state.
        """
        simulation_elapsed = (
            0.0 if self.task.game_paused or restarting else elapsed_seconds
        )
        manual_elapsed = 0.0 if restarting else elapsed_seconds
        self._collision_damage_cooldown = max(
            0.0,
            getattr(self, "_collision_damage_cooldown", 0.0)
            - simulation_elapsed,
        )

        if self.controlled_robot_id is not None and manual_elapsed > 0.0:
            self._move_controlled_robot(move_x, move_y, manual_elapsed)

        if self.sentry.manual_control and not self.task.game_finished:
            if manual_elapsed > 0.0:
                self._update_sentry_motion(
                    manual_elapsed,
                    move_x,
                    move_y,
                    motion_decision,
                )
        elif simulation_elapsed > 0.0:
            self._update_sentry_motion(
                simulation_elapsed,
                move_x,
                move_y,
                motion_decision,
            )

        if simulation_elapsed > 0.0:
            self._update_other_robot_chassis_power(
                simulation_elapsed,
                move_x,
                move_y,
            )
        elif self.controlled_robot_id is not None and manual_elapsed > 0.0:
            # Keep manual-drive telemetry responsive while rule timers and
            # buffer-energy settlement remain frozen by TaskScenario.update().
            self._update_other_robot_chassis_power(
                manual_elapsed,
                move_x,
                move_y,
            )
        return simulation_elapsed

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
                            not self.replay_mode
                            and
                            event.key == self.pg.K_s
                            and event.mod & self.pg.KMOD_CTRL
                        ):
                            self._save_snapshot()
                        elif event.key == self.pg.K_ESCAPE:
                            if (
                                self.region_edit_new_custom
                                or self.region_edit_new_wall
                                or self.region_edit_new_special
                                or self.region_edit_target is not None
                                or self.region_edit_custom_id is not None
                                or self.region_edit_wall_id is not None
                                or self.region_edit_special_id is not None
                                or self.region_edit_patrol_kind is not None
                            ):
                                self._cancel_region_edit()
                            elif self.subsystem_panel_open:
                                self.subsystem_panel_open = False
                            else:
                                running = False
                        elif event.key == self.pg.K_SPACE:
                            self.replay_player.toggle() if self.replay_mode else self.task.toggle_pause()
                        elif event.key == self.pg.K_p:
                            self.replay_player.toggle() if self.replay_mode else self.task.toggle_pause()
                        elif self.replay_mode and event.key == self.pg.K_LEFT:
                            self.replay_player.step(-10.0 if event.mod & self.pg.KMOD_SHIFT else -1.0)
                        elif self.replay_mode and event.key == self.pg.K_RIGHT:
                            self.replay_player.step(10.0 if event.mod & self.pg.KMOD_SHIFT else 1.0)
                        elif self.replay_mode and event.key == self.pg.K_HOME:
                            self.replay_player.seek(0.0)
                        elif self.replay_mode and event.key == self.pg.K_END:
                            self.replay_player.seek(self.replay_player.replay.duration_seconds)
                        elif self.replay_mode and event.key in (self.pg.K_EQUALS, self.pg.K_PLUS, self.pg.K_KP_PLUS):
                            self.replay_player.faster()
                        elif self.replay_mode and event.key in (self.pg.K_MINUS, self.pg.K_KP_MINUS):
                            self.replay_player.slower()
                        elif self.replay_mode and event.key == self.pg.K_l:
                            self.replay_player.loop = not self.replay_player.loop
                        elif self.replay_mode and event.key in (self.pg.K_n, self.pg.K_PAGEDOWN):
                            self._open_replay_match(self.replay_match_index + 1)
                        elif self.replay_mode and event.key in (self.pg.K_b, self.pg.K_PAGEUP):
                            self._open_replay_match(self.replay_match_index - 1)
                        elif not self.replay_mode and event.key in (self.pg.K_0, self.pg.K_KP0):
                            self._switch_to_auto_control()
                        elif not self.replay_mode and event.key == self.pg.K_r:
                            self._restart_validation()
                        elif not self.replay_mode and event.key == self.pg.K_F9:
                            self.subsystem_panel_open = not self.subsystem_panel_open
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
                    elif event.type == self.pg.MOUSEWHEEL:
                        self._scroll_map_editor_list(
                            event.y,
                            self.pg.mouse.get_pos(),
                        )
                    elif (
                        event.type == self.pg.MOUSEBUTTONDOWN
                        and event.button in (4, 5)
                    ):
                        self._scroll_map_editor_list(
                            1 if event.button == 4 else -1,
                            event.pos,
                        )
                    elif event.type == self.pg.MOUSEBUTTONDOWN and event.button == 1:
                        handled = self._handle_replay_timeline(event.pos) if self.replay_mode else False
                        if not handled:
                            handled = self._handle_mouse_click(event.pos)
                        if not handled and not self.replay_mode:
                            handled = self._region_editor_click(event.pos)
                        if not handled and not self.replay_mode:
                            handled = self._fire_controlled_robot_at(event.pos)
                        if not handled:
                            self._manual_fire_held = self.sentry.manual_control
                    elif event.type == self.pg.MOUSEBUTTONDOWN and event.button == 3:
                        if not self.replay_mode:
                            self._region_editor_right_click(event.pos)
                    elif event.type == self.pg.MOUSEBUTTONUP and event.button == 1:
                        self._manual_fire_held = False
                        self._region_editor_release()
                        if self.replay_mode:
                            self.replay_timeline_dragging = False
                    elif event.type == self.pg.MOUSEMOTION:
                        if self.replay_mode and self.replay_timeline_dragging:
                            self._handle_replay_timeline(event.pos)
                        elif not self.replay_mode:
                            self._region_editor_motion(event.pos)

                if self.replay_mode:
                    frame = self.replay_player.update(elapsed_seconds)
                    self._apply_replay_frame(frame)
                    self._render(self._viewport())
                    self.pg.display.flip()
                    frame_count += 1
                    if max_frames is not None and frame_count >= max_frames:
                        if screenshot_path is not None:
                            self.pg.image.save(self.screen, str(screenshot_path))
                        running = False
                    continue

                viewport = self._viewport()
                move_x, move_y = self._movement_input()
                bridge_decision = self._bridge_decision()
                local_decision = self._local_decision()
                motion_decision = self._gate_gimbal_by_alignment(
                    bridge_decision or local_decision
                )
                self.task.set_robot_turntable_mode(
                    8,
                    motion_decision.spin_mode,
                    team="red",
                )
                restarting = self._restart_signal_remaining > 0.0
                simulation_elapsed = self._advance_live_motion(
                    elapsed_seconds,
                    move_x,
                    move_y,
                    motion_decision,
                    restarting=restarting,
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
                shot = (
                    self.task.resolve_fire_shot(
                        self.sentry,
                        preferred_target=preferred_target,
                    )
                    if fire_request
                    else None
                )
                self.hit_target_id = shot.target_id if shot is not None else None
                if not restarting and not self.sentry.manual_control and shot is None:
                    # Automatic fire must not consume ammo/heat while the
                    # target is still outside the firing alignment.
                    fire_request = False
                # A map point only proves that the building was hit; it does
                # not provide the two-dimensional armour impact coordinate
                # needed to award the physical 10 mm x 10 mm critical area.
                critical_zone = False
                armor_zone = (
                    self.task.armor_zone_for_shot(shot, self.sentry, team="blue")
                    if shot is not None
                    else None
                )
                self.decision = self.task.update(
                    0.0 if restarting else elapsed_seconds,
                    self.sentry,
                    decision_override=motion_decision,
                    fire_request=fire_request,
                    hit_target_id=self.hit_target_id,
                    attack_buff=self.task.effective_attack_buff,
                    target_defence_buff=(
                        -self.task.radar_vulnerability(self.hit_target_id)
                        if self.hit_target_id is not None
                        else 0.0
                    ),
                    critical_zone=critical_zone,
                    target_armor_zone=armor_zone,
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
