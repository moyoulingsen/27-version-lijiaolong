from __future__ import annotations

import json
from pathlib import Path


RL_ROOT = Path(__file__).resolve().parents[1]


def test_published_sentry_model_has_validation_and_replays() -> None:
    model_dir = RL_ROOT / "artifacts" / "models" / "sentry_v1"
    replay_dir = RL_ROOT / "artifacts" / "replays" / "sentry_v1"
    validation = json.loads((model_dir / "validation.json").read_text())
    assert (model_dir / "final.pt").is_file()
    assert validation["policy_mode"] == "stochastic"
    assert validation["success_rate"] == 1.0
    assert len(list(replay_dir.glob("*.sqlite"))) == validation["episodes"]

