## Why

现有新闻抓取分散在多个模块中（`market_daily.py` 用 Jina 抓 FT/Reuters 约 15-20 条标题、`breaking_news.py` 用 RSS/FinancialJuice 做实时推送、`market_daily/providers/news.py` 用 Tavily 搜索），但都存在同一个问题：**单次抓取量太少（15-20 条），覆盖面窄，容易遗漏重要新闻**。需要一个统一的 24h 新闻聚合 pipeline：先广泛抓取 50-100 条原始新闻，再通过 LLM 智能筛选、分类、总结为 10 条左右的精华摘要，提升日报新闻质量。

## What Changes

- **新增独立新闻聚合模块**：统一管理多源新闻抓取（Tavily 搜索、RSS feeds、Jina Reader），单次运行目标抓取 50-100 条原始新闻
- **新增 LLM 两阶段筛选**：第一阶段按重要性打分过滤到 ~20 条，第二阶段 LLM 精选并生成 10 条中文分类摘要
- **新增新闻本地缓存**：JSON 文件存储 24h 内已抓取新闻，支持去重和增量更新
- **集成到 market_daily.py**：替换现有的 `summarize_news_zh()` 函数，使用新 pipeline 输出
- **支持独立运行和定时调度**：可作为独立脚本运行，也可被日报 pipeline 调用

## Capabilities

### New Capabilities
- `news-aggregator`: 多源新闻抓取引擎，整合 Tavily 搜索（多关键词批量查询）、RSS feeds（MarketWatch/CNBC/Yahoo Finance 等）、Jina Reader（FT/Reuters），目标 50-100 条/24h，带去重和本地缓存
- `news-digest`: LLM 两阶段筛选 pipeline，从 50-100 条原始新闻中智能筛选并生成 10 条精华中文分类摘要

### Modified Capabilities
<!-- 无需修改现有 spec，但实现时会替换 market_daily.py 中的 summarize_news_zh -->

## Impact

- **新增文件**: `src/news_aggregator.py`（聚合引擎）、`src/news_digest.py`（LLM 筛选）
- **修改文件**: `market_daily.py`（替换 `summarize_news_zh` 调用为新 pipeline）
- **数据文件**: `data/news_cache.json`（24h 新闻缓存）
- **依赖**: 复用现有 `tavily-python`、`requests`、`feedparser`（可能需新增）
- **API 调用**: LLM API 调用量增加（每次日报额外 1-2 次 API 调用用于筛选）
- **环境变量**: 复用现有 `TAVILY_API_KEYS`、`OPENAI_API_KEY`/`AIHUBMIX_KEY` 等
