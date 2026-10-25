"""Shared recurrent PPO learner for all vectorized sentry worlds."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np
import torch
from torch import Tensor
from torch.nn import functional as F

from rl.config import NetworkConfig, PPOConfig
from rl.envs.sentry_assault import (
    AssaultObservation,
    SentryAction,
    TensorAssaultObservation,
    TensorSentryAction,
)
from rl.models import LSTMState, SentryActorCritic
from rl.models.actor_critic import CATEGORICAL_ACTION_SIZES
from .mixed_distribution import MixedActionDistribution
from .rollout import RecurrentRollout


@dataclass(frozen=True, slots=True)
class ActionDecision:
    actions: tuple[SentryAction, ...]
    categorical: dict[str, Tensor]
    continuous: Tensor
    log_probabilities: Tensor
    values: Tensor
    initial_state: LSTMState
    next_state: LSTMState


@dataclass(frozen=True, slots=True)
class TensorActionDecision:
    action: TensorSentryAction
    categorical: dict[str, Tensor]
    continuous: Tensor
    log_probabilities: Tensor
    values: Tensor
    initial_state: LSTMState
    next_state: LSTMState


@dataclass(frozen=True, slots=True)
class PPOUpdateStats:
    policy_loss: float
    value_loss: float
    entropy: float
    approximate_kl: float
    clip_fraction: float
    gradient_norm: float
    updates: int
    early_stopped: bool


class RecurrentPPO:
    def __init__(
        self,
        scalar_size: int,
        spatial_shape: tuple[int, int, int],
        critic_size: int,
        *,
        num_envs: int,
        network: NetworkConfig | None = None,
        config: PPOConfig | None = None,
        device: torch.device | str = "cpu",
    ) -> None:
        self.network_config = network or NetworkConfig()
        self.config = config or PPOConfig()
        self.device = torch.device(device)
        self.model = SentryActorCritic(
            scalar_size,
            spatial_shape,
            critic_size,
            self.network_config,
        ).to(self.device)
        self.optimizer = torch.optim.Adam(
            self.model.parameters(), lr=self.config.learning_rate, eps=1e-5
        )
        self.state = self.model.initial_state(num_envs, device=self.device)

    @staticmethod
    def _observation_tensors(
        observations: Sequence[AssaultObservation],
        device: torch.device,
    ) -> tuple[Tensor, Tensor, Tensor, Tensor]:
        scalar = torch.as_tensor(
            np.stack([item.scalar for item in observations]),
            dtype=torch.float32,
            device=device,
        )
        spatial = torch.as_tensor(
            np.stack([item.spatial for item in observations]),
            dtype=torch.float32,
            device=device,
        )
        critic = torch.as_tensor(
            np.stack([item.critic for item in observations]),
            dtype=torch.float32,
            device=device,
        )
        reset = torch.as_tensor(
            [item.recurrent_reset for item in observations],
            dtype=torch.bool,
            device=device,
        )
        return scalar, spatial, critic, reset

    @torch.no_grad()
    def act(
        self,
        observations: Sequence[AssaultObservation],
        *,
        deterministic: bool = False,
    ) -> ActionDecision:
        scalar, spatial, critic, reset = self._observation_tensors(
            observations, self.device
        )
        initial_state = tuple(component.detach().clone() for component in self.state)
        logits, mean, log_std, values, next_state = self.model.forward_step(
            scalar, spatial, critic, self.state, reset
        )
        distribution = MixedActionDistribution(logits, mean, log_std)
        categorical, continuous = (
            distribution.mode() if deterministic else distribution.sample()
        )
        log_probabilities = distribution.log_prob(categorical, continuous)
        self.state = tuple(component.detach() for component in next_state)
        categorical_names = tuple(CATEGORICAL_ACTION_SIZES)
        categorical_matrix = torch.stack(
            [categorical[name] for name in categorical_names], dim=-1
        ).detach().cpu()
        categorical_cpu = {
            name: categorical_matrix[:, column]
            for column, name in enumerate(categorical_names)
        }
        continuous_cpu = continuous.detach().cpu()
        categorical_rows = categorical_matrix.tolist()
        continuous_rows = continuous_cpu.tolist()
        actions = tuple(
            SentryAction(
                move_direction=int(categorical_rows[index][0]),
                posture=int(categorical_rows[index][1]),
                reinforce=int(categorical_rows[index][2]),
                fire=int(categorical_rows[index][3]),
                spin_speed=float(continuous_rows[index][0]),
                turret_speed=float(continuous_rows[index][1]),
            )
            for index in range(len(observations))
        )
        return ActionDecision(
            actions=actions,
            categorical=categorical_cpu,
            continuous=continuous_cpu,
            log_probabilities=log_probabilities.detach().cpu(),
            values=values.detach().cpu(),
            initial_state=tuple(component.detach().cpu() for component in initial_state),
            next_state=tuple(component.detach().clone() for component in next_state),
        )

    @torch.no_grad()
    def act_tensors(
        self,
        observation: TensorAssaultObservation,
        *,
        deterministic: bool = False,
    ) -> TensorActionDecision:
        """Sample a complete action batch without leaving the model device."""
        initial_state = tuple(component.detach().clone() for component in self.state)
        logits, mean, log_std, values, next_state = self.model.forward_step(
            observation.scalar,
            observation.spatial,
            observation.critic,
            self.state,
            observation.recurrent_reset,
        )
        distribution = MixedActionDistribution(logits, mean, log_std)
        categorical, continuous = (
            distribution.mode() if deterministic else distribution.sample()
        )
        log_probabilities = distribution.log_prob(categorical, continuous)
        self.state = tuple(component.detach() for component in next_state)
        return TensorActionDecision(
            action=TensorSentryAction(
                move_direction=categorical["move_direction"],
                posture=categorical["posture"],
                reinforce=categorical["reinforce"],
                fire=categorical["fire"],
                spin_speed=continuous[:, 0],
                turret_speed=continuous[:, 1],
            ),
            categorical={name: value.detach() for name, value in categorical.items()},
            continuous=continuous.detach(),
            log_probabilities=log_probabilities.detach(),
            values=values.detach(),
            initial_state=tuple(component.detach() for component in initial_state),
            next_state=tuple(component.detach() for component in next_state),
        )

    @torch.no_grad()
    def value(
        self,
        observations: Sequence[AssaultObservation],
        state: LSTMState,
        *,
        reset: Tensor | None = None,
    ) -> Tensor:
        scalar, spatial, critic, observation_reset = self._observation_tensors(
            observations, self.device
        )
        if reset is None:
            reset = observation_reset
        _, _, _, values, _ = self.model.forward_step(
            scalar,
            spatial,
            critic,
            tuple(component.to(self.device) for component in state),
            reset.to(self.device),
        )
        return values.detach().cpu()

    @torch.no_grad()
    def value_tensors(
        self,
        observation: TensorAssaultObservation,
        state: LSTMState,
        *,
        reset: Tensor | None = None,
    ) -> Tensor:
        if reset is None:
            reset = observation.recurrent_reset
        _, _, _, values, _ = self.model.forward_step(
            observation.scalar,
            observation.spatial,
            observation.critic,
            state,
            reset,
        )
        return values.detach()

    def update(self, rollout: RecurrentRollout) -> PPOUpdateStats:
        rollout.compute_returns(
            gamma=self.config.gamma,
            gae_lambda=self.config.gae_lambda,
        )
        policy_losses: list[float] = []
        value_losses: list[float] = []
        entropies: list[float] = []
        kls: list[float] = []
        clip_fractions: list[float] = []
        gradient_norms: list[float] = []
        early_stopped = False
        for _ in range(self.config.update_epochs):
            for batch in rollout.iter_batches(
                sequence_length=self.config.sequence_length,
                minibatch_sequences=self.config.minibatch_sequences,
            ):
                logits, mean, log_std, values, _ = self.model.forward_sequence(
                    batch.scalar,
                    batch.spatial,
                    batch.critic,
                    batch.initial_state,
                    batch.episode_starts,
                )
                distribution = MixedActionDistribution(logits, mean, log_std)
                log_probabilities = distribution.log_prob(
                    batch.categorical_actions, batch.continuous_actions
                )
                categorical_entropies = distribution.categorical_entropies()
                fire_entropy = categorical_entropies["fire"]
                other_categorical_entropy = torch.stack(
                    [
                        value
                        for name, value in categorical_entropies.items()
                        if name != "fire"
                    ],
                    dim=-1,
                ).sum(dim=-1)
                categorical_entropy = (
                    other_categorical_entropy + fire_entropy
                )
                continuous_entropy = distribution.normal.entropy().sum(dim=-1)
                valid = batch.valid
                advantages = batch.advantages.clone()
                selected = advantages[valid]
                advantages[valid] = (
                    selected - selected.mean()
                ) / (selected.std(unbiased=False) + 1e-8)
                log_ratio = log_probabilities - batch.old_log_probabilities
                ratio = log_ratio.exp()
                unclipped = ratio * advantages
                clipped = torch.clamp(
                    ratio,
                    1.0 - self.config.clip_ratio,
                    1.0 + self.config.clip_ratio,
                ) * advantages
                policy_loss = -torch.minimum(unclipped, clipped)[valid].mean()
                clipped_values = batch.old_values + torch.clamp(
                    values - batch.old_values,
                    -self.config.value_clip,
                    self.config.value_clip,
                )
                value_loss = 0.5 * torch.maximum(
                    (values - batch.returns).square(),
                    (clipped_values - batch.returns).square(),
                )[valid].mean()
                categorical_entropy_mean = categorical_entropy[valid].mean()
                fire_entropy_mean = fire_entropy[valid].mean()
                other_categorical_entropy_mean = (
                    other_categorical_entropy[valid].mean()
                )
                continuous_entropy_mean = continuous_entropy[valid].mean()
                entropy_mean = categorical_entropy_mean + continuous_entropy_mean
                loss = (
                    policy_loss
                    + self.config.value_coefficient * value_loss
                    - self.config.entropy_coefficient
                    * other_categorical_entropy_mean
                    - self.config.fire_entropy_coefficient * fire_entropy_mean
                    - self.config.continuous_entropy_coefficient
                    * continuous_entropy_mean
                )
                self.optimizer.zero_grad(set_to_none=True)
                loss.backward()
                gradient_norm = torch.nn.utils.clip_grad_norm_(
                    self.model.parameters(), self.config.maximum_gradient_norm
                )
                self.optimizer.step()
                with torch.no_grad():
                    approximate_kl = ((ratio - 1.0) - log_ratio)[valid].mean()
                    clip_fraction = (
                        (torch.abs(ratio - 1.0) > self.config.clip_ratio)
                        .float()[valid]
                        .mean()
                    )
                policy_losses.append(float(policy_loss.detach().cpu()))
                value_losses.append(float(value_loss.detach().cpu()))
                entropies.append(float(entropy_mean.detach().cpu()))
                kls.append(float(approximate_kl.detach().cpu()))
                clip_fractions.append(float(clip_fraction.detach().cpu()))
                gradient_norms.append(float(gradient_norm.detach().cpu()))
                if approximate_kl > self.config.target_kl:
                    early_stopped = True
                    break
            if early_stopped:
                break
        return PPOUpdateStats(
            policy_loss=float(np.mean(policy_losses)),
            value_loss=float(np.mean(value_losses)),
            entropy=float(np.mean(entropies)),
            approximate_kl=float(np.mean(kls)),
            clip_fraction=float(np.mean(clip_fractions)),
            gradient_norm=float(np.mean(gradient_norms)),
            updates=len(policy_losses),
            early_stopped=early_stopped,
        )

    def checkpoint(self) -> dict[str, object]:
        return {
            "network_config": self.network_config,
            "ppo_config": self.config,
            "model": self.model.state_dict(),
            "optimizer": self.optimizer.state_dict(),
        }

    def load_checkpoint(self, checkpoint: dict[str, object]) -> None:
        self.model.load_state_dict(checkpoint["model"])  # type: ignore[arg-type]
        self.optimizer.load_state_dict(checkpoint["optimizer"])  # type: ignore[arg-type]


__all__ = [
    "ActionDecision",
    "PPOUpdateStats",
    "RecurrentPPO",
    "TensorActionDecision",
]
