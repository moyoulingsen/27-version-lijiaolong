from __future__ import annotations

from dataclasses import replace

import pytest
import torch

from rl.config import AssaultConfig
from rl.envs.sentry_assault import GpuSentryAssaultEnv
from rm2026_sim.field_geometry import RED_HOME


pytestmark = pytest.mark.skipif(not torch.cuda.is_available(), reason="CUDA required")


def test_curriculum_resets_are_free_and_can_finish_at_home_only() -> None:
    config = replace(
        AssaultConfig(),
        curriculum_enabled=True,
        curriculum_max_progress=1.0,
    )
    env = GpuSentryAssaultEnv(512, config, device="cuda")
    env.set_curriculum_progress(0.0)
    env.reset()
    assert bool(env._world_is_free(env.x, env.y).all().item())
    assert len(torch.unique(env.curriculum_mode)) > 1
    env.set_curriculum_progress(1.0)
    env.reset()
    assert bool((env.curriculum_mode == 0).all().item())
    assert float(torch.max(torch.abs(env.x - RED_HOME[0])).item()) == 0.0
    assert float(torch.max(torch.abs(env.y - RED_HOME[1])).item()) == 0.0


def test_v3_keeps_route_exploration_after_curriculum_matures() -> None:
    config = replace(
        AssaultConfig(reward_version=3),
        curriculum_enabled=True,
        curriculum_max_progress=1.0,
    )
    env = GpuSentryAssaultEnv(2048, config, device="cuda")
    env.set_curriculum_progress(1.0)
    env.reset()
    non_home = env.curriculum_mode != 0
    ratio = float(non_home.to(torch.float32).mean().item())
    assert ratio == pytest.approx(0.30, abs=0.04)
    assert bool((env.curriculum_mode == 4).any().item())
    assert bool((env.curriculum_mode == 5).any().item())
    upper_tunnel = env.curriculum_mode == 4
    vertical_tunnel = env.curriculum_mode == 5
    assert bool((env.outpost_hp[upper_tunnel] > 0.0).all().item())
    assert bool((env.outpost_hp[vertical_tunnel] == 0.0).all().item())
    assert bool(env.outpost_bonus_paid[vertical_tunnel].all().item())
