from __future__ import annotations

from dataclasses import asdict, replace

import torch

from rl.algorithms.ppo import RecurrentPPO
from rl.config import (
    AssaultConfig,
    NetworkConfig,
    PPOConfig,
    RewardV2Config,
    RewardV3Config,
)
from rl.envs.sentry_assault import SentryAssaultEnv


def _learner() -> RecurrentPPO:
    env = SentryAssaultEnv()
    return RecurrentPPO(
        env.scalar_size,
        env.spatial_shape,
        env.critic_size,
        num_envs=1,
        network=NetworkConfig(),
        config=PPOConfig(),
        device="cpu",
    )


def test_reward_v1_remains_default_and_v2_round_trips() -> None:
    original = AssaultConfig()
    assert original.reward_version == 1
    configured = replace(original, reward_version=2)
    restored = AssaultConfig(**asdict(configured))
    assert restored.reward_version == 2
    assert isinstance(restored.reward_v2, RewardV2Config)
    assert restored.structure_damage_scale == original.structure_damage_scale
    assert restored.reward_v2.structure_damage_scale == 1.0


def test_reward_v3_round_trips_without_changing_older_profiles() -> None:
    original = AssaultConfig()
    configured = replace(original, reward_version=3)
    restored = AssaultConfig(**asdict(configured))
    assert restored.reward_version == 3
    assert isinstance(restored.reward_v3, RewardV3Config)
    assert restored.reward_v2 == original.reward_v2
    assert restored.reward_v3.movement_cost_per_meter == 0.5
    assert restored.reward_v3.curriculum_floor_upper_tunnel > 0.0


def test_actor_warm_start_keeps_fresh_critic_and_optimizer() -> None:
    source = _learner()
    target = _learner()
    with torch.no_grad():
        for name, parameter in source.model.named_parameters():
            parameter.fill_(0.25 if not name.startswith(("critic_encoder", "value_head")) else 0.75)
    target_critic = {
        name: value.detach().clone()
        for name, value in target.model.state_dict().items()
        if name.startswith(("critic_encoder", "value_head"))
    }
    loaded = target.load_actor_warm_start(source.checkpoint())
    assert loaded > 0
    source_state = source.model.state_dict()
    target_state = target.model.state_dict()
    assert torch.equal(
        target_state["categorical_heads.move_direction.weight"],
        source_state["categorical_heads.move_direction.weight"],
    )
    for name, value in target_critic.items():
        assert torch.equal(target_state[name], value)
    assert not target.optimizer.state


def test_route_reset_keeps_fresh_movement_head() -> None:
    source = _learner()
    target = _learner()
    with torch.no_grad():
        for parameter in source.model.parameters():
            parameter.fill_(0.25)
    original_move = {
        name: value.detach().clone()
        for name, value in target.model.state_dict().items()
        if name.startswith("categorical_heads.move_direction.")
    }
    target.load_actor_warm_start(
        source.checkpoint(),
        reset_movement_head=True,
    )
    target_state = target.model.state_dict()
    source_state = source.model.state_dict()
    for name, value in original_move.items():
        assert torch.equal(target_state[name], value)
    assert torch.equal(
        target_state["categorical_heads.fire.weight"],
        source_state["categorical_heads.fire.weight"],
    )
