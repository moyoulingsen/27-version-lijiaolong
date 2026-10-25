# Configuration presets

The executable configuration is represented by the typed dataclasses in
`src/rl/config/sentry_assault.py` and is embedded into every checkpoint.

Keep experiment-specific overrides in launch scripts or checkpoint metadata;
do not duplicate reward constants inside environment modules.

