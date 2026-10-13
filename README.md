# 苍蝇馆子美食发现器

接地式店铺推荐：LLM 只做语言包装，不做事实生成；输出事实性由 guard 机械校验强制。

- 种子店铺数据：`data/shops.json`（30 家，虚构示例数据，字段结构按生产标准）。
- LLM：真实 API（OpenAI 兼容协议），默认智谱 `glm-4-flash`，可用 `OPENAI_BASE_URL` 切换 DeepSeek 等任意兼容服务。

## 运行

```bash
export OPENAI_API_KEY=your-key          # 必填
# export OPENAI_BASE_URL=https://api.deepseek.com/v1   # 可选
python3 run_demo.py "青岛台东附近有什么宝藏苍蝇馆子"
```

## 测试

```bash
python -m pytest tests/ -q
```

- guard / store / query 单元测试离线运行，不依赖 API。
- 50 条幻觉回归集对真实 LLM 在线运行（`tests/test_regression.py`）：最终输出中出现的店名 100% ∈ 候选集；无 `OPENAI_API_KEY` 时自动跳过。
