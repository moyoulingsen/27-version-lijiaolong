"""Task-one referee inputs and expected high-level decision outputs."""

from __future__ import annotations

from dataclasses import dataclass, field
import math

from .core import Arena, SentryState


HOME = (4.971, 7.5)
SUPPLY = (2.0, 1.0)
ATTACK = (17.0, 10.0)
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
SUPPLY_ZONE = (0.5, 3.7, 0.2, 2.4)
CONSERVATIVE_PATROL_POINTS = ((5.0, 5.0), (9.0, 5.0), (9.0, 9.0))
AGGRESSIVE_PATROL_POINTS = ((12.0, 3.0), (16.0, 7.5), (12.3, 11.7))
PATROL_POINTS = CONSERVATIVE_PATROL_POINTS


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


# Positions and HP are copied from map/config/dataset_snapshot.yaml.
FIELD_ENTITIES = (
    FieldEntity("RED BASE", 1.0, 7.5, "red", "base", hp=5000, max_hp=5000),
    FieldEntity("RED OUTPOST", 8.0, 7.5, "red", "outpost", hp=RULE_OUTPOST_HP, max_hp=RULE_OUTPOST_HP),
    FieldEntity("BLUE OUTPOST", 20.0, 7.5, "blue", "outpost", 6, RULE_OUTPOST_HP, RULE_OUTPOST_HP),
    FieldEntity("BLUE BASE", 27.0, 7.5, "blue", "base", 7, RULE_BASE_HP, RULE_BASE_HP),
    FieldEntity("HERO", 26.931, 6.945, "blue", "robot", 1, ROBOT_PROFILES[1].max_hp, ROBOT_PROFILES[1].max_hp),
    FieldEntity("ENGINEER", 25.796, 8.755, "blue", "robot", 2, ROBOT_PROFILES[2].max_hp, ROBOT_PROFILES[2].max_hp),
    FieldEntity("INFANTRY 3", 24.961, 9.131, "blue", "robot", 3, ROBOT_PROFILES[3].max_hp, ROBOT_PROFILES[3].max_hp),
    FieldEntity("INFANTRY 4", 24.616, 8.549, "blue", "robot", 4, ROBOT_PROFILES[4].max_hp, ROBOT_PROFILES[4].max_hp),
    FieldEntity("AERIAL", 26.658, 2.094, "blue", "robot", 5, ROBOT_PROFILES[5].max_hp, ROBOT_PROFILES[5].max_hp),
    FieldEntity("SENTRY", 25.186, 6.675, "blue", "robot", 8, ROBOT_PROFILES[8].max_hp, ROBOT_PROFILES[8].max_hp),
)

# Friendly spawn points are simulation defaults on traversable map cells.
# Robot 8 uses the existing SentryState rather than a duplicate robot state.
OWN_FIELD_ENTITIES = (
    FieldEntity("RED HERO", 2.5, 5.0, "red", "robot", 1, ROBOT_PROFILES[1].max_hp, ROBOT_PROFILES[1].max_hp),
    FieldEntity("RED ENGINEER", 5.0, 5.0, "red", "robot", 2, ROBOT_PROFILES[2].max_hp, ROBOT_PROFILES[2].max_hp),
    FieldEntity("RED INFANTRY 3", 6.7, 7.0, "red", "robot", 3, ROBOT_PROFILES[3].max_hp, ROBOT_PROFILES[3].max_hp),
    FieldEntity("RED INFANTRY 4", 7.0, 10.0, "red", "robot", 4, ROBOT_PROFILES[4].max_hp, ROBOT_PROFILES[4].max_hp),
    FieldEntity("RED AERIAL", 3.0, 3.0, "red", "robot", 5, ROBOT_PROFILES[5].max_hp, ROBOT_PROFILES[5].max_hp),
    FieldEntity("RED SENTRY", HOME[0], HOME[1], "red", "robot", 8, ROBOT_PROFILES[8].max_hp, ROBOT_PROFILES[8].max_hp),
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
    economy: int = 300
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
    _last_minute: int = 7
    _ammo_shot_accumulator: float = field(default=0.0, repr=False)
    _health_recovery_active: bool = field(default=False, repr=False)
    _dodge_phase: int = field(default=-1, repr=False)
    _unseen_damage_accumulator: float = field(default=0.0, repr=False)
    _unseen_damage_window_remaining: float = field(default=0.0, repr=False)

    @property
    def health_threshold(self) -> int:
        return 160 if self.defence_buff >= 60 else 200

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

    def resolve_fire_target(
        self,
        sentry: SentryState,
        preferred_target: int = 0,
        *,
        maximum_distance: float = WEAPON_RANGE,
        alignment_tolerance: float = FIRE_ALIGNMENT_TOLERANCE,
    ) -> int | None:
        """Return the unit actually intersected by the simulated gun barrel."""
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
            if angle_error <= alignment_tolerance:
                aligned.append((angle_error, distance, target_id))
        if not aligned:
            return None
        return min(aligned)[2]

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
            self.death_elapsed = 0.0
        elif self.sentry_hp > 0.0:
            self.death_elapsed = None
        damage = previous_health - self.sentry_hp
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
        self.ammo = max(0, min(1000, self.ammo + 20 * direction))
        self._set_event(f"当前弹量已调整为 {self.ammo}")

    def adjust_pending_ammo(self, direction: int) -> None:
        self._validate_adjustment_direction(direction)
        self.pending_ammo = max(0, min(500, self.pending_ammo + 25 * direction))
        self._set_event(f"待领弹药已调整为 {self.pending_ammo}")

    def adjust_economy(self, direction: int) -> None:
        self._validate_adjustment_direction(direction)
        self.economy = max(0, min(1000, self.economy + 50 * direction))
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

    def adjust_own_outpost_health(self, direction: int) -> None:
        self._validate_adjustment_direction(direction)
        self.own_outpost_hp = max(
            0,
            min(RULE_OUTPOST_HP, self.own_outpost_hp + 100 * direction),
        )
        self._set_event(f"己方前哨血量已调整为 {self.own_outpost_hp}")

    def adjust_own_base_health(self, direction: int) -> None:
        self._validate_adjustment_direction(direction)
        self.own_base_hp = max(0, min(RULE_BASE_HP, self.own_base_hp + 500 * direction))
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
        self.pending_ammo = max(0, min(500, self.pending_ammo))
        self._finish_if_base_destroyed()
        simulation_elapsed = 0.0 if self.game_paused else elapsed_seconds
        sentry.heat = max(
            0.0,
            sentry.heat
            - float(ROBOT_PROFILES[8].heat_cooling_per_second or 0)
            * simulation_elapsed,
        )
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
            current_minute = math.ceil(self.remaining_time / 60.0)
            if current_minute < self._last_minute:
                self.pending_ammo = min(
                    500,
                    self.pending_ammo + 100 * (self._last_minute - current_minute),
                )
                self._last_minute = current_minute

        if not self.game_paused:
            self._update_respawn(simulation_elapsed)
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
        requested = bool(decision.shoot_mode) if fire_request is None else fire_request
        if requested and self.ammo > 0 and not self.respawn_fire_locked:
            self._ammo_shot_accumulator += self.fire_rate * simulation_elapsed
            spent = min(int(self._ammo_shot_accumulator), self.ammo)
            if spent:
                self.ammo = max(0, self.ammo - spent)
                self._ammo_shot_accumulator -= spent
                sentry.heat = min(
                    float(ROBOT_PROFILES[8].heat_capacity or 0),
                    sentry.heat + spent * float(ROBOT_PROFILES[8].heat_per_shot or 0),
                )
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
        defence_buff: float = 0.0,
        critical_zone: bool = False,
        armor_zone: str | None = None,
        shots: int = 1,
        team: str = "blue",
    ) -> int:
        if not isinstance(shots, int) or isinstance(shots, bool) or shots < 1:
            raise ValueError("shots must be a positive integer")
        if team not in ("blue", "red"):
            raise ValueError(f"unknown team {team}")
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

    def _apply_fire_damage(
        self, target_id: int, damage: float, *, team: str = "blue"
    ) -> None:
        if damage <= 0.0:
            return
        if team == "red":
            if target_id == 6:
                self.own_outpost_hp = max(0, self.own_outpost_hp - int(damage))
            elif target_id == 7:
                shield_damage = min(self.own_base_shield, damage)
                self.own_base_shield -= shield_damage
                self.own_base_hp = max(0, self.own_base_hp - int(damage - shield_damage))
            elif target_id == 8:
                previous_health = self.sentry_hp
                self.sentry_hp = max(0.0, self.sentry_hp - damage)
                if previous_health > 0.0 and self.sentry_hp == 0.0:
                    self.death_elapsed = 0.0
            elif target_id in self.own_robot_hp:
                self.own_robot_hp[target_id] = max(0.0, self.own_robot_hp[target_id] - damage)
            self._finish_if_base_destroyed()
            return
        if target_id == 6:
            self.enemy_outpost_hp = max(0.0, self.enemy_outpost_hp - damage)
        elif target_id == 7:
            shield_damage = min(self.enemy_base_shield, damage)
            self.enemy_base_shield -= shield_damage
            remaining_damage = damage - shield_damage
            self.enemy_base_hp = max(0.0, self.enemy_base_hp - remaining_damage)
        elif target_id in self.robot_hp:
            self.robot_hp[target_id] = max(0.0, self.robot_hp[target_id] - damage)
        self._finish_if_base_destroyed()

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
            shoot_mode = int(at_attack and self.ammo > 0 and not self.respawn_fire_locked)
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
        self._set_event("己方前哨被摧毁，小陀螺已开启")

    def inject_unseen_damage(self, sentry: SentryState) -> None:
        if self.sentry_hp <= 0.0:
            return
        self.sentry_hp = max(0.0, self.sentry_hp - 50.0)
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
        self._set_event("敌方前哨已被摧毁")

    def set_low_health(self) -> None:
        self.sentry_hp = 150.0
        self._set_event("血量设为 150，验证防御增益回血阈值")

    def finish_game(self, reason: str = "比赛结束，返回启动点") -> None:
        self.game_running = False
        self.game_finished = True
        self.game_paused = False
        self.remaining_time = 0.0
        self._set_event(reason)

    def kill_sentry(self) -> None:
        self.sentry_hp = 0.0
        self.death_elapsed = 0.0
        self._set_event("哨兵阵亡，开始复活计时")

    def _update_respawn(self, elapsed_seconds: float) -> None:
        if self.sentry_hp > 0.0 or self.death_elapsed is None:
            return
        self.death_elapsed += elapsed_seconds
        if self.death_elapsed >= 5.5:
            self.sentry_hp = 400.0
            self.ammo = 0
            self.death_elapsed = None
            self.respawn_fire_locked = True
            self._set_event("哨兵已复活，返回补给区解锁射击")

    def _update_supply(self, sentry: SentryState, elapsed_seconds: float) -> None:
        if not in_supply_zone(sentry.x, sentry.y):
            return
        if self.respawn_fire_locked:
            self.respawn_fire_locked = False
            self._set_event("发射机构已解锁")
        if 0.0 < self.sentry_hp < 400.0:
            self.sentry_hp = min(400.0, self.sentry_hp + 100.0 * elapsed_seconds)
        if self.ammo == 0 and self.pending_ammo > 0:
            self.ammo = self.pending_ammo
            self.pending_ammo = 0
            self._set_event("待领取弹药已发放")

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


def in_supply_zone(x: float, y: float) -> bool:
    minimum_x, maximum_x, minimum_y, maximum_y = SUPPLY_ZONE
    return minimum_x <= x <= maximum_x and minimum_y <= y <= maximum_y
