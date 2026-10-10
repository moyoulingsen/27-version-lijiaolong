"""Minimal binary-PGM loader for the checked-in RMUC map asset."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PgmImage:
    width: int
    height: int
    pixels: bytes


def load_p5_pgm(path: Path) -> PgmImage:
    data = path.read_bytes()
    index = 0

    def next_token() -> bytes:
        nonlocal index
        while index < len(data):
            if data[index] == ord("#"):
                newline = data.find(b"\n", index)
                if newline < 0:
                    raise ValueError(f"Unterminated PGM comment: {path}")
                index = newline + 1
            elif chr(data[index]).isspace():
                index += 1
            else:
                break
        start = index
        while index < len(data) and not chr(data[index]).isspace() and data[index] != ord("#"):
            index += 1
        if start == index:
            raise ValueError(f"Missing PGM header token: {path}")
        return data[start:index]

    if next_token() != b"P5":
        raise ValueError(f"Only binary P5 PGM maps are supported: {path}")
    width = int(next_token())
    height = int(next_token())
    maximum = int(next_token())
    if maximum != 255:
        raise ValueError(f"Expected an 8-bit PGM map, got max value {maximum}")
    if index >= len(data) or not chr(data[index]).isspace():
        raise ValueError(f"Missing PGM pixel separator: {path}")
    if data[index : index + 2] == b"\r\n":
        index += 2
    else:
        index += 1

    expected_size = width * height
    pixels = data[index : index + expected_size]
    if len(pixels) != expected_size:
        raise ValueError(
            f"PGM pixel data has {len(pixels)} bytes, expected {expected_size}: {path}"
        )
    return PgmImage(width, height, pixels)
