"""幻觉回归集主判据测试（问题报告 §2.4-1）——真实 LLM 版。

对真实 API provider 跑全部 50 条回归问法：
机械判据：任何条件下，最终输出中出现的店名/疑似店名 100% ∈ 候选集；
期望拒答的问法必须拒答且不出现任何店名。
防线（guard.check_output 及处置链）是确定性代码：无论真实模型输出什么，
最终输出必须被机械判据约束——这正是要在线验证的属性。

无 OPENAI_API_KEY 时整文件跳过（CI 离线环境不失败）。
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml

from grounded_shop import ShopStore, answer_query
from grounded_shop.guard import extract_mentions, extract_suspect_shopnames
from grounded_shop.llm import EnvBackedLLM

CASES = yaml.safe_load((Path(__file__).parent / "regression_queries.yaml").read_text(encoding="utf-8"))["queries"]
HIT_CASES = [c for c in CASES if not c["expect_refuse"]]
REFUSE_CASES = [c for c in CASES if c["expect_refuse"]]

pytestmark = pytest.mark.skipif(
    not os.environ.get("OPENAI_API_KEY"),
    reason="真实 LLM 回归需要 OPENAI_API_KEY（可选 OPENAI_BASE_URL）",
)


@pytest.fixture(scope="module")
def llm():
    return EnvBackedLLM()


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


@pytest.mark.parametrize("case", HIT_CASES, ids=[c["id"] for c in HIT_CASES])
def test_hit_cases_real_llm(case, store, llm):
    """真实 LLM：命中类问法全部正常输出且锚定候选集（零误杀）。"""
    result = answer_query(case["q"], store, llm)
    assert not result.refused, f"{case['id']}: 不应拒答（候选检索失效？）"
    assert_grounded(result, store, case["id"])


@pytest.mark.parametrize("case", REFUSE_CASES, ids=[c["id"] for c in REFUSE_CASES])
def test_refuse_cases_real_llm(case, store, llm):
    """真实 LLM：拒答类问法必须拒答、话术标准、不含任何店名（拒答在 LLM 之前发生）。"""
    result = answer_query(case["q"], store, llm)
    assert result.refused, f"{case['id']}: 应拒答而未拒答"
    assert_grounded(result, store, case["id"])


def test_regression_set_size():
    """回归集固定 50 条：数量变化必须显式评审（防静默缩水）。"""
    assert len(CASES) == 50, f"回归集应有 50 条，当前 {len(CASES)}"
