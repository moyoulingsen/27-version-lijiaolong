"""Full-map, single-sentry, end-to-end assault environment."""

from __future__ import annotations

from dataclasses import dataclass
import math
import random
from typing import Mapping

import numpy as np

from rm2026_sim.core import SentryState, normalize_angle
from rm2026_sim.field_geometry import BLUE_BASE, BLUE_OUTPOST, RED_HOME
from rm2026_sim.navigation import ROBOT_ENTITY_COLLISION_RADIUS
from rm2026_sim.task_state import (
    AMMO_CAP,
    BUFFER_ENERGY_CAP,
    FIRE_ALIGNMENT_TOLERANCE,
    ROBOT_PROFILES,
    DETECTION_RANGE,
    ROBOT_VISION_HALF_ANGLE,
    WEAPON_RANGE,
    DecisionView,
    FireResult,
    TaskScenario,
)

from rl.config import AssaultConfig
from .field import AssaultField, TacticalFields
from .local_map import LOCAL_MAP_CHANNELS, LocalMapEncoder


MOVE_DIRECTIONS = (
    (0.0, 0.0),
    (0.0, 1.0),
    (math.sqrt(0.5), math.sqrt(0.5)),
    (1.0, 0.0),
    (math.sqrt(0.5), -math.sqrt(0.5)),
    (0.0, -1.0),
    (-math.sqrt(0.5), -math.sqrt(0.5)),
    (-1.0, 0.0),
    (-math.sqrt(0.5), math.sqrt(0.5)),
)
SCALAR_OBSERVATION_SIZE = 37
CRITIC_OBSERVATION_SIZE = 25


@dataclass(frozen=True, slots=True)
class SentryAction:
    move_direction: int
    posture: int
    reinforce: int
    fire: int
    spin_speed: float
    turret_speed: float


@dataclass(frozen=True, slots=True)
class AssaultObservation:
    scalar: np.ndarray
    spatial: np.ndarray
    critic: np.ndarray
    recurrent_reset: bool = False


@dataclass(frozen=True, slots=True)
class AssaultStep:
    observation: AssaultObservation
    reward: float
    raw_reward: float
    terminated: bool
    truncated: bool
    info: Mapping[str, object]


class SentryAssaultEnv:
    """One red sentry must destroy the blue outpost and then the blue base."""

    scalar_size = SCALAR_OBSERVATION_SIZE
    spatial_shape = (LOCAL_MAP_CHANNELS, 41, 41)
    critic_size = CRITIC_OBSERVATION_SIZE

    def __init__(
        self,
        config: AssaultConfig | None = None,
        *,
        field: AssaultField | None = None,
        tactical_fields: TacticalFields | None = None,
    ) -> None:
        self.config = config or AssaultConfig()
        self.field = field or AssaultField.load()
        self.tactical_fields = (
            tactical_fields
            if tactical_fields is not None
            else self.field.tactical_fields(
                minimum_fire_range=(
                    self.config.reward_v3.preferred_fire_min_range
                ),
                maximum_fire_range=(
                    self.config.reward_v3.preferred_fire_max_range
                ),
                minimum_clearance=(
                    self.config.reward_v3.preferred_fire_clearance
                ),
            )
            if self.config.reward_version == 3
            else None
        )
        self.spatial_shape = (
            LOCAL_MAP_CHANNELS,
            self.config.local_map_cells,
            self.config.local_map_cells,
        )
        self.local_map = LocalMapEncoder(self.field, self.config)
        self._rng = random.Random()
        self.task = TaskScenario()
        self.sentry = SentryState()
        self._last_collision = False
        self._stuck_seconds = 0.0
        self._lowest_outpost_hp = 0.0
        self._lowest_base_durability = 0.0
        self._outpost_bonus_paid = False
        self._base_bonus_paid = False
        self._shaping_target_id = 6
        self._best_target_distance = 0.0
        self._previous_attack_distance = 0.0
        self._best_target_angle_error = math.pi
        self._aim_tracking_active = False
        self._distance_milestones_paid: set[float] = set()
        self._aim_milestones_paid: set[float] = set()
        self._first_fire_command_paid = False
        self._sensor_fire_bonus_paid = False
        self._range_fire_bonus_paid = False
        self._valid_solution_bonus_paid = False
        self._hit_targets_paid: set[int] = set()
        self._visited_cells: set[tuple[int, int]] = set()
        self._exploration_reward_total = 0.0
        self._escaped_stuck = False
        self._range_bonus_paid = False
        self._line_of_sight_bonus_paid = False
        self._step_index = 0
        self._last_observation: AssaultObservation | None = None
        self._seconds_since_damage = 0.0
        self.reset()

    def reset(self, *, seed: int | None = None) -> AssaultObservation:
        if seed is not None:
            self._rng.seed(seed)
        self.task = TaskScenario()
        self.task.remaining_time = self.config.episode_seconds
        self.task._last_minute = math.ceil(self.config.episode_seconds / 60.0)
        self.sentry = SentryState(
            x=RED_HOME[0],
            y=RED_HOME[1],
            movement_speed=self.config.movement_speed,
        )
        self.sentry.cancel_manual_control()
        self.task.radar_random_seed = seed if seed is not None else 2026
        self.task.ammo = min(AMMO_CAP, self.config.initial_ammunition)
        self.task.field_zone_overrides = {
            name: [[float(x), float(y)] for x, y in points]
            for name, points in self.field.zone_overrides.items()
        }
        self.task.configure_patrol_routes(
            self.field.patrol_routes["conservative"],
            self.field.patrol_routes["aggressive"],
        )
        for target_id in tuple(self.task.robot_hp):
            self.task.robot_hp[target_id] = 0.0
        for target_id in tuple(self.task.own_robot_hp):
            self.task.own_robot_hp[target_id] = 0.0
        self.local_map.reset()
        self._last_collision = False
        self._stuck_seconds = 0.0
        self._lowest_outpost_hp = float(self.task.enemy_outpost_hp)
        self._lowest_base_durability = self._base_durability()
        self._outpost_bonus_paid = False
        self._base_bonus_paid = False
        self._shaping_target_id = 6
        self._best_target_distance, self._best_target_angle_error = (
            self._target_metrics(BLUE_OUTPOST)
        )
        self._previous_attack_distance = self._attack_route_distance(6)
        self._aim_tracking_active = False
        self._distance_milestones_paid.clear()
        self._aim_milestones_paid.clear()
        self._first_fire_command_paid = False
        self._sensor_fire_bonus_paid = False
        self._range_fire_bonus_paid = False
        self._valid_solution_bonus_paid = False
        self._hit_targets_paid.clear()
        self._visited_cells = {self._exploration_cell()}
        self._exploration_reward_total = 0.0
        self._escaped_stuck = False
        self._range_bonus_paid = False
        self._line_of_sight_bonus_paid = False
        self._step_index = 0
        self._seconds_since_damage = 0.0
        self._last_observation = self._observation(recurrent_reset=True)
        return self._last_observation

    def _base_durability(self) -> float:
        return float(self.task.enemy_base_hp + self.task.enemy_base_shield)

    def _active_target(self) -> tuple[int, tuple[float, float]]:
        if self.task.enemy_outpost_hp > 0.0:
            return 6, BLUE_OUTPOST
        return 7, BLUE_BASE

    def _target_metrics(self, target: tuple[float, float]) -> tuple[float, float]:
        delta_x = target[0] - self.sentry.x
        delta_y = target[1] - self.sentry.y
        distance = math.hypot(delta_x, delta_y)
        angle_error = abs(
            normalize_angle(math.atan2(delta_y, delta_x) - self.sentry.turret_angle)
        )
        return distance, angle_error

    def _target_in_sensor_view(self, target: tuple[float, float]) -> bool:
        return self.task.target_in_sensor_view(
            (self.sentry.x, self.sentry.y),
            target,
            self.sentry.turret_angle,
            maximum_distance=DETECTION_RANGE,
            half_angle=ROBOT_VISION_HALF_ANGLE,
        )

    def _tactical_field_value(self, values: np.ndarray) -> float:
        row, column = self.field.collision_grid.world_to_cell(
            self.sentry.x,
            self.sentry.y,
        )
        return float(values[row, column])

    def _attack_route_distance(self, target_id: int) -> float:
        if self.tactical_fields is None:
            _, target = self._active_target()
            return self._target_metrics(target)[0]
        values = (
            self.tactical_fields.outpost_distance
            if target_id == 6
            else self.tactical_fields.base_distance
        )
        return self._tactical_field_value(values)

    def _wall_clearance(self) -> float:
        if self.tactical_fields is None:
            return math.inf
        return self._tactical_field_value(self.tactical_fields.wall_clearance)

    def _exploration_cell(self) -> tuple[int, int]:
        size = self.config.exploration_cell_size
        return int(self.sentry.x / size), int(self.sentry.y / size)

    def _shaping_reward_v1(
        self,
        *,
        fire_requested: bool,
        fire_fired: bool,
        fire_visible: bool,
        fire_in_range: bool,
        valid_fire: bool,
        fire_target_id: int,
        permanent_lock_triggered: bool,
    ) -> tuple[float, dict[str, float]]:
        target_id, target = self._active_target()
        distance, angle_error = self._target_metrics(target)
        distance_reward = 0.0
        distance_milestone_reward = 0.0
        aim_reward = 0.0
        aim_milestone_reward = 0.0
        exploration_reward = 0.0
        range_reward = 0.0
        line_of_sight_reward = 0.0
        valid_solution_reward = 0.0
        first_fire_command_reward = 0.0
        sensor_fire_reward = 0.0
        range_fire_reward = 0.0
        valid_fire_step_reward = 0.0
        invalid_fire_reward = 0.0
        permanent_lock_reward = 0.0
        if target_id != self._shaping_target_id:
            self._shaping_target_id = target_id
            self._best_target_distance = distance
            self._best_target_angle_error = angle_error
            self._aim_tracking_active = False
            self._distance_milestones_paid.clear()
            self._aim_milestones_paid.clear()
            self._sensor_fire_bonus_paid = False
            self._range_fire_bonus_paid = False
            self._valid_solution_bonus_paid = False
            self._range_bonus_paid = False
            self._line_of_sight_bonus_paid = False
        else:
            distance_improvement = max(0.0, self._best_target_distance - distance)
            distance_reward = (
                distance_improvement * self.config.distance_progress_scale
            )
            self._best_target_distance = min(self._best_target_distance, distance)
            distance_milestones = (
                (12.0, self.config.distance_12m_bonus),
                (8.0, self.config.distance_8m_bonus),
                (DETECTION_RANGE, self.config.distance_sensor_bonus),
            )
            for threshold, bonus in distance_milestones:
                if threshold not in self._distance_milestones_paid and distance <= threshold:
                    self._distance_milestones_paid.add(threshold)
                    distance_milestone_reward += bonus
            if not self._range_bonus_paid and distance <= WEAPON_RANGE:
                self._range_bonus_paid = True
                range_reward = self.config.first_range_bonus
            has_line_of_sight = self._target_in_sensor_view(target)
            if not self._line_of_sight_bonus_paid and has_line_of_sight:
                self._line_of_sight_bonus_paid = True
                line_of_sight_reward = self.config.first_line_of_sight_bonus
            if distance <= DETECTION_RANGE:
                if not self._aim_tracking_active:
                    self._aim_tracking_active = True
                    self._best_target_angle_error = angle_error
                else:
                    aim_improvement = max(
                        0.0, self._best_target_angle_error - angle_error
                    )
                    aim_reward = aim_improvement * self.config.aim_progress_scale
                    self._best_target_angle_error = min(
                        self._best_target_angle_error, angle_error
                    )
                aim_milestones = (
                    (math.radians(30.0), self.config.aim_30deg_bonus),
                    (math.radians(15.0), self.config.aim_15deg_bonus),
                    (math.radians(8.0), self.config.aim_8deg_bonus),
                    (FIRE_ALIGNMENT_TOLERANCE, self.config.aim_4deg_bonus),
                )
                for threshold, bonus in aim_milestones:
                    if threshold not in self._aim_milestones_paid and angle_error <= threshold:
                        self._aim_milestones_paid.add(threshold)
                        aim_milestone_reward += bonus
            fire_matches_target = fire_target_id == target_id
            if (
                fire_fired
                and fire_visible
                and fire_matches_target
                and not self._sensor_fire_bonus_paid
            ):
                self._sensor_fire_bonus_paid = True
                sensor_fire_reward = self.config.first_sensor_fire_bonus
            if (
                fire_fired
                and fire_in_range
                and fire_matches_target
                and not self._range_fire_bonus_paid
            ):
                self._range_fire_bonus_paid = True
                range_fire_reward = self.config.first_range_fire_bonus
            valid_solution = valid_fire and fire_matches_target
            if valid_solution and not self._valid_solution_bonus_paid:
                self._valid_solution_bonus_paid = True
                valid_solution_reward = self.config.valid_solution_bonus
            if valid_solution:
                valid_fire_step_reward = self.config.valid_fire_step_bonus
        if fire_requested and fire_visible and not self._first_fire_command_paid:
            self._first_fire_command_paid = True
            first_fire_command_reward = self.config.first_fire_command_bonus
        if fire_requested and not valid_fire:
            invalid_fire_reward = -self.config.invalid_fire_penalty
        if permanent_lock_triggered:
            permanent_lock_reward = -self.config.permanent_heat_lock_penalty
        cell = self._exploration_cell()
        if (
            cell not in self._visited_cells
            and self._exploration_reward_total < self.config.exploration_reward_cap
        ):
            self._visited_cells.add(cell)
            exploration_reward = min(
                self.config.exploration_cell_bonus,
                self.config.exploration_reward_cap - self._exploration_reward_total,
            )
            self._exploration_reward_total += exploration_reward
        collision_reward = (
            -self.config.collision_penalty if self._last_collision else 0.0
        )
        stuck_multiplier = min(
            3.0,
            self._stuck_seconds / self.config.stuck_penalty_after_seconds,
        )
        stuck_reward = -self.config.stuck_penalty * stuck_multiplier
        escape_reward = (
            self.config.escape_stuck_bonus if self._escaped_stuck else 0.0
        )
        time_reward = -self.config.time_penalty_per_second * self.config.time_step
        components = {
            "distance_progress_score": distance_reward,
            "distance_milestone_score": distance_milestone_reward,
            "aim_progress_score": aim_reward,
            "aim_milestone_score": aim_milestone_reward,
            "exploration_score": exploration_reward,
            "first_range_score": range_reward,
            "first_line_of_sight_score": line_of_sight_reward,
            "first_fire_command_score": first_fire_command_reward,
            "first_sensor_fire_score": sensor_fire_reward,
            "first_range_fire_score": range_fire_reward,
            "valid_solution_score": valid_solution_reward,
            "valid_fire_step_score": valid_fire_step_reward,
            "invalid_fire_score": invalid_fire_reward,
            "permanent_heat_lock_score": permanent_lock_reward,
            "collision_score": collision_reward,
            "stuck_score": stuck_reward,
            "escape_stuck_score": escape_reward,
            "time_score": time_reward,
        }
        return sum(components.values()), components

    def _shaping_reward_v2(
        self,
        *,
        permanent_lock_triggered: bool,
    ) -> tuple[float, dict[str, float]]:
        reward = self.config.reward_v2
        target_id, target = self._active_target()
        distance, angle_error = self._target_metrics(target)
        distance_reward = 0.0
        aim_reward = 0.0
        if target_id != self._shaping_target_id:
            self._shaping_target_id = target_id
            self._best_target_distance = distance
            self._best_target_angle_error = angle_error
            self._aim_tracking_active = False
        else:
            distance_improvement = max(0.0, self._best_target_distance - distance)
            distance_reward = distance_improvement * reward.distance_progress_scale
            self._best_target_distance = min(self._best_target_distance, distance)
            if distance <= DETECTION_RANGE:
                if not self._aim_tracking_active:
                    self._aim_tracking_active = True
                    self._best_target_angle_error = angle_error
                else:
                    aim_improvement = max(
                        0.0,
                        self._best_target_angle_error - angle_error,
                    )
                    aim_reward = aim_improvement * reward.aim_progress_scale
                    self._best_target_angle_error = min(
                        self._best_target_angle_error,
                        angle_error,
                    )
        cell = self._exploration_cell()
        exploration_reward = 0.0
        if (
            cell not in self._visited_cells
            and self._exploration_reward_total < reward.exploration_reward_cap
        ):
            self._visited_cells.add(cell)
            exploration_reward = min(
                reward.exploration_cell_bonus,
                reward.exploration_reward_cap - self._exploration_reward_total,
            )
            self._exploration_reward_total += exploration_reward
        collision_reward = -reward.collision_penalty if self._last_collision else 0.0
        stuck_multiplier = min(
            3.0,
            self._stuck_seconds / reward.stuck_penalty_after_seconds,
        )
        components = {
            "v2_distance_progress_score": distance_reward,
            "v2_aim_progress_score": aim_reward,
            "v2_exploration_score": exploration_reward,
            "v2_collision_score": collision_reward,
            "v2_stuck_score": -reward.stuck_penalty * stuck_multiplier,
            "v2_time_score": -reward.time_penalty_per_second * self.config.time_step,
            "v2_permanent_heat_lock_score": (
                -reward.permanent_heat_lock_penalty
                if permanent_lock_triggered
                else 0.0
            ),
        }
        return sum(components.values()), components

    def _shaping_reward_v3(
        self,
        *,
        fire_requested: bool,
        valid_fire: bool,
        fire_target_id: int,
        permanent_lock_triggered: bool,
        movement_distance: float,
        damage_hp: float,
    ) -> tuple[float, dict[str, float]]:
        reward = self.config.reward_v3
        target_id, target = self._active_target()
        direct_distance, angle_error = self._target_metrics(target)
        route_distance = self._attack_route_distance(target_id)
        target_changed = target_id != self._shaping_target_id
        route_progress_score = (
            0.0
            if target_changed
            else (self._previous_attack_distance - route_distance)
            * reward.route_progress_scale
        )
        self._previous_attack_distance = route_distance
        movement_score = -movement_distance * reward.movement_cost_per_meter

        aim_score = 0.0
        if target_changed:
            self._shaping_target_id = target_id
            self._best_target_angle_error = angle_error
            self._aim_tracking_active = False
        elif direct_distance <= DETECTION_RANGE:
            if not self._aim_tracking_active:
                self._aim_tracking_active = True
                self._best_target_angle_error = angle_error
            else:
                improvement = max(0.0, self._best_target_angle_error - angle_error)
                aim_score = improvement * reward.aim_progress_scale
                self._best_target_angle_error = min(
                    self._best_target_angle_error,
                    angle_error,
                )

        cell = self._exploration_cell()
        exploration_score = 0.0
        if (
            cell not in self._visited_cells
            and self._exploration_reward_total < reward.exploration_reward_cap
        ):
            self._visited_cells.add(cell)
            exploration_score = min(
                reward.exploration_cell_bonus,
                reward.exploration_reward_cap - self._exploration_reward_total,
            )
            self._exploration_reward_total += exploration_score

        clearance = self._wall_clearance()
        in_preferred_range = (
            reward.preferred_fire_min_range
            <= direct_distance
            <= reward.preferred_fire_max_range
        )
        open_fire_position = (
            in_preferred_range
            and clearance >= reward.preferred_fire_clearance
        )
        fire_matches_target = fire_target_id == target_id
        open_fire_score = (
            reward.open_fire_bonus_per_second * self.config.time_step
            if valid_fire and fire_matches_target and open_fire_position
            else 0.0
        )
        clearance_deficit = max(
            0.0,
            reward.preferred_fire_clearance - clearance,
        ) / max(reward.preferred_fire_clearance, 1e-6)
        wall_score = (
            -reward.wall_proximity_penalty_per_second
            * self.config.time_step
            * clearance_deficit
            if direct_distance <= WEAPON_RANGE
            else 0.0
        )
        invalid_fire_score = (
            -reward.invalid_fire_penalty
            if fire_requested and not valid_fire
            else 0.0
        )
        if damage_hp > 0.0:
            self._seconds_since_damage = 0.0
        else:
            self._seconds_since_damage += self.config.time_step
        no_damage_multiplier = min(
            3.0,
            max(
                0.0,
                self._seconds_since_damage - reward.no_damage_grace_seconds,
            )
            / reward.no_damage_grace_seconds,
        )
        no_damage_score = (
            -reward.no_damage_penalty_per_second
            * self.config.time_step
            * no_damage_multiplier
        )
        collision_score = (
            -reward.collision_penalty if self._last_collision else 0.0
        )
        stuck_multiplier = min(
            3.0,
            self._stuck_seconds / reward.stuck_penalty_after_seconds,
        )
        components = {
            "v3_route_progress_score": route_progress_score,
            "v3_movement_score": movement_score,
            "v3_aim_progress_score": aim_score,
            "v3_exploration_score": exploration_score,
            "v3_open_fire_position_score": open_fire_score,
            "v3_wall_proximity_score": wall_score,
            "v3_invalid_fire_score": invalid_fire_score,
            "v3_no_damage_score": no_damage_score,
            "v3_collision_score": collision_score,
            "v3_stuck_score": -reward.stuck_penalty * stuck_multiplier,
            "v3_time_score": -reward.time_penalty_per_second
            * self.config.time_step,
            "v3_permanent_heat_lock_score": (
                -reward.permanent_heat_lock_penalty
                if permanent_lock_triggered
                else 0.0
            ),
        }
        return sum(components.values()), components

    def _shaping_reward(
        self,
        *,
        fire_requested: bool,
        fire_fired: bool,
        fire_visible: bool,
        fire_in_range: bool,
        valid_fire: bool,
        fire_target_id: int,
        permanent_lock_triggered: bool,
        movement_distance: float,
        damage_hp: float,
    ) -> tuple[float, dict[str, float]]:
        if self.config.reward_version == 3:
            return self._shaping_reward_v3(
                fire_requested=fire_requested,
                valid_fire=valid_fire,
                fire_target_id=fire_target_id,
                permanent_lock_triggered=permanent_lock_triggered,
                movement_distance=movement_distance,
                damage_hp=damage_hp,
            )
        if self.config.reward_version == 2:
            return self._shaping_reward_v2(
                permanent_lock_triggered=permanent_lock_triggered,
            )
        return self._shaping_reward_v1(
            fire_requested=fire_requested,
            fire_fired=fire_fired,
            fire_visible=fire_visible,
            fire_in_range=fire_in_range,
            valid_fire=valid_fire,
            fire_target_id=fire_target_id,
            permanent_lock_triggered=permanent_lock_triggered,
        )

    @staticmethod
    def _angle_features(
        source: tuple[float, float],
        target: tuple[float, float],
        reference_angle: float,
    ) -> tuple[float, float, float, float]:
        delta_x = target[0] - source[0]
        delta_y = target[1] - source[1]
        distance = math.hypot(delta_x, delta_y)
        relative = normalize_angle(math.atan2(delta_y, delta_x) - reference_angle)
        return math.sin(relative), math.cos(relative), distance, abs(relative)

    def _scalar_observation(self) -> np.ndarray:
        task = self.task
        sentry = self.sentry
        maximum_hp = max(1.0, task.robot_max_hp(8, team="red"))
        ammunition_limit = max(1, task.robot_ammunition_limit(8))
        heat_limit = max(1, task.robot_q2_limit(8, team="red") or 1)
        power_limit = max(1.0, float(task.robot_power_limit(8, team="red") or 1.0))
        outpost = self._angle_features(
            (sentry.x, sentry.y), BLUE_OUTPOST, sentry.turret_angle
        )
        base = self._angle_features(
            (sentry.x, sentry.y), BLUE_BASE, sentry.turret_angle
        )
        can_fire, _ = task.robot_can_fire(8, team="red", sentry=sentry)
        posture = task.active_posture
        values = (
            task.remaining_time / self.config.episode_seconds,
            sentry.x / self.field.arena.width,
            sentry.y / self.field.arena.height,
            math.sin(sentry.spin_angle),
            math.cos(sentry.spin_angle),
            math.sin(sentry.turret_angle),
            math.cos(sentry.turret_angle),
            max(-1.0, min(1.0, sentry.spin_speed / self.config.maximum_spin_speed)),
            max(-1.0, min(1.0, sentry.turret_speed / self.config.maximum_turret_speed)),
            task.sentry_hp / maximum_hp,
            task.robot_ammunition(8, team="red") / ammunition_limit,
            task.robot_heat_value(8, team="red", sentry=sentry) / heat_limit,
            sentry.chassis_power / power_limit,
            task.sentry_buffer_energy / BUFFER_ENERGY_CAP,
            min(1.0, task.sentry_chassis_power_cut_remaining / 5.0),
            float(posture == 1),
            float(posture == 2),
            float(posture == 3),
            float(task.posture_reinforced),
            min(1.0, task.posture_cooldown_remaining / 5.0),
            float(task.enemy_outpost_hp) / 1500.0,
            float(task.enemy_base_hp) / 5000.0,
            float(task.enemy_base_shield) / 150.0,
            outpost[0],
            outpost[1],
            min(1.0, outpost[2] / math.hypot(self.field.arena.width, self.field.arena.height)),
            float(outpost[2] <= WEAPON_RANGE),
            min(1.0, outpost[3] / math.pi),
            base[0],
            base[1],
            min(1.0, base[2] / math.hypot(self.field.arena.width, self.field.arena.height)),
            float(base[2] <= WEAPON_RANGE),
            min(1.0, base[3] / math.pi),
            float(task.enemy_outpost_hp > 0.0),
            float(can_fire),
            float(self._last_collision),
            min(1.0, self._stuck_seconds / 5.0),
        )
        if len(values) != SCALAR_OBSERVATION_SIZE:
            raise RuntimeError("scalar observation size drifted")
        return np.asarray(values, dtype=np.float32)

    def _critic_observation(self) -> np.ndarray:
        task = self.task
        sentry = self.sentry
        outpost_distance = math.hypot(BLUE_OUTPOST[0] - sentry.x, BLUE_OUTPOST[1] - sentry.y)
        base_distance = math.hypot(BLUE_BASE[0] - sentry.x, BLUE_BASE[1] - sentry.y)
        diagonal = math.hypot(self.field.arena.width, self.field.arena.height)
        values = (
            task.remaining_time / self.config.episode_seconds,
            sentry.x / self.field.arena.width,
            sentry.y / self.field.arena.height,
            math.sin(sentry.spin_angle),
            math.cos(sentry.spin_angle),
            math.sin(sentry.turret_angle),
            math.cos(sentry.turret_angle),
            task.sentry_hp / max(1.0, task.robot_max_hp(8, team="red")),
            task.robot_ammunition(8, team="red") / max(1, task.robot_ammunition_limit(8)),
            task.robot_heat_value(8, team="red", sentry=sentry)
            / max(1, task.robot_q2_limit(8, team="red") or 1),
            task.sentry_buffer_energy / BUFFER_ENERGY_CAP,
            min(1.0, task.sentry_chassis_power_cut_remaining / 5.0),
            float(task.active_posture == 1),
            float(task.active_posture == 2),
            float(task.active_posture == 3),
            float(task.posture_reinforced),
            float(task.enemy_outpost_hp) / 1500.0,
            float(task.enemy_base_hp) / 5000.0,
            float(task.enemy_base_shield) / 150.0,
            outpost_distance / diagonal,
            base_distance / diagonal,
            self._lowest_outpost_hp / 1500.0,
            self._lowest_base_durability / 5150.0,
            float(self._outpost_bonus_paid),
            float(self._base_bonus_paid),
        )
        if len(values) != CRITIC_OBSERVATION_SIZE:
            raise RuntimeError("critic observation size drifted")
        return np.asarray(values, dtype=np.float32)

    def _observation(self, *, recurrent_reset: bool = False) -> AssaultObservation:
        return AssaultObservation(
            scalar=self._scalar_observation(),
            spatial=self.local_map.encode(
                self.sentry.x,
                self.sentry.y,
                self.sentry.spin_angle,
                outpost_alive=self.task.enemy_outpost_hp > 0.0,
                base_alive=self.task.enemy_base_hp > 0.0,
            ),
            critic=self._critic_observation(),
            recurrent_reset=recurrent_reset,
        )

    @staticmethod
    def _validate_action(action: SentryAction) -> None:
        if not 0 <= int(action.move_direction) < len(MOVE_DIRECTIONS):
            raise ValueError("move_direction outside valid range")
        if not 0 <= int(action.posture) < 3:
            raise ValueError("posture outside valid range")
        if int(action.reinforce) not in (0, 1) or int(action.fire) not in (0, 1):
            raise ValueError("binary action outside valid range")
        if not -1.0 <= float(action.spin_speed) <= 1.0:
            raise ValueError("spin_speed outside [-1, 1]")
        if not -1.0 <= float(action.turret_speed) <= 1.0:
            raise ValueError("turret_speed outside [-1, 1]")

    def _apply_motion(self, action: SentryAction) -> tuple[float, bool]:
        previous_stuck_seconds = self._stuck_seconds
        move_x, move_y = MOVE_DIRECTIONS[int(action.move_direction)]
        if self.task.sentry_chassis_power_cut_remaining > 0.0 or self.task.sentry_hp <= 0.0:
            move_x = move_y = 0.0
        self.sentry.spin_speed = float(action.spin_speed) * self.config.maximum_spin_speed
        self.sentry.turret_speed = float(action.turret_speed) * self.config.maximum_turret_speed
        self.sentry.update(
            self.config.time_step,
            move_x,
            move_y,
            self.field.arena,
            spin_enabled=abs(self.sentry.spin_speed) > 1e-6,
            spin_speed_scale=1.0,
            turret_enabled=abs(self.sentry.turret_speed) > 1e-6,
            chassis_move_x=move_x,
            chassis_move_y=move_y,
        )
        start = (self.sentry.x, self.sentry.y)
        distance = (
            self.config.movement_speed
            * self.config.time_step
            * self.field.terrain_speed_multiplier(*start)
        )
        requested = self.field.arena.clamp(
            start[0] + move_x * distance,
            start[1] + move_y * distance,
        )
        requested = self.field.apply_fly_slope_one_way(start, requested)
        resolved = self.field.collision_grid.move_with_collision(
            start,
            requested,
            moving_radius=ROBOT_ENTITY_COLLISION_RADIUS,
        )
        self.sentry.x, self.sentry.y = resolved
        actual = math.hypot(resolved[0] - start[0], resolved[1] - start[1])
        expected = math.hypot(requested[0] - start[0], requested[1] - start[1])
        collision = expected > 1e-6 and actual < expected * 0.5
        self._stuck_seconds = (
            self._stuck_seconds + self.config.time_step if collision else 0.0
        )
        self._escaped_stuck = (
            previous_stuck_seconds >= self.config.stuck_penalty_after_seconds
            and not collision
            and actual > 0.05
        )
        self._last_collision = collision
        return actual, collision

    def _apply_posture(self, action: SentryAction) -> DecisionView:
        desired_posture = int(action.posture) + 1
        desired_reinforced = bool(action.reinforce)
        if desired_reinforced != self.task.posture_reinforced:
            self.task.toggle_posture_reinforced(self.sentry)
        return DecisionView(
            behavior="RL direct control",
            posture=desired_posture,
            goal=None,
            spin_mode=0,
            tripod_mode=0,
            shoot_mode=0,
            target=0,
            confirm_respawn=1,
            health_threshold=self.task.health_threshold,
        )

    def _fire(self, action: SentryAction) -> FireResult | None:
        if not action.fire:
            return None
        target_id = 6 if self.task.enemy_outpost_hp > 0.0 else 7
        result = self.task.execute_robot_fire(
            8,
            self.sentry.turret_angle,
            shots=1,
            team="red",
            sentry=self.sentry,
            preferred_target=target_id,
            attack_buff=self.task.effective_attack_buff,
        )
        if self.config.unlimited_ammunition and result.fired_shots > 0:
            self.task.ammo = min(
                AMMO_CAP,
                self.task.ammo + result.fired_shots,
            )
        return result

    def step(self, action: SentryAction) -> AssaultStep:
        if self.task.enemy_base_hp <= 0.0 or self.task.remaining_time <= 0.0:
            raise RuntimeError("step called after episode end; reset first")
        self._validate_action(action)
        outpost_before = float(self.task.enemy_outpost_hp)
        base_before = self._base_durability()
        movement_distance, _ = self._apply_motion(action)
        decision = self._apply_posture(action)
        fire_target_id, fire_target = self._active_target()
        fire_distance, fire_angle_error = self._target_metrics(fire_target)
        fire_visible = (
            fire_distance <= DETECTION_RANGE
            and fire_angle_error <= ROBOT_VISION_HALF_ANGLE
        )
        fire_in_range = fire_distance <= WEAPON_RANGE
        reward_remaining_time = max(
            0.0, self.task.remaining_time - self.config.time_step
        )
        permanent_lock_before = self.task.sentry_heat_permanent_lock
        fire_result = self._fire(action)
        permanent_lock_triggered = (
            not permanent_lock_before and self.task.sentry_heat_permanent_lock
        )
        self.task.update(
            self.config.time_step,
            self.sentry,
            decision_override=decision,
            fire_request=False,
        )
        self._step_index += 1

        outpost_after = float(self.task.enemy_outpost_hp)
        base_after = self._base_durability()
        new_outpost_low = min(self._lowest_outpost_hp, outpost_after)
        new_base_low = min(self._lowest_base_durability, base_after)
        outpost_damage_hp = self._lowest_outpost_hp - new_outpost_low
        base_damage_hp = self._lowest_base_durability - new_base_low
        efficiency_reward = (
            self.config.reward_v2
            if self.config.reward_version == 2
            else self.config.reward_v3
            if self.config.reward_version == 3
            else None
        )
        damage_scale = (
            efficiency_reward.structure_damage_scale
            if efficiency_reward is not None
            else self.config.structure_damage_scale
        )
        outpost_damage_reward = outpost_damage_hp * damage_scale
        base_damage_reward = base_damage_hp * damage_scale
        self._lowest_outpost_hp = new_outpost_low
        self._lowest_base_durability = new_base_low

        outpost_time_reward = 0.0
        outpost_destroy_reward = 0.0
        if (
            not self._outpost_bonus_paid
            and outpost_before > 0.0
            and outpost_after <= 0.0
        ):
            self._outpost_bonus_paid = True
            outpost_destroy_reward = (
                0.0
                if efficiency_reward is not None
                else self.config.outpost_destroy_bonus
            )
            outpost_time_reward = (
                reward_remaining_time
                * (
                    efficiency_reward.outpost_time_multiplier
                    if efficiency_reward is not None
                    else self.config.outpost_time_multiplier
                )
            )
        base_time_reward = 0.0
        base_destroy_reward = 0.0
        if not self._base_bonus_paid and base_before > 0.0 and base_after <= 0.0:
            self._base_bonus_paid = True
            base_destroy_reward = (
                0.0
                if efficiency_reward is not None
                else self.config.base_destroy_bonus
            )
            base_time_reward = (
                reward_remaining_time
                * (
                    efficiency_reward.base_time_multiplier
                    if efficiency_reward is not None
                    else self.config.base_time_multiplier
                )
            )
        first_hit_reward = 0.0
        if (
            fire_result is not None
            and fire_result.damage > 0
            and fire_target_id not in self._hit_targets_paid
        ):
            self._hit_targets_paid.add(fire_target_id)
            if self.config.reward_version == 3:
                multiplier = (
                    self.config.reward_v3.outpost_first_hit_time_multiplier
                    if fire_target_id == 6
                    else self.config.reward_v3.base_first_hit_time_multiplier
                )
                first_hit_reward = reward_remaining_time * multiplier
            else:
                first_hit_reward = (
                    0.0
                    if self.config.reward_version == 2
                    else self.config.first_hit_bonus
                )
        objective_reward = (
            outpost_damage_reward
            + base_damage_reward
            + first_hit_reward
            + outpost_destroy_reward
            + base_destroy_reward
            + outpost_time_reward
            + base_time_reward
        )
        fire_fired = fire_result is not None and fire_result.fired
        valid_fire = (
            fire_result is not None
            and fire_result.fired
            and fire_result.shot is not None
        )
        shaping_reward, shaping_components = self._shaping_reward(
            fire_requested=bool(action.fire),
            fire_fired=fire_fired,
            fire_visible=fire_visible,
            fire_in_range=fire_in_range,
            valid_fire=valid_fire,
            fire_target_id=fire_target_id,
            permanent_lock_triggered=permanent_lock_triggered,
            movement_distance=movement_distance,
            damage_hp=outpost_damage_hp + base_damage_hp,
        )
        raw_reward = objective_reward + shaping_reward
        terminated = base_after <= 0.0
        truncated = self.task.remaining_time <= 0.0 and not terminated
        reported_remaining_time = (
            reward_remaining_time if terminated else self.task.remaining_time
        )
        observation = self._observation(recurrent_reset=False)
        self._last_observation = observation
        info = {
            "step_index": self._step_index,
            "remaining_time": reported_remaining_time,
            "simulation_remaining_time": self.task.remaining_time,
            "outpost_hp": outpost_after,
            "base_hp": self.task.enemy_base_hp,
            "base_shield": self.task.enemy_base_shield,
            "outpost_damage_score": outpost_damage_reward,
            "base_damage_score": base_damage_reward,
            "first_hit_score": first_hit_reward,
            "outpost_destroy_score": outpost_destroy_reward,
            "base_destroy_score": base_destroy_reward,
            "outpost_time_score": outpost_time_reward,
            "base_time_score": base_time_reward,
            "objective_score": objective_reward,
            "shaping_score": shaping_reward,
            **shaping_components,
            "raw_score": raw_reward,
            "fire_result": fire_result,
        }
        return AssaultStep(
            observation=observation,
            reward=raw_reward * self.config.reward_scale,
            raw_reward=raw_reward,
            terminated=terminated,
            truncated=truncated,
            info=info,
        )

    def replay_state(self) -> dict[str, object]:
        return {
            "schema": "single-sentry-assault-v1",
            "step_index": self._step_index,
            "remaining_time": self.task.remaining_time,
            "sentry": {
                "x": self.sentry.x,
                "y": self.sentry.y,
                "chassis_angle": self.sentry.spin_angle,
                "turret_angle": self.sentry.turret_angle,
                "spin_speed": self.sentry.spin_speed,
                "turret_speed": self.sentry.turret_speed,
                "hp": self.task.sentry_hp,
                "ammo": self.task.robot_ammunition(8, team="red"),
                "heat": self.task.robot_heat_value(8, team="red", sentry=self.sentry),
                "posture": self.task.active_posture,
                "reinforced": self.task.posture_reinforced,
            },
            "structures": {
                "outpost_hp": self.task.enemy_outpost_hp,
                "base_hp": self.task.enemy_base_hp,
                "base_shield": self.task.enemy_base_shield,
            },
        }


__all__ = [
    "AssaultObservation",
    "AssaultStep",
    "CRITIC_OBSERVATION_SIZE",
    "SCALAR_OBSERVATION_SIZE",
    "SentryAction",
    "SentryAssaultEnv",
]
