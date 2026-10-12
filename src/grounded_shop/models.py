"""数据模型：店铺记录 schema 与管线结果对象。

设计源头（docs/research-opensource.md §1）：
- pydantic / instructor —— 事实层从 schema 开始收口：LLM 永远拿不到"自由文本进数据库"的入口。
- guardrails —— GuardEvent 对应其 validator 的失败动作记录（reask/strip/fallback）。
"""
from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Shop(BaseModel):
    """一条已验证来源的店铺记录。source 非空是入库硬约束（可追溯性判据）。"""

    model_config = ConfigDict(frozen=True)

    id: str
    name: str = Field(min_length=2)
    address: str
    area: str
    lat: float
    lng: float
    tags: list[str] = Field(default_factory=list)
    rating: float = Field(ge=0, le=5)
    avg_price: float | None = None
    source: str = Field(min_length=1)  # 来源标注，禁止为空
    verified: bool = False
    last_verified_at: date

    @field_validator("source")
    @classmethod
    def _source_not_placeholder(cls, v: str) -> str:
        if v.strip().lower() in {"", "unknown", "n/a", "无"}:
            raise ValueError("source 不能为空或占位符：每条数据必须可追溯")
        return v


class GuardEvent(BaseModel):
    """回校器事件：防线每次动作都留痕，供回归测试与周报统计。"""

    type: Literal["PASS", "RETRY_TRIGGERED", "RETRY_PASSED", "STRIP_SENTENCES", "FALLBACK_TEMPLATE", "REFUSE"]
    detail: str = ""


class PipelineResult(BaseModel):
    """一次问答的完整输出：文本 + 候选集 + 防线事件 + 是否拒答。"""

    answer: str
    candidates: list[Shop] = Field(default_factory=list)
    guard_events: list[GuardEvent] = Field(default_factory=list)
    refused: bool = False

    @property
    def candidate_names(self) -> set[str]:
        return {s.name for s in self.candidates}
