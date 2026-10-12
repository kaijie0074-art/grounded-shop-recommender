"""LLM 适配层：可插拔 provider，全部遵守同一约定——输出 JSON（instructor 思想的轻量实现：不引 SDK，schema 由管线解析与回校强制）。

三种实现：
1. TemplateWrapperLLM   确定性忠实包装（离线测试/CI 默认）
2. HallucinatingLLM     装饰器：向任意 provider 的输出注入编造店名，模拟真实 LLM 幻觉，
                        用于证明回校防线有效（测试里必须被拦截）
3. EnvBackedLLM         真实 API（读 OPENAI_API_KEY / OPENAI_BASE_URL），本项目 CI 不依赖
"""
from __future__ import annotations

import json
import os
import random
from typing import Protocol

# 与种子库刻意不重叠的编造店名：模拟"格式完全可信的假店"
HALLUCINATION_POOL = [
    "老张秘制海鲜楼",
    "百年老字号王记锅贴总店",
    "台东神话炭火烤肉",
    "李村河鲜舫",
    "深夜食堂青岛第一店",
]

HALLUCINATION_SENTENCES = [
    "另外强烈推荐{fake}，本地人都在排队。",
    "如果不排队，{fake}也是不错的选择。",
    "补充一家隐藏宝藏：{fake}。",
]


class LLMProvider(Protocol):
    def complete(self, system: str, user: str) -> str: ...


class TemplateWrapperLLM:
    """忠实 provider：从 prompt 中的候选 JSON 重新组织语言，只转述、不新增。"""

    def complete(self, system: str, user: str) -> str:
        block = json.loads(user.split("候选店铺数据（唯一事实来源）：", 1)[1].split("\n", 1)[0])
        names = [r["name"] for r in block]
        lines = []
        for r in block:
            tags = "、".join(r["tags"][:3])
            lines.append(
                f"- {r['name']}（{r['address']}）：主打 {tags}，评分 {r['rating']}，人均约 {r['avg_price']} 元。"
            )
        answer = (
            "给你挑了几家靠谱的小店：\n"
            + "\n".join(lines)
            + "\n营业情况可能变化，出发前建议电话确认。"
        )
        return json.dumps({"answer": answer, "recommended": names}, ensure_ascii=False)


class HallucinatingLLM:
    """装饰任意 provider：按概率把编造店名夹带进 answer 文本与 recommended 列表。

    模拟真实 LLM 的幻觉行为。它不是 bug，是测试夹具：回归集必须证明
    即使模型这样输出，最终用户可见文本依然 100% 干净。
    """

    def __init__(self, inner: LLMProvider, *, inject_prob: float = 0.5, seed: int = 42):
        self._inner = inner
        self._inject_prob = inject_prob
        self._rng = random.Random(seed)
        self.injected_count = 0

    def complete(self, system: str, user: str) -> str:
        out = json.loads(self._inner.complete(system, user))
        if self._rng.random() < self._inject_prob:
            fake = self._rng.choice(HALLUCINATION_POOL)
            sentence = self._rng.choice(HALLUCINATION_SENTENCES).format(fake=fake)
            sep = "\n" if out["answer"].endswith(("。", "！", "？")) else " "
            out["answer"] = out["answer"] + sep + sentence
            if self._rng.random() < 0.5:
                out["recommended"] = out["recommended"] + [fake]
            self.injected_count += 1
        return json.dumps(out, ensure_ascii=False)


class EnvBackedLLM:
    """真实 API provider（OpenAI 兼容协议）。仅在显式传入时启用。"""

    def __init__(self, *, model: str = "glm-4-flash", base_url: str | None = None, api_key: str | None = None):
        self._model = model
        self._base_url = base_url or os.environ.get("OPENAI_BASE_URL", "https://open.bigmodel.cn/api/paas/v4/")
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY")
        if not self._api_key:
            raise RuntimeError("EnvBackedLLM 需要 OPENAI_API_KEY；离线环境请用 TemplateWrapperLLM")

    def complete(self, system: str, user: str) -> str:
        import urllib.request

        body = json.dumps(
            {"model": self._model, "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]},
            ensure_ascii=False,
        ).encode("utf-8")
        req = urllib.request.Request(
            f"{self._base_url.rstrip('/')}/chat/completions",
            data=body,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self._api_key}"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        return payload["choices"][0]["message"]["content"]
