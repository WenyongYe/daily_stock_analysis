## Context

现有 `market_daily` 流水线采用数据驱动模式：并发拉取 prices/macro/news/calendar → 生成简短叙事(2-3句) + 数据注释 → 拼接 Markdown 日报。新闻处理经过两阶段（50-100条→本地粗筛25条→LLM精选10条30字摘要），但缺乏深度因果分析和前瞻推演。

现有可复用模块：
- `providers/prices.py` — PriceProvider（yfinance 行情）
- `providers/news_digest.py` — NewsDigestPipeline（多源聚合+LLM精选）
- `providers/macro.py` — MacroProvider（VIX + 收益率曲线）
- `providers/calendar.py` — CalendarProvider（ForexFactory 经济日历）
- `report/theme.py` — analyze_theme（主题判断）
- `delivery/feishu.py` — FeishuDelivery（飞书推送）

## Goals / Non-Goals

**Goals:**
- 新增独立的深度解读流水线，与现有日报并行运行互不干扰
- 生成叙事驱动的深度分析报告（3-5个主题，每个包含因果+影响+推演）
- 行情数据与新闻叙事交叉验证（如新闻说利好但股市跌，需指出矛盾）
- 跨事件关联分析（多个信号指向同一方向时归纳）
- 复用现有 providers 和 delivery，零重复代码

**Non-Goals:**
- 不修改现有日报流水线的任何代码
- 不做实时推送或盘中更新（仍为每日定时运行）
- 不做投资建议或具体操作策略
- 不新增数据源（使用现有 providers 已有的数据）

## Decisions

### 1. 分层 Prompt 架构（单次 LLM 调用）

**决策**：使用单次 LLM 调用，在一个结构化 prompt 中要求模型按 事实→因果→推演→关联 的顺序输出。

**备选**：多次 LLM 调用（先提取事实，再推理因果，再做推演）。

**理由**：单次调用延迟低、成本低，且现代 LLM 在结构化长文输出上已足够可靠。如果未来质量不够可拆分为多步。

### 2. 独立调度器 `core_deep.py`

**决策**：新增 `core_deep.py` 作为深度解读的调度器，与 `core.py` 平级。

**备选**：在 `core.py` 中加参数切换模式。

**理由**：两条流水线的 LLM 调用逻辑和报告模板完全不同，混在一起会增加复杂度。独立文件更清晰，也便于独立调整 cron 时间。

### 3. 报告结构：叙事在前，数据在后

**决策**：深度解读报告以"执行摘要 → 主题深度分析 → 行情数据（精简）→ 后续关注"为结构。

**理由**：与现有日报的"数据在前"形成互补。专业读者先看解读判断市场主线，再按需查看具体数据。

### 4. LLM 配置复用

**决策**：复用现有 `AIHUBMIX_KEY`/`OPENAI_API_KEY` 和 `OPENAI_MODEL` 环境变量，但 deep analysis 使用更高的 `max_tokens`（~2000）和略低的 `temperature`（0.2）。

**理由**：保持配置统一，只在调用参数上区分。

## Risks / Trade-offs

- **LLM 输出质量波动** → 通过详细的结构化 prompt 和示例约束输出格式；设置 temperature=0.2 降低随机性
- **Token 消耗增加** → 深度分析每次约 2000 output tokens，比现有叙事(300 tokens)高 6-7 倍；但每日仅运行一次，成本可控
- **新闻与行情时间不匹配** → 建议深度解读 cron 比日报晚 1-2 小时运行，确保行情数据更完整
- **报告过长不适合飞书阅读** → 控制在 3-5 个主题，每个主题 4-6 行，总长度约 800-1200 字
