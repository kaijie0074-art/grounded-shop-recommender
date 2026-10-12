"""命令行演示：python -m grounded_shop "青岛台东附近有什么宝藏苍蝇馆子"

可选：GSR_REAL_LLM=1 且 OPENAI_API_KEY 存在时走 EnvBackedLLM（真实 API），
否则使用离线确定性 provider，保证任何环境可复现。
"""
import os
import sys
from pathlib import Path

from . import ShopStore, answer_query
from .llm import EnvBackedLLM, LLMProvider, TemplateWrapperLLM


def pick_llm() -> LLMProvider:
    if os.environ.get("GSR_REAL_LLM") == "1" and os.environ.get("OPENAI_API_KEY"):
        return EnvBackedLLM()
    return TemplateWrapperLLM()


def main() -> int:
    query = " ".join(sys.argv[1:]) or "青岛台东附近有什么宝藏苍蝇馆子"
    store = ShopStore.load(Path(__file__).resolve().parents[2] / "data" / "shops.json")
    result = answer_query(query, store, pick_llm())
    print(f"问：{query}")
    print(f"答：\n{result.answer}\n")
    if not result.refused:
        print(f"候选集（输出唯一事实来源）：{sorted(result.candidate_names)}")
    print(f"防线事件：{[e.type for e in result.guard_events]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
