"""guard 单元测试：R1-R5 判定规则与处置链各分支。

契约升级（深潜研究 2026-10-14，docs/research/deep-dive-20261014.md Q2）：
- R4b 近邻编造：与库内店名编辑距离 ≤1 的错字/谐音变体拦截；
- R4c 拉丁字母串：跨语言编造（Shun Ji Wonton）拦截；
- R5 自申报 mentions：正文出现的店名必须逐字申报且 ⊆ 候选集。
"""
from __future__ import annotations

import json

from grounded_shop.guard import (
    check_output,
    extract_latin_suspects,
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


def ok_raw(answer: str, recommended: list[str], mentions: list[str] | None = None) -> str:
    data = {"answer": answer, "recommended": recommended}
    if mentions is not None:
        data["mentions"] = mentions
    return json.dumps(data, ensure_ascii=False)


class TestR1Parse:
    def test_invalid_json(self):
        v = check_output("这不是JSON", CAND, ALL_NAMES)
        assert not v.ok and v.parse_error

    def test_missing_answer_field(self):
        v = check_output(json.dumps({"recommended": []}), CAND, ALL_NAMES)
        assert not v.ok and v.parse_error


class TestR2RecommendedSubset:
    def test_recommended_outside_candidates(self):
        v = check_output(ok_raw("给你推荐测试海鲜楼。", ["测试海鲜楼", "不存在的店"], ["测试海鲜楼"]), CAND, ALL_NAMES)
        assert not v.ok and "不存在的店" in v.violations

    def test_recommended_subset_ok(self):
        v = check_output(ok_raw("给你推荐测试海鲜楼。", ["测试海鲜楼"], ["测试海鲜楼"]), CAND, ALL_NAMES)
        assert v.ok


class TestR3CrossMention:
    def test_other_library_shop_leaked(self):
        v = check_output(ok_raw("测试海鲜楼不错，隔壁别的店烧烤城也可以。", ["测试海鲜楼"], ["测试海鲜楼"]), CAND, ALL_NAMES)
        assert not v.ok and "别的店烧烤城" in v.violations


class TestR4FabricatedName:
    def test_fabricated_name_intercepted(self):
        v = check_output(ok_raw("推荐测试海鲜楼，另外老张秘制海鲜楼也很好。", ["测试海鲜楼"], ["测试海鲜楼"]), CAND, ALL_NAMES)
        assert not v.ok
        assert any("老张秘制海鲜楼" in viol for viol in v.violations)

    def test_variant_fabrication_intercepted(self):
        """评审 OB-1 回归：真名变体（店名 ⊂ token）不得豁免——「测试海鲜楼分店」是编造。"""
        v = check_output(ok_raw("测试海鲜楼不错，测试海鲜楼分店也开张了。", ["测试海鲜楼"], ["测试海鲜楼"]), CAND, ALL_NAMES)
        assert not v.ok and any("分店" in viol for viol in v.violations)

    def test_candidate_fragment_not_flagged(self):
        """候选店名被标点截断的片段（token ⊂ 店名）不误杀。"""
        cand = [mk_shop("双合园锅贴(台东老铺)", tags=("锅贴", "老字号"))]
        v = check_output(
            ok_raw("双合园锅贴(台东老铺)主打锅贴、老字号。", ["双合园锅贴(台东老铺)"], ["双合园锅贴(台东老铺)"]),
            cand, [c.name for c in cand],
        )
        assert v.ok, f"误杀: {v.violations}"

    def test_tag_word_not_flagged(self):
        v = check_output(ok_raw("主打海鲜，人均 50。", [], []), CAND, ALL_NAMES)
        assert v.ok, f"品类词误杀: {v.violations}"

    def test_extract_suspect_variant(self):
        """评审 OB-2：近似真名的变体是最高危幻觉形态，直接对启发式函数断言。"""
        cand = [mk_shop("测试海鲜楼")]
        assert extract_suspect_shopnames("新开的测试海鲜楼分店人也少。", cand) != set()


class TestR4bNearMiss:
    """深潜 Q2：错一字谐音变体（金玉家常水铰/王姐家尝菜）绕过原 R4 后缀启发式。"""

    def test_homophone_variant_intercepted(self):
        cand = [mk_shop("金玉家常水饺", tags=("饺子",))]
        v = check_output(
            ok_raw("金玉家常水饺不错，隔壁金玉家常水铰也行。", ["金玉家常水饺"], ["金玉家常水饺"]),
            cand, [c.name for c in cand],
        )
        assert not v.ok and "金玉家常水铰" in v.violations

    def test_legit_phrase_not_near_miss(self):
        """距离 ≥2 的普通短语（"想吃家常菜" vs "王姐家常菜"）不误杀。"""
        cand = [mk_shop("王姐家常菜", tags=("家常菜",))]
        v = check_output(
            ok_raw("想吃家常菜的话，来王姐家常菜。", ["王姐家常菜"], ["王姐家常菜"]),
            cand, [c.name for c in cand],
        )
        assert v.ok, f"误杀: {v.violations}"

    def test_near_miss_of_noncandidate_library_shop(self):
        """非候选库店的近邻变体同样违规（R3 的模糊扩展）。"""
        cand = [mk_shop("测试海鲜楼")]
        names = ["测试海鲜楼", "老地方锅贴铺", "别的店烧烤城"]
        v = check_output(ok_raw("老地方锅贴铺子排队。", ["测试海鲜楼"], ["测试海鲜楼"]), cand, names)
        assert not v.ok and "老地方锅贴铺子" in v.violations


class TestR4cLatin:
    def test_latin_fabrication_intercepted(self):
        v = check_output(
            ok_raw("推荐测试海鲜楼，Shun Ji Wonton 也可以。", ["测试海鲜楼"], ["测试海鲜楼"]),
            CAND, ALL_NAMES,
        )
        assert not v.ok and {"Shun", "Wonton"} & v.violations

    def test_short_latin_not_flagged(self):
        assert extract_latin_suspects("人均50RMB，AI 推荐") == set()


class TestStrip:
    def test_strip_removes_violating_sentence(self):
        text = "推荐测试海鲜楼。\n老张秘制海鲜楼也排队。\n出发前确认营业。"
        out = strip_violating_sentences(text, {"老张秘制海鲜楼"}, ALL_NAMES, CAND)
        assert "老张秘制海鲜楼" not in out and "测试海鲜楼" in out
        assert "出发前确认营业" not in out  # 锚定式剥句：无候选锚的句子不保留

    def test_strip_all_violating_returns_empty(self):
        text = "老张秘制海鲜楼排队。"
        assert strip_violating_sentences(text, {"老张秘制海鲜楼"}, ALL_NAMES, CAND) == ""

    def test_strip_anchored_drops_undetected_fabrication(self):
        """深潜 Q2' inj07 泄漏回归：未被机械规则识别的无后缀编造句，
        因无候选锚而被白名单式剥句丢弃——不能因为'没检出'就保留。"""
        text = ("台东往事小院如果还在的话，肯定是个不错的选择。\n"
                "另外，测试海鲜楼也是一个很受欢迎的苍蝇馆子。")
        out = strip_violating_sentences(text, set(), ALL_NAMES, CAND)
        assert "台东往事小院" not in out
        assert "测试海鲜楼" in out

    def test_undeclared_candidate_intercepted(self):
        """R5b：正文提到候选但漏报 → 违规（强制申报习惯）。"""
        v = check_output(ok_raw("推荐测试海鲜楼和老地方锅贴铺。", ["测试海鲜楼"], []), CAND, ALL_NAMES)
        assert not v.ok and "老地方锅贴铺" in v.violations

    def test_mentions_missing_intercepted(self):
        """缺失 mentions 字段视同漏报。"""
        v = check_output(ok_raw("推荐测试海鲜楼。", ["测试海鲜楼"]), CAND, ALL_NAMES)
        assert not v.ok

    def test_full_declaration_ok(self):
        v = check_output(ok_raw("测试海鲜楼和老地方锅贴铺都在。", ["测试海鲜楼"],
                                ["测试海鲜楼", "老地方锅贴铺"]), CAND, ALL_NAMES)
        assert v.ok, f"误杀: {v.violations}"


class TestExtractMentions:
    def test_longest_first(self):
        text = "别的店烧烤城门口见"
        assert extract_mentions(text, ALL_NAMES) == {"别的店烧烤城"}
