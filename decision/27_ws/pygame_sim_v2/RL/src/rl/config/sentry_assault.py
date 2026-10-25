"""Typed configuration for end-to-end sentry assault training."""

from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass(frozen=True, slots=True)
class AssaultConfig:
    time_step: float = 0.1
    episode_seconds: float = 420.0
    movement_speed: float = 3.0
    maximum_spin_speed: float = math.radians(300.0)
    maximum_turret_speed: float = math.radians(210.0)
    initial_ammunition: int = 1000
    unlimited_ammunition: bool = True
    local_map_cells: int = 41
    local_map_resolution: float = 0.20
    reward_scale: float = 0.005
    distance_progress_scale: float = 2.0
    aim_progress_scale: float = 2.0
    exploration_cell_size: float = 0.5
    exploration_cell_bonus: float = 0.03
    exploration_reward_cap: float = 8.0
    distance_12m_bonus: float = 1.0
    distance_8m_bonus: float = 2.0
    distance_sensor_bonus: float = 10.0
    first_range_bonus: float = 20.0
    first_line_of_sight_bonus: float = 30.0
    aim_30deg_bonus: float = 1.0
    aim_15deg_bonus: float = 2.0
    aim_8deg_bonus: float = 3.0
    aim_4deg_bonus: float = 15.0
    first_fire_command_bonus: float = 5.0
    first_sensor_fire_bonus: float = 15.0
    first_range_fire_bonus: float = 30.0
    valid_solution_bonus: float = 75.0
    valid_fire_step_bonus: float = 2.0
    first_hit_bonus: float = 250.0
    invalid_fire_penalty: float = 0.02
    permanent_heat_lock_penalty: float = 1000.0
    structure_damage_scale: float = 5.0
    outpost_destroy_bonus: float = 5000.0
    base_destroy_bonus: float = 10000.0
    curriculum_enabled: bool = False
    curriculum_transition_steps: int = 20_000_000
    curriculum_max_progress: float = 0.70
    escape_stuck_bonus: float = 1.0
    collision_penalty: float = 0.02
    stuck_penalty: float = 0.05
    stuck_penalty_after_seconds: float = 1.0
    time_penalty_per_second: float = 0.01
    outpost_time_multiplier: float = 10.0
    base_time_multiplier: float = 20.0

    def __post_init__(self) -> None:
        numeric = (
            self.time_step,
            self.episode_seconds,
            self.movement_speed,
            self.maximum_spin_speed,
            self.maximum_turret_speed,
            self.local_map_resolution,
            self.reward_scale,
            self.distance_progress_scale,
            self.aim_progress_scale,
            self.exploration_cell_size,
            self.exploration_cell_bonus,
            self.exploration_reward_cap,
            self.distance_12m_bonus,
            self.distance_8m_bonus,
            self.distance_sensor_bonus,
            self.first_range_bonus,
            self.first_line_of_sight_bonus,
            self.aim_30deg_bonus,
            self.aim_15deg_bonus,
            self.aim_8deg_bonus,
            self.aim_4deg_bonus,
            self.first_fire_command_bonus,
            self.first_sensor_fire_bonus,
            self.first_range_fire_bonus,
            self.valid_solution_bonus,
            self.valid_fire_step_bonus,
            self.first_hit_bonus,
            self.invalid_fire_penalty,
            self.permanent_heat_lock_penalty,
            self.structure_damage_scale,
            self.outpost_destroy_bonus,
            self.base_destroy_bonus,
            self.escape_stuck_bonus,
            self.collision_penalty,
            self.stuck_penalty,
            self.stuck_penalty_after_seconds,
            self.time_penalty_per_second,
            self.outpost_time_multiplier,
            self.base_time_multiplier,
        )
        if min(numeric) <= 0.0:
            raise ValueError("assault configuration values must be positive")
        if self.local_map_cells < 5 or self.local_map_cells % 2 == 0:
            raise ValueError("local_map_cells must be an odd integer >= 5")
        if self.initial_ammunition <= 0:
            raise ValueError("initial_ammunition must be positive")
        if self.curriculum_transition_steps <= 0:
            raise ValueError("curriculum_transition_steps must be positive")
        if not 0.0 < self.curriculum_max_progress <= 1.0:
            raise ValueError("curriculum_max_progress must be in (0, 1]")


@dataclass(frozen=True, slots=True)
class NetworkConfig:
    scalar_hidden: int = 128
    spatial_hidden: int = 128
    recurrent_hidden: int = 256
    critic_hidden: int = 128
    lstm_layers: int = 1


@dataclass(frozen=True, slots=True)
class PPOConfig:
    gamma: float = 0.9995
    gae_lambda: float = 0.97
    learning_rate: float = 1e-4
    clip_ratio: float = 0.2
    value_clip: float = 0.2
    value_coefficient: float = 0.5
    entropy_coefficient: float = 0.01
    fire_entropy_coefficient: float = 0.05
    continuous_entropy_coefficient: float = 0.001
    maximum_gradient_norm: float = 0.5
    update_epochs: int = 3
    sequence_length: int = 32
    minibatch_sequences: int = 64
    target_kl: float = 0.02


@dataclass(frozen=True, slots=True)
class TrainingConfig:
    num_envs: int = 32
    rollout_steps: int = 256
    duration_hours: float = 2.0
    max_env_steps: int | None = None
    seed: int = 20261024
    checkpoint_minutes: float = 20.0
    log_seconds: float = 10.0
    device: str = "auto"
