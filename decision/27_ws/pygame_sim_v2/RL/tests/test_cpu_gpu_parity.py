from __future__ import annotations

import pytest
import torch

from rl.envs.sentry_assault import (
    GpuSentryAssaultEnv,
    SentryAction,
    SentryAssaultEnv,
    TensorSentryAction,
)
from rm2026_sim.field_geometry import BLUE_OUTPOST


pytestmark = pytest.mark.skipif(not torch.cuda.is_available(), reason="CUDA required")


def _tensor_action(action: SentryAction) -> TensorSentryAction:
    values = (
        action.move_direction,
        action.posture,
        action.reinforce,
        action.fire,
        action.spin_speed,
        action.turret_speed,
    )
    tensors = [torch.tensor([value], device="cuda") for value in values]
    return TensorSentryAction(*tensors)


def test_valid_hit_reward_matches_cpu_reference() -> None:
    cpu = SentryAssaultEnv()
    cpu.reset(seed=2026)
    gpu = GpuSentryAssaultEnv(1, device="cuda")
    x = BLUE_OUTPOST[0] - 3.0
    y = BLUE_OUTPOST[1]
    cpu.sentry.x = x
    cpu.sentry.y = y
    cpu.sentry.turret_angle = 0.0
    gpu.x.fill_(x)
    gpu.y.fill_(y)
    gpu.turret_angle.zero_()
    action = SentryAction(0, 0, 0, 1, 0.0, 0.0)
    cpu_step = cpu.step(action)
    gpu_step = gpu.step(_tensor_action(action))
    assert cpu_step.raw_reward == pytest.approx(
        float(gpu_step.raw_reward.item()), abs=1e-3
    )
    assert cpu_step.info["objective_score"] == pytest.approx(
        float(gpu_step.objective_score.item()), abs=1e-3
    )

