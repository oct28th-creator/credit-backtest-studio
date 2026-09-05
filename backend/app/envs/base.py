"""Environment registry and confidence bands."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Optional

HIGH, MEDIUM, LOW = "high", "medium", "low"


@dataclass(frozen=True)
class Environment:
    id: str
    version: str
    level: str            # L0a | L0b | L0c
    name_zh: str
    confidence: str       # high | medium | low
    valid_for: list       # question types this environment can answer
    not_valid_for: list   # questions it cannot answer, whatever the numbers say

    def to_dict(self) -> dict:
        return asdict(self)


ENVIRONMENTS: dict[str, Environment] = {
    "replay": Environment(
        id="replay",
        version="1.0",
        level="L0a",
        name_zh="历史回放",
        confidence=HIGH,
        valid_for=[
            "同一批客群下不同策略的排序（谁批得准）",
            "模型区分度与校准（KS/AUC/Brier）",
            "swap-set 结构与即期坏账对比",
        ],
        not_valid_for=[
            "策略放开后新客群的表现（拒绝客群无表现数据）",
            "长期客群迁移、用信弹性、多期滚动",
            "任何依赖客户行为对政策做出反应的结论",
        ],
    ),
    "reject_inference": Environment(
        id="reject_inference",
        version="1.0",
        level="L0b",
        name_zh="拒绝推断",
        confidence=MEDIUM,
        valid_for=[
            "放宽准入后新增客群的坏账估计（带偏差区间）",
            "不同拒绝推断方法之间的稳健性比较",
            "swap-in 客群风险的量级判断",
        ],
        not_valid_for=[
            "行为反馈（接受率、用信率随额度变化）",
            "多期滚动与客群迁移",
            "精确到小数点后一位的坏账预测",
        ],
    ),
}


def get_environment(env_id: Optional[str]) -> Environment:
    return ENVIRONMENTS.get(env_id or "replay", ENVIRONMENTS["replay"])


def list_environments() -> list[dict]:
    return [e.to_dict() for e in ENVIRONMENTS.values()]
