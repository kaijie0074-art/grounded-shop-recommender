"""store / query / 数据质量测试。

覆盖：规则排序可解释性、时效隐藏、预算过滤、来源可追溯（验收判据 §2.4-4）、
拒答触发留痕（判据 §2.4-3 的数据基础）。
"""
from __future__ import annotations

from datetime import date

import pytest

from grounded_shop import answer_query
from grounded_shop.llm import TemplateWrapperLLM
from grounded_shop.models import Shop
from grounded_shop.query import parse_query
from grounded_shop.store import ShopStore


class TestDataQuality:
    def test_all_sources_nonempty(self, store):
        """验收判据：数据来源字段 100% 非空（可追溯）。"""
        for s in store._shops.values():
            assert s.source and s.source.strip()

    def test_source_placeholder_rejected(self):
        with pytest.raises(Exception):
            Shop(**{**_row("X1"), "source": ""})

    def test_dataset_marked_simulated(self, store):
        """数据诚信：种子数据集必须显式标注 SIMULATED。"""
        import json
        from pathlib import Path
        meta = json.loads((Path(__file__).parents[1] / "data" / "shops.json").read_text(encoding="utf-8"))["_meta"]
        assert meta["dataset"] == "SIMULATED_SEED_DATA"


def _row(sid: str, **over):
    base = dict(
        id=sid, name=f"测试店{sid}", address="市北区测试路 1 号(虚构)", area="台东",
        lat=36.08, lng=120.36, tags=["海鲜"], rating=4.0, avg_price=50,
        source="unit-test", verified=False, last_verified_at="2026-09-01",
    )
    base.update(over)
    return base


def mk_store(rows):
    return ShopStore([Shop(**r) for r in rows], reference_date=date(2026, 10, 13))


class TestStoreRules:
    def test_staleness_hides_expired(self):
        store = mk_store([_row("A", last_verified_at="2026-09-20"), _row("B", last_verified_at="2026-05-01")])
        names = [s.name for s in store.select(parse_query("台东海鲜"))]
        assert "测试店A" in names and "测试店B" not in names

    def test_budget_filter(self):
        store = mk_store([_row("A", avg_price=30), _row("B", avg_price=90)])
        pq = parse_query("台东海鲜人均50以内")
        assert pq.max_price == 50
        names = [s.name for s in store.select(pq)]
        assert "测试店A" in names and "测试店B" not in names

    def test_rating_ranking_explainable(self):
        store = mk_store([_row("A", rating=4.9), _row("B", rating=4.1)])
        ranked = [s.name for s in store.select(parse_query("台东海鲜"))]
        assert ranked.index("测试店A") < ranked.index("测试店B")

    def test_tag_mismatch_returns_empty(self):
        store = mk_store([_row("A")])
        assert store.select(parse_query("台东火锅")) == []


class TestQueryParse:
    def test_area_lexicon_priority(self):
        pq = parse_query("台东八路好吃的")
        assert pq.areas == {"台东"}

    def test_out_of_coverage(self):
        assert parse_query("李沧吃海鲜").out_of_coverage

    def test_generic_food_query_gets_any_tag(self):
        assert parse_query("台东有什么美食").tags


class TestRefusalTelemetry:
    def test_refusal_logged_as_event(self, store):
        result = answer_query("李沧区有什么好吃的", store, TemplateWrapperLLM())
        assert result.refused
        assert [e.type for e in result.guard_events] == ["REFUSE"]
        assert "数据还在完善中" in result.answer

    def test_no_match_refusal_mentions_known_tags(self, store):
        result = answer_query("台东有法餐吗", store, TemplateWrapperLLM())
        assert result.refused and "海鲜" in result.answer  # 引导到已收录品类
