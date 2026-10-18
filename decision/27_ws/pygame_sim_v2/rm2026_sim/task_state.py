"""Task-one referee inputs and expected high-level decision outputs."""

from __future__ import annotations

from dataclasses import dataclass, field
import math
import random
from collections.abc import Callable

from .core import Arena, SentryState
from .field_rules import (
    FIELD_ZONES,
    FieldZone,
    LARGE_RUNE_ACTIVATION_WINDOW,
    RUNE_POSITIONS,
    ROAD_CARD_HALF_EXTENT,
    ROAD_CROSSING_CARDS,
    ROAD_CROSSING_WINDOW,
    SMALL_RUNE_ACTIVATION_WINDOW,
    SMALL_RUNE_DEFENCE,
    SMALL_RUNE_DURATION,
    large_rune_profile,
    rune_distance_to,
    zones_for_team,
)
from .field_geometry import (
    AGGRESSIVE_PATROL_POINTS,
    BLUE_BASE,
    BLUE_OUTPOST,
    BLUE_START_POSITIONS,
    CONSERVATIVE_PATROL_POINTS,
    OUTPOST_ATTACK_POINT,
    RED_BASE,
    RED_HOME,
    RED_OUTPOST,
    RED_START_POSITIONS,
    RED_SUPPLY_POINT,
    RED_SUPPLY_ZONE,
)


HOME = RED_HOME
SUPPLY = RED_SUPPLY_POINT
ATTACK = OUTPOST_ATTACK_POINT
MATCH_DURATION = 420.0
DETECTION_RANGE = 6.2
ATTACK_RANGE = 4.0
WEAPON_RANGE = ATTACK_RANGE
FIRE_ALIGNMENT_TOLERANCE = math.radians(4.0)
RULE_FIRE_RATE_MAX = 20
# Rulebook V2.2.0, table 5-2. Raw damage before attack/defence buffs.
RULE_DAMAGE_17MM = 20
RULE_DAMAGE_42MM = 200
RULE_COLLISION_DAMAGE = 2
# Compatibility alias for callers that display the sentry's 17mm base value.
RULE_DAMAGE_PER_SHOT = RULE_DAMAGE_17MM
RULE_BASE_SHIELD = 150
RULE_OUTPOST_HP = 1500
RULE_BASE_HP = 5000
DAMAGE_BURST_THRESHOLD = 30.0
DAMAGE_BURST_WINDOW = 1.0
EVADE_DURATION = 5.0
EVADE_DIRECTION_PERIOD = 0.7
EVADE_OFFSETS = (
    (1.10, 0.35),
    (-0.55, 1.05),
    (0.80, -0.95),
    (-1.15, -0.30),
    (0.25, 1.20),
    (0.95, -0.55),
    (-0.85, 0.65),
)
SUPPLY_ZONE = RED_SUPPLY_ZONE
PATROL_POINTS = CONSERVATIVE_PATROL_POINTS

# v2 rule-fidelity constants.  The task-one sheet keeps the sentry in "task"
# mode (5 s confirm, 400 HP); the other values follow rulebook V2.2.0.
RESPAWN_CONFIRM_SECONDS = 5.0
OUT_OF_COMBAT_SECONDS = 6.0
SUPPLY_HEAL_BASE_FRACTION = 0.10
SUPPLY_HEAL_LATE_FRACTION = 0.25
SUPPLY_LATE_MATCH_ELAPSED = 240.0
PENDING_AMMO_CAP = 1000
AMMO_CAP = 1000
ECONOMY_INITIAL = 400
ECONOMY_CAP = 1000
# Rulebook table 5-5: 06:59 initial 400, 05:59..01:59 +50, 00:59 +150.
ECONOMY_TICKS = (
    (61.0, 50),
    (121.0, 50),
    (181.0, 50),
    (241.0, 50),
    (301.0, 50),
    (361.0, 150),
)
HEAT_PERMANENT_EXTRA = 100
BUFFER_ENERGY_CAP = 60.0
CHASSIS_POWER_CUT_SECONDS = 5.0
CRITICAL_HALF_WIDTH = 0.005
POSTURE_SWITCH_COOLDOWN = 5.0
POSTURE_REINFORCED_SECONDS = 15.0
POSTURE_DECAY_SECONDS = 180.0

# Economy exchanges (rulebook table 5-6 / 5.3.2).
LOCAL_17MM_COST = 10
LOCAL_17MM_AMOUNT = 10
REMOTE_17MM_COST = 150
REMOTE_17MM_AMOUNT = 100
AMMO_EXCHANGE_CAP_17MM = 1000
REMOTE_EXCHANGE_DELAY = 6.0
REMOTE_HEAL_DELAY = 6.0
REMOTE_HEAL_FRACTION = 0.60

# Respawn (rulebook 5.2.2).  The task-one sheet still uses the old 5 s /
# 400 HP mode; rulebook mode is selectable from the pygame panel.
RULEBOOK_REVIVE_HP_FRACTION = 0.10
RULEBOOK_REVIVE_INVINCIBLE = 30.0
RULEBOOK_REVIVE_WEAK_INVINCIBLE_MIN = 10.0
RULEBOOK_REVIVE_RATE = 1.0
RULEBOOK_REVIVE_SUPPLY_RATE = 4.0
RULEBOOK_REVIVE_BASE = 10.0
INSTANT_REVIVE_INVINCIBLE = 3.0
INSTANT_REVIVE_POWER_BOOST = 4.0

# Level tables (rulebook 5.4).  Sentry and engineer do not use levels.
LEVEL_EXP_THRESHOLDS = (0, 550, 1100, 1650, 2200, 2750, 3300, 3850, 4400, 5000)
HERO_HP_RANGED = (200, 220, 240, 260, 280, 300, 320, 340, 360, 400)
HERO_HP_MELEE = (260, 300, 330, 360, 400, 430, 460, 500, 530, 600)
INFANTRY_HP_BLOOD = (200, 225, 250, 275, 300, 325, 350, 375, 400, 400)
INFANTRY_HP_POWER = (150, 175, 200, 225, 250, 275, 300, 325, 350, 400)
AERIAL_HP = 100


@dataclass(frozen=True)
class FieldEntity:
    name: str
    x: float
    y: float
    team: str
    kind: str
    target_id: int = 0
    hp: int = 0
    max_hp: int = 0


@dataclass(frozen=True)
class RobotProfile:
    """Basic referee attributes from rulebook sections 3 and 5.4."""

    role: str
    max_hp: int
    projectile: str
    initial_ammo: int
    muzzle_speed_limit: float | None
    chassis_power_limit: int | None
    heat_limit: int | None
    heat_cooling_per_second: int | None
    raw_projectile_damage: int | None
    collision_damage: int | None
    collision_applies: bool
    decision_controlled: bool
    # Mechanical equipment.  A turntable is the rotating chassis platform;
    # the gimbal is the independently aimed weapon/camera platform.
    has_gimbal: bool = False
    has_turntable: bool = False
    heat_per_shot: int | None = None

    @property
    def power_limit(self) -> int | None:
        """Rulebook-facing alias used by the UI and integrations."""
        return self.chassis_power_limit

    @property
    def heat_capacity(self) -> int | None:
        """Rulebook-facing alias for the firing heat limit."""
        return self.heat_limit

    @property
    def gimbal_enabled(self) -> bool:
        return self.has_gimbal

    @property
    def small_turntable_enabled(self) -> bool:
        return self.has_turntable


# Default level/performance choices used when a team does not select another
# configuration: hero remote-priority, infantry blood-priority chassis plus
# cooling-priority launcher, and automatic sentry.
ROBOT_PROFILES = {
    1: RobotProfile("英雄", 200, "42mm", 0, 12.0, 50, 160, 20, RULE_DAMAGE_42MM, RULE_COLLISION_DAMAGE, True, False, True, True, 100),
    2: RobotProfile("工程", 250, "无", 0, None, 120, None, None, None, RULE_COLLISION_DAMAGE, True, False, False, True, None),
    3: RobotProfile("步兵", 200, "17mm", 0, 25.0, 45, 40, 12, RULE_DAMAGE_17MM, RULE_COLLISION_DAMAGE, True, False, True, True, 10),
    4: RobotProfile("步兵", 200, "17mm", 0, 25.0, 45, 40, 12, RULE_DAMAGE_17MM, RULE_COLLISION_DAMAGE, True, False, True, True, 10),
    5: RobotProfile("空中", 100, "17mm", 750, 25.0, None, 100, 20, RULE_DAMAGE_17MM, None, False, False, True, False, 10),
    8: RobotProfile("自动哨兵", 400, "17mm", 300, 25.0, 100, 260, 30, RULE_DAMAGE_17MM, RULE_COLLISION_DAMAGE, True, True, True, True, 10),
}


# Building positions follow the 28 x 15 dataset frame.  Robot positions are
# the median t<=2 s start positions from the three regional dataset slices.
FIELD_ENTITIES = (
    FieldEntity("RED BASE", *RED_BASE, "red", "base", hp=5000, max_hp=5000),
    FieldEntity("RED OUTPOST", *RED_OUTPOST, "red", "outpost", hp=RULE_OUTPOST_HP, max_hp=RULE_OUTPOST_HP),
    FieldEntity("BLUE OUTPOST", *BLUE_OUTPOST, "blue", "outpost", 6, RULE_OUTPOST_HP, RULE_OUTPOST_HP),
    FieldEntity("BLUE BASE", *BLUE_BASE, "blue", "base", 7, RULE_BASE_HP, RULE_BASE_HP),
    FieldEntity("HERO", *BLUE_START_POSITIONS[1], "blue", "robot", 1, ROBOT_PROFILES[1].max_hp, ROBOT_PROFILES[1].max_hp),
    FieldEntity("ENGINEER", *BLUE_START_POSITIONS[2], "blue", "robot", 2, ROBOT_PROFILES[2].max_hp, ROBOT_PROFILES[2].max_hp),
    FieldEntity("INFANTRY 3", *BLUE_START_POSITIONS[3], "blue", "robot", 3, ROBOT_PROFILES[3].max_hp, ROBOT_PROFILES[3].max_hp),
    FieldEntity("INFANTRY 4", *BLUE_START_POSITIONS[4], "blue", "robot", 4, ROBOT_PROFILES[4].max_hp, ROBOT_PROFILES[4].max_hp),
    FieldEntity("AERIAL", *BLUE_START_POSITIONS[5], "blue", "robot", 5, ROBOT_PROFILES[5].max_hp, ROBOT_PROFILES[5].max_hp),
    FieldEntity("SENTRY", *BLUE_START_POSITIONS[8], "blue", "robot", 8, ROBOT_PROFILES[8].max_hp, ROBOT_PROFILES[8].max_hp),
)

# Friendly spawn points are simulation defaults on traversable map cells.
# Robot 8 uses the existing SentryState rather than a duplicate robot state.
OWN_FIELD_ENTITIES = (
    FieldEntity("RED HERO", *RED_START_POSITIONS[1], "red", "robot", 1, ROBOT_PROFILES[1].max_hp, ROBOT_PROFILES[1].max_hp),
    FieldEntity("RED ENGINEER", *RED_START_POSITIONS[2], "red", "robot", 2, ROBOT_PROFILES[2].max_hp, ROBOT_PROFILES[2].max_hp),
    FieldEntity("RED INFANTRY 3", *RED_START_POSITIONS[3], "red", "robot", 3, ROBOT_PROFILES[3].max_hp, ROBOT_PROFILES[3].max_hp),
    FieldEntity("RED INFANTRY 4", *RED_START_POSITIONS[4], "red", "robot", 4, ROBOT_PROFILES[4].max_hp, ROBOT_PROFILES[4].max_hp),
    FieldEntity("RED AERIAL", *RED_START_POSITIONS[5], "red", "robot", 5, ROBOT_PROFILES[5].max_hp, ROBOT_PROFILES[5].max_hp),
    FieldEntity("RED SENTRY", *RED_START_POSITIONS[8], "red", "robot", 8, ROBOT_PROFILES[8].max_hp, ROBOT_PROFILES[8].max_hp),
)
def _initial_robot_positions() -> dict[int, list[float]]:
    return {
        entity.target_id: [entity.x, entity.y]
        for entity in FIELD_ENTITIES
        if entity.kind == "robot"
    }


def _initial_robot_health() -> dict[int, float]:
    return {
        entity.target_id: float(entity.hp)
        for entity in FIELD_ENTITIES
        if entity.kind == "robot"
    }


def _initial_robot_ammo() -> dict[int, int]:
    return {
        target_id: profile.initial_ammo
        for target_id, profile in ROBOT_PROFILES.items()
    }


def _initial_own_robot_positions() -> dict[int, list[float]]:
    return {
        entity.target_id: [entity.x, entity.y]
        for entity in OWN_FIELD_ENTITIES
        if entity.kind == "robot" and entity.target_id != 8
    }


def _initial_own_robot_health() -> dict[int, float]:
    return {
        entity.target_id: float(entity.hp)
        for entity in OWN_FIELD_ENTITIES
        if entity.kind == "robot" and entity.target_id != 8
    }


def _initial_own_robot_ammo() -> dict[int, int]:
    return {
        target_id: profile.initial_ammo
        for target_id, profile in ROBOT_PROFILES.items()
        if target_id != 8
    }


def _initial_robot_heat() -> dict[int, float]:
    return {target_id: 0.0 for target_id in ROBOT_PROFILES}


def _initial_robot_power() -> dict[int, float]:
    return {target_id: 0.0 for target_id in ROBOT_PROFILES}


def _initial_robot_shots() -> dict[int, int | None]:
    # Dataset telemetry is nullable: NULL means the weapon is not applicable
    # or was not recorded, and must not be rendered as zero shots.
    return {target_id: None for target_id in ROBOT_PROFILES}


@dataclass
class ActiveBuff:
    source: str
    kind: str
    value: float
    remaining: float
    duration: float


@dataclass(frozen=True)
class FireSolution:
    """A live shot solution used by the 2-D rendering/validation layer."""

    target_id: int
    distance: float
    angle_error: float


@dataclass(frozen=True)
class DecisionView:
    behavior: str
    posture: int
    goal: tuple[float, float] | None
    spin_mode: int
    tripod_mode: int
    shoot_mode: int
    target: int
    confirm_respawn: int
    health_threshold: int


@dataclass
class TaskScenario:
    game_running: bool = True
    game_finished: bool = False
    game_paused: bool = False
    remaining_time: float = MATCH_DURATION
    sentry_hp: float = 400.0
    defence_buff: int = 60
    ammo: int = ROBOT_PROFILES[8].initial_ammo
    pending_ammo: int = 0
    economy: int = ECONOMY_INITIAL
    fire_rate: int = RULE_FIRE_RATE_MAX
    # Retained for old scenario files and referee-panel compatibility.  The
    # live damage path intentionally ignores this debug value and uses the
    # projectile/armor rule tables below.
    damage_per_shot: int = RULE_DAMAGE_PER_SHOT
    own_outpost_hp: int = RULE_OUTPOST_HP
    own_base_hp: int = RULE_BASE_HP
    own_base_shield: float = RULE_BASE_SHIELD
    enemy_outpost_hp: float = RULE_OUTPOST_HP
    enemy_base_hp: float = RULE_BASE_HP
    enemy_base_shield: float = RULE_BASE_SHIELD
    respawn_fire_locked: bool = False
    death_elapsed: float | None = None
    dodge_remaining: float = 0.0
    dodge_goal: tuple[float, float] | None = None
    aggressive_patrol: bool = False
    patrol_index: int = 0
    event_message: str = "比赛进行中"
    event_message_remaining: float = 3.0
    robot_positions: dict[int, list[float]] = field(default_factory=_initial_robot_positions)
    robot_hp: dict[int, float] = field(default_factory=_initial_robot_health)
    robot_ammo: dict[int, int] = field(default_factory=_initial_robot_ammo)
    # These friendly non-sentry robots are deliberately not read by evaluate(),
    # resolve_fire_target(), or the ROS bridge. They belong to the 2-D scene
    # UI/collision layer only.
    own_robot_positions: dict[int, list[float]] = field(
        default_factory=_initial_own_robot_positions
    )
    own_robot_hp: dict[int, float] = field(default_factory=_initial_own_robot_health)
    own_robot_ammo: dict[int, int] = field(default_factory=_initial_own_robot_ammo)
    # Live referee-style resource telemetry.  The dictionaries include every
    # profile id so a snapshot can be restored without special casing roles.
    robot_heat: dict[int, float] = field(default_factory=_initial_robot_heat)
    own_robot_heat: dict[int, float] = field(default_factory=_initial_robot_heat)
    robot_power: dict[int, float] = field(default_factory=_initial_robot_power)
    own_robot_power: dict[int, float] = field(default_factory=_initial_robot_power)
    # Read-only cumulative dataset telemetry.  These are deliberately separate
    # from ``robot_ammo``/``ammo`` which retain live remaining-ammunition
    # semantics used by the simulator and rulebook controls.
    robot_shots_17mm: dict[int, int | None] = field(default_factory=_initial_robot_shots)
    robot_shots_42mm: dict[int, int | None] = field(default_factory=_initial_robot_shots)
    own_robot_shots_17mm: dict[int, int | None] = field(default_factory=_initial_robot_shots)
    own_robot_shots_42mm: dict[int, int | None] = field(default_factory=_initial_robot_shots)
    # v2 live rule telemetry.  Out-of-combat is measured on the sentry; the
    # same value is used for friendly ground-robot supply healing.
    sentry_out_of_combat_seconds: float = OUT_OF_COMBAT_SECONDS
    sentry_buffer_energy: float = BUFFER_ENERGY_CAP
    sentry_chassis_power_cut_remaining: float = 0.0
    sentry_heat_locked: bool = False
    sentry_heat_permanent_lock: bool = False
    active_posture: int = 3
    posture_cooldown_remaining: float = 0.0
    posture_time: dict[int, float] = field(
        default_factory=lambda: {1: 0.0, 2: 0.0, 3: 0.0}
    )
    reinforced_time: dict[int, float] = field(
        default_factory=lambda: {1: 0.0, 2: 0.0, 3: 0.0}
    )
    posture_reinforced: bool = False
    # v2 economy/respawn additions.
    revive_mode: str = "task"
    revive_required: float = 0.0
    revive_progress: float = 0.0
    instant_revive_count: int = 0
    invincible_remaining: float = 0.0
    weak_state: bool = False
    instant_revive_power_boost_remaining: float = 0.0
    remote_heal_remaining: float | None = None
    remote_ammo_pending: int = 0
    remote_ammo_remaining: float | None = None
    exchanged_17mm: int = 0
    # Level / experience / performance selection.
    robot_level: dict[int, int] = field(
        default_factory=lambda: {1: 1, 2: 1, 3: 1, 4: 1, 5: 1, 8: 1}
    )
    own_robot_level: dict[int, int] = field(
        default_factory=lambda: {1: 1, 2: 1, 3: 1, 4: 1, 5: 1}
    )
    robot_exp: dict[int, float] = field(
        default_factory=lambda: {1: 0.0, 2: 0.0, 3: 0.0, 4: 0.0, 5: 0.0, 8: 0.0}
    )
    own_robot_exp: dict[int, float] = field(
        default_factory=lambda: {1: 0.0, 2: 0.0, 3: 0.0, 4: 0.0, 5: 0.0}
    )
    hero_mode: str = "ranged"
    infantry_chassis_mode: str = "blood"
    infantry_launcher_mode: str = "cooling"
    # Field gain points / energy rune.
    active_buffs: list[ActiveBuff] = field(default_factory=list)
    zone_inside: set[str] = field(default_factory=set)
    zone_cooldowns: dict[str, float] = field(default_factory=dict)
    road_crossing_side: str | None = None
    road_crossing_elapsed: float = 0.0
    _last_field_position: list[float] | None = None
    rune_state: str = "inactive"
    rune_kind: str = "small"
    rune_timer: float = 0.0
    rune_hits: int = 0
    rune_arm_count: int = 5
    rune_ring_average: float = 1.0
    rune_active_plates: list[int] = field(default_factory=list)
    # Engineering assembly / tech core (2-D simplified).
    assembly_difficulty: int = 0
    assembly_active: bool = False
    assembly_progress: float = 0.0
    assembly_required: float = 0.0
    assembly_completed: set[int] = field(default_factory=set)
    assembly_bonus_per_10s: int = 0
    assembly_bonus_accumulator: float = 0.0
    assembly_defence: float = 0.0
    level_cap: int = 5
    own_base_max_hp: int = RULE_BASE_HP
    # Dart system.
    darts_remaining: int = 4
    dart_gate_windows: int = 2
    dart_gate_state: str = "closed"
    dart_gate_timer: float = 0.0
    dart_fire_window: float = 0.0
    dart_detection_window: float = 0.0
    dart_target_type: str = "fixed"
    dart_in_flight: float | None = None
    dart_cooldown: float = 0.0
    dart_hits: int = 0
    enemy_base_armor_deployed: bool = False
    # Radar marking.
    radar_marks: dict[int, float] = field(
        default_factory=lambda: {target: 0.0 for target in (1, 3, 4, 5, 8, 6, 7)}
    )
    radar_double_remaining: float = 0.0
    radar_double_charges: int = 0
    # Match result bookkeeping (rulebook 5.8).
    winner_team: str | None = None
    end_reason: str = ""
    own_team_damage: float = 0.0
    enemy_team_damage: float = 0.0
    own_outpost_destroyed_ever: bool = False
    enemy_outpost_destroyed_ever: bool = False
    _last_minute: int = 7
    _economy_tick: int = 0
    _ammo_shot_accumulator: float = field(default=0.0, repr=False)
    _health_recovery_active: bool = field(default=False, repr=False)
    _dodge_phase: int = field(default=-1, repr=False)
    _unseen_damage_accumulator: float = field(default=0.0, repr=False)
    _unseen_damage_window_remaining: float = field(default=0.0, repr=False)

    @property
    def health_threshold(self) -> int:
        return 160 if self.defence_buff >= 60 else 200

    @property
    def match_elapsed(self) -> float:
        return max(0.0, MATCH_DURATION - self.remaining_time)

    @property
    def result_label(self) -> str:
        if self.winner_team == "red":
            return "己方获胜"
        if self.winner_team == "blue":
            return "敌方获胜"
        if self.winner_team == "draw":
            return "平局"
        return "进行中"

    @property
    def posture_mode(self) -> str:
        if (
            self.posture_reinforced
            and self.reinforced_time.get(self.active_posture, 0.0)
            < POSTURE_REINFORCED_SECONDS
        ):
            return "reinforced"
        if self.posture_time.get(self.active_posture, 0.0) >= POSTURE_DECAY_SECONDS:
            return "decayed"
        return "default"

    @property
    def posture_effects(self) -> tuple[float, float, float, float]:
        """Return (defence bonus, vulnerability, heat multiplier, power multiplier)."""
        mode = self.posture_mode
        if self.active_posture == 1:
            if mode == "reinforced":
                return 0.0, 0.25, 3.0, 0.5
            if mode == "decayed":
                return 0.0, 0.25, 2.0, 0.5
            return 0.0, 0.25, 3.0, 0.5
        if self.active_posture == 2:
            if mode == "reinforced":
                return 0.99, 0.0, 1.0 / 3.0, 0.5
            if mode == "decayed":
                return 0.25, 0.0, 1.0 / 3.0, 0.5
            return 0.50, 0.0, 1.0 / 3.0, 0.5
        if mode == "reinforced":
            return 0.0, 0.25, 1.0 / 3.0, 2.0
        if mode == "decayed":
            return 0.0, 0.25, 1.0 / 3.0, 1.2
        return 0.0, 0.25, 1.0 / 3.0, 1.5

    @property
    def posture_heat_gain_multiplier(self) -> float:
        if self.active_posture == 1 and self.posture_mode == "reinforced":
            return 0.0
        return 1.0

    def buff_value(self, kind: str) -> float:
        values = [
            buff.value for buff in self.active_buffs if buff.kind == kind
        ]
        return max(values) if values else 0.0

    @property
    def effective_attack_buff(self) -> float:
        return max(1.0, self.buff_value("attack"))

    @property
    def effective_sentry_defence(self) -> float:
        bonus, vulnerability, _, _ = self.posture_effects
        defence = max(
            self.defence_buff / 100.0,
            self.buff_value("defence"),
            self.assembly_defence,
            bonus,
        )
        weakness = max(self.buff_value("vulnerability"), vulnerability)
        return max(-1.0, min(0.99, defence - weakness))

    @property
    def effective_sentry_heat_cooling(self) -> float:
        _, _, multiplier, _ = self.posture_effects
        cooling_buff = max(1.0, self.buff_value("heat_cooling"))
        return (
            float(ROBOT_PROFILES[8].heat_cooling_per_second or 0)
            * multiplier
            * cooling_buff
        )

    @property
    def effective_buffer_cap(self) -> float:
        return BUFFER_ENERGY_CAP + max(0.0, self.buff_value("buffer_energy"))

    @property
    def effective_sentry_power_limit(self) -> float:
        _, _, _, multiplier = self.posture_effects
        base = float(ROBOT_PROFILES[8].power_limit or 0)
        limit = min(200.0, base * multiplier)
        if self.instant_revive_power_boost_remaining > 0.0:
            limit = min(200.0, limit * 2.0)
        return limit

    @property
    def sentry_invincible(self) -> bool:
        return self.invincible_remaining > 0.0

    @property
    def remote_heal_cost(self) -> int:
        return 50 + math.ceil((MATCH_DURATION - self.remaining_time) / 60.0) * 20

    @property
    def instant_revive_cost(self) -> int:
        return math.ceil((MATCH_DURATION - self.remaining_time) / 60.0) * 80 + 20

    @property
    def revive_seconds_required(self) -> float:
        return (
            RULEBOOK_REVIVE_BASE
            + (MATCH_DURATION - self.remaining_time) / 10.0
            + 20.0 * self.instant_revive_count
        )

    @property
    def sentry_chassis_power_cut(self) -> bool:
        return self.sentry_chassis_power_cut_remaining > 0.0

    @property
    def sentry_fire_locked(self) -> bool:
        return self.sentry_heat_locked or self.sentry_heat_permanent_lock

    @property
    def resources_low_for_patrol(self) -> bool:
        return self.sentry_hp < 150.0 and self.economy < 400.0

    @property
    def patrol_is_aggressive(self) -> bool:
        return not self.resources_low_for_patrol

    @property
    def patrol_name(self) -> str:
        return "激进巡逻" if self.patrol_is_aggressive else "保守巡逻"

    @property
    def patrol_points(self) -> tuple[tuple[float, float], ...]:
        return AGGRESSIVE_PATROL_POINTS if self.patrol_is_aggressive else CONSERVATIVE_PATROL_POINTS

    def reset(self) -> None:
        fresh = type(self)()
        self.__dict__.update(fresh.__dict__)

    def move_robot(
        self,
        target_id: int,
        move_x: float,
        move_y: float,
        elapsed_seconds: float,
        arena: Arena,
        speed: float = 3.0,
        *,
        team: str = "blue",
    ) -> None:
        if team not in ("red", "blue"):
            raise ValueError(f"unknown team {team}")
        positions = self.robot_positions if team == "blue" else self.own_robot_positions
        allowed = (1, 2, 3, 4, 8) if team == "blue" else (1, 2, 3, 4, 5)
        if target_id not in allowed or target_id not in positions:
            raise ValueError(f"target {target_id} is not a controllable robot")
        if elapsed_seconds < 0.0:
            raise ValueError("elapsed_seconds must be non-negative")
        length = math.hypot(move_x, move_y)
        if length > 1.0:
            move_x /= length
            move_y /= length
        position = positions[target_id]
        position[0], position[1] = arena.clamp(
            position[0] + move_x * speed * elapsed_seconds,
            position[1] + move_y * speed * elapsed_seconds,
        )

    def robot_position(self, target_id: int, *, team: str = "blue") -> tuple[float, float]:
        if team not in ("red", "blue"):
            raise ValueError(f"unknown team {team}")
        positions = self.robot_positions if team == "blue" else self.own_robot_positions
        position = positions[target_id]
        return position[0], position[1]

    def set_robot_position(
        self, target_id: int, position: tuple[float, float], *, team: str = "blue"
    ) -> None:
        if team not in ("red", "blue"):
            raise ValueError(f"unknown team {team}")
        positions = self.robot_positions if team == "blue" else self.own_robot_positions
        if target_id not in positions:
            raise ValueError(f"unknown {team} robot {target_id}")
        positions[target_id] = [float(position[0]), float(position[1])]

    def own_robot_position(
        self, target_id: int, sentry: SentryState | None = None
    ) -> tuple[float, float]:
        if target_id == 8:
            if sentry is None:
                return HOME
            return sentry.x, sentry.y
        return self.robot_position(target_id, team="red")

    def own_robot_health(self, target_id: int) -> float:
        if target_id == 8:
            return float(self.sentry_hp)
        return float(self.own_robot_hp[target_id])

    def adjust_own_robot_health(self, target_id: int, direction: int) -> None:
        self._validate_adjustment_direction(direction)
        entity = next(
            (item for item in OWN_FIELD_ENTITIES if item.target_id == target_id),
            None,
        )
        if entity is None:
            raise ValueError(f"unknown own robot {target_id}")
        if target_id == 8:
            # The sentry has additional respawn/recovery bookkeeping and must
            # continue through adjust_sentry_health instead of this dictionary.
            raise ValueError("sentry health must use adjust_sentry_health")
        step = max(10.0, entity.max_hp / 10.0)
        self.own_robot_hp[target_id] = max(
            0.0,
            min(float(entity.max_hp), self.own_robot_hp[target_id] + step * direction),
        )
        self._set_event(
            f"己方 {target_id} 号机器人血量已调整为 {round(self.own_robot_hp[target_id])}"
        )

    def own_robot_ammunition(self, target_id: int) -> int:
        return self.ammo if target_id == 8 else self.own_robot_ammo[target_id]

    def robot_heat_value(
        self,
        target_id: int,
        *,
        team: str = "blue",
        sentry: SentryState | None = None,
    ) -> float:
        """Return current firing heat for a robot, or zero when inapplicable."""
        if target_id not in ROBOT_PROFILES:
            raise ValueError(f"unknown robot {target_id}")
        if target_id == 8 and team == "red":
            return float(sentry.heat) if sentry is not None else 0.0
        return (self.robot_heat if team == "blue" else self.own_robot_heat)[target_id]

    def robot_power_value(
        self,
        target_id: int,
        *,
        team: str = "blue",
        sentry: SentryState | None = None,
    ) -> float:
        """Return current chassis power draw for a robot."""
        if target_id not in ROBOT_PROFILES:
            raise ValueError(f"unknown robot {target_id}")
        if target_id == 8 and team == "red":
            return float(sentry.chassis_power) if sentry is not None else 0.0
        return (self.robot_power if team == "blue" else self.own_robot_power)[target_id]

    def robot_resource_limits(self, target_id: int) -> tuple[int | None, int | None]:
        if target_id not in ROBOT_PROFILES:
            raise ValueError(f"unknown robot {target_id}")
        profile = ROBOT_PROFILES[target_id]
        return profile.heat_capacity, profile.power_limit

    def robot_level_value(self, target_id: int, *, team: str = "blue") -> int:
        levels = self.robot_level if team == "blue" else self.own_robot_level
        return levels.get(target_id, 1)

    def robot_experience_value(self, target_id: int, *, team: str = "blue") -> float:
        exp = self.robot_exp if team == "blue" else self.own_robot_exp
        return exp.get(target_id, 0.0)

    def _level_hp(self, target_id: int, level: int) -> float:
        level = max(1, min(10, level))
        if target_id == 1:
            table = HERO_HP_MELEE if self.hero_mode == "melee" else HERO_HP_RANGED
            return float(table[level - 1])
        if target_id in (3, 4):
            table = (
                INFANTRY_HP_POWER
                if self.infantry_chassis_mode == "power"
                else INFANTRY_HP_BLOOD
            )
            return float(table[level - 1])
        if target_id == 5:
            return float(AERIAL_HP)
        return float(ROBOT_PROFILES[target_id].max_hp)

    def robot_max_hp(self, target_id: int, *, team: str = "blue") -> float:
        return self._level_hp(target_id, self.robot_level_value(target_id, team=team))

    def award_experience(
        self,
        target_id: int,
        amount: float,
        *,
        team: str = "blue",
    ) -> int:
        """Award level experience; return the number of levels gained."""
        if target_id not in (1, 3, 4, 5) or amount <= 0.0:
            return 0
        levels = self.robot_level if team == "blue" else self.own_robot_level
        exp = self.robot_exp if team == "blue" else self.own_robot_exp
        hp = self.robot_hp if team == "blue" else self.own_robot_hp
        old_level = levels.get(target_id, 1)
        levels[target_id] = old_level
        exp[target_id] = exp.get(target_id, 0.0) + amount
        while (
            levels[target_id] < self.level_cap
            and exp[target_id] >= LEVEL_EXP_THRESHOLDS[levels[target_id]]
        ):
            levels[target_id] += 1
        gained = levels[target_id] - old_level
        if gained:
            old_max = self._level_hp(target_id, old_level)
            new_max = self._level_hp(target_id, levels[target_id])
            hp[target_id] = hp.get(target_id, new_max) + (new_max - old_max)
            self._set_event(
                f"{'己方' if team == 'red' else '蓝方'} {target_id} 号升到 "
                f"{levels[target_id]} 级，血量上限 {new_max:.0f}"
            )
        return gained

    def adjust_own_robot_experience(self, target_id: int, amount: float) -> None:
        if target_id not in self.own_robot_level:
            raise ValueError(f"unknown own robot {target_id}")
        self.award_experience(target_id, amount, team="red")
        self._set_event(
            f"己方 {target_id} 号经验 "
            f"{self.own_robot_exp[target_id]:.0f}，等级 "
            f"{self.own_robot_level[target_id]}"
        )

    def _apply_max_hp_delta(self, target_ids: tuple[int, ...], delta: float) -> None:
        if delta == 0.0:
            return
        for target_id in target_ids:
            for hp_map in (self.robot_hp, self.own_robot_hp):
                if target_id in hp_map and hp_map[target_id] > 0.0:
                    hp_map[target_id] = max(0.0, hp_map[target_id] + delta)

    def cycle_hero_mode(self) -> None:
        old = {
            team: self.robot_max_hp(1, team=team) for team in ("blue", "red")
        }
        self.hero_mode = "melee" if self.hero_mode == "ranged" else "ranged"
        new = {team: self.robot_max_hp(1, team=team) for team in ("blue", "red")}
        self._apply_max_hp_delta((1,), new["blue"] - old["blue"])
        self._set_event(
            f"英雄整机：{'近战优先' if self.hero_mode == 'melee' else '远程优先'}"
        )

    def cycle_infantry_chassis(self) -> None:
        old = {
            team: self.robot_max_hp(3, team=team) for team in ("blue", "red")
        }
        self.infantry_chassis_mode = (
            "power" if self.infantry_chassis_mode == "blood" else "blood"
        )
        new = {team: self.robot_max_hp(3, team=team) for team in ("blue", "red")}
        self._apply_max_hp_delta((3, 4), new["blue"] - old["blue"])
        self._set_event(
            "步兵底盘："
            + ("功率优先" if self.infantry_chassis_mode == "power" else "血量优先")
        )

    def cycle_infantry_launcher(self) -> None:
        self.infantry_launcher_mode = (
            "burst" if self.infantry_launcher_mode == "cooling" else "cooling"
        )
        self._set_event(
            "步兵发射机构："
            + ("爆发优先" if self.infantry_launcher_mode == "burst" else "冷却优先")
        )

    def robot_ammunition(self, target_id: int, *, team: str = "blue") -> int:
        if target_id == 8 and team == "red":
            return self.ammo
        if team == "blue":
            return self.robot_ammo[target_id]
        return self.own_robot_ammo[target_id]

    def own_robot_ammunition_limit(self, target_id: int) -> int:
        if target_id not in ROBOT_PROFILES:
            raise ValueError(f"unknown robot {target_id}")
        if target_id == 2:
            return 0
        if target_id == 5:
            return ROBOT_PROFILES[5].initial_ammo
        # The UI limit is a scenario-injection bound, not a claim about the
        # match's remote-exchange economy cap.
        return 1000

    def adjust_own_robot_ammunition(self, target_id: int, direction: int) -> None:
        self._validate_adjustment_direction(direction)
        maximum = self.own_robot_ammunition_limit(target_id)
        step = 20 if target_id != 5 else 25
        if target_id == 8:
            self.adjust_ammo(direction)
            return
        self.own_robot_ammo[target_id] = max(
            0,
            min(maximum, self.own_robot_ammo[target_id] + step * direction),
        )
        self._set_event(
            f"己方 {target_id} 号机器人弹量已调整为 {self.own_robot_ammo[target_id]}"
        )

    def target_position(self, target_id: int) -> tuple[float, float]:
        if target_id in self.robot_positions:
            return self.robot_position(target_id)
        entity = next(
            (
                item
                for item in FIELD_ENTITIES
                if item.team == "blue" and item.target_id == target_id
            ),
            None,
        )
        if entity is None:
            raise ValueError(f"target {target_id} is not an enemy unit")
        return entity.x, entity.y

    def aim_error(self, sentry: SentryState, target_id: int) -> float | None:
        """Return the absolute turret-to-target angular error in radians."""
        try:
            target_x, target_y = self.target_position(target_id)
        except ValueError:
            return None
        target_angle = math.atan2(target_y - sentry.y, target_x - sentry.x)
        return abs(
            (target_angle - sentry.turret_angle + math.pi) % math.tau - math.pi
        )

    def resolve_fire_shot(
        self,
        sentry: SentryState,
        preferred_target: int = 0,
        *,
        maximum_distance: float = WEAPON_RANGE,
        alignment_tolerance: float = FIRE_ALIGNMENT_TOLERANCE,
        line_of_sight: "Callable[[tuple[float, float], tuple[float, float]], bool] | None" = None,
    ) -> FireSolution | None:
        """Return the best aligned target and its shot geometry.

        ``line_of_sight`` is injected by the 2-D layer so the pure scenario
        model stays independent of the occupancy map.
        """
        if maximum_distance <= 0.0 or alignment_tolerance < 0.0:
            raise ValueError("fire geometry limits must be non-negative")

        candidates = (
            (preferred_target,)
            if preferred_target
            else tuple(item.target_id for item in FIELD_ENTITIES if item.team == "blue")
        )
        aligned: list[tuple[float, float, int]] = []
        for target_id in candidates:
            try:
                health = self.enemy_health(target_id)
                target_x, target_y = self.target_position(target_id)
            except ValueError:
                continue
            if health <= 0.0 or health == 1001.0:
                continue
            delta_x = target_x - sentry.x
            delta_y = target_y - sentry.y
            distance = math.hypot(delta_x, delta_y)
            if distance > maximum_distance:
                continue
            target_angle = math.atan2(delta_y, delta_x)
            angle_error = abs(
                (target_angle - sentry.turret_angle + math.pi) % math.tau - math.pi
            )
            if angle_error > alignment_tolerance:
                continue
            if line_of_sight is not None and not line_of_sight(
                (sentry.x, sentry.y), (target_x, target_y)
            ):
                continue
            aligned.append((angle_error, distance, target_id))
        if not aligned:
            return None
        angle_error, distance, target_id = min(aligned)
        return FireSolution(target_id, distance, angle_error)

    def resolve_fire_target(
        self,
        sentry: SentryState,
        preferred_target: int = 0,
        *,
        maximum_distance: float = WEAPON_RANGE,
        alignment_tolerance: float = FIRE_ALIGNMENT_TOLERANCE,
        line_of_sight: "Callable[[tuple[float, float], tuple[float, float]], bool] | None" = None,
    ) -> int | None:
        """Return the unit actually intersected by the simulated gun barrel."""
        shot = self.resolve_fire_shot(
            sentry,
            preferred_target,
            maximum_distance=maximum_distance,
            alignment_tolerance=alignment_tolerance,
            line_of_sight=line_of_sight,
        )
        return shot.target_id if shot is not None else None

    @staticmethod
    def is_center_hit(shot: FireSolution) -> bool:
        """2-D approximation of the 10 mm x 10 mm building critical zone."""
        if shot.target_id not in (6, 7):
            return False
        lateral_offset = shot.distance * math.tan(shot.angle_error)
        return abs(lateral_offset) <= CRITICAL_HALF_WIDTH

    @staticmethod
    def armor_zone_for_shot(
        shot: FireSolution,
        sentry: SentryState,
        *,
        team: str = "blue",
    ) -> str | None:
        """Return the 2-D armour zone used by the live damage path."""
        if shot.target_id == 6:
            return "normal"
        if shot.target_id != 7:
            return None
        base_x = 27.0 if team == "blue" else 1.0
        front_direction = -1.0 if team == "blue" else 1.0
        # A base's upper-front armour faces the field.  Side/rear hits use the
        # remaining five plates and therefore the normal 17mm raw damage.
        in_front = front_direction * (sentry.x - base_x) > 0.0
        return "upper_front" if in_front else "normal"

    def toggle_patrol_mode(self) -> None:
        if self.patrol_is_aggressive:
            self.sentry_hp = min(self.sentry_hp, 125.0)
            self.economy = 350
        else:
            # Return above both possible recovery thresholds so a manual
            # patrol-mode toggle demonstrates aggressive patrol instead of
            # remaining in recovery.
            self.sentry_hp = max(self.sentry_hp, 200.0)
            self.economy = 400
        self.patrol_index = 0
        self._set_event(f"已按资源边界切换为{self.patrol_name}")

    def reset_match_time(self) -> None:
        self.reset()
        self._set_event("比赛时间及全场状态已全部复位")

    def toggle_pause(self) -> None:
        self.game_paused = not self.game_paused
        self._set_event("比赛已暂停" if self.game_paused else "比赛继续")

    def notify(self, message: str) -> None:
        self._set_event(message)

    def adjust_match_time(self, direction: int, step: float = 10.0) -> None:
        if direction not in (-1, 1):
            raise ValueError("direction must be -1 or 1")
        if step <= 0.0:
            raise ValueError("step must be positive")
        self.remaining_time = max(
            0.0,
            min(MATCH_DURATION, self.remaining_time + step * direction),
        )
        self._last_minute = math.ceil(self.remaining_time / 60.0)
        self._set_event(f"比赛时间已调整为 {round(self.remaining_time)} 秒")
        if self.remaining_time <= 0.0 and self.game_running:
            self.finish_game("比赛时间结束")

    def enemy_health(self, target_id: int) -> float:
        if target_id == 6:
            return self.enemy_outpost_hp
        if target_id == 7:
            return self.enemy_base_hp
        if target_id in self.robot_hp:
            return self.robot_hp[target_id]
        raise ValueError(f"target {target_id} is not an enemy unit")

    def adjust_enemy_health(self, target_id: int, direction: int) -> None:
        if direction not in (-1, 1):
            raise ValueError("direction must be -1 or 1")
        entity = next(
            (
                item
                for item in FIELD_ENTITIES
                if item.team == "blue" and item.target_id == target_id
            ),
            None,
        )
        if entity is None:
            raise ValueError(f"target {target_id} is not an enemy unit")

        step = 500.0 if target_id == 7 else 100.0 if target_id == 6 else max(10.0, entity.max_hp / 10.0)
        health = max(0.0, min(float(entity.max_hp), self.enemy_health(target_id) + step * direction))
        if target_id == 6:
            self.enemy_outpost_hp = health
            if health <= 0.0:
                self.enemy_outpost_destroyed_ever = True
            name = "敌方前哨"
        elif target_id == 7:
            self.enemy_base_hp = health
            name = "敌方基地"
        else:
            self.robot_hp[target_id] = health
            name = f"敌方 {target_id} 号机器人"
        self._set_event(f"{name}血量已调整为 {round(health)}")

    def adjust_sentry_health(
        self,
        direction: int,
        sentry: SentryState | None = None,
        *,
        unseen_damage: bool = False,
    ) -> None:
        if direction not in (-1, 1):
            raise ValueError("direction must be -1 or 1")
        previous_health = self.sentry_hp
        self.sentry_hp = max(0.0, min(400.0, self.sentry_hp + 25.0 * direction))
        if self.sentry_hp == 0.0 and previous_health > 0.0:
            self._mark_sentry_death()
        elif self.sentry_hp > 0.0:
            self.death_elapsed = None
        damage = previous_health - self.sentry_hp
        if damage > 0.0:
            self.sentry_out_of_combat_seconds = 0.0
        if damage > 0.0 and unseen_damage and sentry is not None:
            if self._unseen_damage_window_remaining <= 0.0:
                self._unseen_damage_accumulator = 0.0
            self._unseen_damage_accumulator += damage
            self._unseen_damage_window_remaining = DAMAGE_BURST_WINDOW
            if self._unseen_damage_accumulator >= DAMAGE_BURST_THRESHOLD:
                accumulated = self._unseen_damage_accumulator
                self._unseen_damage_accumulator = 0.0
                self._unseen_damage_window_remaining = 0.0
                self._start_unseen_damage_evasion(sentry, accumulated)
                return
            self._set_event(
                f"己方哨兵血量 {round(self.sentry_hp)}，"
                f"视野外伤害累计 {round(self._unseen_damage_accumulator)}/30"
            )
            return
        if damage > 0.0:
            self._unseen_damage_accumulator = 0.0
            self._unseen_damage_window_remaining = 0.0
        self._set_event(f"己方哨兵血量已调整为 {round(self.sentry_hp)}")

    def adjust_ammo(self, direction: int) -> None:
        self._validate_adjustment_direction(direction)
        self.ammo = max(0, min(AMMO_CAP, self.ammo + 20 * direction))
        self._set_event(f"当前弹量已调整为 {self.ammo}")

    def adjust_pending_ammo(self, direction: int) -> None:
        self._validate_adjustment_direction(direction)
        self.pending_ammo = max(0, min(PENDING_AMMO_CAP, self.pending_ammo + 25 * direction))
        self._set_event(f"待领弹药已调整为 {self.pending_ammo}")

    def adjust_economy(self, direction: int) -> None:
        self._validate_adjustment_direction(direction)
        self.economy = max(0, min(ECONOMY_CAP, self.economy + 50 * direction))
        self.patrol_index = 0
        self._set_event(f"经济已调整为 {self.economy}")

    def adjust_fire_rate(self, direction: int) -> None:
        self._validate_adjustment_direction(direction)
        self.fire_rate = max(1, min(RULE_FIRE_RATE_MAX, self.fire_rate + direction))
        self._set_event(f"射速已调整为 {self.fire_rate} 发/秒")

    def adjust_damage_per_shot(self, direction: int) -> None:
        """Adjust the legacy display/debug value without changing rule damage."""
        self._validate_adjustment_direction(direction)
        self.damage_per_shot = max(
            1, min(RULE_DAMAGE_PER_SHOT, self.damage_per_shot + direction)
        )
        self._set_event(
            f"调试单发值已调整为 {self.damage_per_shot}（实际按规则弹种计算）"
        )

    def adjust_defence_buff(self, direction: int) -> None:
        self._validate_adjustment_direction(direction)
        self.defence_buff = max(0, min(100, self.defence_buff + 10 * direction))
        self._set_event(f"防御增益已调整为 {self.defence_buff}%")

    def toggle_revive_mode(self) -> None:
        self.revive_mode = "rulebook" if self.revive_mode == "task" else "task"
        self._set_event(
            "复活模式：规则书读条"
            if self.revive_mode == "rulebook"
            else "复活模式：任务 5 秒确认"
        )

    def exchange_17mm(
        self,
        *,
        remote: bool,
        sentry: SentryState | None = None,
    ) -> bool:
        """Exchange sentry 17mm ammunition using rulebook table 5-6."""
        if remote:
            if self.sentry_out_of_combat_seconds < OUT_OF_COMBAT_SECONDS:
                self._set_event("远程兑换需要先脱战 6 秒")
                return False
            cost = REMOTE_17MM_COST
            amount = REMOTE_17MM_AMOUNT
        else:
            if sentry is None or not in_supply_zone(sentry.x, sentry.y):
                self._set_event("非远程兑换需要在补给区")
                return False
            cost = LOCAL_17MM_COST
            amount = LOCAL_17MM_AMOUNT
        if self.economy < cost:
            self._set_event(f"金币不足：需要 {cost}")
            return False
        if self.exchanged_17mm + amount > AMMO_EXCHANGE_CAP_17MM:
            self._set_event("已达到 17mm 兑换上限")
            return False
        self.economy -= cost
        self.exchanged_17mm += amount
        if remote:
            self.remote_ammo_pending += amount
            self.remote_ammo_remaining = REMOTE_EXCHANGE_DELAY
            self._set_event(f"远程兑换 {amount} 发，6 秒后生效，金币 -{cost}")
        else:
            space = max(0, AMMO_CAP - self.ammo)
            transferred = min(space, amount)
            self.ammo += transferred
            self.pending_ammo += amount - transferred
            self._set_event(f"补给区兑换 {amount} 发，金币 -{cost}")
        return True

    def exchange_remote_heal(self) -> bool:
        if self.sentry_hp <= 0.0:
            self._set_event("哨兵已阵亡，无法远程回血")
            return False
        if self.sentry_out_of_combat_seconds < OUT_OF_COMBAT_SECONDS:
            self._set_event("远程回血需要先脱战 6 秒")
            return False
        if self.remote_heal_remaining is not None:
            self._set_event("远程回血已在等待生效")
            return False
        cost = self.remote_heal_cost
        if self.economy < cost:
            self._set_event(f"金币不足：远程回血需要 {cost}")
            return False
        self.economy -= cost
        self.remote_heal_remaining = REMOTE_HEAL_DELAY
        self._set_event(f"远程回血已购买，6 秒后生效，金币 -{cost}")
        return True

    def exchange_instant_revive(self) -> bool:
        if self.sentry_hp > 0.0:
            self._set_event("哨兵存活，无需立即复活")
            return False
        cost = self.instant_revive_cost
        if self.economy < cost:
            self._set_event(f"金币不足：立即复活需要 {cost}")
            return False
        self.economy -= cost
        self.instant_revive_count += 1
        self.sentry_hp = 400.0
        self.death_elapsed = None
        self.revive_progress = 0.0
        self.revive_required = 0.0
        self.invincible_remaining = INSTANT_REVIVE_INVINCIBLE
        self.weak_state = True
        self.instant_revive_power_boost_remaining = INSTANT_REVIVE_POWER_BOOST
        self.respawn_fire_locked = True
        self.sentry_heat_locked = self.sentry_heat_permanent_lock
        self.sentry_buffer_energy = self.effective_buffer_cap
        self._set_event(f"立即复活，金币 -{cost}")
        return True

    def adjust_own_outpost_health(self, direction: int) -> None:
        self._validate_adjustment_direction(direction)
        self.own_outpost_hp = max(
            0,
            min(RULE_OUTPOST_HP, self.own_outpost_hp + 100 * direction),
        )
        if self.own_outpost_hp <= 0:
            self.own_outpost_destroyed_ever = True
        self._set_event(f"己方前哨血量已调整为 {self.own_outpost_hp}")

    def adjust_own_base_health(self, direction: int) -> None:
        self._validate_adjustment_direction(direction)
        self.own_base_hp = max(0, min(self.own_base_max_hp, self.own_base_hp + 500 * direction))
        self._set_event(f"己方基地血量已调整为 {self.own_base_hp}")

    @staticmethod
    def _validate_adjustment_direction(direction: int) -> None:
        if direction not in (-1, 1):
            raise ValueError("direction must be -1 or 1")

    def update(
        self,
        elapsed_seconds: float,
        sentry: SentryState,
        decision_override: DecisionView | None = None,
        *,
        fire_request: bool | None = None,
        hit_target_id: int | None = None,
        attack_buff: float = 1.0,
        target_defence_buff: float = 0.0,
        critical_zone: bool = False,
        target_armor_zone: str | None = None,
        confirm_respawn: bool | None = None,
    ) -> DecisionView:
        if elapsed_seconds < 0.0:
            raise ValueError("elapsed_seconds must be non-negative")
        self.pending_ammo = max(0, min(PENDING_AMMO_CAP, self.pending_ammo))
        self._finish_if_base_destroyed()
        simulation_elapsed = 0.0 if self.game_paused else elapsed_seconds

        self.sentry_out_of_combat_seconds = min(
            OUT_OF_COMBAT_SECONDS,
            self.sentry_out_of_combat_seconds + simulation_elapsed,
        )
        sentry.heat = max(
            0.0,
            sentry.heat - self.effective_sentry_heat_cooling * simulation_elapsed,
        )
        if (
            sentry.heat <= 0.0
            and self.sentry_heat_locked
            and not self.sentry_heat_permanent_lock
        ):
            self.sentry_heat_locked = False
            self._set_event("热量已冷却，发射机构解锁")

        # Keep resource telemetry useful even for robots that are only shown
        # in the two-dimensional referee view.  Their power draw is supplied
        # by a future controller; heat still cools according to each profile.
        if simulation_elapsed > 0.0:
            for target_id, profile in ROBOT_PROFILES.items():
                decay = max(0.0, 1.0 - simulation_elapsed * 5.0)
                self.robot_power[target_id] *= decay
                self.own_robot_power[target_id] *= decay
                if profile.heat_limit is None:
                    continue
                cooling = float(profile.heat_cooling_per_second or 0)
                self.robot_heat[target_id] = max(
                    0.0, self.robot_heat[target_id] - cooling * simulation_elapsed
                )
                self.own_robot_heat[target_id] = max(
                    0.0, self.own_robot_heat[target_id] - cooling * simulation_elapsed
                )
        self._unseen_damage_window_remaining = max(
            0.0,
            self._unseen_damage_window_remaining - elapsed_seconds,
        )
        if self._unseen_damage_window_remaining <= 0.0:
            self._unseen_damage_accumulator = 0.0
        self.event_message_remaining = max(
            0.0,
            self.event_message_remaining - simulation_elapsed,
        )

        if self.game_running:
            self.remaining_time = max(0.0, self.remaining_time - simulation_elapsed)
            self._update_economy()
            current_minute = math.ceil(self.remaining_time / 60.0)
            if current_minute < self._last_minute:
                self.pending_ammo = min(
                    PENDING_AMMO_CAP,
                    self.pending_ammo + 100 * (self._last_minute - current_minute),
                )
                self._last_minute = current_minute
            if self.remaining_time <= 0.0:
                self.finish_game("比赛时间结束")

        if confirm_respawn is None:
            provisional = decision_override or self.evaluate(sentry)
            confirm_respawn = bool(provisional.confirm_respawn)

        if not self.game_paused:
            self._update_buffs(simulation_elapsed)
            self._update_field_zones(sentry, simulation_elapsed)
            self._update_rune(simulation_elapsed)
            if not self.game_finished:
                self._update_assembly(simulation_elapsed)
                self._update_assembly_bonus(simulation_elapsed)
                self._update_dart(simulation_elapsed)
                self._update_radar(simulation_elapsed)
                self._update_economy_timers(sentry, simulation_elapsed)
            if not self.game_finished and self.sentry_hp > 0.0:
                self._update_power(sentry, simulation_elapsed)
            if not self.game_finished:
                self._update_respawn(sentry, simulation_elapsed, bool(confirm_respawn))
                self._update_supply(sentry, simulation_elapsed)
            self._update_patrol(sentry)
            self.dodge_remaining = max(
                0.0,
                self.dodge_remaining - simulation_elapsed,
            )
            if self.dodge_remaining > 0.0:
                elapsed = EVADE_DURATION - self.dodge_remaining
                phase = int(elapsed / EVADE_DIRECTION_PERIOD) % len(EVADE_OFFSETS)
                if phase != self._dodge_phase:
                    self._dodge_phase = phase
                    offset_x, offset_y = EVADE_OFFSETS[phase]
                    self.dodge_goal = Arena().clamp(
                        sentry.x + offset_x,
                        sentry.y + offset_y,
                    )
            else:
                self.dodge_goal = None
                self._dodge_phase = -1

        decision = decision_override or self.evaluate(sentry)
        if self.game_finished:
            decision = self.evaluate(sentry)
        if not self.game_paused and not self.game_finished:
            self._update_posture(decision.posture, simulation_elapsed)
        requested = bool(decision.shoot_mode) if fire_request is None else fire_request
        if self.game_finished:
            requested = False
        if (
            requested
            and self.ammo > 0
            and not self.respawn_fire_locked
            and not self.sentry_fire_locked
        ):
            self._ammo_shot_accumulator += self.fire_rate * simulation_elapsed
            spent = min(int(self._ammo_shot_accumulator), self.ammo)
            if spent:
                self.ammo = max(0, self.ammo - spent)
                self._ammo_shot_accumulator -= spent
                self.sentry_out_of_combat_seconds = 0.0
                sentry.heat += (
                    spent
                    * float(ROBOT_PROFILES[8].heat_per_shot or 0)
                    * self.posture_heat_gain_multiplier
                )
                heat_capacity = float(ROBOT_PROFILES[8].heat_capacity or 0)
                if sentry.heat > heat_capacity + HEAT_PERMANENT_EXTRA:
                    self.sentry_heat_permanent_lock = True
                    self.sentry_heat_locked = True
                    self._set_event("热量超过 Q2，发射机构当局永久锁定")
                elif sentry.heat > heat_capacity:
                    self.sentry_heat_locked = True
                    self._set_event("热量超过 Q1，发射机构锁定至冷却为 0")
                if hit_target_id is not None:
                    self.apply_attack_damage(
                        hit_target_id,
                        "17mm",
                        attack_buff=attack_buff,
                        defence_buff=target_defence_buff,
                        critical_zone=critical_zone,
                        armor_zone=target_armor_zone,
                        shots=spent,
                    )
        return decision

    def rule_damage(
        self,
        projectile: str,
        target_id: int,
        *,
        attack_buff: float = 1.0,
        defence_buff: float = 0.0,
        critical_zone: bool = False,
        armor_zone: str | None = None,
    ) -> int:
        """Calculate final projectile damage using rulebook table 5-2/5-19.

        ``attack_buff`` and ``defence_buff`` are expressed as multipliers and
        fractions respectively (for example 2.0 and 0.25).  A base/outpost
        centre hit receives the rulebook 150% attack bonus.  Final values are
        rounded to the nearest integer as specified by the rulebook.
        """
        if target_id not in (*ROBOT_PROFILES.keys(), 6, 7):
            raise ValueError(f"target {target_id} cannot receive projectile damage")
        if armor_zone not in (None, "normal", "upper_front"):
            raise ValueError(f"unknown armor zone: {armor_zone}")
        if armor_zone == "upper_front" and target_id != 7:
            raise ValueError("upper front armor applies only to a base")
        if projectile not in ("17mm", "42mm", "collision"):
            raise ValueError(f"unsupported damage type: {projectile}")
        if target_id == 5:
            # Rulebook section 3.4: aerial units do not take armor-hit damage.
            return 0
        if projectile == "17mm":
            raw_damage = RULE_DAMAGE_17MM
            if target_id == 7 and armor_zone == "upper_front":
                # Table 5-2: the upper front base armor takes 5 raw 17mm damage.
                raw_damage = 5
        elif projectile == "42mm":
            raw_damage = RULE_DAMAGE_42MM
        elif projectile == "collision":
            if target_id in (6, 7):
                return 0
            raw_damage = RULE_COLLISION_DAMAGE
            final_damage = raw_damage * max(0.0, 1.0 - defence_buff)
            return int(math.floor(final_damage + 0.5))
        else:
            raise ValueError(f"unsupported damage type: {projectile}")
        if critical_zone and target_id in (6, 7):
            # Same-type buffs take the greatest value (section 5.5.3).
            attack_buff = max(attack_buff, 1.5)
        final_damage = raw_damage * max(0.0, attack_buff) * max(0.0, 1.0 - defence_buff)
        return int(math.floor(final_damage + 0.5))

    def apply_attack_damage(
        self,
        target_id: int,
        projectile: str,
        *,
        attack_buff: float = 1.0,
        defence_buff: float | None = None,
        critical_zone: bool = False,
        armor_zone: str | None = None,
        shots: int = 1,
        team: str = "blue",
    ) -> int:
        if not isinstance(shots, int) or isinstance(shots, bool) or shots < 1:
            raise ValueError("shots must be a positive integer")
        if team not in ("blue", "red"):
            raise ValueError(f"unknown team {team}")
        if target_id == 8 and team == "red" and self.invincible_remaining > 0.0:
            return 0
        if defence_buff is None:
            if target_id == 8 and team == "red":
                defence_buff = self.effective_sentry_defence
            else:
                defence_buff = 0.0
        damage = self.rule_damage(
            projectile,
            target_id,
            attack_buff=attack_buff,
            defence_buff=defence_buff,
            critical_zone=critical_zone,
            armor_zone=armor_zone,
        ) * shots
        # Section 5.5.1: a base is invulnerable while its own outpost survives.
        if target_id == 7:
            outpost_hp = self.own_outpost_hp if team == "red" else self.enemy_outpost_hp
            if outpost_hp > 0:
                return 0
        self._apply_fire_damage(target_id, float(damage), team=team)
        return damage

    def apply_collision_contact(
        self,
        first_team: str,
        first_id: int,
        second_team: str,
        second_id: int,
    ) -> int:
        """Apply the 2-D contact model for a robot-robot collision.

        The rulebook allows armour-module impact to be judged as 2 damage.
        This 2-D validator applies it deterministically to both ground robots;
        walls, buildings and aerial units are excluded.
        """
        if first_team == second_team:
            return 0
        total = 0
        for team, target_id in (
            (first_team, first_id),
            (second_team, second_id),
        ):
            if target_id in (5, 6, 7):
                continue
            if target_id not in (1, 2, 3, 4, 8):
                continue
            total += self.apply_attack_damage(
                target_id,
                "collision",
                team=team,
                defence_buff=None,
            )
        if total:
            self._set_event(f"机器人碰撞，双方各受 {RULE_COLLISION_DAMAGE} 点撞击伤害")
        return total

    def _target_health_total(self, target_id: int, *, team: str) -> float:
        if team == "red":
            if target_id == 6:
                return float(self.own_outpost_hp)
            if target_id == 7:
                return float(self.own_base_shield + self.own_base_hp)
            if target_id == 8:
                return float(self.sentry_hp)
            return float(self.own_robot_hp.get(target_id, 0.0))
        if target_id == 6:
            return float(self.enemy_outpost_hp)
        if target_id == 7:
            return float(self.enemy_base_shield + self.enemy_base_hp)
        return float(self.robot_hp.get(target_id, 0.0))

    def _apply_fire_damage(
        self, target_id: int, damage: float, *, team: str = "blue"
    ) -> None:
        if damage <= 0.0:
            return
        before = self._target_health_total(target_id, team=team)
        if team == "red":
            if target_id == 6:
                self.own_outpost_hp = max(0, self.own_outpost_hp - int(damage))
                if self.own_outpost_hp <= 0:
                    self.own_outpost_destroyed_ever = True
            elif target_id == 7:
                shield_damage = min(self.own_base_shield, damage)
                self.own_base_shield -= shield_damage
                self.own_base_hp = max(0, self.own_base_hp - int(damage - shield_damage))
            elif target_id == 8:
                previous_health = self.sentry_hp
                self.sentry_hp = max(0.0, self.sentry_hp - damage)
                self.sentry_out_of_combat_seconds = 0.0
                if previous_health > 0.0 and self.sentry_hp == 0.0:
                    self._mark_sentry_death()
            elif target_id in self.own_robot_hp:
                self.own_robot_hp[target_id] = max(0.0, self.own_robot_hp[target_id] - damage)
            after = self._target_health_total(target_id, team=team)
            self.enemy_team_damage += max(0.0, before - after)
            self._finish_if_base_destroyed()
            return
        if target_id == 6:
            self.enemy_outpost_hp = max(0.0, self.enemy_outpost_hp - damage)
            if self.enemy_outpost_hp <= 0.0:
                self.enemy_outpost_destroyed_ever = True
        elif target_id == 7:
            shield_damage = min(self.enemy_base_shield, damage)
            self.enemy_base_shield -= shield_damage
            remaining_damage = damage - shield_damage
            self.enemy_base_hp = max(0.0, self.enemy_base_hp - remaining_damage)
        elif target_id in self.robot_hp:
            self.robot_hp[target_id] = max(0.0, self.robot_hp[target_id] - damage)
        after = self._target_health_total(target_id, team=team)
        self.own_team_damage += max(0.0, before - after)
        self._finish_if_base_destroyed()

    def _team_remaining_health(self, team: str) -> float:
        if team == "red":
            return (
                self.sentry_hp
                + self.own_outpost_hp
                + self.own_base_hp
                + self.own_base_shield
                + sum(self.own_robot_hp.values())
            )
        return (
            sum(self.robot_hp.values())
            + self.enemy_outpost_hp
            + self.enemy_base_hp
            + self.enemy_base_shield
        )

    def _decide_winner(self) -> str:
        """Rulebook 5.8 winner priority, reduced to the 2-D model."""
        if self.own_base_hp != self.enemy_base_hp:
            return "red" if self.own_base_hp > self.enemy_base_hp else "blue"
        own_outpost_gone = self.own_outpost_destroyed_ever or self.own_outpost_hp <= 0
        enemy_outpost_gone = (
            self.enemy_outpost_destroyed_ever or self.enemy_outpost_hp <= 0
        )
        if own_outpost_gone != enemy_outpost_gone:
            return "red" if not own_outpost_gone else "blue"
        if not own_outpost_gone and self.own_outpost_hp != self.enemy_outpost_hp:
            return "red" if self.own_outpost_hp > self.enemy_outpost_hp else "blue"
        if abs(self.own_team_damage - self.enemy_team_damage) > 1e-6:
            return "red" if self.own_team_damage > self.enemy_team_damage else "blue"
        own_health = self._team_remaining_health("red")
        enemy_health = self._team_remaining_health("blue")
        if abs(own_health - enemy_health) > 1e-6:
            return "red" if own_health > enemy_health else "blue"
        return "draw"

    def _finish_if_base_destroyed(self) -> bool:
        if self.game_finished:
            return True
        if self.own_base_hp <= 0:
            self.finish_game("己方基地被摧毁，比赛结束")
            return True
        if self.enemy_base_hp <= 0:
            self.finish_game("敌方基地被摧毁，比赛结束")
            return True
        return False

    def evaluate(self, sentry: SentryState) -> DecisionView:
        if self.sentry_hp >= 400.0:
            self._health_recovery_active = False
        elif self.sentry_hp < self.health_threshold:
            self._health_recovery_active = True

        spin_mode = 0
        behavior = "巡逻"
        posture = 3
        goal: tuple[float, float] | None = self.patrol_points[self.patrol_index]
        shoot_mode = 0
        target = 0
        confirm_respawn = 0

        if self.game_finished:
            behavior, goal = "比赛结束归位", HOME
        elif self.sentry_hp <= 0.0:
            behavior, goal = "等待复活", None
            confirm_respawn = int(
                self.death_elapsed is not None and self.death_elapsed >= 5.0
            )
        elif self.respawn_fire_locked:
            behavior, goal = "复活后补给解锁", SUPPLY
        elif self._health_recovery_active:
            behavior, goal = "低血量回血", SUPPLY
        elif self.dodge_remaining > 0.0 and self.dodge_goal is not None:
            behavior, posture, goal = "视野外显著受伤不规则回避", 2, self.dodge_goal
        elif self.enemy_outpost_hp > 0.0:
            behavior, posture, goal, target = "攻击敌方前哨", 1, ATTACK, 6
            at_attack = _distance((sentry.x, sentry.y), ATTACK) <= 0.20
            alignment = self.aim_error(sentry, 6)
            aligned = (
                alignment is not None
                and alignment <= FIRE_ALIGNMENT_TOLERANCE
            )
            shoot_mode = int(
                at_attack
                and aligned
                and self.ammo > 0
                and not self.respawn_fire_locked
            )
        elif self.ammo == 0:
            behavior = "前往补给领弹" if self.pending_ammo > 0 else "无弹站桩"
            goal = SUPPLY if self.pending_ammo > 0 else HOME
        if self.game_running and self.sentry_hp > 0.0:
            if "巡逻" in behavior:
                spin_mode = 1 if self.patrol_is_aggressive else 3
            elif "回避" in behavior:
                spin_mode = 3
            elif target > 0:
                spin_mode = 0 if shoot_mode else 1

        if "回避" in behavior:
            tripod_mode = 1
        elif "巡逻" in behavior:
            tripod_mode = int(self.patrol_is_aggressive)
        else:
            tripod_mode = int(target > 0 and shoot_mode == 0)
        if self.sentry_fire_locked:
            shoot_mode = 0
        return DecisionView(
            behavior=behavior,
            posture=posture,
            goal=goal,
            spin_mode=spin_mode,
            tripod_mode=tripod_mode,
            shoot_mode=shoot_mode,
            target=target,
            confirm_respawn=confirm_respawn,
            health_threshold=self.health_threshold,
        )

    def destroy_own_outpost(self) -> None:
        self.own_outpost_hp = 0
        self.own_outpost_destroyed_ever = True
        self._set_event("己方前哨被摧毁，小陀螺已开启")

    def inject_unseen_damage(self, sentry: SentryState) -> None:
        if self.sentry_hp <= 0.0:
            return
        self.sentry_hp = max(0.0, self.sentry_hp - 50.0)
        self.sentry_out_of_combat_seconds = 0.0
        self._start_unseen_damage_evasion(sentry, 50.0)

    def _start_unseen_damage_evasion(
        self, sentry: SentryState, damage: float
    ) -> None:
        offset_x, offset_y = EVADE_OFFSETS[0]
        self.dodge_goal = Arena().clamp(sentry.x + offset_x, sentry.y + offset_y)
        self.dodge_remaining = EVADE_DURATION
        self._dodge_phase = 0
        self._set_event(f"视野外显著受伤 -{round(damage)}，启动不规则回避")

    def empty_ammo(self) -> None:
        self.ammo = 0
        self.pending_ammo = max(self.pending_ammo, 100)
        self._set_event("弹量清零，待领取弹药 100")

    def destroy_enemy_outpost(self) -> None:
        self.enemy_outpost_hp = 0.0
        self.enemy_outpost_destroyed_ever = True
        self._set_event("敌方前哨已被摧毁")

    def set_low_health(self) -> None:
        self.sentry_hp = 150.0
        self._set_event("血量设为 150，验证防御增益回血阈值")

    def finish_game(self, reason: str = "比赛结束，返回启动点") -> None:
        if self.game_finished:
            return
        self.game_running = False
        self.game_finished = True
        self.game_paused = False
        self.remaining_time = 0.0
        self.winner_team = self._decide_winner()
        self.end_reason = reason
        self._set_event(f"{reason}｜{self.result_label}")

    def _mark_sentry_death(self) -> None:
        self.active_buffs = [
            buff for buff in self.active_buffs if buff.source != "terrain_road"
        ]
        self.road_crossing_side = None
        self.road_crossing_elapsed = 0.0
        self.death_elapsed = 0.0
        self.revive_progress = 0.0
        self.revive_required = (
            self.revive_seconds_required if self.revive_mode == "rulebook" else 0.0
        )
        self.remote_heal_remaining = None
        self.instant_revive_power_boost_remaining = 0.0

    def kill_sentry(self) -> None:
        self.sentry_hp = 0.0
        self._mark_sentry_death()
        self._set_event("哨兵阵亡，开始复活计时")

    def add_buff(
        self,
        source: str,
        kind: str,
        value: float,
        duration: float,
    ) -> None:
        if duration <= 0.0:
            return
        for buff in self.active_buffs:
            if buff.source == source and buff.kind == kind:
                buff.value = value
                buff.duration = max(buff.duration, duration)
                buff.remaining = max(buff.remaining, duration)
                return
        self.active_buffs.append(
            ActiveBuff(source, kind, value, duration, duration)
        )

    def _update_buffs(self, elapsed_seconds: float) -> None:
        remaining: list[ActiveBuff] = []
        for buff in self.active_buffs:
            buff.remaining -= elapsed_seconds
            if buff.remaining > 0.0:
                remaining.append(buff)
        self.active_buffs = remaining

    def _update_field_zones(
        self,
        sentry: SentryState,
        elapsed_seconds: float,
    ) -> None:
        road_cooldown_at_start = max(
            self.zone_cooldowns.get("terrain_road", 0.0),
            self.zone_cooldowns.get("red_road", 0.0),
            self.zone_cooldowns.get("blue_road", 0.0),
        )
        for name in list(self.zone_cooldowns):
            self.zone_cooldowns[name] = max(
                0.0, self.zone_cooldowns[name] - elapsed_seconds
            )
        inside: set[str] = set()
        for zone in zones_for_team("red"):
            if not zone.contains(sentry.x, sentry.y):
                continue
            inside.add(zone.name)
            if zone.kind == "terrain_road":
                continue
            if zone.mode == "continuous":
                for kind, value, duration in zone.buffs:
                    self.add_buff(zone.name, kind, value, duration)
            elif (
                zone.name not in self.zone_inside
                and self.zone_cooldowns.get(zone.name, 0.0) <= 0.0
            ):
                for kind, value, duration in zone.buffs:
                    self.add_buff(zone.name, kind, value, duration)
                self.zone_cooldowns[zone.name] = zone.cooldown
        self.zone_inside = inside
        self._update_road_crossing(
            sentry,
            elapsed_seconds,
            road_cooldown_at_start,
        )

    def _update_road_crossing(
        self,
        sentry: SentryState,
        elapsed_seconds: float,
        cooldown_at_start: float,
    ) -> None:
        current = (sentry.x, sentry.y)
        previous = (
            tuple(self._last_field_position)
            if self._last_field_position is not None
            else None
        )
        self._last_field_position = [sentry.x, sentry.y]
        if self.sentry_hp <= 0.0:
            self.road_crossing_side = None
            self.road_crossing_elapsed = 0.0
            return

        events: list[tuple[float, int, str, str | None]] = []
        for side, cards in ROAD_CROSSING_CARDS.items():
            for index, (x, y) in enumerate(cards):
                half_extent = ROAD_CARD_HALF_EXTENT
                time = _segment_rect_entry_time(
                    previous,
                    current,
                    (
                        x - half_extent,
                        y - half_extent,
                        x + half_extent,
                        y + half_extent,
                    ),
                )
                if time is not None:
                    card = "low" if index == 0 else "high"
                    events.append((time, 1, card, side))

        for zone in FIELD_ZONES:
            if zone.kind == "terrain_road":
                continue
            time = _segment_zone_entry_time(previous, current, zone)
            if time is not None:
                events.append((time, 0, "other", zone.name))

        crossing_side = self.road_crossing_side
        crossing_elapsed = self.road_crossing_elapsed
        previous_time = 0.0
        last_success_time: float | None = None
        road_zone = next(zone for zone in FIELD_ZONES if zone.kind == "terrain_road")

        for time, _priority, event_kind, side in sorted(events):
            crossing_elapsed += (time - previous_time) * elapsed_seconds
            if (
                crossing_side is not None
                and crossing_elapsed > ROAD_CROSSING_WINDOW
            ):
                crossing_side = None
                crossing_elapsed = 0.0
            previous_time = time

            if event_kind == "other":
                crossing_side = None
                crossing_elapsed = 0.0
                continue

            if last_success_time is None:
                cooling_down = cooldown_at_start - time * elapsed_seconds > 0.0
            else:
                cooling_down = (
                    (time - last_success_time) * elapsed_seconds
                    < road_zone.cooldown
                )
            if cooling_down:
                crossing_side = None
                crossing_elapsed = 0.0
                continue

            if event_kind == "low":
                crossing_side = side
                crossing_elapsed = 0.0
            elif crossing_side == side and crossing_elapsed <= ROAD_CROSSING_WINDOW:
                for kind, value, duration in road_zone.buffs:
                    self.add_buff("terrain_road", kind, value, duration)
                last_success_time = time
                crossing_side = None
                crossing_elapsed = 0.0
            else:
                crossing_side = None
                crossing_elapsed = 0.0

        crossing_elapsed += (1.0 - previous_time) * elapsed_seconds
        if crossing_elapsed > ROAD_CROSSING_WINDOW:
            crossing_side = None
            crossing_elapsed = 0.0
        self.road_crossing_side = crossing_side
        self.road_crossing_elapsed = crossing_elapsed

        if last_success_time is not None:
            self.zone_cooldowns["terrain_road"] = max(
                0.0,
                road_zone.cooldown
                - (1.0 - last_success_time) * elapsed_seconds,
            )

    def activate_rune(self, kind: str = "small") -> None:
        if kind not in ("small", "large"):
            raise ValueError("rune kind must be small or large")
        if self.rune_state == "activating":
            self._set_event("能量机关正在激活")
            return
        self.rune_kind = kind
        self.rune_state = "activating"
        self.rune_timer = (
            SMALL_RUNE_ACTIVATION_WINDOW
            if kind == "small"
            else LARGE_RUNE_ACTIVATION_WINDOW
        )
        self.rune_hits = 0
        self.rune_arm_count = 5
        self.rune_ring_average = 1.0
        count = 1 if kind == "small" else 2
        self.rune_active_plates = random.sample(range(5), count)
        self._set_event(
            "小能量机关开始激活" if kind == "small" else "大能量机关开始激活"
        )

    def hit_rune(self, sentry: SentryState) -> bool:
        if self.rune_state != "activating":
            self._set_event("能量机关未处于激活状态")
            return False
        if rune_distance_to((sentry.x, sentry.y), "red") > 8.0:
            self._set_event("距离能量机关过远，无法击打")
            return False
        if not self.rune_active_plates:
            self._set_event("没有亮起的装甲")
            return False
        self.rune_hits += 1
        if self.rune_hits >= 5:
            self._complete_rune()
            return True
        count = 1 if self.rune_kind == "small" else 2
        self.rune_active_plates = random.sample(range(5), count)
        self._set_event(f"能量机关命中 {self.rune_hits}/5")
        return True

    def _complete_rune(self) -> None:
        self.rune_active_plates = []
        if self.rune_kind == "small":
            duration = SMALL_RUNE_DURATION
            self.add_buff("小能量机关", "defence", SMALL_RUNE_DEFENCE, duration)
            self.rune_state = "active"
            self.rune_timer = duration
            self._set_event("小能量机关激活：25% 防御增益 45 秒")
            return
        self.rune_ring_average = random.uniform(1.0, 10.0)
        self.rune_arm_count = random.randint(5, 10)
        for kind, value, duration in large_rune_profile(
            self.rune_ring_average, self.rune_arm_count
        ):
            self.add_buff("大能量机关", kind, value, duration)
        self.rune_state = "active"
        self.rune_timer = max(30.0, min(60.0, 5.0 * self.rune_arm_count + 5.0))
        self._set_event(
            f"大能量机关激活：{self.rune_ring_average:.1f} 环，"
            f"{self.rune_arm_count} 灯臂"
        )

    def _update_rune(self, elapsed_seconds: float) -> None:
        if self.rune_state == "inactive":
            return
        self.rune_timer = max(0.0, self.rune_timer - elapsed_seconds)
        if self.rune_timer > 0.0:
            return
        self.rune_state = "inactive"
        self.rune_active_plates = []
        self._set_event("能量机关状态结束")

    def _zone_named(self, name: str):
        return next((zone for zone in FIELD_ZONES if zone.name == name), None)

    def select_assembly_difficulty(self, difficulty: int) -> bool:
        if difficulty not in (1, 2, 3, 4):
            raise ValueError("assembly difficulty must be 1..4")
        required_elapsed = (difficulty - 1) * 60.0
        if self.match_elapsed < required_elapsed:
            self._set_event(f"{difficulty} 级装配尚未到开放时间")
            return False
        if difficulty > 1 and (difficulty - 1) not in self.assembly_completed:
            self._set_event("需要先完成上一级装配")
            return False
        self.assembly_difficulty = difficulty
        self._set_event(f"已选择 {difficulty} 级装配")
        return True

    def start_assembly(self) -> bool:
        if self.assembly_difficulty <= 0:
            self._set_event("请先选择装配难度")
            return False
        zone = self._zone_named("red_assembly")
        position = self.own_robot_position(2)
        if zone is None or not zone.contains(*position):
            self._set_event("工程机器人不在己方装配区")
            return False
        if self.assembly_active:
            self._set_event("装配已在进行")
            return False
        self.assembly_active = True
        self.assembly_progress = 0.0
        self.assembly_required = float(4 + self.assembly_difficulty * 2)
        self._set_event(
            f"开始 {self.assembly_difficulty} 级装配，"
            f"需要 {self.assembly_required:.0f} 秒"
        )
        return True

    def cancel_assembly(self) -> None:
        if self.assembly_active:
            self.assembly_active = False
            self.assembly_progress = 0.0
            self._set_event("装配已取消")

    def _complete_assembly(self) -> None:
        difficulty = self.assembly_difficulty
        first = difficulty not in self.assembly_completed
        self.assembly_completed.add(difficulty)
        self.assembly_active = False
        self.assembly_progress = 0.0
        self.assembly_difficulty = 0
        if difficulty == 1:
            self.assembly_bonus_per_10s += 50 if first else 5
        elif difficulty == 2:
            self.level_cap = max(self.level_cap, 7)
            self.assembly_bonus_per_10s += 10
        elif difficulty == 3:
            self.level_cap = 10
            self.assembly_defence = max(self.assembly_defence, 0.25)
            self.assembly_bonus_per_10s += 25 if first else 15
        elif difficulty == 4:
            self.assembly_defence = max(self.assembly_defence, 0.50)
            self.own_base_max_hp = 7000
            gained = 2000
            space = max(0, self.own_base_max_hp - self.own_base_hp)
            applied = min(space, gained)
            self.own_base_hp += applied
            self.own_base_shield += gained - applied
            if first:
                self.assembly_bonus_per_10s += 50
        self._set_event(
            f"{difficulty} 级装配完成，每 10 秒额外金币 "
            f"{self.assembly_bonus_per_10s}"
        )

    def _update_assembly(self, elapsed_seconds: float) -> None:
        if not self.assembly_active:
            return
        zone = self._zone_named("red_assembly")
        if zone is None or not zone.contains(*self.own_robot_position(2)):
            self.cancel_assembly()
            return
        self.assembly_progress = min(
            self.assembly_required,
            self.assembly_progress + elapsed_seconds,
        )
        if self.assembly_progress >= self.assembly_required:
            self._complete_assembly()

    def _update_assembly_bonus(self, elapsed_seconds: float) -> None:
        if self.assembly_bonus_per_10s <= 0:
            return
        self.assembly_bonus_accumulator += elapsed_seconds
        while self.assembly_bonus_accumulator >= 10.0:
            self.assembly_bonus_accumulator -= 10.0
            self.economy = min(
                ECONOMY_CAP, self.economy + self.assembly_bonus_per_10s
            )

    def cycle_dart_target(self) -> None:
        order = ("fixed", "random_fixed", "random_moving", "end_moving")
        current = order.index(self.dart_target_type)
        self.dart_target_type = order[(current + 1) % len(order)]
        self._set_event(f"飞镖目标：{self.dart_target_type}")

    def open_dart_gate(self) -> bool:
        if self.dart_gate_windows <= 0:
            self._set_event("飞镖闸门开启次数已用完")
            return False
        if self.dart_gate_state != "closed":
            self._set_event("飞镖闸门正在动作")
            return False
        self.dart_gate_windows -= 1
        self.dart_gate_state = "opening"
        self.dart_gate_timer = 7.0
        self._set_event("飞镖闸门开启中，约 7 秒")
        return True

    def fire_dart(self) -> bool:
        if self.dart_gate_state != "open" or self.dart_fire_window <= 0.0:
            self._set_event("飞镖发射窗口未开启")
            return False
        if self.darts_remaining <= 0:
            self._set_event("飞镖已用完")
            return False
        if self.dart_in_flight is not None:
            self._set_event("飞镖正在飞行")
            return False
        self.darts_remaining -= 1
        self.dart_in_flight = 1.0
        self._set_event(f"飞镖已发射，剩余 {self.darts_remaining} 枚")
        return True

    def _update_dart(self, elapsed_seconds: float) -> None:
        self.dart_cooldown = max(0.0, self.dart_cooldown - elapsed_seconds)
        if self.dart_gate_state == "opening":
            self.dart_gate_timer = max(0.0, self.dart_gate_timer - elapsed_seconds)
            if self.dart_gate_timer <= 0.0:
                self.dart_gate_state = "open"
                self.dart_fire_window = 30.0
                self.dart_detection_window = 40.0
                self._set_event("飞镖闸门已开启，发射窗口 30 秒")
        elif self.dart_gate_state == "open":
            self.dart_fire_window = max(0.0, self.dart_fire_window - elapsed_seconds)
            self.dart_detection_window = max(
                0.0, self.dart_detection_window - elapsed_seconds
            )
            if self.dart_fire_window <= 0.0:
                self.dart_gate_state = "cooldown"
                self.dart_cooldown = 15.0
        elif self.dart_gate_state == "cooldown":
            if self.dart_cooldown <= 0.0:
                self.dart_gate_state = "closed"
        if self.dart_in_flight is not None:
            self.dart_in_flight -= elapsed_seconds
            if self.dart_in_flight <= 0.0:
                self.dart_in_flight = None
                self._resolve_dart_hit()

    def _resolve_dart_hit(self) -> None:
        if self.dart_detection_window <= 0.0:
            self._set_event("飞镖检测窗口已关闭，攻击无效")
            return
        if self.enemy_outpost_hp > 0.0:
            damage = 750.0
            self.enemy_outpost_hp = max(0.0, self.enemy_outpost_hp - damage)
            if self.enemy_outpost_hp <= 0.0:
                self.enemy_outpost_destroyed_ever = True
            self.dart_hits += 1
            self._set_event("飞镖命中敌方前哨 -750")
            return
        damage = {
            "fixed": 200.0,
            "random_fixed": 300.0,
            "random_moving": 625.0,
            "end_moving": 1000.0,
        }[self.dart_target_type]
        shield_damage = min(self.enemy_base_shield, damage)
        self.enemy_base_shield -= shield_damage
        self.enemy_base_hp = max(
            0.0, self.enemy_base_hp - (damage - shield_damage)
        )
        self.dart_hits += 1
        if self.dart_target_type in ("random_moving", "end_moving"):
            self.enemy_base_armor_deployed = True
        self._set_event(f"飞镖命中敌方基地 -{damage:.0f}")
        self._finish_if_base_destroyed()

    def radar_mark(self, target_id: int, amount: float = 10.0) -> None:
        if target_id not in self.radar_marks:
            raise ValueError(f"target {target_id} has no radar mark")
        self.radar_marks[target_id] = min(
            150.0, self.radar_marks[target_id] + amount
        )
        self._set_event(
            f"雷达标记 {target_id} 号：{self.radar_marks[target_id]:.0f}"
        )

    def radar_vulnerability(self, target_id: int) -> float:
        if target_id not in (1, 3, 4, 5, 8):
            return 0.0
        progress = self.radar_marks.get(target_id, 0.0)
        if progress >= 120.0:
            value = 0.20
        elif progress >= 100.0:
            value = 0.15
        else:
            return 0.0
        if self.radar_double_remaining > 0.0:
            value *= 2.0
        return value

    def trigger_radar_double(self) -> bool:
        if self.radar_double_charges <= 0:
            self._set_event("没有双倍易伤机会")
            return False
        self.radar_double_charges -= 1
        self.radar_double_remaining = 30.0
        self._set_event("雷达双倍易伤已触发 30 秒")
        return True

    def _update_radar(self, elapsed_seconds: float) -> None:
        self.radar_double_remaining = max(
            0.0, self.radar_double_remaining - elapsed_seconds
        )
        if any(value >= 100.0 for value in self.radar_marks.values()):
            self._radar_mark_seconds = getattr(self, "_radar_mark_seconds", 0.0) + elapsed_seconds
            if self._radar_mark_seconds >= 60.0:
                self._radar_mark_seconds -= 60.0
                self.radar_double_charges = min(
                    2, self.radar_double_charges + 1
                )

    def _update_economy(self) -> None:
        """Award the rulebook table 5-5 periodic gold."""
        if not self.game_running:
            return
        elapsed = self.match_elapsed
        while (
            self._economy_tick < len(ECONOMY_TICKS)
            and elapsed >= ECONOMY_TICKS[self._economy_tick][0]
        ):
            amount = ECONOMY_TICKS[self._economy_tick][1]
            self.economy = min(ECONOMY_CAP, self.economy + amount)
            self._economy_tick += 1
            self._set_event(f"比赛定期金币 +{amount}，当前经济 {self.economy}")

    def _update_power(self, sentry: SentryState, elapsed_seconds: float) -> None:
        if elapsed_seconds <= 0.0:
            return
        if self.sentry_chassis_power_cut_remaining > 0.0:
            self.sentry_chassis_power_cut_remaining = max(
                0.0,
                self.sentry_chassis_power_cut_remaining - elapsed_seconds,
            )
            sentry.chassis_power = 0.0
            if self.sentry_chassis_power_cut_remaining <= 0.0:
                self.sentry_buffer_energy = self.effective_buffer_cap
                self._set_event("底盘断电结束，缓冲能量已恢复")
            return
        power_limit = self.effective_sentry_power_limit
        over_power = sentry.chassis_power - power_limit
        if over_power <= 0.0:
            return
        self.sentry_buffer_energy = max(
            0.0,
            self.sentry_buffer_energy - over_power * elapsed_seconds,
        )
        if self.sentry_buffer_energy <= 0.0:
            self.sentry_chassis_power_cut_remaining = CHASSIS_POWER_CUT_SECONDS
            sentry.chassis_power = 0.0
            self._set_event("底盘功率超限，缓冲能量耗尽，断电 5 秒")

    def toggle_posture_reinforced(self) -> None:
        active = self.active_posture
        if self.reinforced_time.get(active, 0.0) >= POSTURE_REINFORCED_SECONDS:
            self._set_event("该姿态的强化时间已用完")
            return
        self.posture_reinforced = not self.posture_reinforced
        self._set_event(
            "已进入强化姿态" if self.posture_reinforced else "已退出强化姿态"
        )

    def _update_posture(self, desired_posture: int, elapsed_seconds: float) -> None:
        if elapsed_seconds <= 0.0:
            return
        if desired_posture not in (1, 2, 3):
            return
        if self.posture_cooldown_remaining > 0.0:
            self.posture_cooldown_remaining = max(
                0.0,
                self.posture_cooldown_remaining - elapsed_seconds,
            )
        elif desired_posture != self.active_posture:
            self.active_posture = desired_posture
            self.posture_cooldown_remaining = POSTURE_SWITCH_COOLDOWN
            self.posture_reinforced = False
            names = {1: "进攻姿态", 2: "防御姿态", 3: "移动姿态"}
            self._set_event(f"姿态切换为{names[desired_posture]}，冷却 5 秒")

        active = self.active_posture
        was_decayed = self.posture_time.get(active, 0.0) >= POSTURE_DECAY_SECONDS
        self.posture_time[active] = self.posture_time.get(active, 0.0) + elapsed_seconds
        if not was_decayed and self.posture_time[active] >= POSTURE_DECAY_SECONDS:
            self._set_event("该姿态累计超过 3 分钟，效果下降")
        if self.posture_reinforced:
            self.reinforced_time[active] = (
                self.reinforced_time.get(active, 0.0) + elapsed_seconds
            )
            if self.reinforced_time[active] >= POSTURE_REINFORCED_SECONDS:
                self.reinforced_time[active] = POSTURE_REINFORCED_SECONDS
                self.posture_reinforced = False
                self._set_event("强化姿态 15 秒已用完，自动退出")

    def _update_respawn(
        self,
        sentry: SentryState,
        elapsed_seconds: float,
        confirmed: bool,
    ) -> None:
        if self.sentry_hp > 0.0 or self.death_elapsed is None:
            return
        self.death_elapsed += elapsed_seconds
        if self.revive_mode == "rulebook":
            self._update_rulebook_revive(sentry, elapsed_seconds)
            return
        if self.death_elapsed < RESPAWN_CONFIRM_SECONDS or not confirmed:
            return
        self.sentry_hp = 400.0
        sentry.heat = 0.0
        self.death_elapsed = None
        self.respawn_fire_locked = True
        self.sentry_heat_locked = self.sentry_heat_permanent_lock
        self.sentry_buffer_energy = self.effective_buffer_cap
        self.sentry_chassis_power_cut_remaining = 0.0
        sentry.chassis_power = 0.0
        self._ammo_shot_accumulator = 0.0
        self._set_event("哨兵已复活，热量与缓冲能量重置，返回补给区解锁射击")

    def _update_rulebook_revive(
        self,
        sentry: SentryState,
        elapsed_seconds: float,
    ) -> None:
        if self.revive_required <= 0.0:
            self.revive_required = self.revive_seconds_required
        in_supply = in_supply_zone(sentry.x, sentry.y)
        fast = in_supply or self.own_base_hp < 2000
        rate = (
            RULEBOOK_REVIVE_SUPPLY_RATE
            if fast
            else RULEBOOK_REVIVE_RATE
        )
        self.revive_progress = min(
            self.revive_required,
            self.revive_progress + rate * elapsed_seconds,
        )
        if self.revive_progress < self.revive_required:
            return
        self.sentry_hp = 400.0 * RULEBOOK_REVIVE_HP_FRACTION
        sentry.heat = 0.0
        self.death_elapsed = None
        self.revive_progress = 0.0
        self.revive_required = 0.0
        self.invincible_remaining = RULEBOOK_REVIVE_INVINCIBLE
        self.weak_state = True
        self.respawn_fire_locked = True
        self.sentry_heat_locked = self.sentry_heat_permanent_lock
        self.sentry_buffer_energy = self.effective_buffer_cap
        self.sentry_chassis_power_cut_remaining = 0.0
        sentry.chassis_power = 0.0
        self._ammo_shot_accumulator = 0.0
        self._set_event("读条复活：10% 血量，30 秒无敌并进入虚弱状态")

    def _update_economy_timers(
        self,
        sentry: SentryState,
        elapsed_seconds: float,
    ) -> None:
        self.invincible_remaining = max(
            0.0, self.invincible_remaining - elapsed_seconds
        )
        self.instant_revive_power_boost_remaining = max(
            0.0,
            self.instant_revive_power_boost_remaining - elapsed_seconds,
        )
        if self.remote_heal_remaining is not None:
            self.remote_heal_remaining = max(
                0.0, self.remote_heal_remaining - elapsed_seconds
            )
            if self.remote_heal_remaining <= 0.0:
                self.remote_heal_remaining = None
                if self.sentry_hp > 0.0:
                    self.sentry_hp = min(
                        400.0,
                        self.sentry_hp + 400.0 * REMOTE_HEAL_FRACTION,
                    )
                    self._set_event("远程回血生效：恢复 60% 上限血量")
                else:
                    self._set_event("远程回血失效：哨兵已阵亡")
        if self.remote_ammo_remaining is not None:
            self.remote_ammo_remaining = max(
                0.0, self.remote_ammo_remaining - elapsed_seconds
            )
            if self.remote_ammo_remaining <= 0.0:
                self.remote_ammo_remaining = None
                amount = self.remote_ammo_pending
                self.remote_ammo_pending = 0
                space = max(0, AMMO_CAP - self.ammo)
                transferred = min(space, amount)
                self.ammo += transferred
                self.pending_ammo = min(
                    PENDING_AMMO_CAP,
                    self.pending_ammo + amount - transferred,
                )
                self._set_event(f"远程兑换弹药生效 +{amount}")

    def _update_supply(self, sentry: SentryState, elapsed_seconds: float) -> None:
        late_heal = (
            self.match_elapsed >= SUPPLY_LATE_MATCH_ELAPSED
            and self.sentry_out_of_combat_seconds >= OUT_OF_COMBAT_SECONDS
        )
        heal_fraction = (
            SUPPLY_HEAL_LATE_FRACTION if late_heal else SUPPLY_HEAL_BASE_FRACTION
        )
        if in_supply_zone(sentry.x, sentry.y):
            if self.weak_state:
                self.weak_state = False
                self.respawn_fire_locked = False
                self.invincible_remaining = min(
                    self.invincible_remaining,
                    RULEBOOK_REVIVE_WEAK_INVINCIBLE_MIN,
                )
                self._set_event("虚弱状态解除，发射机构解锁")
            elif self.respawn_fire_locked:
                self.respawn_fire_locked = False
                self._set_event("发射机构已解锁")
            if 0.0 < self.sentry_hp < 400.0:
                self.sentry_hp = min(
                    400.0,
                    self.sentry_hp + 400.0 * heal_fraction * elapsed_seconds,
                )
            if self.pending_ammo > 0:
                transfer = min(AMMO_CAP - self.ammo, self.pending_ammo)
                if transfer > 0:
                    self.ammo += transfer
                    self.pending_ammo -= transfer
                    self._set_event(f"补给区补弹 +{transfer}，当前弹量 {self.ammo}")
        # Friendly ground robots share the same supply-zone healing model.
        for target_id, health in self.own_robot_hp.items():
            if target_id == 5:
                continue
            x, y = self.own_robot_positions[target_id]
            if not in_supply_zone(x, y) or health <= 0.0:
                continue
            maximum = float(ROBOT_PROFILES[target_id].max_hp)
            if health >= maximum:
                continue
            self.own_robot_hp[target_id] = min(
                maximum,
                health + maximum * heal_fraction * elapsed_seconds,
            )

    def _update_patrol(self, sentry: SentryState) -> None:
        points = self.patrol_points
        point = points[self.patrol_index]
        if _distance((sentry.x, sentry.y), point) > 0.15:
            return
        if len(points) == 1:
            return
        self.patrol_index = (self.patrol_index + 1) % len(points)

    def _set_event(self, message: str) -> None:
        self.event_message = message
        self.event_message_remaining = 3.0


def _distance(first: tuple[float, float], second: tuple[float, float]) -> float:
    return math.hypot(first[0] - second[0], first[1] - second[1])


def _segment_rect_entry_time(
    start: tuple[float, float] | None,
    end: tuple[float, float],
    rectangle: tuple[float, float, float, float],
) -> float | None:
    min_x, min_y, max_x, max_y = rectangle

    def contains(point: tuple[float, float]) -> bool:
        return min_x <= point[0] <= max_x and min_y <= point[1] <= max_y

    if start is None:
        return 0.0 if contains(end) else None
    if contains(start):
        return None

    delta_x = end[0] - start[0]
    delta_y = end[1] - start[1]
    enter = 0.0
    leave = 1.0
    for origin, delta, lower, upper in (
        (start[0], delta_x, min_x, max_x),
        (start[1], delta_y, min_y, max_y),
    ):
        if abs(delta) <= 1e-12:
            if origin < lower or origin > upper:
                return None
            continue
        first = (lower - origin) / delta
        second = (upper - origin) / delta
        axis_enter, axis_leave = sorted((first, second))
        enter = max(enter, axis_enter)
        leave = min(leave, axis_leave)
        if enter > leave:
            return None
    if leave < 0.0 or enter > 1.0:
        return None
    return max(0.0, enter)


def _segment_zone_entry_time(
    start: tuple[float, float] | None,
    end: tuple[float, float],
    zone: FieldZone,
) -> float | None:
    if not zone.polygon:
        return _segment_rect_entry_time(
            start,
            end,
            (zone.min_x, zone.min_y, zone.max_x, zone.max_y),
        )
    if start is None:
        return 0.0 if zone.contains(*end) else None
    if zone.contains(*start):
        return None

    delta_x = end[0] - start[0]
    delta_y = end[1] - start[1]
    candidates = [1.0] if zone.contains(*end) else []
    for index, (edge_x, edge_y) in enumerate(zone.polygon):
        next_x, next_y = zone.polygon[(index + 1) % len(zone.polygon)]
        edge_delta_x = next_x - edge_x
        edge_delta_y = next_y - edge_y
        denominator = delta_x * edge_delta_y - delta_y * edge_delta_x
        if abs(denominator) <= 1e-12:
            continue
        offset_x = edge_x - start[0]
        offset_y = edge_y - start[1]
        time = (offset_x * edge_delta_y - offset_y * edge_delta_x) / denominator
        edge_time = (offset_x * delta_y - offset_y * delta_x) / denominator
        if -1e-12 <= time <= 1.0 + 1e-12 and -1e-12 <= edge_time <= 1.0 + 1e-12:
            candidates.append(max(0.0, min(time, 1.0)))
    return min(candidates) if candidates else None


def in_supply_zone(x: float, y: float) -> bool:
    minimum_x, maximum_x, minimum_y, maximum_y = SUPPLY_ZONE
    return minimum_x <= x <= maximum_x and minimum_y <= y <= maximum_y
