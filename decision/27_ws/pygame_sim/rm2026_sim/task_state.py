"""Task-one referee inputs and expected high-level decision outputs."""

from __future__ import annotations

from dataclasses import dataclass, field
import math

from .core import Arena, SentryState


HOME = (4.971, 7.5)
SUPPLY = (2.0, 1.0)
ATTACK = (16.0, 11.0)
MATCH_DURATION = 420.0
SUPPLY_ZONE = (0.5, 3.7, 0.2, 2.4)
CONSERVATIVE_PATROL_POINTS = ((5.0, 5.0), (9.0, 5.0), (9.0, 9.0))
AGGRESSIVE_PATROL_POINTS = ((12.0, 3.0), (16.0, 7.5), (12.0, 12.0))
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
    remaining_time: float = MATCH_DURATION
    sentry_hp: float = 400.0
    defence_buff: int = 60
    ammo: int = 120
    pending_ammo: int = 0
    own_outpost_hp: int = 1000
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

    @property
    def health_threshold(self) -> int:
        return 160 if self.defence_buff >= 60 else 200

    @property
    def patrol_name(self) -> str:
        return "激进巡逻" if self.aggressive_patrol else "保守巡逻"

    @property
    def patrol_points(self) -> tuple[tuple[float, float], ...]:
        return AGGRESSIVE_PATROL_POINTS if self.aggressive_patrol else CONSERVATIVE_PATROL_POINTS

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

    def toggle_patrol_mode(self) -> None:
        self.aggressive_patrol = not self.aggressive_patrol
        self.patrol_index = 0
        self._set_event(f"已切换为{self.patrol_name}")

    def reset_match_time(self) -> None:
        self.remaining_time = MATCH_DURATION
        self.game_running = True
        self.game_finished = False
        self._last_minute = math.ceil(MATCH_DURATION / 60.0)
        self._set_event("比赛时间已重置为 420 秒")

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

    def adjust_sentry_health(self, direction: int) -> None:
        if direction not in (-1, 1):
            raise ValueError("direction must be -1 or 1")
        previous_health = self.sentry_hp
        self.sentry_hp = max(0.0, min(400.0, self.sentry_hp + 40.0 * direction))
        if self.sentry_hp == 0.0 and previous_health > 0.0:
            self.death_elapsed = 0.0
        elif self.sentry_hp > 0.0:
            self.death_elapsed = None
        self._set_event(f"己方哨兵血量已调整为 {round(self.sentry_hp)}")

    def update(
        self,
        elapsed_seconds: float,
        sentry: SentryState,
        decision_override: DecisionView | None = None,
    ) -> DecisionView:
        if elapsed_seconds < 0.0:
            raise ValueError("elapsed_seconds must be non-negative")
        self.event_message_remaining = max(0.0, self.event_message_remaining - elapsed_seconds)

        if self.game_running:
            self.remaining_time = max(0.0, self.remaining_time - elapsed_seconds)
            current_minute = math.ceil(self.remaining_time / 60.0)
            if current_minute < self._last_minute:
                self.pending_ammo += 100 * (self._last_minute - current_minute)
                self._last_minute = current_minute

        self._update_respawn(elapsed_seconds)
        self._update_supply(sentry, elapsed_seconds)
        self._update_patrol(sentry)
        self.dodge_remaining = max(0.0, self.dodge_remaining - elapsed_seconds)

        decision = decision_override or self.evaluate(sentry)
        if decision.shoot_mode and self.enemy_outpost_hp > 0.0:
            self.enemy_outpost_hp = max(0.0, self.enemy_outpost_hp - 240.0 * elapsed_seconds)
            self._ammo_shot_accumulator += 10.0 * elapsed_seconds
            spent = int(self._ammo_shot_accumulator)
            if spent:
                self.ammo = max(0, self.ammo - spent)
                self._ammo_shot_accumulator -= spent
        return decision

    def evaluate(self, sentry: SentryState) -> DecisionView:
        spin_mode = int(
            self.game_running and self.sentry_hp > 0.0 and self.own_outpost_hp == 0
        )
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
        elif self.sentry_hp < self.health_threshold:
            behavior, goal = "低血量回血", SUPPLY
        elif self.enemy_outpost_hp > 0.0:
            behavior, posture, goal, target = "攻击敌方前哨", 1, ATTACK, 6
            at_attack = _distance((sentry.x, sentry.y), ATTACK) <= 0.20
            shoot_mode = int(at_attack and self.ammo > 0 and not self.respawn_fire_locked)
        elif self.ammo == 0:
            behavior = "前往补给领弹" if self.pending_ammo > 0 else "无弹站桩"
            goal = SUPPLY if self.pending_ammo > 0 else HOME
        elif self.dodge_remaining > 0.0 and self.dodge_goal is not None:
            behavior, goal = "视野外受伤躲避", self.dodge_goal

        tripod_mode = int(shoot_mode == 0)
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
        current_goal = self.evaluate(sentry).goal
        self.sentry_hp = max(0.0, self.sentry_hp - 50.0)
        if current_goal is None or _distance((sentry.x, sentry.y), current_goal) > 0.15:
            self._set_event("视野外受伤 -50，移动中不触发躲避")
            return
        direction = 0.8 if sentry.x <= 27.0 else -0.8
        self.dodge_goal = Arena().clamp(sentry.x + direction, sentry.y)
        self.dodge_remaining = 4.0
        self._set_event("视野外受伤 -50，已触发躲避")

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

    def finish_game(self) -> None:
        self.game_running = False
        self.game_finished = True
        self.remaining_time = 0.0
        self._set_event("比赛结束，返回启动点")

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
