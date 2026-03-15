## Why

当前 openclaw 的市场日报和深度分析依赖国内财经新闻源，缺乏对全球即时金融快讯的覆盖。@FirstSquawk、@DeItaone、@KobeissiLetter 等 Twitter 账号是华尔街交易员获取突发新闻的核心渠道，能提供央行决策、地缘事件、重大经济数据等第一手信息。接入这些数据源可显著提升系统的信息时效性和全球视野。

## What Changes

- 新增 `twitter_monitor` 模块，通过 twitterapi.io API 定时拉取指定 Twitter 账号的推文
- 新增 AI 筛选与解读层，将原始英文推文过滤、分类、翻译为结构化中文金融简报
- 新增 CLI 入口 `twitter_news_run.py`，复用现有飞书通知通道进行推送
- 新增 cron job，每 8 小时执行一次（北京时间 00:00 / 08:00 / 16:00）
- 监控账号列表可通过配置文件动态添加，无需改代码

## Capabilities

### New Capabilities
- `twitter-api-client`: twitterapi.io API 客户端封装，支持按账号+时间窗口拉取推文、游标分页、错误重试
- `twitter-news-analysis`: AI 驱动的推文筛选与解读，将原始推文转化为分级结构化金融简报（重大事件/重要动态/市场观点）
- `twitter-news-delivery`: 简报生成与飞书推送，复用现有 notification 通道，支持定时调度和 CLI 操作

### Modified Capabilities
（无现有 spec 变更）

## Impact

- 新增文件：`src/twitter_monitor/`（client.py, analyzer.py, config.py）、`twitter_news_run.py`
- 依赖：无新增 pip 依赖（复用现有 `requests`、`tenacity`、LLM adapter）
- 配置：需在 `.env` 中新增 `TWITTER_API_KEY`
- 调度：`cron/jobs.json` 新增 `twitter_news` 定时任务
- 费用：twitterapi.io 约 $0.01/天（3 账号 × 3 次/天）
