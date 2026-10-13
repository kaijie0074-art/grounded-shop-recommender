# 真实 LLM 在线回归实跑记录 · 2026-10-13

## 幻觉回归集（50 条问法 × 真实 LLM）

```bash
export OPENAI_BASE_URL=https://open.bigmodel.cn/api/coding/paas/v4   # 智谱 GLM Coding Plan（OpenAI 兼容）
export OPENAI_API_KEY=<凭证经环境变量注入，不入库>
.venv/bin/python -m pytest tests/test_regression.py -q
```

结果：

```
51 passed in 329.60s (0:05:29)
```

- 模型：glm-4-flash（默认，Coding Plan 订阅内）
- 覆盖：命中类问法全部正常输出且店名 100% ∈ 候选集（零误杀）；拒答类问法全部拒答且不含任何店名（零漏杀）
- 判据对应：docs/test-coverage.md S14/S15/S22

## 环境说明

- 端点为智谱 GLM Coding Plan 专属 OpenAI 兼容端点，非开放平台标准端点
- 凭证不落盘：通过 `OPENAI_API_KEY` 环境变量注入，本文件与仓库任何位置均不含密钥
- CI 离线路径不受影响：无凭证时 `test_regression.py` 整文件跳过
