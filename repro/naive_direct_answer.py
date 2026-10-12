"""复现材料：v0 直答版（bug 现场快照）——Issue #1 的复现脚本。

这是"修复前"的原始实现：用户问题直接进 prompt，让 LLM 自由推荐。
运行方式（无需任何依赖）：

    python3 repro/naive_direct_answer.py

预期观察到的故障（= Issue #1 的全部要素）：
  1. 输出的店名/地址/评分格式完全可信，但全部是编造的；
  2. 库里明明有 data/shops.json（30 家种子店），直答版根本不读它；
  3. 没有任何校验层，编造内容直达用户；
  4. 每次运行结果不同（不可回归测试）。

本文件在修复 PR (#2) 合并后保留，作为回归演示与新人教材：先跑它看到幻觉，
再跑 run_demo.py 看接地后的输出对比。
"""
import json
import random
from pathlib import Path

# 模拟"语料里旧知识 + 自由发挥"的 LLM：以高置信口吻生成格式可信的假店
FAKE_KNOWLEDGE = [
    ("老台东十六号院海鲜居", "市北区台东六路 16 号", "辣炒蛤蜊、原汁海虹", 4.9),
    ("王记三代祖传锅贴(1912)", "市北区威海路 1 号", "三鲜锅贴、鲅鱼水饺", 4.8),
    ("劈柴院李氏烧烤总店", "市北区营口路 88 号", "烤鱿鱼、烤肉串、散啤", 4.7),
    ("青岛一号苍蝇馆子", "市北区台东三路 9 号", "家常菜、葱烧海参", 4.6),
    ("夜宴台东私房菜", "市北区人和路 66 号", "私房溜肝尖、坛子肉", 4.8),
]


def naive_direct_answer(query: str, seed: int | None = None) -> str:
    rng = random.Random(seed)
    picks = rng.sample(FAKE_KNOWLEDGE, k=min(3, len(FAKE_KNOWLEDGE)))
    lines = [
        f"- {n}（{a}）：招牌 {d}，评分 {r}，本地人强烈推荐。" for n, a, d, r in picks
    ]
    return (
        f"你问「{query}」，这几家绝对不踩雷：\n" + "\n".join(lines) + "\n有问题随时再问我！"
    )


if __name__ == "__main__":
    shops = json.loads((Path(__file__).resolve().parents[1] / "data" / "shops.json").read_text(encoding="utf-8"))
    print("=" * 62)
    print("库内真实（模拟）店名前 5 条：")
    for s in shops["shops"][:5]:
        print(f"  {s['name']}")
    print("=" * 62)
    for q in ["台东有什么宝藏苍蝇馆子", "威海路晚上吃什么", "营口路海鲜推荐"]:
        print(f"\n问：{q}")
        print("答：" + naive_direct_answer(q))
    print("\n→ 观察点：以上输出的店名 0% 命中库内数据，且语气极其自信。")
    print("  这就是 Issue #1：无接地架构下，幻觉是默认行为而非偶发事故。")
