# 开源项目调研笔记（T1 · 幻觉接地）

> 调研时间：2026-10-13。所有项目均经独立检索核实存在与机制描述，未核实的点显式标注。
> 本文档是本仓库设计决策的思考源头：每个设计点都能在下面找到出处。

## 1. instructor（jxnl/instructor，现 567-labs/instructor）· 12.2k★

- 仓库：https://github.com/jxnl/instructor
- 定位：LLM 结构化输出库，基于 Pydantic schema 约束模型返回。
- 核心机制：patch 客户端 → 响应强制匹配 Pydantic model → 校验失败自动重试（reask）。
- **借鉴点**：本仓库的事实层从 schema 开始收口——`models.Shop` 用 Pydantic 定义，
  `source` 字段非空是入库硬约束；LLM 输出约定为 JSON（`{"answer", "recommended"}`），
  解析失败即拦截（R1）。本项目不引 instructor SDK，只取其「schema 即契约」思想，
  因为我们的约束对象不是"模型返回格式"而是"返回内容的事实性"。

## 2. guardrails-ai/guardrails · 7.4k★

- 仓库：https://github.com/guardrails-ai/guardrails
- 文档：https://guardrailsai.com/guardrails/docs/concepts/validators
- 核心机制：validator（质量准则）+ on-fail 动作（reask / filter / fix / refrain），
  每次校验产生可追溯的校验历史（iterations 栈）。
- **借鉴点**：`guard.py` 的处置链直接对应——
  RETRY_TRIGGERED（reask）→ STRIP_SENTENCES（filter）→ FALLBACK_TEMPLATE（refrain 的变体：
  不再让模型说，改用零 LLM 模板）。`GuardEvent` 对应其校验历史，作为回归测试与
  周报统计的留痕（验收判据 §2.4-3 的数据基础）。

## 3. ragas（explodinggradients/ragas）· faithfulness 指标

- 文档：https://docs.ragas.io/en/latest/concepts/metrics/available_metrics/faithfulness/
- 核心机制：把答案拆成 claims，逐条核对是否被检索上下文支持，输出 0-1 一致性分。
- **借鉴点与背离**：ragas 是"评估器"（打分，人工看趋势）；本仓库的场景是
  "推荐店名是真是假"（二值，用户会真的跑过去）。打 0.9 分的幻觉依然是幻觉——
  所以我们把 faithfulness 从「评估指标」升级为「硬校验」（R2/R3/R4：违规即拦截降级，
  不存在灰度）。这是评估框架与门禁框架的本质区别，也是本仓库最重要的架构判断。

## 4. promptfoo（promptfoo/promptfoo）

- 仓库：https://github.com/promptfoo/promptfoo
- 文档：https://www.promptfoo.dev/docs/configuration/expected-outputs/（assertions）
  https://www.promptfoo.dev/docs/integrations/ci-cd/（CI 集成）
- 核心机制：声明式 YAML 用例（prompts × providers × asserts），断言类型库
  （contains / is-json / python / llm-rubric 等），CLI 跑评测、CI 门禁。
- **借鉴点**：`tests/regression_queries.yaml` 的形态——50 条真实问法 + 每条期望
  （命中/拒答）+ CI 强制 100% 通过。同一断言集对真实 LLM provider 在线运行，
  验证「不误杀」与「不漏杀」两个方向（无凭证环境自动跳过）。

## 5. 机制对照表

| 本仓库组件 | 思想源头 | 差异（为什么不全搬） |
|---|---|---|
| `models.Shop`（Pydantic） | instructor | 约束对象是入库数据与出口文本，非模型返回 |
| `guard.check_output` R1-R4 | guardrails validators | 校验的是"事实锚定"而非格式/毒性 |
| RETRY→STRIP→FALLBACK 处置链 | guardrails on-fail actions | 兜底是零 LLM 模板，幻觉概率恒为 0 |
| faithfulness 硬化 | ragas | 二值门禁取代 0-1 评分 |
| 50 条回归集 YAML + CI | promptfoo | 不引框架，pytest 原生参数化即可满足 |

## 未采纳的候选

- **LangChain/LlamaIndex RAG 链**：问题报告 §2.3 的选型结论——小语料（30-300 条）
  下向量检索的漏召回仍会把幻觉引进来，结构化查询 + 规则排序更可控。RAG 保留给
  未来「自然语言搜店」入口，且仍需过同一套 guard。
- **NeMo Guardrails**：对话流编排器，对本场景（单轮推荐）过重。
