"""Synchronous vector wrapper for many independent single-sentry worlds."""

from __future__ import annotations

from typing import Sequence

from rl.config import AssaultConfig
from .field import AssaultField
from .cpu_env import AssaultObservation, AssaultStep, SentryAction, SentryAssaultEnv


class VectorSentryAssaultEnv:
    def __init__(self, num_envs: int, config: AssaultConfig | None = None) -> None:
        if num_envs <= 0:
            raise ValueError("num_envs must be positive")
        field = AssaultField.load()
        self.envs = tuple(
            SentryAssaultEnv(config, field=field) for _ in range(num_envs)
        )

    @property
    def num_envs(self) -> int:
        return len(self.envs)

    def reset(self, *, seed: int) -> tuple[AssaultObservation, ...]:
        return tuple(
            env.reset(seed=seed + index) for index, env in enumerate(self.envs)
        )

    def reset_at(self, index: int, *, seed: int) -> AssaultObservation:
        return self.envs[index].reset(seed=seed)

    def step(self, actions: Sequence[SentryAction]) -> tuple[AssaultStep, ...]:
        if len(actions) != self.num_envs:
            raise ValueError("one action is required per environment")
        return tuple(env.step(action) for env, action in zip(self.envs, actions))


__all__ = ["VectorSentryAssaultEnv"]
