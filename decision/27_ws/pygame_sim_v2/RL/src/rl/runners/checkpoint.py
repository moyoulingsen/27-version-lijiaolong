"""Atomic checkpoint persistence."""

from __future__ import annotations

from pathlib import Path
import random
from typing import Mapping

import numpy as np
import torch

from rl.algorithms.ppo import RecurrentPPO
from rl.compat import install_legacy_checkpoint_aliases


def save_checkpoint(
    path: Path,
    *,
    learner: RecurrentPPO,
    global_step: int,
    episode: int,
    update_round: int,
    successful_episodes: int,
    elapsed_seconds: float,
    metadata: Mapping[str, object],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    torch.save(
        {
            "schema": "single-sentry-rppo-v1",
            "global_step": global_step,
            "episode": episode,
            "update_round": update_round,
            "successful_episodes": successful_episodes,
            "elapsed_seconds": elapsed_seconds,
            "metadata": dict(metadata),
            "learner": learner.checkpoint(),
            "random_state": {
                "python": random.getstate(),
                "numpy": np.random.get_state(),
                "torch": torch.get_rng_state(),
                "cuda": torch.cuda.get_rng_state_all()
                if torch.cuda.is_available()
                else None,
            },
        },
        temporary,
    )
    temporary.replace(path)


def load_checkpoint(path: Path, learner: RecurrentPPO) -> dict[str, object]:
    install_legacy_checkpoint_aliases()
    payload = torch.load(path, map_location=learner.device, weights_only=False)
    if payload.get("schema") != "single-sentry-rppo-v1":
        raise ValueError("unsupported checkpoint schema")
    learner.load_checkpoint(payload["learner"])
    random_state = payload.get("random_state")
    if isinstance(random_state, dict):
        random.setstate(random_state["python"])
        np.random.set_state(random_state["numpy"])
        torch.set_rng_state(random_state["torch"].cpu())
        cuda_state = random_state.get("cuda")
        if torch.cuda.is_available() and cuda_state is not None:
            torch.cuda.set_rng_state_all([state.cpu() for state in cuda_state])
    return payload


def load_warm_start(
    path: Path,
    learner: RecurrentPPO,
    *,
    reset_movement_head: bool = False,
) -> dict[str, object]:
    """Load only Actor-side tensors from a checkpoint into a fresh learner."""
    install_legacy_checkpoint_aliases()
    payload = torch.load(path, map_location=learner.device, weights_only=False)
    if payload.get("schema") != "single-sentry-rppo-v1":
        raise ValueError("unsupported checkpoint schema")
    learner_state = payload.get("learner")
    if not isinstance(learner_state, dict):
        raise ValueError("checkpoint learner state is invalid")
    learner.load_actor_warm_start(
        learner_state,
        reset_movement_head=reset_movement_head,
    )
    return payload


__all__ = ["load_checkpoint", "load_warm_start", "save_checkpoint"]
