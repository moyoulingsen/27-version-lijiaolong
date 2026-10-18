"""Canonical RMUC 2026 field coordinates.

The coordinate frame is the one used by ``rmuc_2026_region_dataset.sqlite``:
the playable rectangle is 28 m by 15 m, with x increasing from the red side
to the blue side and y increasing from the lower long edge to the upper one.

The dataset supplies robot trajectories, while the rulebook supplies the
layout and symmetry of the field modules.  The points below are therefore
deliberately kept in one module so the renderer, task model and navigation
cannot silently drift apart again.
"""

from __future__ import annotations


FIELD_WIDTH = 28.0
FIELD_HEIGHT = 15.0

# Dataset start-of-match medians (t <= 2 s) across the East, South and North
# region slices.  Robot ids in the simulator are local role ids (1..5, 8);
# the public dataset uses 1..6/7 and 101..107 for the two teams.
RED_START_POSITIONS = {
    1: (1.876, 8.035), # hero
    2: (1.924, 5.788), # engineer
    3: (2.949, 7.338), # infantry 3
    4: (2.756, 7.879), # infantry 4
    5: (1.421, 13.350), # aerial projection
    8: (3.559, 7.995), # sentry (dataset robot 7)
}
BLUE_START_POSITIONS = {
    1: (26.245, 7.119), # hero (dataset robot 101)
    2: (26.180, 9.392), # engineer (102)
    3: (24.985, 7.626), # infantry 3 (103)
    4: (25.286, 7.656), # infantry 4 (104)
    5: (26.684, 1.786), # aerial projection (106)
    8: (24.426, 7.429), # sentry (dataset robot 107)
}

# Building centres are anchored to the black-circle centres in
# ``rmuc2026_field_layout.png``.  The source image is 3708 x 2052 px; these
# values are the corresponding points in the simulator's 28 x 15 m frame.
RED_BASE = (1.0, 7.5)
BLUE_BASE = (27.0, 7.5)
RED_OUTPOST = (11.055, 3.894)
BLUE_OUTPOST = (16.976, 11.099)

# Main task points.  The red point in the panoramic field image is the
# opening attack position for the right/blue outpost.  The old (17, 10) BT
# point is retained as a wire-compat alias in app.py.
# Nearest 5 cm free-cell centre to the dataset sentry start.  The raw median
# is retained in RED_START_POSITIONS; this point is used as a navigation goal
# so the official 0.39 m collision footprint starts on a valid cell.
RED_HOME = (3.725, 7.975)
RED_SUPPLY_POINT = (2.10, 1.30)
BLUE_SUPPLY_POINT = (25.90, 13.70)
OUTPOST_ATTACK_POINT = (13.440, 11.140)

# Patrol points are map-cell centres chosen from the dataset's observed
# sentry routes and kept clear of the inflated occupancy grid.
CONSERVATIVE_PATROL_POINTS = ((5.0, 5.0), (9.0, 5.0), (9.0, 9.0))
AGGRESSIVE_PATROL_POINTS = ((12.0, 3.0), (14.0, 7.5), (12.3, 11.7))

# Each side has one half of the central energy mechanism.  The old 7/21 m
# positions were on the side bases and did not match either the map or the
# rulebook's central-highland placement.
RUNE_POSITIONS = {"red": (13.0, 7.5), "blue": (15.0, 7.5)}
