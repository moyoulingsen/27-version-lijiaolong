"""Task-one referee inputs and expected high-level decision outputs."""

from __future__ import annotations

from dataclasses import dataclass, field
import math
import random
from collections.abc import Callable

from .core import Arena, SentryState
from .field_rules import (
    LARGE_RUNE_ACTIVATION_WINDOW,
    RUNE_POSITIONS,
    SMALL_RUNE_ACTIVATION_WINDOW,
    SMALL_RUNE_DEFENCE,
    SMALL_RUNE_DURATION,
    large_rune_profile,
    rune_distance_to,
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
)
from .map_regions import normalize_points, validate_polygon


HOME = RED_HOME
SUPPLY = RED_SUPPLY_POINT
ATTACK = OUTPOST_ATTACK_POINT
MATCH_DURATION = 420.0
TASK_RESPAWN_CONFIRM_SECONDS = 5.0
DETECTION_RANGE = 6.2
ATTACK_RANGE = 4.0
WEAPON_RANGE = ATTACK_RANGE
FIRE_ALIGNMENT_TOLERANCE = math.radians(4.0)
ROBOT_VISION_HALF_ANGLE = math.radians(24.0)
ROBOT_TURRET_SPEED = math.radians(210.0)
ROBOT_TURNTABLE_SPEED = math.radians(150.0)
ROBOT_TURNTABLE_SPEED_SCALE = {0: 0.0, 1: 0.6, 2: 1.0, 3: 1.6}
ROBOT_TURNTABLE_HIT_PROBABILITY = {0: 1.0, 1: 0.90, 2: 0.75, 3: 0.50}
OUTPOST_HIT_PROBABILITY = 0.90
COMMUNICATION_ROBOT_IDS = (1, 2, 3, 4, 5, 8)
ORDINARY_COMMUNICATION_IDS = (1, 2, 3, 4, 5)
RADAR_COMMUNICATION_NODE = "radar"
RULE_FIRE_RATE_MAX = 20
# The rulebook's 50 ms armour detection interval allows at most 20 detected
# 17 mm hits per second.  The simulator uses that referee-detectable ceiling
# instead of inventing a lower rulebook value.
SENTRY_FIRE_RATE_DEFAULT = RULE_FIRE_RATE_MAX
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
PATROL_POINTS = CONSERVATIVE_PATROL_POINTS

# v2 rule-fidelity constants following rulebook V2.2.0.
OUT_OF_COMBAT_SECONDS = 6.0
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
HEAT_COOLING_PERIOD = 0.1
HEAT_Q2_EXTRA = {
    "17mm": 100,
    "42mm": 200,
}
# Compatibility alias retained for existing UI/tests that display the
# sentry's 17 mm Q2 threshold.
HEAT_PERMANENT_EXTRA = HEAT_Q2_EXTRA["17mm"]
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
RULEBOOK_REVIVE_BASE = 10.0
INSTANT_REVIVE_INVINCIBLE = 3.0
INSTANT_REVIVE_POWER_BOOST = 4.0
BASE_GAIN_DEFENCE = 0.50
BASE_GAIN_ZONE_IDS = {
    "red": "region_06_base_red",
    "blue": "region_06_base_blue",
}
TRAPEZOID_GAIN_DEFENCE = 0.50
TRAPEZOID_GAIN_ZONE_IDS = {
    "red": "region_05_trapezoid_highland_red",
    "blue": "region_05_trapezoid_highland_blue",
}
CENTRAL_HIGHLAND_ZONE_ID = "region_11_central_highland"
CENTRAL_HIGHLAND_DEFENCE = 0.25
GAIN_OCCUPATION_EXIT_DELAY = 2.0
CENTRAL_HIGHLAND_EXIT_DELAY = GAIN_OCCUPATION_EXIT_DELAY
CENTRAL_HIGHLAND_ROBOT_IDS = (1, 3, 4, 8)
OUTPOST_GAIN_DEFENCE = 0.25
OUTPOST_GAIN_ENEMY_CAPTURE_SECONDS = 300.0
OUTPOST_REBUILD_DAMAGE_STEP = 1000.0
OUTPOST_REBUILD_HP = 750.0
OUTPOST_REBUILD_DEADLINE_SECONDS = 300.0
OUTPOST_REBUILD_SECONDS = {1: 10.0, 2: 5.0, 3: 10.0, 4: 10.0, 8: 10.0}
OUTPOST_GAIN_ZONE_IDS = {
    "red": "region_09_outpost_red",
    "blue": "region_09_outpost_blue",
}
ASSEMBLY_GAIN_MAX_SECONDS = 180.0
ASSEMBLY_GAIN_ZONE_IDS = {
    "red": "region_12_assembly_red",
    "blue": "region_12_assembly_blue",
}
# The physical 6-DOF assembly is represented by a short referee-side timer in
# the 2-D simulator.  Leaving the interaction region follows the rulebook's
# continuous 15-second card-loss failure condition.
ASSEMBLY_SIM_DURATION = {1: 6.0, 2: 8.0, 3: 10.0, 4: 12.0}
# The 2-D referee deliberately uses one fixed success probability per
# assembly difficulty.  No manipulator physics is simulated: once the
# engineer is inside the configured assembly polygon and the timer expires,
# exactly one Bernoulli trial is made.  These are referee-side calibrated
# values; callers can override the mapping on
# ``TaskScenario(assembly_success_probability=...)`` without touching the
# behavior tree or ROS bridge.
ASSEMBLY_SUCCESS_PROBABILITY = {1: 0.95, 2: 0.80, 3: 0.40, 4: 0.05}
ASSEMBLY_OUTSIDE_FAILURE_SECONDS = 15.0
SUPPLY_GAIN_HEAL = 0.10
SUPPLY_GAIN_HEAL_LATE = 0.25
SUPPLY_GAIN_LATE_SECONDS = 240.0
SUPPLY_GAIN_ZONE_IDS = {
    "red": "region_01_supply_red",
    "blue": "region_01_supply_blue",
}
FORT_GAIN_DEFENCE = 0.50
FORT_GAIN_COOLING_CAP = 75
FORT_GAIN_RESERVE_MIN = 100
FORT_GAIN_RESERVE_CAP = 500
FORT_ENEMY_CAPTURE_START_SECONDS = 180.0
FORT_ENEMY_CAPTURE_REQUIRED_SECONDS = 20.0
FORT_ENEMY_CAPTURE_GRACE_SECONDS = 3.0
FORT_GAIN_ZONE_IDS = {
    "red": "region_07_fort_red",
    "blue": "region_07_fort_blue",
}
FORT_ROBOT_IDS = (1, 3, 4, 8)
GROUND_ROBOT_IDS = (1, 2, 3, 4, 8)
ENGINEER_OPENING_DEFENCE = 0.50
ENGINEER_OPENING_DEFENCE_SECONDS = 180.0
TERRAIN_CROSSING_KINDS = ("road", "highland", "fly_slope", "tunnel")
TERRAIN_CROSSING_WINDOWS = {
    "road": 3.0,
    "highland": 5.0,
    "fly_slope": 10.0,
    "tunnel": 3.0,
}
TERRAIN_CROSSING_CARD_COUNTS = {
    "road": 2,
    "highland": 2,
    "fly_slope": 2,
    "tunnel": 3,
}
TERRAIN_STANDARD_DEFENCE = 0.25
TERRAIN_REPEATED_DEFENCE = 0.50
TERRAIN_STANDARD_DURATIONS = {
    "road": 5.0,
    "highland": 30.0,
    "fly_slope": 30.0,
}
TERRAIN_ROAD_COOLDOWN = 15.0
TERRAIN_TUNNEL_DEFENCE = 0.50
TERRAIN_TUNNEL_DEFENCE_DURATION = 10.0
TERRAIN_TUNNEL_COOLING = 2.0
TERRAIN_TUNNEL_COOLING_DURATION = 120.0

# Radar referee-side abstraction.  The simulator does not model RF waveforms
# or 3-D laser geometry; it samples these configurable outcomes and then
# applies the rulebook P/threshold logic to the result.
RADAR_ROBOT_IDS = (1, 2, 3, 4, 5, 8)
RADAR_MARK_TARGET_IDS = RADAR_ROBOT_IDS + (6, 7)
RADAR_REPORT_FREQUENCY_HZ = 5.0
RADAR_REPORT_INTERVAL = 1.0 / RADAR_REPORT_FREQUENCY_HZ
RADAR_ACCURACY_PROBABILITY = {
    "accurate": 0.80,
    "half_accurate": 0.15,
    "error": 0.05,
}
RADAR_DATA_LOSS_PROBABILITY = 0.02
RADAR_AIR_LOCK_DURATION = 45.0
RADAR_AIR_MAX_LOCKS = 5
RADAR_AIR_LOCK_PROBABILITY = {1: 0.85, 2: 0.65, 3: 0.45}
RADAR_INFO_WAVE_PROBABILITY = 0.80
RADAR_INTERFERENCE_PARSE_PROBABILITY = 0.70
RADAR_INFO_PACKET_TTL = 2.0

# Level tables (rulebook 5.4).  Sentry and engineer do not use levels.
LEVEL_EXP_THRESHOLDS = (0, 550, 1100, 1650, 2200, 2750, 3300, 3850, 4400, 5000)
HERO_HP_RANGED = (200, 220, 240, 260, 280, 300, 320, 340, 360, 400)
HERO_HP_MELEE = (260, 300, 330, 360, 400, 430, 460, 500, 530, 600)
HERO_POWER_RANGED = (50, 55, 60, 65, 70, 75, 80, 85, 90, 100)
HERO_POWER_MELEE = (70, 75, 80, 85, 90, 95, 100, 105, 110, 120)
HERO_HEAT_RANGED = (160, 162, 164, 166, 168, 170, 175, 180, 185, 190)
HERO_COOLING_RANGED = (20, 23, 26, 29, 32, 35, 38, 41, 44, 50)
HERO_HEAT_MELEE = (200, 210, 220, 230, 240, 250, 260, 270, 280, 300)
HERO_COOLING_MELEE = (12, 14, 16, 18, 20, 22, 24, 26, 28, 30)
INFANTRY_HP_BLOOD = (200, 225, 250, 275, 300, 325, 350, 375, 400, 400)
INFANTRY_HP_POWER = (150, 175, 200, 225, 250, 275, 300, 325, 350, 400)
INFANTRY_POWER_BLOOD = (45, 50, 55, 60, 65, 70, 75, 80, 90, 100)
INFANTRY_POWER_POWER = (60, 65, 70, 75, 80, 85, 90, 95, 100, 100)
INFANTRY_HEAT_COOLING = (40, 48, 56, 64, 72, 80, 88, 96, 114, 120)
INFANTRY_COOLING_COOLING = (12, 14, 16, 18, 20, 22, 24, 26, 28, 30)
INFANTRY_HEAT_BURST = (170, 180, 190, 200, 210, 220, 230, 240, 250, 260)
INFANTRY_COOLING_BURST = (5, 7, 9, 11, 12, 13, 14, 16, 18, 20)
AERIAL_HP = 100
AERIAL_HEAT = (100, 110, 120, 130, 140, 150, 160, 170, 180, 200)
AERIAL_COOLING = (20, 30, 40, 50, 60, 70, 80, 90, 100, 120)


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
    5: RobotProfile("空中", 100, "17mm", 750, 25.0, None, 100, 20, RULE_DAMAGE_17MM, None, False, False, True, True, 10),
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


def _initial_radar_marks() -> dict[int, float]:
    return {target_id: 0.0 for target_id in RADAR_MARK_TARGET_IDS}


def _initial_radar_mark_x() -> dict[int, float]:
    return {target_id: 0.0 for target_id in RADAR_ROBOT_IDS}


def _initial_radar_report_quality() -> dict[int, str]:
    return {target_id: "未发送" for target_id in RADAR_ROBOT_IDS}


def _initial_radar_report_rolls() -> dict[int, float | None]:
    return {target_id: None for target_id in RADAR_ROBOT_IDS}


def _initial_radar_missing_seconds() -> dict[int, float]:
    return {target_id: 0.0 for target_id in RADAR_ROBOT_IDS}


def _initial_radar_estimated_positions() -> dict[int, list[float]]:
    return {
        entity.target_id: [entity.x, entity.y]
        for entity in FIELD_ENTITIES
        if entity.kind == "robot"
    }


def _initial_robot_heat() -> dict[int, float]:
    return {target_id: 0.0 for target_id in ROBOT_PROFILES}


def _initial_robot_heat_flags() -> dict[int, bool]:
    return {target_id: False for target_id in ROBOT_PROFILES}


def _initial_robot_power() -> dict[int, float]:
    return {target_id: 0.0 for target_id in ROBOT_PROFILES}


def _initial_robot_buffer_energy() -> dict[int, float]:
    return {target_id: BUFFER_ENERGY_CAP for target_id in ROBOT_PROFILES}


def _initial_robot_power_cut() -> dict[int, float]:
    return {target_id: 0.0 for target_id in ROBOT_PROFILES}


def _initial_robot_view_angles() -> dict[str, dict[int, float]]:
    return {
        team: {target_id: 0.0 for target_id in COMMUNICATION_ROBOT_IDS}
        for team in ("red", "blue")
    }


def _initial_robot_turntable_angles() -> dict[str, dict[int, float]]:
    return {
        team: {target_id: 0.0 for target_id in COMMUNICATION_ROBOT_IDS}
        for team in ("red", "blue")
    }


def _initial_robot_turntable_modes() -> dict[str, dict[int, int]]:
    return {
        team: {target_id: 1 for target_id in COMMUNICATION_ROBOT_IDS}
        for team in ("red", "blue")
    }


def _initial_robot_visible_positions() -> dict[str, dict[int, dict[int, list[float]]]]:
    return {
        team: {target_id: {} for target_id in COMMUNICATION_ROBOT_IDS}
        for team in ("red", "blue")
    }


def _initial_team_communication_inboxes() -> dict[str, dict[str, dict[str, dict]]]:
    receivers = tuple(str(target_id) for target_id in COMMUNICATION_ROBOT_IDS) + (
        RADAR_COMMUNICATION_NODE,
    )
    return {
        team: {receiver: {} for receiver in receivers}
        for team in ("red", "blue")
    }


def _initial_robot_shots() -> dict[int, int | None]:
    # Dataset telemetry is nullable: NULL means the weapon is not applicable
    # or was not recorded, and must not be rendered as zero shots.
    return {target_id: None for target_id in ROBOT_PROFILES}


def _initial_enemy_ground_flags() -> dict[int, bool]:
    return {target_id: False for target_id in GROUND_ROBOT_IDS}


def _initial_own_ground_flags() -> dict[int, bool]:
    # The red sentry keeps its legacy scalar fields for ROS/UI compatibility.
    return {target_id: False for target_id in GROUND_ROBOT_IDS if target_id != 8}


def _initial_enemy_ground_timers() -> dict[int, float]:
    return {target_id: 0.0 for target_id in GROUND_ROBOT_IDS}


def _initial_own_ground_timers() -> dict[int, float]:
    return {target_id: 0.0 for target_id in GROUND_ROBOT_IDS if target_id != 8}


def _initial_enemy_death_timers() -> dict[int, float | None]:
    return {target_id: None for target_id in GROUND_ROBOT_IDS}


def _initial_own_death_timers() -> dict[int, float | None]:
    return {target_id: None for target_id in GROUND_ROBOT_IDS if target_id != 8}


def _initial_base_gain_occupants() -> dict[str, list[int]]:
    return {"red": [], "blue": []}


def _initial_trapezoid_gain_occupants() -> dict[str, list[int]]:
    return {"red": [], "blue": []}


def _initial_central_highland_occupants() -> dict[str, list[int]]:
    return {"red": [], "blue": []}


def _initial_central_highland_grace() -> dict[str, dict[str, dict[int, float]]]:
    return {}


def _initial_gain_exit_grace() -> dict[str, dict[str, dict[int, float]]]:
    return {}


def _initial_outpost_gain_occupants() -> dict[str, list[int]]:
    return {"red": [], "blue": []}


def _initial_assembly_gain_occupants() -> dict[str, list[int]]:
    return {"red": [], "blue": []}


def _initial_assembly_gain_elapsed() -> dict[str, float]:
    return {"red": 0.0, "blue": 0.0}


def _initial_supply_gain_occupants() -> dict[str, list[int]]:
    return {"red": [], "blue": []}


def _initial_fort_gain_occupants() -> dict[str, list[int]]:
    return {"red": [], "blue": []}


def _initial_fort_values() -> dict[str, int]:
    return {"red": 0, "blue": 0}


def _initial_fort_capture_timers() -> dict[str, dict[int, float]]:
    return {"red": {}, "blue": {}}


def _initial_team_float_values() -> dict[str, float]:
    return {"red": 0.0, "blue": 0.0}


def _initial_team_int_values() -> dict[str, int]:
    return {"red": 0, "blue": 0}


def _initial_outpost_rebuild_progress() -> dict[str, dict[int, float]]:
    return {
        team: {target_id: 0.0 for target_id in GROUND_ROBOT_IDS}
        for team in ("red", "blue")
    }


def _initial_terrain_robot_values() -> dict[str, dict[int, float]]:
    return {
        team: {target_id: 0.0 for target_id in GROUND_ROBOT_IDS}
        for team in ("red", "blue")
    }


def _initial_terrain_sequence_cards() -> dict[str, dict[int, list[str]]]:
    return {
        team: {target_id: [] for target_id in GROUND_ROBOT_IDS}
        for team in ("red", "blue")
    }


def _initial_terrain_robot_card_sets() -> dict[str, dict[int, list[str]]]:
    return _initial_terrain_sequence_cards()


def _initial_terrain_last_positions() -> dict[str, dict[int, list[float]]]:
    return {"red": {}, "blue": {}}


def _initial_enemy_out_of_combat() -> dict[int, float]:
    return {target_id: OUT_OF_COMBAT_SECONDS for target_id in GROUND_ROBOT_IDS}


def _initial_own_out_of_combat() -> dict[int, float]:
    return {
        target_id: OUT_OF_COMBAT_SECONDS
        for target_id in GROUND_ROBOT_IDS
        if target_id != 8
    }


def _initial_enemy_revive_sources() -> dict[int, str]:
    return {target_id: "" for target_id in GROUND_ROBOT_IDS}


def _initial_own_revive_sources() -> dict[int, str]:
    return {target_id: "" for target_id in GROUND_ROBOT_IDS if target_id != 8}


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
class FireResult:
    """Referee result for one robot firing transaction.

    The caller supplies the aim/target intent.  The referee layer owns all
    ammunition, heat, hit geometry and damage settlement.
    """

    shooter_team: str
    shooter_id: int
    projectile: str
    fired_shots: int = 0
    target_team: str | None = None
    target_id: int | None = None
    damage: int = 0
    reason: str = ""
    shot: FireSolution | None = None

    @property
    def fired(self) -> bool:
        return self.fired_shots > 0


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
    # Manual referee override.  The rulebook does not grant a free defence
    # buff at match start; live posture/zone/tech-core effects are calculated
    # separately by ``effective_sentry_defence``.
    defence_buff: int = 0
    ammo: int = ROBOT_PROFILES[8].initial_ammo
    pending_ammo: int = 0
    economy: int = ECONOMY_INITIAL
    # Enemy economy is referee-side telemetry used by the radar information
    # packet.  Existing gameplay controls continue to spend only ``economy``.
    enemy_economy: int = ECONOMY_INITIAL
    fire_rate: int = SENTRY_FIRE_RATE_DEFAULT
    # Retained for old scenario files and referee-panel compatibility.  The
    # live damage path intentionally ignores this debug value and uses the
    # projectile/armor rule tables below.
    damage_per_shot: int = RULE_DAMAGE_PER_SHOT
    own_outpost_hp: int = RULE_OUTPOST_HP
    own_base_hp: int = RULE_BASE_HP
    own_base_min_hp: float = RULE_BASE_HP
    own_base_shield: float = RULE_BASE_SHIELD
    enemy_outpost_hp: float = RULE_OUTPOST_HP
    enemy_base_hp: float = RULE_BASE_HP
    enemy_base_min_hp: float = RULE_BASE_HP
    enemy_base_shield: float = RULE_BASE_SHIELD
    respawn_fire_locked: bool = False
    death_elapsed: float | None = None
    dodge_remaining: float = 0.0
    dodge_goal: tuple[float, float] | None = None
    aggressive_patrol: bool = False
    patrol_index: int = 0
    conservative_patrol_route: list[list[float]] = field(
        default_factory=lambda: [list(point) for point in CONSERVATIVE_PATROL_POINTS]
    )
    aggressive_patrol_route: list[list[float]] = field(
        default_factory=lambda: [list(point) for point in AGGRESSIVE_PATROL_POINTS]
    )
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
    # Every robot has a persistent viewing direction and a local position-only
    # perception result.  The red sentry's live angle remains in SentryState;
    # its mirrored entry here is refreshed during each scenario update.
    robot_view_angles: dict[str, dict[int, float]] = field(
        default_factory=_initial_robot_view_angles
    )
    robot_turntable_angles: dict[str, dict[int, float]] = field(
        default_factory=_initial_robot_turntable_angles
    )
    robot_turntable_modes: dict[str, dict[int, int]] = field(
        default_factory=_initial_robot_turntable_modes
    )
    robot_visible_positions: dict[str, dict[int, dict[int, list[float]]]] = field(
        default_factory=_initial_robot_visible_positions
    )
    # Latest-message inboxes enforce the rulebook team communication topology.
    # Keys are receiver node names ("1".."8" and "radar"), then channels.
    team_communication_inboxes: dict[str, dict[str, dict[str, dict]]] = field(
        default_factory=_initial_team_communication_inboxes
    )
    own_robot_hp: dict[int, float] = field(default_factory=_initial_own_robot_health)
    own_robot_ammo: dict[int, int] = field(default_factory=_initial_own_robot_ammo)
    # Live referee-style resource telemetry.  The dictionaries include every
    # profile id so a snapshot can be restored without special casing roles.
    robot_heat: dict[int, float] = field(default_factory=_initial_robot_heat)
    own_robot_heat: dict[int, float] = field(default_factory=_initial_robot_heat)
    robot_heat_locked: dict[int, bool] = field(default_factory=_initial_robot_heat_flags)
    own_robot_heat_locked: dict[int, bool] = field(default_factory=_initial_robot_heat_flags)
    robot_heat_permanent_lock: dict[int, bool] = field(default_factory=_initial_robot_heat_flags)
    own_robot_heat_permanent_lock: dict[int, bool] = field(default_factory=_initial_robot_heat_flags)
    heat_cooling_accumulator: float = 0.0
    robot_power: dict[int, float] = field(default_factory=_initial_robot_power)
    own_robot_power: dict[int, float] = field(default_factory=_initial_robot_power)
    robot_buffer_energy: dict[int, float] = field(
        default_factory=_initial_robot_buffer_energy
    )
    own_robot_buffer_energy: dict[int, float] = field(
        default_factory=_initial_robot_buffer_energy
    )
    robot_chassis_power_cut_remaining: dict[int, float] = field(
        default_factory=_initial_robot_power_cut
    )
    own_robot_chassis_power_cut_remaining: dict[int, float] = field(
        default_factory=_initial_robot_power_cut
    )
    hit_random_seed: int = 2026
    hit_random_counter: int = 0
    last_hit_probability: float = 1.0
    last_hit_roll: float | None = None
    # Read-only cumulative dataset telemetry.  These are deliberately separate
    # from ``robot_ammo``/``ammo`` which retain live remaining-ammunition
    # semantics used by the simulator and rulebook controls.
    robot_shots_17mm: dict[int, int | None] = field(default_factory=_initial_robot_shots)
    robot_shots_42mm: dict[int, int | None] = field(default_factory=_initial_robot_shots)
    own_robot_shots_17mm: dict[int, int | None] = field(default_factory=_initial_robot_shots)
    own_robot_shots_42mm: dict[int, int | None] = field(default_factory=_initial_robot_shots)
    # v2 live rule telemetry. Out-of-combat means six continuous seconds
    # without firing or losing health, tracked independently per ground robot.
    sentry_out_of_combat_seconds: float = OUT_OF_COMBAT_SECONDS
    robot_out_of_combat_seconds: dict[int, float] = field(
        default_factory=_initial_enemy_out_of_combat
    )
    own_robot_out_of_combat_seconds: dict[int, float] = field(
        default_factory=_initial_own_out_of_combat
    )
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
    revive_required: float = 0.0
    revive_progress: float = 0.0
    instant_revive_count: int = 0
    invincible_remaining: float = 0.0
    weak_state: bool = False
    revive_invincibility_source: str = ""
    instant_revive_power_boost_remaining: float = 0.0
    # Per-robot rulebook state for every other ground robot.  The red sentry
    # continues to use the scalar fields above so existing ROS/UI consumers do
    # not need to change.
    robot_weak_state: dict[int, bool] = field(default_factory=_initial_enemy_ground_flags)
    own_robot_weak_state: dict[int, bool] = field(default_factory=_initial_own_ground_flags)
    robot_invincible_remaining: dict[int, float] = field(default_factory=_initial_enemy_ground_timers)
    own_robot_invincible_remaining: dict[int, float] = field(default_factory=_initial_own_ground_timers)
    robot_revive_invincibility_source: dict[int, str] = field(
        default_factory=_initial_enemy_revive_sources
    )
    own_robot_revive_invincibility_source: dict[int, str] = field(
        default_factory=_initial_own_revive_sources
    )
    robot_death_elapsed: dict[int, float | None] = field(default_factory=_initial_enemy_death_timers)
    own_robot_death_elapsed: dict[int, float | None] = field(default_factory=_initial_own_death_timers)
    robot_revive_progress: dict[int, float] = field(default_factory=_initial_enemy_ground_timers)
    own_robot_revive_progress: dict[int, float] = field(default_factory=_initial_own_ground_timers)
    robot_revive_required: dict[int, float] = field(default_factory=_initial_enemy_ground_timers)
    own_robot_revive_required: dict[int, float] = field(default_factory=_initial_own_ground_timers)
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
    hero_deployed: dict[str, bool] = field(
        default_factory=lambda: {"red": False, "blue": False}
    )
    infantry_chassis_mode: str = "blood"
    infantry_launcher_mode: str = "cooling"
    # Field gain points / energy rune.
    # Optional world-coordinate polygons edited from the Pygame map editor.
    # An empty polygon means that the corresponding required region was
    # deleted and must be drawn again before validation can start.
    field_zone_overrides: dict[str, list[list[float]]] = field(default_factory=dict)
    active_buffs: list[ActiveBuff] = field(default_factory=list)
    zone_inside: set[str] = field(default_factory=set)
    base_gain_occupants: dict[str, list[int]] = field(
        default_factory=_initial_base_gain_occupants
    )
    trapezoid_gain_occupants: dict[str, list[int]] = field(
        default_factory=_initial_trapezoid_gain_occupants
    )
    central_highland_zones: list[dict] = field(default_factory=list)
    central_highland_owners: dict[str, str] = field(default_factory=dict)
    central_highland_occupants: dict[str, list[int]] = field(
        default_factory=_initial_central_highland_occupants
    )
    central_highland_exit_grace: dict[str, dict[str, dict[int, float]]] = field(
        default_factory=_initial_central_highland_grace
    )
    # Rule 5.5.3.1: occupation remains valid for two seconds after card/zone
    # detection is lost.  Central highland keeps a separate per-polygon map
    # because ownership is mutually exclusive there.
    gain_exit_grace: dict[str, dict[str, dict[int, float]]] = field(
        default_factory=_initial_gain_exit_grace
    )
    outpost_gain_occupants: dict[str, list[int]] = field(
        default_factory=_initial_outpost_gain_occupants
    )
    base_hp_damage_taken: dict[str, float] = field(
        default_factory=_initial_team_float_values
    )
    outpost_rebuild_chances: dict[str, int] = field(
        default_factory=_initial_team_int_values
    )
    outpost_rebuild_progress: dict[str, dict[int, float]] = field(
        default_factory=_initial_outpost_rebuild_progress
    )
    assembly_gain_occupants: dict[str, list[int]] = field(
        default_factory=_initial_assembly_gain_occupants
    )
    assembly_gain_elapsed: dict[str, float] = field(
        default_factory=_initial_assembly_gain_elapsed
    )
    supply_gain_occupants: dict[str, list[int]] = field(
        default_factory=_initial_supply_gain_occupants
    )
    fort_own_occupants: dict[str, list[int]] = field(
        default_factory=_initial_fort_gain_occupants
    )
    fort_enemy_occupants: dict[str, list[int]] = field(
        default_factory=_initial_fort_gain_occupants
    )
    fort_reserve_ammo: dict[str, int] = field(default_factory=_initial_fort_values)
    fort_reserve_capacity: dict[str, int] = field(default_factory=_initial_fort_values)
    fort_enemy_capture_elapsed: dict[str, dict[int, float]] = field(
        default_factory=_initial_fort_capture_timers
    )
    fort_enemy_capture_grace: dict[str, dict[int, float]] = field(
        default_factory=_initial_fort_capture_timers
    )
    # 5.5.3.5 terrain-crossing cards are supplied by the editable map.  Each
    # item contains id/kind/field_team/route/order/points.  Progress and gains
    # are independent for every ground robot on both teams.
    terrain_crossing_cards: list[dict] = field(default_factory=list)
    terrain_sequence_cards: dict[str, dict[int, list[str]]] = field(
        default_factory=_initial_terrain_sequence_cards
    )
    terrain_sequence_elapsed: dict[str, dict[int, float]] = field(
        default_factory=_initial_terrain_robot_values
    )
    terrain_cards_inside: dict[str, dict[int, list[str]]] = field(
        default_factory=_initial_terrain_robot_card_sets
    )
    terrain_last_positions: dict[str, dict[int, list[float]]] = field(
        default_factory=_initial_terrain_last_positions
    )
    terrain_standard_defence: dict[str, dict[int, float]] = field(
        default_factory=_initial_terrain_robot_values
    )
    terrain_standard_remaining: dict[str, dict[int, float]] = field(
        default_factory=_initial_terrain_robot_values
    )
    terrain_tunnel_defence_remaining: dict[str, dict[int, float]] = field(
        default_factory=_initial_terrain_robot_values
    )
    terrain_tunnel_cooling_remaining: dict[str, dict[int, float]] = field(
        default_factory=_initial_terrain_robot_values
    )
    terrain_road_cooldown: dict[str, dict[int, float]] = field(
        default_factory=_initial_terrain_robot_values
    )
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
    # Per-difficulty fixed success probabilities for the 2-D assembly trial.
    assembly_success_probability: dict[int, float] = field(
        default_factory=lambda: dict(ASSEMBLY_SUCCESS_PROBABILITY)
    )
    assembly_last_difficulty: int = 0
    assembly_last_result: str = "未判定"
    assembly_last_roll: float | None = None
    assembly_outside_seconds: float = 0.0
    assembly_level4_cooldown_remaining: float = 0.0
    assembly_completed: set[int] = field(default_factory=set)
    assembly_bonus_per_10s: int = 0
    assembly_bonus_accumulator: float = 0.0
    assembly_defence: float = 0.0
    # ``level_cap`` is the own/red team's cap retained for snapshot/UI
    # compatibility.  The opponent must not inherit red assembly rewards.
    level_cap: int = 5
    enemy_level_cap: int = 5
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
    own_base_armor_deployed: bool = False
    # Radar recognition/marking.  P and its double-vulnerability behavior are
    # retained; reports now arrive through the probabilistic referee model
    # below instead of only through a manual +10 button.
    radar_marks: dict[int, float] = field(default_factory=_initial_radar_marks)
    radar_mark_x: dict[int, float] = field(default_factory=_initial_radar_mark_x)
    radar_last_report_quality: dict[int, str] = field(
        default_factory=_initial_radar_report_quality
    )
    radar_last_report_roll: dict[int, float | None] = field(
        default_factory=_initial_radar_report_rolls
    )
    radar_estimated_positions: dict[int, list[float]] = field(
        default_factory=_initial_radar_estimated_positions
    )
    radar_missing_seconds: dict[int, float] = field(
        default_factory=_initial_radar_missing_seconds
    )
    radar_accuracy_probability: dict[str, float] = field(
        default_factory=lambda: dict(RADAR_ACCURACY_PROBABILITY)
    )
    radar_data_loss_probability: float = RADAR_DATA_LOSS_PROBABILITY
    radar_report_interval: float = RADAR_REPORT_INTERVAL
    radar_report_accumulator: float = 0.0
    radar_report_count: int = 0
    radar_random_seed: int = 2026
    radar_random_counter: int = 0
    radar_last_report_status: str = "未发送"
    radar_double_remaining: float = 0.0
    radar_double_charges: int = 0
    # Decoded information-wave referee object.  Team robot communication is
    # routed separately through ``team_communication_inboxes``.
    radar_team_packet: dict[str, object] = field(default_factory=dict)
    radar_info_wave_decoded: bool = False
    radar_info_wave_probability: float = RADAR_INFO_WAVE_PROBABILITY
    radar_info_wave_last_roll: float | None = None
    radar_info_wave_age: float = RADAR_INFO_PACKET_TTL
    radar_info_wave_ttl: float = RADAR_INFO_PACKET_TTL
    # Electronic-warfare levels start at the rulebook's level-one baseline.
    radar_interference_level: int = 1
    enemy_radar_interference_level: int = 1
    radar_interference_parse_probability: float = RADAR_INTERFERENCE_PARSE_PROBABILITY
    radar_interference_last_roll: float | None = None
    radar_interference_last_result: str = "未解析"
    # Simplified radar laser countermeasure state for the enemy aerial robot.
    radar_air_support_active: bool = False
    radar_air_lock_progress: float = 0.0
    radar_air_lock_remaining: float = 0.0
    radar_air_lock_count: int = 0
    radar_air_lock_difficulty: int = 1
    radar_air_lock_probability: dict[int, float] = field(
        default_factory=lambda: dict(RADAR_AIR_LOCK_PROBABILITY)
    )
    radar_air_last_roll: float | None = None
    radar_air_last_result: str = "未尝试"
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

    def terrain_crossing_defence(self, target_id: int, *, team: str) -> float:
        """Return the live 5.5.3.5 defence gain for one ground robot."""
        if team not in ("red", "blue") or target_id not in GROUND_ROBOT_IDS:
            return 0.0
        standard = 0.0
        if self.terrain_standard_remaining[team].get(target_id, 0.0) > 0.0:
            standard = self.terrain_standard_defence[team].get(target_id, 0.0)
        tunnel = (
            TERRAIN_TUNNEL_DEFENCE
            if self.terrain_tunnel_defence_remaining[team].get(target_id, 0.0) > 0.0
            else 0.0
        )
        return max(standard, tunnel)

    def terrain_crossing_cooling(self, target_id: int, *, team: str) -> float:
        """Return the live tunnel heat-cooling multiplier for one robot."""
        if team not in ("red", "blue") or target_id not in GROUND_ROBOT_IDS:
            return 1.0
        return (
            TERRAIN_TUNNEL_COOLING
            if self.terrain_tunnel_cooling_remaining[team].get(target_id, 0.0) > 0.0
            else 1.0
        )

    @property
    def effective_attack_buff(self) -> float:
        return max(1.0, self.buff_value("attack"))

    @property
    def effective_sentry_defence(self) -> float:
        bonus, vulnerability, _, _ = self.posture_effects
        base_gain_active = self.robot_in_base_gain("red", 8)
        trapezoid_gain_active = self.robot_in_trapezoid_gain("red", 8)
        central_highland_active = self.robot_in_central_highland("red", 8)
        outpost_gain_active = self.robot_in_outpost_gain("red", 8)
        own_fort_active = self.robot_in_own_fort_gain("red", 8)
        defence = max(
            self.defence_buff / 100.0,
            self.buff_value("defence"),
            self.assembly_defence,
            self.terrain_crossing_defence(8, team="red"),
            bonus,
        )
        weakness = max(self.buff_value("vulnerability"), vulnerability)
        effective = max(-1.0, min(0.99, defence - weakness))
        zone_defence = 0.0
        if base_gain_active:
            zone_defence = max(zone_defence, BASE_GAIN_DEFENCE)
        if trapezoid_gain_active:
            zone_defence = max(zone_defence, TRAPEZOID_GAIN_DEFENCE)
        if central_highland_active:
            zone_defence = max(zone_defence, CENTRAL_HIGHLAND_DEFENCE)
        if outpost_gain_active:
            zone_defence = max(zone_defence, OUTPOST_GAIN_DEFENCE)
        if own_fort_active:
            zone_defence = max(zone_defence, FORT_GAIN_DEFENCE)
        if self.enemy_fort_vulnerability_active("red", 8):
            result = max(zone_defence, defence) - max(weakness, 1.0)
        else:
            result = max(zone_defence, effective) if zone_defence > 0.0 else effective
        return max(-1.0, min(0.99, result))

    @property
    def effective_sentry_heat_cooling(self) -> float:
        _, _, multiplier, _ = self.posture_effects
        base = float(ROBOT_PROFILES[8].heat_cooling_per_second or 0)
        cooling_buff = max(
            1.0,
            self.buff_value("heat_cooling"),
            self.terrain_crossing_cooling(8, team="red"),
        )
        cooling_before_posture = base * cooling_buff
        if self.robot_in_own_fort_gain("red", 8):
            cooling_before_posture = max(
                cooling_before_posture,
                base + self.fortress_cooling_bonus("red"),
            )
        # Rulebook 5.6.4: first settle the strongest ordinary/fortress cooling
        # gain, then multiply the result by the active sentry posture effect.
        return cooling_before_posture * multiplier

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

    def robot_in_base_gain(self, team: str, target_id: int) -> bool:
        """Return whether a living ground robot occupies its own base gain point."""
        if team not in ("red", "blue"):
            raise ValueError(f"unknown team {team}")
        return target_id in self.base_gain_occupants.get(team, ())

    def robot_in_trapezoid_gain(self, team: str, target_id: int) -> bool:
        """Return whether a ground robot occupies its own trapezoid highland."""
        if team not in ("red", "blue"):
            raise ValueError(f"unknown team {team}")
        return target_id in self.trapezoid_gain_occupants.get(team, ())

    def robot_in_central_highland(self, team: str, target_id: int) -> bool:
        """Return whether an eligible robot occupies a central highland point."""
        if team not in ("red", "blue"):
            raise ValueError(f"unknown team {team}")
        return target_id in self.central_highland_occupants.get(team, ())

    def robot_in_outpost_gain(self, team: str, target_id: int) -> bool:
        """Return whether a robot occupies an eligible outpost gain point."""
        if team not in ("red", "blue"):
            raise ValueError(f"unknown team {team}")
        return target_id in self.outpost_gain_occupants.get(team, ())

    def robot_in_assembly_gain(self, team: str, target_id: int) -> bool:
        """Return whether the team's engineer currently has assembly invincibility."""
        if team not in ("red", "blue"):
            raise ValueError(f"unknown team {team}")
        return target_id in self.assembly_gain_occupants.get(team, ())

    def robot_in_supply_gain(self, team: str, target_id: int) -> bool:
        """Return whether a living ground robot occupies its own supply point."""
        if team not in ("red", "blue"):
            raise ValueError(f"unknown team {team}")
        return target_id in self.supply_gain_occupants.get(team, ())

    def robot_in_own_fort_gain(self, team: str, target_id: int) -> bool:
        if team not in ("red", "blue"):
            raise ValueError(f"unknown team {team}")
        return target_id in self.fort_own_occupants.get(team, ())

    def robot_in_enemy_fort_gain(self, team: str, target_id: int) -> bool:
        if team not in ("red", "blue"):
            raise ValueError(f"unknown team {team}")
        return target_id in self.fort_enemy_occupants.get(team, ())

    def fortress_damage_delta(self, team: str) -> int:
        if team == "red":
            maximum = float(self.own_base_max_hp)
            lowest = min(float(self.own_base_min_hp), float(self.own_base_hp))
        elif team == "blue":
            maximum = float(RULE_BASE_HP)
            lowest = min(float(self.enemy_base_min_hp), float(self.enemy_base_hp))
        else:
            raise ValueError(f"unknown team {team}")
        return max(0, int(math.floor(maximum - lowest)))

    def _record_base_minimum(self, team: str) -> None:
        if team == "red":
            self.own_base_min_hp = min(
                float(self.own_base_min_hp), float(self.own_base_hp)
            )
        elif team == "blue":
            self.enemy_base_min_hp = min(
                float(self.enemy_base_min_hp), float(self.enemy_base_hp)
            )
        else:
            raise ValueError(f"unknown team {team}")

    def _record_base_hp_damage(self, team: str, damage: float) -> None:
        """Accumulate real base-HP loss and award rebuild opportunities."""
        if team not in ("red", "blue"):
            raise ValueError(f"unknown team {team}")
        damage = max(0.0, float(damage))
        if damage <= 0.0:
            return
        previous = max(0.0, float(self.base_hp_damage_taken.get(team, 0.0)))
        current = previous + damage
        self.base_hp_damage_taken[team] = current
        previous_awards = int(previous // OUTPOST_REBUILD_DAMAGE_STEP)
        current_awards = int(current // OUTPOST_REBUILD_DAMAGE_STEP)
        gained = max(0, current_awards - previous_awards)
        if gained:
            self.outpost_rebuild_chances[team] = max(
                0, int(self.outpost_rebuild_chances.get(team, 0))
            ) + gained
            self._set_event(
                f"{'红' if team == 'red' else '蓝'}方基地累计损失"
                f" {current:.0f}，前哨重建机会 +{gained}"
            )

    def fortress_cooling_bonus(self, team: str) -> int:
        return min(FORT_GAIN_COOLING_CAP, self.fortress_damage_delta(team) // 40)

    def fortress_reserve_limit(self, team: str) -> int:
        value = FORT_GAIN_RESERVE_MIN + 2 * (self.fortress_damage_delta(team) // 15)
        return min(FORT_GAIN_RESERVE_CAP, value)

    def fortress_reserve_cost_per_shot(self, target_id: int) -> int:
        if target_id == 1:
            return 10
        if target_id in (3, 4, 8):
            return 1
        return 0

    def fortress_reserve_shots_available(self, target_id: int, *, team: str) -> int:
        if not self.robot_in_own_fort_gain(team, target_id):
            return 0
        cost = self.fortress_reserve_cost_per_shot(target_id)
        if cost <= 0:
            return 0
        return max(0, int(self.fort_reserve_ammo.get(team, 0))) // cost

    def robot_available_shots(self, target_id: int, *, team: str) -> int:
        return self.robot_ammunition(target_id, team=team) + self.fortress_reserve_shots_available(
            target_id, team=team
        )

    def enemy_fort_vulnerability_active(self, team: str, target_id: int) -> bool:
        if not self.robot_in_enemy_fort_gain(team, target_id):
            return False
        target_armor_deployed = (
            self.enemy_base_armor_deployed
            if team == "red"
            else self.own_base_armor_deployed
        )
        return not target_armor_deployed

    def robot_is_weak(self, target_id: int, *, team: str = "blue") -> bool:
        if team not in ("red", "blue"):
            raise ValueError(f"unknown team {team}")
        if team == "red" and target_id == 8:
            return self.weak_state
        states = self.robot_weak_state if team == "blue" else self.own_robot_weak_state
        return bool(states.get(target_id, False))

    def _clear_robot_weakness_at_gain(self, target_id: int, *, team: str) -> bool:
        """Clear weakness and apply the read-bar revive ten-second minimum."""
        if not self.robot_is_weak(target_id, team=team):
            return False
        if team == "red" and target_id == 8:
            source = self.revive_invincibility_source
            remaining = self.invincible_remaining
            self.weak_state = False
            self.respawn_fire_locked = False
            if source == "readbar" or (not source and remaining > INSTANT_REVIVE_INVINCIBLE):
                elapsed = max(0.0, RULEBOOK_REVIVE_INVINCIBLE - remaining)
                self.invincible_remaining = max(0.0, 10.0 - elapsed)
            return True

        weak = self.robot_weak_state if team == "blue" else self.own_robot_weak_state
        invincible = (
            self.robot_invincible_remaining
            if team == "blue"
            else self.own_robot_invincible_remaining
        )
        sources = (
            self.robot_revive_invincibility_source
            if team == "blue"
            else self.own_robot_revive_invincibility_source
        )
        source = sources.get(target_id, "")
        remaining = invincible.get(target_id, 0.0)
        weak[target_id] = False
        if source == "readbar" or (not source and remaining > INSTANT_REVIVE_INVINCIBLE):
            elapsed = max(0.0, RULEBOOK_REVIVE_INVINCIBLE - remaining)
            invincible[target_id] = max(0.0, 10.0 - elapsed)
        return True

    def robot_invincibility_remaining(
        self, target_id: int, *, team: str = "blue"
    ) -> float:
        if team not in ("red", "blue"):
            raise ValueError(f"unknown team {team}")
        if team == "red" and target_id == 8:
            return self.invincible_remaining
        timers = (
            self.robot_invincible_remaining
            if team == "blue"
            else self.own_robot_invincible_remaining
        )
        remaining = max(0.0, float(timers.get(target_id, 0.0)))
        if target_id == 2 and self.robot_in_assembly_gain(team, target_id):
            remaining = max(
                remaining,
                ASSEMBLY_GAIN_MAX_SECONDS
                - self.assembly_gain_elapsed.get(team, 0.0),
            )
        if target_id == 2 and self.robot_in_supply_gain(team, target_id):
            remaining = max(remaining, 1.0)
        return remaining

    def robot_effective_defence(self, target_id: int, *, team: str = "blue") -> float:
        """Return the live defence fraction used by the damage path."""
        if team not in ("red", "blue"):
            raise ValueError(f"unknown team {team}")
        if team == "red" and target_id == 8:
            return self.effective_sentry_defence
        # Tech-core defence is a persistent team reward for ground robots.
        # Same-type defence bonuses use the greatest value rather than adding.
        defence = self.assembly_defence if team == "red" else 0.0
        if target_id == 1 and self.hero_deployment_active(team):
            defence = max(defence, 0.25)
        if target_id == 2:
            health = (
                self.own_robot_hp.get(target_id, 0.0)
                if team == "red"
                else self.robot_hp.get(target_id, 0.0)
            )
            opening_cutoff = MATCH_DURATION - ENGINEER_OPENING_DEFENCE_SECONDS
            if (
                not self.game_finished
                and health > 0.0
                and self.remaining_time > opening_cutoff
            ):
                defence = max(defence, ENGINEER_OPENING_DEFENCE)
        defence = max(defence, self.terrain_crossing_defence(target_id, team=team))
        if self.robot_in_base_gain(team, target_id):
            defence = max(defence, BASE_GAIN_DEFENCE)
        if self.robot_in_trapezoid_gain(team, target_id):
            defence = max(defence, TRAPEZOID_GAIN_DEFENCE)
        if self.robot_in_central_highland(team, target_id):
            defence = max(defence, CENTRAL_HIGHLAND_DEFENCE)
        if self.robot_in_outpost_gain(team, target_id):
            defence = max(defence, OUTPOST_GAIN_DEFENCE)
        if self.robot_in_own_fort_gain(team, target_id):
            defence = max(defence, FORT_GAIN_DEFENCE)
        if self.enemy_fort_vulnerability_active(team, target_id):
            defence -= 1.0
        return max(-1.0, min(0.99, defence))

    def building_effective_defence(self, target_id: int, *, team: str) -> float:
        """Return persistent tech-core defence for an outpost or base."""
        if team not in ("red", "blue"):
            raise ValueError(f"unknown team {team}")
        if target_id not in (6, 7):
            raise ValueError(f"target {target_id} is not a building")
        return self.assembly_defence if team == "red" else 0.0

    @property
    def remote_heal_cost(self) -> int:
        return 50 + math.ceil((MATCH_DURATION - self.remaining_time) / 60.0) * 20

    @property
    def instant_revive_cost(self) -> int:
        return math.ceil((MATCH_DURATION - self.remaining_time) / 60.0) * 80 + 20

    @property
    def revive_seconds_required(self) -> float:
        return self.revive_seconds_required_for(8, team="red")

    def revive_seconds_required_for(
        self, target_id: int, *, team: str = "red"
    ) -> float:
        """Return the integer rulebook read-bar length fixed at death time."""
        if team not in ("red", "blue") or target_id not in GROUND_ROBOT_IDS:
            raise ValueError("unknown ground robot")
        revive_count = self.instant_revive_count if team == "red" and target_id == 8 else 0
        elapsed_tenths = math.floor(
            (MATCH_DURATION - self.remaining_time) / 10.0 + 0.5
        )
        return RULEBOOK_REVIVE_BASE + elapsed_tenths + 20.0 * revive_count

    def robot_out_of_combat_seconds_value(
        self, target_id: int, *, team: str = "blue"
    ) -> float:
        if team not in ("red", "blue") or target_id not in GROUND_ROBOT_IDS:
            raise ValueError("unknown ground robot")
        if team == "red" and target_id == 8:
            return self.sentry_out_of_combat_seconds
        timers = (
            self.robot_out_of_combat_seconds
            if team == "blue"
            else self.own_robot_out_of_combat_seconds
        )
        return max(0.0, float(timers.get(target_id, 0.0)))

    @property
    def sentry_is_out_of_combat(self) -> bool:
        """Whether the sentry is alive after six uninterrupted combat-free seconds."""
        return (
            self.sentry_hp > 0.0
            and self.sentry_out_of_combat_seconds >= OUT_OF_COMBAT_SECONDS
        )

    def _reset_robot_out_of_combat(self, target_id: int, *, team: str) -> None:
        if target_id not in GROUND_ROBOT_IDS:
            return
        if team == "red" and target_id == 8:
            self.sentry_out_of_combat_seconds = 0.0
            return
        timers = (
            self.robot_out_of_combat_seconds
            if team == "blue"
            else self.own_robot_out_of_combat_seconds
        )
        timers[target_id] = 0.0

    @property
    def sentry_chassis_power_cut(self) -> bool:
        return self.sentry_chassis_power_cut_remaining > 0.0

    def robot_chassis_power_cut(self, target_id: int, *, team: str) -> bool:
        if team == "red" and target_id == 8:
            return self.sentry_chassis_power_cut
        timers = (
            self.robot_chassis_power_cut_remaining
            if team == "blue"
            else self.own_robot_chassis_power_cut_remaining
        )
        return float(timers.get(target_id, 0.0)) > 0.0

    def robot_buffer_energy_value(self, target_id: int, *, team: str) -> float:
        if team == "red" and target_id == 8:
            return float(self.sentry_buffer_energy)
        values = (
            self.robot_buffer_energy
            if team == "blue"
            else self.own_robot_buffer_energy
        )
        return float(values.get(target_id, BUFFER_ENERGY_CAP))

    @property
    def sentry_fire_locked(self) -> bool:
        return self.sentry_heat_locked or self.sentry_heat_permanent_lock

    @property
    def radar_air_fire_locked(self) -> bool:
        """Whether radar countermeasure currently blocks aerial firing."""
        return self.radar_air_lock_remaining > 0.0

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
        route = (
            self.aggressive_patrol_route
            if self.patrol_is_aggressive
            else self.conservative_patrol_route
        )
        points = normalize_points(route)
        if len(points) >= 2:
            return points
        return AGGRESSIVE_PATROL_POINTS if self.patrol_is_aggressive else CONSERVATIVE_PATROL_POINTS

    def configure_patrol_routes(
        self,
        conservative: list[list[float]] | tuple[tuple[float, float], ...],
        aggressive: list[list[float]] | tuple[tuple[float, float], ...],
    ) -> None:
        """Install ordered referee-simulator patrol loops without changing policy."""
        conservative_points = normalize_points(conservative)
        aggressive_points = normalize_points(aggressive)
        if len(conservative_points) >= 2:
            self.conservative_patrol_route = [list(point) for point in conservative_points]
        if len(aggressive_points) >= 2:
            self.aggressive_patrol_route = [list(point) for point in aggressive_points]
        self.patrol_index %= len(self.patrol_points)

    def reset(self) -> None:
        field_zone_overrides = {
            name: [list(point) for point in points]
            for name, points in self.field_zone_overrides.items()
        }
        conservative_patrol_route = [list(point) for point in self.conservative_patrol_route]
        aggressive_patrol_route = [list(point) for point in self.aggressive_patrol_route]
        fresh = type(self)()
        fresh.field_zone_overrides = field_zone_overrides
        fresh.configure_patrol_routes(
            conservative_patrol_route,
            aggressive_patrol_route,
        )
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
        allowed = (1, 2, 3, 4, 5, 8)
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

    @staticmethod
    def _communication_receivers(sender: int | str) -> tuple[str, ...]:
        sender_key = str(sender)
        ordinary = tuple(str(target_id) for target_id in ORDINARY_COMMUNICATION_IDS)
        if sender_key == RADAR_COMMUNICATION_NODE:
            return tuple(str(target_id) for target_id in COMMUNICATION_ROBOT_IDS)
        if sender_key == "8":
            return ordinary + (RADAR_COMMUNICATION_NODE,)
        if sender_key in ordinary:
            return tuple(receiver for receiver in ordinary if receiver != sender_key)
        raise ValueError(f"unknown communication sender {sender}")

    def send_team_message(
        self,
        team: str,
        sender: int | str,
        channel: str,
        payload: dict,
    ) -> tuple[str, ...]:
        """Route one latest-value message using rulebook communication limits."""
        if team not in ("red", "blue"):
            raise ValueError(f"unknown team {team}")
        if not channel:
            raise ValueError("communication channel must not be empty")
        sender_key = str(sender)
        receivers = self._communication_receivers(sender_key)
        team_inboxes = self.team_communication_inboxes.setdefault(team, {})
        packet = {
            "sender": sender_key,
            "timestamp": self.match_elapsed,
            "payload": dict(payload),
        }
        for receiver in receivers:
            team_inboxes.setdefault(receiver, {})[channel] = packet
        return receivers

    def received_team_message(
        self,
        team: str,
        receiver: int | str,
        channel: str,
    ) -> dict | None:
        if team not in ("red", "blue"):
            raise ValueError(f"unknown team {team}")
        packet = (
            self.team_communication_inboxes.get(team, {})
            .get(str(receiver), {})
            .get(channel)
        )
        return packet if isinstance(packet, dict) else None

    def robot_view_angle(
        self,
        target_id: int,
        *,
        team: str,
        sentry: SentryState | None = None,
    ) -> float:
        if team not in ("red", "blue"):
            raise ValueError(f"unknown team {team}")
        if target_id not in COMMUNICATION_ROBOT_IDS:
            raise ValueError(f"unknown robot {target_id}")
        if team == "red" and target_id == 8 and sentry is not None:
            return float(sentry.turret_angle)
        return float(self.robot_view_angles.get(team, {}).get(target_id, 0.0))

    def set_robot_view_angle(
        self,
        target_id: int,
        angle: float,
        *,
        team: str,
    ) -> None:
        if team not in ("red", "blue"):
            raise ValueError(f"unknown team {team}")
        if target_id not in COMMUNICATION_ROBOT_IDS:
            raise ValueError(f"unknown robot {target_id}")
        self.robot_view_angles.setdefault(team, {})[target_id] = (
            float(angle) + math.pi
        ) % math.tau - math.pi

    def robot_turntable_mode(self, target_id: int, *, team: str) -> int:
        if team not in ("red", "blue"):
            raise ValueError(f"unknown team {team}")
        if target_id not in COMMUNICATION_ROBOT_IDS:
            raise ValueError(f"unknown robot {target_id}")
        return int(self.robot_turntable_modes.get(team, {}).get(target_id, 1))

    def set_robot_turntable_mode(
        self,
        target_id: int,
        mode: int,
        *,
        team: str,
    ) -> None:
        if mode not in ROBOT_TURNTABLE_SPEED_SCALE:
            raise ValueError("turntable mode must be 0, 1, 2, or 3")
        self.robot_turntable_modes.setdefault(team, {})[target_id] = int(mode)

    def cycle_robot_turntable_mode(self, target_id: int, *, team: str) -> int:
        mode = self.robot_turntable_mode(target_id, team=team)
        mode = 1 if mode >= 3 else mode + 1
        self.set_robot_turntable_mode(target_id, mode, team=team)
        labels = {1: "低速", 2: "中速", 3: "高速"}
        self._set_event(
            f"{'己方' if team == 'red' else '蓝方'} {target_id} 号小转盘切换为"
            f"{labels[mode]}"
        )
        return mode

    def robot_turntable_angle(
        self,
        target_id: int,
        *,
        team: str,
        sentry: SentryState | None = None,
    ) -> float:
        if team == "red" and target_id == 8 and sentry is not None:
            return float(sentry.spin_angle)
        return float(self.robot_turntable_angles.get(team, {}).get(target_id, 0.0))

    def robot_turntable_speed(self, target_id: int, *, team: str) -> float:
        mode = self.robot_turntable_mode(target_id, team=team)
        return ROBOT_TURNTABLE_SPEED * ROBOT_TURNTABLE_SPEED_SCALE[mode]

    def shooting_hit_probability(
        self,
        shooter_id: int,
        *,
        team: str,
        target_id: int | None = None,
    ) -> float:
        if target_id == 6:
            return OUTPOST_HIT_PROBABILITY
        mode = self.robot_turntable_mode(shooter_id, team=team)
        return ROBOT_TURNTABLE_HIT_PROBABILITY[mode]

    def _hit_random(self) -> float:
        self.hit_random_counter += 1
        return random.Random(self.hit_random_seed + self.hit_random_counter).random()

    def robot_visible_enemy_positions(
        self,
        target_id: int,
        *,
        team: str,
    ) -> dict[int, tuple[float, float]]:
        visible = self.robot_visible_positions.get(team, {}).get(target_id, {})
        return {
            int(enemy_id): (float(position[0]), float(position[1]))
            for enemy_id, position in visible.items()
        }

    @staticmethod
    def target_in_sensor_view(
        observer: tuple[float, float],
        target: tuple[float, float],
        view_angle: float,
        *,
        maximum_distance: float = DETECTION_RANGE,
        half_angle: float = ROBOT_VISION_HALF_ANGLE,
    ) -> bool:
        """Return whether target is inside the sensor cone.

        RMUC walls affect movement collision only.  They never occlude robot
        vision, target locking, radar information, or referee hit geometry.
        """
        delta_x = target[0] - observer[0]
        delta_y = target[1] - observer[1]
        distance = math.hypot(delta_x, delta_y)
        if distance > maximum_distance:
            return False
        target_angle = math.atan2(delta_y, delta_x)
        angle_error = abs(
            (target_angle - view_angle + math.pi) % math.tau - math.pi
        )
        return angle_error <= half_angle

    def _update_robot_perception(
        self,
        sentry: SentryState,
        elapsed_seconds: float,
    ) -> None:
        """Advance robot view angles, local vision, and routed position messages."""
        self.team_communication_inboxes = _initial_team_communication_inboxes()
        for team in ("red", "blue"):
            target_team = self.opposing_team(team)
            for target_id in COMMUNICATION_ROBOT_IDS:
                if team == "red" and target_id == 8:
                    self.robot_turntable_angles[team][target_id] = float(
                        sentry.spin_angle
                    )
                elif not self.robot_chassis_power_cut(target_id, team=team):
                    turntable_angle = self.robot_turntable_angle(
                        target_id,
                        team=team,
                    )
                    self.robot_turntable_angles[team][target_id] = (
                        turntable_angle
                        + self.robot_turntable_speed(target_id, team=team)
                        * max(0.0, elapsed_seconds)
                        + math.pi
                    ) % math.tau - math.pi
                if team == "red" and target_id == 8:
                    angle = float(sentry.turret_angle)
                    self.robot_view_angles[team][target_id] = angle
                else:
                    angle = self.robot_view_angle(target_id, team=team)
                    angle = (
                        angle + ROBOT_TURRET_SPEED * max(0.0, elapsed_seconds)
                        + math.pi
                    ) % math.tau - math.pi
                    self.robot_view_angles[team][target_id] = angle

                health = (
                    self.own_robot_health(target_id)
                    if team == "red"
                    else self.enemy_health(target_id)
                )
                visible: dict[int, list[float]] = {}
                if health > 0.0:
                    observer = self.combatant_position(
                        team,
                        target_id,
                        sentry=sentry,
                    )
                    for enemy_id in COMMUNICATION_ROBOT_IDS:
                        enemy_health = (
                            self.enemy_health(enemy_id)
                            if target_team == "blue"
                            else self.own_robot_health(enemy_id)
                        )
                        if enemy_health <= 0.0:
                            continue
                        enemy_position = self.combatant_position(
                            target_team,
                            enemy_id,
                            sentry=sentry,
                        )
                        if self.target_in_sensor_view(
                            observer,
                            enemy_position,
                            angle,
                        ):
                            visible[enemy_id] = [
                                float(enemy_position[0]),
                                float(enemy_position[1]),
                            ]
                self.robot_visible_positions[team][target_id] = visible

        for team in ("red", "blue"):
            target_team = self.opposing_team(team)
            for sender_id in COMMUNICATION_ROBOT_IDS:
                self.send_team_message(
                    team,
                    sender_id,
                    f"vision:{sender_id}",
                    {
                        "positions": dict(
                            self.robot_visible_positions[team][sender_id]
                        )
                    },
                )
            radar_positions = {
                enemy_id: list(
                    self.combatant_position(
                        target_team,
                        enemy_id,
                        sentry=sentry,
                    )
                )
                for enemy_id in COMMUNICATION_ROBOT_IDS
            }
            self.send_team_message(
                team,
                RADAR_COMMUNICATION_NODE,
                "radar_positions",
                {"positions": radar_positions},
            )

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
        previous_health = self.own_robot_hp[target_id]
        self.own_robot_hp[target_id] = max(
            0.0,
            min(float(entity.max_hp), self.own_robot_hp[target_id] + step * direction),
        )
        if self.own_robot_hp[target_id] < previous_health:
            self._reset_robot_out_of_combat(target_id, team="red")
        if previous_health > 0.0 and self.own_robot_hp[target_id] <= 0.0:
            self._mark_robot_death(target_id, team="red")
        elif self.own_robot_hp[target_id] > 0.0:
            self.own_robot_death_elapsed[target_id] = None
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

    @staticmethod
    def _level_index(level: int) -> int:
        return max(1, min(10, level)) - 1

    def robot_heat_limit(self, target_id: int, *, team: str = "blue") -> int | None:
        """Return Q0 using the selected level and launcher performance."""
        if target_id not in ROBOT_PROFILES:
            raise ValueError(f"unknown robot {target_id}")
        index = self._level_index(self.robot_level_value(target_id, team=team))
        if target_id == 1:
            table = HERO_HEAT_MELEE if self.hero_mode == "melee" else HERO_HEAT_RANGED
            return table[index]
        if target_id in (3, 4):
            table = (
                INFANTRY_HEAT_BURST
                if self.infantry_launcher_mode == "burst"
                else INFANTRY_HEAT_COOLING
            )
            return table[index]
        if target_id == 5:
            return AERIAL_HEAT[index]
        return ROBOT_PROFILES[target_id].heat_capacity

    def robot_heat_cooling_rate(
        self,
        target_id: int,
        *,
        team: str = "blue",
    ) -> float | None:
        """Return the rulebook heat cooling value per second."""
        if target_id not in ROBOT_PROFILES:
            raise ValueError(f"unknown robot {target_id}")
        index = self._level_index(self.robot_level_value(target_id, team=team))
        if target_id == 1:
            table = (
                HERO_COOLING_MELEE
                if self.hero_mode == "melee"
                else HERO_COOLING_RANGED
            )
            base = float(table[index])
        elif target_id in (3, 4):
            table = (
                INFANTRY_COOLING_BURST
                if self.infantry_launcher_mode == "burst"
                else INFANTRY_COOLING_COOLING
            )
            base = float(table[index])
        elif target_id == 5:
            base = float(AERIAL_COOLING[index])
        else:
            profile_cooling = ROBOT_PROFILES[target_id].heat_cooling_per_second
            if profile_cooling is None:
                return None
            base = float(profile_cooling)
        multiplied = base * max(
            1.0,
            self.buff_value("heat_cooling") if team == "red" else 1.0,
            self.terrain_crossing_cooling(target_id, team=team),
        )
        if target_id in FORT_ROBOT_IDS and self.robot_in_own_fort_gain(team, target_id):
            return max(multiplied, base + self.fortress_cooling_bonus(team))
        return multiplied

    def robot_power_limit(self, target_id: int, *, team: str = "blue") -> int | None:
        """Return the selected level/chassis power limit."""
        if target_id not in ROBOT_PROFILES:
            raise ValueError(f"unknown robot {target_id}")
        index = self._level_index(self.robot_level_value(target_id, team=team))
        if target_id == 1:
            table = HERO_POWER_MELEE if self.hero_mode == "melee" else HERO_POWER_RANGED
            return table[index]
        if target_id in (3, 4):
            table = (
                INFANTRY_POWER_POWER
                if self.infantry_chassis_mode == "power"
                else INFANTRY_POWER_BLOOD
            )
            return table[index]
        return ROBOT_PROFILES[target_id].power_limit

    def robot_muzzle_speed_limit(
        self,
        target_id: int,
        *,
        team: str = "blue",
    ) -> float | None:
        """Return the live muzzle-speed limit including hero deployment."""
        if target_id not in ROBOT_PROFILES:
            raise ValueError(f"unknown robot {target_id}")
        if target_id == 1 and self.hero_deployment_active(team):
            return 16.5
        return ROBOT_PROFILES[target_id].muzzle_speed_limit

    def robot_q2_limit(self, target_id: int, *, team: str = "blue") -> int | None:
        q0 = self.robot_heat_limit(target_id, team=team)
        projectile = ROBOT_PROFILES[target_id].projectile
        extra = HEAT_Q2_EXTRA.get(projectile)
        return None if q0 is None or extra is None else q0 + extra

    def robot_heat_lock_state(self, target_id: int, *, team: str = "blue") -> str:
        """Return ``normal``, ``q1`` or ``q2`` for referee/UI consumers."""
        if team not in ("red", "blue"):
            raise ValueError(f"unknown team {team}")
        if target_id == 8 and team == "red":
            if self.sentry_heat_permanent_lock:
                return "q2"
            return "q1" if self.sentry_heat_locked else "normal"
        temporary = self.robot_heat_locked if team == "blue" else self.own_robot_heat_locked
        permanent = (
            self.robot_heat_permanent_lock
            if team == "blue"
            else self.own_robot_heat_permanent_lock
        )
        if permanent.get(target_id, False):
            return "q2"
        return "q1" if temporary.get(target_id, False) else "normal"

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

    def robot_resource_limits(
        self,
        target_id: int,
        *,
        team: str = "blue",
    ) -> tuple[int | None, int | None]:
        if target_id not in ROBOT_PROFILES:
            raise ValueError(f"unknown robot {target_id}")
        return (
            self.robot_heat_limit(target_id, team=team),
            self.robot_power_limit(target_id, team=team),
        )

    def robot_level_value(self, target_id: int, *, team: str = "blue") -> int:
        levels = self.robot_level if team == "blue" else self.own_robot_level
        return levels.get(target_id, 1)

    def robot_level_cap(self, *, team: str = "blue") -> int:
        if team not in ("red", "blue"):
            raise ValueError(f"unknown team {team}")
        return self.level_cap if team == "red" else self.enemy_level_cap

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
            levels[target_id] < self.robot_level_cap(team=team)
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

    def _max_hp_snapshot(
        self,
        target_ids: tuple[int, ...],
    ) -> dict[tuple[str, int], float]:
        return {
            (team, target_id): self.robot_max_hp(target_id, team=team)
            for team in ("blue", "red")
            for target_id in target_ids
        }

    def _apply_max_hp_changes(
        self,
        previous: dict[tuple[str, int], float],
    ) -> None:
        for (team, target_id), old_max in previous.items():
            hp_map = self.robot_hp if team == "blue" else self.own_robot_hp
            if target_id not in hp_map or hp_map[target_id] <= 0.0:
                continue
            new_max = self.robot_max_hp(target_id, team=team)
            hp_map[target_id] = max(0.0, hp_map[target_id] + new_max - old_max)

    def _refresh_heat_locks(self, target_ids: tuple[int, ...]) -> None:
        for team in ("blue", "red"):
            for target_id in target_ids:
                self._evaluate_robot_heat_lock(target_id, team=team)

    def cycle_hero_mode(self) -> None:
        old = self._max_hp_snapshot((1,))
        self.hero_mode = "melee" if self.hero_mode == "ranged" else "ranged"
        if self.hero_mode != "ranged":
            self.hero_deployed = {"red": False, "blue": False}
        self._apply_max_hp_changes(old)
        self._refresh_heat_locks((1,))
        self._set_event(
            f"英雄整机：{'近战优先' if self.hero_mode == 'melee' else '远程优先'}"
        )

    def hero_deployment_active(self, team: str) -> bool:
        if team not in ("red", "blue"):
            raise ValueError(f"unknown team {team}")
        return self.hero_mode == "ranged" and bool(self.hero_deployed.get(team, False))

    def toggle_hero_deployment(self, team: str) -> bool:
        """Manually enter or exit ranged-priority hero deployment mode."""
        if team not in ("red", "blue"):
            raise ValueError(f"unknown team {team}")
        if self.hero_mode != "ranged":
            self._set_event("英雄需选择远程优先才能进入部署模式")
            return False
        self.hero_deployed[team] = not self.hero_deployed.get(team, False)
        state = "进入" if self.hero_deployed[team] else "退出"
        side = "己方" if team == "red" else "蓝方"
        self._set_event(f"{side}英雄{state}部署模式")
        return True

    def cycle_infantry_chassis(self) -> None:
        old = self._max_hp_snapshot((3, 4))
        self.infantry_chassis_mode = (
            "power" if self.infantry_chassis_mode == "blood" else "blood"
        )
        self._apply_max_hp_changes(old)
        self._set_event(
            "步兵底盘："
            + ("功率优先" if self.infantry_chassis_mode == "power" else "血量优先")
        )

    def cycle_infantry_launcher(self) -> None:
        self.infantry_launcher_mode = (
            "burst" if self.infantry_launcher_mode == "cooling" else "cooling"
        )
        self._refresh_heat_locks((3, 4))
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

    def robot_ammunition_limit(self, target_id: int) -> int:
        if target_id not in ROBOT_PROFILES:
            raise ValueError(f"unknown robot {target_id}")
        if target_id == 2:
            return 0
        if target_id == 5:
            return ROBOT_PROFILES[5].initial_ammo
        # The UI limit is a scenario-injection bound, not a claim about the
        # match's remote-exchange economy cap.
        return 1000

    def own_robot_ammunition_limit(self, target_id: int) -> int:
        return self.robot_ammunition_limit(target_id)

    def adjust_robot_ammunition(
        self,
        target_id: int,
        direction: int,
        *,
        team: str = "blue",
    ) -> None:
        if team not in ("red", "blue"):
            raise ValueError(f"unknown team {team}")
        self._validate_adjustment_direction(direction)
        maximum = self.robot_ammunition_limit(target_id)
        step = 20 if target_id != 5 else 25
        if target_id == 8 and team == "red":
            self.adjust_ammo(direction)
            return
        ammo = self.robot_ammo if team == "blue" else self.own_robot_ammo
        ammo[target_id] = max(0, min(maximum, ammo[target_id] + step * direction))
        self._set_event(
            f"{'蓝方' if team == 'blue' else '己方'} {target_id} 号机器人弹量"
            f"已调整为 {ammo[target_id]}"
        )

    def adjust_own_robot_ammunition(self, target_id: int, direction: int) -> None:
        self.adjust_robot_ammunition(target_id, direction, team="red")

    def _set_robot_heat_value(
        self,
        target_id: int,
        value: float,
        *,
        team: str,
        sentry: SentryState | None,
    ) -> None:
        value = max(0.0, float(value))
        if target_id == 8 and team == "red":
            if sentry is None:
                raise ValueError("red sentry heat requires sentry state")
            sentry.heat = value
            return
        heat = self.robot_heat if team == "blue" else self.own_robot_heat
        heat[target_id] = value

    def _evaluate_robot_heat_lock(
        self,
        target_id: int,
        *,
        team: str,
        sentry: SentryState | None = None,
    ) -> str:
        q0 = self.robot_heat_limit(target_id, team=team)
        q2 = self.robot_q2_limit(target_id, team=team)
        if q0 is None or q2 is None:
            return "normal"
        heat = self.robot_heat_value(target_id, team=team, sentry=sentry)
        if target_id == 8 and team == "red":
            if heat >= q2:
                self.sentry_heat_permanent_lock = True
                self.sentry_heat_locked = True
            elif heat > q0:
                self.sentry_heat_locked = True
            return self.robot_heat_lock_state(target_id, team=team)
        temporary = self.robot_heat_locked if team == "blue" else self.own_robot_heat_locked
        permanent = (
            self.robot_heat_permanent_lock
            if team == "blue"
            else self.own_robot_heat_permanent_lock
        )
        if heat >= q2:
            permanent[target_id] = True
            temporary[target_id] = True
        elif heat > q0:
            temporary[target_id] = True
        return self.robot_heat_lock_state(target_id, team=team)

    def record_robot_fire(
        self,
        target_id: int,
        shots: int = 1,
        *,
        team: str = "blue",
        sentry: SentryState | None = None,
    ) -> int:
        """Record referee-detected shots and apply ammunition/heat rules.

        This is intentionally a referee/Pygame operation.  It does not select
        targets, move robots, or alter any decision-tree output.
        """
        if team not in ("red", "blue"):
            raise ValueError(f"unknown team {team}")
        if target_id not in ROBOT_PROFILES:
            raise ValueError(f"unknown robot {target_id}")
        if shots <= 0:
            return 0
        if team == "blue" and target_id == 5 and self.radar_air_lock_remaining > 0.0:
            self._set_event("蓝方空中机器人被雷达反制，发射机构锁定")
            return 0
        if target_id in GROUND_ROBOT_IDS and self.robot_is_weak(target_id, team=team):
            self._set_event(f"{ROBOT_PROFILES[target_id].role}处于虚弱状态，发射机锁定")
            return 0
        profile = ROBOT_PROFILES[target_id]
        if profile.heat_per_shot is None or profile.projectile not in HEAT_Q2_EXTRA:
            self._set_event(f"{profile.role}没有可记录的发射机构")
            return 0
        if self.robot_heat_lock_state(target_id, team=team) != "normal":
            self._set_event(f"{profile.role}发射机构已被热量锁定")
            return 0
        available = self.robot_available_shots(target_id, team=team)
        fired = min(int(shots), available)
        multiplier = (
            self.posture_heat_gain_multiplier
            if target_id == 8 and team == "red"
            else 1.0
        )
        heat_per_shot = float(profile.heat_per_shot) * multiplier
        q0 = self.robot_heat_limit(target_id, team=team)
        heat = self.robot_heat_value(target_id, team=team, sentry=sentry)
        if heat_per_shot > 0.0 and q0 is not None:
            # A long render frame must not bypass the referee lock by settling
            # every accumulated projectile as one unrestricted batch.  Allow
            # only the first projectile that crosses Q0; subsequent shots wait
            # until the launcher has cooled and unlocked.
            shots_until_lock = max(
                1,
                int(math.floor(max(0.0, float(q0) - heat) / heat_per_shot)) + 1,
            )
            fired = min(fired, shots_until_lock)
        if fired <= 0:
            self._set_event(f"{profile.role}允许发弹量不足")
            return 0
        reserve_cost = self.fortress_reserve_cost_per_shot(target_id)
        reserve_shots = min(
            fired,
            self.fortress_reserve_shots_available(target_id, team=team),
        )
        if reserve_shots > 0:
            self.fort_reserve_ammo[team] = max(
                0,
                self.fort_reserve_ammo.get(team, 0) - reserve_shots * reserve_cost,
            )
        own_ammo_shots = fired - reserve_shots
        if target_id == 8 and team == "red":
            self.ammo -= own_ammo_shots
        elif team == "blue":
            self.robot_ammo[target_id] -= own_ammo_shots
        else:
            self.own_robot_ammo[target_id] -= own_ammo_shots
        self._set_robot_heat_value(
            target_id,
            heat + fired * heat_per_shot,
            team=team,
            sentry=sentry,
        )
        state = self._evaluate_robot_heat_lock(
            target_id,
            team=team,
            sentry=sentry,
        )
        self._reset_robot_out_of_combat(target_id, team=team)
        suffix = "，Q2 永久锁定" if state == "q2" else "，Q1 锁定" if state == "q1" else ""
        self._set_event(
            f"{'蓝方' if team == 'blue' else '己方'} {target_id} 号发射 {fired} 发，"
            f"热量 {self.robot_heat_value(target_id, team=team, sentry=sentry):.0f}{suffix}"
        )
        return fired

    @staticmethod
    def opposing_team(team: str) -> str:
        if team == "red":
            return "blue"
        if team == "blue":
            return "red"
        raise ValueError(f"unknown team {team}")

    def combatant_position(
        self,
        team: str,
        target_id: int,
        *,
        sentry: SentryState | None = None,
    ) -> tuple[float, float]:
        """Return a robot/building position in the shared referee frame."""
        if team not in ("red", "blue"):
            raise ValueError(f"unknown team {team}")
        if target_id == 6:
            return RED_OUTPOST if team == "red" else BLUE_OUTPOST
        if target_id == 7:
            return RED_BASE if team == "red" else BLUE_BASE
        if target_id not in ROBOT_PROFILES:
            raise ValueError(f"unknown target {target_id}")
        if team == "red" and target_id == 8:
            if sentry is None:
                raise ValueError("red sentry position requires sentry state")
            return sentry.x, sentry.y
        return self.robot_position(target_id, team=team)

    def robot_can_fire(
        self,
        target_id: int,
        *,
        team: str,
        sentry: SentryState | None = None,
    ) -> tuple[bool, str]:
        """Return referee fire eligibility without choosing any behavior."""
        if team not in ("red", "blue"):
            raise ValueError(f"unknown team {team}")
        if target_id not in ROBOT_PROFILES:
            raise ValueError(f"unknown robot {target_id}")
        profile = ROBOT_PROFILES[target_id]
        if profile.heat_per_shot is None or profile.projectile not in HEAT_Q2_EXTRA:
            return False, "no_launcher"
        if self.game_finished or not self.game_running:
            return False, "match_inactive"
        if self.game_paused:
            return False, "match_paused"
        if self._target_health_total(target_id, team=team) <= 0.0:
            return False, "robot_destroyed"
        if self.robot_is_weak(target_id, team=team):
            return False, "weak_state"
        if team == "red" and target_id == 8 and self.respawn_fire_locked:
            return False, "respawn_fire_locked"
        if team == "blue" and target_id == 5 and self.radar_air_lock_remaining > 0.0:
            return False, "radar_countermeasure_locked"
        if self.robot_heat_lock_state(target_id, team=team) != "normal":
            return False, "heat_locked"
        if self.robot_available_shots(target_id, team=team) <= 0:
            return False, "no_ammo"
        if team == "red" and target_id == 8 and sentry is None:
            return False, "missing_sentry_state"
        return True, "ready"

    def settle_robot_fire(
        self,
        shooter_id: int,
        shots: int = 1,
        *,
        team: str,
        sentry: SentryState | None = None,
        shot: FireSolution | None = None,
        attack_buff: float = 1.0,
        target_defence_buff: float | None = None,
        critical_zone: bool | None = None,
        target_armor_zone: str | None = None,
    ) -> FireResult:
        """Consume resources and settle an already supplied shot solution."""
        profile = ROBOT_PROFILES.get(shooter_id)
        if profile is None:
            raise ValueError(f"unknown robot {shooter_id}")
        ready, reason = self.robot_can_fire(
            shooter_id,
            team=team,
            sentry=sentry,
        )
        if not ready:
            return FireResult(team, shooter_id, profile.projectile, reason=reason)
        fired = self.record_robot_fire(
            shooter_id,
            shots,
            team=team,
            sentry=sentry,
        )
        if fired <= 0:
            return FireResult(team, shooter_id, profile.projectile, reason="fire_rejected")
        if shot is None:
            self.last_hit_probability = 0.0
            self.last_hit_roll = None
            return FireResult(
                team,
                shooter_id,
                profile.projectile,
                fired_shots=fired,
                reason="fired_miss",
            )

        target_team = self.opposing_team(team)
        hit_probability = self.shooting_hit_probability(
            shooter_id,
            team=team,
            target_id=shot.target_id,
        )
        self.last_hit_probability = hit_probability
        self.last_hit_roll = (
            self._hit_random() if hit_probability < 1.0 else None
        )
        if (
            self.last_hit_roll is not None
            and self.last_hit_roll >= hit_probability
        ):
            return FireResult(
                team,
                shooter_id,
                profile.projectile,
                fired_shots=fired,
                target_team=target_team,
                target_id=shot.target_id,
                reason="fired_miss",
                shot=shot,
            )
        if critical_zone is None:
            # The 2-D point-target model has no vertical impact coordinate and
            # therefore cannot prove a hit landed inside the physical
            # 10 mm x 10 mm building critical area.  Critical damage remains
            # available to explicit referee/test callers via critical_zone.
            critical_zone = False
        if target_armor_zone is None:
            shooter_position = self.combatant_position(
                team,
                shooter_id,
                sentry=sentry,
            )
            target_armor_zone = self.armor_zone_for_position(
                shot,
                shooter_position,
                target_team=target_team,
            )
        if (
            shooter_id == 1
            and shot.target_id == 7
            and self.hero_deployment_active(team)
        ):
            attack_buff = max(attack_buff, 1.5)
        damage = self.apply_attack_damage(
            shot.target_id,
            profile.projectile,
            attack_buff=attack_buff,
            defence_buff=target_defence_buff,
            critical_zone=bool(critical_zone),
            armor_zone=target_armor_zone,
            shots=fired,
            team=target_team,
        )
        return FireResult(
            team,
            shooter_id,
            profile.projectile,
            fired_shots=fired,
            target_team=target_team,
            target_id=shot.target_id,
            damage=damage,
            reason="fired",
            shot=shot,
        )

    def execute_robot_fire(
        self,
        shooter_id: int,
        aim_angle: float,
        shots: int = 1,
        *,
        team: str,
        sentry: SentryState | None = None,
        preferred_target: int = 0,
        maximum_distance: float = WEAPON_RANGE,
        alignment_tolerance: float = FIRE_ALIGNMENT_TOLERANCE,
        line_of_sight: "Callable[[tuple[float, float], tuple[float, float]], bool] | None" = None,
        attack_buff: float = 1.0,
        target_defence_buff: float | None = None,
    ) -> FireResult:
        """Run the full referee firing chain for any projectile robot.

        Target selection and aim generation remain outside this method.  A
        manual controller, replay source or future global automation layer can
        submit the same intent without changing referee calculations.
        """
        profile = ROBOT_PROFILES.get(shooter_id)
        if profile is None:
            raise ValueError(f"unknown robot {shooter_id}")
        ready, reason = self.robot_can_fire(
            shooter_id,
            team=team,
            sentry=sentry,
        )
        if not ready:
            return FireResult(team, shooter_id, profile.projectile, reason=reason)
        shot = self.resolve_robot_fire_shot(
            shooter_id,
            aim_angle,
            team=team,
            sentry=sentry,
            preferred_target=preferred_target,
            maximum_distance=maximum_distance,
            alignment_tolerance=alignment_tolerance,
            line_of_sight=line_of_sight,
        )
        return self.settle_robot_fire(
            shooter_id,
            shots,
            team=team,
            sentry=sentry,
            shot=shot,
            attack_buff=attack_buff,
            target_defence_buff=target_defence_buff,
        )

    def target_position(self, target_id: int) -> tuple[float, float]:
        return self.combatant_position("blue", target_id)

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

        ``line_of_sight`` remains accepted for integration compatibility, but
        field walls do not block referee hit detection in this simulation.
        """
        return self.resolve_robot_fire_shot(
            8,
            sentry.turret_angle,
            team="red",
            sentry=sentry,
            preferred_target=preferred_target,
            maximum_distance=maximum_distance,
            alignment_tolerance=alignment_tolerance,
            line_of_sight=line_of_sight,
        )

    def resolve_robot_fire_shot(
        self,
        shooter_id: int,
        aim_angle: float,
        *,
        team: str,
        sentry: SentryState | None = None,
        preferred_target: int = 0,
        maximum_distance: float = WEAPON_RANGE,
        alignment_tolerance: float = FIRE_ALIGNMENT_TOLERANCE,
        line_of_sight: "Callable[[tuple[float, float], tuple[float, float]], bool] | None" = None,
    ) -> FireSolution | None:
        """Resolve shot geometry without choosing when or where to aim."""
        if shooter_id not in ROBOT_PROFILES:
            raise ValueError(f"unknown robot {shooter_id}")
        if maximum_distance <= 0.0 or alignment_tolerance < 0.0:
            raise ValueError("fire geometry limits must be non-negative")
        shooter_position = self.combatant_position(team, shooter_id, sentry=sentry)
        target_team = self.opposing_team(team)
        candidates = (
            (preferred_target,)
            if preferred_target
            else (*ROBOT_PROFILES.keys(), 6, 7)
        )
        aligned: list[tuple[float, float, int]] = []
        for target_id in candidates:
            try:
                health = self._target_health_total(target_id, team=target_team)
                target_x, target_y = self.combatant_position(
                    target_team,
                    target_id,
                    sentry=sentry,
                )
            except ValueError:
                continue
            if health <= 0.0 or health == 1001.0:
                continue
            delta_x = target_x - shooter_position[0]
            delta_y = target_y - shooter_position[1]
            distance = math.hypot(delta_x, delta_y)
            if distance > maximum_distance:
                continue
            target_angle = math.atan2(delta_y, delta_x)
            angle_error = abs(
                (target_angle - aim_angle + math.pi) % math.tau - math.pi
            )
            if angle_error > alignment_tolerance:
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

    def armor_zone_for_shot(
        self,
        shot: FireSolution,
        sentry: SentryState,
        *,
        team: str = "blue",
    ) -> str | None:
        """Return the 2-D armour zone used by the live damage path."""
        return self.armor_zone_for_position(
            shot,
            (sentry.x, sentry.y),
            target_team=team,
        )

    @staticmethod
    def armor_zone_for_position(
        shot: FireSolution,
        shooter_position: tuple[float, float],
        *,
        target_team: str,
    ) -> str | None:
        """Return building armour zone for a generic robot shooter."""
        if shot.target_id == 6:
            return "normal"
        if shot.target_id != 7:
            return None
        if target_team not in ("red", "blue"):
            raise ValueError(f"unknown team {target_team}")
        base_x = BLUE_BASE[0] if target_team == "blue" else RED_BASE[0]
        front_direction = -1.0 if target_team == "blue" else 1.0
        # A base's upper-front armour faces the field.  Side/rear hits use the
        # remaining five plates and therefore the normal 17mm raw damage.
        in_front = front_direction * (shooter_position[0] - base_x) > 0.0
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

        previous_health = self.enemy_health(target_id)
        step = 500.0 if target_id == 7 else 100.0 if target_id == 6 else max(10.0, entity.max_hp / 10.0)
        health = max(0.0, min(float(entity.max_hp), self.enemy_health(target_id) + step * direction))
        if target_id == 6:
            self.enemy_outpost_hp = health
            if health <= 0.0:
                self.enemy_outpost_destroyed_ever = True
            name = "敌方前哨"
        elif target_id == 7:
            previous_base_hp = self.enemy_base_hp
            self.enemy_base_hp = health
            self._record_base_hp_damage(
                "blue", max(0.0, previous_base_hp - self.enemy_base_hp)
            )
            self._record_base_minimum("blue")
            name = "敌方基地"
        else:
            self.robot_hp[target_id] = health
            if health < previous_health and target_id in GROUND_ROBOT_IDS:
                self._reset_robot_out_of_combat(target_id, team="blue")
            if previous_health > 0.0 and health <= 0.0 and target_id in GROUND_ROBOT_IDS:
                self._mark_robot_death(target_id, team="blue")
            elif health > 0.0 and target_id in self.robot_death_elapsed:
                self.robot_death_elapsed[target_id] = None
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

    def exchange_17mm(
        self,
        *,
        remote: bool,
        sentry: SentryState | None = None,
    ) -> bool:
        """Exchange sentry 17mm ammunition using rulebook table 5-6."""
        allowed, reason = self.can_exchange_17mm(remote=remote, sentry=sentry)
        if not allowed:
            self._set_event(reason)
            return False
        if remote:
            cost = REMOTE_17MM_COST
            amount = REMOTE_17MM_AMOUNT
        else:
            cost = LOCAL_17MM_COST
            amount = LOCAL_17MM_AMOUNT
        self.economy -= cost
        self.exchanged_17mm += amount
        if remote:
            self.remote_ammo_pending += amount
            self.remote_ammo_remaining = REMOTE_EXCHANGE_DELAY
            self._set_event(
                f"远程兑换 {amount} 发，6 秒后生效｜"
                f"金币 -{cost}，剩余 {self.economy}"
            )
        else:
            space = max(0, AMMO_CAP - self.ammo)
            transferred = min(space, amount)
            self.ammo += transferred
            self.pending_ammo += amount - transferred
            self._set_event(
                f"增益点本地兑换 {amount} 发｜"
                f"金币 -{cost}，剩余 {self.economy}"
            )
        return True

    def can_exchange_17mm(
        self,
        *,
        remote: bool,
        sentry: SentryState | None = None,
    ) -> tuple[bool, str]:
        """Return whether the sentry can buy one 17 mm exchange unit."""
        cost = REMOTE_17MM_COST if remote else LOCAL_17MM_COST
        amount = REMOTE_17MM_AMOUNT if remote else LOCAL_17MM_AMOUNT
        if self.sentry_hp <= 0.0:
            return False, "哨兵已阵亡，不能兑换弹量"
        if remote:
            if not self.sentry_is_out_of_combat:
                remaining = OUT_OF_COMBAT_SECONDS - self.sentry_out_of_combat_seconds
                return False, f"远程兑换需脱战，还需 {remaining:.1f} 秒"
        else:
            inside_base_gain = self.robot_in_base_gain("red", 8)
            inside_outpost_gain = self.robot_in_outpost_gain("red", 8)
            inside_supply_gain = self.robot_in_supply_gain("red", 8)
            if sentry is not None:
                inside_base_gain = self._position_in_base_gain(
                    "red", (sentry.x, sentry.y)
                )
                inside_outpost_gain = any(
                    self._outpost_gain_zone_available("red", zone_team)
                    and self._position_in_outpost_gain(
                        zone_team, (sentry.x, sentry.y)
                    )
                    for zone_team in ("red", "blue")
                )
                inside_supply_gain = self._robot_position_in_supply_gain(
                    "red", 8, sentry
                )
            if not inside_base_gain and not inside_outpost_gain and not inside_supply_gain:
                return False, "需位于补给区、基地或可用前哨增益点"
        if self.economy < cost:
            return False, f"金币不足：需要 {cost}"
        if self.exchanged_17mm + amount > AMMO_EXCHANGE_CAP_17MM:
            return False, "已达到 17mm 兑换上限"
        return True, "可兑换"

    def exchange_remote_heal(self) -> bool:
        cost = self.remote_heal_cost
        allowed, reason = self.can_exchange_remote_heal()
        if not allowed:
            self._set_event(reason)
            return False
        self.economy -= cost
        self.remote_heal_remaining = REMOTE_HEAL_DELAY
        self._set_event(
            f"远程回血已购买，6 秒后生效｜"
            f"金币 -{cost}，剩余 {self.economy}"
        )
        return True

    def can_exchange_remote_heal(self) -> tuple[bool, str]:
        if self.sentry_hp <= 0.0:
            return False, "哨兵已阵亡，无法远程回血"
        if not self.sentry_is_out_of_combat:
            remaining = OUT_OF_COMBAT_SECONDS - self.sentry_out_of_combat_seconds
            return False, f"远程回血需脱战，还需 {remaining:.1f} 秒"
        if self.remote_heal_remaining is not None:
            return False, "远程回血已在等待生效"
        cost = self.remote_heal_cost
        if self.economy < cost:
            return False, f"金币不足：远程回血需要 {cost}"
        return True, "可远程回血"

    def exchange_instant_revive(self) -> bool:
        cost = self.instant_revive_cost
        allowed, reason = self.can_exchange_instant_revive()
        if not allowed:
            self._set_event(reason)
            return False
        self.economy -= cost
        self.instant_revive_count += 1
        self.sentry_hp = 400.0
        self.death_elapsed = None
        self.revive_progress = 0.0
        self.revive_required = 0.0
        self.invincible_remaining = INSTANT_REVIVE_INVINCIBLE
        self.weak_state = True
        self.revive_invincibility_source = "instant"
        self.instant_revive_power_boost_remaining = INSTANT_REVIVE_POWER_BOOST
        self.respawn_fire_locked = True
        self.sentry_heat_locked = self.sentry_heat_permanent_lock
        self.sentry_buffer_energy = self.effective_buffer_cap
        self._set_event(
            f"立即复活｜金币 -{cost}，剩余 {self.economy}"
        )
        return True

    def can_exchange_instant_revive(self) -> tuple[bool, str]:
        if self.sentry_hp > 0.0 or self.death_elapsed is None:
            return False, "仅哨兵阵亡且复活读条进行中可立即复活"
        cost = self.instant_revive_cost
        if self.economy < cost:
            return False, f"金币不足：立即复活需要 {cost}"
        return True, "可立即复活"

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
        previous_base_hp = self.own_base_hp
        self.own_base_hp = max(0, min(self.own_base_max_hp, self.own_base_hp + 500 * direction))
        self._record_base_hp_damage(
            "red", max(0.0, previous_base_hp - self.own_base_hp)
        )
        self._record_base_minimum("red")
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
    ) -> DecisionView:
        if elapsed_seconds < 0.0:
            raise ValueError("elapsed_seconds must be non-negative")
        self.pending_ammo = max(0, min(PENDING_AMMO_CAP, self.pending_ammo))
        self._finish_if_base_destroyed()
        simulation_elapsed = 0.0 if self.game_paused else elapsed_seconds

        self.sentry_out_of_combat_seconds = (
            min(
                OUT_OF_COMBAT_SECONDS,
                self.sentry_out_of_combat_seconds + simulation_elapsed,
            )
            if self.sentry_hp > 0.0
            else 0.0
        )
        for team in ("red", "blue"):
            timers = (
                self.own_robot_out_of_combat_seconds
                if team == "red"
                else self.robot_out_of_combat_seconds
            )
            for target_id in timers:
                health = (
                    self.own_robot_health(target_id)
                    if team == "red"
                    else self.enemy_health(target_id)
                )
                timers[target_id] = (
                    min(OUT_OF_COMBAT_SECONDS, timers[target_id] + simulation_elapsed)
                    if health > 0.0
                    else 0.0
                )
        self._update_heat_cooling(sentry, simulation_elapsed)

        self._update_other_robot_power(simulation_elapsed)
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

        if not self.game_paused:
            self._update_buffs(simulation_elapsed)
            self._update_rune(simulation_elapsed)
            if not self.game_finished:
                self._update_dart(simulation_elapsed)
                self._update_radar(simulation_elapsed)
                self._update_economy_timers(sentry, simulation_elapsed)
                if self.game_running:
                    # Existing assembly income accrues before a newly completed
                    # attempt begins contributing on the following referee tick.
                    self._update_assembly_bonus(simulation_elapsed)
                    self._update_assembly(simulation_elapsed)
            if not self.game_finished and self.sentry_hp > 0.0:
                self._update_power(sentry, simulation_elapsed)
            if not self.game_finished:
                self._update_respawn(sentry, simulation_elapsed)
                self._update_robot_respawns(simulation_elapsed)
                self._update_base_gain_points(sentry, simulation_elapsed)
                self._update_trapezoid_gain_points(sentry, simulation_elapsed)
                self._update_central_highland_gain_points(sentry, simulation_elapsed)
                self._update_outpost_rebuild(sentry, simulation_elapsed)
                self._update_outpost_gain_points(sentry, simulation_elapsed)
                self._update_assembly_gain_points(sentry, simulation_elapsed)
                self._update_supply(sentry, simulation_elapsed)
                self._update_fort_gain_points(sentry, simulation_elapsed)
                self._update_terrain_crossing(sentry, simulation_elapsed)
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
        elif decision.confirm_respawn:
            self._confirm_task_respawn(sentry)
        if not self.game_paused and not self.game_finished:
            self._update_posture(decision.posture, simulation_elapsed)
        requested = bool(decision.shoot_mode) if fire_request is None else fire_request
        if self.game_finished:
            requested = False
        if (
            requested
            and self.robot_available_shots(8, team="red") > 0
            and not self.respawn_fire_locked
            and not self.sentry_fire_locked
        ):
            self._ammo_shot_accumulator += self.fire_rate * simulation_elapsed
            requested_shots = min(
                int(self._ammo_shot_accumulator),
                self.robot_available_shots(8, team="red"),
            )
            if requested_shots:
                result = self.settle_robot_fire(
                    8,
                    requested_shots,
                    team="red",
                    sentry=sentry,
                    shot=(
                        FireSolution(hit_target_id, 0.0, 0.0)
                        if hit_target_id is not None
                        else None
                    ),
                    attack_buff=attack_buff,
                    target_defence_buff=target_defence_buff,
                    critical_zone=critical_zone,
                    target_armor_zone=target_armor_zone,
                )
                if result.fired:
                    self._ammo_shot_accumulator -= result.fired_shots
        self._update_robot_perception(sentry, simulation_elapsed)
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
        if (
            target_id in GROUND_ROBOT_IDS
            and self.robot_invincibility_remaining(target_id, team=team) > 0.0
        ):
            return 0
        if defence_buff is None:
            if target_id in GROUND_ROBOT_IDS:
                defence_buff = self.robot_effective_defence(target_id, team=team)
            elif target_id in (6, 7):
                defence_buff = self.building_effective_defence(target_id, team=team)
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
                previous_base_hp = self.own_base_hp
                self.own_base_hp = max(0, self.own_base_hp - int(damage - shield_damage))
                self._record_base_hp_damage(
                    "red", max(0.0, previous_base_hp - self.own_base_hp)
                )
                self._record_base_minimum("red")
            elif target_id == 8:
                previous_health = self.sentry_hp
                self.sentry_hp = max(0.0, self.sentry_hp - damage)
                self.sentry_out_of_combat_seconds = 0.0
                if previous_health > 0.0 and self.sentry_hp == 0.0:
                    self._mark_sentry_death()
            elif target_id in self.own_robot_hp:
                previous_health = self.own_robot_hp[target_id]
                self.own_robot_hp[target_id] = max(0.0, self.own_robot_hp[target_id] - damage)
                self._reset_robot_out_of_combat(target_id, team="red")
                if (
                    target_id in GROUND_ROBOT_IDS
                    and previous_health > 0.0
                    and self.own_robot_hp[target_id] <= 0.0
                ):
                    self._mark_robot_death(target_id, team="red")
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
            previous_base_hp = self.enemy_base_hp
            self.enemy_base_hp = max(0.0, self.enemy_base_hp - remaining_damage)
            self._record_base_hp_damage(
                "blue", max(0.0, previous_base_hp - self.enemy_base_hp)
            )
            self._record_base_minimum("blue")
        elif target_id in self.robot_hp:
            previous_health = self.robot_hp[target_id]
            self.robot_hp[target_id] = max(0.0, self.robot_hp[target_id] - damage)
            if target_id in GROUND_ROBOT_IDS:
                self._reset_robot_out_of_combat(target_id, team="blue")
            if (
                target_id in GROUND_ROBOT_IDS
                and previous_health > 0.0
                and self.robot_hp[target_id] <= 0.0
            ):
                self._mark_robot_death(target_id, team="blue")
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
                and self.robot_available_shots(8, team="red") > 0
                and not self.respawn_fire_locked
            )
        elif self.robot_available_shots(8, team="red") == 0:
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

    def _update_heat_cooling(
        self,
        sentry: SentryState,
        elapsed_seconds: float,
    ) -> None:
        """Apply heat cooling on the referee system's 100 ms clock."""
        if self.active_posture == 1 and self.posture_mode == "reinforced":
            sentry.heat = 0.0
            if self.sentry_heat_locked and not self.sentry_heat_permanent_lock:
                self.sentry_heat_locked = False
        if elapsed_seconds <= 0.0:
            return
        self.heat_cooling_accumulator += elapsed_seconds
        ticks = int((self.heat_cooling_accumulator + 1e-9) / HEAT_COOLING_PERIOD)
        if ticks <= 0:
            return
        self.heat_cooling_accumulator = max(
            0.0,
            self.heat_cooling_accumulator - ticks * HEAT_COOLING_PERIOD,
        )
        duration = ticks * HEAT_COOLING_PERIOD
        unlocked: list[str] = []

        sentry.heat = max(
            0.0,
            sentry.heat - self.effective_sentry_heat_cooling * duration,
        )
        if (
            sentry.heat <= 0.0
            and self.sentry_heat_locked
            and not self.sentry_heat_permanent_lock
        ):
            self.sentry_heat_locked = False
            unlocked.append("己方 8 号")

        for team in ("red", "blue"):
            heat = self.own_robot_heat if team == "red" else self.robot_heat
            temporary = (
                self.own_robot_heat_locked if team == "red" else self.robot_heat_locked
            )
            permanent = (
                self.own_robot_heat_permanent_lock
                if team == "red"
                else self.robot_heat_permanent_lock
            )
            for target_id in ROBOT_PROFILES:
                if team == "red" and target_id == 8:
                    continue
                cooling = self.robot_heat_cooling_rate(target_id, team=team)
                if cooling is None:
                    continue
                heat[target_id] = max(0.0, heat[target_id] - cooling * duration)
                if (
                    heat[target_id] <= 0.0
                    and temporary.get(target_id, False)
                    and not permanent.get(target_id, False)
                ):
                    temporary[target_id] = False
                    unlocked.append(
                        f"{'己方' if team == 'red' else '蓝方'} {target_id} 号"
                    )
        if unlocked:
            self._set_event("热量冷却至 0，发射机构解锁：" + "、".join(unlocked))

    def _mark_sentry_death(self) -> None:
        self.active_buffs = [
            buff for buff in self.active_buffs if buff.source != "terrain_road"
        ]
        self.road_crossing_side = None
        self.road_crossing_elapsed = 0.0
        self._clear_terrain_crossing_robot(8, team="red")
        self._clear_central_highland_robot(8, team="red")
        self._clear_gain_exit_grace_robot(8, team="red")
        self.outpost_rebuild_progress["red"][8] = 0.0
        self.death_elapsed = 0.0
        self.revive_progress = 0.0
        self.revive_required = self.revive_seconds_required
        self.remote_heal_remaining = None
        self.instant_revive_power_boost_remaining = 0.0
        self.revive_invincibility_source = ""
        self.sentry_out_of_combat_seconds = 0.0
        self.sentry_buffer_energy = self.effective_buffer_cap
        self.base_gain_occupants["red"] = [
            target_id
            for target_id in self.base_gain_occupants.get("red", [])
            if target_id != 8
        ]
        self.trapezoid_gain_occupants["red"] = [
            target_id
            for target_id in self.trapezoid_gain_occupants.get("red", [])
            if target_id != 8
        ]
        self.outpost_gain_occupants["red"] = [
            target_id
            for target_id in self.outpost_gain_occupants.get("red", [])
            if target_id != 8
        ]
        self.supply_gain_occupants["red"] = [
            target_id
            for target_id in self.supply_gain_occupants.get("red", [])
            if target_id != 8
        ]
        if 8 in self.fort_own_occupants.get("red", []):
            self.fort_own_occupants["red"] = []
            self.fort_reserve_ammo["red"] = 0
            self.fort_reserve_capacity["red"] = 0
        self.fort_enemy_occupants["red"] = [
            target_id
            for target_id in self.fort_enemy_occupants.get("red", [])
            if target_id != 8
        ]
        if not self.base_gain_occupants["red"]:
            self.zone_inside.discard(BASE_GAIN_ZONE_IDS["red"])
        if not self.trapezoid_gain_occupants["red"]:
            self.zone_inside.discard(TRAPEZOID_GAIN_ZONE_IDS["red"])
        if not any(self.outpost_gain_occupants.values()):
            for zone_id in OUTPOST_GAIN_ZONE_IDS.values():
                self.zone_inside.discard(zone_id)

    def _mark_robot_death(self, target_id: int, *, team: str) -> None:
        """Start the common respawn state machine for a non-player ground robot."""
        if target_id not in GROUND_ROBOT_IDS or (team == "red" and target_id == 8):
            return
        if team == "blue":
            death, progress, required = (
                self.robot_death_elapsed,
                self.robot_revive_progress,
                self.robot_revive_required,
            )
            weak = self.robot_weak_state
            invincible = self.robot_invincible_remaining
        elif team == "red":
            death, progress, required = (
                self.own_robot_death_elapsed,
                self.own_robot_revive_progress,
                self.own_robot_revive_required,
            )
            weak = self.own_robot_weak_state
            invincible = self.own_robot_invincible_remaining
        else:
            raise ValueError(f"unknown team {team}")
        death[target_id] = 0.0
        progress[target_id] = 0.0
        required[target_id] = self.revive_seconds_required_for(target_id, team=team)
        weak[target_id] = False
        invincible[target_id] = 0.0
        sources = (
            self.robot_revive_invincibility_source
            if team == "blue"
            else self.own_robot_revive_invincibility_source
        )
        sources[target_id] = ""
        self._clear_terrain_crossing_robot(target_id, team=team)
        self._clear_central_highland_robot(target_id, team=team)
        self._clear_gain_exit_grace_robot(target_id, team=team)
        self.outpost_rebuild_progress[team][target_id] = 0.0
        self._reset_robot_out_of_combat(target_id, team=team)
        heat = self.robot_heat if team == "blue" else self.own_robot_heat
        temporary = self.robot_heat_locked if team == "blue" else self.own_robot_heat_locked
        permanent = (
            self.robot_heat_permanent_lock
            if team == "blue"
            else self.own_robot_heat_permanent_lock
        )
        heat[target_id] = 0.0
        temporary[target_id] = bool(permanent.get(target_id, False))
        self.base_gain_occupants[team] = [
            item for item in self.base_gain_occupants.get(team, []) if item != target_id
        ]
        self.trapezoid_gain_occupants[team] = [
            item
            for item in self.trapezoid_gain_occupants.get(team, [])
            if item != target_id
        ]
        self.outpost_gain_occupants[team] = [
            item
            for item in self.outpost_gain_occupants.get(team, [])
            if item != target_id
        ]
        self.assembly_gain_occupants[team] = [
            item
            for item in self.assembly_gain_occupants.get(team, [])
            if item != target_id
        ]
        self.supply_gain_occupants[team] = [
            item
            for item in self.supply_gain_occupants.get(team, [])
            if item != target_id
        ]
        if target_id in self.fort_own_occupants.get(team, []):
            self.fort_own_occupants[team] = []
            self.fort_reserve_ammo[team] = 0
            self.fort_reserve_capacity[team] = 0
        self.fort_enemy_occupants[team] = [
            item
            for item in self.fort_enemy_occupants.get(team, [])
            if item != target_id
        ]
        if not self.base_gain_occupants[team]:
            self.zone_inside.discard(BASE_GAIN_ZONE_IDS[team])
        if not self.trapezoid_gain_occupants[team]:
            self.zone_inside.discard(TRAPEZOID_GAIN_ZONE_IDS[team])
        if not any(self.outpost_gain_occupants.values()):
            for zone_id in OUTPOST_GAIN_ZONE_IDS.values():
                self.zone_inside.discard(zone_id)
        if not self.assembly_gain_occupants[team]:
            self.zone_inside.discard(ASSEMBLY_GAIN_ZONE_IDS[team])
        if not self.supply_gain_occupants[team]:
            self.zone_inside.discard(SUPPLY_GAIN_ZONE_IDS[team])

    def _clear_terrain_crossing_robot(self, target_id: int, *, team: str) -> None:
        """Clear acquired crossing gains and in-progress detection on death."""
        if team not in ("red", "blue") or target_id not in GROUND_ROBOT_IDS:
            return
        self.terrain_sequence_cards[team][target_id] = []
        self.terrain_sequence_elapsed[team][target_id] = 0.0
        self.terrain_cards_inside[team][target_id] = []
        self.terrain_last_positions[team].pop(target_id, None)
        self.terrain_standard_defence[team][target_id] = 0.0
        self.terrain_standard_remaining[team][target_id] = 0.0
        self.terrain_tunnel_defence_remaining[team][target_id] = 0.0
        self.terrain_tunnel_cooling_remaining[team][target_id] = 0.0

    def _clear_central_highland_robot(self, target_id: int, *, team: str) -> None:
        """Immediately remove a destroyed robot from central-highland control."""
        if team not in ("red", "blue") or target_id not in CENTRAL_HIGHLAND_ROBOT_IDS:
            return
        self.central_highland_occupants[team] = [
            item
            for item in self.central_highland_occupants.get(team, [])
            if item != target_id
        ]
        for zone_id, grace in self.central_highland_exit_grace.items():
            grace.setdefault(team, {}).pop(target_id, None)
            if (
                self.central_highland_owners.get(zone_id) == team
                and not grace.get(team)
            ):
                self.central_highland_owners.pop(zone_id, None)
        if not any(self.central_highland_occupants.values()):
            self.zone_inside.discard(CENTRAL_HIGHLAND_ZONE_ID)

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

    def _base_gain_polygon(self, team: str) -> tuple[tuple[float, float], ...]:
        if team not in BASE_GAIN_ZONE_IDS:
            raise ValueError(f"unknown team {team}")
        points = normalize_points(
            self.field_zone_overrides.get(BASE_GAIN_ZONE_IDS[team])
        )
        return points if validate_polygon(points) is None else ()

    def _position_in_base_gain(
        self, team: str, position: tuple[float, float]
    ) -> bool:
        polygon = self._base_gain_polygon(team)
        return bool(polygon) and _point_in_polygon(position, polygon)

    def _trapezoid_gain_polygon(self, team: str) -> tuple[tuple[float, float], ...]:
        if team not in TRAPEZOID_GAIN_ZONE_IDS:
            raise ValueError(f"unknown team {team}")
        points = normalize_points(
            self.field_zone_overrides.get(TRAPEZOID_GAIN_ZONE_IDS[team])
        )
        return points if validate_polygon(points) is None else ()

    def _position_in_trapezoid_gain(
        self, team: str, position: tuple[float, float]
    ) -> bool:
        polygon = self._trapezoid_gain_polygon(team)
        return bool(polygon) and _point_in_polygon(position, polygon)

    def _outpost_gain_polygon(self, team: str) -> tuple[tuple[float, float], ...]:
        if team not in OUTPOST_GAIN_ZONE_IDS:
            raise ValueError(f"unknown team {team}")
        points = normalize_points(
            self.field_zone_overrides.get(OUTPOST_GAIN_ZONE_IDS[team])
        )
        return points if validate_polygon(points) is None else ()

    def _position_in_outpost_gain(
        self, zone_team: str, position: tuple[float, float]
    ) -> bool:
        polygon = self._outpost_gain_polygon(zone_team)
        return bool(polygon) and _point_in_polygon(position, polygon)

    def _outpost_health(self, team: str) -> float:
        if team == "red":
            return float(self.own_outpost_hp)
        if team == "blue":
            return float(self.enemy_outpost_hp)
        raise ValueError(f"unknown team {team}")

    def _outpost_destroyed(self, team: str) -> bool:
        if team == "red":
            return self.own_outpost_destroyed_ever or self.own_outpost_hp <= 0
        if team == "blue":
            return self.enemy_outpost_destroyed_ever or self.enemy_outpost_hp <= 0.0
        raise ValueError(f"unknown team {team}")

    def _outpost_gain_zone_available(
        self, occupying_team: str, zone_team: str
    ) -> bool:
        """Return whether one team may occupy the specified outpost point."""
        if occupying_team not in ("red", "blue") or zone_team not in ("red", "blue"):
            raise ValueError("unknown team")
        if self._outpost_health(occupying_team) <= 0.0:
            return False
        if occupying_team == zone_team:
            return True
        return (
            self._outpost_health(zone_team) <= 0.0
            and self.match_elapsed <= OUTPOST_GAIN_ENEMY_CAPTURE_SECONDS
        )

    def _assembly_gain_polygon(self, team: str) -> tuple[tuple[float, float], ...]:
        if team not in ASSEMBLY_GAIN_ZONE_IDS:
            raise ValueError(f"unknown team {team}")
        points = normalize_points(
            self.field_zone_overrides.get(ASSEMBLY_GAIN_ZONE_IDS[team])
        )
        return points if validate_polygon(points) is None else ()

    def _position_in_assembly_gain(
        self, team: str, position: tuple[float, float]
    ) -> bool:
        polygon = self._assembly_gain_polygon(team)
        return bool(polygon) and _point_in_polygon(position, polygon)

    def assembly_engineer_in_zone(self, team: str = "red") -> bool:
        """Return whether the living, non-weak engineer may assemble now."""
        if team not in ("red", "blue"):
            raise ValueError(f"unknown team {team}")
        health = self.own_robot_health(2) if team == "red" else self.enemy_health(2)
        position = (
            self.own_robot_position(2)
            if team == "red"
            else self.robot_position(2, team="blue")
        )
        return (
            health > 0.0
            and not self.robot_is_weak(2, team=team)
            and self._position_in_assembly_gain(team, position)
        )

    def assembly_zone_position(self, team: str = "red") -> tuple[float, float] | None:
        """Return a stable point inside the configured assembly polygon."""
        polygon = self._assembly_gain_polygon(team)
        if not polygon:
            return None
        signed_area = 0.0
        centroid_x = 0.0
        centroid_y = 0.0
        for index, (x1, y1) in enumerate(polygon):
            x2, y2 = polygon[(index + 1) % len(polygon)]
            cross = x1 * y2 - x2 * y1
            signed_area += cross
            centroid_x += (x1 + x2) * cross
            centroid_y += (y1 + y2) * cross
        if abs(signed_area) > 1e-9:
            candidate = (
                centroid_x / (3.0 * signed_area),
                centroid_y / (3.0 * signed_area),
            )
            if self._position_in_assembly_gain(team, candidate):
                return candidate
        average = (
            sum(point[0] for point in polygon) / len(polygon),
            sum(point[1] for point in polygon) / len(polygon),
        )
        if self._position_in_assembly_gain(team, average):
            return average
        return polygon[0]

    def _supply_gain_polygon(self, team: str) -> tuple[tuple[float, float], ...]:
        if team not in SUPPLY_GAIN_ZONE_IDS:
            raise ValueError(f"unknown team {team}")
        points = normalize_points(
            self.field_zone_overrides.get(SUPPLY_GAIN_ZONE_IDS[team])
        )
        return points if validate_polygon(points) is None else ()

    def _position_in_supply_gain(
        self, team: str, position: tuple[float, float]
    ) -> bool:
        polygon = self._supply_gain_polygon(team)
        return bool(polygon) and _point_in_polygon(position, polygon)

    def _robot_position_in_supply_gain(
        self,
        team: str,
        target_id: int,
        sentry: SentryState | None = None,
    ) -> bool:
        if team == "red" and target_id == 8:
            if sentry is None:
                return self.robot_in_supply_gain(team, target_id)
            position = (sentry.x, sentry.y)
            return self._position_in_supply_gain(team, position) or self._sentry_at_supply(sentry)
        position = (
            self.own_robot_position(target_id)
            if team == "red"
            else self.robot_position(target_id, team="blue")
        )
        return self._position_in_supply_gain(team, position)

    def _fort_gain_polygon(self, team: str) -> tuple[tuple[float, float], ...]:
        if team not in FORT_GAIN_ZONE_IDS:
            raise ValueError(f"unknown team {team}")
        points = normalize_points(
            self.field_zone_overrides.get(FORT_GAIN_ZONE_IDS[team])
        )
        return points if validate_polygon(points) is None else ()

    def _position_in_fort_gain(
        self, fort_team: str, position: tuple[float, float]
    ) -> bool:
        polygon = self._fort_gain_polygon(fort_team)
        return bool(polygon) and _point_in_polygon(position, polygon)

    def _fort_active(self, fort_team: str) -> bool:
        return self._outpost_destroyed(fort_team)

    def _fort_enemy_capture_available(self, attacking_team: str) -> bool:
        fort_team = self.opposing_team(attacking_team)
        return (
            self.match_elapsed >= FORT_ENEMY_CAPTURE_START_SECONDS
            and self._fort_active(fort_team)
        )

    @staticmethod
    def _sentry_at_supply(sentry: SentryState) -> bool:
        # Compatibility footprint used by the existing simulator before the
        # editable annotation system was introduced.
        return 0.0 <= sentry.x <= 4.0 and 0.0 <= sentry.y <= 3.0

    def _gain_robot_health(self, team: str, target_id: int) -> float:
        if team == "red":
            return float(self.own_robot_health(target_id))
        if team == "blue":
            return float(self.enemy_health(target_id))
        raise ValueError(f"unknown team {team}")

    def _update_gain_exit_grace(
        self,
        zone_id: str,
        detected: dict[str, set[int]],
        elapsed_seconds: float,
    ) -> dict[str, set[int]]:
        """Return active occupants after the universal two-second exit delay."""
        elapsed_seconds = max(0.0, float(elapsed_seconds))
        grace = self.gain_exit_grace.setdefault(
            zone_id, {"red": {}, "blue": {}}
        )
        active: dict[str, set[int]] = {"red": set(), "blue": set()}
        for team in ("red", "blue"):
            timers = grace.setdefault(team, {})
            present = {int(target_id) for target_id in detected.get(team, set())}
            for target_id in present:
                if self._gain_robot_health(team, target_id) > 0.0:
                    timers[target_id] = GAIN_OCCUPATION_EXIT_DELAY
            for target_id in tuple(timers):
                if self._gain_robot_health(team, target_id) <= 0.0:
                    timers.pop(target_id, None)
                    continue
                if target_id not in present:
                    remaining = max(0.0, timers[target_id] - elapsed_seconds)
                    if remaining <= 0.0:
                        timers.pop(target_id, None)
                        continue
                    timers[target_id] = remaining
                active[team].add(target_id)
        if not any(grace[team] for team in ("red", "blue")):
            self.gain_exit_grace.pop(zone_id, None)
        return active

    def _clear_gain_exit_grace_robot(self, target_id: int, *, team: str) -> None:
        """Deaths invalidate every ordinary gain occupation immediately."""
        for zone_id in tuple(self.gain_exit_grace):
            teams = self.gain_exit_grace[zone_id]
            teams.setdefault(team, {}).pop(target_id, None)
            if not any(teams.get(side) for side in ("red", "blue")):
                self.gain_exit_grace.pop(zone_id, None)

    def _update_outpost_rebuild(
        self, sentry: SentryState, elapsed_seconds: float
    ) -> None:
        """Rebuild a destroyed outpost from independently timed robot scans."""
        elapsed_seconds = max(0.0, float(elapsed_seconds))
        for team in ("red", "blue"):
            progress = self.outpost_rebuild_progress.setdefault(
                team, {target_id: 0.0 for target_id in GROUND_ROBOT_IDS}
            )
            available = (
                self._outpost_health(team) <= 0.0
                and self.outpost_rebuild_chances.get(team, 0) > 0
                and self.match_elapsed <= OUTPOST_REBUILD_DEADLINE_SECONDS
                and bool(self._outpost_gain_polygon(team))
            )
            if not available:
                for target_id in GROUND_ROBOT_IDS:
                    progress[target_id] = 0.0
                continue

            candidates: list[tuple[float, int]] = []
            for target_id in GROUND_ROBOT_IDS:
                health = self._gain_robot_health(team, target_id)
                position = (
                    self.own_robot_position(target_id, sentry)
                    if team == "red"
                    else self.robot_position(target_id, team="blue")
                )
                detected = (
                    health > 0.0
                    and not self.robot_is_weak(target_id, team=team)
                    and self._position_in_outpost_gain(team, position)
                )
                if not detected:
                    progress[target_id] = 0.0
                    continue
                required = OUTPOST_REBUILD_SECONDS[target_id]
                previous = max(0.0, float(progress.get(target_id, 0.0)))
                progress[target_id] = min(required, previous + elapsed_seconds)
                if progress[target_id] >= required:
                    completion_offset = max(0.0, required - previous)
                    candidates.append((completion_offset, target_id))

            if not candidates:
                continue
            _, builder_id = min(candidates)
            if team == "red":
                self.own_outpost_hp = OUTPOST_REBUILD_HP
            else:
                self.enemy_outpost_hp = OUTPOST_REBUILD_HP
            self.outpost_rebuild_chances[team] = max(
                0, self.outpost_rebuild_chances.get(team, 0) - 1
            )
            for target_id in GROUND_ROBOT_IDS:
                progress[target_id] = 0.0
            self._set_event(
                f"{'红' if team == 'red' else '蓝'}方 {builder_id} 号机器人"
                f"完成前哨重建，前哨恢复 {OUTPOST_REBUILD_HP:.0f} 血"
            )

    def _field_zones(self) -> tuple:
        """Return configured rule-bearing region ids.

        Other annotation families remain geometry-only.  The side-specific
        base, trapezoid-highland, outpost, assembly, supply, and fort slots
        become active once drawn.
        """
        zone_ids = [
            zone_id
            for team, zone_id in BASE_GAIN_ZONE_IDS.items()
            if self._base_gain_polygon(team)
        ]
        zone_ids.extend(
            zone_id
            for team, zone_id in TRAPEZOID_GAIN_ZONE_IDS.items()
            if self._trapezoid_gain_polygon(team)
        )
        if self.central_highland_zones:
            zone_ids.append(CENTRAL_HIGHLAND_ZONE_ID)
        zone_ids.extend(
            zone_id
            for team, zone_id in OUTPOST_GAIN_ZONE_IDS.items()
            if self._outpost_gain_polygon(team)
        )
        zone_ids.extend(
            zone_id
            for team, zone_id in ASSEMBLY_GAIN_ZONE_IDS.items()
            if self._assembly_gain_polygon(team)
        )
        zone_ids.extend(
            zone_id
            for team, zone_id in SUPPLY_GAIN_ZONE_IDS.items()
            if self._supply_gain_polygon(team)
        )
        zone_ids.extend(
            zone_id
            for team, zone_id in FORT_GAIN_ZONE_IDS.items()
            if self._fort_gain_polygon(team)
        )
        return tuple(zone_ids)

    def _zones_for_team(self, team: str = "red") -> tuple:
        if team not in ("red", "blue"):
            return ()
        zone_ids: list[str] = []
        if self._base_gain_polygon(team):
            zone_ids.append(BASE_GAIN_ZONE_IDS[team])
        if self._trapezoid_gain_polygon(team):
            zone_ids.append(TRAPEZOID_GAIN_ZONE_IDS[team])
        if self.central_highland_zones:
            zone_ids.append(CENTRAL_HIGHLAND_ZONE_ID)
        for zone_team in ("red", "blue"):
            if (
                self._outpost_gain_zone_available(team, zone_team)
                and self._outpost_gain_polygon(zone_team)
            ):
                zone_ids.append(OUTPOST_GAIN_ZONE_IDS[zone_team])
        if (
            self._assembly_gain_polygon(team)
            and self.assembly_gain_elapsed.get(team, 0.0)
            < ASSEMBLY_GAIN_MAX_SECONDS
        ):
            zone_ids.append(ASSEMBLY_GAIN_ZONE_IDS[team])
        if self._supply_gain_polygon(team):
            zone_ids.append(SUPPLY_GAIN_ZONE_IDS[team])
        if self._fort_active(team) and self._fort_gain_polygon(team):
            zone_ids.append(FORT_GAIN_ZONE_IDS[team])
        enemy_team = self.opposing_team(team)
        if (
            self._fort_enemy_capture_available(team)
            and self._fort_gain_polygon(enemy_team)
        ):
            zone_ids.append(FORT_GAIN_ZONE_IDS[enemy_team])
        return tuple(zone_ids)

    def _update_field_zones(self, sentry: SentryState, elapsed_seconds: float) -> None:
        """Compatibility hook for callers that update rule-bearing regions."""
        self._update_base_gain_points(sentry, elapsed_seconds)
        self._update_trapezoid_gain_points(sentry, elapsed_seconds)
        self._update_central_highland_gain_points(sentry, elapsed_seconds)
        self._update_outpost_rebuild(sentry, elapsed_seconds)
        self._update_outpost_gain_points(sentry, elapsed_seconds)
        self._update_assembly_gain_points(sentry, elapsed_seconds)
        self._update_supply(sentry, elapsed_seconds)
        self._update_fort_gain_points(sentry, elapsed_seconds)
        self._update_terrain_crossing(sentry, elapsed_seconds)

    def _update_base_gain_points(
        self, sentry: SentryState, elapsed_seconds: float
    ) -> None:
        """Apply both teams' base gain points with delayed occupation loss."""
        occupants: dict[str, set[int]] = {"red": set(), "blue": set()}
        cleared: list[str] = []
        for team in ("red", "blue"):
            zone_id = BASE_GAIN_ZONE_IDS[team]
            detected: dict[str, set[int]] = {"red": set(), "blue": set()}
            if self._base_gain_polygon(team):
                for target_id in GROUND_ROBOT_IDS:
                    position = (
                        self.own_robot_position(target_id, sentry)
                        if team == "red"
                        else self.robot_position(target_id, team="blue")
                    )
                    if (
                        self._gain_robot_health(team, target_id) > 0.0
                        and self._position_in_base_gain(team, position)
                    ):
                        detected[team].add(target_id)
                        if self._clear_robot_weakness_at_gain(target_id, team=team):
                            cleared.append(
                                f"{'红' if team == 'red' else '蓝'}方{target_id}号"
                            )
            active = self._update_gain_exit_grace(
                zone_id, detected, elapsed_seconds
            )
            occupants[team].update(active[team])
            if active[team]:
                self.zone_inside.add(zone_id)
            else:
                self.zone_inside.discard(zone_id)

        self.base_gain_occupants = {
            team: sorted(target_ids) for team, target_ids in occupants.items()
        }
        if cleared:
            self._set_event("基地增益点解除虚弱：" + "、".join(cleared))

    def _update_trapezoid_gain_points(
        self, sentry: SentryState, elapsed_seconds: float
    ) -> None:
        """Track trapezoid occupation with the universal two-second delay."""
        occupants: dict[str, set[int]] = {"red": set(), "blue": set()}
        for team in ("red", "blue"):
            zone_id = TRAPEZOID_GAIN_ZONE_IDS[team]
            detected: dict[str, set[int]] = {"red": set(), "blue": set()}
            if self._trapezoid_gain_polygon(team):
                for target_id in GROUND_ROBOT_IDS:
                    position = (
                        self.own_robot_position(target_id, sentry)
                        if team == "red"
                        else self.robot_position(target_id, team="blue")
                    )
                    if (
                        self._gain_robot_health(team, target_id) > 0.0
                        and not self.robot_is_weak(target_id, team=team)
                        and self._position_in_trapezoid_gain(team, position)
                    ):
                        detected[team].add(target_id)
            active = self._update_gain_exit_grace(
                zone_id, detected, elapsed_seconds
            )
            occupants[team].update(active[team])
            if active[team]:
                self.zone_inside.add(zone_id)
            else:
                self.zone_inside.discard(zone_id)

        self.trapezoid_gain_occupants = {
            team: sorted(target_ids) for team, target_ids in occupants.items()
        }

    def _update_central_highland_gain_points(
        self, sentry: SentryState, elapsed_seconds: float
    ) -> None:
        """Apply independent, mutually exclusive central-highland ownership."""
        elapsed_seconds = max(0.0, elapsed_seconds)
        occupants: dict[str, set[int]] = {"red": set(), "blue": set()}
        valid_zone_ids: set[str] = set()
        ownership_changes: list[str] = []

        for zone in self.central_highland_zones:
            if not isinstance(zone, dict):
                continue
            zone_id = str(zone.get("id") or "")
            polygon = normalize_points(zone.get("points"))
            if not zone_id or validate_polygon(polygon) is not None:
                continue
            valid_zone_ids.add(zone_id)
            grace = self.central_highland_exit_grace.setdefault(
                zone_id, {"red": {}, "blue": {}}
            )
            for team in ("red", "blue"):
                team_grace = grace.setdefault(team, {})
                for target_id in CENTRAL_HIGHLAND_ROBOT_IDS:
                    health = (
                        self.own_robot_health(target_id)
                        if team == "red"
                        else self.enemy_health(target_id)
                    )
                    position = (
                        self.own_robot_position(target_id, sentry)
                        if team == "red"
                        else self.robot_position(target_id, team="blue")
                    )
                    if health <= 0.0 or self.robot_is_weak(target_id, team=team):
                        team_grace.pop(target_id, None)
                    elif _point_in_polygon(position, polygon):
                        team_grace[target_id] = CENTRAL_HIGHLAND_EXIT_DELAY
                    elif target_id in team_grace:
                        remaining = max(
                            0.0, team_grace[target_id] - elapsed_seconds
                        )
                        if remaining > 0.0:
                            team_grace[target_id] = remaining
                        else:
                            team_grace.pop(target_id, None)

            previous_owner = self.central_highland_owners.get(zone_id)
            owner = previous_owner if previous_owner in ("red", "blue") else None
            if owner is not None and not grace[owner]:
                owner = None
            if owner is None:
                red_present = bool(grace["red"])
                blue_present = bool(grace["blue"])
                if red_present != blue_present:
                    owner = "red" if red_present else "blue"

            if owner is None:
                self.central_highland_owners.pop(zone_id, None)
            else:
                self.central_highland_owners[zone_id] = owner
                occupants[owner].update(grace[owner])
            if owner != previous_owner:
                label = "空闲" if owner is None else ("红方" if owner == "red" else "蓝方")
                ownership_changes.append(f"{zone_id}→{label}")

        for zone_id in tuple(self.central_highland_owners):
            if zone_id not in valid_zone_ids:
                self.central_highland_owners.pop(zone_id, None)
        for zone_id in tuple(self.central_highland_exit_grace):
            if zone_id not in valid_zone_ids:
                self.central_highland_exit_grace.pop(zone_id, None)

        self.central_highland_occupants = {
            team: sorted(target_ids) for team, target_ids in occupants.items()
        }
        if any(occupants.values()):
            self.zone_inside.add(CENTRAL_HIGHLAND_ZONE_ID)
        else:
            self.zone_inside.discard(CENTRAL_HIGHLAND_ZONE_ID)
        if ownership_changes:
            self._set_event("中央高地占领更新：" + "、".join(ownership_changes))

    def _update_outpost_gain_points(
        self, sentry: SentryState, elapsed_seconds: float
    ) -> None:
        """Apply outpost occupation and delayed loss for either team."""
        occupants: dict[str, set[int]] = {"red": set(), "blue": set()}
        cleared: list[str] = []

        for zone_team in ("red", "blue"):
            zone_id = OUTPOST_GAIN_ZONE_IDS[zone_team]
            detected: dict[str, set[int]] = {"red": set(), "blue": set()}
            if self._outpost_gain_polygon(zone_team):
                for occupying_team in ("red", "blue"):
                    if not self._outpost_gain_zone_available(
                        occupying_team, zone_team
                    ):
                        continue
                    for target_id in GROUND_ROBOT_IDS:
                        position = (
                            self.own_robot_position(target_id, sentry)
                            if occupying_team == "red"
                            else self.robot_position(target_id, team="blue")
                        )
                        if (
                            self._gain_robot_health(occupying_team, target_id) > 0.0
                            and self._position_in_outpost_gain(zone_team, position)
                        ):
                            detected[occupying_team].add(target_id)
                            if self._clear_robot_weakness_at_gain(
                                target_id, team=occupying_team
                            ):
                                cleared.append(
                                    f"{'红' if occupying_team == 'red' else '蓝'}方"
                                    f"{target_id}号"
                                )
            active = self._update_gain_exit_grace(
                zone_id, detected, elapsed_seconds
            )
            for team in ("red", "blue"):
                occupants[team].update(active[team])
            if any(active.values()):
                self.zone_inside.add(zone_id)
            else:
                self.zone_inside.discard(zone_id)

        self.outpost_gain_occupants = {
            team: sorted(target_ids) for team, target_ids in occupants.items()
        }
        if cleared:
            self._set_event(
                "前哨站增益点解除虚弱及无敌：" + "、".join(cleared)
            )

    def _update_assembly_gain_points(
        self, sentry: SentryState, elapsed_seconds: float
    ) -> None:
        """Grant each team's engineer up to 180 cumulative seconds of invincibility."""
        occupants: dict[str, list[int]] = {"red": [], "blue": []}
        for team in ("red", "blue"):
            zone_id = ASSEMBLY_GAIN_ZONE_IDS[team]
            elapsed = min(
                ASSEMBLY_GAIN_MAX_SECONDS,
                max(0.0, float(self.assembly_gain_elapsed.get(team, 0.0))),
            )
            health = (
                self.own_robot_health(2)
                if team == "red"
                else self.enemy_health(2)
            )
            position = (
                self.own_robot_position(2, sentry)
                if team == "red"
                else self.robot_position(2, team="blue")
            )
            detected_inside = (
                health > 0.0
                and not self.robot_is_weak(2, team=team)
                and elapsed < ASSEMBLY_GAIN_MAX_SECONDS
                and self._position_in_assembly_gain(team, position)
            )
            detected = {"red": set(), "blue": set()}
            if detected_inside:
                detected[team].add(2)
            previous_exit = (
                self.gain_exit_grace.get(zone_id, {}).get(team, {}).get(2, 0.0)
            )
            active_duration = (
                max(0.0, elapsed_seconds)
                if detected_inside
                else min(max(0.0, elapsed_seconds), max(0.0, previous_exit))
            )
            active = self._update_gain_exit_grace(
                zone_id, detected, elapsed_seconds
            )
            if active_duration > 0.0 and elapsed < ASSEMBLY_GAIN_MAX_SECONDS:
                elapsed = min(
                    ASSEMBLY_GAIN_MAX_SECONDS,
                    elapsed + active_duration,
                )
            if 2 in active[team] and elapsed < ASSEMBLY_GAIN_MAX_SECONDS:
                occupants[team].append(2)
                self.zone_inside.add(zone_id)
            else:
                if elapsed >= ASSEMBLY_GAIN_MAX_SECONDS:
                    self.gain_exit_grace.get(zone_id, {}).get(team, {}).pop(2, None)
                self.zone_inside.discard(zone_id)
            self.assembly_gain_elapsed[team] = elapsed
        self.assembly_gain_occupants = occupants

    def _update_supply(self, sentry: SentryState, elapsed_seconds: float) -> None:
        """Apply supply occupancy, healing, revive unlocks, and engineer immunity."""
        occupants: dict[str, list[int]] = {"red": [], "blue": []}
        cleared: list[str] = []
        for team in ("red", "blue"):
            zone_id = SUPPLY_GAIN_ZONE_IDS[team]
            detected: dict[str, set[int]] = {"red": set(), "blue": set()}
            for target_id in GROUND_ROBOT_IDS:
                if (
                    self._gain_robot_health(team, target_id) > 0.0
                    and self._robot_position_in_supply_gain(
                        team, target_id, sentry
                    )
                ):
                    detected[team].add(target_id)
                    if self._clear_robot_weakness_at_gain(target_id, team=team):
                        cleared.append(
                            f"{'红' if team == 'red' else '蓝'}方{target_id}号"
                        )
            previous_exit = dict(
                self.gain_exit_grace.get(zone_id, {}).get(team, {})
            )
            active = self._update_gain_exit_grace(
                zone_id, detected, elapsed_seconds
            )
            occupants[team] = sorted(active[team])
            if occupants[team]:
                self.zone_inside.add(zone_id)
            else:
                self.zone_inside.discard(zone_id)

            active_durations = {
                target_id: (
                    max(0.0, elapsed_seconds)
                    if target_id in detected[team]
                    else min(
                        max(0.0, elapsed_seconds),
                        max(0.0, previous_exit.get(target_id, 0.0)),
                    )
                )
                for target_id in set(previous_exit) | detected[team]
            }
            for target_id, active_duration in active_durations.items():
                if active_duration <= 0.0:
                    continue
                maximum = self.robot_max_hp(target_id, team=team)
                out_of_combat = (
                    self.robot_out_of_combat_seconds_value(target_id, team=team)
                    >= OUT_OF_COMBAT_SECONDS
                )
                fraction = SUPPLY_GAIN_HEAL
                if self.match_elapsed >= SUPPLY_GAIN_LATE_SECONDS and out_of_combat:
                    fraction = SUPPLY_GAIN_HEAL_LATE
                healed = maximum * fraction * active_duration
                if team == "red" and target_id == 8:
                    self.sentry_hp = min(maximum, self.sentry_hp + healed)
                elif team == "red":
                    self.own_robot_hp[target_id] = min(
                        maximum, self.own_robot_hp[target_id] + healed
                    )
                else:
                    self.robot_hp[target_id] = min(
                        maximum, self.robot_hp[target_id] + healed
                    )

        self.supply_gain_occupants = occupants

        if 8 in occupants["red"]:
            self.respawn_fire_locked = False
        if 8 in occupants["red"] and self.pending_ammo > 0:
            transferred = min(self.pending_ammo, AMMO_CAP - self.ammo)
            self.ammo += transferred
            self.pending_ammo -= transferred
        if cleared:
            self._set_event("补给区解除虚弱：" + "、".join(cleared))

    def _update_fort_gain_points(
        self, sentry: SentryState, elapsed_seconds: float
    ) -> None:
        """Apply both friendly and enemy occupation rules for each fort."""
        previous_owners = {
            team: (self.fort_own_occupants.get(team) or [None])[0]
            for team in ("red", "blue")
        }
        own_occupants: dict[str, list[int]] = {"red": [], "blue": []}
        enemy_occupants: dict[str, list[int]] = {"red": [], "blue": []}
        enemy_capture_active_duration: dict[str, dict[int, float]] = {
            "red": {}, "blue": {}
        }
        enemy_capture_active_end: dict[str, set[int]] = {
            "red": set(), "blue": set()
        }

        for fort_team in ("red", "blue"):
            zone_id = FORT_GAIN_ZONE_IDS[fort_team]
            detected: dict[str, set[int]] = {"red": set(), "blue": set()}
            own_candidates: list[int] = []
            active_polygon = bool(self._fort_gain_polygon(fort_team))
            if self._fort_active(fort_team) and active_polygon:
                for target_id in FORT_ROBOT_IDS:
                    position = (
                        self.own_robot_position(target_id, sentry)
                        if fort_team == "red"
                        else self.robot_position(target_id, team="blue")
                    )
                    if (
                        self._gain_robot_health(fort_team, target_id) > 0.0
                        and not self.robot_is_weak(target_id, team=fort_team)
                        and self._position_in_fort_gain(fort_team, position)
                    ):
                        own_candidates.append(target_id)
            previous_owner = previous_owners[fort_team]
            if previous_owner in own_candidates:
                detected[fort_team].add(int(previous_owner))
            else:
                previous_grace = (
                    self.gain_exit_grace.get(zone_id, {})
                    .get(fort_team, {})
                )
                if previous_owner not in previous_grace and own_candidates:
                    detected[fort_team].add(own_candidates[0])

            attacking_team = self.opposing_team(fort_team)
            if self._fort_enemy_capture_available(attacking_team) and active_polygon:
                for target_id in FORT_ROBOT_IDS:
                    position = (
                        self.own_robot_position(target_id, sentry)
                        if attacking_team == "red"
                        else self.robot_position(target_id, team="blue")
                    )
                    if (
                        self._gain_robot_health(attacking_team, target_id) > 0.0
                        and not self.robot_is_weak(target_id, team=attacking_team)
                        and self._position_in_fort_gain(fort_team, position)
                    ):
                        detected[attacking_team].add(target_id)

            previous_enemy_exit = dict(
                self.gain_exit_grace.get(zone_id, {}).get(attacking_team, {})
            )
            active = self._update_gain_exit_grace(
                zone_id, detected, elapsed_seconds
            )
            if not active[fort_team] and own_candidates:
                detected[fort_team] = {own_candidates[0]}
                active = self._update_gain_exit_grace(zone_id, detected, 0.0)
            if active[fort_team]:
                owner = (
                    int(previous_owner)
                    if previous_owner in active[fort_team]
                    else min(active[fort_team], key=FORT_ROBOT_IDS.index)
                )
                own_occupants[fort_team] = [owner]
                grace = self.gain_exit_grace.get(zone_id, {}).get(fort_team, {})
                for target_id in tuple(grace):
                    if target_id != owner:
                        grace.pop(target_id, None)
            enemy_occupants[attacking_team] = sorted(active[attacking_team])
            for target_id in set(previous_enemy_exit) | detected[attacking_team]:
                if target_id in detected[attacking_team]:
                    duration = max(0.0, elapsed_seconds)
                else:
                    duration = min(
                        max(0.0, elapsed_seconds),
                        max(0.0, previous_enemy_exit.get(target_id, 0.0)),
                    )
                enemy_capture_active_duration[attacking_team][target_id] = max(
                    enemy_capture_active_duration[attacking_team].get(target_id, 0.0),
                    duration,
                )
            enemy_capture_active_end[attacking_team].update(
                active[attacking_team]
            )

        self.fort_own_occupants = own_occupants
        self.fort_enemy_occupants = enemy_occupants

        for team in ("red", "blue"):
            owner = (own_occupants[team] or [None])[0]
            previous_owner = previous_owners[team]
            if owner is None:
                self.fort_reserve_capacity[team] = 0
                self.fort_reserve_ammo[team] = 0
                continue
            capacity = self.fortress_reserve_limit(team)
            if owner != previous_owner:
                remaining = capacity
            else:
                previous_capacity = max(0, self.fort_reserve_capacity.get(team, 0))
                spent = max(
                    0,
                    previous_capacity - max(0, self.fort_reserve_ammo.get(team, 0)),
                )
                remaining = max(0, capacity - spent)
            self.fort_reserve_capacity[team] = capacity
            self.fort_reserve_ammo[team] = remaining

        for attacking_team in ("red", "blue"):
            elapsed_map = self.fort_enemy_capture_elapsed[attacking_team]
            grace_map = self.fort_enemy_capture_grace[attacking_team]
            durations = enemy_capture_active_duration[attacking_team]
            active_at_end = enemy_capture_active_end[attacking_team]
            for target_id, active_duration in durations.items():
                if active_duration <= 0.0:
                    continue
                elapsed_map[target_id] = min(
                    FORT_ENEMY_CAPTURE_REQUIRED_SECONDS,
                    elapsed_map.get(target_id, 0.0) + active_duration,
                )
                inactive_duration = max(0.0, elapsed_seconds - active_duration)
                grace_map[target_id] = (
                    FORT_ENEMY_CAPTURE_GRACE_SECONDS
                    if target_id in active_at_end
                    else max(
                        0.0,
                        FORT_ENEMY_CAPTURE_GRACE_SECONDS - inactive_duration,
                    )
                )
            for target_id in tuple(elapsed_map):
                if target_id in durations:
                    if grace_map.get(target_id, 0.0) <= 0.0:
                        elapsed_map.pop(target_id, None)
                        grace_map.pop(target_id, None)
                    continue
                grace = max(0.0, grace_map.get(target_id, 0.0) - elapsed_seconds)
                if grace > 0.0:
                    grace_map[target_id] = grace
                else:
                    elapsed_map.pop(target_id, None)
                    grace_map.pop(target_id, None)
            if any(
                value >= FORT_ENEMY_CAPTURE_REQUIRED_SECONDS
                for value in elapsed_map.values()
            ):
                if attacking_team == "red" and not self.enemy_base_armor_deployed:
                    self.enemy_base_armor_deployed = True
                    self._set_event("红方占领敌方堡垒20秒，敌方基地护甲展开")
                elif attacking_team == "blue" and not self.own_base_armor_deployed:
                    self.own_base_armor_deployed = True
                    self._set_event("蓝方占领己方堡垒20秒，己方基地护甲展开")

        for fort_team, zone_id in FORT_GAIN_ZONE_IDS.items():
            attacking_team = self.opposing_team(fort_team)
            if own_occupants[fort_team] or enemy_occupants[attacking_team]:
                self.zone_inside.add(zone_id)
            else:
                self.zone_inside.discard(zone_id)

    def set_central_highland_zones(self, zones: list[dict]) -> None:
        """Install disconnected central-highland polygons from the map editor."""
        normalized: list[dict] = []
        used_ids: set[str] = set()
        for index, item in enumerate(zones or []):
            if not isinstance(item, dict):
                continue
            points = normalize_points(item.get("points"))
            if validate_polygon(points) is not None:
                continue
            zone_id = str(item.get("id") or f"central_highland_{index}")
            if zone_id in used_ids:
                zone_id = f"{zone_id}_{index}"
            used_ids.add(zone_id)
            normalized.append(
                {
                    "id": zone_id,
                    "points": [[float(x), float(y)] for x, y in points],
                }
            )
        self.central_highland_zones = normalized
        valid_ids = {zone["id"] for zone in normalized}
        self.central_highland_owners = {
            zone_id: owner
            for zone_id, owner in self.central_highland_owners.items()
            if zone_id in valid_ids and owner in ("red", "blue")
        }
        self.central_highland_exit_grace = {
            zone_id: grace
            for zone_id, grace in self.central_highland_exit_grace.items()
            if zone_id in valid_ids
        }

    def set_terrain_crossing_cards(self, cards: list[dict]) -> None:
        """Install normalized editable card regions for rule 5.5.3.5."""
        normalized: list[dict] = []
        used_ids: set[str] = set()
        for index, item in enumerate(cards or []):
            if not isinstance(item, dict):
                continue
            kind = str(item.get("kind") or "")
            if kind not in TERRAIN_CROSSING_KINDS:
                continue
            field_team = str(item.get("field_team") or item.get("team") or "")
            if field_team not in ("red", "blue", "neutral"):
                continue
            points = normalize_points(item.get("points"))
            if validate_polygon(points) is not None:
                continue
            try:
                route = max(0, int(item.get("route", 0)))
                order = max(0, int(item.get("order", 0)))
            except (TypeError, ValueError):
                continue
            card_id = str(item.get("id") or f"terrain_{index}")
            if card_id in used_ids:
                card_id = f"{card_id}_{index}"
            used_ids.add(card_id)
            normalized.append(
                {
                    "id": card_id,
                    "kind": kind,
                    "field_team": field_team,
                    "route": route,
                    "order": order,
                    "points": [[float(x), float(y)] for x, y in points],
                }
            )
        self.terrain_crossing_cards = normalized
        valid_ids = {card["id"] for card in normalized}
        for team in ("red", "blue"):
            for target_id in GROUND_ROBOT_IDS:
                if any(
                    card_id not in valid_ids
                    for card_id in self.terrain_sequence_cards[team][target_id]
                ):
                    self._reset_terrain_sequence(target_id, team=team)
                self.terrain_cards_inside[team][target_id] = [
                    card_id
                    for card_id in self.terrain_cards_inside[team][target_id]
                    if card_id in valid_ids
                ]

    def _terrain_card_by_id(self, card_id: str) -> dict | None:
        return next(
            (card for card in self.terrain_crossing_cards if card.get("id") == card_id),
            None,
        )

    def _terrain_route_cards(self, card: dict) -> list[dict]:
        cards = [
            item
            for item in self.terrain_crossing_cards
            if item.get("kind") == card.get("kind")
            and item.get("field_team") == card.get("field_team")
            and item.get("route") == card.get("route")
        ]
        return sorted(cards, key=lambda item: (int(item.get("order", 0)), str(item.get("id"))))

    def _reset_terrain_sequence(self, target_id: int, *, team: str) -> None:
        self.terrain_sequence_cards[team][target_id] = []
        self.terrain_sequence_elapsed[team][target_id] = 0.0
        if team == "red" and target_id == 8:
            self.road_crossing_side = None
            self.road_crossing_elapsed = 0.0

    def _start_terrain_sequence(
        self, target_id: int, *, team: str, card: dict
    ) -> None:
        kind = str(card.get("kind"))
        route_cards = self._terrain_route_cards(card)
        required = TERRAIN_CROSSING_CARD_COUNTS[kind]
        if len(route_cards) != required:
            return
        order = int(card.get("order", 0))
        if kind in ("road", "highland") and order != 0:
            return
        if kind == "tunnel" and order not in (0, required - 1):
            return
        self.terrain_sequence_cards[team][target_id] = [str(card["id"])]
        self.terrain_sequence_elapsed[team][target_id] = 0.0
        if team == "red" and target_id == 8 and kind == "road":
            self.road_crossing_side = str(card.get("field_team"))
            self.road_crossing_elapsed = 0.0

    def _terrain_expected_card_ids(self, progress: list[str]) -> set[str]:
        if not progress:
            return set()
        first = self._terrain_card_by_id(progress[0])
        if first is None:
            return set()
        kind = str(first.get("kind"))
        route_cards = self._terrain_route_cards(first)
        if len(route_cards) != TERRAIN_CROSSING_CARD_COUNTS[kind]:
            return set()
        if kind in ("road", "highland"):
            return {str(route_cards[1]["id"])} if len(progress) == 1 else set()
        if kind == "fly_slope":
            return {
                str(card["id"])
                for card in route_cards
                if str(card["id"]) not in progress
            }
        if len(progress) == 1:
            return {
                str(card["id"])
                for card in route_cards
                if int(card.get("order", 0)) == 1
            }
        start_order = int(first.get("order", 0))
        end_order = 2 if start_order == 0 else 0
        return {
            str(card["id"])
            for card in route_cards
            if int(card.get("order", 0)) == end_order
        }

    def _grant_terrain_crossing_gain(
        self, target_id: int, *, team: str, kind: str
    ) -> bool:
        if kind == "road" and self.terrain_road_cooldown[team][target_id] > 0.0:
            return False
        if kind == "tunnel":
            self.terrain_tunnel_defence_remaining[team][target_id] = max(
                self.terrain_tunnel_defence_remaining[team][target_id],
                TERRAIN_TUNNEL_DEFENCE_DURATION,
            )
            self.terrain_tunnel_cooling_remaining[team][target_id] = max(
                self.terrain_tunnel_cooling_remaining[team][target_id],
                TERRAIN_TUNNEL_COOLING_DURATION,
            )
        else:
            duration = TERRAIN_STANDARD_DURATIONS[kind]
            already_active = self.terrain_standard_remaining[team][target_id] > 0.0
            self.terrain_standard_defence[team][target_id] = (
                TERRAIN_REPEATED_DEFENCE
                if already_active
                else TERRAIN_STANDARD_DEFENCE
            )
            self.terrain_standard_remaining[team][target_id] = max(
                self.terrain_standard_remaining[team][target_id], duration
            )
            if kind == "road":
                self.terrain_road_cooldown[team][target_id] = TERRAIN_ROAD_COOLDOWN
        side = "己方" if team == "red" else "蓝方"
        label = {
            "road": "公路",
            "highland": "高地",
            "fly_slope": "飞坡",
            "tunnel": "隧道",
        }[kind]
        self._set_event(f"{side} {target_id} 号获得地形跨越增益（{label}）")
        return True

    def _advance_terrain_sequence_time(
        self, target_id: int, *, team: str, elapsed_seconds: float
    ) -> None:
        progress = self.terrain_sequence_cards[team][target_id]
        if not progress or elapsed_seconds <= 0.0:
            return
        self.terrain_sequence_elapsed[team][target_id] += elapsed_seconds
        first = self._terrain_card_by_id(progress[0])
        window = (
            TERRAIN_CROSSING_WINDOWS.get(str(first.get("kind")), 0.0)
            if first is not None
            else 0.0
        )
        if self.terrain_sequence_elapsed[team][target_id] > window + 1e-9:
            self._reset_terrain_sequence(target_id, team=team)

    def _detect_terrain_card(self, target_id: int, *, team: str, card: dict) -> None:
        progress = self.terrain_sequence_cards[team][target_id]
        if not progress:
            self._start_terrain_sequence(target_id, team=team, card=card)
            return
        first = self._terrain_card_by_id(progress[0])
        if first is None:
            self._reset_terrain_sequence(target_id, team=team)
            self._start_terrain_sequence(target_id, team=team, card=card)
            return
        same_route = (
            card.get("kind") == first.get("kind")
            and card.get("field_team") == first.get("field_team")
            and card.get("route") == first.get("route")
        )
        card_id = str(card.get("id"))
        if same_route and card_id in self._terrain_expected_card_ids(progress):
            progress.append(card_id)
            required = TERRAIN_CROSSING_CARD_COUNTS[str(first.get("kind"))]
            if len(progress) >= required:
                self._grant_terrain_crossing_gain(
                    target_id, team=team, kind=str(first.get("kind"))
                )
                self._reset_terrain_sequence(target_id, team=team)
            return
        # Any other field-interaction card breaks the sequence.  The card that
        # caused the break may itself be a legal first card for a new attempt.
        self._reset_terrain_sequence(target_id, team=team)
        self._start_terrain_sequence(target_id, team=team, card=card)

    def _update_terrain_crossing(
        self, sentry: SentryState, elapsed_seconds: float
    ) -> None:
        elapsed_seconds = max(0.0, elapsed_seconds)
        cards = [
            card
            for card in self.terrain_crossing_cards
            if isinstance(card, dict)
            and card.get("kind") in TERRAIN_CROSSING_KINDS
            and validate_polygon(normalize_points(card.get("points"))) is None
        ]
        card_index = {str(card.get("id")): index for index, card in enumerate(cards)}

        for team in ("red", "blue"):
            for target_id in GROUND_ROBOT_IDS:
                for timers in (
                    self.terrain_standard_remaining,
                    self.terrain_tunnel_defence_remaining,
                    self.terrain_tunnel_cooling_remaining,
                    self.terrain_road_cooldown,
                ):
                    timers[team][target_id] = max(
                        0.0, timers[team][target_id] - elapsed_seconds
                    )
                if self.terrain_standard_remaining[team][target_id] <= 0.0:
                    self.terrain_standard_defence[team][target_id] = 0.0

                health = (
                    self.own_robot_health(target_id)
                    if team == "red"
                    else self.enemy_health(target_id)
                )
                if health <= 0.0:
                    self.terrain_cards_inside[team][target_id] = []
                    self.terrain_last_positions[team].pop(target_id, None)
                    continue
                position = (
                    self.own_robot_position(target_id, sentry)
                    if team == "red"
                    else self.robot_position(target_id, team="blue")
                )
                previous_values = self.terrain_last_positions[team].get(target_id)
                previous = (
                    (float(previous_values[0]), float(previous_values[1]))
                    if previous_values is not None
                    else position
                )
                previously_inside = set(self.terrain_cards_inside[team][target_id])
                currently_inside: list[str] = []
                detections: list[tuple[float, int, dict]] = []
                for card in cards:
                    card_id = str(card.get("id"))
                    polygon = normalize_points(card.get("points"))
                    if _point_in_polygon(position, polygon):
                        currently_inside.append(card_id)
                    if card_id in previously_inside:
                        continue
                    entry = _segment_polygon_entry(previous, position, polygon)
                    if entry is not None:
                        detections.append((entry, card_index[card_id], card))
                self.terrain_cards_inside[team][target_id] = currently_inside
                self.terrain_last_positions[team][target_id] = [
                    float(position[0]),
                    float(position[1]),
                ]
                previous_fraction = 0.0
                for entry, _, card in sorted(
                    detections, key=lambda item: (item[0], item[1])
                ):
                    self._advance_terrain_sequence_time(
                        target_id,
                        team=team,
                        elapsed_seconds=max(0.0, entry - previous_fraction)
                        * elapsed_seconds,
                    )
                    self._detect_terrain_card(target_id, team=team, card=card)
                    previous_fraction = max(previous_fraction, entry)
                self._advance_terrain_sequence_time(
                    target_id,
                    team=team,
                    elapsed_seconds=max(0.0, 1.0 - previous_fraction)
                    * elapsed_seconds,
                )

        cooldown = self.terrain_road_cooldown["red"].get(8, 0.0)
        if cooldown > 0.0:
            self.zone_cooldowns["terrain_road"] = cooldown
        else:
            self.zone_cooldowns.pop("terrain_road", None)
        progress = self.terrain_sequence_cards["red"].get(8, [])
        first = self._terrain_card_by_id(progress[0]) if progress else None
        if first is not None and first.get("kind") == "road":
            self.road_crossing_side = str(first.get("field_team"))
            self.road_crossing_elapsed = self.terrain_sequence_elapsed["red"][8]
        elif not progress:
            self.road_crossing_side = None
            self.road_crossing_elapsed = 0.0

    def _update_road_crossing(
        self,
        sentry: SentryState,
        elapsed_seconds: float,
        cooldown_at_start: float = 0.0,
    ) -> None:
        """Compatibility alias for integrations that called the old hook."""
        self._update_terrain_crossing(sentry, elapsed_seconds)

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

    def select_assembly_difficulty(self, difficulty: int) -> bool:
        if difficulty not in (1, 2, 3, 4):
            raise ValueError("assembly difficulty must be 1..4")
        if self.game_finished or not self.game_running:
            self._set_event("比赛未进行，不能选择装配难度")
            return False
        if self.assembly_active:
            self._set_event("装配进行中，不能更改难度")
            return False
        if not self._assembly_gain_polygon("red"):
            self._set_event("请先在地图中标注己方装配区增益点")
            return False
        if not self.assembly_engineer_in_zone("red"):
            self._set_event("工程机器人需先占领己方装配区增益点")
            return False
        required_elapsed = (difficulty - 1) * 60.0
        if self.match_elapsed < required_elapsed:
            self._set_event(f"{difficulty} 级装配尚未到开放时间")
            return False
        if difficulty > 1 and (difficulty - 1) not in self.assembly_completed:
            self._set_event("需要先完成上一级装配")
            return False
        if difficulty == 4 and difficulty in self.assembly_completed:
            self._set_event("四级装配每局仅可完成一次")
            return False
        if difficulty == 4 and self.assembly_level4_cooldown_remaining > 0.0:
            self._set_event(
                f"四级装配失败冷却中：{self.assembly_level4_cooldown_remaining:.1f} 秒"
            )
            return False
        self.assembly_difficulty = difficulty
        self.assembly_last_difficulty = difficulty
        self.assembly_last_result = "已选择，等待开始"
        self.assembly_last_roll = None
        self._set_event(f"已选择 {difficulty} 级装配")
        return True

    def assembly_success_rate(self, difficulty: int | None = None) -> float:
        """Return the configured fixed success probability for one attempt.

        The value is intentionally kept in the referee-side scenario state so
        the Pygame simulator can vary it without changing the behavior tree.
        Values outside ``[0, 1]`` are clamped defensively when read.
        """
        selected = self.assembly_difficulty if difficulty is None else difficulty
        configured = self.assembly_success_probability.get(
            selected,
            ASSEMBLY_SUCCESS_PROBABILITY.get(selected, 1.0),
        )
        return max(0.0, min(1.0, float(configured)))

    def start_assembly(self) -> bool:
        if self.assembly_difficulty <= 0:
            self._set_event("请先选择装配难度")
            return False
        if self.game_finished or not self.game_running:
            self._set_event("比赛未进行，不能开始装配")
            return False
        if not self._assembly_gain_polygon("red"):
            self._set_event("请先在地图中标注己方装配区增益点")
            return False
        if not self.assembly_engineer_in_zone("red"):
            self._set_event("工程机器人不在己方装配区")
            return False
        if self.assembly_active:
            self._set_event("装配已在进行")
            return False
        if self.assembly_difficulty == 4 and 4 in self.assembly_completed:
            self._set_event("四级装配每局仅可完成一次")
            return False
        if (
            self.assembly_difficulty == 4
            and self.assembly_level4_cooldown_remaining > 0.0
        ):
            self._set_event(
                f"四级装配失败冷却中：{self.assembly_level4_cooldown_remaining:.1f} 秒"
            )
            return False
        self.assembly_active = True
        self.assembly_progress = 0.0
        self.assembly_outside_seconds = 0.0
        self.assembly_required = ASSEMBLY_SIM_DURATION[self.assembly_difficulty]
        self.assembly_last_result = "装配中"
        self.assembly_last_roll = None
        self._set_event(
            f"开始 {self.assembly_difficulty} 级装配，"
            f"二维裁判计时 {self.assembly_required:.0f} 秒，"
            f"固定成功率 {self.assembly_success_rate() * 100:.0f}%"
        )
        return True

    def cancel_assembly(self, reason: str = "装配已取消", *, failed: bool = False) -> None:
        if self.assembly_active:
            difficulty = self.assembly_difficulty
            self.assembly_active = False
            self.assembly_progress = 0.0
            self.assembly_required = 0.0
            self.assembly_outside_seconds = 0.0
            self.assembly_last_result = "取消"
            self.assembly_last_roll = None
            if failed and difficulty == 4:
                self.assembly_level4_cooldown_remaining = max(
                    self.assembly_level4_cooldown_remaining,
                    90.0,
                )
                reason += "，四级装配冷却 90 秒"
            self._set_event(reason)

    def _complete_assembly(self) -> None:
        difficulty = self.assembly_difficulty
        success_probability = self.assembly_success_rate(difficulty)
        self.assembly_last_roll = random.random()
        if self.assembly_last_roll >= success_probability:
            self.assembly_active = False
            self.assembly_progress = 0.0
            self.assembly_required = 0.0
            self.assembly_outside_seconds = 0.0
            self.assembly_last_result = "失败"
            if difficulty == 4:
                self.assembly_level4_cooldown_remaining = max(
                    self.assembly_level4_cooldown_remaining,
                    90.0,
                )
                cooldown = "，四级装配冷却 90 秒"
            else:
                cooldown = ""
            self._set_event(
                f"{difficulty} 级装配失败：随机值 {self.assembly_last_roll:.3f}"
                f" ≥ 成功率 {success_probability:.3f}{cooldown}"
            )
            return
        first = difficulty not in self.assembly_completed
        self.assembly_completed.add(difficulty)
        self.assembly_active = False
        self.assembly_progress = 0.0
        self.assembly_required = 0.0
        self.assembly_outside_seconds = 0.0
        self.assembly_last_result = "成功"
        self.assembly_difficulty = 0
        if difficulty == 1:
            self.assembly_bonus_per_10s += 50 if first else 5
        elif difficulty == 2:
            self.level_cap = max(self.level_cap, 7)
            self.assembly_bonus_per_10s += 25 if first else 10
        elif difficulty == 3:
            self.level_cap = max(self.level_cap, 10)
            self.assembly_defence = max(self.assembly_defence, 0.25)
            self.assembly_bonus_per_10s += 25 if first else 15
        elif difficulty == 4:
            if not first:
                self._set_event("四级装配每局仅可完成一次")
                return
            self.assembly_defence = max(self.assembly_defence, 0.50)
            gained = 2000
            space = max(0, self.own_base_max_hp - self.own_base_hp)
            applied = min(space, gained)
            self.own_base_hp += applied
            self.own_base_shield += gained - applied
            self.assembly_bonus_per_10s += 50
        self._set_event(
            f"{difficulty} 级装配成功（随机值 {self.assembly_last_roll:.3f}，"
            f"成功率 {success_probability:.3f}），每 10 秒额外金币 "
            f"{self.assembly_bonus_per_10s}"
        )

    def _update_assembly(self, elapsed_seconds: float) -> None:
        self.assembly_level4_cooldown_remaining = max(
            0.0,
            self.assembly_level4_cooldown_remaining - elapsed_seconds,
        )
        if not self.assembly_active:
            return
        if self.own_robot_health(2) <= 0.0:
            self.cancel_assembly("工程机器人战亡，装配失败", failed=True)
            return
        if not self.assembly_engineer_in_zone("red"):
            self.assembly_outside_seconds += elapsed_seconds
            if self.assembly_outside_seconds >= ASSEMBLY_OUTSIDE_FAILURE_SECONDS:
                self.cancel_assembly(
                    "工程机器人连续 15 秒未占领装配区，装配失败",
                    failed=True,
                )
            return
        self.assembly_outside_seconds = 0.0
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
        previous_base_hp = self.enemy_base_hp
        self.enemy_base_hp = max(
            0.0, self.enemy_base_hp - (damage - shield_damage)
        )
        self._record_base_hp_damage(
            "blue", max(0.0, previous_base_hp - self.enemy_base_hp)
        )
        self._record_base_minimum("blue")
        self.dart_hits += 1
        if self.dart_target_type in ("random_moving", "end_moving"):
            self.enemy_base_armor_deployed = True
        self._set_event(f"飞镖命中敌方基地 -{damage:.0f}")
        self._finish_if_base_destroyed()

    def radar_mark(self, target_id: int, amount: float = 10.0) -> None:
        """Compatibility helper for deterministic tests and referee setup.

        The Pygame panel uses :meth:`radar_scan`; this method remains useful
        for tests that need to place a target directly at a threshold.
        """
        if target_id not in self.radar_marks:
            raise ValueError(f"target {target_id} has no radar mark")
        self.radar_marks[target_id] = min(
            150.0, self.radar_marks[target_id] + amount
        )
        self._set_event(
            f"雷达标记 {target_id} 号：{self.radar_marks[target_id]:.0f}"
        )

    def radar_vulnerability(self, target_id: int) -> float:
        if target_id not in RADAR_ROBOT_IDS:
            return 0.0
        # If the opponent's interference level is higher than ours, the
        # rulebook suppresses the radar-originated vulnerability effect.
        if self.enemy_radar_interference_level > self.radar_interference_level:
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

    def _radar_random(self) -> float:
        """Return a replayable pseudo-random value for radar abstractions."""
        self.radar_random_counter += 1
        return random.Random(
            self.radar_random_seed + self.radar_random_counter
        ).random()

    def _radar_quality_from_roll(self, roll: float) -> str:
        probabilities = {
            key: max(0.0, float(value))
            for key, value in self.radar_accuracy_probability.items()
            if key in ("accurate", "half_accurate", "error")
        }
        total = sum(probabilities.values())
        if total <= 0.0:
            return "error"
        cursor = 0.0
        for quality in ("accurate", "half_accurate", "error"):
            cursor += probabilities.get(quality, 0.0) / total
            if roll < cursor:
                return quality
        return "error"

    def _radar_apply_quality(self, target_id: int, quality: str) -> None:
        previous = self.radar_last_report_quality.get(target_id, "未发送")
        x = self.radar_mark_x.get(target_id, 0.0)
        if quality == "accurate":
            x = x + 1.0 if previous in ("accurate", "half_accurate") else 1.0
        elif quality == "half_accurate":
            x = x + 0.5 if previous in ("accurate", "half_accurate") else 0.5
        else:
            x = x - 0.8 if previous in ("error", "中断") else -0.8
        self.radar_mark_x[target_id] = x
        self.radar_marks[target_id] = max(
            0.0, min(150.0, self.radar_marks.get(target_id, 0.0) + x)
        )
        self.radar_last_report_quality[target_id] = quality

    def _radar_update_estimated_position(
        self, target_id: int, quality: str, roll: float
    ) -> None:
        actual_x, actual_y = self.robot_position(target_id, team="blue")
        if quality == "accurate":
            radius = 0.0
        elif quality == "half_accurate":
            radius = 0.8 + (roll * 997 % 1.0) * 0.8
        else:
            radius = 1.6 + (roll * 991 % 1.0) * 1.4
        if radius <= 0.0:
            estimate = [actual_x, actual_y]
        else:
            angle = (roll * 7919 % 1.0) * math.tau
            estimate = [
                actual_x + math.cos(angle) * radius,
                actual_y + math.sin(angle) * radius,
            ]
        self.radar_estimated_positions[target_id] = estimate

    def radar_scan(self, target_id: int) -> str:
        """Generate one referee-side radar report for an enemy robot.

        The result is one of ``accurate``, ``half_accurate``, ``error`` or
        ``中断``.  P updates follow the rulebook after the probabilistic
        measurement quality has been selected.
        """
        if target_id not in RADAR_ROBOT_IDS:
            raise ValueError(f"target {target_id} is not a radar robot target")
        loss_roll = self._radar_random()
        self.radar_last_report_roll[target_id] = loss_roll
        if loss_roll < max(0.0, min(1.0, self.radar_data_loss_probability)):
            self.radar_missing_seconds[target_id] = (
                self.radar_missing_seconds.get(target_id, 0.0)
                + self.radar_report_interval
            )
            while self.radar_missing_seconds[target_id] >= 0.5:
                self.radar_missing_seconds[target_id] -= 0.5
                self._radar_apply_quality(target_id, "中断")
            self.radar_last_report_status = f"{target_id}号数据中断"
            return "中断"

        quality_roll = self._radar_random()
        quality = self._radar_quality_from_roll(quality_roll)
        self.radar_missing_seconds[target_id] = 0.0
        self._radar_apply_quality(target_id, quality)
        self._radar_update_estimated_position(target_id, quality, quality_roll)
        self.radar_last_report_quality[target_id] = quality
        self.radar_last_report_status = f"{target_id}号{quality}"
        return quality

    def _refresh_radar_team_packet(self) -> None:
        targets: dict[int, dict[str, object]] = {}
        for target_id in RADAR_ROBOT_IDS:
            actual_position = list(self.robot_position(target_id, team="blue"))
            targets[target_id] = {
                "position": actual_position,
                "health": round(float(self.enemy_health(target_id)), 3),
                "ammo": int(self.robot_ammo.get(target_id, 0)),
                "level": int(self.robot_level.get(target_id, 1)),
                "weak": bool(self.robot_weak_state.get(target_id, False)),
                "defence": self.robot_effective_defence(target_id, team="blue"),
                "radar_mark": round(self.radar_marks.get(target_id, 0.0), 3),
                "radar_vulnerability": self.radar_vulnerability(target_id),
            }
        self.radar_team_packet = {
            "valid": bool(self.radar_info_wave_decoded and self.radar_info_wave_age <= self.radar_info_wave_ttl),
            "timestamp": self.match_elapsed,
            "targets": targets,
            "team_economy": {
                "own": int(self.economy),
                "enemy": int(self.enemy_economy),
            },
            "active_buffs": [
                {
                    "source": buff.source,
                    "kind": buff.kind,
                    "value": buff.value,
                    "remaining": buff.remaining,
                }
                for buff in self.active_buffs
            ],
            "gain_points": {
                "assembly_completed": sorted(self.assembly_completed),
                "central_highland_owners": dict(self.central_highland_owners),
            },
        }

    def parse_radar_information_wave(self) -> bool:
        """Attempt to decode the rulebook information wave."""
        self.radar_info_wave_last_roll = self._radar_random()
        if self.radar_info_wave_last_roll >= max(
            0.0, min(1.0, self.radar_info_wave_probability)
        ):
            self.radar_info_wave_decoded = False
            self.radar_info_wave_age = self.radar_info_wave_ttl
            self.radar_interference_last_result = "信息波解析失败"
            self._refresh_radar_team_packet()
            self._set_event("雷达信息波解析失败")
            return False
        self.radar_info_wave_decoded = True
        self.radar_info_wave_age = 0.0
        self.radar_interference_last_result = "信息波已解析"
        self._refresh_radar_team_packet()
        self._set_event("雷达信息波解析成功：全队态势包已更新")
        return True

    def parse_radar_interference_key(self) -> bool:
        """Attempt to raise this radar base's interference difficulty."""
        self.radar_interference_last_roll = self._radar_random()
        if self.radar_interference_last_roll >= max(
            0.0, min(1.0, self.radar_interference_parse_probability)
        ):
            self.radar_interference_last_result = "干扰密钥解析失败"
            self._set_event("雷达干扰密钥解析失败")
            return False
        self.radar_interference_level = min(3, self.radar_interference_level + 1)
        self.radar_interference_last_result = (
            f"己方干扰等级 {self.radar_interference_level}"
        )
        self._set_event(
            f"干扰密钥解析成功：己方干扰等级 {self.radar_interference_level}"
        )
        return True

    def set_radar_air_support(self, active: bool) -> None:
        self.radar_air_support_active = bool(active)
        if not active:
            self.radar_air_lock_progress = 0.0
        self._set_event(
            "对方空中支援已开始" if active else "对方空中支援已暂停"
        )

    def attempt_radar_air_countermeasure(self) -> bool:
        """Try one simplified laser countermeasure attempt against robot 5."""
        if not self.radar_air_support_active:
            self.radar_air_last_result = "空中支援未启动"
            self._set_event("空中支援未启动，无法进行雷达反制")
            return False
        if self.radar_air_lock_remaining > 0.0:
            self.radar_air_last_result = "已在锁定"
            return False
        if self.radar_air_lock_count >= RADAR_AIR_MAX_LOCKS:
            self.radar_air_last_result = "本局反制次数已用尽"
            self._set_event("雷达反制次数已达上限5次")
            return False
        if self.radar_air_lock_count == 0:
            difficulty = 1
        elif self.radar_air_lock_count < 3:
            difficulty = 2
        else:
            difficulty = 3
        self.radar_air_lock_difficulty = difficulty
        self.radar_air_last_roll = self._radar_random()
        probability = max(
            0.0, min(1.0, self.radar_air_lock_probability.get(difficulty, 0.0))
        )
        if self.radar_air_last_roll >= probability:
            self.radar_air_last_result = f"反制失败（难度{difficulty}）"
            self._set_event(self.radar_air_last_result)
            return False
        self.radar_air_lock_count += 1
        self.radar_air_lock_progress = 100.0
        self.radar_air_lock_remaining = RADAR_AIR_LOCK_DURATION
        self.radar_air_last_result = f"反制成功，发射机构锁定{RADAR_AIR_LOCK_DURATION:.0f}秒"
        self._set_event(
            f"雷达反制成功：空中机器人发射机构锁定 {RADAR_AIR_LOCK_DURATION:.0f} 秒"
        )
        return True

    def _update_radar(self, elapsed_seconds: float) -> None:
        self.radar_double_remaining = max(
            0.0, self.radar_double_remaining - elapsed_seconds
        )
        if self.radar_air_lock_remaining > 0.0:
            self.radar_air_lock_remaining = max(
                0.0, self.radar_air_lock_remaining - elapsed_seconds
            )
            if self.radar_air_lock_remaining <= 0.0:
                self.radar_air_lock_progress = 0.0
                self.radar_air_last_result = "反制锁定已解除"
        self.radar_report_accumulator += elapsed_seconds
        interval = max(0.01, float(self.radar_report_interval))
        while self.radar_report_accumulator >= interval:
            self.radar_report_accumulator -= interval
            self.radar_report_count += 1
            for target_id in RADAR_ROBOT_IDS:
                self.radar_scan(target_id)
        if self.radar_info_wave_decoded:
            self.radar_info_wave_age += elapsed_seconds
            self._refresh_radar_team_packet()
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
            sentry.reset_chassis_dynamics()
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
            sentry.reset_chassis_dynamics()
            self._set_event("底盘功率超限，缓冲能量耗尽，断电 5 秒")

    def _update_other_robot_power(self, elapsed_seconds: float) -> None:
        """Apply the rulebook 60 J buffer and five-second chassis cut."""
        if elapsed_seconds <= 0.0:
            return
        for team in ("red", "blue"):
            power_values = self.own_robot_power if team == "red" else self.robot_power
            buffers = (
                self.own_robot_buffer_energy
                if team == "red"
                else self.robot_buffer_energy
            )
            cuts = (
                self.own_robot_chassis_power_cut_remaining
                if team == "red"
                else self.robot_chassis_power_cut_remaining
            )
            for target_id in ROBOT_PROFILES:
                if team == "red" and target_id == 8:
                    continue
                power_limit = self.robot_power_limit(target_id, team=team)
                if power_limit is None:
                    power_values[target_id] = 0.0
                    buffers[target_id] = BUFFER_ENERGY_CAP
                    cuts[target_id] = 0.0
                    continue
                if cuts[target_id] > 0.0:
                    cuts[target_id] = max(0.0, cuts[target_id] - elapsed_seconds)
                    power_values[target_id] = 0.0
                    if cuts[target_id] <= 0.0:
                        buffers[target_id] = BUFFER_ENERGY_CAP
                    continue
                over_power = power_values[target_id] - float(power_limit)
                if over_power <= 0.0:
                    buffers[target_id] = min(
                        BUFFER_ENERGY_CAP,
                        buffers[target_id] - over_power * elapsed_seconds,
                    )
                    continue
                buffers[target_id] = max(
                    0.0,
                    buffers[target_id] - over_power * elapsed_seconds,
                )
                if buffers[target_id] <= 0.0:
                    cuts[target_id] = CHASSIS_POWER_CUT_SECONDS
                    power_values[target_id] = 0.0
                    self._set_event(
                        f"{'己方' if team == 'red' else '蓝方'} {target_id} 号"
                        "底盘功率超限，断电 5 秒"
                    )

    def toggle_posture_reinforced(self, sentry: SentryState | None = None) -> None:
        active = self.active_posture
        if self.reinforced_time.get(active, 0.0) >= POSTURE_REINFORCED_SECONDS:
            self._set_event("该姿态的强化时间已用完")
            return
        self.posture_reinforced = not self.posture_reinforced
        if self.posture_reinforced and active == 1 and sentry is not None:
            # Reinforced attack posture requires current heat to remain zero,
            # so entering it clears existing heat immediately rather than on
            # the next simulation/referee tick.
            sentry.heat = 0.0
            if not self.sentry_heat_permanent_lock:
                self.sentry_heat_locked = False
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
    ) -> None:
        if self.sentry_hp > 0.0 or self.death_elapsed is None:
            return
        self.death_elapsed += elapsed_seconds
        self._update_rulebook_revive(sentry, elapsed_seconds)

    def _confirm_task_respawn(self, sentry: SentryState) -> bool:
        """Apply the task-mode five-second autonomous respawn confirmation."""
        if (
            self.sentry_hp > 0.0
            or self.death_elapsed is None
            or self.death_elapsed < TASK_RESPAWN_CONFIRM_SECONDS
        ):
            return False
        self.sentry_hp = 400.0
        sentry.heat = 0.0
        self.death_elapsed = None
        self.revive_progress = 0.0
        self.revive_required = 0.0
        self.invincible_remaining = 0.0
        self.weak_state = True
        self.revive_invincibility_source = "task_confirm"
        self.instant_revive_power_boost_remaining = 0.0
        self.respawn_fire_locked = True
        self.sentry_heat_locked = self.sentry_heat_permanent_lock
        self.sentry_buffer_energy = self.effective_buffer_cap
        self.sentry_chassis_power_cut_remaining = 0.0
        sentry.reset_chassis_dynamics()
        self._ammo_shot_accumulator = 0.0
        self._set_event("自主确认复活：恢复 400 血，返回补给区前禁止开火")
        return True

    def _update_rulebook_revive(
        self,
        sentry: SentryState,
        elapsed_seconds: float,
    ) -> None:
        if self.revive_required <= 0.0:
            self.revive_required = self.revive_seconds_required
        accelerated = (
            self._robot_position_in_supply_gain("red", 8, sentry)
            or self.own_base_hp < 2000
        )
        rate = RULEBOOK_REVIVE_RATE * (4.0 if accelerated else 1.0)
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
        self.revive_invincibility_source = "readbar"
        self.respawn_fire_locked = True
        self.sentry_heat_locked = self.sentry_heat_permanent_lock
        self.sentry_buffer_energy = self.effective_buffer_cap
        self.sentry_chassis_power_cut_remaining = 0.0
        sentry.reset_chassis_dynamics()
        self._ammo_shot_accumulator = 0.0
        self._set_event("读条复活：10% 血量，30 秒无敌并进入虚弱状态")

    def _update_robot_respawns(self, elapsed_seconds: float) -> None:
        """Advance respawn timers for every non-player ground robot."""
        if elapsed_seconds <= 0.0:
            return
        revived: list[str] = []
        for team in ("red", "blue"):
            if team == "blue":
                hp_map = self.robot_hp
                death = self.robot_death_elapsed
                progress = self.robot_revive_progress
                required = self.robot_revive_required
                weak = self.robot_weak_state
                invincible = self.robot_invincible_remaining
            else:
                hp_map = self.own_robot_hp
                death = self.own_robot_death_elapsed
                progress = self.own_robot_revive_progress
                required = self.own_robot_revive_required
                weak = self.own_robot_weak_state
                invincible = self.own_robot_invincible_remaining
            for target_id in tuple(death):
                if death[target_id] is None or hp_map.get(target_id, 0.0) > 0.0:
                    continue
                death[target_id] = float(death[target_id] or 0.0) + elapsed_seconds
                if required.get(target_id, 0.0) <= 0.0:
                    required[target_id] = self.revive_seconds_required_for(
                        target_id, team=team
                    )
                base_hp = self.own_base_hp if team == "red" else self.enemy_base_hp
                accelerated = (
                    self._robot_position_in_supply_gain(team, target_id)
                    or base_hp < 2000
                )
                rate = 4.0 if accelerated else 1.0
                progress[target_id] = min(
                    required[target_id],
                    progress.get(target_id, 0.0) + rate * elapsed_seconds,
                )
                if progress[target_id] < required[target_id]:
                    continue
                maximum = self.robot_max_hp(target_id, team=team)
                hp_map[target_id] = maximum * RULEBOOK_REVIVE_HP_FRACTION
                weak[target_id] = True
                invincible[target_id] = RULEBOOK_REVIVE_INVINCIBLE
                sources = (
                    self.robot_revive_invincibility_source
                    if team == "blue"
                    else self.own_robot_revive_invincibility_source
                )
                sources[target_id] = "readbar"
                death[target_id] = None
                progress[target_id] = 0.0
                required[target_id] = 0.0
                revived.append(
                    f"{'红' if team == 'red' else '蓝'}方{target_id}号"
                )
        if revived:
            self._set_event(
                "机器人复活："
                + "、".join(revived)
                + "，10%血量、30秒无敌并进入虚弱"
            )

    def _update_economy_timers(
        self,
        sentry: SentryState,
        elapsed_seconds: float,
    ) -> None:
        self.invincible_remaining = max(
            0.0, self.invincible_remaining - elapsed_seconds
        )
        if self.invincible_remaining <= 0.0:
            source = self.revive_invincibility_source
            self.revive_invincibility_source = ""
            if source == "instant" and self.weak_state and self.death_elapsed is None:
                self.weak_state = False
                self.respawn_fire_locked = False
        for timers, weak, sources in (
            (
                self.robot_invincible_remaining,
                self.robot_weak_state,
                self.robot_revive_invincibility_source,
            ),
            (
                self.own_robot_invincible_remaining,
                self.own_robot_weak_state,
                self.own_robot_revive_invincibility_source,
            ),
        ):
            for target_id in timers:
                timers[target_id] = max(
                    0.0, timers[target_id] - elapsed_seconds
                )
                if timers[target_id] <= 0.0:
                    source = sources.get(target_id, "")
                    sources[target_id] = ""
                    if source == "instant":
                        weak[target_id] = False
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


def _point_in_polygon(
    point: tuple[float, float],
    polygon: tuple[tuple[float, float], ...],
) -> bool:
    """Return True for points inside or on the boundary of a polygon."""
    x, y = point
    inside = False
    previous_x, previous_y = polygon[-1]
    for current_x, current_y in polygon:
        cross = (x - previous_x) * (current_y - previous_y) - (
            y - previous_y
        ) * (current_x - previous_x)
        if (
            abs(cross) <= 1e-9
            and min(previous_x, current_x) - 1e-9
            <= x
            <= max(previous_x, current_x) + 1e-9
            and min(previous_y, current_y) - 1e-9
            <= y
            <= max(previous_y, current_y) + 1e-9
        ):
            return True
        if (current_y > y) != (previous_y > y):
            edge_x = previous_x + (y - previous_y) * (
                current_x - previous_x
            ) / (current_y - previous_y)
            if x < edge_x:
                inside = not inside
        previous_x, previous_y = current_x, current_y
    return inside


def _segment_polygon_entry(
    start: tuple[float, float],
    end: tuple[float, float],
    polygon: tuple[tuple[float, float], ...],
) -> float | None:
    """Return the earliest normalized segment position touching a polygon."""
    if _point_in_polygon(start, polygon):
        return 0.0
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    if abs(dx) <= 1e-12 and abs(dy) <= 1e-12:
        return 0.0 if _point_in_polygon(end, polygon) else None

    def cross(ax: float, ay: float, bx: float, by: float) -> float:
        return ax * by - ay * bx

    candidates: list[float] = []
    for index, edge_start in enumerate(polygon):
        edge_end = polygon[(index + 1) % len(polygon)]
        ex = edge_end[0] - edge_start[0]
        ey = edge_end[1] - edge_start[1]
        qx = edge_start[0] - start[0]
        qy = edge_start[1] - start[1]
        denominator = cross(dx, dy, ex, ey)
        if abs(denominator) <= 1e-12:
            if abs(cross(qx, qy, dx, dy)) > 1e-9:
                continue
            length_squared = dx * dx + dy * dy
            for point in (edge_start, edge_end):
                value = (
                    (point[0] - start[0]) * dx
                    + (point[1] - start[1]) * dy
                ) / length_squared
                if -1e-9 <= value <= 1.0 + 1e-9:
                    candidates.append(min(1.0, max(0.0, value)))
            continue
        t = cross(qx, qy, ex, ey) / denominator
        u = cross(qx, qy, dx, dy) / denominator
        if -1e-9 <= t <= 1.0 + 1e-9 and -1e-9 <= u <= 1.0 + 1e-9:
            candidates.append(min(1.0, max(0.0, t)))
    if candidates:
        return min(candidates)
    return 1.0 if _point_in_polygon(end, polygon) else None
