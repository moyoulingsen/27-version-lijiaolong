from __future__ import annotations

import json
from pathlib import Path

import pytest
import torch

from rl.config import AssaultConfig
from rl.envs.sentry_assault import GpuSentryAssaultEnv
from rl.envs.sentry_assault.field import AssaultField
from rm2026_sim.app import SimulatorApp
from rm2026_sim.core import Arena
from rm2026_sim.map_regions import (
    restore_extra_geometry_payload,
    restore_geometry_payload,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _pygame_v2_collision_grid():
    payload = json.loads((PROJECT_ROOT / "map_regions.json").read_text(encoding="utf-8"))
    _, custom = restore_geometry_payload(payload)
    walls, special = restore_extra_geometry_payload(payload)
    app = SimulatorApp.__new__(SimulatorApp)
    app.arena = Arena()
    app.wall_polygons = walls
    app.special_regions = special
    app.custom_map_polygons = custom
    app.special_wall_traverse_timers = {}
    app.special_wall_traverse_active = set()
    app._rebuild_collision_grids()
    return app.collision_grid


def test_rl_grid_is_built_from_the_same_v2_geometry_as_pygame() -> None:
    field = AssaultField.load()
    pygame_grid = _pygame_v2_collision_grid()
    assert field.collision_grid.blocked == pygame_grid.blocked


def test_two_marked_tunnels_are_traversable() -> None:
    grid = AssaultField.load().collision_grid
    crossings = (
        ((11.70, 13.05), (15.55, 13.05)),
        ((18.40, 14.00), (18.40, 11.10)),
    )
    for start, end in crossings:
        assert grid.is_free_world(*start)
        assert grid.is_free_world(*end)
        assert grid.move_with_collision(start, end) == pytest.approx(end)


def test_v2_slow_regions_and_fly_slope_direction_are_loaded() -> None:
    field = AssaultField.load()
    for item in field.slow_regions:
        points = item["points"]
        centre = (
            sum(point[0] for point in points) / len(points),
            sum(point[1] for point in points) / len(points),
        )
        assert field.terrain_speed_multiplier(*centre) == pytest.approx(
            item["speed_multiplier"]
        )
    upper = field.fly_slope_polygons[0]
    centre = (
        sum(point[0] for point in upper) / len(upper),
        sum(point[1] for point in upper) / len(upper),
    )
    assert field.apply_fly_slope_one_way(
        centre,
        (centre[0] + 0.1, centre[1]),
    ) == pytest.approx(centre)
    assert field.apply_fly_slope_one_way(
        centre,
        (centre[0] - 0.1, centre[1]),
    ) == pytest.approx((centre[0] - 0.1, centre[1]))


@pytest.mark.skipif(not torch.cuda.is_available(), reason="CUDA required")
def test_reward_v2_curriculum_samples_both_tunnel_entrances() -> None:
    config = AssaultConfig(
        reward_version=2,
        curriculum_enabled=True,
        curriculum_max_progress=1.0,
    )
    env = GpuSentryAssaultEnv(4096, config, device="cuda")
    env.set_curriculum_progress(0.0)
    env.reset()
    modes = set(torch.unique(env.curriculum_mode).tolist())
    assert {4, 5}.issubset(modes)
