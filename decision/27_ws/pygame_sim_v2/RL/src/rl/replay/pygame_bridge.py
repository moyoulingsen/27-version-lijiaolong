"""Read compressed RL trajectories for a future Pygame renderer adapter."""

from __future__ import annotations

import gzip
import json
import sqlite3
from pathlib import Path
from typing import Iterator


def iter_replay(path: Path) -> Iterator[dict[str, object]]:
    if path.suffix == ".sqlite":
        yield from _iter_sqlite_replay(path)
        return
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        for line in stream:
            yield json.loads(line)


def _iter_sqlite_replay(path: Path) -> Iterator[dict[str, object]]:
    connection = sqlite3.connect(path)
    try:
        row = connection.execute(
            "SELECT episode, seed, metadata_json FROM rl_episodes ORDER BY episode LIMIT 1"
        ).fetchone()
        if row is not None:
            yield {
                "type": "header",
                "episode": int(row[0]),
                "seed": int(row[1]),
                "metadata": json.loads(row[2]),
            }
        rows = connection.execute(
            "SELECT reward, action_json, state_json FROM rl_frames ORDER BY frame_index"
        )
        for reward, action_json, state_json in rows:
            yield {
                "type": "frame",
                "reward": float(reward),
                "action": json.loads(action_json),
                "state": json.loads(state_json),
            }
    finally:
        connection.close()


__all__ = ["iter_replay"]
