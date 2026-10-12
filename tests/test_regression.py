"""幻觉回归集主判据测试（问题报告 §2.4-1）。

两个 provider 各跑全部 50 条：
1. TemplateWrapperLLM（忠实）——验证管线正常路径零误杀；
2. HallucinatingLLM(inject_prob=1.0)（每次必注入编造店名）——验证回校防线零漏杀。

机械判据：任何条件下，最终输出中出现的店名/疑似店名 100% ∈ 候选集；
期望拒答的问法必须拒答且不出现任何店名。
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from grounded_shop import ShopStore, answer_query
from grounded_shop.guard import extract_mentions, extract_suspect_shopnames
from grounded_shop.llm import HallucinatingLLM, HALLUCINATION_POOL, TemplateWrapperLLM

CASES = yaml.safe_load((Path(__file__).parent / "regression_queries.yaml").read_text(encoding="utf-8"))["queries"]
HIT_CASES = [c for c in CASES if not c["expect_refuse"]]
REFUSE_CASES = [c for c in CASES if c["expect_refuse"]]


def assert_grounded(result, store: ShopStore, case_id: str) -> None:
    """核心断言：输出文本中出现的店名（库内店名 + 启发式疑似名）必须 ⊆ 候选集。"""
    candidates = result.candidates
    if result.refused:
        assert not candidates, f"{case_id}: 拒答时不应携带候选"
        mentioned = extract_mentions(result.answer, store.all_names)
        assert not mentioned, f"{case_id}: 拒答话术中出现了店名 {mentioned}"
        suspects = extract_suspect_shopnames(result.answer, candidates)
        assert not suspects, f"{case_id}: 拒答话术中出现疑似店名 {suspects}"
        return
    assert candidates, f"{case_id}: 非拒答但候选为空"
    cand_names = {s.name for s in candidates}
    mentioned = extract_mentions(result.answer, store.all_names)
    leaked = mentioned - cand_names
    assert not leaked, f"{case_id}: 输出夹带候选外店名 {leaked}"
    suspects = extract_suspect_shopnames(result.answer, candidates)
    assert not suspects, f"{case_id}: 输出疑似编造店名 {suspects}"
    for fake in HALLUCINATION_POOL:
        assert fake not in result.answer, f"{case_id}: 编造店名 {fake} 泄漏到最终输出"


@pytest.mark.parametrize("case", HIT_CASES, ids=[c["id"] for c in HIT_CASES])
def test_hit_cases_faithful_provider(case, store):
    """忠实 provider：命中类问法全部正常输出且锚定候选集（零误杀）。"""
    result = answer_query(case["q"], store, TemplateWrapperLLM())
    assert not result.refused, f"{case['id']}: 不应拒答（候选检索失效？）"
    assert_grounded(result, store, case["id"])


@pytest.mark.parametrize("case", REFUSE_CASES, ids=[c["id"] for c in REFUSE_CASES])
def test_refuse_cases_faithful_provider(case, store):
    """拒答类问法：必须拒答、话术标准、不含任何店名。"""
    result = answer_query(case["q"], store, TemplateWrapperLLM())
    assert result.refused, f"{case['id']}: 应拒答而未拒答"
    assert_grounded(result, store, case["id"])


@pytest.mark.parametrize("case", HIT_CASES, ids=[c["id"] for c in HIT_CASES])
def test_hit_cases_hallucinating_provider(case, store):
    """必注入幻觉的 provider：每次都被注入编造店名，最终输出仍 100% 干净（零漏杀）。"""
    llm = HallucinatingLLM(TemplateWrapperLLM(), inject_prob=1.0, seed=13)
    result = answer_query(case["q"], store, llm)
    assert llm.injected_count >= 1, f"{case['id']}: 测试前提失败——幻觉未注入"
    assert_grounded(result, store, case["id"])


def test_regression_set_size():
    """回归集固定 50 条：数量变化必须显式评审（防静默缩水）。"""
    assert len(CASES) == 50, f"回归集应有 50 条，当前 {len(CASES)}"
