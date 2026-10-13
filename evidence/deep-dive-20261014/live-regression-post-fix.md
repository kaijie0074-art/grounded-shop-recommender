# 修复后真实 LLM 在线回归 · 2026-10-14（深潜加固后）

## glm-4-flash（默认模型）

```bash
export OPENAI_BASE_URL=https://open.bigmodel.cn/api/coding/paas/v4
export GROUNDED_SHOP_TIMEOUT=120   # 共享配额下偶发慢调用
.venv/bin/python -m pytest tests/ -q
```

结果：**88 passed in 308.64s**（37 离线 + 51 在线回归，含 R4b/R4c/R5 新契约）。

## glm-5.3-flash（模型对比）

```bash
export GROUNDED_SHOP_MODEL=glm-5.3-flash GROUNDED_SHOP_TIMEOUT=300
.venv/bin/python -m pytest tests/test_regression.py -q
```

结果：**51 passed in 346.26s**（reasoning 模型，content 字段干净 JSON，无围栏）。

## 说明

- 两代模型在加固后的 guard（R1-R5）下 50 条幻觉回归全部通过：命中类输出
  100% 锚定候选集，拒答类话术标准且零店名。
- 与 2026-10-13 基线（evidence/live-llm-run-20261013.md）的差异：输出契约新增
  mentions 字段（R5），JSON 解析容错（R1），谐音/拉丁/无后缀编造的检测与
  锚定式剥句（Q2/Q2'，见 docs/research/deep-dive-20261014.md）。
- 凭证经环境变量注入，不落盘。
