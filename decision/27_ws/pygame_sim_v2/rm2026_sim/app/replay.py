"""数据集回放控制。

回放只更新画面状态，不参与实时规则推进，和实时仿真保持清晰边界。
"""

from __future__ import annotations

from .main import *


class ReplayMixin:
    @staticmethod
    def _dataset_local_id(sample) -> int | None:
        """Map region-dataset ids/types to the simulator's local ids."""
        return dataset_local_entity_id(sample.team, sample.robot_id)

    @staticmethod
    def _dataset_team(sample) -> str:
        return "red" if sample.team in ("红", "red") else "blue"

    @staticmethod
    def _shot_text(value: int | None) -> str:
        return "不适用" if value is None else str(round(value))

    def _replay_max_health(self, team: str, target_id: int, fallback: float) -> float:
        return self.replay_max_hp.get((team, target_id), fallback) if self.replay_mode else fallback

    @staticmethod
    def _sample_heat(sample) -> tuple[float | None, float | None]:
        if sample.robot_type == "英雄":
            return sample.large_heat, sample.large_heat_limit
        return sample.small_heat, sample.small_heat_limit

    @staticmethod
    def _inferred_economy_text(action) -> str:
        income = any(marker in action.action for marker in ("收入", "额度", "基线"))
        sign = "+" if income else "-"
        return f"{action.action} {sign}{action.cost:g}（{action.confidence:.0%}）"

    def _replay_shots(self, team: str, target_id: int) -> tuple[int | None, int | None]:
        prefix = "own_robot_" if team == "red" else "robot_"
        return (
            getattr(self.task, f"{prefix}shots_17mm").get(target_id),
            getattr(self.task, f"{prefix}shots_42mm").get(target_id),
        )

    def _apply_replay_frame(self, frame: ReplayFrame) -> None:
        """Apply one SQLite snapshot; events are annotations only.

        HP, position, heat, power, coins and cumulative shots come from
        ``timeseries``.  Event rows are consumed in the time interval below
        and are never applied as damage/ammo a second time.
        """
        if not self.replay_mode:
            return
        previous_time = -1e-6 if self.replay_last_frame is None else self.replay_last_time
        seeking_back = frame.time_seconds + 1e-6 < previous_time
        if seeking_back:
            self._rebuild_replay_annotations(frame)
            interval_events: tuple[ReplayEvent, ...] = ()
        else:
            interval_events = tuple(
                event for event in frame.events
                if event.time_seconds > previous_time + 1e-6
                and event.time_seconds <= frame.time_seconds + 1e-6
            )
            self.replay_event_log.extend(interval_events)
            if len(self.replay_event_log) > 80:
                del self.replay_event_log[:-80]
            if self.replay_inference is not None:
                self._advance_replay_inference(frame.time_seconds)

        self.replay_vulnerability.clear()
        self.replay_max_hp.clear()
        self.replay_heat_limits.clear()
        for sample in frame.samples:
            team = self._dataset_team(sample)
            target_id = self._dataset_local_id(sample)
            if target_id is None:
                continue
            if sample.robot_type not in ("基地", "前哨站"):
                self.replay_vulnerability[(team, target_id)] = sample.vulnerable
                _, heat_limit = self._sample_heat(sample)
                if heat_limit is not None and heat_limit > 0.0:
                    self.replay_heat_limits[(team, target_id)] = heat_limit
            if sample.max_hp is not None and sample.max_hp > 0.0:
                self.replay_max_hp[(team, target_id)] = sample.max_hp
            if sample.team_coins is not None:
                self.replay_total_coins[team] = sample.team_coins
            if sample.remaining_coins is not None:
                self.replay_remaining_coins[team] = sample.remaining_coins
            if sample.robot_type in ("基地", "前哨站"):
                if team == "red":
                    if target_id == 7 and sample.hp is not None:
                        self.task.own_base_hp = max(0.0, sample.hp)
                    elif target_id == 6 and sample.hp is not None:
                        self.task.own_outpost_hp = max(0.0, sample.hp)
                else:
                    if target_id == 7 and sample.hp is not None:
                        self.task.enemy_base_hp = max(0.0, sample.hp)
                    elif target_id == 6 and sample.hp is not None:
                        self.task.enemy_outpost_hp = max(0.0, sample.hp)
                continue
            if team == "red" and target_id == 8:
                if sample.x is not None:
                    self.sentry.x = sample.x
                if sample.y is not None:
                    self.sentry.y = sample.y
                if sample.heading_degrees is not None:
                    self.sentry.turret_angle = math.radians(sample.heading_degrees)
                replay_heat, self.replay_sentry_heat_limit = self._sample_heat(sample)
                if replay_heat is not None:
                    self.sentry.heat = replay_heat
                if sample.chassis_power is not None:
                    self.sentry.chassis_power = sample.chassis_power
                if sample.hp is not None:
                    self.task.sentry_hp = max(0.0, sample.hp)
                self.replay_sentry_vulnerable = sample.vulnerable
                self.task.own_robot_shots_17mm[target_id] = None if sample.shots_17mm is None else round(sample.shots_17mm)
                self.task.own_robot_shots_42mm[target_id] = None if sample.shots_42mm is None else round(sample.shots_42mm)
                continue
            positions = self.task.own_robot_positions if team == "red" else self.task.robot_positions
            health = self.task.own_robot_hp if team == "red" else self.task.robot_hp
            shots_17 = self.task.own_robot_shots_17mm if team == "red" else self.task.robot_shots_17mm
            shots_42 = self.task.own_robot_shots_42mm if team == "red" else self.task.robot_shots_42mm
            if target_id in positions:
                if sample.x is not None and sample.y is not None:
                    positions[target_id] = [sample.x, sample.y]
                if sample.hp is not None:
                    health[target_id] = max(0.0, sample.hp)
                if sample.chassis_power is not None:
                    (self.task.own_robot_power if team == "red" else self.task.robot_power)[target_id] = sample.chassis_power
                replay_heat, heat_limit = self._sample_heat(sample)
                if replay_heat is not None:
                    (self.task.own_robot_heat if team == "red" else self.task.robot_heat)[target_id] = replay_heat
                if heat_limit is not None and heat_limit > 0.0:
                    self.replay_heat_limits[(team, target_id)] = heat_limit
                shots_17[target_id] = None if sample.shots_17mm is None else round(sample.shots_17mm)
                shots_42[target_id] = None if sample.shots_42mm is None else round(sample.shots_42mm)
        # The replay clock is the only clock in this mode.  Keep existing UI
        # panels usable while preventing live rule simulation from mutating it.
        self.task.remaining_time = max(0.0, MATCH_DURATION - frame.time_seconds)
        self.task.game_running = True
        self.task.game_finished = frame.time_seconds >= self.replay_player.replay.duration_seconds - 1e-6
        self.task.game_paused = not self.replay_player.playing
        self.task.economy = round(self.replay_remaining_coins["red"] or 0.0)
        self.decision = DecisionView(
            behavior="SQLite 时间序列回放",
            posture=self.task.active_posture,
            goal=None,
            spin_mode=0,
            tripod_mode=0,
            shoot_mode=0,
            target=0,
            confirm_respawn=0,
            health_threshold=self.task.health_threshold,
        )
        self.replay_last_time = frame.time_seconds
        self.replay_last_frame = frame

    def _rebuild_replay_annotations(self, target: ReplayFrame) -> None:
        """Reconstruct event/economy annotations after a backwards seek."""
        self.replay_event_log = list(target.events[-80:])
        self.replay_economy_log.clear()
        if self.replay_inference is None or self.replay_player is None:
            return
        self.replay_inference.reset()
        self.replay_inference_cursor = -1e-6
        times = sorted({0.0, target.time_seconds, *(
            time_value for time_value in self.replay_player.replay.times
            if time_value <= target.time_seconds
        )})
        previous = -1e-6
        for time_value in times:
            replay_frame = self.replay_player.replay.frame_at(time_value)
            events = self.replay_player.replay.events_between(previous, time_value)
            self.replay_economy_log.extend(
                self.replay_inference.observe(replay_frame, events)
            )
            previous = time_value
        self.replay_inference_cursor = target.time_seconds
        if len(self.replay_economy_log) > 80:
            del self.replay_economy_log[:-80]

    def _advance_replay_inference(self, target_time: float) -> None:
        if self.replay_inference is None or self.replay_player is None:
            return
        replay = self.replay_player.replay
        for time_value in replay.times:
            if time_value <= self.replay_inference_cursor + 1e-9:
                continue
            if time_value > target_time + 1e-6:
                break
            events = replay.events_between(self.replay_inference_cursor, time_value)
            frame = replay.frame_at(time_value)
            self.replay_economy_log.extend(
                self.replay_inference.observe(frame, events)
            )
            self.replay_inference_cursor = time_value
        if len(self.replay_economy_log) > 80:
            del self.replay_economy_log[:-80]

    def _open_replay_match(self, index: int) -> None:
        if not self.replay_repository or not self.replay_matches:
            return
        self.replay_match_index = index % len(self.replay_matches)
        replay = self.replay_repository.load_replay(
            self.replay_matches[self.replay_match_index].game_id
        )
        self.replay_player = ReplayPlayer(replay)
        self.replay_last_time = 0.0
        self.replay_inference_cursor = -1e-6
        self.replay_last_frame = None
        self.replay_event_log.clear()
        self.replay_economy_log.clear()
        self.replay_total_coins = {"red": None, "blue": None}
        self.replay_remaining_coins = {"red": None, "blue": None}
        self.replay_vulnerability.clear()
        self.replay_max_hp.clear()
        self.replay_heat_limits.clear()
        self.replay_sentry_heat_limit = None
        self.replay_sentry_vulnerable = False
        self.pending_fire_shooter = None
        self.task.robot_shots_17mm = {target_id: None for target_id in self.task.robot_shots_17mm}
        self.task.robot_shots_42mm = {target_id: None for target_id in self.task.robot_shots_42mm}
        self.task.own_robot_shots_17mm = {target_id: None for target_id in self.task.own_robot_shots_17mm}
        self.task.own_robot_shots_42mm = {target_id: None for target_id in self.task.own_robot_shots_42mm}
        if self.replay_inference is not None:
            self.replay_inference.reset()
        self._apply_replay_frame(self.replay_player.frame())

    def _handle_replay_timeline(self, position: tuple[int, int]) -> bool:
        timeline = getattr(self, "replay_timeline_rect", None)
        if timeline is None or not timeline.collidepoint(position):
            return False
        self.replay_timeline_dragging = True
        ratio = (position[0] - timeline.left) / max(1, timeline.width)
        self.replay_player.seek(ratio * self.replay_player.replay.duration_seconds)
        self._apply_replay_frame(self.replay_player.frame())
        return True
