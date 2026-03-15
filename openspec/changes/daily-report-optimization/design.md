## Context

日报由 `market_daily/` 包生成，核心链路：`core.py`（调度）→ 4 个 Provider（prices/macro/news/calendar）→ `report/builder.py`（渲染）→ `delivery/`（推送）。`report/theme.py` 负责 Risk-Off/On 判断和后续关注生成。

## Goals / Non-Goals

**Goals:**
- 宏观事件板块只展示有价值的事件（有 actual 数据的 + 未来 3 天内的高影响事件）
- 飞书推送可读性大幅提升（无乱码表格、不超长）
- 后续关注每天不同，紧贴当日行情
- 新增 1 段 LLM 综合叙事放在主题判断后、行情数据前
- BTC/ETH 行情展示

**Non-Goals:**
- 不改变整体 8 节结构
- 不加 A 股/中概
- 不改动新闻精选 pipeline（刚做完）

## Decisions

### 1. 宏观事件过滤逻辑
在 `builder.py` 的 `_calendar()` 中过滤：保留 `actual` 非空的已公布事件 + 未来 3 天内的待公布事件。标题改为"本周宏观事件"（去掉"未来"二字）。

### 2. 飞书推送优化
在 `delivery/` 的飞书模块中：
- 表格（宏观事件）转为 `事件名: 实际值 vs 预期值 (解读)` 纯文本格式
- 总字符超过 15000 时截断并附"完整版见文件"提示
- 保留 emoji，去除 Markdown 链接语法

### 3. LLM 综合叙事
在 `core.py` 中新增一步：把 prices 摘要 + news 摘要 + theme 判断拼成 prompt，调 LLM 生成 2-3 句中文综合叙事，插入到报告第一节（主题判断）之后。复用 `news_digest.py` 中已有的 `_call_llm()` 函数。

### 4. 后续关注动态化
`theme.py` 的 `watch` 列表改为完全动态生成：
- 删除写死的"NFP就业报告、CPI通胀数据"
- 从 calendar 事件中提取未来 3 天内的高影响事件名作为关注点
- 结合当日异动指标（哪些涨跌超阈值）生成针对性关注

### 5. 加密货币行情
在 `prices.py` 的 SYMBOLS 中加入 `BTC-USD` 和 `ETH-USD`。`builder.py` 新增 `_crypto()` 小节，放在外汇和债券之间。

## Risks / Trade-offs

- **[LLM 叙事额外延迟]** 多一次 LLM 调用 ~3-5s → 可与新闻精选并行，总延迟增加可控
- **[飞书截断]** 15000 字符阈值可能丢失尾部信息 → 关键信息（主题+叙事+新闻）在报告前半段，不受影响
- **[后续关注依赖 calendar]** ForexFactory 数据质量不稳 → 兜底保留 1-2 条通用关注点
