## ADDED Requirements

### Requirement: Multi-source news aggregation with 50-100 items target
系统 SHALL 通过多源并发抓取，单次运行目标获取 50-100 条原始财经新闻。数据源包括：
- Tavily 搜索：8-10 组金融关键词查询，每组返回 8-10 条结果
- RSS feeds：复用现有 `RssFetcher`（MarketWatch、CNBC、Yahoo Finance、Investing.com、Reuters）
- Jina Reader：FT Markets、Reuters Markets 页面标题提取（作为补充源）

#### Scenario: Normal multi-source fetch
- **WHEN** 调用 `NewsAggregator.fetch_all()` 且所有数据源可用
- **THEN** 返回 50-100 条去重后的原始新闻条目，每条包含 `title`、`url`、`snippet`、`source`、`category`、`importance_score`、`fetched_at` 字段

#### Scenario: Partial source failure
- **WHEN** 某个数据源（如 Tavily）不可用
- **THEN** 系统 SHALL 继续从其他可用源抓取，不因单一源失败而中断，最终返回至少 20 条新闻

#### Scenario: All search sources fail
- **WHEN** Tavily 和 RSS 均不可用
- **THEN** 系统 SHALL 回退到 Jina Reader 抓取 FT/Reuters 标题，返回至少 10 条新闻

### Requirement: Extended search query coverage
系统 SHALL 使用 8-10 组搜索查询词，覆盖以下主题领域：
1. 美股市场动态（S&P 500, Nasdaq, Wall Street）
2. 央行政策与宏观数据（Fed, FOMC, CPI, inflation, payroll）
3. 地缘政治风险（tariff, sanction, war, trade conflict）
4. 大宗商品（oil, gold, commodity, OPEC）
5. 科技行业（AI, semiconductor, NVIDIA, earnings）
6. 欧洲/亚洲市场（ECB, BOJ, DAX, Nikkei, China markets）
7. 企业财报/并购（earnings, M&A, IPO, bankruptcy）
8. 加密货币/数字资产（Bitcoin, crypto, digital currency regulation）

#### Scenario: Query coverage validation
- **WHEN** 执行所有搜索查询
- **THEN** 搜索结果 SHALL 覆盖至少 5 个不同主题分类

### Requirement: 24-hour local news cache with deduplication
系统 SHALL 维护本地 JSON 缓存文件 `data/news_digest_cache.json`，存储 24 小时内的已抓取新闻，实现跨运行去重。

#### Scenario: Cache prevents duplicate fetching
- **WHEN** 新闻已存在于缓存中（基于标题指纹匹配）
- **THEN** 该新闻 SHALL 不重复计入本次抓取结果，但 SHALL 参与后续筛选

#### Scenario: Cache auto-cleanup
- **WHEN** 加载缓存时发现超过 24 小时的旧条目
- **THEN** 系统 SHALL 自动清理这些过期条目，保持缓存文件体积可控（最多 500 条）

#### Scenario: Cache file corruption recovery
- **WHEN** 缓存文件损坏或格式错误
- **THEN** 系统 SHALL 忽略缓存并从空缓存开始，不中断正常抓取流程

### Requirement: Concurrent fetching for performance
系统 SHALL 使用 `ThreadPoolExecutor` 并发执行多源数据抓取，避免串行等待。

#### Scenario: Parallel fetch execution
- **WHEN** 启动新闻抓取
- **THEN** RSS 拉取、Tavily 搜索、Jina Reader 抓取 SHALL 并发执行，总耗时不超过 30 秒（正常网络条件下）
