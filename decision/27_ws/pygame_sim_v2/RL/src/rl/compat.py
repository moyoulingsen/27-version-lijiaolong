"""Compatibility helpers for checkpoints created before the src-layout move."""

from __future__ import annotations

import importlib
import sys


def install_legacy_checkpoint_aliases() -> None:
    """Expose the old config module names used by existing torch pickles."""
    root_package = importlib.import_module("rl")
    config_package = importlib.import_module("rl.config")
    sentry_config = importlib.import_module("rl.config.sentry_assault")
    sys.modules.setdefault("RL", root_package)
    sys.modules.setdefault("RL.config", config_package)
    sys.modules.setdefault("RL.config.sentry_assault", sentry_config)


__all__ = ["install_legacy_checkpoint_aliases"]

