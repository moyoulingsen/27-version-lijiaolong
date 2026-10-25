"""Deterministic checkpoint evaluation in the real assault scenario."""

from __future__ import annotations

from pathlib import Path

import torch

from rl.algorithms.ppo import RecurrentPPO
from rl.compat import install_legacy_checkpoint_aliases
from rl.config import AssaultConfig, NetworkConfig, PPOConfig
from rl.envs.sentry_assault import SentryAssaultEnv
from rl.replay import ReplayRecorder
from .checkpoint import load_checkpoint


def evaluate_checkpoint(
    checkpoint: Path,
    *,
    episodes: int,
    seed: int,
    replay_directory: Path | None = None,
    device: str = "cpu",
    deterministic: bool = True,
) -> dict[str, object]:
    if episodes <= 0:
        raise ValueError("episodes must be positive")
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    install_legacy_checkpoint_aliases()
    payload = torch.load(checkpoint, map_location="cpu", weights_only=False)
    metadata = payload.get("metadata", {})
    assault = AssaultConfig(**metadata.get("assault", {}))
    network = NetworkConfig(**metadata.get("network", {}))
    ppo = PPOConfig(**metadata.get("ppo", {}))
    env = SentryAssaultEnv(assault)
    learner = RecurrentPPO(
        env.scalar_size,
        env.spatial_shape,
        env.critic_size,
        num_envs=1,
        network=network,
        config=ppo,
        device=device,
    )
    load_checkpoint(checkpoint, learner)
    recorder = ReplayRecorder(replay_directory) if replay_directory else None
    successes = 0
    scores: list[float] = []
    remaining_times: list[float] = []
    for episode in range(1, episodes + 1):
        observation = env.reset(seed=seed + episode - 1)
        if recorder:
            recorder.start(episode, seed=seed + episode - 1, metadata={"checkpoint": str(checkpoint)})
        score = 0.0
        while True:
            decision = learner.act(
                (observation,), deterministic=deterministic
            )
            transition = env.step(decision.actions[0])
            score += transition.raw_reward
            if recorder:
                recorder.write(
                    {
                        "type": "frame",
                        "action": {
                            "move_direction": decision.actions[0].move_direction,
                            "posture": decision.actions[0].posture,
                            "reinforce": decision.actions[0].reinforce,
                            "fire": decision.actions[0].fire,
                            "spin_speed": decision.actions[0].spin_speed,
                            "turret_speed": decision.actions[0].turret_speed,
                        },
                        "reward": transition.raw_reward,
                        "state": env.replay_state(),
                    }
                )
            observation = transition.observation
            if transition.terminated or transition.truncated:
                successes += int(transition.terminated)
                scores.append(score)
                remaining_times.append(float(transition.info["remaining_time"]))
                break
        if recorder:
            recorder.close()
    return {
        "episodes": episodes,
        "successes": successes,
        "success_rate": successes / episodes,
        "mean_raw_score": sum(scores) / len(scores),
        "mean_remaining_time": sum(remaining_times) / len(remaining_times),
        "policy_mode": "deterministic" if deterministic else "stochastic",
    }


__all__ = ["evaluate_checkpoint"]
