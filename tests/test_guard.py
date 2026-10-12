"""guard 单元测试：R1-R4 判定规则与处置链各分支。"""
from __future__ import annotations

import json

from grounded_shop.guard import (
    check_output,
    extract_mentions,
    extract_suspect_shopnames,
    strip_violating_sentences,
)
from grounded_shop.models import Shop


def mk_shop(name: str, *, tags=("海鲜",), rating=4.5) -> Shop:
    return Shop(
        id="T1", name=name, address="市北区测试路 1 号(虚构)", area="台东",
        lat=36.08, lng=120.36, tags=list(tags), rating=rating, avg_price=50,
        source="unit-test", verified=True, last_verified_at="2026-10-01",
    )


CAND = [mk_shop("测试海鲜楼"), mk_shop("老地方锅贴铺", tags=("锅贴",))]
ALL_NAMES = ["测试海鲜楼", "老地方锅贴铺", "别的店烧烤城"]


def ok_raw(answer: str, recommended: list[str]) -> str:
    return json.dumps({"answer": answer, "recommended": recommended}, ensure_ascii=False)


class TestR1Parse:
    def test_invalid_json(self):
        v = check_output("这不是 JSON", CAND, ALL_NAMES)
        assert not v.ok and v.parse_error

    def test_missing_answer_field(self):
        v = check_output('{"recommended": []}', CAND, ALL_NAMES)
        assert not v.ok and v.parse_error


class TestR2RecommendedSubset:
    def test_recommended_outside_candidates(self):
        v = check_output(ok_raw("给你推荐测试海鲜楼。", ["测试海鲜楼", "不存在的店"]), CAND, ALL_NAMES)
        assert not v.ok and "不存在的店" in v.violations

    def test_recommended_subset_ok(self):
        v = check_output(ok_raw("给你推荐测试海鲜楼。", ["测试海鲜楼"]), CAND, ALL_NAMES)
        assert v.ok


class TestR3CrossMention:
    def test_other_library_shop_leaked(self):
        v = check_output(ok_raw("测试海鲜楼不错，隔壁别的店烧烤城也可以。", ["测试海鲜楼"]), CAND, ALL_NAMES)
        assert not v.ok and "别的店烧烤城" in v.violations


class TestR4FabricatedName:
    def test_fabricated_name_intercepted(self):
        v = check_output(ok_raw("推荐测试海鲜楼，另外老张秘制海鲜楼也很好。", ["测试海鲜楼"]), CAND, ALL_NAMES)
        assert not v.ok
        assert any("老张秘制海鲜楼" in viol for viol in v.violations)

    def test_variant_fabrication_intercepted(self):
        """评审 OB-1 回归：真名变体（店名 ⊂ token）不得豁免——「测试海鲜楼分店」是编造。"""
        v = check_output(ok_raw("测试海鲜楼不错，测试海鲜楼分店也开张了。", ["测试海鲜楼"]), CAND, ALL_NAMES)
        assert not v.ok and any("分店" in viol for viol in v.violations)

    def test_candidate_fragment_not_flagged(self):
        """候选店名被标点截断的片段（token ⊂ 店名）不误杀。"""
        cand = [mk_shop("双合园锅贴(台东老铺)", tags=("锅贴", "老字号"))]
        v = check_output(
            ok_raw("双合园锅贴(台东老铺)主打锅贴、老字号。", ["双合园锅贴(台东老铺)"]),
            cand, [c.name for c in cand],
        )
        assert v.ok, f"误杀: {v.violations}"

    def test_tag_word_not_flagged(self):
        v = check_output(ok_raw("主打海鲜，人均 50。", []), CAND, ALL_NAMES)
        assert v.ok, f"品类词误杀: {v.violations}"

    def test_extract_suspect_variant(self):
        """评审 OB-2：近似真名的变体是最高危幻觉形态，直接对启发式函数断言。"""
        cand = [mk_shop("测试海鲜楼")]
        assert extract_suspect_shopnames("新开的测试海鲜楼分店人也少。", cand) != set()


class TestStrip:
    def test_strip_removes_violating_sentence(self):
        text = "推荐测试海鲜楼。\n老张秘制海鲜楼也排队。\n出发前确认营业。"
        out = strip_violating_sentences(text, {"老张秘制海鲜楼"}, ALL_NAMES)
        assert "老张秘制海鲜楼" not in out and "测试海鲜楼" in out

    def test_strip_all_violating_returns_empty(self):
        text = "老张秘制海鲜楼排队。"
        assert strip_violating_sentences(text, {"老张秘制海鲜楼"}, ALL_NAMES) == ""


class TestExtractMentions:
    def test_longest_first(self):
        text = "别的店烧烤城门口见"
        assert extract_mentions(text, ALL_NAMES) == {"别的店烧烤城"}
