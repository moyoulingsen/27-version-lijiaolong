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

# Building centres are inferred from the symmetric rulebook plan and the
# corresponding occupancy structures in rmuc2026.pgm.
RED_BASE = (1.0, 7.5)
BLUE_BASE = (27.0, 7.5)
RED_OUTPOST = (8.7, 7.5)
BLUE_OUTPOST = (19.3, 7.5)

# Main task points.  The old (17, 10) BT point is retained as a wire-compat
# alias in app.py; this is the map-valid point on the central highland from
# which the blue outpost has a clear <4 m line of sight.
# Nearest 5 cm free-cell centre to the dataset sentry start.  The raw median
# is retained in RED_START_POSITIONS; this point is used as a navigation goal
# so the official 0.39 m collision footprint starts on a valid cell.
RED_HOME = (3.725, 7.975)
RED_SUPPLY_POINT = (2.10, 1.30)
BLUE_SUPPLY_POINT = (25.90, 13.70)
OUTPOST_ATTACK_POINT = (18.225, 10.675)

# Patrol points are map-cell centres chosen from the dataset's observed
# sentry routes and kept clear of the inflated occupancy grid.
CONSERVATIVE_PATROL_POINTS = ((5.0, 5.0), (9.0, 5.0), (9.0, 9.0))
AGGRESSIVE_PATROL_POINTS = ((12.0, 3.0), (14.0, 7.5), (12.3, 11.7))

# Functional areas.  These are axis-aligned approximations of the rulebook
# modules on the 28 x 15 dataset frame; their centres are stable even where
# the physical boundary is sloped or polygonal.
RED_SUPPLY_ZONE = (0.5, 3.7, 0.2, 2.4)
BLUE_SUPPLY_ZONE = (24.3, 27.5, 12.6, 14.8)
CENTRAL_HIGHLAND = (9.2, 18.8, 4.4, 10.6)
RED_TRAPEZOID_HIGHLAND = (4.8, 8.3, 3.5, 6.4)
BLUE_TRAPEZOID_HIGHLAND = (19.7, 23.2, 8.6, 11.5)
# Road gain cards sit near the lower red / upper blue field edges.  These
# tighter rectangles cover the card pair and the dataset's activation cluster,
# rather than painting the surrounding roadway as one large gain area.
RED_ROAD = (7.7, 8.8, 1.8, 3.3)
BLUE_ROAD = (19.2, 20.3, 11.7, 13.2)
# Approximate module-card centers, ordered low-to-high for each approach.
# The high-card coordinates align with dataset road-gain event clusters.
RED_ROAD_CROSSING_CARDS = ((8.25, 2.0), (8.25, 2.5))
BLUE_ROAD_CROSSING_CARDS = ((19.75, 13.0), (19.75, 12.5))
RED_TERRAIN_HIGHLAND = (6.0, 7.8, 5.8, 7.6)
BLUE_TERRAIN_HIGHLAND = (20.2, 22.0, 7.4, 9.2)
RED_FLY_SLOPE = (13.0, 16.3, 0.0, 1.2)
BLUE_FLY_SLOPE = (12.0, 15.3, 13.8, 15.0)
RED_TUNNEL = (2.8, 4.5, 9.8, 11.7)
BLUE_TUNNEL = (23.5, 25.2, 3.3, 5.2)
RED_BASE_GAIN = (1.8, 3.4, 6.3, 8.7)
BLUE_BASE_GAIN = (24.6, 26.2, 6.3, 8.7)
RED_OUTPOST_GAIN = (7.75, 9.65, 6.4, 8.6)
BLUE_OUTPOST_GAIN = (18.35, 20.25, 6.4, 8.6)
# Engineer locations at successful assembly events: red clusters around
# (13.1, 8.3), blue around (15.0, 6.8).  These narrow regions match the two
# technology-core stations below the energy mechanism in the rulebook plan.
RED_ASSEMBLY = (12.7, 13.5, 8.0, 8.9)
BLUE_ASSEMBLY = (14.6, 15.4, 6.4, 7.3)
# Fortress gain pads follow the hexagons in rulebook figures 4-5 and 5-24.
RED_FORT_POLYGON = (
    (5.35, 7.5),
    (6.05, 8.42),
    (7.25, 8.42),
    (7.9, 7.5),
    (7.25, 6.48),
    (6.05, 6.48),
)
BLUE_FORT_POLYGON = (
    (22.65, 7.5),
    (21.95, 8.42),
    (20.75, 8.42),
    (20.1, 7.5),
    (20.75, 6.48),
    (21.95, 6.48),
)
RED_FORT = (5.35, 7.9, 6.48, 8.42)
BLUE_FORT = (20.1, 22.65, 6.48, 8.42)

# Each side has one half of the central energy mechanism.  The old 7/21 m
# positions were on the side bases and did not match either the map or the
# rulebook's central-highland placement.
RUNE_POSITIONS = {"red": (13.0, 7.5), "blue": (15.0, 7.5)}
