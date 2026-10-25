"""CLI entry point for deterministic assault evaluation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from rl.runners.evaluator import evaluate_checkpoint


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate one sentry checkpoint.")
    parser.add_argument("checkpoint", type=Path)
    parser.add_argument("--episodes", type=int, default=10)
    parser.add_argument("--seed", type=int, default=20261024)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--replay-directory", type=Path)
    parser.add_argument(
        "--stochastic",
        action="store_true",
        help="Sample actions from the learned policy instead of taking argmax actions.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = evaluate_checkpoint(
        args.checkpoint,
        episodes=args.episodes,
        seed=args.seed,
        replay_directory=args.replay_directory,
        device=args.device,
        deterministic=not args.stochastic,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
