## Context

openclaw 已有完善的飞书推送（Webhook + Stream）、LLM adapter（Claude/OpenAI/Gemini）、定时调度（cron jobs）和格式化工具。本次新增 Twitter 数据源模块，需融入现有架构，复用已有基础设施，最小化新增代码。

twitterapi.io 提供 REST API，通过 `advanced_search` 端点按账号+时间范围查询推文，$0.15/1000条，无需 Twitter 开发者账号。

## Goals / Non-Goals

**Goals**
- 每 8 小时从指定 Twitter 账号拉取推文，经 AI 筛选后推送结构化中文简报到飞书
- 监控账号列表可配置，后期动态扩展
- 复用现有 LLM adapter、notification、formatters 模块
- 支持 `--dry-run` 调试和 `--feishu` 推送两种模式

**Non-Goals**
- 不做实时/紧急推送（后期迭代）
- 不新增数据库存储推文（简报生成即推送，无需持久化）
- 不修改现有模块的接口和行为

## Decisions

### 1. API 客户端设计

使用 `requests` + `tenacity` 封装 twitterapi.io 客户端。

```
GET https://api.twitterapi.io/twitter/tweet/advanced_search
Headers: X-API-Key: {key}
Params: query=from:{account} since:{since} until:{until}&queryType=Latest
```

- 按账号逐个拉取，游标分页处理 `has_next_page` / `next_cursor`
- 时间窗口：当前时间往前 8 小时
- 重试策略：指数退避，最多 3 次

**替代方案**：WebSocket 实时流 → 不选，8h 定时场景用 REST 更简单且成本低。

### 2. AI 筛选与解读

将同一时间窗口内所有账号的推文合并后，单次调用 LLM 完成：
1. 去重：多账号报道同一事件合并
2. 分级：🔴 重大事件 / 🟡 重要动态 / 🔵 市场观点
3. 翻译：英文原文 → 中文解读 + 影响分析

复用 `src/agent/llm_adapter.py`，默认使用当前配置的模型。

**替代方案**：先关键词过滤再送 LLM → 不选，LLM 上下文窗口足够处理 8h 的推文量（通常 <100条），关键词容易漏掉重要信息。

### 3. 简报格式

```
📌 推特金融快讯 | {date} {time} (过去8小时)
━━━━━━━━━━━━━━━━━━━━━━━

🔴 重大事件
  • {事件} → 影响：{分析}
    来源：@{account} {time}

🟡 重要动态
  • {内容}
  • {内容}

🔵 市场观点
  • @{account}：{观点摘要}

⏰ 下次推送：{next_time}
```

使用 `src/formatters.py` 的 `format_feishu_markdown` 转为飞书格式。

### 4. 配置管理

在 `src/twitter_monitor/config.py` 中定义默认配置，支持 `.env` 覆盖：

```python
TWITTER_API_KEY = os.getenv("TWITTER_API_KEY")
MONITOR_ACCOUNTS = ["FirstSquawk", "DeItaone", "KobeissiLetter"]
FETCH_INTERVAL_HOURS = 8
```

后期扩展账号只需修改环境变量或配置文件。

### 5. CLI 入口

`twitter_news_run.py`，与现有 `market_daily_run.py` 风格一致：

```bash
python3 twitter_news_run.py --output report          # 仅输出到终端
python3 twitter_news_run.py --output report --feishu  # 推送飞书
python3 twitter_news_run.py --dry-run                 # 仅拉取推文不分析
```

### 6. 定时调度

在 `cron/jobs.json` 新增任务，cron 表达式 `0 0,8,16 * * *`（北京时间 00:00/08:00/16:00）。

## Risks / Trade-offs

- **twitterapi.io 服务可用性** → 加重试 + 失败不阻塞其他定时任务，推送错误摘要
- **API Key 泄露** → 仅存 `.env`，不入代码库
- **推文量异常大（突发事件）** → LLM 输入设 token 上限，超出时按时间倒序截断
- **推文内容质量** → LLM prompt 要求在信息不足时明确标注，避免幻觉

## Module Structure

```
src/twitter_monitor/
├── __init__.py
├── client.py       # twitterapi.io API 客户端
├── analyzer.py     # AI 筛选 + 简报生成
└── config.py       # 账号列表 + API 配置

twitter_news_run.py  # CLI 入口
```
