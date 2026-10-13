"""命令行入口：python -m grounded_shop "青岛台东附近有什么宝藏苍蝇馆子"

使用真实 LLM API（OpenAI 兼容协议）。需要环境变量：
  OPENAI_API_KEY              必填，API 凭证
  OPENAI_BASE_URL             可选，默认智谱开放平台；可指向 DeepSeek 等兼容服务
  GROUNDED_SHOP_MODEL         可选，模型名，默认 glm-4-flash
"""
import os
import sys
from pathlib import Path

from . import ShopStore, answer_query
from .llm import EnvBackedLLM


def main() -> int:
    if not os.environ.get("OPENAI_API_KEY"):
        print(
            "错误：未检测到 OPENAI_API_KEY。\n"
            "请设置后重试，例如：\n"
            "  export OPENAI_API_KEY=your-key\n"
            "  export OPENAI_BASE_URL=https://api.deepseek.com/v1   # 可选，默认智谱\n",
            file=sys.stderr,
        )
        return 2
    llm = EnvBackedLLM(model=os.environ.get("GROUNDED_SHOP_MODEL", "glm-4-flash"))
    query = " ".join(sys.argv[1:]) or "青岛台东附近有什么宝藏苍蝇馆子"
    store = ShopStore.load(Path(__file__).resolve().parents[2] / "data" / "shops.json")
    result = answer_query(query, store, llm)
    print(f"问：{query}")
    print(f"答：\n{result.answer}\n")
    if not result.refused:
        print(f"候选集（输出唯一事实来源）：{sorted(result.candidate_names)}")
    print(f"防线事件：{[e.type for e in result.guard_events]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
