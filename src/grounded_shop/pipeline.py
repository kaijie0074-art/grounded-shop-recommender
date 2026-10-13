"""管线编排：解析 → 规则排序 → LLM 包装（受限）→ 回校 → 拒答/兜底。

架构决策（问题报告 §2.3 方案 C）：
LLM 只负责把候选记录组织成人话；决定"推荐哪家店"的是 store.select 的规则。
"""
from __future__ import annotations

from . import answer as answer_mod
from . import guard
from .llm import EnvBackedLLM, LLMProvider
from .models import GuardEvent, PipelineResult
from .store import ShopStore
from .wrappers import AI_LABEL, SYSTEM_PROMPT, build_user_prompt, render_template_answer
from .query import parse_query


def answer_query(query: str, store: ShopStore, llm: LLMProvider | None = None) -> PipelineResult:
    # 拒答路径（覆盖外/无信号/无候选）不触达 LLM，无需凭证即可运行；
    # 凭证检查推迟到真正需要调用 LLM 时
    pq = parse_query(query)

    if pq.out_of_coverage:
        text, ev = answer_mod.refuse_out_of_coverage()
        return PipelineResult(answer=text, guard_events=[ev], refused=True)

    if not pq.areas and not pq.tags and pq.max_price is None:
        # 纯闲聊/无美食信号：不猜、不推荐，引导到可回答的问题（防"强行推荐"幻觉）
        text, ev = answer_mod.refuse_no_match(query_hint="没识别到区域或品类")
        return PipelineResult(answer=text, guard_events=[ev], refused=True)

    candidates = store.select(pq)
    if not candidates:
        text, ev = answer_mod.refuse_no_match(query_hint=query[:30])
        return PipelineResult(answer=text, guard_events=[ev], refused=True)

    if llm is None:
        llm = EnvBackedLLM()
    events: list[GuardEvent] = []
    all_names = store.all_names

    raw = llm.complete(SYSTEM_PROMPT, build_user_prompt(query, candidates))
    verdict = guard.check_output(raw, candidates, all_names)

    if verdict.ok:
        events.append(GuardEvent(type="PASS", detail="first_pass"))
        final_text = verdict.answer
    else:
        # 处置链第 1 步：重试一次（guardrails 的 reask 动作）
        events.append(GuardEvent(type="RETRY_TRIGGERED", detail=f"violations={sorted(verdict.violations)} parse_error={verdict.parse_error}"))
        raw2 = llm.complete(SYSTEM_PROMPT, build_user_prompt(query, candidates))
        verdict2 = guard.check_output(raw2, candidates, all_names)
        if verdict2.ok:
            events.append(GuardEvent(type="RETRY_PASSED", detail="retry_clean"))
            final_text = verdict2.answer
        else:
            # 第 2 步：剥离违规句（guardrails 的 filter 动作）
            stripped = guard.strip_violating_sentences(verdict2.answer, verdict2.violations, all_names)
            if stripped and not (guard.extract_mentions(stripped, all_names) & verdict2.violations):
                events.append(GuardEvent(type="STRIP_SENTENCES", detail=f"stripped={sorted(verdict2.violations)}"))
                final_text = stripped
            else:
                # 第 3 步：零 LLM 兜底模板——幻觉概率恒为 0
                events.append(GuardEvent(type="FALLBACK_TEMPLATE", detail=f"violations={sorted(verdict2.violations)}"))
                final_text = render_template_answer(query, candidates)

    if AI_LABEL not in final_text:
        final_text = f"{final_text}\n{AI_LABEL}"
    return PipelineResult(answer=final_text, candidates=candidates, guard_events=events, refused=False)
