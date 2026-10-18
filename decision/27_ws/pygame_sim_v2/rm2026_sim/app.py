"""Pygame UI for RMUC 2026 sentry motion verification."""

from __future__ import annotations

import math
import argparse
from dataclasses import replace
from pathlib import Path

from .core import Arena, SentryState, Viewport
from .dataset_replay import (
    DEFAULT_DATASET_PATH,
    DatasetError,
    DatasetRepository,
    DatasetReplay,
    dataset_local_entity_id,
    EconomicInference,
    ReplayEvent,
    ReplayFrame,
    ReplayPlayer,
    MatchRecord,
)
from .field_rules import FIELD_ZONES, RUNE_POSITIONS, zones_for_team
from .field_geometry import BLUE_BASE, BLUE_OUTPOST
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
    AMMO_CAP,
    ATTACK,
    ATTACK_RANGE,
    CONSERVATIVE_PATROL_POINTS,
    DETECTION_RANGE,
    FIRE_ALIGNMENT_TOLERANCE,
    HOME,
    LEVEL_EXP_THRESHOLDS,
    MATCH_DURATION,
    PENDING_AMMO_CAP,
    RULE_FIRE_RATE_MAX,
    SUPPLY,
    ROBOT_PROFILES,
    RULE_BASE_HP,
    RULE_BASE_SHIELD,
    RULE_DAMAGE_17MM,
    RULE_DAMAGE_42MM,
    RULE_OUTPOST_HP,
    HEAT_PERMANENT_EXTRA,
    DecisionView,
    FIELD_ENTITIES,
    OWN_FIELD_ENTITIES,
    TaskScenario,
)


APP_ROOT = Path(__file__).resolve().parent.parent
MAP_PATH = APP_ROOT / "assets" / "rmuc2026.pgm"
FIELD_LAYOUT_PATH = APP_ROOT / "assets" / "rmuc2026_field_layout.png"
SNAPSHOT_PATH = APP_ROOT / "scenario_saves.json"
WINDOW_SIZE = (2240, 1260)
HEADER_HEIGHT = 112
SIDE_PANEL_WIDTH = 390
RIGHT_PANEL_WIDTH = 520
SNAPSHOT_BAR_HEIGHT = 62
AUTOAIM_HALF_VIEW = math.radians(24.0)
MAP_LAYER_PANEL_COLLAPSED_HEIGHT = 42
MAP_LAYER_PANEL_EXPANDED_HEIGHT = 206

# These labels are also the stable order used by the bottom map-layer panel.
# Field zones are grouped by their rulebook type so one button controls both
# the red and blue copy of a region (for example, both roads).
FIELD_ZONE_KIND_LABELS = (
    ("supply", "补给区"),
    ("base_gain", "基地增益"),
    ("outpost_gain", "前哨增益"),
    ("central_highland", "中央高地"),
    ("trapezoid_highland", "梯形高地"),
    ("terrain_road", "公路"),
    ("terrain_highland", "高地跨越"),
    ("terrain_fly_slope", "飞坡"),
    ("terrain_tunnel", "隧道"),
    ("assembly", "装配区"),
    ("fort", "堡垒"),
)
MAP_OVERLAY_LABELS = (
    ("patrol_route", "巡逻路线"),
    ("energy_rune", "能量机关"),
    ("sensor_view", "传感器视野"),
    ("collision_volumes", "碰撞体"),
    ("objectives", "目标点"),
    ("navigation", "导航路径"),
)
# The v1/C++ behaviour tree still sends this pre-LOS outpost goal.  v2 maps it
# to the LOS-clear firing point so ROS-online mode does not stop behind a wall.
LEGACY_ATTACK_POINT = (17.0, 10.0)
LEGACY_GOAL_ALIASES = (
    (LEGACY_ATTACK_POINT, ATTACK),
    ((4.971, 7.5), HOME),
    ((2.0, 1.0), SUPPLY),
    ((12.0, 3.0), AGGRESSIVE_PATROL_POINTS[0]),
    ((16.0, 7.5), AGGRESSIVE_PATROL_POINTS[1]),
    ((12.3, 11.7), AGGRESSIVE_PATROL_POINTS[2]),
)

# Static 2-D collision footprints for the field buildings.  The PGM already
# contains the surrounding walls; these rectangles prevent a robot centre from
# entering the base/outpost structures themselves.
AERIAL_COLLISION_RADIUS = 0.26
STATIC_COLLISION_RECTANGLES = (
    (0.00, 6.40, 0.55, 8.60),    # red base edge
    (27.45, 6.40, 28.00, 8.60),  # blue base edge
    (7.95, 6.75, 9.45, 8.25),    # red outpost
    (18.55, 6.75, 20.05, 8.25),  # blue outpost
)


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
    def __init__(
        self,
        pygame_module,
        *,
        replay: DatasetReplay | None = None,
        replay_repository: DatasetRepository | None = None,
        replay_matches: tuple[MatchRecord, ...] = (),
        replay_index: int = 0,
    ) -> None:
        self.pg = pygame_module
        self.pg.init()
        self.pg.display.set_caption("RMUC 2026 二维哨兵验证 v2")
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
        self.map_surface = self.pg.image.load(str(FIELD_LAYOUT_PATH)).convert()
        self.collision_grid = OccupancyGrid.from_pgm(
            map_image,
            self.arena,
        ).with_blocked_rectangles(
            STATIC_COLLISION_RECTANGLES,
            inflation=ROBOT_ENTITY_COLLISION_RADIUS,
        )
        self.los_grid = OccupancyGrid.from_pgm(
            map_image,
            self.arena,
            collision_radius=0.0,
        )
        self.planning_grid = OccupancyGrid.from_pgm(
            map_image,
            self.arena,
            collision_radius=ASTAR_PLANNING_RADIUS,
        ).with_blocked_rectangles(
            STATIC_COLLISION_RECTANGLES,
            inflation=ASTAR_PLANNING_RADIUS,
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
        self._collision_damage_cooldown = 0.0
        # Map overlays are opt-in.  The map, grid, robots and sentry remain
        # visible; every optional region/route layer starts hidden and is
        # controlled from the bottom folded panel.
        self.map_layers_panel_open = False
        self.map_layer_visibility = {
            f"zone:{kind}": False for kind, _ in FIELD_ZONE_KIND_LABELS
        }
        self.map_layer_visibility.update(
            {name: False for name, _ in MAP_OVERLAY_LABELS}
        )
        # Keep the old attributes as compatibility aliases for callers that
        # inspect them directly.
        self.show_collision_volumes = False
        self.show_field_zones = False
        self.subsystem_panel_open = False
        # Replay state lives in the original SimulatorApp.  It never invokes
        # live movement/fire/update paths, and it never writes to SQLite.
        self.replay_mode = replay is not None
        self.replay_repository = replay_repository
        self.replay_matches = replay_matches
        self.replay_match_index = max(0, min(replay_index, len(replay_matches) - 1)) if replay_matches else 0
        self.replay_player = ReplayPlayer(replay) if replay is not None else None
        self.replay_inference = EconomicInference() if replay is not None else None
        self.replay_inference_cursor = -1e-6
        self.replay_last_time = 0.0
        self.replay_event_log: list[ReplayEvent] = []
        self.replay_economy_log = []
        self.replay_total_coins: dict[str, float | None] = {"red": None, "blue": None}
        self.replay_remaining_coins: dict[str, float | None] = {"red": None, "blue": None}
        self.replay_vulnerability: dict[tuple[str, int], bool] = {}
        self.replay_max_hp: dict[tuple[str, int], float] = {}
        self.replay_heat_limits: dict[tuple[str, int], float] = {}
        self.replay_sentry_heat_limit: float | None = None
        self.replay_sentry_vulnerable = False
        self.replay_last_frame: ReplayFrame | None = None
        self.replay_timeline_rect = None
        self.replay_timeline_dragging = False
        if self.replay_mode:
            self._apply_replay_frame(self.replay_player.frame())

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
                            if self.subsystem_panel_open:
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
                    elif event.type == self.pg.MOUSEBUTTONDOWN and event.button == 1:
                        handled = self._handle_replay_timeline(event.pos) if self.replay_mode else False
                        if not handled:
                            handled = self._handle_mouse_click(event.pos)
                        if not handled:
                            self._manual_fire_held = self.sentry.manual_control
                    elif event.type == self.pg.MOUSEBUTTONUP and event.button == 1:
                        self._manual_fire_held = False
                        if self.replay_mode:
                            self.replay_timeline_dragging = False
                    elif event.type == self.pg.MOUSEMOTION and self.replay_mode and self.replay_timeline_dragging:
                        self._handle_replay_timeline(event.pos)

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
                self._collision_damage_cooldown = max(
                    0.0,
                    self._collision_damage_cooldown - elapsed_seconds,
                )
                bridge_decision = self._bridge_decision()
                local_decision = self._local_decision()
                motion_decision = self._gate_gimbal_by_alignment(
                    bridge_decision or local_decision
                )
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
                shot = (
                    self.task.resolve_fire_shot(
                        self.sentry,
                        preferred_target=preferred_target,
                        line_of_sight=self._line_of_sight,
                    )
                    if fire_request
                    else None
                )
                self.hit_target_id = shot.target_id if shot is not None else None
                if not restarting and not self.sentry.manual_control and shot is None:
                    # Automatic fire must not consume ammo/heat while the
                    # target is behind cover or still outside alignment.
                    fire_request = False
                critical_zone = bool(
                    shot is not None and self.task.is_center_hit(shot)
                )
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
                    confirm_respawn=bool(motion_decision.confirm_respawn),
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
        return max(MAP_LAYER_PANEL_EXPANDED_HEIGHT, 58 + rows * 38)

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
            self.sentry.update(
                elapsed_seconds,
                move_x,
                move_y,
                self.arena,
                spin_enabled=decision.spin_mode > 0 and not power_cut,
                spin_speed_scale=self._spin_speed_scale(decision.spin_mode),
                turret_enabled=not self._manual_fire_held,
            )
            proposed = (self.sentry.x, self.sentry.y)
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
        if waypoint is not None and not power_cut:
            delta_x = waypoint[0] - self.sentry.x
            delta_y = waypoint[1] - self.sentry.y
            distance = math.hypot(delta_x, delta_y)
            if distance > 0.08:
                travel = min(distance, self.sentry.movement_speed * elapsed_seconds)
                proposed = self.arena.clamp(
                    self.sentry.x + delta_x / distance * travel,
                    self.sentry.y + delta_y / distance * travel,
                )
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
        self.sentry.update(
            elapsed_seconds,
            0.0,
            0.0,
            self.arena,
            spin_enabled=decision.spin_mode > 0 and not power_cut,
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
            robot_radius = (
                ROBOT_ENTITY_COLLISION_RADIUS
                if team == "sentry"
                else self._robot_collision_radius(team, target_id)
            )
            overlaps = any(
                math.hypot(position[0] - x, position[1] - y)
                < robot_radius + radius
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
            placed.append((*position, robot_radius))

    def _collision_entries(
        self, moving_team: str, moving_id: int
    ) -> list[tuple[int, str, float, float, float]]:
        if moving_team == "sentry":
            moving_team, moving_id = "red", 8
        entries: list[tuple[int, str, float, float, float]] = []
        for target_id in self.task.robot_positions:
            if moving_team == "blue" and target_id == moving_id:
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
        if not (moving_team == "red" and moving_id == 8):
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

    def _line_of_sight(
        self,
        start: tuple[float, float],
        end: tuple[float, float],
    ) -> bool:
        grid = getattr(self, "los_grid", None)
        if grid is None:
            return True
        return grid.line_of_sight(start, end)

    @staticmethod
    def _robot_collision_radius(team: str, target_id: int) -> float:
        if target_id == 5:
            return AERIAL_COLLISION_RADIUS
        return ROBOT_ENTITY_COLLISION_RADIUS

    def _dynamic_planning_bodies(self) -> tuple[tuple[float, float, float], ...]:
        bodies = [
            (
                x,
                y,
                self._robot_collision_radius("blue", target_id),
            )
            for target_id in self.task.robot_positions
            for x, y in (self.task.robot_position(target_id, team="blue"),)
        ]
        bodies.extend(
            (
                x,
                y,
                self._robot_collision_radius("red", target_id),
            )
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
        if getattr(self, "replay_mode", False):
            return
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
        robot_radius = self._robot_collision_radius(team, target_id)
        resolved = self.collision_grid.move_with_collision(
            start,
            proposed,
            collision_bodies=self._collision_bodies(team, target_id),
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
        if not self._line_of_sight((self.sentry.x, self.sentry.y), (target_x, target_y)):
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

    def _gate_gimbal_by_alignment(self, decision: DecisionView) -> DecisionView:
        """Keep the gimbal rotating until the barrel is inside firing tolerance.

        ``shoot_mode`` means "ready to fire", not merely "the decision selected
        this target".  Without this gate the outpost branch can stop the gimbal
        while the target is outside the 4-degree firing cone.  The same gate
        clears a fire request when the target is behind cover.
        """
        if decision.target <= 0:
            return decision
        error = self.task.aim_error(self.sentry, decision.target)
        if error is None:
            return decision
        try:
            target_position = self.task.target_position(decision.target)
        except ValueError:
            target_position = None
        if target_position is not None and not self._line_of_sight(
            (self.sentry.x, self.sentry.y), target_position
        ):
            return replace(decision, tripod_mode=1, shoot_mode=0)
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
            if distance <= DETECTION_RANGE and abs(relative_angle) <= AUTOAIM_HALF_VIEW:
                if not self._line_of_sight(
                    (self.sentry.x, self.sentry.y),
                    position,
                ):
                    continue
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

    def _toggle_map_layer(self, layer: str) -> None:
        """Toggle one map overlay and keep legacy flags in sync."""
        if layer not in self.map_layer_visibility:
            return
        visible = not self.map_layer_visibility[layer]
        self.map_layer_visibility[layer] = visible
        if layer == "collision_volumes":
            self.show_collision_volumes = visible
        if layer.startswith("zone:"):
            self.show_field_zones = any(
                self.map_layer_visibility.get(f"zone:{kind}", False)
                for kind, _ in FIELD_ZONE_KIND_LABELS
            )

    def _set_all_map_layers(self, visible: bool) -> None:
        for layer in self.map_layer_visibility:
            self.map_layer_visibility[layer] = visible
        self.show_collision_volumes = visible
        self.show_field_zones = visible

    def _toggle_all_field_zones(self) -> None:
        show_zones = not self.show_field_zones
        for kind, _ in FIELD_ZONE_KIND_LABELS:
            self.map_layer_visibility[f"zone:{kind}"] = show_zones
        self.show_field_zones = show_zones

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
            elif action == "toggle_revive_mode":
                self.task.toggle_revive_mode()
            elif action == "toggle_posture_reinforced":
                self.task.toggle_posture_reinforced()
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
            elif action == "show_all_map_layers":
                self._set_all_map_layers(True)
            elif action == "hide_all_map_layers":
                self._set_all_map_layers(False)
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
                self.task.cancel_assembly()
            elif action == "move_engineer_to_assembly":
                self.task.own_robot_positions[2] = [2.5, 4.0]
                self.task.notify("工程机器人已移到装配区")
            elif action == "cycle_dart_target":
                self.task.cycle_dart_target()
            elif action == "open_dart_gate":
                self.task.open_dart_gate()
            elif action == "fire_dart":
                self.task.fire_dart()
            elif action == "radar_mark":
                self.task.radar_mark(target_id, 10.0)
            elif action == "radar_double":
                self.task.trigger_radar_double()
            elif action == "activate_small_rune":
                self.task.activate_rune("small")
            elif action == "activate_large_rune":
                self.task.activate_rune("large")
            elif action == "hit_rune":
                self.task.hit_rune(self.sentry)
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
            elif action == "own_robot_exp":
                self.task.adjust_own_robot_experience(target_id, 100.0)
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
            "底盘功率",
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
            f"防御增益（有效 {self.task.effective_sentry_defence * 100:.0f}%）",
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
        mode = "规则书读条" if self.task.revive_mode == "rulebook" else "任务 5 秒"
        y = self._draw_key_value(x, y, "复活模式", mode, width)

        if self.task.death_elapsed is not None:
            if self.task.revive_mode == "rulebook":
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
                y = self._draw_progress_bar(
                    x,
                    y,
                    width,
                    "确认复活倒计时",
                    self.task.death_elapsed,
                    max(0.1, 5.0),
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

        gap = 8
        button_width = (width - gap) // 2
        button_height = 32
        actions = (
            (
                "远程 +100 弹 -150",
                "exchange_remote_ammo",
            ),
            (
                "补给 +10 弹 -10",
                "exchange_local_ammo",
            ),
            (
                f"远程回血 -{self.task.remote_heal_cost}",
                "exchange_remote_heal",
            ),
            (
                f"立即复活 -{self.task.instant_revive_cost}",
                "exchange_instant_revive",
            ),
        )
        for index, (label, action) in enumerate(actions):
            column = index % 2
            row = index // 2
            rect = self.pg.Rect(
                x + column * (button_width + gap),
                y + row * (button_height + 6),
                button_width,
                button_height,
            )
            self._draw_click_button(rect, label)
            self.click_regions.append((rect, action, 0, 0))
        y += 2 * (button_height + 6)

        mode_rect = self.pg.Rect(x, y, width, button_height)
        mode_text = (
            "切换为任务 5 秒复活"
            if self.task.revive_mode == "rulebook"
            else "切换为规则书读条复活"
        )
        self._draw_click_button(mode_rect, mode_text)
        self.click_regions.append((mode_rect, "toggle_revive_mode", 0, 0))
        y += button_height + 8

        posture_rect = self.pg.Rect(x, y, width, button_height)
        posture_text = (
            "退出强化姿态"
            if self.task.posture_reinforced
            else "进入强化姿态"
        )
        self._draw_click_button(posture_rect, posture_text)
        self.click_regions.append((posture_rect, "toggle_posture_reinforced", 0, 0))
        y += button_height + 6

        performance_actions = (
            (
                "英雄：近战优先"
                if self.task.hero_mode == "ranged"
                else "英雄：远程优先",
                "cycle_hero_mode",
            ),
            (
                "步兵：功率优先"
                if self.task.infantry_chassis_mode == "blood"
                else "步兵：血量优先",
                "cycle_infantry_chassis",
            ),
            (
                "发射：爆发优先"
                if self.task.infantry_launcher_mode == "cooling"
                else "发射：冷却优先",
                "cycle_infantry_launcher",
            ),
        )
        performance_width = (width - 2 * gap) // 3
        for index, (label, action) in enumerate(performance_actions):
            rect = self.pg.Rect(
                x + index * (performance_width + gap),
                y,
                performance_width,
                button_height,
            )
            self._draw_click_button(rect, label)
            self.click_regions.append((rect, action, 0, 0))
        return y + button_height + 14

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
            f"{round(self.task.own_base_shield)}/{RULE_BASE_SHIELD}",
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

        entries = [
            ("show_all_map_layers", "全部显示", True),
            ("hide_all_map_layers", "全部隐藏", False),
        ]
        entries.extend(
            ("toggle_map_layer", label, self.map_layer_visibility[f"zone:{kind}"])
            for kind, label in FIELD_ZONE_KIND_LABELS
        )
        entries.extend(
            ("toggle_map_layer", label, self.map_layer_visibility[name])
            for name, label in MAP_OVERLAY_LABELS
        )

        content_top = panel.top + 45
        gap = 6
        columns = max(2, min(8, panel.width // 150))
        button_width = (panel.width - 20 - gap * (columns - 1)) // columns
        button_height = 30
        for index, (action, label, active) in enumerate(entries):
            row, column = divmod(index, columns)
            rect = self.pg.Rect(
                panel.left + 10 + column * (button_width + gap),
                content_top + row * (button_height + 6),
                button_width,
                button_height,
            )
            if action == "toggle_map_layer":
                if index < 2 + len(FIELD_ZONE_KIND_LABELS):
                    target = (
                        f"zone:{FIELD_ZONE_KIND_LABELS[index - 2][0]}"
                        if index >= 2
                        else ""
                    )
                else:
                    target = MAP_OVERLAY_LABELS[index - 2 - len(FIELD_ZONE_KIND_LABELS)][0]
            else:
                target = 0
            hovered = rect.collidepoint(self.pg.mouse.get_pos())
            if action == "toggle_map_layer":
                background = (40, 117, 87) if active else (50, 58, 63)
                if hovered:
                    background = (54, 137, 103) if active else (75, 86, 92)
                self.pg.draw.rect(self.screen, background, rect)
                self.pg.draw.rect(self.screen, (104, 117, 123), rect, 1)
                button_label = f"{label}：{'开' if active else '关'}"
                rendered = self.panel_label_font.render(button_label, True, (236, 239, 240))
                self.screen.blit(rendered, rendered.get_rect(center=rect.center))
            else:
                self._draw_click_button(rect, label)
            self.click_regions.append((rect, action, target, 0))

    def _draw_subsystem_panel(self) -> None:
        if not self.subsystem_panel_open:
            return
        screen_width, screen_height = self.screen.get_size()
        panel_width = min(820, screen_width - 120)
        panel_height = min(640, screen_height - 160)
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
        y = self._draw_key_value(
            x,
            y,
            "装配状态",
            f"难度 {self.task.assembly_difficulty or '—'}｜{status}"
            f"｜等级上限 {self.task.level_cap}"
            f"｜每10秒 +{self.task.assembly_bonus_per_10s} 金",
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
        if radar_target not in (1, 3, 4, 5, 8):
            radar_target = 1
        progress = self.task.radar_marks.get(radar_target, 0.0)
        y = self._draw_key_value(
            x,
            y,
            "标记对象",
            f"{radar_target} 号｜P={progress:.0f}｜易伤 "
            f"{self.task.radar_vulnerability(radar_target) * 100:.0f}%"
            f"｜双倍 {self.task.radar_double_remaining:.0f}s"
            f"｜机会 {self.task.radar_double_charges}",
            panel.width - 48,
        )
        radar_actions = (
            ("标记 +10", "radar_mark"),
            ("双倍易伤", "radar_double"),
        )
        for index, (label, action) in enumerate(radar_actions):
            rect = self.pg.Rect(
                x + index * (action_width + 6),
                y,
                action_width,
                32,
            )
            self._draw_click_button(rect, label)
            self.click_regions.append((rect, action, radar_target, 0))
        y += 44
        self._draw_wrapped_status(
            x,
            y,
            panel.width - 48,
            "说明",
            "二维简化：装配用计时模拟科技核心步骤；飞镖用按钮模拟发射；"
            "雷达标记/双倍易伤用于验证属性计算，不改变行为树接口。",
        )

    def _engineer_in_assembly_zone(self) -> bool:
        from .field_rules import FIELD_ZONES

        zone = next((item for item in FIELD_ZONES if item.name == "red_assembly"), None)
        position = self.task.own_robot_position(2)
        return zone is not None and zone.contains(*position)

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
        popup_height = 840 if target_id in ROBOT_PROFILES else 350
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
            level = self.task.robot_level_value(target_id, team=team)
            configuration = {
                1: f"{level}级·{'近战' if self.task.hero_mode == 'melee' else '远程'}优先",
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
            health_label = (
                f"{round(health)}/{round(maximum)}"
                if target_id != 5
                else "不适用地面装甲扣血"
            )
            if target_id == 5:
                y = self._draw_key_value(x, y, "血量", health_label, popup.width - 28)
            else:
                y = self._draw_adjustable_progress_bar(
                    x, y, popup.width - 28, "血量", health, maximum,
                    (62, 184, 112) if team == "red" else (68, 133, 217),
                    target_id, compact=True,
                    action="own_robot_health" if team == "red" else "enemy_health",
                )
            y = self._draw_key_value(x, y, "弹丸", profile.projectile, popup.width - 28)
            y = self._draw_key_value(x, y, "初始允许发弹量", str(profile.initial_ammo), popup.width - 28)
            if self.replay_mode:
                shots_17, shots_42 = self._replay_shots(team, target_id)
                y = self._draw_key_value(
                    x, y, "累计17mm发弹（SQLite）", self._shot_text(shots_17), popup.width - 28
                )
                y = self._draw_key_value(
                    x, y, "累计42mm发弹（SQLite）", self._shot_text(shots_42), popup.width - 28
                )
            y = self._draw_key_value(x, y, "射击初速度上限", self._format_rule_value(profile.muzzle_speed_limit, "m/s"), popup.width - 28)
            power_limit = self._format_rule_value(profile.power_limit, "W")
            heat_capacity = (
                self.replay_heat_limits.get((team, target_id), profile.heat_capacity)
                if self.replay_mode
                else profile.heat_capacity
            )
            heat_limit = self._format_rule_value(heat_capacity, "")
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
            heat_value = "不适用" if heat_capacity is None else f"{current_heat:.1f} / {heat_limit}"
            y = self._draw_key_value(x, y, "当前热量", heat_value, popup.width - 28)
            y = self._draw_key_value(x, y, "射击热量上限", heat_limit, popup.width - 28)
            y = self._draw_key_value(x, y, "热量冷却", self._format_rule_value(profile.heat_cooling_per_second, "/秒"), popup.width - 28)
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
        if not self.replay_mode and target_id in ROBOT_PROFILES and (team == "red" or target_id != 5):
            drive = self.pg.Rect(x, button_y, 86, 30)
            self._draw_click_button(drive, "驾驶")
            action = "control_own_robot" if team == "red" else "control_enemy_robot"
            self.click_regions.append((drive, action, target_id, 0))
            if team == "red" and target_id in (1, 3, 4, 5):
                exp_button = self.pg.Rect(x + 92, button_y, 100, 30)
                self._draw_click_button(exp_button, "经验 +100")
                self.click_regions.append((exp_button, "own_robot_exp", target_id, 0))
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
        try:
            target_position = self.task.target_position(self.decision.target)
        except ValueError:
            target_position = None
        vision = ""
        if target_position is not None:
            vision = (
                "｜视线通"
                if self._line_of_sight(
                    (self.sentry.x, self.sentry.y), target_position
                )
                else "｜视线遮挡"
            )
        return f"｜误差 {math.degrees(error):.1f}°{vision}"

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

    def _draw_supply_zone(self, viewport: Viewport) -> None:
        zone = next(item for item in FIELD_ZONES if item.name == "red_supply")
        points = [
            tuple(round(value) for value in viewport.world_to_screen(x, y))
            for x, y in zone.polygon
        ]
        overlay = self.pg.Surface(self.screen.get_size(), self.pg.SRCALPHA)
        self.pg.draw.polygon(overlay, (*zone.color, 58), points)
        self.screen.blit(overlay, (0, 0))
        self.pg.draw.polygon(self.screen, zone.color, points, 2)

        bounds = self.pg.Rect(
            min(point[0] for point in points),
            min(point[1] for point in points),
            max(point[0] for point in points) - min(point[0] for point in points),
            max(point[1] for point in points) - min(point[1] for point in points),
        )
        label = self.small_font.render("补给区", True, (20, 112, 62))
        label_background = label.get_rect(
            midtop=(bounds.centerx, bounds.top + 4)
        ).inflate(8, 4)
        self.pg.draw.rect(self.screen, (231, 247, 237), label_background)
        self.screen.blit(label, label.get_rect(midtop=(bounds.centerx, bounds.top + 6)))

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
        for zone in FIELD_ZONES:
            if zone.kind not in visible_kinds:
                continue
            if zone.polygon:
                points = [
                    tuple(round(value) for value in viewport.world_to_screen(x, y))
                    for x, y in zone.polygon
                ]
                left = min(point[0] for point in points)
                top = min(point[1] for point in points)
                right = max(point[0] for point in points)
                bottom = max(point[1] for point in points)
                rect = self.pg.Rect(left, top, max(1, right - left), max(1, bottom - top))
                self.pg.draw.polygon(overlay, (*zone.color, 28), points)
            else:
                left, top = viewport.world_to_screen(zone.min_x, zone.max_y)
                right, bottom = viewport.world_to_screen(zone.max_x, zone.min_y)
                rect = self.pg.Rect(
                    round(left),
                    round(top),
                    max(1, round(right - left)),
                    max(1, round(bottom - top)),
                )
                points = []
                self.pg.draw.rect(overlay, (*zone.color, 28), rect)
            regions.append((zone, rect, points))
        self.screen.blit(overlay, (0, 0))
        for zone, rect, points in regions:
            if points:
                self.pg.draw.polygon(self.screen, zone.color, points, 1)
            else:
                self.pg.draw.rect(self.screen, zone.color, rect, 1)
            if zone.label:
                label = self.small_font.render(zone.label, True, zone.color)
                if points:
                    self.screen.blit(
                        label,
                        label.get_rect(midbottom=(rect.centerx, rect.top - 2)),
                    )
                elif label.get_width() < rect.width + 20:
                    self.screen.blit(
                        label,
                        (rect.centerx - label.get_width() // 2, rect.top + 2),
                    )

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

def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="RMUC 2026 Pygame SimulatorApp")
    parser.add_argument("--replay", action="store_true", help="在原 SimulatorApp 中开启 SQLite 回放")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET_PATH)
    parser.add_argument("--game-id", type=int)
    parser.add_argument("--region")
    parser.add_argument("--school")
    parser.add_argument("--max-frames", type=int)
    parser.add_argument("--screenshot", type=Path)
    args = parser.parse_args(argv)
    try:
        import pygame
    except ModuleNotFoundError as error:
        raise SystemExit(
            "尚未安装 Pygame，请执行：python -m pip install -r requirements.txt"
        ) from error
    repository = None
    try:
        if not args.replay:
            SimulatorApp(pygame).run(
                max_frames=args.max_frames,
                screenshot_path=args.screenshot,
            )
            return
        repository = DatasetRepository(args.dataset)
        matches = repository.list_matches(region=args.region, school=args.school)
        if not matches:
            raise DatasetError("No matches matched the requested filters")
        match_index = 0
        if args.game_id is not None:
            matching = [index for index, match in enumerate(matches) if match.game_id == args.game_id]
            if not matching:
                raise DatasetError(f"game_id {args.game_id} is not in the filtered match list")
            match_index = matching[0]
        replay = repository.load_replay(matches[match_index].game_id)
        SimulatorApp(
            pygame,
            replay=replay,
            replay_repository=repository,
            replay_matches=matches,
            replay_index=match_index,
        ).run(max_frames=args.max_frames, screenshot_path=args.screenshot)
    except KeyboardInterrupt:
        pass
    except (DatasetError, OSError) as error:
        raise SystemExit(str(error)) from error
    finally:
        if repository is not None:
            repository.close()
