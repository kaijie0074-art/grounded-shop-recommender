"""拒答层：候选为空/区域未覆盖时的标准话术。绝不降级到自由生成。

拒答率是健康指标，不是缺陷指标：每次拒答以 GuardEvent(type="REFUSE") 留痕。
话术为固定模板（不回显用户原话——用户输入不经任何生成环节，回显反而会被
输出自检启发式误报，见 tests/test_regression.py 的拒答断言）。
"""
from __future__ import annotations

from .models import GuardEvent
from .query import KNOWN_TAG_HINT
from .wrappers import AI_LABEL

COVERED_AREAS_HINT = "台东、威海路、营口路、登州路、延安二路、镇江路"


def refuse_out_of_coverage() -> tuple[str, GuardEvent]:
    text = (
        f"抱歉，该区域的店铺数据还在完善中，目前只收录了{COVERED_AREAS_HINT}一带。"
        f"可以先看看这些区域，或之后再来问。{AI_LABEL}"
    )
    return text, GuardEvent(type="REFUSE", detail="out_of_coverage")


def refuse_no_match(query_hint: str = "") -> tuple[str, GuardEvent]:
    text = (
        "这个条件下暂时没有收录中的店。"
        f"换个关键词试试？目前收录较全的品类：{KNOWN_TAG_HINT}。{AI_LABEL}"
    )
    return text, GuardEvent(type="REFUSE", detail=f"no_match hint={query_hint}")
