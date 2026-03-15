## Why

现有日报（`market_daily.py`）以数据罗列为主，新闻仅做 30 字概括，叙事只有 2-3 句。专业投资者需要的不是"发生了什么"，而是"为什么发生、意味着什么、后续该关注什么"。需要新增一条深度解读流水线，复用现有数据层，通过分层 LLM prompt 生成叙事驱动的市场解读报告。

## What Changes

- 新增 `market_daily/report/deep_analysis.py`：深度解读生成器，包含分层 prompt（事实→因果→推演→关联）
- 新增 `market_deep.py`：独立入口文件，编排深度解读流程
- 新增 `market_daily/core_deep.py`：深度解读调度器，复用现有 providers，调用 deep_analysis 生成报告
- 现有代码不做修改，两条流水线独立运行

## Capabilities

### New Capabilities
- `deep-analysis-generator`: 分层 LLM prompt 引擎，将行情+新闻+宏观数据转化为 3-5 个主题的深度解读（因果分析、市场影响、前瞻推演、跨事件关联）
- `deep-report-pipeline`: 深度解读流水线编排，复用现有 providers 并发拉取数据，调用深度分析生成器，通过飞书推送

### Modified Capabilities

（无需修改现有能力，两条流水线独立运行）

## Impact

- 新增文件：`market_deep.py`, `market_daily/core_deep.py`, `market_daily/report/deep_analysis.py`
- 复用模块：`providers/prices.py`, `providers/news_digest.py`, `providers/macro.py`, `providers/calendar.py`, `delivery/feishu.py`, `report/theme.py`
- LLM API：新增一次较长的深度分析调用（max_tokens ~2000），token 消耗高于现有叙事生成
- 部署：新增一条 cron 任务（建议比现有日报晚 1-2 小时运行）
