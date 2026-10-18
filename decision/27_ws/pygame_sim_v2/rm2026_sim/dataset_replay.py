"""Read-only RMUC 2026 SQLite access and deterministic replay state.

The simulator uses a small hand-authored scenario for decision validation.  A
replay must use the dataset as its source of truth instead: ``matches`` picks
the game, ``timeseries`` supplies robot state, and ``events`` supplies events
that do not have a per-second state row.  This module keeps that boundary
explicit and deliberately does not mutate the source database.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from dataclasses import dataclass, replace
import math
from pathlib import Path
import re
import sqlite3
from typing import Iterable, Iterator


DEFAULT_DATASET_PATH = (
    Path(__file__).resolve().parents[3] / "data" / "rmuc_2026_region_dataset.sqlite"
)

# Region-dataset ids are intentionally not the same as the local simulator
# ids.  Buildings use the same local slots as the existing property panels:
# outpost=6 and base=7; local sentry=8 and aerial=5.
DATASET_ENTITY_ID_MAP = {
    "red": {1: 1, 2: 2, 3: 3, 4: 4, 6: 5, 7: 8, 10: 7, 11: 6},
    "blue": {101: 1, 102: 2, 103: 3, 104: 4, 106: 5, 107: 8, 110: 7, 111: 6},
}


def dataset_local_entity_id(team: str, dataset_id: int) -> int | None:
    """Return the local robot/building slot for a dataset entity id."""
    normalized = "red" if team in ("red", "红") else "blue"
    return DATASET_ENTITY_ID_MAP[normalized].get(int(dataset_id))

MATCH_COLUMNS = (
    "赛区",
    "场次号",
    "赛程",
    "局号",
    "game_id",
    "web_game_id",
    "红方学校",
    "蓝方学校",
    "胜方",
    "开始时间",
    "时长秒",
)
TIMESERIES_COLUMNS = (
    "赛区",
    "场次号",
    "赛程",
    "局号",
    "game_id",
    "时刻秒",
    "robot_id",
    "机器人类型",
    "阵营",
    "学校名",
    "对手学校",
    "当前血量",
    "最大血量",
    "x",
    "y",
    "z",
    "枪口朝向",
    "底盘功率",
    "小热量",
    "小热量上限",
    "大热量",
    "大热量上限",
    "累计17mm发弹",
    "累计42mm发弹",
    "队伍总金币",
    "队伍剩余金币",
    "是否易伤",
)
EVENT_COLUMNS = (
    "赛区",
    "场次号",
    "赛程",
    "局号",
    "game_id",
    "时刻秒",
    "事件类型",
    "robot_id",
    "机器人类型",
    "阵营",
    "学校名",
    "目标robot_id",
    "目标类型",
    "类别",
    "数值",
    "备注",
)


class DatasetError(RuntimeError):
    """Raised when a dataset cannot satisfy the replay contract."""


def _optional_float(value: object) -> float | None:
    return None if value is None else float(value)


def _optional_int(value: object) -> int | None:
    return None if value is None else int(value)


@dataclass(frozen=True)
class MatchRecord:
    region: str
    match_number: int
    schedule: str
    round_number: int
    game_id: int
    web_game_id: int | None
    red_school: str
    blue_school: str
    winner: str | None
    started_at: str | None
    duration_seconds: float

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "MatchRecord":
        return cls(
            region=str(row["赛区"]),
            match_number=int(row["场次号"]),
            schedule=str(row["赛程"]),
            round_number=int(row["局号"]),
            game_id=int(row["game_id"]),
            web_game_id=_optional_int(row["web_game_id"]),
            red_school=str(row["红方学校"]),
            blue_school=str(row["蓝方学校"]),
            winner=None if row["胜方"] is None else str(row["胜方"]),
            started_at=None if row["开始时间"] is None else str(row["开始时间"]),
            duration_seconds=float(row["时长秒"] or 0.0),
        )

    @property
    def title(self) -> str:
        winner = self.winner or "未知"
        return (
            f"{self.region} 第{self.match_number}场 / 第{self.round_number}局 "
            f"({self.red_school} vs {self.blue_school}) 胜方:{winner}"
        )


@dataclass(frozen=True)
class RobotSample:
    time_seconds: float
    robot_id: int
    robot_type: str
    team: str
    school: str
    opponent_school: str
    hp: float | None
    max_hp: float | None
    x: float | None
    y: float | None
    z: float | None
    heading_degrees: float | None
    chassis_power: float | None
    small_heat: float | None
    small_heat_limit: float | None
    large_heat: float | None
    large_heat_limit: float | None
    shots_17mm: float | None
    shots_42mm: float | None
    team_coins: float | None
    remaining_coins: float | None
    vulnerable: bool

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "RobotSample":
        return cls(
            time_seconds=float(row["时刻秒"]),
            robot_id=int(row["robot_id"]),
            robot_type=str(row["机器人类型"]),
            team=str(row["阵营"]),
            school=str(row["学校名"] or ""),
            opponent_school=str(row["对手学校"] or ""),
            hp=_optional_float(row["当前血量"]),
            max_hp=_optional_float(row["最大血量"]),
            x=_optional_float(row["x"]),
            y=_optional_float(row["y"]),
            z=_optional_float(row["z"]),
            heading_degrees=_optional_float(row["枪口朝向"]),
            chassis_power=_optional_float(row["底盘功率"]),
            small_heat=_optional_float(row["小热量"]),
            small_heat_limit=_optional_float(row["小热量上限"]),
            large_heat=_optional_float(row["大热量"]),
            large_heat_limit=_optional_float(row["大热量上限"]),
            shots_17mm=_optional_float(row["累计17mm发弹"]),
            shots_42mm=_optional_float(row["累计42mm发弹"]),
            team_coins=_optional_float(row["队伍总金币"]),
            remaining_coins=_optional_float(row["队伍剩余金币"]),
            vulnerable=bool(int(row["是否易伤"] or 0)),
        )


@dataclass(frozen=True)
class ReplayEvent:
    time_seconds: float
    event_type: str
    robot_id: int | None
    robot_type: str
    team: str
    school: str
    target_robot_id: int | None
    target_type: str
    category: str
    value: float | None
    note: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "ReplayEvent":
        return cls(
            time_seconds=float(row["时刻秒"]),
            event_type=str(row["事件类型"]),
            robot_id=_optional_int(row["robot_id"]),
            robot_type=str(row["机器人类型"] or ""),
            team=str(row["阵营"] or ""),
            school=str(row["学校名"] or ""),
            target_robot_id=_optional_int(row["目标robot_id"]),
            target_type=str(row["目标类型"] or ""),
            category=str(row["类别"] or ""),
            value=_optional_float(row["数值"]),
            note=str(row["备注"] or ""),
        )


@dataclass(frozen=True)
class ReplayFrame:
    time_seconds: float
    samples: tuple[RobotSample, ...]
    events: tuple[ReplayEvent, ...]

    def by_robot(self) -> dict[int, RobotSample]:
        return {sample.robot_id: sample for sample in self.samples}


@dataclass(frozen=True)
class InferredEconomyAction:
    """A rulebook-constrained economy action inferred from state deltas.

    The dataset exposes team coin totals and balances, but not a transaction
    id.  Consequently an action is a candidate, never an authoritative event;
    ``confidence`` and ``evidence`` make that ambiguity visible to the UI.
    """

    time_seconds: float
    team: str
    action: str
    cost: float
    confidence: float
    evidence: str


class EconomicInference:
    """Infer economy behaviour while replay time advances.

    ``timeseries`` remains the source of truth.  This class only consumes
    snapshots and emits annotations for the replay panel.  Costs and periodic
    income follow rulebook table 5-5/5-6 and sections 5.2.2/5.3.2.
    """

    PERIODIC_INCOME = ((61.0, 50.0), (121.0, 50.0), (181.0, 50.0),
                       (241.0, 50.0), (301.0, 50.0), (361.0, 150.0))
    LOCAL_17MM = (10.0, 10.0, 1000.0)    # cost, shots, team cap
    REMOTE_17MM = (150.0, 100.0, 1000.0)
    LOCAL_42MM = (10.0, 1.0, 100.0)
    REMOTE_42MM = (150.0, 10.0, 100.0)
    AMMO_COSTS = (10.0, 150.0)
    AIR_SUPPORT_COST_PER_SECOND = 1.0
    INITIAL_AIR_SUPPORT_SECONDS = 30.0
    AIR_SUPPORT_BONUS_PER_MINUTE = 20.0
    AUTO_SENTRY_COMMAND_COST = 50.0
    REMOTE_HEAL_DELAY = 6.0

    def __init__(self) -> None:
        self._previous: dict[str, tuple[float, float, float]] = {}
        self._previous_samples: dict[int, RobotSample] = {}
        self._scheduled_seen: set[tuple[str, float]] = set()
        self._supply_seen: set[tuple[str, int]] = set()
        self._pending_costs: list[tuple[str, float, float, str]] = []
        self._air_support_active: set[str] = set()
        self._assembly_seen: set[str] = set()
        self._assembly_counts: dict[str, dict[int, int]] = {"red": {}, "blue": {}}
        self._assembly_bonus_per_10: dict[str, float] = {"red": 0.0, "blue": 0.0}
        self._assembly_last_success: dict[str, float] = {"red": -math.inf, "blue": -math.inf}
        self._ammo_exchange_credited: dict[str, dict[str, float]] = {
            "red": {"17mm": 0.0, "42mm": 0.0},
            "blue": {"17mm": 0.0, "42mm": 0.0},
        }
        self._radar_countermeasures: dict[str, int] = {"red": 0, "blue": 0}
        self.actions: list[InferredEconomyAction] = []

    @staticmethod
    def _team_label(team: str) -> str:
        return "red" if team in ("red", "红") else "blue"

    @staticmethod
    def _team_samples(frame: ReplayFrame, team: str) -> tuple[RobotSample, ...]:
        return tuple(sample for sample in frame.samples if sample.team in (team, "红" if team == "red" else "蓝"))

    @staticmethod
    def _close(value: float, expected: float, tolerance: float = 2.0) -> bool:
        return abs(value - expected) <= tolerance

    @staticmethod
    def _remote_heal_eligible(sample: RobotSample) -> bool:
        return sample.robot_type == "英雄" or sample.robot_type == "哨兵" or sample.robot_type.startswith("步兵")

    @staticmethod
    def _revive_costs(elapsed_seconds: float) -> tuple[float, ...]:
        base = 80.0 * math.ceil(max(0.0, elapsed_seconds) / 60.0)
        return tuple(base + level * 20.0 for level in range(1, 11))

    def _append(self, frame: ReplayFrame, team: str, action: str, cost: float,
                confidence: float, evidence: str) -> InferredEconomyAction:
        result = InferredEconomyAction(
            frame.time_seconds, self._team_label(team), action, float(cost),
            max(0.0, min(1.0, float(confidence))), evidence,
        )
        self.actions.append(result)
        return result

    def reset(self) -> None:
        self._previous.clear()
        self._previous_samples.clear()
        self._scheduled_seen.clear()
        self._supply_seen.clear()
        self._pending_costs.clear()
        self._air_support_active.clear()
        self._assembly_seen.clear()
        self._assembly_counts = {"red": {}, "blue": {}}
        self._assembly_bonus_per_10 = {"red": 0.0, "blue": 0.0}
        self._assembly_last_success = {"red": -math.inf, "blue": -math.inf}
        self._ammo_exchange_credited = {
            "red": {"17mm": 0.0, "42mm": 0.0},
            "blue": {"17mm": 0.0, "42mm": 0.0},
        }
        self._radar_countermeasures = {"red": 0, "blue": 0}
        self.actions.clear()

    def _ammo_exchange_room(self, team: str, caliber: str, amount: float) -> bool:
        cap = self.REMOTE_17MM[2] if caliber == "17mm" else self.REMOTE_42MM[2]
        return self._ammo_exchange_credited[team][caliber] + amount <= cap

    def _record_ammo_exchange(self, team: str, caliber: str, amount: float) -> float:
        self._ammo_exchange_credited[team][caliber] += amount
        cap = self.REMOTE_17MM[2] if caliber == "17mm" else self.REMOTE_42MM[2]
        return cap - self._ammo_exchange_credited[team][caliber]

    def observe(
        self,
        frame: ReplayFrame,
        events: Iterable[ReplayEvent] = (),
    ) -> tuple[InferredEconomyAction, ...]:
        """Consume one chronological frame and return newly inferred actions."""
        new_actions: list[InferredEconomyAction] = []
        events = tuple(events)
        for raw_team in ("red", "blue"):
            air_support_candidate = False
            samples = self._team_samples(frame, raw_team)
            for event in events:
                if (event.event_type == "雷达反制UAV"
                        and event.team in (raw_team, "红" if raw_team == "red" else "蓝")):
                    self._radar_countermeasures[raw_team] += 1
                    new_actions.append(self._append(
                        frame, raw_team, "雷达反制记录", 0.0, 1.0,
                        f"该方空中单位累计被反制第{self._radar_countermeasures[raw_team]}次；第4次起可按立即复活费用两倍兑换解除并呼叫支援",
                    ))
            assembly_events = tuple(
                event for event in events
                if event.event_type == "装配成功"
                and event.team in (raw_team, "红" if raw_team == "red" else "蓝")
            )
            for event in assembly_events:
                match_level = re.search(r"\d+", event.category)
                if match_level is None:
                    continue
                difficulty = int(match_level.group())
                if difficulty not in (1, 2, 3, 4):
                    continue
                counts = self._assembly_counts[raw_team]
                first = counts.get(difficulty, 0) == 0
                counts[difficulty] = counts.get(difficulty, 0) + 1
                bonus = {
                    1: 50.0 if first else 5.0,
                    2: 25.0 if first else 10.0,
                    3: 25.0 if first else 15.0,
                    4: 50.0 if first else 0.0,
                }[difficulty]
                self._assembly_bonus_per_10[raw_team] += bonus
                self._assembly_last_success[raw_team] = event.time_seconds
                self._assembly_seen.add(raw_team)
                new_actions.append(self._append(
                    frame, raw_team, f"装配成功·等级{difficulty}", 0.0, 0.88,
                    f"规则书5.3.3收益规则；本次预计每10秒新增{bonus:g}金币，累计{self._assembly_bonus_per_10[raw_team]:g}",
                ))
            health_rise = any(
                (old := self._previous_samples.get(sample.robot_id)) is not None
                and old.hp is not None and sample.hp is not None
                and sample.hp - old.hp >= 5.0
                for sample in samples
            )
            if health_rise:
                confirmed: list[tuple[str, float, float, str]] = []
                for pending in self._pending_costs:
                    pending_team, pending_time, pending_cost, pending_action = pending
                    age = frame.time_seconds - pending_time
                    eligible_recovery = any(
                        (old := self._previous_samples.get(sample.robot_id)) is not None
                        and old.hp is not None and sample.hp is not None
                        and sample.hp - old.hp >= 5.0
                        and (pending_action.startswith("立即复活") or self._remote_heal_eligible(sample))
                        for sample in samples
                    )
                    if pending_team == raw_team and 5.0 <= age <= 8.0 and eligible_recovery:
                        new_actions.append(self._append(
                            frame, raw_team, f"{pending_action}（延迟确认）", pending_cost,
                            0.88 if pending_action.startswith("立即复活") else 0.72,
                            f"支出发生于{pending_time:.1f}s；约{age:.1f}s后观察到血量恢复，数据无交易机器人ID",
                        ))
                        confirmed.append(pending)
                for pending in confirmed:
                    self._pending_costs.remove(pending)
            self._pending_costs = [
                pending for pending in self._pending_costs
                if frame.time_seconds - pending[1] <= 8.0
            ]
            coin_rows = [sample for sample in samples
                         if sample.team_coins is not None and sample.remaining_coins is not None]
            if coin_rows:
                # Every robot carries the same team balance.  Taking the first
                # row avoids multiplying a transaction by robot count.
                current_total = float(coin_rows[0].team_coins)
                current_remaining = float(coin_rows[0].remaining_coins)
                previous = self._previous.get(raw_team)
                if previous is not None:
                    previous_time, previous_total, previous_remaining = previous
                    income = max(0.0, current_total - previous_total)
                    spend = previous_remaining + income - current_remaining
                    periodic_income = any(abs(frame.time_seconds - tick) <= 1e-6 for tick, _ in self.PERIODIC_INCOME)
                    assembly_elapsed = frame.time_seconds - self._assembly_last_success[raw_team]
                    bonus_per_10 = self._assembly_bonus_per_10[raw_team]
                    is_assembly_bonus = (
                        raw_team in self._assembly_seen
                        and bonus_per_10 > 0.0
                        and assembly_elapsed >= 8.0
                        and abs(income - bonus_per_10) <= 2.0
                    )
                    if (income >= 10.0 and not periodic_income
                            and abs(income - round(income)) <= 1e-6):
                        new_actions.append(self._append(
                            frame, raw_team,
                            "装配/科技核心周期收入" if is_assembly_bonus else "未分类队伍收入",
                            income, 0.78 if is_assembly_bonus else 0.25,
                            f"总金币增加{income:g}且非规则书定时节点；"
                            + ("金额符合已观察装配等级的每10秒累计奖励" if is_assembly_bonus
                               else "无装配成功事件可对应，保留为未分类收入"),
                        ))
                    if spend >= 1.0:
                        # A balance can move in one-second jumps.  Match the
                        # exact rulebook prices first, then retain ambiguity.
                        hp_rise = any(
                            (old := self._previous_samples.get(sample.robot_id)) is not None
                            and old.hp is not None and sample.hp is not None
                            and sample.hp - old.hp >= 20.0
                            and self._remote_heal_eligible(sample)
                            for sample in samples
                        )
                        death_recovery = any(
                            (old := self._previous_samples.get(sample.robot_id)) is not None
                            and (old.hp or 0.0) <= 0.0 and (sample.hp or 0.0) > 0.0
                            for sample in samples
                        )
                        elapsed = frame.time_seconds
                        has_sentry = any(sample.robot_type == "哨兵" for sample in samples)
                        auto_command_fee = self.AUTO_SENTRY_COMMAND_COST if has_sentry else 0.0
                        matched_action = False
                        aerial_present = any(sample.robot_type == "空中" for sample in samples)
                        radar_release_costs = tuple(
                            2.0 * cost for cost in self._revive_costs(elapsed)
                        )
                        if (aerial_present and self._radar_countermeasures[raw_team] >= 4
                                and any(self._close(spend, cost, 3.0) for cost in radar_release_costs)):
                            matched_cost = min(radar_release_costs, key=lambda value: abs(value - spend))
                            new_actions.append(self._append(
                                frame, raw_team, "反制后解除并呼叫空中支援候选", spend, 0.62,
                                f"已有{self._radar_countermeasures[raw_team]}次反制；支出符合地面机器人立即复活费用两倍≈{matched_cost:g}，但未记录操作确认",
                            ))
                            matched_action = True
                        if death_recovery:
                            revive_costs = self._revive_costs(elapsed)
                            auto_costs = tuple(cost + auto_command_fee for cost in revive_costs) if auto_command_fee else ()
                            candidates = revive_costs + auto_costs
                            cost = min(candidates, key=lambda value: abs(value - spend))
                            if not matched_action and self._close(spend, cost, 3.0):
                                command_fee = auto_command_fee > 0 and cost in auto_costs
                                new_actions.append(self._append(
                                    frame, raw_team,
                                    "立即复活+自动哨兵指令费候选" if command_fee else "立即复活",
                                    spend, 0.78 if command_fee else 0.92,
                                    f"死亡后血量恢复；支出符合ROUNDUP(已用时/60)×80+等级×20"
                                    + ("再加50金币自动哨兵指令费（模式未记录）" if command_fee else ""),
                                ))
                                matched_action = True
                        elif hp_rise:
                            cost = 50.0 + math.ceil(elapsed / 60.0) * 20.0
                            candidates = (cost, cost + auto_command_fee) if auto_command_fee else (cost,)
                            matched_cost = min(candidates, key=lambda value: abs(value - spend))
                            if not matched_action and self._close(spend, matched_cost, 3.0):
                                command_fee = auto_command_fee > 0 and matched_cost > cost
                                new_actions.append(self._append(
                                    frame, raw_team,
                                    "远程回血+自动哨兵指令费候选" if command_fee else "远程回血",
                                    spend, 0.70 if command_fee else 0.82,
                                    f"非死亡且可远程回血单位血量上升；规则书延迟{self.REMOTE_HEAL_DELAY:g}s"
                                    + ("；另含自动哨兵指令费候选50金币" if command_fee else ""),
                                ))
                                matched_action = True
                        shot_delta_17 = sum(
                            max(0.0, (sample.shots_17mm or 0.0) - (old.shots_17mm or 0.0))
                            for sample in samples
                            if sample.robot_type in ("哨兵", "空中") or sample.robot_type.startswith("步兵")
                            if (old := self._previous_samples.get(sample.robot_id)) is not None
                            and sample.shots_17mm is not None and old.shots_17mm is not None
                        )
                        shot_delta_42 = sum(
                            max(0.0, (sample.shots_42mm or 0.0) - (old.shots_42mm or 0.0))
                            for sample in samples
                            if sample.robot_type == "英雄"
                            if (old := self._previous_samples.get(sample.robot_id)) is not None
                            and sample.shots_42mm is not None and old.shots_42mm is not None
                        )
                        if not matched_action:
                            dead_waiting = any(
                                (old := self._previous_samples.get(sample.robot_id)) is not None
                                and (old.hp or 0.0) <= 0.0
                                for sample in samples
                            )
                            if has_sentry and (self._close(spend, 200.0) or self._close(spend, 60.0)):
                                remote = self._close(spend, 200.0)
                                ammo_cost = 150.0 if remote else 10.0
                                caliber = None
                                grant = 0.0
                                if remote and 1.0 <= shot_delta_42 <= self.REMOTE_42MM[1] and shot_delta_17 < 1.0:
                                    caliber, grant = "42mm", self.REMOTE_42MM[1]
                                elif remote and 1.0 <= shot_delta_17 <= self.REMOTE_17MM[1]:
                                    caliber, grant = "17mm", self.REMOTE_17MM[1]
                                elif not remote and 1.0 <= shot_delta_42 <= self.LOCAL_42MM[1] and shot_delta_17 < 1.0:
                                    caliber, grant = "42mm", self.LOCAL_42MM[1]
                                elif not remote and 1.0 <= shot_delta_17 <= self.LOCAL_17MM[1]:
                                    caliber, grant = "17mm", self.LOCAL_17MM[1]
                                if caliber and self._ammo_exchange_room(raw_team, caliber, grant):
                                    remaining_cap = self._record_ammo_exchange(raw_team, caliber, grant)
                                    new_actions.append(self._append(
                                        frame, raw_team, f"{('远程' if remote else '本地')}{caliber}兑换+自动哨兵指令费候选",
                                        spend, 0.34,
                                        f"金币变化可拆为兑换{ammo_cost:g}+指令费50；{caliber}额度估计剩余{remaining_cap:g}，哨兵控制模式及交易对象未记录",
                                    ))
                                    matched_action = True
                            if not matched_action and has_sentry and self._close(spend, self.AUTO_SENTRY_COMMAND_COST):
                                new_actions.append(self._append(
                                    frame, raw_team, "自动哨兵指令费候选", spend, 0.22,
                                    "规则书规定自动哨兵操作手执行相关裁判指令每次50金币；数据未记录自动/半自动模式及指令内容",
                                ))
                                matched_action = True
                            if not matched_action and (self._close(spend, 150.0)
                                    and 1.0 <= shot_delta_42 <= self.REMOTE_42MM[1]
                                    and shot_delta_17 < 1.0
                                    and self._ammo_exchange_room(raw_team, "42mm", self.REMOTE_42MM[1])):
                                remaining_cap = self._record_ammo_exchange(raw_team, "42mm", self.REMOTE_42MM[1])
                                new_actions.append(self._append(
                                    frame, raw_team, "远程42mm兑换候选", spend, 0.50,
                                    f"支出150且42mm计数变化{shot_delta_42:g}；候选兑换10发，队伍推算额度剩余{remaining_cap:g}/100；发弹计数不能证明弹量到账",
                                ))
                                matched_action = True
                            elif (self._close(spend, 150.0)
                                  and 1.0 <= shot_delta_17 <= self.REMOTE_17MM[1]
                                  and self._ammo_exchange_room(raw_team, "17mm", self.REMOTE_17MM[1])):
                                remaining_cap = self._record_ammo_exchange(raw_team, "17mm", self.REMOTE_17MM[1])
                                new_actions.append(self._append(
                                    frame, raw_team, "远程17mm兑换候选", spend, 0.50,
                                    f"支出150且17mm计数变化{shot_delta_17:g}；候选兑换100发，队伍推算额度剩余{remaining_cap:g}/1000；发弹计数不能证明弹量到账",
                                ))
                                matched_action = True
                            elif (self._close(spend, 10.0)
                                  and 1.0 <= shot_delta_42 <= self.LOCAL_42MM[1]
                                  and shot_delta_17 < 1.0
                                  and self._ammo_exchange_room(raw_team, "42mm", self.LOCAL_42MM[1])):
                                remaining_cap = self._record_ammo_exchange(raw_team, "42mm", self.LOCAL_42MM[1])
                                new_actions.append(self._append(
                                    frame, raw_team, "本地42mm兑换候选", spend, 0.50,
                                    f"支出10且42mm计数变化1；候选兑换1发，队伍推算额度剩余{remaining_cap:g}/100；发弹计数不能证明弹量到账",
                                ))
                                matched_action = True
                            elif (self._close(spend, 10.0)
                                  and 1.0 <= shot_delta_17 <= self.LOCAL_17MM[1]
                                  and self._ammo_exchange_room(raw_team, "17mm", self.LOCAL_17MM[1])):
                                remaining_cap = self._record_ammo_exchange(raw_team, "17mm", self.LOCAL_17MM[1])
                                new_actions.append(self._append(
                                    frame, raw_team, "本地17mm兑换候选", spend, 0.50,
                                    f"支出10且17mm计数变化{shot_delta_17:g}；候选兑换10发，队伍推算额度剩余{remaining_cap:g}/1000；发弹计数不能证明弹量到账",
                                ))
                                matched_action = True
                            elif dead_waiting and any(
                                self._close(spend, cost, 3.0)
                                for cost in self._revive_costs(frame.time_seconds)
                            ):
                                self._pending_costs.append((raw_team, frame.time_seconds, spend, "立即复活候选"))
                                matched_action = True
                            elif self._close(
                                spend,
                                50.0 + math.ceil(frame.time_seconds / 60.0) * 20.0,
                            ):
                                self._pending_costs.append((raw_team, frame.time_seconds, spend, "远程回血候选"))
                                matched_action = True
                            elif self._close(spend, 150.0):
                                new_actions.append(self._append(
                                    frame, raw_team, "远程兑换弹药（口径不明）", spend, 0.45,
                                    "支出匹配150金币，但无交易流水/剩余弹量，仍可能是42mm兑换或其他用途",
                                ))
                                matched_action = True
                            elif self._close(spend, 10.0):
                                new_actions.append(self._append(
                                    frame, raw_team, "本地兑换弹药（口径不明）", spend, 0.45,
                                    "支出匹配10金币，但累计发弹未能区分17mm/42mm",
                                ))
                                matched_action = True
                            elif aerial := any(sample.robot_type == "空中" for sample in samples):
                                free_support = (
                                    self.INITIAL_AIR_SUPPORT_SECONDS
                                    + self.AIR_SUPPORT_BONUS_PER_MINUTE * math.floor(frame.time_seconds / 60.0)
                                )
                                if (frame.time_seconds > free_support
                                        and self._close(spend, max(1.0, round(frame.time_seconds - previous_time)), 1.5)):
                                    air_support_candidate = True
                                    if raw_team not in self._air_support_active:
                                        new_actions.append(self._append(
                                            frame, raw_team, "空中支援扣费候选", spend, 0.48,
                                            f"符合免费时长30秒+每分钟20秒后的1金币/秒扣费；数据没有支援开关/耗时流水",
                                        ))
                                    self._air_support_active.add(raw_team)
                                    matched_action = True
                            if not matched_action and spend >= 5.0:
                                # Air support is 1 coin/s and an exchange can
                                # be combined with it; surface the residual.
                                aerial = any(sample.robot_type == "空中" for sample in samples)
                                confidence = 0.38 if aerial else 0.18
                                new_actions.append(self._append(
                                    frame, raw_team, "未分类经济支出", spend, confidence,
                                    "由总金币、剩余金币和收入增量守恒反推；数据未提供交易类型",
                                ))
                    if spend < 1.0 or (spend >= 1.0 and not air_support_candidate and spend < 5.0):
                        self._air_support_active.discard(raw_team)
                else:
                    # Rulebook table 5-5 starts each team at 400 coins.  The
                    # first dataset row can already include an observed spend,
                    # so expose this as a baseline annotation only.
                    if frame.time_seconds <= 1.0:
                        new_actions.append(self._append(
                            frame, raw_team, "规则书初始金币基线", 400.0, 1.0,
                            "规则书5-5规定初始金币400；这是规则基线，不代表timeseries首行余额恰为400",
                        ))
                self._previous[raw_team] = (frame.time_seconds, current_total, current_remaining)

            # Rulebook scheduled income and assembly/tech-core income are
            # positive deltas.  They are annotations, not balance mutations.
            for tick, amount in self.PERIODIC_INCOME:
                marker = (raw_team, tick)
                if marker not in self._scheduled_seen and frame.time_seconds >= tick:
                    self._scheduled_seen.add(marker)
                    new_actions.append(self._append(
                        frame, raw_team, "定时队伍收入", amount, 1.0,
                        f"规则书5-5：倒计时对应的定时收入+{amount:g}",
                    ))
            # Sentry supply acquisition: +100 allowed 17mm each minute while
            # the supply area is held, accumulating when not collected.
            minute = int(frame.time_seconds // 60.0)
            supply_marker = (raw_team, minute)
            if frame.time_seconds > 0 and minute > 0 and supply_marker not in self._supply_seen:
                sentry = next((s for s in samples if s.robot_type == "哨兵"), None)
                in_supply = bool(
                    sentry is not None and sentry.x is not None and sentry.y is not None
                    and ((raw_team == "red" and 0.5 <= sentry.x <= 3.7 and 0.2 <= sentry.y <= 2.4)
                         or (raw_team == "blue" and 24.3 <= sentry.x <= 27.5 and 12.6 <= sentry.y <= 14.8))
                )
                if in_supply:
                    self._supply_seen.add(supply_marker)
                    new_actions.append(self._append(
                        frame, raw_team, "哨兵补给区17mm额度", 0.0, 0.30,
                        "规则书：占领补给区每分钟累计+100允许发弹；timeseries无领取流水",
                    ))

        self._previous_samples = {sample.robot_id: sample for sample in frame.samples}
        return tuple(new_actions)


def _interpolate_angle(first: float | None, second: float | None, ratio: float) -> float | None:
    if first is None or second is None:
        return first if ratio < 0.5 else second
    delta = (second - first + 180.0) % 360.0 - 180.0
    return (first + delta * ratio + 180.0) % 360.0 - 180.0


def _interpolate_optional(first: float | None, second: float | None, ratio: float) -> float | None:
    if first is None or second is None:
        return first if ratio < 0.5 else second
    return first + (second - first) * ratio


def _interpolate_sample(first: RobotSample, second: RobotSample, time_seconds: float) -> RobotSample:
    span = second.time_seconds - first.time_seconds
    ratio = 0.0 if span <= 0.0 else (time_seconds - first.time_seconds) / span
    ratio = max(0.0, min(1.0, ratio))
    return replace(
        first,
        time_seconds=time_seconds,
        hp=_interpolate_optional(first.hp, second.hp, ratio),
        max_hp=_interpolate_optional(first.max_hp, second.max_hp, ratio),
        x=_interpolate_optional(first.x, second.x, ratio),
        y=_interpolate_optional(first.y, second.y, ratio),
        z=_interpolate_optional(first.z, second.z, ratio),
        heading_degrees=_interpolate_angle(first.heading_degrees, second.heading_degrees, ratio),
        chassis_power=_interpolate_optional(first.chassis_power, second.chassis_power, ratio),
        small_heat=_interpolate_optional(first.small_heat, second.small_heat, ratio),
        small_heat_limit=_interpolate_optional(first.small_heat_limit, second.small_heat_limit, ratio),
        large_heat=_interpolate_optional(first.large_heat, second.large_heat, ratio),
        large_heat_limit=_interpolate_optional(first.large_heat_limit, second.large_heat_limit, ratio),
        shots_17mm=_interpolate_optional(first.shots_17mm, second.shots_17mm, ratio),
        shots_42mm=_interpolate_optional(first.shots_42mm, second.shots_42mm, ratio),
        team_coins=_interpolate_optional(first.team_coins, second.team_coins, ratio),
        remaining_coins=_interpolate_optional(first.remaining_coins, second.remaining_coins, ratio),
        vulnerable=first.vulnerable if ratio < 0.5 else second.vulnerable,
    )


class DatasetReplay:
    """A loaded game with random access to interpolated frames."""

    def __init__(
        self,
        match: MatchRecord,
        samples: Iterable[RobotSample],
        events: Iterable[ReplayEvent],
    ) -> None:
        self.match = match
        self._samples_by_robot: dict[int, tuple[RobotSample, ...]] = {}
        grouped: dict[int, list[RobotSample]] = {}
        for sample in samples:
            grouped.setdefault(sample.robot_id, []).append(sample)
        for robot_id, robot_samples in grouped.items():
            robot_samples.sort(key=lambda item: item.time_seconds)
            self._samples_by_robot[robot_id] = tuple(robot_samples)
        self.events = tuple(sorted(events, key=lambda item: item.time_seconds))
        observed_max = max(
            [sample.time_seconds for values in self._samples_by_robot.values() for sample in values]
            + [event.time_seconds for event in self.events]
            + [0.0]
        )
        self.duration_seconds = max(float(match.duration_seconds), observed_max)
        self.times = tuple(
            sorted(
                {
                    sample.time_seconds
                    for values in self._samples_by_robot.values()
                    for sample in values
                }
                | {event.time_seconds for event in self.events}
                | {0.0, self.duration_seconds}
            )
        )
        self._event_times = tuple(event.time_seconds for event in self.events)

    @property
    def robot_ids(self) -> tuple[int, ...]:
        return tuple(sorted(self._samples_by_robot))

    @property
    def sample_count(self) -> int:
        return sum(len(samples) for samples in self._samples_by_robot.values())

    def _sample_at(self, samples: tuple[RobotSample, ...], time_seconds: float) -> RobotSample | None:
        if not samples:
            return None
        first, last = samples[0], samples[-1]
        # Aerial rows are intentionally sparse.  Do not show an aircraft before
        # launch or after its final row; all ordinary rows start at t=1, so
        # rendering at t=0 still has a useful initial frame.
        if time_seconds < first.time_seconds:
            return replace(first, time_seconds=time_seconds) if first.time_seconds <= 1.0 else None
        if time_seconds > last.time_seconds:
            return replace(last, time_seconds=time_seconds) if last.time_seconds >= self.duration_seconds - 1.0 else None
        times = [sample.time_seconds for sample in samples]
        right = bisect_right(times, time_seconds)
        if right == 0:
            return first
        if right >= len(samples):
            return last
        left_sample, right_sample = samples[right - 1], samples[right]
        if math.isclose(left_sample.time_seconds, time_seconds, abs_tol=1e-9):
            return left_sample
        return _interpolate_sample(left_sample, right_sample, time_seconds)

    def frame_at(self, time_seconds: float, *, include_events: bool = True) -> ReplayFrame:
        current = max(0.0, min(float(time_seconds), self.duration_seconds))
        samples = tuple(
            sample
            for robot_id in self.robot_ids
            if (sample := self._sample_at(self._samples_by_robot[robot_id], current)) is not None
        )
        events: tuple[ReplayEvent, ...] = ()
        if include_events:
            right = bisect_right(self._event_times, current)
            events = self.events[:right]
        return ReplayFrame(current, samples, events)

    def events_between(self, start_seconds: float, end_seconds: float) -> tuple[ReplayEvent, ...]:
        """Return events in the forward interval ``(start_seconds, end]``.

        The half-open boundary lets a time-driven consumer advance one frame
        at a time without delivering an event at the previous frame twice.
        ``frame_at`` remains cumulative for inspection and rendering.
        """
        start = min(float(start_seconds), float(end_seconds))
        end = max(float(start_seconds), float(end_seconds))
        left = bisect_right(self._event_times, start)
        right = bisect_right(self._event_times, end)
        return self.events[left:right]


class ReplayPlayer:
    """Clock and transport controls for a :class:`DatasetReplay`."""

    SPEEDS = (0.25, 0.5, 1.0, 2.0, 4.0, 8.0)

    def __init__(self, replay: DatasetReplay) -> None:
        self.replay = replay
        self.time_seconds = 0.0
        self.speed = 1.0
        self.playing = False
        self.loop = False

    @property
    def ended(self) -> bool:
        return self.time_seconds >= self.replay.duration_seconds

    def frame(self) -> ReplayFrame:
        return self.replay.frame_at(self.time_seconds)

    def play(self) -> None:
        if self.ended and not self.loop:
            return
        self.playing = True

    def pause(self) -> None:
        self.playing = False

    def toggle(self) -> bool:
        if self.playing:
            self.pause()
        else:
            self.play()
        return self.playing

    def set_speed(self, speed: float) -> float:
        closest = min(self.SPEEDS, key=lambda value: abs(value - float(speed)))
        self.speed = closest
        return self.speed

    def faster(self) -> float:
        index = self.SPEEDS.index(self.speed)
        self.speed = self.SPEEDS[min(index + 1, len(self.SPEEDS) - 1)]
        return self.speed

    def slower(self) -> float:
        index = self.SPEEDS.index(self.speed)
        self.speed = self.SPEEDS[max(index - 1, 0)]
        return self.speed

    def seek(self, time_seconds: float) -> float:
        self.time_seconds = max(0.0, min(float(time_seconds), self.replay.duration_seconds))
        if self.ended and not self.loop:
            self.playing = False
        return self.time_seconds

    def step(self, seconds: float) -> float:
        self.pause()
        return self.seek(self.time_seconds + float(seconds))

    def reset(self) -> None:
        self.pause()
        self.time_seconds = 0.0

    def update(self, real_seconds: float) -> ReplayFrame:
        if self.playing and real_seconds > 0.0:
            target = self.time_seconds + float(real_seconds) * self.speed
            if target >= self.replay.duration_seconds:
                if self.loop and self.replay.duration_seconds > 0.0:
                    target %= self.replay.duration_seconds
                else:
                    target = self.replay.duration_seconds
                    self.playing = False
            self.time_seconds = target
        return self.frame()


class DatasetRepository:
    """Small, parameterized, read-only facade over the dataset schema."""

    def __init__(self, path: str | Path = DEFAULT_DATASET_PATH) -> None:
        self.path = Path(path).expanduser().resolve()
        if not self.path.is_file():
            raise DatasetError(f"SQLite dataset does not exist: {self.path}")
        self._connection = self._open_connection()
        self._validate_schema()

    def _open_connection(self) -> sqlite3.Connection:
        uri = f"file:{self.path.as_posix()}?mode=ro"
        try:
            connection = sqlite3.connect(uri, uri=True)
        except sqlite3.Error as error:
            raise DatasetError(f"Cannot open SQLite dataset read-only: {self.path}") from error
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only = ON")
        return connection

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> "DatasetRepository":
        return self

    def __exit__(self, _type, _value, _traceback) -> None:
        self.close()

    def _validate_schema(self) -> None:
        rows = self._connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
        tables = {str(row["name"]) for row in rows}
        missing_tables = {"matches", "timeseries", "events"} - tables
        if missing_tables:
            raise DatasetError(f"Dataset is missing tables: {sorted(missing_tables)}")
        for table, expected in (
            ("matches", MATCH_COLUMNS),
            ("timeseries", TIMESERIES_COLUMNS),
            ("events", EVENT_COLUMNS),
        ):
            actual = {
                str(row[1])
                for row in self._connection.execute(f'PRAGMA table_info("{table}")')
            }
            missing = set(expected) - actual
            if missing:
                raise DatasetError(f"Table {table!r} is missing columns: {sorted(missing)}")

    def list_matches(
        self,
        *,
        region: str | None = None,
        school: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> tuple[MatchRecord, ...]:
        clauses: list[str] = []
        parameters: list[object] = []
        if region:
            clauses.append('"赛区" = ?')
            parameters.append(region)
        if school:
            clauses.append('("红方学校" = ? OR "蓝方学校" = ?)')
            parameters.extend((school, school))
        sql = "SELECT * FROM matches"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += ' ORDER BY "开始时间", game_id'
        if limit is not None:
            if limit < 0 or offset < 0:
                raise ValueError("limit and offset must be non-negative")
            sql += " LIMIT ? OFFSET ?"
            parameters.extend((int(limit), int(offset)))
        elif offset:
            raise ValueError("offset requires limit")
        rows = self._connection.execute(sql, parameters).fetchall()
        return tuple(MatchRecord.from_row(row) for row in rows)

    def get_match(self, game_id: int) -> MatchRecord:
        row = self._connection.execute(
            "SELECT * FROM matches WHERE game_id = ?", (int(game_id),)
        ).fetchone()
        if row is None:
            raise DatasetError(f"Unknown game_id: {game_id}")
        return MatchRecord.from_row(row)

    def load_replay(self, game_id: int) -> DatasetReplay:
        match = self.get_match(game_id)
        sample_rows = self._connection.execute(
            "SELECT * FROM timeseries WHERE game_id = ? ORDER BY \"时刻秒\", robot_id",
            (match.game_id,),
        )
        event_rows = self._connection.execute(
            "SELECT * FROM events WHERE game_id = ? ORDER BY \"时刻秒\", rowid",
            (match.game_id,),
        )
        samples = (RobotSample.from_row(row) for row in sample_rows)
        events = (ReplayEvent.from_row(row) for row in event_rows)
        return DatasetReplay(match, samples, events)

    def iter_replays(self, matches: Iterable[MatchRecord]) -> Iterator[DatasetReplay]:
        for match in matches:
            yield self.load_replay(match.game_id)


__all__ = [
    "DEFAULT_DATASET_PATH",
    "DATASET_ENTITY_ID_MAP",
    "DatasetError",
    "DatasetReplay",
    "DatasetRepository",
    "EconomicInference",
    "InferredEconomyAction",
    "dataset_local_entity_id",
    "MatchRecord",
    "ReplayEvent",
    "ReplayFrame",
    "ReplayPlayer",
    "RobotSample",
]
