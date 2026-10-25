"""CNN + MLP + LSTM actor with a privileged single-agent critic."""

from __future__ import annotations

from typing import Mapping, TypeAlias

import torch
from torch import Tensor, nn

from rl.config import NetworkConfig


LSTMState: TypeAlias = tuple[Tensor, Tensor]
CATEGORICAL_ACTION_SIZES = {
    "move_direction": 9,
    "posture": 3,
    "reinforce": 2,
    "fire": 2,
}
CONTINUOUS_ACTION_SIZE = 2


class SpatialEncoder(nn.Module):
    def __init__(self, channels: int, output_size: int) -> None:
        super().__init__()
        self.network = nn.Sequential(
            nn.Conv2d(channels, 16, kernel_size=5, stride=2, padding=2),
            nn.SiLU(),
            nn.Conv2d(16, 32, kernel_size=3, stride=2, padding=1),
            nn.SiLU(),
            nn.Conv2d(32, 64, kernel_size=3, stride=2, padding=1),
            nn.SiLU(),
            nn.AdaptiveAvgPool2d((1, 1)),
            nn.Flatten(),
            nn.Linear(64, output_size),
            nn.LayerNorm(output_size),
            nn.SiLU(),
        )

    def forward(self, value: Tensor) -> Tensor:
        return self.network(value)


class SentryActorCritic(nn.Module):
    def __init__(
        self,
        scalar_size: int,
        spatial_shape: tuple[int, int, int],
        critic_size: int,
        config: NetworkConfig | None = None,
    ) -> None:
        super().__init__()
        self.config = config or NetworkConfig()
        self.scalar_size = scalar_size
        self.spatial_shape = spatial_shape
        self.critic_size = critic_size
        self.scalar_encoder = nn.Sequential(
            nn.Linear(scalar_size, self.config.scalar_hidden),
            nn.LayerNorm(self.config.scalar_hidden),
            nn.SiLU(),
            nn.Linear(self.config.scalar_hidden, self.config.scalar_hidden),
            nn.SiLU(),
        )
        self.spatial_encoder = SpatialEncoder(
            spatial_shape[0], self.config.spatial_hidden
        )
        self.fusion = nn.Sequential(
            nn.Linear(
                self.config.scalar_hidden + self.config.spatial_hidden,
                self.config.recurrent_hidden,
            ),
            nn.LayerNorm(self.config.recurrent_hidden),
            nn.SiLU(),
        )
        self.lstm = nn.LSTM(
            input_size=self.config.recurrent_hidden,
            hidden_size=self.config.recurrent_hidden,
            num_layers=self.config.lstm_layers,
            batch_first=True,
        )
        self.categorical_heads = nn.ModuleDict(
            {
                name: nn.Linear(self.config.recurrent_hidden, size)
                for name, size in CATEGORICAL_ACTION_SIZES.items()
            }
        )
        self.continuous_mean = nn.Linear(
            self.config.recurrent_hidden, CONTINUOUS_ACTION_SIZE
        )
        self.continuous_log_std = nn.Parameter(
            torch.full((CONTINUOUS_ACTION_SIZE,), -0.8)
        )
        self.critic_encoder = nn.Sequential(
            nn.Linear(critic_size, self.config.critic_hidden),
            nn.LayerNorm(self.config.critic_hidden),
            nn.SiLU(),
        )
        self.value_head = nn.Sequential(
            nn.Linear(
                self.config.recurrent_hidden + self.config.critic_hidden,
                self.config.critic_hidden,
            ),
            nn.SiLU(),
            nn.Linear(self.config.critic_hidden, 1),
        )
        self.apply(self._initialize)
        nn.init.orthogonal_(self.value_head[-1].weight, gain=1.0)
        nn.init.orthogonal_(self.continuous_mean.weight, gain=0.01)
        for head in self.categorical_heads.values():
            nn.init.orthogonal_(head.weight, gain=0.01)

    @staticmethod
    def _initialize(module: nn.Module) -> None:
        if isinstance(module, (nn.Linear, nn.Conv2d)):
            nn.init.orthogonal_(module.weight, gain=2**0.5)
            if module.bias is not None:
                nn.init.zeros_(module.bias)

    def initial_state(
        self,
        batch_size: int,
        *,
        device: torch.device | str | None = None,
    ) -> LSTMState:
        parameter = next(self.parameters())
        target_device = parameter.device if device is None else torch.device(device)
        shape = (
            self.config.lstm_layers,
            batch_size,
            self.config.recurrent_hidden,
        )
        return (
            torch.zeros(shape, dtype=parameter.dtype, device=target_device),
            torch.zeros(shape, dtype=parameter.dtype, device=target_device),
        )

    @staticmethod
    def _reset_state(state: LSTMState, reset: Tensor) -> LSTMState:
        keep = (~reset.bool()).to(dtype=state[0].dtype).view(1, -1, 1)
        return state[0] * keep, state[1] * keep

    def forward_sequence(
        self,
        scalar: Tensor,
        spatial: Tensor,
        critic: Tensor,
        state: LSTMState | None = None,
        episode_starts: Tensor | None = None,
    ) -> tuple[Mapping[str, Tensor], Tensor, Tensor, Tensor, LSTMState]:
        if scalar.ndim != 3:
            raise ValueError("scalar input must be [batch, time, features]")
        if spatial.ndim != 5:
            raise ValueError("spatial input must be [batch, time, channels, height, width]")
        if critic.ndim != 3:
            raise ValueError("critic input must be [batch, time, features]")
        batch, time, scalar_features = scalar.shape
        if scalar_features != self.scalar_size:
            raise ValueError("scalar observation size mismatch")
        if tuple(spatial.shape[2:]) != self.spatial_shape:
            raise ValueError("spatial observation shape mismatch")
        if critic.shape != (batch, time, self.critic_size):
            raise ValueError("critic observation shape mismatch")
        if state is None:
            state = self.initial_state(batch, device=scalar.device)
        if episode_starts is None:
            episode_starts = torch.zeros(
                (batch, time), dtype=torch.bool, device=scalar.device
            )
        scalar_encoded = self.scalar_encoder(scalar.reshape(batch * time, -1))
        spatial_encoded = self.spatial_encoder(
            spatial.reshape(batch * time, *self.spatial_shape)
        )
        fused = self.fusion(torch.cat((scalar_encoded, spatial_encoded), dim=-1))
        fused = fused.reshape(batch, time, -1)
        state = self._reset_state(state, episode_starts[:, 0])
        if time == 1 or not bool(episode_starts[:, 1:].any().item()):
            recurrent, state = self.lstm(fused, state)
        else:
            recurrent_outputs: list[Tensor] = []
            for index in range(time):
                if index:
                    state = self._reset_state(state, episode_starts[:, index])
                output, state = self.lstm(fused[:, index : index + 1], state)
                recurrent_outputs.append(output)
            recurrent = torch.cat(recurrent_outputs, dim=1)
        logits = {
            name: head(recurrent) for name, head in self.categorical_heads.items()
        }
        continuous_mean = self.continuous_mean(recurrent)
        continuous_log_std = self.continuous_log_std.clamp(-2.0, 0.3).expand_as(
            continuous_mean
        )
        critic_encoded = self.critic_encoder(critic.reshape(batch * time, -1))
        critic_encoded = critic_encoded.reshape(batch, time, -1)
        values = self.value_head(
            torch.cat((recurrent, critic_encoded), dim=-1)
        ).squeeze(-1)
        return logits, continuous_mean, continuous_log_std, values, state

    def forward_step(
        self,
        scalar: Tensor,
        spatial: Tensor,
        critic: Tensor,
        state: LSTMState | None = None,
        reset: Tensor | None = None,
    ) -> tuple[Mapping[str, Tensor], Tensor, Tensor, Tensor, LSTMState]:
        if reset is None:
            reset = torch.zeros(scalar.shape[0], dtype=torch.bool, device=scalar.device)
        logits, mean, log_std, values, new_state = self.forward_sequence(
            scalar.unsqueeze(1),
            spatial.unsqueeze(1),
            critic.unsqueeze(1),
            state,
            reset.unsqueeze(1),
        )
        return (
            {name: value[:, 0] for name, value in logits.items()},
            mean[:, 0],
            log_std[:, 0],
            values[:, 0],
            new_state,
        )


__all__ = [
    "CATEGORICAL_ACTION_SIZES",
    "CONTINUOUS_ACTION_SIZE",
    "LSTMState",
    "SentryActorCritic",
]
