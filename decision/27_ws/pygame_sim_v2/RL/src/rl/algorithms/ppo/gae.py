"""Generalized advantage estimation with explicit value bootstrap."""

from __future__ import annotations

import torch
from torch import Tensor


def generalized_advantage_estimate(
    rewards: Tensor,
    values: Tensor,
    next_values: Tensor,
    terminated: Tensor,
    truncated: Tensor,
    *,
    gamma: float,
    gae_lambda: float,
) -> tuple[Tensor, Tensor]:
    if rewards.shape != values.shape or rewards.shape != next_values.shape:
        raise ValueError("reward and value tensors must share shape")
    advantages = torch.zeros_like(rewards)
    running = torch.zeros(
        rewards.shape[1], dtype=rewards.dtype, device=rewards.device
    )
    for time_index in range(rewards.shape[0] - 1, -1, -1):
        bootstrap = (~terminated[time_index]).to(dtype=rewards.dtype)
        continuation = (~(terminated[time_index] | truncated[time_index])).to(
            dtype=rewards.dtype
        )
        delta = (
            rewards[time_index]
            + gamma * next_values[time_index] * bootstrap
            - values[time_index]
        )
        running = delta + gamma * gae_lambda * continuation * running
        advantages[time_index] = running
    return advantages, advantages + values


__all__ = ["generalized_advantage_estimate"]
