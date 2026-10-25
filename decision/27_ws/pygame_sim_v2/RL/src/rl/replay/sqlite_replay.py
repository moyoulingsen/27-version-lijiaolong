"""SQLite export for RL trajectories.

The trainer writes numerical trajectory data only.  This module keeps the
export format independent from Pygame while retaining the RMUC dataset's
``matches``/``timeseries``/``events`` tables and an RL-specific frame table
that preserves the complete sentry state and action.
"""

from __future__ import annotations

import gzip
import json
import sqlite3
from pathlib import Path
from typing import Mapping


class SQLiteReplayWriter:
    """Write one RL episode to a self-contained SQLite replay."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.duration_seconds = 420.0
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.execute("PRAGMA journal_mode=OFF")
        self.connection.execute("PRAGMA synchronous=OFF")
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS matches(
                赛区 TEXT, 场次号 INT, 赛程 TEXT, 局号 INT, game_id INT,
                web_game_id INT, 红方学校 TEXT, 蓝方学校 TEXT, 胜方 TEXT,
                开始时间 TEXT, 时长秒 REAL
            );
            CREATE TABLE IF NOT EXISTS timeseries(
                赛区 TEXT, 场次号 INT, 赛程 TEXT, 局号 INT, game_id INT,
                时刻秒 REAL, robot_id INT, 机器人类型 TEXT, 阵营 TEXT,
                学校名 TEXT, 对手学校 TEXT, 当前血量 REAL, 最大血量 REAL,
                x REAL, y REAL, z REAL, 枪口朝向 REAL, 底盘功率 REAL,
                小热量 REAL, 小热量上限 REAL, 大热量 REAL, 大热量上限 REAL,
                累计17mm发弹 REAL, 累计42mm发弹 REAL, 队伍总金币 REAL,
                队伍剩余金币 REAL, 是否易伤 INT
            );
            CREATE TABLE IF NOT EXISTS events(
                赛区 TEXT, 场次号 INT, 赛程 TEXT, 局号 INT, game_id INT,
                时刻秒 REAL, 事件类型 TEXT, robot_id INT, 机器人类型 TEXT,
                阵营 TEXT, 学校名 TEXT, 目标robot_id INT, 目标类型 TEXT,
                类别 TEXT, 数值 REAL, 备注 TEXT
            );
            CREATE TABLE IF NOT EXISTS rl_episodes(
                episode INT PRIMARY KEY, seed INT, metadata_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS rl_frames(
                frame_index INTEGER PRIMARY KEY AUTOINCREMENT,
                episode INT NOT NULL, step_index INT NOT NULL,
                remaining_time REAL NOT NULL, reward REAL NOT NULL,
                action_json TEXT NOT NULL, state_json TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS ix_rl_frames_episode
                ON rl_frames(episode, frame_index);
            """
        )
        self._episode: int | None = None
        self._frame_count = 0

    def write_header(self, payload: Mapping[str, object]) -> None:
        self._episode = int(payload["episode"])
        metadata = payload.get("metadata", {})
        seed = int(payload.get("seed", 0))
        self.connection.execute(
            "INSERT OR REPLACE INTO rl_episodes(episode, seed, metadata_json) VALUES (?, ?, ?)",
            (self._episode, seed, json.dumps(metadata, ensure_ascii=False)),
        )
        started_at = str(metadata.get("started_at", "")) if isinstance(metadata, Mapping) else ""
        if isinstance(metadata, Mapping):
            self.duration_seconds = float(
                metadata.get("assault", {}).get("episode_seconds", self.duration_seconds)
            )
        self.connection.execute(
            "INSERT INTO matches VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("RL", self._episode, "RL", 1, self._episode, None,
             "RL红方", "RMUC环境", None, started_at, self.duration_seconds),
        )

    def write_frame(self, payload: Mapping[str, object]) -> None:
        if self._episode is None:
            return
        state = payload.get("state", {})
        action = payload.get("action", {})
        if not isinstance(state, Mapping) or not isinstance(action, Mapping):
            return
        sentry = state.get("sentry", {})
        structures = state.get("structures", {})
        if not isinstance(sentry, Mapping) or not isinstance(structures, Mapping):
            return
        step_index = int(state.get("step_index", self._frame_count + 1))
        remaining = float(state.get("remaining_time", 0.0))
        reward = float(payload.get("reward", 0.0))
        action_json = json.dumps(action, ensure_ascii=False, separators=(",", ":"))
        state_json = json.dumps(state, ensure_ascii=False, separators=(",", ":"))
        self.connection.execute(
            "INSERT INTO rl_frames(episode, step_index, remaining_time, reward, action_json, state_json) VALUES (?, ?, ?, ?, ?, ?)",
            (self._episode, step_index, remaining, reward, action_json, state_json),
        )
        time_seconds = max(0.0, self.duration_seconds - remaining)
        x = float(sentry.get("x", 0.0))
        y = float(sentry.get("y", 0.0))
        self.connection.execute(
            f"INSERT INTO timeseries VALUES ({', '.join('?' for _ in range(27))})",
            ("RL", self._episode, "RL", 1, self._episode, time_seconds, 8,
             "哨兵", "红", "RL红方", "RMUC环境", float(sentry.get("hp", 0.0)),
             400.0, x, y, 0.0, float(sentry.get("turret_angle", 0.0)),
             float(sentry.get("spin_speed", 0.0)), float(sentry.get("heat", 0.0)),
             100.0, 0.0, 0.0, 0.0, 0.0, None, None, 0),
        )
        self._frame_count += 1
        if self._frame_count % 256 == 0:
            self.connection.commit()

    def close(self) -> None:
        self.connection.commit()
        self.connection.close()


def export_jsonl_to_sqlite(source: Path, destination: Path) -> None:
    """Convert an existing gzip JSONL replay without starting Pygame."""
    with gzip.open(source, "rt", encoding="utf-8") as stream:
        writer = SQLiteReplayWriter(destination)
        try:
            for line in stream:
                payload = json.loads(line)
                if payload.get("type") == "header":
                    writer.write_header(payload)
                elif payload.get("type") == "frame":
                    writer.write_frame(payload)
        finally:
            writer.close()


__all__ = ["SQLiteReplayWriter", "export_jsonl_to_sqlite"]
