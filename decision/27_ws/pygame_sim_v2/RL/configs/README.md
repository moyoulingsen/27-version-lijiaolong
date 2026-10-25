# Configuration presets

The executable configuration is represented by the typed dataclasses in
`src/rl/config/sentry_assault.py` and is embedded into every checkpoint.

Keep experiment-specific overrides in launch scripts or checkpoint metadata;
do not duplicate reward constants inside environment modules.

Reward profiles are numbered in `AssaultConfig.reward_version`:

- `1`: original guided reward used by the published V1 checkpoint.
- `2`: efficiency reward for Actor warm-start refinement on the Pygame V2 map.
- `3`: route-efficiency reward using reward-only geodesic attack fields, open
  firing-position quality, movement cost, wall/corner pressure and persistent
  route-exploration curriculum.

Never use ordinary resume to change reward versions. Use `--warm-start` so the
Actor representation is loaded while the Critic and optimizer remain fresh.
For V3 route relearning, `--reset-movement-head` additionally leaves the
movement-direction action head freshly initialized while preserving perception,
LSTM, posture, reinforcement, fire and continuous turret/spin heads.
