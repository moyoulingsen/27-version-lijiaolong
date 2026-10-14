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
RULE_DAMAGE_PER_SHOT = 20
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


# Positions and HP are copied from map/config/dataset_snapshot.yaml.
FIELD_ENTITIES = (
    FieldEntity("RED BASE", 1.0, 7.5, "red", "base", hp=5000, max_hp=5000),
    FieldEntity("RED OUTPOST", 8.0, 7.5, "red", "outpost", hp=1000, max_hp=1000),
    FieldEntity("BLUE OUTPOST", 20.0, 7.5, "blue", "outpost", 6, 1000, 1000),
    FieldEntity("BLUE BASE", 27.0, 7.5, "blue", "base", 7, 5000, 5000),
    FieldEntity("HERO", 26.931, 6.945, "blue", "robot", 1, 200, 200),
    FieldEntity("ENGINEER", 25.796, 8.755, "blue", "robot", 2, 250, 250),
    FieldEntity("INFANTRY 3", 24.961, 9.131, "blue", "robot", 3, 200, 200),
    FieldEntity("INFANTRY 4", 24.616, 8.549, "blue", "robot", 4, 200, 200),
    FieldEntity("AERIAL", 26.658, 2.094, "blue", "robot", 5, 100, 100),
    FieldEntity("SENTRY", 25.186, 6.675, "blue", "robot", 8, 400, 400),
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
    ammo: int = 120
    pending_ammo: int = 0
    economy: int = 300
    fire_rate: int = RULE_FIRE_RATE_MAX
    damage_per_shot: int = RULE_DAMAGE_PER_SHOT
    own_outpost_hp: int = 1000
    own_base_hp: int = 5000
    enemy_outpost_hp: float = 1000.0
    enemy_base_hp: float = 5000.0
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
    ) -> None:
        if target_id not in (1, 2, 3, 4, 8):
            raise ValueError(f"target {target_id} is not a controllable ground robot")
        if elapsed_seconds < 0.0:
            raise ValueError("elapsed_seconds must be non-negative")
        length = math.hypot(move_x, move_y)
        if length > 1.0:
            move_x /= length
            move_y /= length
        position = self.robot_positions[target_id]
        position[0], position[1] = arena.clamp(
            position[0] + move_x * speed * elapsed_seconds,
            position[1] + move_y * speed * elapsed_seconds,
        )

    def robot_position(self, target_id: int) -> tuple[float, float]:
        position = self.robot_positions[target_id]
        return position[0], position[1]

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
            # Return above both possible recovery thresholds so the F9 helper
            # demonstrates aggressive patrol instead of remaining in recovery.
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
        self._validate_adjustment_direction(direction)
        self.damage_per_shot = max(1, min(RULE_DAMAGE_PER_SHOT, self.damage_per_shot + direction))
        self._set_event(f"单发伤害已调整为 {self.damage_per_shot} HP")

    def adjust_defence_buff(self, direction: int) -> None:
        self._validate_adjustment_direction(direction)
        self.defence_buff = max(0, min(100, self.defence_buff + 10 * direction))
        self._set_event(f"防御增益已调整为 {self.defence_buff}%")

    def adjust_own_outpost_health(self, direction: int) -> None:
        self._validate_adjustment_direction(direction)
        self.own_outpost_hp = max(
            0,
            min(1000, self.own_outpost_hp + 100 * direction),
        )
        self._set_event(f"己方前哨血量已调整为 {self.own_outpost_hp}")

    def adjust_own_base_health(self, direction: int) -> None:
        self._validate_adjustment_direction(direction)
        self.own_base_hp = max(0, min(5000, self.own_base_hp + 500 * direction))
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
    ) -> DecisionView:
        if elapsed_seconds < 0.0:
            raise ValueError("elapsed_seconds must be non-negative")
        self.pending_ammo = max(0, min(500, self.pending_ammo))
        self._finish_if_base_destroyed()
        simulation_elapsed = 0.0 if self.game_paused else elapsed_seconds
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
                if hit_target_id is not None:
                    self._apply_fire_damage(
                        hit_target_id,
                        float(self.damage_per_shot * spent),
                    )
        return decision

    def _apply_fire_damage(self, target_id: int, damage: float) -> None:
        if damage <= 0.0:
            return
        if target_id == 6:
            self.enemy_outpost_hp = max(0.0, self.enemy_outpost_hp - damage)
        elif target_id == 7:
            self.enemy_base_hp = max(0.0, self.enemy_base_hp - damage)
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
