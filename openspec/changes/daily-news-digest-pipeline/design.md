## Context

当前项目新闻抓取分布在三个独立模块：
- `market_daily.py`：通过 Jina Reader 抓取 FT/Reuters ~15-20 条标题，LLM 直接总结
- `market_daily/providers/news.py`：RSS + Tavily 搜索聚合，关键词评分筛选 ~15 条
- `src/breaking_news.py`：FinancialJuice + RSS 实时监控，每 10 分钟推送

**问题**：单次抓取量少（15-20 条），覆盖面窄，LLM 筛选只在 `market_daily.py` 中做简单总结，没有利用 LLM 的智能筛选能力从大量候选新闻中选出真正重要的。

**现有可复用资源**：
- `NewsProvider`（`market_daily/providers/news.py`）已有完整的 RSS + Tavily + FT 多源聚合、关键词评分、去重逻辑
- `search_service.py` 已有 Tavily/Brave 搜索封装（含 retry、多 key 轮转）
- `breaking_news.py` 的 `RssFetcher` 已有 5 个 RSS 源
- LLM API 调用已有统一封装（`AIHUBMIX_KEY` / `OPENAI_API_KEY`）

## Goals / Non-Goals

**Goals:**
- 单次运行抓取 50-100 条原始新闻（扩大搜索查询数 + 提高每查询返回数 + 多源并发）
- LLM 两阶段筛选：第一阶段关键词 + 评分粗筛到 ~25 条，第二阶段 LLM 精选总结为 ~10 条中文分类摘要
- 24h 本地缓存去重，避免重复抓取同一新闻
- 无缝替换 `market_daily.py` 中的 `summarize_news_zh()`，输出格式保持一致
- 支持独立 CLI 运行（调试/测试用）

**Non-Goals:**
- 不改变 `breaking_news.py` 的实时推送逻辑（那是分钟级推送，与日报是不同场景）
- 不引入新的外部依赖（复用现有 Tavily/RSS/Jina）
- 不做新闻全文抓取和深度分析（保持标题+摘要级别）
- 不构建独立数据库，用 JSON 文件缓存即可

## Decisions

### 1. 扩展现有 NewsProvider 而非新建模块

**选择**：在 `market_daily/providers/news.py` 的 `NewsProvider` 基础上扩展，新增一个 `NewsDigestPipeline` 类作为上层编排器。

**理由**：`NewsProvider` 已有完整的 RSS/Tavily/FT 聚合、评分、去重逻辑，重新实现没有意义。只需：
- 扩大搜索查询列表（从 5 组增加到 8-10 组）
- 提高 `max_per_query`（从 3 增加到 8-10）
- 新增 Jina Reader 源（Reuters/FT/CNBC）作为补充

**替代方案**：新建 `src/news_aggregator.py` 独立模块 → 会重复大量已有逻辑。

### 2. LLM 两阶段筛选策略

**选择**：
- **阶段一（本地）**：复用现有关键词评分 `_score_item()`，扩大阈值从 15 条放宽到 ~25 条
- **阶段二（LLM）**：将 ~25 条候选新闻发送给 LLM，由 LLM 执行：重要性判断 + 去重合并 + 分类 + 中文总结，输出 ~10 条

**理由**：先本地粗筛降低 LLM token 消耗（50-100 条全发给 LLM 太贵），同时保留 LLM 的语义理解优势做最终筛选。

**替代方案**：
- 全部 100 条发 LLM → token 消耗过大，且可能超出 context window
- 纯本地评分不用 LLM → 缺乏语义理解，无法判断新闻间的关联性和真正的市场影响力

### 3. 24h 缓存使用 JSON 文件

**选择**：`data/news_digest_cache.json`，存储 `{fingerprint: {title, url, source, fetched_at, ...}}` 格式，启动时加载，写入时清理 >24h 的旧条目。

**理由**：与现有 `data/breaking_news_seen.json` 风格一致，简单可靠，无需额外依赖。

### 4. 新增搜索查询组覆盖更多领域

扩展查询词从 5 组到 8-10 组，新增：
- 欧洲/亚洲市场新闻
- 加密货币/数字资产
- 企业财报/并购
- 全球债券/外汇重大变动

每组查询 `max_per_query=8-10`，预计：8 组 × 10 条 ≈ 80 条搜索 + 20 条 RSS ≈ 100 条原始。

### 5. LLM API 调用复用现有配置

复用 `AIHUBMIX_KEY` / `OPENAI_API_KEY` + `OPENAI_BASE_URL` + `OPENAI_MODEL`，与 `market_daily.py` 中 `summarize_news_zh()` 的调用方式一致。不引入 Anthropic/Gemini SDK 以保持简单。

## Risks / Trade-offs

- **[Tavily API 配额]** 扩大搜索量后每次运行消耗 8-10 次 Tavily 搜索 → 免费版 1000 次/月，日报每日 1 次 = 约 300 次/月，在免费额度内。如果多次手动运行可能超额。→ 缓存层可减少重复查询。
- **[LLM 成本增加]** 每次日报额外 1 次 LLM 调用（~2000 token input + ~800 token output）→ 使用 gpt-4o-mini 或同等低成本模型，每次 <$0.01。
- **[Jina Reader 限流]** 增加 3 个 Jina 源可能触发限流 → 设置合理间隔，Jina 作为补充源而非必须源，失败不影响整体。
- **[新闻时效性]** 24h 缓存可能包含已过时新闻 → LLM 筛选 prompt 中明确要求优先选择最新、最具市场影响力的新闻。
