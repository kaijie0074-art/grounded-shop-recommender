"""LLM 适配层：provider 遵守同一约定——输出 JSON（instructor 思想的轻量实现：
不引 SDK，schema 由管线解析与回校强制）。

唯一实现 EnvBackedLLM：真实 API（OpenAI 兼容协议，读 OPENAI_API_KEY /
OPENAI_BASE_URL，默认智谱开放平台）。无凭证时构造即报错并给出配置指引。
"""
from __future__ import annotations

import json
import os
from typing import Protocol


class LLMProvider(Protocol):
    def complete(self, system: str, user: str) -> str: ...


class EnvBackedLLM:
    """真实 API provider（OpenAI 兼容协议）。"""

    def __init__(self, *, model: str | None = None, base_url: str | None = None,
                 api_key: str | None = None, timeout: int | None = None):
        # GROUNDED_SHOP_MODEL/GROUNDED_SHOP_TIMEOUT 支持不改代码切换模型做对比实验
        # （深潜 Q5：glm-5.3-flash reasoning 输出需更长超时，默认 30s 不够）
        self._model = model or os.environ.get("GROUNDED_SHOP_MODEL", "glm-4-flash")
        self._timeout = timeout or int(os.environ.get("GROUNDED_SHOP_TIMEOUT", "30"))
        self._base_url = base_url or os.environ.get("OPENAI_BASE_URL", "https://open.bigmodel.cn/api/paas/v4/")
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY")
        if not self._api_key:
            raise RuntimeError(
                "需要真实 LLM API 凭证：请设置 OPENAI_API_KEY（可选 OPENAI_BASE_URL 指向任意 "
                "OpenAI 兼容服务，如 https://api.deepseek.com/v1）。"
            )

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
        with urllib.request.urlopen(req, timeout=self._timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        return payload["choices"][0]["message"]["content"]
