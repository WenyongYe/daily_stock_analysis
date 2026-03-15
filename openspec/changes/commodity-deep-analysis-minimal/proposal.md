## Why

用户需要日报中稳定包含黄金/白银/原油的客观深度解读，并要求最小化改动，仅在日报结果体现，便于快速验收。

## What Changes

- 强化 `market_daily/report/deep_analysis.py` 的深度分析 prompt：
  - 强制输出 Gold / Silver / Crude 三段结构化解读
  - 每段包含：事件、驱动因素、市场影响、定价状态、前瞻推演、可信度
  - 明确要求跨资产验证（DXY / US10Y / 商品价格）
- 在 `market_daily/core_deep.py` 增加轻量商品新闻聚合（基于现有新闻文本关键词筛选），作为 deep prompt 额外上下文
- 保持现有 pipeline 和 provider 不变，不新增数据源，不改调度

## Capabilities

### Modified Capabilities
- `deep-analysis-generator`：增强商品维度输出约束，提升日报可验收性
- `deep-report-pipeline`：增加商品相关新闻上下文注入，提升黄金/白银/原油分析稳定性

## Impact

- 修改文件：
  - `market_daily/report/deep_analysis.py`
  - `market_daily/core_deep.py`
- 不新增第三方依赖
- 向后兼容：LLM 失败时仍保持降级报告输出
