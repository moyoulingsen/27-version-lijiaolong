"""JSONL gzip trajectory recorder for later Pygame visualization."""

from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Mapping, TextIO

from .sqlite_replay import SQLiteReplayWriter


class ReplayRecorder:
    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)
        self._stream: TextIO | None = None
        self._path: Path | None = None
        self._sqlite: SQLiteReplayWriter | None = None

    def start(self, episode: int, *, seed: int, metadata: Mapping[str, object]) -> None:
        self.close()
        self._path = self.directory / f"episode_{episode:06d}.jsonl.gz"
        self._stream = gzip.open(self._path, "wt", encoding="utf-8")
        self._sqlite = SQLiteReplayWriter(
            self.directory / f"episode_{episode:06d}.sqlite"
        )
        self.write({"type": "header", "episode": episode, "seed": seed, "metadata": dict(metadata)})

    def write(self, payload: Mapping[str, object]) -> None:
        if self._stream is None:
            return
        self._stream.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
        self._stream.write("\n")
        if self._sqlite is not None:
            if payload.get("type") == "header":
                self._sqlite.write_header(payload)
            elif payload.get("type") == "frame":
                self._sqlite.write_frame(payload)

    def close(self) -> None:
        if self._stream is not None:
            self._stream.close()
        if self._sqlite is not None:
            self._sqlite.close()
        self._stream = None
        self._path = None
        self._sqlite = None


__all__ = ["ReplayRecorder"]
