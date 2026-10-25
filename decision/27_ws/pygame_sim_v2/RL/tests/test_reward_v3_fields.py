from __future__ import annotations

import numpy as np

from rl.config import AssaultConfig
from rl.envs.sentry_assault.field import AssaultField
from rm2026_sim.field_geometry import RED_HOME


def test_v3_tactical_fields_are_finite_and_choose_upper_attack_access() -> None:
    field = AssaultField.load()
    reward = AssaultConfig(reward_version=3).reward_v3
    tactical = field.tactical_fields(
        minimum_fire_range=reward.preferred_fire_min_range,
        maximum_fire_range=reward.preferred_fire_max_range,
        minimum_clearance=reward.preferred_fire_clearance,
    )
    assert np.isfinite(tactical.outpost_distance).all()
    assert np.isfinite(tactical.base_distance).all()
    home = field.collision_grid.world_to_cell(*RED_HOME)
    upper_attack = field.collision_grid.world_to_cell(15.5, 13.3)
    bad_base_corner = field.collision_grid.world_to_cell(27.58, 5.37)
    open_base_attack = field.collision_grid.world_to_cell(22.4, 8.8)
    assert tactical.outpost_distance[upper_attack] == 0.0
    assert tactical.outpost_distance[home] > 0.0
    assert tactical.base_distance[open_base_attack] == 0.0
    assert tactical.base_distance[bad_base_corner] > 0.0
    assert (
        tactical.wall_clearance[open_base_attack]
        > tactical.wall_clearance[bad_base_corner]
    )
