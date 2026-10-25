"""Small JSON helpers for training telemetry."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping


def write_json(path: Path, payload: Mapping[str, object]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def append_jsonl(path: Path, payload: Mapping[str, object]) -> None:
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
        stream.write("\n")


__all__ = ["append_jsonl", "write_json"]
