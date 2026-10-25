"""Tensor-native batched assault simulator for high-throughput CUDA training.

This module implements only the single-sentry assault task used by RL.  It
does not execute Pygame, the behavior tree, navigation, or the complete match
controller.  Its movement, collision, posture, heat, firing, structure damage,
observations, and rewards mirror :mod:`rl.envs.sentry_assault.cpu_env`.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import random

import numpy as np
import torch
from torch import Tensor

from rm2026_sim.core import (
    GAZEBO_GRAVITY,
    GAZEBO_LINEAR_GAINS,
    GAZEBO_LINEAR_INTEGRAL_LIMIT,
    GAZEBO_MAX_ANGULAR_SPEED,
    GAZEBO_MAX_FORCE,
    GAZEBO_MAX_LINEAR_SPEED,
    GAZEBO_MAX_TORQUE,
    GAZEBO_POWER_STEP,
    GAZEBO_SENTRY_MASS,
    GAZEBO_SENTRY_YAW_INERTIA,
    GAZEBO_SUPPORT_FRICTION,
    GAZEBO_WHEEL_ARM,
    GAZEBO_YAW_GAINS,
    GAZEBO_YAW_INTEGRAL_LIMIT,
)
from rm2026_sim.field_geometry import BLUE_BASE, BLUE_OUTPOST, RED_HOME
from rm2026_sim.task_state import (
    BUFFER_ENERGY_CAP,
    CHASSIS_POWER_CUT_SECONDS,
    DETECTION_RANGE,
    FIRE_ALIGNMENT_TOLERANCE,
    POSTURE_DECAY_SECONDS,
    POSTURE_REINFORCED_SECONDS,
    POSTURE_SWITCH_COOLDOWN,
    ROBOT_VISION_HALF_ANGLE,
    RULE_BASE_HP,
    RULE_BASE_SHIELD,
    RULE_DAMAGE_17MM,
    RULE_OUTPOST_HP,
    WEAPON_RANGE,
)

from rl.config import AssaultConfig
from .field import AssaultField
from .local_map import LOCAL_MAP_CHANNELS
from .cpu_env import (
    CRITIC_OBSERVATION_SIZE,
    MOVE_DIRECTIONS,
    SCALAR_OBSERVATION_SIZE,
)


def _normalize_angle(value: Tensor) -> Tensor:
    return torch.remainder(value + math.pi, math.tau) - math.pi


@dataclass(frozen=True, slots=True)
class TensorAssaultObservation:
    scalar: Tensor
    spatial: Tensor
    critic: Tensor
    recurrent_reset: Tensor


@dataclass(frozen=True, slots=True)
class TensorSentryAction:
    move_direction: Tensor
    posture: Tensor
    reinforce: Tensor
    fire: Tensor
    spin_speed: Tensor
    turret_speed: Tensor


@dataclass(frozen=True, slots=True)
class TensorAssaultStep:
    observation: TensorAssaultObservation
    reward: Tensor
    raw_reward: Tensor
    terminated: Tensor
    truncated: Tensor
    objective_score: Tensor
    shaping_score: Tensor
    remaining_time: Tensor
    hit: Tensor
    valid_fire: Tensor
    permanent_lock_triggered: Tensor
    outpost_destroyed: Tensor
    base_destroyed: Tensor
    curriculum_mode: Tensor


class GpuSentryAssaultEnv:
    """Many independent assault worlds stored and advanced on one device."""

    scalar_size = SCALAR_OBSERVATION_SIZE
    critic_size = CRITIC_OBSERVATION_SIZE

    def __init__(
        self,
        num_envs: int,
        config: AssaultConfig | None = None,
        *,
        device: torch.device | str = "cuda",
    ) -> None:
        if num_envs <= 0:
            raise ValueError("num_envs must be positive")
        self.num_envs = int(num_envs)
        self.config = config or AssaultConfig()
        self.device = torch.device(device)
        self.field = AssaultField.load()
        self.spatial_shape = (
            LOCAL_MAP_CHANNELS,
            self.config.local_map_cells,
            self.config.local_map_cells,
        )
        grid = self.field.collision_grid
        self.grid_width = grid.width
        self.grid_height = grid.height
        self.map_resolution = float(grid.arena.map_resolution)
        self.arena_width = float(grid.arena.width)
        self.arena_height = float(grid.arena.height)
        self.collision_radius = float(grid.collision_radius)
        blocked = np.frombuffer(grid.blocked, dtype=np.uint8).copy().reshape(
            grid.height, grid.width
        )
        self.blocked = torch.as_tensor(
            blocked, dtype=torch.bool, device=self.device
        )
        self.move_directions = torch.tensor(
            MOVE_DIRECTIONS, dtype=torch.float32, device=self.device
        )
        self.outpost_position = torch.tensor(
            BLUE_OUTPOST, dtype=torch.float32, device=self.device
        )
        self.base_position = torch.tensor(
            BLUE_BASE, dtype=torch.float32, device=self.device
        )
        self.home_position = torch.tensor(
            RED_HOME, dtype=torch.float32, device=self.device
        )
        self.diagonal = math.hypot(self.arena_width, self.arena_height)
        self.hit_rolls = torch.tensor(
            [random.Random(2026 + counter).random() for counter in range(1, 4201)],
            dtype=torch.float32,
            device=self.device,
        )
        self._build_local_map_constants()
        self._allocate_state()
        self.reset()

    def _build_local_map_constants(self) -> None:
        cells = self.config.local_map_cells
        half = cells // 2
        offsets = (
            torch.arange(cells, dtype=torch.float32, device=self.device) - half
        ) * self.config.local_map_resolution
        self.local_x_offsets = offsets.view(1, 1, cells)
        self.local_y_offsets = (-offsets).view(1, cells, 1)
        radius = max(
            1,
            round(
                cells
                * self.config.local_map_resolution
                / self.map_resolution
                / 2.0
            ),
        )
        offsets_cpu = [
            (row, column)
            for row in range(-radius, radius + 1)
            for column in range(-radius, radius + 1)
            if row * row + column * column <= radius * radius
        ]
        self.explore_offsets = torch.tensor(
            offsets_cpu, dtype=torch.long, device=self.device
        )
        self.local_half = half
        self.direction_length = max(1, cells // 10)

    def _allocate_state(self) -> None:
        n = self.num_envs
        d = self.device
        zeros = lambda: torch.zeros(n, dtype=torch.float32, device=d)
        self.remaining_time = zeros()
        self.x = zeros()
        self.y = zeros()
        self.spin_angle = zeros()
        self.turret_angle = zeros()
        self.spin_speed = zeros()
        self.turret_speed = zeros()
        self.sentry_hp = zeros()
        self.ammo = zeros()
        self.heat = zeros()
        self.heat_locked = torch.zeros(n, dtype=torch.bool, device=d)
        self.heat_permanent = torch.zeros(n, dtype=torch.bool, device=d)
        self.chassis_power = zeros()
        self.velocity_x = zeros()
        self.velocity_y = zeros()
        self.yaw_rate = zeros()
        self.integral_x = zeros()
        self.integral_y = zeros()
        self.integral_yaw = zeros()
        self.previous_error_x = zeros()
        self.previous_error_y = zeros()
        self.previous_error_yaw = zeros()
        self.pid_has_previous = torch.zeros(n, dtype=torch.bool, device=d)
        self.buffer_energy = zeros()
        self.power_cut = zeros()
        self.active_posture = torch.zeros(n, dtype=torch.long, device=d)
        self.posture_cooldown = zeros()
        self.posture_time = torch.zeros(n, 3, dtype=torch.float32, device=d)
        self.reinforced_time = torch.zeros(n, 3, dtype=torch.float32, device=d)
        self.posture_reinforced = torch.zeros(n, dtype=torch.bool, device=d)
        self.outpost_hp = zeros()
        self.base_hp = zeros()
        self.base_shield = zeros()
        self.lowest_outpost_hp = zeros()
        self.lowest_base_durability = zeros()
        self.outpost_bonus_paid = torch.zeros(n, dtype=torch.bool, device=d)
        self.base_bonus_paid = torch.zeros(n, dtype=torch.bool, device=d)
        self.shaping_target = torch.zeros(n, dtype=torch.long, device=d)
        self.best_target_distance = zeros()
        self.best_target_angle_error = zeros()
        self.aim_tracking_active = torch.zeros(n, dtype=torch.bool, device=d)
        self.distance_milestones_paid = torch.zeros(
            n, 3, dtype=torch.bool, device=d
        )
        self.aim_milestones_paid = torch.zeros(n, 4, dtype=torch.bool, device=d)
        self.first_fire_command_paid = torch.zeros(n, dtype=torch.bool, device=d)
        self.sensor_fire_bonus_paid = torch.zeros(n, dtype=torch.bool, device=d)
        self.range_fire_guidance_paid = torch.zeros(n, dtype=torch.bool, device=d)
        self.valid_solution_bonus_paid = torch.zeros(
            n, dtype=torch.bool, device=d
        )
        self.hit_targets_paid = torch.zeros(n, 2, dtype=torch.bool, device=d)
        self.range_bonus_paid = torch.zeros(n, dtype=torch.bool, device=d)
        self.vision_bonus_paid = torch.zeros(n, dtype=torch.bool, device=d)
        self.reward_grid_width = math.ceil(
            self.arena_width / self.config.exploration_cell_size
        )
        self.reward_grid_height = math.ceil(
            self.arena_height / self.config.exploration_cell_size
        )
        self.reward_visited = torch.zeros(
            n,
            self.reward_grid_height,
            self.reward_grid_width,
            dtype=torch.bool,
            device=d,
        )
        self.exploration_reward_total = zeros()
        self.distance_reward_thresholds = torch.tensor(
            (12.0, 8.0, DETECTION_RANGE),
            dtype=torch.float32,
            device=d,
        )
        self.distance_reward_bonuses = torch.tensor(
            (
                self.config.distance_12m_bonus,
                self.config.distance_8m_bonus,
                self.config.distance_sensor_bonus,
            ),
            dtype=torch.float32,
            device=d,
        )
        self.aim_reward_thresholds = torch.tensor(
            (
                math.radians(30.0),
                math.radians(15.0),
                math.radians(8.0),
                FIRE_ALIGNMENT_TOLERANCE,
            ),
            dtype=torch.float32,
            device=d,
        )
        self.aim_reward_bonuses = torch.tensor(
            (
                self.config.aim_30deg_bonus,
                self.config.aim_15deg_bonus,
                self.config.aim_8deg_bonus,
                self.config.aim_4deg_bonus,
            ),
            dtype=torch.float32,
            device=d,
        )
        self.last_collision = torch.zeros(n, dtype=torch.bool, device=d)
        self.stuck_seconds = zeros()
        self.escaped_stuck = torch.zeros(n, dtype=torch.bool, device=d)
        self.step_index = torch.zeros(n, dtype=torch.long, device=d)
        self.hit_counter = torch.zeros(n, dtype=torch.long, device=d)
        self.explored = torch.zeros(
            n, self.grid_height, self.grid_width, dtype=torch.bool, device=d
        )
        self.curriculum_mode = torch.zeros(n, dtype=torch.long, device=d)
        self.curriculum_progress = 0.0

    def _assign(self, target: Tensor, value: float | int | bool, mask: Tensor) -> None:
        target[mask] = value

    def set_curriculum_progress(self, progress: float) -> None:
        maximum = (
            self.config.curriculum_max_progress
            if self.config.curriculum_enabled
            else 1.0
        )
        self.curriculum_progress = min(maximum, max(0.0, float(progress)))

    def _sample_free_positions(
        self,
        mask: Tensor,
        *,
        center: Tensor | None = None,
        minimum_radius: float = 0.0,
        maximum_radius: float = 0.0,
    ) -> None:
        unresolved = mask.clone()
        for _ in range(16):
            if not bool(unresolved.any().item()):
                break
            if center is None:
                candidate_x = self.collision_radius + torch.rand(
                    self.num_envs, device=self.device
                ) * (self.arena_width - 2.0 * self.collision_radius)
                candidate_y = self.collision_radius + torch.rand(
                    self.num_envs, device=self.device
                ) * (self.arena_height - 2.0 * self.collision_radius)
            else:
                angle = torch.rand(self.num_envs, device=self.device) * math.tau
                radius = minimum_radius + torch.rand(
                    self.num_envs, device=self.device
                ) * (maximum_radius - minimum_radius)
                candidate_x = center[0] + torch.cos(angle) * radius
                candidate_y = center[1] + torch.sin(angle) * radius
            accepted = unresolved & self._world_is_free(candidate_x, candidate_y)
            self.x[accepted] = candidate_x[accepted]
            self.y[accepted] = candidate_y[accepted]
            unresolved &= ~accepted

    def _apply_curriculum_reset(self, mask: Tensor) -> None:
        self.curriculum_mode[mask] = 0
        if not self.config.curriculum_enabled:
            return
        bootstrap = 1.0 - self.curriculum_progress
        near_outpost_probability = 0.35 * bootstrap
        random_field_probability = 0.30 * bootstrap
        near_base_probability = 0.25 * bootstrap
        sample = torch.rand(self.num_envs, device=self.device)
        selected_mode = torch.zeros(
            self.num_envs, dtype=torch.long, device=self.device
        )
        selected_mode[sample < near_outpost_probability] = 1
        selected_mode[
            (sample >= near_outpost_probability)
            & (sample < near_outpost_probability + random_field_probability)
        ] = 2
        selected_mode[
            (sample >= near_outpost_probability + random_field_probability)
            & (
                sample
                < near_outpost_probability
                + random_field_probability
                + near_base_probability
            )
        ] = 3
        self.curriculum_mode[mask] = selected_mode[mask]
        near_outpost = mask & (self.curriculum_mode == 1)
        random_field = mask & (self.curriculum_mode == 2)
        near_base = mask & (self.curriculum_mode == 3)
        self._sample_free_positions(
            near_outpost,
            center=self.outpost_position,
            minimum_radius=2.0,
            maximum_radius=3.7,
        )
        near_home_random = random_field & (
            torch.rand(self.num_envs, device=self.device) < 0.5
        )
        uniform_random = random_field & ~near_home_random
        self._sample_free_positions(uniform_random)
        self._sample_free_positions(
            near_home_random,
            center=self.home_position,
            minimum_radius=0.5,
            maximum_radius=6.0,
        )
        self._sample_free_positions(
            near_base,
            center=self.base_position,
            minimum_radius=2.0,
            maximum_radius=3.7,
        )
        non_home = mask & (self.curriculum_mode != 0)
        random_angle = (
            torch.rand(self.num_envs, device=self.device) * math.tau - math.pi
        )
        self.spin_angle[non_home] = random_angle[non_home]
        self.turret_angle[non_home] = random_angle[non_home]
        self.outpost_hp[near_base] = 0.0
        self.lowest_outpost_hp[near_base] = 0.0
        self.outpost_bonus_paid[near_base] = True

    def reset(self, mask: Tensor | None = None) -> TensorAssaultObservation:
        if mask is None:
            mask = torch.ones(self.num_envs, dtype=torch.bool, device=self.device)
        else:
            mask = mask.to(device=self.device, dtype=torch.bool)
        self._assign(self.remaining_time, self.config.episode_seconds, mask)
        self._assign(self.x, RED_HOME[0], mask)
        self._assign(self.y, RED_HOME[1], mask)
        for value in (
            self.spin_angle,
            self.turret_angle,
            self.heat,
            self.chassis_power,
            self.velocity_x,
            self.velocity_y,
            self.yaw_rate,
            self.integral_x,
            self.integral_y,
            self.integral_yaw,
            self.previous_error_x,
            self.previous_error_y,
            self.previous_error_yaw,
            self.power_cut,
            self.posture_cooldown,
            self.stuck_seconds,
        ):
            self._assign(value, 0.0, mask)
        self._assign(self.sentry_hp, 400.0, mask)
        self._assign(self.spin_speed, math.radians(150.0), mask)
        self._assign(self.turret_speed, math.radians(210.0), mask)
        self._assign(self.ammo, float(self.config.initial_ammunition), mask)
        self._assign(self.buffer_energy, BUFFER_ENERGY_CAP, mask)
        self._assign(self.active_posture, 3, mask)
        self.posture_time[mask] = 0.0
        self.reinforced_time[mask] = 0.0
        for value in (
            self.heat_locked,
            self.heat_permanent,
            self.pid_has_previous,
            self.posture_reinforced,
            self.outpost_bonus_paid,
            self.base_bonus_paid,
            self.aim_tracking_active,
            self.first_fire_command_paid,
            self.sensor_fire_bonus_paid,
            self.range_fire_guidance_paid,
            self.valid_solution_bonus_paid,
            self.range_bonus_paid,
            self.vision_bonus_paid,
            self.last_collision,
            self.escaped_stuck,
        ):
            self._assign(value, False, mask)
        self._assign(self.outpost_hp, float(RULE_OUTPOST_HP), mask)
        self._assign(self.base_hp, float(RULE_BASE_HP), mask)
        self._assign(self.base_shield, float(RULE_BASE_SHIELD), mask)
        self._assign(self.lowest_outpost_hp, float(RULE_OUTPOST_HP), mask)
        self._assign(
            self.lowest_base_durability,
            float(RULE_BASE_HP + RULE_BASE_SHIELD),
            mask,
        )
        self._apply_curriculum_reset(mask)
        target_id, target_x, target_y = self._active_target()
        distance = torch.hypot(target_x - self.x, target_y - self.y)
        angle = torch.abs(
            _normalize_angle(
                torch.atan2(target_y - self.y, target_x - self.x)
                - self.turret_angle
            )
        )
        self.shaping_target[mask] = target_id[mask]
        self.best_target_distance[mask] = distance[mask]
        self.best_target_angle_error[mask] = angle[mask]
        self.distance_milestones_paid[mask] = False
        self.aim_milestones_paid[mask] = False
        self.hit_targets_paid[mask] = False
        self.reward_visited[mask] = False
        self._assign(self.exploration_reward_total, 0.0, mask)
        reward_column = torch.clamp(
            (self.x / self.config.exploration_cell_size).to(torch.long),
            0,
            self.reward_grid_width - 1,
        )
        reward_row = torch.clamp(
            (self.y / self.config.exploration_cell_size).to(torch.long),
            0,
            self.reward_grid_height - 1,
        )
        reset_envs = torch.nonzero(mask, as_tuple=False).squeeze(1)
        self.reward_visited[reset_envs, reward_row[mask], reward_column[mask]] = True
        self._assign(self.step_index, 0, mask)
        self._assign(self.hit_counter, 0, mask)
        self.explored[mask] = False
        return self._observation(recurrent_reset=mask)

    def _target_metrics(self, target: Tensor) -> tuple[Tensor, Tensor]:
        delta_x = target[0] - self.x
        delta_y = target[1] - self.y
        distance = torch.hypot(delta_x, delta_y)
        angle = torch.abs(_normalize_angle(torch.atan2(delta_y, delta_x) - self.turret_angle))
        return distance, angle

    def _active_target(self) -> tuple[Tensor, Tensor, Tensor]:
        outpost_alive = self.outpost_hp > 0.0
        target_x = torch.where(outpost_alive, self.outpost_position[0], self.base_position[0])
        target_y = torch.where(outpost_alive, self.outpost_position[1], self.base_position[1])
        target_id = torch.where(
            outpost_alive,
            torch.full_like(self.shaping_target, 6),
            torch.full_like(self.shaping_target, 7),
        )
        return target_id, target_x, target_y

    def _pid_step(
        self,
        error: Tensor,
        previous: Tensor,
        integral: Tensor,
        gains: tuple[float, float, float],
        integral_limit: float,
        output_limit: float,
        step: float,
    ) -> tuple[Tensor, Tensor]:
        p, i, d = gains
        rate = torch.where(
            self.pid_has_previous,
            (error - previous) / step,
            torch.zeros_like(error),
        )
        candidate_integral = torch.clamp(
            integral + error * step, -integral_limit, integral_limit
        )
        candidate_output = p * error + i * candidate_integral + d * rate
        accept = (
            (torch.abs(candidate_output) <= output_limit)
            | ((candidate_output > output_limit) & (error < 0.0))
            | ((candidate_output < -output_limit) & (error > 0.0))
        )
        integral = torch.where(accept, candidate_integral, integral)
        output = torch.clamp(p * error + i * integral + d * rate, -output_limit, output_limit)
        return output, integral

    def _reset_chassis_dynamics(self, mask: Tensor) -> None:
        for value in (
            self.chassis_power,
            self.velocity_x,
            self.velocity_y,
            self.yaw_rate,
            self.integral_x,
            self.integral_y,
            self.integral_yaw,
            self.previous_error_x,
            self.previous_error_y,
            self.previous_error_yaw,
        ):
            value[mask] = 0.0
        self.pid_has_previous[mask] = False

    def _update_chassis_power(
        self, command_x: Tensor, command_y: Tensor, command_yaw: Tensor
    ) -> None:
        target_x = torch.clamp(command_x, -GAZEBO_MAX_LINEAR_SPEED, GAZEBO_MAX_LINEAR_SPEED)
        target_y = torch.clamp(command_y, -GAZEBO_MAX_LINEAR_SPEED, GAZEBO_MAX_LINEAR_SPEED)
        target_yaw = torch.clamp(command_yaw, -GAZEBO_MAX_ANGULAR_SPEED, GAZEBO_MAX_ANGULAR_SPEED)
        remaining = self.config.time_step
        mechanical_energy = torch.zeros_like(self.x)
        while remaining > 1e-9:
            step = min(GAZEBO_POWER_STEP, remaining)
            error_x = target_x - self.velocity_x
            error_y = target_y - self.velocity_y
            error_yaw = target_yaw - self.yaw_rate
            force_x, self.integral_x = self._pid_step(
                error_x,
                self.previous_error_x,
                self.integral_x,
                GAZEBO_LINEAR_GAINS,
                GAZEBO_LINEAR_INTEGRAL_LIMIT,
                GAZEBO_MAX_FORCE,
                step,
            )
            force_y, self.integral_y = self._pid_step(
                error_y,
                self.previous_error_y,
                self.integral_y,
                GAZEBO_LINEAR_GAINS,
                GAZEBO_LINEAR_INTEGRAL_LIMIT,
                GAZEBO_MAX_FORCE,
                step,
            )
            magnitude = torch.hypot(force_x, force_y)
            scale = torch.clamp(GAZEBO_MAX_FORCE / torch.clamp_min(magnitude, 1e-12), max=1.0)
            force_x = force_x * scale
            force_y = force_y * scale
            torque, self.integral_yaw = self._pid_step(
                error_yaw,
                self.previous_error_yaw,
                self.integral_yaw,
                GAZEBO_YAW_GAINS,
                GAZEBO_YAW_INTEGRAL_LIMIT,
                GAZEBO_MAX_TORQUE,
                step,
            )
            speed = torch.hypot(self.velocity_x, self.velocity_y)
            resistance = GAZEBO_SUPPORT_FRICTION * GAZEBO_SENTRY_MASS * GAZEBO_GRAVITY
            resistance_x = torch.where(
                speed > 1e-6,
                -resistance * self.velocity_x / torch.clamp_min(speed, 1e-12),
                torch.zeros_like(speed),
            )
            resistance_y = torch.where(
                speed > 1e-6,
                -resistance * self.velocity_y / torch.clamp_min(speed, 1e-12),
                torch.zeros_like(speed),
            )
            yaw_resistance = torch.where(
                torch.abs(self.yaw_rate) > 1e-6,
                -torch.sign(self.yaw_rate) * resistance * GAZEBO_WHEEL_ARM,
                torch.zeros_like(self.yaw_rate),
            )
            self.velocity_x = torch.clamp(
                self.velocity_x + (force_x + resistance_x) / GAZEBO_SENTRY_MASS * step,
                -GAZEBO_MAX_LINEAR_SPEED,
                GAZEBO_MAX_LINEAR_SPEED,
            )
            self.velocity_y = torch.clamp(
                self.velocity_y + (force_y + resistance_y) / GAZEBO_SENTRY_MASS * step,
                -GAZEBO_MAX_LINEAR_SPEED,
                GAZEBO_MAX_LINEAR_SPEED,
            )
            self.yaw_rate = torch.clamp(
                self.yaw_rate + (torque + yaw_resistance) / GAZEBO_SENTRY_YAW_INERTIA * step,
                -GAZEBO_MAX_ANGULAR_SPEED,
                GAZEBO_MAX_ANGULAR_SPEED,
            )
            mechanical_power = torch.clamp_min(
                force_x * self.velocity_x + force_y * self.velocity_y + torque * self.yaw_rate,
                0.0,
            )
            mechanical_energy = mechanical_energy + mechanical_power * step
            self.previous_error_x = error_x
            self.previous_error_y = error_y
            self.previous_error_yaw = error_yaw
            self.pid_has_previous.fill_(True)
            remaining -= step
        self.chassis_power = mechanical_energy / self.config.time_step

    def _world_is_free(self, x: Tensor, y: Tensor) -> Tensor:
        inside = (
            (x >= self.collision_radius)
            & (x <= self.arena_width - self.collision_radius)
            & (y >= self.collision_radius)
            & (y <= self.arena_height - self.collision_radius)
        )
        column = torch.clamp((x / self.map_resolution).to(torch.long), 0, self.grid_width - 1)
        row = torch.clamp(
            ((self.arena_height - y) / self.map_resolution).to(torch.long),
            0,
            self.grid_height - 1,
        )
        return inside & ~self.blocked[row, column]

    def _trace_free_motion(
        self, start_x: Tensor, start_y: Tensor, target_x: Tensor, target_y: Tensor
    ) -> tuple[Tensor, Tensor]:
        delta_x = target_x - start_x
        delta_y = target_y - start_y
        distance = torch.hypot(delta_x, delta_y)
        step_length = self.map_resolution * 0.5
        # Match ``math.ceil`` on the CPU reference's double-precision target
        # coordinates at exact map-step boundaries.
        steps = torch.clamp(
            torch.ceil(distance / step_length + 1e-4).to(torch.long), min=1
        )
        # Float32 target coordinates can place a nominal 0.30 m move one ULP
        # above the exact distance.  The CPU reference then uses one extra
        # trace sample, so reserve two guard samples here as well.
        maximum_steps = max(
            1,
            math.ceil(
                self.config.movement_speed
                * self.config.time_step
                / step_length
            )
            + 2,
        )
        indices = torch.arange(1, maximum_steps + 1, device=self.device).view(1, -1)
        active = indices <= steps.view(-1, 1)
        ratio = indices.to(torch.float32) / steps.view(-1, 1)
        candidate_x = start_x.view(-1, 1) + delta_x.view(-1, 1) * ratio
        candidate_y = start_y.view(-1, 1) + delta_y.view(-1, 1) * ratio
        free = self._world_is_free(candidate_x, candidate_y) | ~active
        blocked_prefix = torch.cumsum((~free & active).to(torch.int32), dim=1) > 0
        valid = active & ~blocked_prefix
        last_index = valid.to(torch.long).sum(dim=1) - 1
        has_valid = last_index >= 0
        gather_index = torch.clamp(last_index, min=0).view(-1, 1)
        result_x = torch.gather(candidate_x, 1, gather_index).squeeze(1)
        result_y = torch.gather(candidate_y, 1, gather_index).squeeze(1)
        return (
            torch.where(has_valid, result_x, start_x),
            torch.where(has_valid, result_y, start_y),
        )

    def _move_with_collision(
        self, start_x: Tensor, start_y: Tensor, target_x: Tensor, target_y: Tensor
    ) -> tuple[Tensor, Tensor]:
        direct_x, direct_y = self._trace_free_motion(start_x, start_y, target_x, target_y)
        reached = torch.hypot(direct_x - target_x, direct_y - target_y) <= 1e-6
        x1, y1 = self._trace_free_motion(start_x, start_y, target_x, start_y)
        x1, y1 = self._trace_free_motion(x1, y1, x1, target_y)
        x2, y2 = self._trace_free_motion(start_x, start_y, start_x, target_y)
        x2, y2 = self._trace_free_motion(x2, y2, target_x, y2)
        candidates_x = torch.stack((direct_x, x1, x2), dim=1)
        candidates_y = torch.stack((direct_y, y1, y2), dim=1)
        distances = torch.hypot(candidates_x - target_x.view(-1, 1), candidates_y - target_y.view(-1, 1))
        choice = torch.argmin(distances, dim=1, keepdim=True)
        best_x = torch.gather(candidates_x, 1, choice).squeeze(1)
        best_y = torch.gather(candidates_y, 1, choice).squeeze(1)
        return torch.where(reached, direct_x, best_x), torch.where(reached, direct_y, best_y)

    def _apply_motion(self, action: TensorSentryAction) -> None:
        direction = self.move_directions[action.move_direction.long()]
        move_x = direction[:, 0]
        move_y = direction[:, 1]
        disabled = (self.power_cut > 0.0) | (self.sentry_hp <= 0.0)
        move_x = torch.where(disabled, torch.zeros_like(move_x), move_x)
        move_y = torch.where(disabled, torch.zeros_like(move_y), move_y)
        self.spin_speed = action.spin_speed * self.config.maximum_spin_speed
        self.turret_speed = action.turret_speed * self.config.maximum_turret_speed
        self.spin_angle = _normalize_angle(
            self.spin_angle + self.spin_speed * self.config.time_step
        )
        self.turret_angle = _normalize_angle(
            self.turret_angle + self.turret_speed * self.config.time_step
        )
        self._update_chassis_power(
            move_x * self.config.movement_speed,
            move_y * self.config.movement_speed,
            self.spin_speed,
        )
        start_x = self.x
        start_y = self.y
        distance = self.config.movement_speed * self.config.time_step
        requested_x = torch.clamp(start_x + move_x * distance, 0.0, self.arena_width)
        requested_y = torch.clamp(start_y + move_y * distance, 0.0, self.arena_height)
        resolved_x, resolved_y = self._move_with_collision(
            start_x, start_y, requested_x, requested_y
        )
        actual = torch.hypot(resolved_x - start_x, resolved_y - start_y)
        expected = torch.hypot(requested_x - start_x, requested_y - start_y)
        collision = (expected > 1e-6) & (actual < expected * 0.5)
        self.x = resolved_x
        self.y = resolved_y
        previous_stuck_seconds = self.stuck_seconds
        self.stuck_seconds = torch.where(
            collision,
            self.stuck_seconds + self.config.time_step,
            torch.zeros_like(self.stuck_seconds),
        )
        self.escaped_stuck = (
            (previous_stuck_seconds >= self.config.stuck_penalty_after_seconds)
            & ~collision
            & (actual > 0.05)
        )
        self.last_collision = collision

    def _posture_mode_masks(self) -> tuple[Tensor, Tensor]:
        index = self.active_posture - 1
        active_time = torch.gather(self.posture_time, 1, index.view(-1, 1)).squeeze(1)
        active_reinforced = torch.gather(
            self.reinforced_time, 1, index.view(-1, 1)
        ).squeeze(1)
        # The CPU reference accumulates 0.1 in binary float and reaches
        # 14.999999999999... on its nominal 150th tick.  Inclusive comparison
        # preserves the same final reinforced tick in float32 batches.
        reinforced = self.posture_reinforced & (
            active_reinforced <= POSTURE_REINFORCED_SECONDS
        )
        decayed = active_time >= POSTURE_DECAY_SECONDS
        return reinforced, decayed

    def _toggle_reinforcement(self, desired: Tensor) -> None:
        desired = desired.bool()
        changed = desired != self.posture_reinforced
        index = self.active_posture - 1
        used = torch.gather(self.reinforced_time, 1, index.view(-1, 1)).squeeze(1)
        threshold_tolerance = self.config.time_step * 0.5
        allowed = changed & (
            used <= POSTURE_REINFORCED_SECONDS + threshold_tolerance
        )
        self.posture_reinforced = torch.where(
            allowed, ~self.posture_reinforced, self.posture_reinforced
        )
        clear_heat = allowed & self.posture_reinforced & (self.active_posture == 1)
        self.heat = torch.where(clear_heat, torch.zeros_like(self.heat), self.heat)
        self.heat_locked = torch.where(
            clear_heat & ~self.heat_permanent,
            torch.zeros_like(self.heat_locked),
            self.heat_locked,
        )

    def _fire(
        self, action: TensorSentryAction
    ) -> tuple[Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor]:
        requested = action.fire.bool()
        ready = requested & ~self.heat_locked & ~self.heat_permanent & (self.ammo > 0.0)
        reinforced, _ = self._posture_mode_masks()
        zero_heat = reinforced & (self.active_posture == 1)
        heat_gain = torch.where(
            zero_heat,
            torch.zeros_like(self.heat),
            torch.full_like(self.heat, 10.0),
        )
        self.heat = torch.where(ready, self.heat + heat_gain, self.heat)
        self.heat_permanent = self.heat_permanent | (ready & (self.heat >= 360.0))
        self.heat_locked = self.heat_locked | (ready & (self.heat > 260.0))
        target_id, target_x, target_y = self._active_target()
        delta_x = target_x - self.x
        delta_y = target_y - self.y
        distance = torch.hypot(delta_x, delta_y)
        angle_error = torch.abs(
            _normalize_angle(torch.atan2(delta_y, delta_x) - self.turret_angle)
        )
        aligned = (distance <= WEAPON_RANGE) & (angle_error <= FIRE_ALIGNMENT_TOLERANCE)
        resolved_shot = ready & aligned
        self.hit_counter = self.hit_counter + resolved_shot.long()
        probability = torch.where(
            target_id == 6,
            torch.full_like(distance, 0.90),
            torch.full_like(distance, 0.90),
        )
        roll_index = torch.clamp(
            self.hit_counter - 1, min=0, max=self.hit_rolls.numel() - 1
        )
        hit_roll = self.hit_rolls[roll_index]
        hit = resolved_shot & (hit_roll < probability)
        outpost_hit = hit & (target_id == 6)
        self.outpost_hp = torch.clamp_min(
            self.outpost_hp - outpost_hit.to(self.outpost_hp.dtype) * RULE_DAMAGE_17MM,
            0.0,
        )
        base_hit = hit & (target_id == 7) & (self.outpost_hp <= 0.0)
        upper_front = self.x < self.base_position[0]
        base_damage = torch.where(
            upper_front,
            torch.full_like(self.base_hp, 5.0),
            torch.full_like(self.base_hp, float(RULE_DAMAGE_17MM)),
        ) * base_hit.to(self.base_hp.dtype)
        shield_damage = torch.minimum(self.base_shield, base_damage)
        self.base_shield = self.base_shield - shield_damage
        self.base_hp = torch.clamp_min(self.base_hp - (base_damage - shield_damage), 0.0)
        visible = (distance <= DETECTION_RANGE) & (
            angle_error <= ROBOT_VISION_HALF_ANGLE
        )
        return requested, ready, visible, distance <= WEAPON_RANGE, resolved_shot, hit, target_id

    def _heat_cooling(self) -> None:
        reinforced, _ = self._posture_mode_masks()
        attack_reinforced = reinforced & (self.active_posture == 1)
        self.heat = torch.where(attack_reinforced, torch.zeros_like(self.heat), self.heat)
        self.heat_locked = torch.where(
            attack_reinforced & ~self.heat_permanent,
            torch.zeros_like(self.heat_locked),
            self.heat_locked,
        )
        cooling_multiplier = torch.where(
            self.active_posture == 1,
            torch.full_like(self.heat, 3.0),
            torch.full_like(self.heat, 1.0 / 3.0),
        )
        self.heat = torch.clamp_min(
            self.heat - 30.0 * cooling_multiplier * self.config.time_step,
            0.0,
        )
        unlock = (self.heat <= 0.0) & self.heat_locked & ~self.heat_permanent
        self.heat_locked = self.heat_locked & ~unlock

    def _effective_power_limit(self) -> Tensor:
        reinforced, decayed = self._posture_mode_masks()
        multiplier = torch.where(
            self.active_posture == 3,
            torch.where(
                reinforced,
                torch.full_like(self.x, 2.0),
                torch.where(decayed, torch.full_like(self.x, 1.2), torch.full_like(self.x, 1.5)),
            ),
            torch.full_like(self.x, 0.5),
        )
        return torch.clamp(100.0 * multiplier, max=200.0)

    def _update_power(self) -> None:
        cutting = self.power_cut > 0.0
        self.power_cut = torch.where(
            cutting,
            torch.clamp_min(self.power_cut - self.config.time_step, 0.0),
            self.power_cut,
        )
        self._reset_chassis_dynamics(cutting)
        ended = cutting & (self.power_cut <= 0.0)
        self.buffer_energy = torch.where(
            ended, torch.full_like(self.buffer_energy, BUFFER_ENERGY_CAP), self.buffer_energy
        )
        active = ~cutting
        over = self.chassis_power - self._effective_power_limit()
        draining = active & (over > 0.0)
        self.buffer_energy = torch.where(
            draining,
            torch.clamp_min(self.buffer_energy - over * self.config.time_step, 0.0),
            self.buffer_energy,
        )
        depleted = draining & (self.buffer_energy <= 0.0)
        self.power_cut = torch.where(
            depleted,
            torch.full_like(self.power_cut, CHASSIS_POWER_CUT_SECONDS),
            self.power_cut,
        )
        self._reset_chassis_dynamics(depleted)

    def _update_posture(self, desired: Tensor) -> None:
        desired = desired.long() + 1
        cooling = self.posture_cooldown > 0.0
        self.posture_cooldown = torch.where(
            cooling,
            torch.clamp_min(self.posture_cooldown - self.config.time_step, 0.0),
            self.posture_cooldown,
        )
        switch = ~cooling & (desired != self.active_posture)
        self.active_posture = torch.where(switch, desired, self.active_posture)
        self.posture_cooldown = torch.where(
            switch,
            torch.full_like(self.posture_cooldown, POSTURE_SWITCH_COOLDOWN),
            self.posture_cooldown,
        )
        self.posture_reinforced = self.posture_reinforced & ~switch
        index = self.active_posture - 1
        self.posture_time.scatter_add_(
            1,
            index.view(-1, 1),
            torch.full((self.num_envs, 1), self.config.time_step, device=self.device),
        )
        reinforcement_increment = self.posture_reinforced.to(torch.float32) * self.config.time_step
        self.reinforced_time.scatter_add_(
            1, index.view(-1, 1), reinforcement_increment.view(-1, 1)
        )
        used = torch.gather(self.reinforced_time, 1, index.view(-1, 1)).squeeze(1)
        expired = self.posture_reinforced & (
            used > POSTURE_REINFORCED_SECONDS + self.config.time_step * 0.5
        )
        self.reinforced_time.scatter_(
            1,
            index.view(-1, 1),
            torch.minimum(used, torch.full_like(used, POSTURE_REINFORCED_SECONDS)).view(-1, 1),
        )
        self.posture_reinforced = self.posture_reinforced & ~expired

    def _shaping_reward(
        self,
        *,
        fire_requested: Tensor,
        fire_fired: Tensor,
        fire_visible: Tensor,
        fire_in_range: Tensor,
        valid_fire: Tensor,
        fire_target_id: Tensor,
        permanent_lock_triggered: Tensor,
    ) -> tuple[Tensor, Tensor]:
        target_id, target_x, target_y = self._active_target()
        delta_x = target_x - self.x
        delta_y = target_y - self.y
        distance = torch.hypot(delta_x, delta_y)
        angle_error = torch.abs(
            _normalize_angle(torch.atan2(delta_y, delta_x) - self.turret_angle)
        )
        changed = target_id != self.shaping_target
        self.best_target_distance = torch.where(
            changed, distance, self.best_target_distance
        )
        self.best_target_angle_error = torch.where(
            changed, angle_error, self.best_target_angle_error
        )
        self.aim_tracking_active = self.aim_tracking_active & ~changed
        self.distance_milestones_paid[changed] = False
        self.aim_milestones_paid[changed] = False
        self.sensor_fire_bonus_paid = self.sensor_fire_bonus_paid & ~changed
        self.range_fire_guidance_paid = (
            self.range_fire_guidance_paid & ~changed
        )
        self.valid_solution_bonus_paid = (
            self.valid_solution_bonus_paid & ~changed
        )
        self.range_bonus_paid = self.range_bonus_paid & ~changed
        self.vision_bonus_paid = self.vision_bonus_paid & ~changed

        distance_improvement = torch.clamp_min(
            self.best_target_distance - distance, 0.0
        )
        distance_score = torch.where(
            changed,
            torch.zeros_like(distance),
            distance_improvement * self.config.distance_progress_scale,
        )
        self.best_target_distance = torch.minimum(
            self.best_target_distance, distance
        )

        reached_distance = (
            distance.view(-1, 1) <= self.distance_reward_thresholds
        )
        new_distance_milestones = (
            reached_distance & ~self.distance_milestones_paid & ~changed.view(-1, 1)
        )
        distance_milestone_score = (
            new_distance_milestones.to(torch.float32)
            * self.distance_reward_bonuses
        ).sum(dim=1)
        self.distance_milestones_paid |= new_distance_milestones

        first_range = ~changed & ~self.range_bonus_paid & (distance <= WEAPON_RANGE)
        range_score = first_range.to(torch.float32) * self.config.first_range_bonus
        self.range_bonus_paid = self.range_bonus_paid | first_range
        visible = (distance <= DETECTION_RANGE) & (angle_error <= ROBOT_VISION_HALF_ANGLE)
        first_vision = ~changed & ~self.vision_bonus_paid & visible
        vision_score = first_vision.to(torch.float32) * self.config.first_line_of_sight_bonus
        self.vision_bonus_paid = self.vision_bonus_paid | first_vision

        in_detection_range = distance <= DETECTION_RANGE
        eligible_aim_tracking = in_detection_range & ~changed
        start_aim_tracking = eligible_aim_tracking & ~self.aim_tracking_active
        continue_aim_tracking = eligible_aim_tracking & self.aim_tracking_active
        aim_improvement = torch.clamp_min(
            self.best_target_angle_error - angle_error, 0.0
        )
        aim_score = torch.where(
            continue_aim_tracking,
            aim_improvement * self.config.aim_progress_scale,
            torch.zeros_like(distance),
        )
        self.best_target_angle_error = torch.where(
            start_aim_tracking,
            angle_error,
            torch.where(
                continue_aim_tracking,
                torch.minimum(self.best_target_angle_error, angle_error),
                self.best_target_angle_error,
            ),
        )
        self.aim_tracking_active |= eligible_aim_tracking
        reached_aim = angle_error.view(-1, 1) <= self.aim_reward_thresholds
        new_aim_milestones = (
            reached_aim
            & ~self.aim_milestones_paid
            & in_detection_range.view(-1, 1)
            & ~changed.view(-1, 1)
        )
        aim_milestone_score = (
            new_aim_milestones.to(torch.float32) * self.aim_reward_bonuses
        ).sum(dim=1)
        self.aim_milestones_paid |= new_aim_milestones

        first_fire_command = (
            fire_requested & fire_visible & ~self.first_fire_command_paid
        )
        first_fire_command_score = (
            first_fire_command.to(torch.float32)
            * self.config.first_fire_command_bonus
        )
        self.first_fire_command_paid |= first_fire_command
        fire_matches_target = fire_target_id == target_id
        first_sensor_fire = (
            fire_fired
            & fire_visible
            & fire_matches_target
            & ~self.sensor_fire_bonus_paid
            & ~changed
        )
        sensor_fire_score = (
            first_sensor_fire.to(torch.float32)
            * self.config.first_sensor_fire_bonus
        )
        self.sensor_fire_bonus_paid |= first_sensor_fire
        first_range_fire = (
            fire_fired
            & fire_in_range
            & fire_matches_target
            & ~self.range_fire_guidance_paid
            & ~changed
        )
        range_fire_guidance_score = (
            first_range_fire.to(torch.float32)
            * self.config.first_range_fire_bonus
        )
        self.range_fire_guidance_paid |= first_range_fire
        valid_solution = valid_fire & fire_matches_target & ~changed
        first_valid_solution = (
            valid_solution & ~self.valid_solution_bonus_paid & ~changed
        )
        valid_solution_score = (
            first_valid_solution.to(torch.float32)
            * self.config.valid_solution_bonus
        )
        self.valid_solution_bonus_paid |= first_valid_solution
        valid_fire_step_score = (
            valid_solution.to(torch.float32) * self.config.valid_fire_step_bonus
        )
        invalid_fire_score = -(
            (fire_requested & ~valid_fire).to(torch.float32)
            * self.config.invalid_fire_penalty
        )
        permanent_lock_score = -(
            permanent_lock_triggered.to(torch.float32)
            * self.config.permanent_heat_lock_penalty
        )

        reward_column = torch.clamp(
            (self.x / self.config.exploration_cell_size).to(torch.long),
            0,
            self.reward_grid_width - 1,
        )
        reward_row = torch.clamp(
            (self.y / self.config.exploration_cell_size).to(torch.long),
            0,
            self.reward_grid_height - 1,
        )
        env_index = torch.arange(self.num_envs, device=self.device)
        is_new_cell = ~self.reward_visited[env_index, reward_row, reward_column]
        reward_room = torch.clamp_min(
            self.config.exploration_reward_cap - self.exploration_reward_total,
            0.0,
        )
        exploration_score = torch.where(
            is_new_cell & (reward_room > 0.0),
            torch.minimum(
                torch.full_like(distance, self.config.exploration_cell_bonus),
                reward_room,
            ),
            torch.zeros_like(distance),
        )
        self.reward_visited[env_index, reward_row, reward_column] = True
        self.exploration_reward_total += exploration_score

        self.shaping_target = target_id
        collision_score = -self.last_collision.to(torch.float32) * self.config.collision_penalty
        stuck_multiplier = torch.clamp(
            self.stuck_seconds / self.config.stuck_penalty_after_seconds,
            max=3.0,
        )
        stuck_score = -self.config.stuck_penalty * stuck_multiplier
        escape_score = (
            self.escaped_stuck.to(torch.float32) * self.config.escape_stuck_bonus
        )
        time_score = torch.full_like(distance, -self.config.time_penalty_per_second * self.config.time_step)
        shaping = (
            distance_score
            + distance_milestone_score
            + aim_score
            + aim_milestone_score
            + exploration_score
            + range_score
            + vision_score
            + first_fire_command_score
            + sensor_fire_score
            + range_fire_guidance_score
            + valid_solution_score
            + valid_fire_step_score
            + invalid_fire_score
            + permanent_lock_score
            + collision_score
            + stuck_score
            + escape_score
            + time_score
        )
        return shaping, distance

    def step(self, action: TensorSentryAction) -> TensorAssaultStep:
        outpost_before = self.outpost_hp.clone()
        base_before = self.base_hp + self.base_shield
        reward_remaining = torch.clamp_min(
            self.remaining_time - self.config.time_step, 0.0
        )
        self._apply_motion(action)
        self._toggle_reinforcement(action.reinforce)
        heat_permanent_before = self.heat_permanent.clone()
        (
            fire_requested,
            fire_fired,
            fire_visible,
            fire_in_range,
            valid_fire,
            hit,
            fire_target_id,
        ) = self._fire(action)
        permanent_lock_triggered = (
            ~heat_permanent_before & self.heat_permanent
        )
        self._heat_cooling()
        self.remaining_time = torch.clamp_min(
            self.remaining_time - self.config.time_step, 0.0
        )
        self._update_power()
        self._update_posture(action.posture)
        self.step_index = self.step_index + 1
        outpost_after = self.outpost_hp
        base_after = self.base_hp + self.base_shield
        new_low_outpost = torch.minimum(self.lowest_outpost_hp, outpost_after)
        new_low_base = torch.minimum(self.lowest_base_durability, base_after)
        outpost_damage = (
            self.lowest_outpost_hp - new_low_outpost
        ) * self.config.structure_damage_scale
        base_damage = (
            self.lowest_base_durability - new_low_base
        ) * self.config.structure_damage_scale
        self.lowest_outpost_hp = new_low_outpost
        self.lowest_base_durability = new_low_base
        outpost_destroyed = (
            ~self.outpost_bonus_paid & (outpost_before > 0.0) & (outpost_after <= 0.0)
        )
        base_destroyed = (
            ~self.base_bonus_paid & (base_before > 0.0) & (base_after <= 0.0)
        )
        outpost_time = outpost_destroyed.to(torch.float32) * reward_remaining * self.config.outpost_time_multiplier
        base_time = base_destroyed.to(torch.float32) * reward_remaining * self.config.base_time_multiplier
        self.outpost_bonus_paid = self.outpost_bonus_paid | outpost_destroyed
        self.base_bonus_paid = self.base_bonus_paid | base_destroyed
        outpost_destroy_score = (
            outpost_destroyed.to(torch.float32)
            * self.config.outpost_destroy_bonus
        )
        base_destroy_score = (
            base_destroyed.to(torch.float32) * self.config.base_destroy_bonus
        )
        hit_target_index = torch.clamp(fire_target_id - 6, min=0, max=1)
        env_index = torch.arange(self.num_envs, device=self.device)
        first_hit = hit & ~self.hit_targets_paid[env_index, hit_target_index]
        first_hit_score = (
            first_hit.to(torch.float32) * self.config.first_hit_bonus
        )
        self.hit_targets_paid[env_index[first_hit], hit_target_index[first_hit]] = True
        objective = (
            outpost_damage
            + base_damage
            + first_hit_score
            + outpost_destroy_score
            + base_destroy_score
            + outpost_time
            + base_time
        )
        shaping, _ = self._shaping_reward(
            fire_requested=fire_requested,
            fire_fired=fire_fired,
            fire_visible=fire_visible,
            fire_in_range=fire_in_range,
            valid_fire=valid_fire,
            fire_target_id=fire_target_id,
            permanent_lock_triggered=permanent_lock_triggered,
        )
        raw = objective + shaping
        terminated = base_after <= 0.0
        truncated = (self.remaining_time <= 0.0) & ~terminated
        observation = self._observation(
            recurrent_reset=torch.zeros(self.num_envs, dtype=torch.bool, device=self.device)
        )
        return TensorAssaultStep(
            observation=observation,
            reward=raw * self.config.reward_scale,
            raw_reward=raw,
            terminated=terminated,
            truncated=truncated,
            objective_score=objective,
            shaping_score=shaping,
            remaining_time=torch.where(terminated, reward_remaining, self.remaining_time),
            hit=hit,
            valid_fire=valid_fire,
            permanent_lock_triggered=permanent_lock_triggered,
            outpost_destroyed=outpost_destroyed,
            base_destroyed=base_destroyed,
            curriculum_mode=self.curriculum_mode.clone(),
        )

    def _mark_explored(self) -> None:
        center_column = torch.clamp(
            (self.x / self.map_resolution).to(torch.long), 0, self.grid_width - 1
        )
        center_row = torch.clamp(
            ((self.arena_height - self.y) / self.map_resolution).to(torch.long),
            0,
            self.grid_height - 1,
        )
        rows = center_row.view(-1, 1) + self.explore_offsets[:, 0]
        columns = center_column.view(-1, 1) + self.explore_offsets[:, 1]
        valid = (
            (rows >= 0)
            & (rows < self.grid_height)
            & (columns >= 0)
            & (columns < self.grid_width)
        )
        envs = torch.arange(self.num_envs, device=self.device).view(-1, 1).expand_as(rows)
        flat = envs * (self.grid_height * self.grid_width) + rows.clamp(0, self.grid_height - 1) * self.grid_width + columns.clamp(0, self.grid_width - 1)
        self.explored.view(-1)[flat[valid]] = True

    def _local_map(self) -> Tensor:
        self._mark_explored()
        cells = self.config.local_map_cells
        world_x = self.x.view(-1, 1, 1) + self.local_x_offsets
        world_y = self.y.view(-1, 1, 1) + self.local_y_offsets
        world_x = world_x.expand(-1, cells, -1)
        world_y = world_y.expand(-1, -1, cells)
        inside_arena = (
            (world_x >= 0.0)
            & (world_x <= self.arena_width)
            & (world_y >= 0.0)
            & (world_y <= self.arena_height)
        )
        inside_collision = (
            (world_x >= self.collision_radius)
            & (world_x <= self.arena_width - self.collision_radius)
            & (world_y >= self.collision_radius)
            & (world_y <= self.arena_height - self.collision_radius)
        )
        columns = torch.clamp(
            (world_x / self.map_resolution).to(torch.long), 0, self.grid_width - 1
        )
        rows = torch.clamp(
            ((self.arena_height - world_y) / self.map_resolution).to(torch.long),
            0,
            self.grid_height - 1,
        )
        blocked = self.blocked[rows, columns]
        free = inside_arena & inside_collision & ~blocked
        env_index = torch.arange(self.num_envs, device=self.device).view(-1, 1, 1)
        explored = self.explored[env_index, rows, columns]
        result = torch.zeros(
            self.num_envs,
            LOCAL_MAP_CHANNELS,
            cells,
            cells,
            dtype=torch.float32,
            device=self.device,
        )
        result[:, 0] = (~free).to(torch.float32)
        result[:, 1] = (free & explored).to(torch.float32)
        result[:, 2] = (free & ~explored).to(torch.float32)
        envs = torch.arange(self.num_envs, device=self.device)
        for channel, position, enabled in (
            (3, self.outpost_position, self.outpost_hp > 0.0),
            (4, self.base_position, self.base_hp > 0.0),
        ):
            column = torch.round((position[0] - self.x) / self.config.local_map_resolution).long() + self.local_half
            row = self.local_half - torch.round((position[1] - self.y) / self.config.local_map_resolution).long()
            valid = enabled & (row >= 0) & (row < cells) & (column >= 0) & (column < cells)
            result[envs[valid], channel, row[valid], column[valid]] = 1.0
        result[:, 5, self.local_half, self.local_half] = 1.0
        direction_column = self.local_half + torch.round(
            torch.cos(self.spin_angle) * self.direction_length
        ).long()
        direction_row = self.local_half - torch.round(
            torch.sin(self.spin_angle) * self.direction_length
        ).long()
        valid = (
            (direction_row >= 0)
            & (direction_row < cells)
            & (direction_column >= 0)
            & (direction_column < cells)
        )
        result[envs[valid], 5, direction_row[valid], direction_column[valid]] = 0.5
        return result

    def _angle_features(self, target: Tensor) -> tuple[Tensor, Tensor, Tensor, Tensor]:
        dx = target[0] - self.x
        dy = target[1] - self.y
        distance = torch.hypot(dx, dy)
        relative = _normalize_angle(torch.atan2(dy, dx) - self.turret_angle)
        return torch.sin(relative), torch.cos(relative), distance, torch.abs(relative)

    def _scalar_observation(self) -> Tensor:
        outpost = self._angle_features(self.outpost_position)
        base = self._angle_features(self.base_position)
        can_fire = (~self.heat_locked & ~self.heat_permanent & (self.ammo > 0.0)).to(torch.float32)
        values = (
            self.remaining_time / self.config.episode_seconds,
            self.x / self.arena_width,
            self.y / self.arena_height,
            torch.sin(self.spin_angle),
            torch.cos(self.spin_angle),
            torch.sin(self.turret_angle),
            torch.cos(self.turret_angle),
            torch.clamp(self.spin_speed / self.config.maximum_spin_speed, -1.0, 1.0),
            torch.clamp(self.turret_speed / self.config.maximum_turret_speed, -1.0, 1.0),
            self.sentry_hp / 400.0,
            self.ammo / 1000.0,
            self.heat / 360.0,
            self.chassis_power / 100.0,
            self.buffer_energy / BUFFER_ENERGY_CAP,
            torch.clamp(self.power_cut / 5.0, max=1.0),
            (self.active_posture == 1).to(torch.float32),
            (self.active_posture == 2).to(torch.float32),
            (self.active_posture == 3).to(torch.float32),
            self.posture_reinforced.to(torch.float32),
            torch.clamp(self.posture_cooldown / 5.0, max=1.0),
            self.outpost_hp / 1500.0,
            self.base_hp / 5000.0,
            self.base_shield / 150.0,
            outpost[0],
            outpost[1],
            torch.clamp(outpost[2] / self.diagonal, max=1.0),
            (outpost[2] <= WEAPON_RANGE).to(torch.float32),
            torch.clamp(outpost[3] / math.pi, max=1.0),
            base[0],
            base[1],
            torch.clamp(base[2] / self.diagonal, max=1.0),
            (base[2] <= WEAPON_RANGE).to(torch.float32),
            torch.clamp(base[3] / math.pi, max=1.0),
            (self.outpost_hp > 0.0).to(torch.float32),
            can_fire,
            self.last_collision.to(torch.float32),
            torch.clamp(self.stuck_seconds / 5.0, max=1.0),
        )
        return torch.stack(values, dim=1)

    def _critic_observation(self) -> Tensor:
        outpost_distance = torch.hypot(
            self.outpost_position[0] - self.x, self.outpost_position[1] - self.y
        )
        base_distance = torch.hypot(
            self.base_position[0] - self.x, self.base_position[1] - self.y
        )
        values = (
            self.remaining_time / self.config.episode_seconds,
            self.x / self.arena_width,
            self.y / self.arena_height,
            torch.sin(self.spin_angle),
            torch.cos(self.spin_angle),
            torch.sin(self.turret_angle),
            torch.cos(self.turret_angle),
            self.sentry_hp / 400.0,
            self.ammo / 1000.0,
            self.heat / 360.0,
            self.buffer_energy / BUFFER_ENERGY_CAP,
            torch.clamp(self.power_cut / 5.0, max=1.0),
            (self.active_posture == 1).to(torch.float32),
            (self.active_posture == 2).to(torch.float32),
            (self.active_posture == 3).to(torch.float32),
            self.posture_reinforced.to(torch.float32),
            self.outpost_hp / 1500.0,
            self.base_hp / 5000.0,
            self.base_shield / 150.0,
            outpost_distance / self.diagonal,
            base_distance / self.diagonal,
            self.lowest_outpost_hp / 1500.0,
            self.lowest_base_durability / 5150.0,
            self.outpost_bonus_paid.to(torch.float32),
            self.base_bonus_paid.to(torch.float32),
        )
        return torch.stack(values, dim=1)

    def _observation(self, *, recurrent_reset: Tensor) -> TensorAssaultObservation:
        return TensorAssaultObservation(
            scalar=self._scalar_observation(),
            spatial=self._local_map(),
            critic=self._critic_observation(),
            recurrent_reset=recurrent_reset,
        )

    def replay_state(self, index: int = 0) -> dict[str, object]:
        """Copy one world to the existing replay schema outside the hot path."""
        if not 0 <= index < self.num_envs:
            raise IndexError(index)
        values = torch.stack(
            (
                self.x[index],
                self.y[index],
                self.spin_angle[index],
                self.turret_angle[index],
                self.spin_speed[index],
                self.turret_speed[index],
                self.sentry_hp[index],
                self.ammo[index],
                self.heat[index],
                self.active_posture[index].float(),
                self.posture_reinforced[index].float(),
                self.remaining_time[index],
                self.outpost_hp[index],
                self.base_hp[index],
                self.base_shield[index],
            )
        ).detach().cpu().tolist()
        return {
            "schema": "single-sentry-assault-v1",
            "step_index": int(self.step_index[index].item()),
            "remaining_time": values[11],
            "sentry": {
                "x": values[0], "y": values[1],
                "chassis_angle": values[2], "turret_angle": values[3],
                "spin_speed": values[4], "turret_speed": values[5],
                "hp": values[6], "ammo": int(values[7]), "heat": values[8],
                "posture": int(values[9]), "reinforced": bool(values[10]),
            },
            "structures": {
                "outpost_hp": values[12], "base_hp": values[13],
                "base_shield": values[14],
            },
        }


__all__ = [
    "GpuSentryAssaultEnv",
    "TensorAssaultObservation",
    "TensorAssaultStep",
    "TensorSentryAction",
]
