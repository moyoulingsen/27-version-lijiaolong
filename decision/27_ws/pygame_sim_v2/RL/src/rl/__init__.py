"""End-to-end single-sentry reinforcement-learning package."""

from pathlib import Path
import sys


# The RL package is intentionally kept inside the simulator repository and
# reuses its authoritative ``rm2026_sim`` rules. Console-script entry points
# start from the virtualenv's ``bin`` directory, so add the repository root
# explicitly instead of requiring users to export PYTHONPATH.
PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

__version__ = "1.1.0"
