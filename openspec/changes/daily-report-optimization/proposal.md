## Why

当前日报存在五个核心问题：
1. 第六节标题写"未来一周"但数据是过去的，且大量空值事件信息价值低
2. 飞书推送时表格乱码、报告过长可能被截断
3. "后续关注"写死通用话术，每天雷同
4. 行情和新闻割裂，缺少把两者关联的综合分析
5. 缺少加密货币行情数据（已有新闻分类但无价格）

## What Changes

- **修复宏观事件板块**：标题改为"本周宏观事件"，过滤掉无 actual 数据的空事件，仅保留有实际数据或即将发生的高影响事件
- **飞书推送格式优化**：表格转纯文本列表、控制总长度、分段推送长报告
- **后续关注动态化**：结合当日实际行情数据和日历事件生成，不再使用写死话术
- **新增 LLM 综合分析段**：在主题判断后增加 2-3 句核心叙事，将行情异动与新闻事件关联
- **新增加密货币行情**：在价格 Provider 中加入 BTC、ETH 行情，报告新增独立小节

## Capabilities

### New Capabilities
- `llm-market-narrative`: LLM 生成的 2-3 句市场综合叙事，关联行情异动与新闻事件
- `crypto-prices`: BTC/ETH 行情数据采集与展示

### Modified Capabilities
<!-- 无现有 spec 需要修改 -->

## Impact

- **修改文件**: `market_daily/report/builder.py`（飞书格式、宏观事件过滤、新增综合分析段、加密货币节）、`market_daily/report/theme.py`（后续关注动态化）、`market_daily/delivery/`（飞书推送优化）、`market_daily/providers/prices.py`（加密货币 ticker）
- **API 调用**: 每次日报额外 1 次 LLM 调用生成综合叙事（~1500 token）
- **依赖**: 无新增依赖，BTC/ETH 用 yfinance 即可
