"""语言包装层：prompt 硬约束构建 + 零 LLM 兜底模板。

呼应 T2：《人工智能生成合成内容标识办法》第四条——所有出口文本自带显式标识。
"""
from __future__ import annotations

import json

from .models import Shop

AI_LABEL = "〔内容由 AI 生成，仅供参考，请以实际营业信息为准〕"

SYSTEM_PROMPT = (
    "你是本地美食推荐的文案包装器。你只能介绍用户消息中给出的候选店铺数据，"
    "不得新增、联想、补充任何列表之外的店铺（即使你'知道'它们）。"
    '只输出 JSON：{"answer": string, "recommended": [候选店名子集]}。'
)


def build_user_prompt(query: str, candidates: list[Shop]) -> str:
    rows = [
        {"id": s.id, "name": s.name, "address": s.address, "tags": s.tags, "rating": s.rating, "avg_price": s.avg_price}
        for s in candidates
    ]
    return (
        f"用户问题：{query}\n"
        f"候选店铺数据（唯一事实来源）：{json.dumps(rows, ensure_ascii=False)}\n"
        "请把这些店组织成 2-4 句自然的推荐语。"
    )


def render_template_answer(query: str, candidates: list[Shop]) -> str:
    """兜底模板：完全不经过 LLM，由候选集直接生成——幻觉概率恒等于 0。"""
    lines = [f"- {s.name}（{s.address}）：主打{'、'.join(s.tags[:3])}，评分 {s.rating}。" for s in candidates]
    body = "这几家可以看看：\n" + "\n".join(lines) + "\n出发前建议电话确认营业状态。"
    return f"{body}\n{AI_LABEL}"
