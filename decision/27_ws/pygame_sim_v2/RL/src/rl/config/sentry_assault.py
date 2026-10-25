"""Typed configuration for end-to-end sentry assault training."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import math


@dataclass(frozen=True, slots=True)
class RewardV2Config:
    """Efficiency reward used for warm-start refinement of the V1 policy."""

    distance_progress_scale: float = 0.5
    aim_progress_scale: float = 0.2
    exploration_cell_bonus: float = 0.01
    exploration_reward_cap: float = 1.0
    structure_damage_scale: float = 1.0
    outpost_time_multiplier: float = 10.0
    base_time_multiplier: float = 20.0
    collision_penalty: float = 0.02
    stuck_penalty: float = 0.05
    stuck_penalty_after_seconds: float = 1.0
    time_penalty_per_second: float = 0.01
    permanent_heat_lock_penalty: float = 1000.0

    def __post_init__(self) -> None:
        values = (
            self.distance_progress_scale,
            self.aim_progress_scale,
            self.exploration_cell_bonus,
            self.exploration_reward_cap,
            self.structure_damage_scale,
            self.outpost_time_multiplier,
            self.base_time_multiplier,
            self.collision_penalty,
            self.stuck_penalty,
            self.stuck_penalty_after_seconds,
            self.time_penalty_per_second,
            self.permanent_heat_lock_penalty,
        )
        if min(values) < 0.0:
            raise ValueError("reward V2 values must be non-negative")
        if self.stuck_penalty_after_seconds <= 0.0:
            raise ValueError("stuck_penalty_after_seconds must be positive")


@dataclass(frozen=True, slots=True)
class RewardV3Config:
    """Route-efficiency reward that preserves autonomous tactical choice."""

    route_progress_scale: float = 2.0
    movement_cost_per_meter: float = 0.5
    aim_progress_scale: float = 0.2
    exploration_cell_bonus: float = 0.01
    exploration_reward_cap: float = 1.0
    structure_damage_scale: float = 1.0
    outpost_time_multiplier: float = 10.0
    base_time_multiplier: float = 20.0
    outpost_first_hit_time_multiplier: float = 1.0
    base_first_hit_time_multiplier: float = 0.5
    preferred_fire_min_range: float = 2.2
    preferred_fire_max_range: float = 3.8
    preferred_fire_clearance: float = 0.10
    open_fire_bonus_per_second: float = 0.25
    wall_proximity_penalty_per_second: float = 0.5
    invalid_fire_penalty: float = 0.02
    collision_penalty: float = 0.05
    stuck_penalty: float = 0.10
    stuck_penalty_after_seconds: float = 1.0
    no_damage_grace_seconds: float = 8.0
    no_damage_penalty_per_second: float = 0.20
    time_penalty_per_second: float = 0.02
    permanent_heat_lock_penalty: float = 1000.0
    curriculum_floor_near_outpost: float = 0.05
    curriculum_floor_random_field: float = 0.05
    curriculum_floor_near_base: float = 0.03
    curriculum_floor_upper_tunnel: float = 0.10
    curriculum_floor_vertical_tunnel: float = 0.07

    def __post_init__(self) -> None:
        values = (
            self.route_progress_scale,
            self.movement_cost_per_meter,
            self.aim_progress_scale,
            self.exploration_cell_bonus,
            self.exploration_reward_cap,
            self.structure_damage_scale,
            self.outpost_time_multiplier,
            self.base_time_multiplier,
            self.outpost_first_hit_time_multiplier,
            self.base_first_hit_time_multiplier,
            self.preferred_fire_min_range,
            self.preferred_fire_max_range,
            self.preferred_fire_clearance,
            self.open_fire_bonus_per_second,
            self.wall_proximity_penalty_per_second,
            self.invalid_fire_penalty,
            self.collision_penalty,
            self.stuck_penalty,
            self.stuck_penalty_after_seconds,
            self.no_damage_grace_seconds,
            self.no_damage_penalty_per_second,
            self.time_penalty_per_second,
            self.permanent_heat_lock_penalty,
            self.curriculum_floor_near_outpost,
            self.curriculum_floor_random_field,
            self.curriculum_floor_near_base,
            self.curriculum_floor_upper_tunnel,
            self.curriculum_floor_vertical_tunnel,
        )
        if min(values) < 0.0:
            raise ValueError("reward V3 values must be non-negative")
        if self.route_progress_scale <= 0.0:
            raise ValueError("route_progress_scale must be positive")
        if self.stuck_penalty_after_seconds <= 0.0:
            raise ValueError("stuck_penalty_after_seconds must be positive")
        if self.no_damage_grace_seconds <= 0.0:
            raise ValueError("no_damage_grace_seconds must be positive")
        if not 0.0 < self.preferred_fire_min_range < self.preferred_fire_max_range:
            raise ValueError("preferred fire range must be increasing and positive")
        curriculum_floor = (
            self.curriculum_floor_near_outpost
            + self.curriculum_floor_random_field
            + self.curriculum_floor_near_base
            + self.curriculum_floor_upper_tunnel
            + self.curriculum_floor_vertical_tunnel
        )
        if curriculum_floor >= 1.0:
            raise ValueError("reward V3 curriculum floor must leave home probability")


@dataclass(frozen=True, slots=True)
class RewardV4Config(RewardV3Config):
    """V3 route refinement that favours open, full-damage base positions."""

    route_progress_scale: float = 3.0
    preferred_fire_clearance: float = 0.60
    open_fire_bonus_per_second: float = 1.0
    wall_proximity_penalty_per_second: float = 5.0
    base_normal_damage_margin: float = 0.10
    off_tactical_field_penalty_per_meter_second: float = 2.0

    def __post_init__(self) -> None:
        RewardV3Config.__post_init__(self)
        if self.base_normal_damage_margin < 0.0:
            raise ValueError("base_normal_damage_margin must be non-negative")
        if self.off_tactical_field_penalty_per_meter_second < 0.0:
            raise ValueError(
                "off_tactical_field_penalty_per_meter_second must be non-negative"
            )


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
    reward_version: int = 1
    reward_v2: RewardV2Config = field(default_factory=RewardV2Config)
    reward_v3: RewardV3Config = field(default_factory=RewardV3Config)
    reward_v4: RewardV4Config = field(default_factory=RewardV4Config)

    def __post_init__(self) -> None:
        if isinstance(self.reward_v2, Mapping):
            object.__setattr__(self, "reward_v2", RewardV2Config(**self.reward_v2))
        if isinstance(self.reward_v3, Mapping):
            object.__setattr__(self, "reward_v3", RewardV3Config(**self.reward_v3))
        if isinstance(self.reward_v4, Mapping):
            object.__setattr__(self, "reward_v4", RewardV4Config(**self.reward_v4))
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
        if self.reward_version not in (1, 2, 3, 4):
            raise ValueError("reward_version must be 1, 2, 3, or 4")


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
