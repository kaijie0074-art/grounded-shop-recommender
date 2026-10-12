"""店铺库：加载、过滤、规则排序。

推荐排序 = 可解释的规则（评分 + 标签命中 + 验证状态 + 时效），不是模型偏好——
这是"LLM 不掌握事实生成权"的第一半；第二半在 guard.py。
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from .models import Shop
from .query import ANY_TAG, ParsedQuery


class ShopStore:
    def __init__(self, shops: list[Shop], *, reference_date: date, hide_after_days: int = 90):
        self._shops = {s.id: s for s in shops}
        self.reference_date = reference_date
        self.hide_after_days = hide_after_days

    @classmethod
    def load(cls, path: str | Path) -> "ShopStore":
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        meta = raw["_meta"]
        shops = [Shop(**row) for row in raw["shops"]]
        return cls(
            shops,
            reference_date=date.fromisoformat(meta["reference_date"]),
            hide_after_days=int(meta.get("staleness_days_threshold", 90)),
        )

    @property
    def all_names(self) -> list[str]:
        """库内全部店名，供回校器做"夹带检测"。"""
        return [s.name for s in self._shops.values()]

    @property
    def all_shops(self) -> list[Shop]:
        """公开只读视图：数据质量检查等场景使用，不暴露内部容器（评审 OB-4）。"""
        return list(self._shops.values())

    def _staleness_days(self, shop: Shop) -> int:
        return (self.reference_date - shop.last_verified_at).days

    def _visible(self, shop: Shop) -> bool:
        # 时效衰减：超期未复验的店隐藏（问题报告 §2.3 子问题 3）
        return self._staleness_days(shop) <= self.hide_after_days

    def _score(self, shop: Shop, pq: ParsedQuery) -> float:
        tag_hits = len(set(shop.tags) & pq.tags) if pq.tags else 0
        verified_bonus = 0.5 if shop.verified else 0.0
        staleness_penalty = self._staleness_days(shop) / 30.0  # 越老分越低，平滑降权
        return shop.rating * 2 + tag_hits * 1.5 + verified_bonus - staleness_penalty

    def select(self, pq: ParsedQuery, *, top_k: int = 3) -> list[Shop]:
        """规则排序选出候选集。候选为空 = 拒答，绝不降级到自由生成。"""
        want_tags = pq.tags - {ANY_TAG}
        pool = [
            s for s in self._shops.values()
            if self._visible(s)
            and (not pq.areas or s.area in pq.areas)
            and s.rating >= 0  # pydantic 已保证 ≥0；显式保留可读性
            and (pq.max_price is None or (s.avg_price is not None and s.avg_price <= pq.max_price))
            and (not want_tags or (set(s.tags) & want_tags))
        ]
        pool.sort(key=lambda s: self._score(s, pq), reverse=True)
        return pool[:top_k]

    def get(self, shop_id: str) -> Shop:
        return self._shops[shop_id]
