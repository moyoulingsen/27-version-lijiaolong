"""Print completed-episode scores and optionally follow new results."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import time


def format_episode(item: dict[str, object]) -> str:
    success = "成功" if bool(item.get("success")) else "未成功"
    return (
        f"episode={int(item['episode'])} "
        f"总奖励={float(item.get('raw_score', 0.0)):+.3f} "
        f"引导分={float(item.get('shaping_score', 0.0)):+.3f} "
        f"建筑分={float(item.get('objective_score', 0.0)):+.1f} "
        f"剩余时间={float(item.get('remaining_time', 0.0)):.1f}s "
        f"{success} step={int(item.get('global_step', 0))}"
    )


def parse_line(line: str) -> dict[str, object] | None:
    try:
        item = json.loads(line)
    except json.JSONDecodeError:
        return None
    return item if item.get("type") == "episode" else None


def main() -> None:
    parser = argparse.ArgumentParser(description="Monitor RL episode scores.")
    parser.add_argument("run_directory", type=Path)
    parser.add_argument("--last", type=int, default=10)
    parser.add_argument("--no-follow", action="store_true")
    args = parser.parse_args()
    metrics_path = args.run_directory / "metrics.jsonl"
    if not metrics_path.is_file():
        raise SystemExit(f"metrics file does not exist: {metrics_path}")

    existing = metrics_path.read_text(encoding="utf-8").splitlines()
    episodes = [item for line in existing if (item := parse_line(line)) is not None]
    for item in episodes[-max(0, args.last):]:
        print(format_episode(item), flush=True)
    if args.no_follow:
        return

    with metrics_path.open("r", encoding="utf-8") as stream:
        stream.seek(0, 2)
        while True:
            line = stream.readline()
            if not line:
                time.sleep(0.25)
                continue
            item = parse_line(line)
            if item is not None:
                print(format_episode(item), flush=True)


if __name__ == "__main__":
    main()
