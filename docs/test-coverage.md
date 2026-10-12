# 测试覆盖场景说明（T1）

> 每个产品场景 ↔ 测试的映射。测试不是"覆盖率数字"，是"场景清单的可执行形式"。

## 场景矩阵

| # | 场景 | 期望行为 | 测试 |
|---|---|---|---|
| S1 | 正常问法（区域+品类） | 输出候选集内店铺，PASS 直通 | `test_hit_cases_faithful_provider[q01-q37]` |
| S2 | 口语变体（"宝藏/撸串/求推荐/哪家好"） | 词典归一化后同 S1 | 同上（q04/q06/q22 等） |
| S3 | 预算约束（"人均50以内"） | 过滤超价候选；预算内无店 → 拒答 | q09/q17/q30/q31/q34 + `test_budget_filter` |
| S4 | 泛美食问法（"有什么美食"） | 不做品类过滤，推高分店 | q28/q35 + `test_generic_food_query_gets_any_tag` |
| S5 | 未覆盖区域（李沧/市南…） | 区域未覆盖拒答，提示已覆盖范围 | q36-q41 + `test_refusal_logged_as_event` |
| S6 | 库内无此品类（法餐/日料/火锅/素食） | 无匹配拒答，引导到已收录品类 | q42-q44/q47 + `test_no_match_refusal_mentions_known_tags` |
| S7 | 区域×品类组合无匹配（登州路+馄饨） | 无匹配拒答 | q45/q46 |
| S8 | 约束过窄（预算内无海鲜） | 无匹配拒答 | q31/q34 |
| S9 | 纯闲聊/无美食信号（天气/写诗/电影） | 不强行推荐，拒答引导 | q48-q50 + pipeline 闲聊分支 |
| S10 | LLM 推荐列表夹带候选外店名（R2） | 拦截 → 处置链 | `TestR2RecommendedSubset` |
| S11 | LLM 文本夹带库内其他店（R3） | 拦截 → 处置链 | `TestR3CrossMention` |
| S12 | LLM 完全编造店名（R4） | 拦截 → 处置链 | `TestR4FabricatedName` |
| S13 | LLM 输出不可解析（R1） | 拦截 → 处置链 | `TestR1Parse` |
| S14 | 必注入幻觉（每轮都编造） | 最终输出 0 泄漏（零漏杀） | `test_hit_cases_hallucinating_provider[35 条]` |
| S15 | 忠实输出被误杀（假阳性） | 0 误杀，PASS 直通 | `test_hit_cases_faithful_provider` 全绿 |
| S16 | 处置链逐级降级 | 剥句保干净句；全违规 → 空串触发兜底 | `TestStrip` |
| S17 | 数据时效：超期未复验（>90 天） | 隐藏不进候选 | `test_staleness_hides_expired` |
| S18 | 排序可解释性：高分在前 | 评分降序 | `test_rating_ranking_explainable` |
| S19 | 数据可追溯：来源 100% 非空 | 校验失败即拒绝入库 | `test_all_sources_nonempty` / `test_source_placeholder_rejected` |
| S20 | 数据诚信：种子集显式标注模拟 | `_meta.dataset` 断言 | `test_dataset_marked_simulated` |
| S21 | 回归集防缩水 | 固定 50 条 | `test_regression_set_size` |
| S22 | bug 现场可复现 | repro 脚本保持可运行 | CI 独立步骤 |

## 判据对应（问题报告 §2.4）

1. 回归集 100% 命中 → S1-S9 + S14/S15（共 109 项断言，CI 强制）
2. 编造名拦截 → S10-S14、S16
3. 拒答留痕可观测 → S5/S6 + GuardEvent 结构
4. 来源可追溯 → S19/S20

## 已知局限（诚实清单）

- R4 是启发式：理论存在构造出"不含任何店名后缀"的编造名（如"台东往事"）绕过检测。
  防线纵深依赖 R2（recommended 白名单）——文本绕过 R4 时，列表通常仍会暴露。
  真实生产接入 NER 或让 LLM 以结构化字段输出全部提及实体（本仓库 R2 已覆盖此路径）。
- 词典解析覆盖台东商圈词表；新区域/新品类需要扩词典（`query.py` 顶部集中维护）。
- 拒答话术与兜底模板文案为硬编码，产品化时应走配置。
