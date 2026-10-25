"""Joint categorical and tanh-normal action distribution."""

from __future__ import annotations

from typing import Mapping

import torch
from torch import Tensor
from torch.distributions import Categorical, Normal


class MixedActionDistribution:
    def __init__(
        self,
        logits: Mapping[str, Tensor],
        continuous_mean: Tensor,
        continuous_log_std: Tensor,
    ) -> None:
        self.categorical = {
            name: Categorical(logits=value) for name, value in logits.items()
        }
        self.normal = Normal(continuous_mean, continuous_log_std.exp())

    def sample(self) -> tuple[dict[str, Tensor], Tensor]:
        categorical = {
            name: distribution.sample()
            for name, distribution in self.categorical.items()
        }
        return categorical, torch.tanh(self.normal.rsample())

    def mode(self) -> tuple[dict[str, Tensor], Tensor]:
        categorical = {
            name: distribution.logits.argmax(dim=-1)
            for name, distribution in self.categorical.items()
        }
        return categorical, torch.tanh(self.normal.mean)

    def log_prob(
        self,
        categorical_actions: Mapping[str, Tensor],
        continuous_actions: Tensor,
    ) -> Tensor:
        categorical_log_prob = torch.stack(
            [
                distribution.log_prob(categorical_actions[name].long())
                for name, distribution in self.categorical.items()
            ],
            dim=-1,
        ).sum(dim=-1)
        bounded = continuous_actions.clamp(-0.999999, 0.999999)
        raw = torch.atanh(bounded)
        continuous_log_prob = (
            self.normal.log_prob(raw)
            - torch.log(1.0 - bounded.square() + 1e-6)
        ).sum(dim=-1)
        return categorical_log_prob + continuous_log_prob

    def categorical_entropies(self) -> dict[str, Tensor]:
        return {
            name: distribution.entropy()
            for name, distribution in self.categorical.items()
        }

    def entropy_components(self) -> tuple[Tensor, Tensor]:
        categorical_entropy = torch.stack(
            list(self.categorical_entropies().values()), dim=-1
        ).sum(dim=-1)
        continuous_entropy = self.normal.entropy().sum(dim=-1)
        return categorical_entropy, continuous_entropy

    def entropy(self) -> Tensor:
        categorical_entropy, continuous_entropy = self.entropy_components()
        return categorical_entropy + continuous_entropy


__all__ = ["MixedActionDistribution"]
