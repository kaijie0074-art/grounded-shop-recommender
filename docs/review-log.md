# 评审采纳记录（PR #2）

> 评审者：虚拟评审者（资深后端人设，岗位演练设定——单人无评审环境下以显式标注的
> 模拟评审替代流程缺失）。意见原文见 PR #2 review，本文件记录逐条处置。

| # | 意见 | 严重度 | 处置 | 证据/commit |
|---|---|---|---|---|
| OB-1 | R4 豁免「店名 ⊂ token」放行编造变体（"测试海鲜楼分店"漏杀） | blocker | **采纳**。重构 R4 为两遍检测：pass-1 变体模式（候选名+分店/总店/…，零启发式直接违规）；pass-2 抹除完整店名后跑后缀启发式（合法提及不误杀）。比原"单向子串"方案同时消灭误杀与漏杀。 | `guard.py` 重构 + `test_variant_fabrication_intercepted` / `test_recommended_subset_ok` 回归 |
| OB-2 | 幻觉夹具只有 5 个无形态关联假名，变体形态未覆盖 | major | **采纳**。新增变体注入单测（对启发式函数直接断言）。变体进 50 条回归集不采纳：回归集问法与 provider 注入解耦，注入形态由单测矩阵覆盖更精确。 | `test_extract_suspect_variant` |
| OB-3 | `store.select` 的 `min_rating` 无调用方（死参数） | minor | **采纳**。删除参数。 | `store.py` |
| OB-4 | 测试直接摸 `store._shops` 私有属性 | minor | **采纳**。新增 `all_shops` 公开只读属性，测试改用公开接口。 | `store.py` + `test_store.py` |
| OB-5 | GuardEvent 缺 provider 类名/调用次数，真实 API 重试成本难审计 | question | **暂不采纳，登记后续**。当前 provider 均离线零成本；接入 EnvBackedLLM 时一并引入 token 计量（属 observability 迭代，不阻塞本 PR）。已记入 README 已知局限。 | 本文件 + `docs/test-coverage.md` 已知局限 |

## 修复验证

- 评审前：109 passed（含 1 个已知的变体盲区，评审实测复现）
- 评审后：**111 passed**（+2 评审驱动测试），`run_demo.py` 冒烟正常

## 流程说明

意见提出 → 作者逐条研判（3 采纳 / 1 部分采纳 / 1 登记后续）→ 修复 + 测试 →
评审复核 approve → 负责人验收 → merge。单人无评审岗位的真实缺陷不是"没有评审"，
而是"评审意见没有留痕与追责"——本文件即留痕。

## 2026-10-13 移除模拟 provider

应用户要求移除全部模拟元素：删除 `TemplateWrapperLLM`、`HallucinatingLLM`、
`repro/naive_direct_answer.py`（幻觉注入演示脚本），`EnvBackedLLM`（OpenAI 兼容
真实 API）成为唯一 provider。50 条回归集改为对真实 LLM 在线运行（无凭证自动
跳过）。OB-5 的 token 计量仍未实现，继续登记后续。
