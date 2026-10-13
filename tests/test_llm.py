"""EnvBackedLLM 构造契约：模型/超时经环境变量可配（深潜 Q5 模型对比的前提）。"""
from __future__ import annotations

import pytest

from grounded_shop.llm import EnvBackedLLM


def test_requires_api_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        EnvBackedLLM()


def test_model_env_default(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    monkeypatch.delenv("GROUNDED_SHOP_MODEL", raising=False)
    assert EnvBackedLLM()._model == "glm-4-flash"
    monkeypatch.setenv("GROUNDED_SHOP_MODEL", "glm-5.3-flash")
    assert EnvBackedLLM()._model == "glm-5.3-flash"
    assert EnvBackedLLM(model="explicit-model")._model == "explicit-model"  # 显式参数优先


def test_timeout_env_default(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    monkeypatch.delenv("GROUNDED_SHOP_TIMEOUT", raising=False)
    assert EnvBackedLLM()._timeout == 30
    monkeypatch.setenv("GROUNDED_SHOP_TIMEOUT", "300")
    assert EnvBackedLLM()._timeout == 300
    assert EnvBackedLLM(timeout=120)._timeout == 120
