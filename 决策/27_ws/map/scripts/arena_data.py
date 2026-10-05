#!/usr/bin/env python3
"""Read one static opening snapshot from the supplied RMUC SQLite dataset."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3


@dataclass(frozen=True)
class Entity:
    target_id: int
    robot_id: int
    robot_type: str
    team: str
    hp: int
    max_hp: int
    x: float
    y: float


@dataclass(frozen=True)
class ArenaSnapshot:
    game_id: int
    match_name: str
    red_school: str
    blue_school: str
    own_base_hp: int
    own_outpost_hp: int
    enemy_base_hp: int
    enemy_outpost_hp: int
    enemies: tuple[Entity, ...]


TARGET_BY_TYPE = {
    "英雄": 1,
    "工程": 2,
    "步兵3": 3,
    "步兵4": 4,
    "空中": 5,
    "哨兵": 8,
}


def _bounded_hp(value, maximum):
    return max(0, min(int(round(value or 0)), maximum))


def load_snapshot(database_path, requested_game_id=0):
    path = Path(database_path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"RMUC dataset does not exist: {path}")

    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        cursor = connection.cursor()
        if requested_game_id:
            game_id = int(requested_game_id)
        else:
            row = cursor.execute("SELECT MIN(game_id) FROM matches").fetchone()
            game_id = int(row[0])

        match = cursor.execute(
            "SELECT 赛程, 红方学校, 蓝方学校 FROM matches WHERE game_id=?",
            (game_id,),
        ).fetchone()
        if match is None:
            raise ValueError(f"game_id {game_id} is absent from matches")

        first_time = cursor.execute(
            "SELECT MIN(时刻秒) FROM timeseries WHERE game_id=?", (game_id,)
        ).fetchone()[0]
        if first_time is None:
            raise ValueError(f"game_id {game_id} has no timeseries rows")

        rows = cursor.execute(
            "SELECT robot_id, 机器人类型, 阵营, 当前血量, 最大血量, x, y "
            "FROM timeseries WHERE game_id=? AND 时刻秒=?",
            (game_id, first_time),
        ).fetchall()

        building_hp = {}
        enemies = []
        for robot_id, robot_type, team, hp, max_hp, x, y in rows:
            if robot_type in ("基地", "前哨站"):
                building_hp[(team, robot_type)] = int(round(hp or 0))
                continue
            if team != "蓝" or robot_type not in TARGET_BY_TYPE:
                continue
            if x is None or y is None or not (0.0 <= x <= 28.0 and 0.0 <= y <= 15.0):
                continue
            enemies.append(
                Entity(
                    target_id=TARGET_BY_TYPE[robot_type],
                    robot_id=int(robot_id),
                    robot_type=robot_type,
                    team=team,
                    hp=int(round(hp or 0)),
                    max_hp=int(round(max_hp or 0)),
                    x=float(x),
                    y=float(y),
                )
            )

        if not enemies:
            raise ValueError(f"game_id {game_id} has no usable blue robot snapshot")
        enemies.sort(key=lambda entity: entity.target_id)

        # The dataset deliberately stores building xyz as zero. Placement is supplied
        # by the mirrored 28 m x 15 m arena layout; HP still comes from this snapshot.
        return ArenaSnapshot(
            game_id=game_id,
            match_name=str(match[0]),
            red_school=str(match[1]),
            blue_school=str(match[2]),
            own_base_hp=_bounded_hp(building_hp.get(("红", "基地"), 5000), 5000),
            own_outpost_hp=_bounded_hp(building_hp.get(("红", "前哨站"), 1000), 1000),
            enemy_base_hp=_bounded_hp(building_hp.get(("蓝", "基地"), 5000), 5000),
            enemy_outpost_hp=_bounded_hp(building_hp.get(("蓝", "前哨站"), 1000), 1000),
            enemies=tuple(enemies),
        )
    finally:
        connection.close()
