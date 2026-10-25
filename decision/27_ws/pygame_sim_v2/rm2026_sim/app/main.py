"""Pygame UI for RMUC 2026 sentry motion verification."""

from __future__ import annotations

import math
import argparse
import json
from dataclasses import replace
from pathlib import Path

from ..core import Arena, SentryState, Viewport
from ..dataset_replay import (
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
from ..field_rules import (
    REGION_DEFINITIONS,
    REGION_TYPES,
    RUNE_POSITIONS,
    canonical_region_id,
)
from ..field_geometry import BLUE_BASE, BLUE_OUTPOST, FIELD_WIDTH
from ..map_asset import load_p5_pgm
from ..map_regions import (
    geometry_payload,
    wall_collision_polygons,
    traversable_tunnel_corridors,
    load_geometry_file,
    restore_extra_geometry_payload,
    restore_slow_regions_payload,
    load_patrol_routes_file,
    nearest_segment_index,
    normalize_points,
    restore_geometry_payload,
    restore_patrol_routes,
    save_geometry_file,
    validate_polygon,
)
from ..navigation import (
    ASTAR_PLANNING_RADIUS,
    ROBOT_ENTITY_COLLISION_RADIUS,
    AStarNavigator,
    OccupancyGrid,
)
from ..ros_bridge import BehaviorTreeBridgeClient
from ..scenario_store import (
    ScenarioStore,
    capture_snapshot,
    delete_snapshot,
    restore_snapshot,
)
from ..task_state import (
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
    OUTPOST_HIT_PROBABILITY,
    OUT_OF_COMBAT_SECONDS,
    PENDING_AMMO_CAP,
    RULE_FIRE_RATE_MAX,
    SUPPLY,
    ROBOT_PROFILES,
    RULE_BASE_HP,
    RULE_BASE_SHIELD,
    RULE_DAMAGE_17MM,
    RULE_DAMAGE_42MM,
    RULE_OUTPOST_HP,
    OUTPOST_REBUILD_SECONDS,
    HEAT_PERMANENT_EXTRA,
    DecisionView,
    FIELD_ENTITIES,
    OWN_FIELD_ENTITIES,
    TaskScenario,
)


APP_ROOT = Path(__file__).resolve().parents[2]
MAP_PATH = APP_ROOT / "assets" / "rmuc2026.pgm"
FIELD_LAYOUT_PATH = APP_ROOT / "assets" / "rmuc2026_field_layout.png"
SNAPSHOT_PATH = APP_ROOT / "scenario_saves.json"
MAP_GEOMETRY_PATH = APP_ROOT / "map_regions.json"
WINDOW_SIZE = (2240, 1260)
HEADER_HEIGHT = 112
SIDE_PANEL_WIDTH = 390
RIGHT_PANEL_WIDTH = 520
SNAPSHOT_BAR_HEIGHT = 62
AUTOAIM_HALF_VIEW = math.radians(24.0)
MAP_LAYER_PANEL_COLLAPSED_HEIGHT = 42
MAP_LAYER_PANEL_EXPANDED_HEIGHT = 206
MAP_EDITOR_VERTEX_RADIUS = 10
MAP_EDITOR_HIT_RADIUS = 16
DEFAULT_WALL_THICKNESS = 0.20
SPECIAL_WALL_TRAVERSE_SECONDS = 1.0
SPECIAL_WALL_TRAVERSAL_ROBOT_IDS = (2, 3, 4)
DEFAULT_SLOW_REGION_MULTIPLIER = 0.50
MAP_EXTRA_VISIBLE_ROWS = 8
MAP_REGION_VISIBLE_ROWS = 5

# These labels are also the stable order used by the bottom map-layer panel.
# Side-specific gain points intentionally have separate buttons so they can be
# annotated and shown independently.
FIELD_ZONE_KIND_LABELS = REGION_TYPES
MAP_OVERLAY_LABELS = (
    ("patrol_route", "巡逻路线"),
    ("energy_rune", "能量机关"),
    ("sensor_view", "传感器视野"),
    ("collision_volumes", "墙体/碰撞体"),
    ("editable_walls", "可编辑墙体"),
    ("special_regions", "特殊墙体"),
    ("slow_regions", "减速区域"),
    ("objectives", "目标点"),
    ("navigation", "导航路径"),
)
# The v1/C++ behaviour tree still sends this historical outpost goal.  v2 maps
# it to the configured opening attack point.
LEGACY_ATTACK_POINT = (17.0, 10.0)
LEGACY_AGGRESSIVE_PATROL_POINTS = (
    (12.0, 3.0),
    (16.0, 7.5),
    (12.3, 11.7),
)
LEGACY_GOAL_ALIASES = (
    (LEGACY_ATTACK_POINT, ATTACK),
    ((4.971, 7.5), HOME),
    ((2.0, 1.0), SUPPLY),
)

# Static collision is user-authored through the line-segment wall editor.
# This compatibility collection remains available for old integrations.
AERIAL_COLLISION_RADIUS = 0.26
STATIC_COLLISION_RECTANGLES: tuple[tuple[float, float, float, float], ...] = ()


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


# 通过 mixin 组合应用层职责；每个模块保持可单独阅读，避免主类再次膨胀。
from .runtime import RuntimeMixin
from .replay import ReplayMixin
from .simulation import SimulationMixin
from .interaction import InteractionMixin
from .controls import ControlsMixin
from .rendering import RenderingMixin


class SimulatorApp(
    ReplayMixin,
    RuntimeMixin,
    SimulationMixin,
    InteractionMixin,
    ControlsMixin,
    RenderingMixin,
):
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
        self.map_image = map_image
        self.map_surface = self.pg.image.load(str(FIELD_LAYOUT_PATH)).convert()
        # The field artwork/PGM is visual reference only. Collision starts as
        # an empty arena; users add every solid wall through the map editor.
        self.collision_grid = OccupancyGrid.empty(
            self.arena,
        ).with_blocked_rectangles(
            STATIC_COLLISION_RECTANGLES,
            inflation=ROBOT_ENTITY_COLLISION_RADIUS,
        )
        self.infantry_collision_grid = self.collision_grid
        self.aerial_collision_grid = OccupancyGrid.empty(
            self.arena,
            collision_radius=AERIAL_COLLISION_RADIUS,
        )
        self.special_wall_traverse_timers: dict[tuple[str, int, str], float] = {}
        self.special_wall_traverse_active: set[tuple[str, int, str]] = set()
        self.robot_chassis_dynamics: dict[tuple[str, int], SentryState] = {}
        self.special_wall_collision_polygons: tuple[
            tuple[str, tuple[tuple[float, float], ...]], ...
        ] = ()
        self.special_wall_individual_grids: dict[str, OccupancyGrid] = {}
        self.special_wall_only_grids: dict[str, OccupancyGrid] = {}
        self.los_grid = OccupancyGrid.empty(
            self.arena,
            collision_radius=0.0,
        ).with_blocked_rectangles(
            STATIC_COLLISION_RECTANGLES,
            inflation=0.0,
        )
        self.planning_grid = OccupancyGrid.empty(
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
        self.pending_fire_shooter: tuple[str, int] | None = None
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
        # Map-editor state. Existing rule regions keep their stable FIELD_ZONE
        # ids; an empty override means "deleted, awaiting replacement".
        self.map_zone_overrides = {
            canonical_region_id(name): normalize_points(points)
            for name, points in getattr(self.task, "field_zone_overrides", {}).items()
            if canonical_region_id(name) in {identifier for identifier, _ in REGION_TYPES}
        }
        self.custom_map_polygons: list[dict] = []
        self.wall_polygons: list[dict] = []
        self.special_regions: list[dict] = []
        self.slow_regions: list[dict] = []
        patrol_defaults = {
            "conservative": CONSERVATIVE_PATROL_POINTS,
            "aggressive": AGGRESSIVE_PATROL_POINTS,
        }
        self.patrol_routes = restore_patrol_routes({}, patrol_defaults)
        # Keep persistence path on the fully initialized app instance.  Tests
        # and lightweight helper objects created with ``__new__`` must never
        # fall back to the user's real map_regions.json file.
        self.map_geometry_path: Path | None = MAP_GEOMETRY_PATH
        self._persistent_geometry_loaded = self.map_geometry_path.is_file()
        if self._persistent_geometry_loaded:
            self.map_zone_overrides, self.custom_map_polygons = load_geometry_file(
                self.map_geometry_path
            )
            try:
                raw_geometry = json.loads(
                    self.map_geometry_path.read_text(encoding="utf-8")
                )
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                raw_geometry = {}
            self.wall_polygons, self.special_regions = restore_extra_geometry_payload(
                raw_geometry
            )
            self.slow_regions = restore_slow_regions_payload(raw_geometry)
            self.patrol_routes = load_patrol_routes_file(
                self.map_geometry_path,
                patrol_defaults,
            )
        else:
            # Migrate geometry from the newest scene once.  Future edits are
            # written to the independent map_regions.json file immediately.
            for snapshot in reversed(self.snapshots):
                raw_geometry = snapshot.get("map_geometry")
                if isinstance(raw_geometry, dict) and raw_geometry:
                    migrated_overrides, migrated_custom = restore_geometry_payload(
                        raw_geometry
                    )
                    migrated_walls, migrated_special = restore_extra_geometry_payload(
                        raw_geometry
                    )
                    migrated_slow = restore_slow_regions_payload(raw_geometry)
                    migrated_routes = restore_patrol_routes(
                        raw_geometry,
                        patrol_defaults,
                    )
                else:
                    task_data = snapshot.get("task") or {}
                    legacy_overrides = task_data.get("field_zone_overrides")
                    migrated_overrides, migrated_custom = restore_geometry_payload(
                        {"zone_overrides": legacy_overrides}
                    ) if legacy_overrides else ({}, [])
                    migrated_walls, migrated_special = [], []
                    migrated_slow = []
                    migrated_routes = restore_patrol_routes({}, patrol_defaults)
                if (
                    migrated_overrides
                    or migrated_custom
                    or migrated_walls
                    or migrated_special
                    or migrated_slow
                    or (
                        isinstance(raw_geometry, dict)
                        and bool(raw_geometry.get("patrol_routes"))
                    )
                ):
                    self.map_zone_overrides = migrated_overrides
                    self.custom_map_polygons = migrated_custom
                    self.wall_polygons = migrated_walls
                    self.special_regions = migrated_special
                    self.slow_regions = migrated_slow
                    self.patrol_routes = migrated_routes
                    try:
                        save_geometry_file(
                            self.map_geometry_path,
                            self.map_zone_overrides,
                            self.custom_map_polygons,
                            patrol_routes=self.patrol_routes,
                            wall_polygons=self.wall_polygons,
                            special_regions=self.special_regions,
                            slow_regions=self.slow_regions,
                        )
                        self._persistent_geometry_loaded = True
                    except OSError:
                        pass
                    break
        # Register every persisted sub-polygon as an independent visible
        # layer. A region family may contain one base polygon plus several
        # custom parts; none of those parts should disappear after startup.
        for item in self.custom_map_polygons:
            identifier = str(item.get("id"))
            visible = bool(item.get("visible", False))
            self.map_layer_visibility[f"custom:{identifier}"] = visible
            if visible:
                kind = canonical_region_id(
                    item.get("kind") or REGION_TYPES[0][0]
                )
                self.map_layer_visibility[f"zone:{kind}"] = True
        # The permanent map file is independent from scene snapshots.  Make
        # its polygons available to live rule evaluation immediately on every
        # startup, without requiring the user to edit or reload a scene first.
        self._sync_task_zone_overrides()
        self._sync_task_patrol_routes()
        self._rebuild_collision_grids()
        self._normalize_robot_positions()
        self._refresh_dynamic_planning_grid(force=True)
        self.region_edit_target: str | None = None
        self.region_edit_custom_id: str | None = None
        self.region_edit_kind: str | None = None
        self.region_edit_patrol_kind: str | None = None
        self.region_edit_new_custom = False
        self.region_edit_points: list[tuple[float, float]] = []
        self.region_edit_drag_index: int | None = None
        self.region_edit_error = ""
        self.region_edit_counter = 1
        self.region_edit_wall_id: str | None = None
        self.region_edit_special_id: str | None = None
        self.region_edit_slow_id: str | None = None
        self.region_edit_new_wall = False
        self.region_edit_new_special = False
        self.region_edit_new_slow = False
        self.map_editor_tab = "layers"
        self.map_extra_list_open = True
        self.map_extra_scroll_offsets = {"walls": 0, "special": 0, "slow": 0}
        self.map_extra_scroll_rect = None
        self.map_region_scroll_offset = 0
        self.map_region_scroll_rect = None
        # Keep the long patrol/region management list collapsed by default.
        # It can be opened independently from the main map-layer controls.
        self.map_region_editor_open = False
        # The long route/region list is opt-in so the map remains usable at
        # common window sizes. Wall and special-region tabs stay compact.
        self.map_region_editor_open = False
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

def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="RMUC 2026 Pygame SimulatorApp")
    parser.add_argument(
        "--dataset-replay",
        action="store_true",
        help="在 v2 裁判系统与可视化界面中加载 SQLite 比赛数据",
    )
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
        if not args.dataset_replay:
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
