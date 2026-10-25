"""Recurrent vector rollout storage for mixed sentry actions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator, Mapping

import numpy as np
import torch
from torch import Tensor

from rl.models import LSTMState
from rl.models.actor_critic import CATEGORICAL_ACTION_SIZES, CONTINUOUS_ACTION_SIZE
from .gae import generalized_advantage_estimate


@dataclass(frozen=True, slots=True)
class RecurrentBatch:
    scalar: Tensor
    spatial: Tensor
    critic: Tensor
    categorical_actions: Mapping[str, Tensor]
    continuous_actions: Tensor
    old_log_probabilities: Tensor
    old_values: Tensor
    returns: Tensor
    advantages: Tensor
    episode_starts: Tensor
    valid: Tensor
    initial_state: LSTMState


class RecurrentRollout:
    def __init__(
        self,
        capacity: int,
        num_envs: int,
        scalar_size: int,
        spatial_shape: tuple[int, int, int],
        critic_size: int,
        *,
        lstm_layers: int,
        recurrent_hidden: int,
        device: torch.device | str,
    ) -> None:
        if min(capacity, num_envs, scalar_size, critic_size) <= 0:
            raise ValueError("rollout dimensions must be positive")
        self.capacity = capacity
        self.num_envs = num_envs
        self.scalar_size = scalar_size
        self.spatial_shape = spatial_shape
        self.critic_size = critic_size
        self.lstm_layers = lstm_layers
        self.recurrent_hidden = recurrent_hidden
        self.device = torch.device(device)
        self.position = 0
        self.advantages: Tensor | None = None
        self.returns: Tensor | None = None
        self.scalar = torch.zeros(
            capacity, num_envs, scalar_size, device=self.device
        )
        self.spatial = torch.zeros(
            capacity,
            num_envs,
            *spatial_shape,
            dtype=torch.uint8,
            device=self.device,
        )
        self.critic = torch.zeros(
            capacity, num_envs, critic_size, device=self.device
        )
        self.categorical_actions = {
            name: torch.zeros(
                capacity, num_envs, dtype=torch.long, device=self.device
            )
            for name in CATEGORICAL_ACTION_SIZES
        }
        self.continuous_actions = torch.zeros(
            capacity, num_envs, CONTINUOUS_ACTION_SIZE, device=self.device
        )
        self.log_probabilities = torch.zeros(capacity, num_envs, device=self.device)
        self.values = torch.zeros(capacity, num_envs, device=self.device)
        self.next_values = torch.zeros(capacity, num_envs, device=self.device)
        self.rewards = torch.zeros(capacity, num_envs, device=self.device)
        self.terminated = torch.zeros(
            capacity, num_envs, dtype=torch.bool, device=self.device
        )
        self.truncated = torch.zeros(
            capacity, num_envs, dtype=torch.bool, device=self.device
        )
        self.episode_starts = torch.zeros(
            capacity, num_envs, dtype=torch.bool, device=self.device
        )
        self.hidden_h = torch.zeros(
            capacity, lstm_layers, num_envs, recurrent_hidden, device=self.device
        )
        self.hidden_c = torch.zeros_like(self.hidden_h)

    @property
    def full(self) -> bool:
        return self.position == self.capacity

    def clear(self) -> None:
        self.position = 0
        self.advantages = None
        self.returns = None

    @staticmethod
    def _copy(target: Tensor, value) -> None:
        source = torch.as_tensor(value, dtype=target.dtype, device=target.device)
        if source.shape != target.shape:
            raise ValueError(
                f"rollout shape mismatch expected={tuple(target.shape)} got={tuple(source.shape)}"
            )
        target.copy_(source)

    def add(
        self,
        *,
        scalar,
        spatial,
        critic,
        categorical_actions: Mapping[str, object],
        continuous_actions,
        log_probabilities,
        values,
        next_values,
        rewards,
        terminated,
        truncated,
        episode_starts,
        initial_state: LSTMState,
    ) -> None:
        if self.full:
            raise RuntimeError("rollout is full")
        if set(categorical_actions) != set(CATEGORICAL_ACTION_SIZES):
            raise ValueError("categorical action branches mismatch")
        index = self.position
        self._copy(self.scalar[index], scalar)
        spatial_tensor = torch.as_tensor(spatial, device=self.device)
        expected_spatial = self.spatial[index].shape
        if spatial_tensor.shape != expected_spatial:
            raise ValueError(
                "rollout shape mismatch "
                f"expected={tuple(expected_spatial)} got={tuple(spatial_tensor.shape)}"
            )
        self.spatial[index].copy_(
            torch.round(spatial_tensor * 2.0).to(torch.uint8)
        )
        self._copy(self.critic[index], critic)
        for name in CATEGORICAL_ACTION_SIZES:
            self._copy(
                self.categorical_actions[name][index], categorical_actions[name]
            )
        self._copy(self.continuous_actions[index], continuous_actions)
        self._copy(self.log_probabilities[index], log_probabilities)
        self._copy(self.values[index], values)
        self._copy(self.next_values[index], next_values)
        self._copy(self.rewards[index], rewards)
        self._copy(self.terminated[index], terminated)
        self._copy(self.truncated[index], truncated)
        self._copy(self.episode_starts[index], episode_starts)
        expected = (self.lstm_layers, self.num_envs, self.recurrent_hidden)
        if initial_state[0].shape != expected or initial_state[1].shape != expected:
            raise ValueError("initial recurrent state shape mismatch")
        self.hidden_h[index].copy_(initial_state[0].detach().to(self.device))
        self.hidden_c[index].copy_(initial_state[1].detach().to(self.device))
        self.position += 1

    def compute_returns(self, *, gamma: float, gae_lambda: float) -> None:
        if self.position == 0:
            raise RuntimeError("empty rollout")
        data = slice(0, self.position)
        self.advantages, self.returns = generalized_advantage_estimate(
            self.rewards[data],
            self.values[data],
            self.next_values[data],
            self.terminated[data],
            self.truncated[data],
            gamma=gamma,
            gae_lambda=gae_lambda,
        )

    def iter_batches(
        self,
        *,
        sequence_length: int,
        minibatch_sequences: int,
    ) -> Iterator[RecurrentBatch]:
        if self.advantages is None or self.returns is None:
            raise RuntimeError("returns must be computed before batching")
        if self.position % sequence_length == 0:
            yield from self._iter_dense_batches(
                sequence_length=sequence_length,
                minibatch_sequences=minibatch_sequences,
            )
            return
        descriptors = [
            (env_index, start, min(start + sequence_length, self.position))
            for env_index in range(self.num_envs)
            for start in range(0, self.position, sequence_length)
        ]
        np.random.shuffle(descriptors)
        for offset in range(0, len(descriptors), minibatch_sequences):
            selected = descriptors[offset : offset + minibatch_sequences]
            batch = len(selected)
            scalar = torch.zeros(
                batch, sequence_length, self.scalar_size, device=self.device
            )
            spatial = torch.zeros(
                batch, sequence_length, *self.spatial_shape, device=self.device
            )
            critic = torch.zeros(
                batch, sequence_length, self.critic_size, device=self.device
            )
            categorical = {
                name: torch.zeros(
                    batch, sequence_length, dtype=torch.long, device=self.device
                )
                for name in CATEGORICAL_ACTION_SIZES
            }
            continuous = torch.zeros(
                batch,
                sequence_length,
                CONTINUOUS_ACTION_SIZE,
                device=self.device,
            )
            old_log_probabilities = torch.zeros(
                batch, sequence_length, device=self.device
            )
            old_values = torch.zeros(batch, sequence_length, device=self.device)
            returns = torch.zeros(batch, sequence_length, device=self.device)
            advantages = torch.zeros(batch, sequence_length, device=self.device)
            episode_starts = torch.ones(
                batch, sequence_length, dtype=torch.bool, device=self.device
            )
            valid = torch.zeros(
                batch, sequence_length, dtype=torch.bool, device=self.device
            )
            initial_h = torch.zeros(
                self.lstm_layers,
                batch,
                self.recurrent_hidden,
                device=self.device,
            )
            initial_c = torch.zeros_like(initial_h)
            for batch_index, (env_index, start, end) in enumerate(selected):
                length = end - start
                destination = slice(0, length)
                source = (slice(start, end), env_index)
                scalar[batch_index, destination] = self.scalar[source]
                spatial[batch_index, destination] = self.spatial[source]
                critic[batch_index, destination] = self.critic[source]
                for name in CATEGORICAL_ACTION_SIZES:
                    categorical[name][batch_index, destination] = (
                        self.categorical_actions[name][source]
                    )
                continuous[batch_index, destination] = self.continuous_actions[source]
                old_log_probabilities[batch_index, destination] = self.log_probabilities[source]
                old_values[batch_index, destination] = self.values[source]
                returns[batch_index, destination] = self.returns[source]
                advantages[batch_index, destination] = self.advantages[source]
                episode_starts[batch_index, destination] = self.episode_starts[source]
                valid[batch_index, destination] = True
                initial_h[:, batch_index] = self.hidden_h[start, :, env_index]
                initial_c[:, batch_index] = self.hidden_c[start, :, env_index]
            yield RecurrentBatch(
                scalar=scalar,
                spatial=spatial.to(torch.float32).mul_(0.5),
                critic=critic,
                categorical_actions=categorical,
                continuous_actions=continuous,
                old_log_probabilities=old_log_probabilities,
                old_values=old_values,
                returns=returns,
                advantages=advantages,
                episode_starts=episode_starts,
                valid=valid,
                initial_state=(initial_h, initial_c),
            )

    def _iter_dense_batches(
        self,
        *,
        sequence_length: int,
        minibatch_sequences: int,
    ) -> Iterator[RecurrentBatch]:
        """Vectorized recurrent batching for full, evenly divided rollouts."""
        if self.advantages is None or self.returns is None:
            raise RuntimeError("returns must be computed before batching")
        chunks = self.position // sequence_length
        total = self.num_envs * chunks

        def sequences(value: Tensor) -> Tensor:
            tail = value.shape[2:]
            return (
                value[: self.position]
                .transpose(0, 1)
                .reshape(total, sequence_length, *tail)
            )

        scalar = sequences(self.scalar)
        spatial = sequences(self.spatial)
        critic = sequences(self.critic)
        categorical = {
            name: sequences(value) for name, value in self.categorical_actions.items()
        }
        continuous = sequences(self.continuous_actions)
        old_log_probabilities = sequences(self.log_probabilities)
        old_values = sequences(self.values)
        returns = sequences(self.returns)
        advantages = sequences(self.advantages)
        episode_starts = sequences(self.episode_starts)
        valid = torch.ones(
            total, sequence_length, dtype=torch.bool, device=self.device
        )
        starts = torch.arange(
            0, self.position, sequence_length, device=self.device
        )
        initial_h = (
            self.hidden_h[starts]
            .permute(2, 0, 1, 3)
            .reshape(total, self.lstm_layers, self.recurrent_hidden)
            .permute(1, 0, 2)
        )
        initial_c = (
            self.hidden_c[starts]
            .permute(2, 0, 1, 3)
            .reshape(total, self.lstm_layers, self.recurrent_hidden)
            .permute(1, 0, 2)
        )
        order = torch.randperm(total, device=self.device)
        for offset in range(0, total, minibatch_sequences):
            selected = order[offset : offset + minibatch_sequences]
            yield RecurrentBatch(
                scalar=scalar[selected],
                spatial=spatial[selected].to(torch.float32).mul_(0.5),
                critic=critic[selected],
                categorical_actions={
                    name: value[selected] for name, value in categorical.items()
                },
                continuous_actions=continuous[selected],
                old_log_probabilities=old_log_probabilities[selected],
                old_values=old_values[selected],
                returns=returns[selected],
                advantages=advantages[selected],
                episode_starts=episode_starts[selected],
                valid=valid[selected],
                initial_state=(initial_h[:, selected], initial_c[:, selected]),
            )


__all__ = ["RecurrentBatch", "RecurrentRollout"]
