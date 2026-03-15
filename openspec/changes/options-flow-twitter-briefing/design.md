## Context

系统已有 twitterapi.io 接入、LLM adapter 与 SearchService，可复用现有基础设施。@FL0WG0D 推文中异动细节大量存在于图片截图，必须引入 Vision OCR。报告需按“上一交易日”聚合并定时推送。

## Goals / Non-Goals

**Goals**
- 仅基于 @FL0WG0D 推文生成上一交易日异动期权简报
- 接入图片 OCR 提取 Volume / OI / 到期日 / 执行价
- 结合联网搜索，生成可能的异动信息摘要
- 支持 CLI 运行与飞书推送

**Non-Goals**
- 不接入真实期权行情/交易所数据
- 不做历史数据库持久化
- 不做实时流式推送

## Decisions

### 1. 数据源
使用 twitterapi.io `tweet/advanced_search` 拉取上一交易日推文，提取 `entities.media[].media_url_https` 作为图片入口。

### 2. 时间窗口
- 以纽约时区计算“上一交易日”
- 若当前时间 < 16:00 NY，则取前一交易日；否则取当日（已收盘）
- 时间窗固定为 NY 09:30–16:00，并转换为 UTC 格式供 API 使用

### 3. Vision OCR
- 首选 Gemini Flash
- 若未抽取到 Volume/OI/Expiry 等关键字段，回退 Gemini Pro
- OCR 输出要求严格 JSON，失败则丢弃该图片结果

### 4. 结构化与异动判定
- 汇总字段：ticker、call/put、expiry、strike、volume、open_interest、premium(可选)
- 聚合：按 ticker + expiry + strike + call/put 归并
- 排序：优先按 premium / volume / volume_oi_ratio

### 5. 联网搜索
- SearchService：优先 Bocha/Tavily/Brave/SerpAPI
- 查询关键词：`{TICKER} unusual options activity`
- LLM 总结：每个标的 2-3 条“可能驱动”摘要

### 6. 输出与推送
- 输出报告：`reports/options_flow_YYYYMMDD.md`
- 推送：复用 NotificationService（飞书/Telegram/邮箱等）
- 定时脚本：北京时间 10:00

## Module Structure

```
src/options_flow/
├── __init__.py
├── config.py         # 账号与阈值配置、时间窗计算
├── client.py         # twitterapi.io 拉推文（含图片）
├── vision.py         # OCR 与 JSON 解析
├── parser.py         # 文本/图片结构化抽取
├── enricher.py       # 联网搜索 + LLM 摘要
├── formatter.py      # 简报格式化
└── llm.py            # 文本 LLM 调用封装

options_flow_run.py   # CLI 入口
scripts/options_flow_cron.sh
```

## Risks / Trade-offs

- Vision OCR 误识别：通过回退模型与字段校验降低风险
- OpenRouter 模型可能不支持图像：以 Gemini 原生 key 为优先
- 推文格式变化：保留文本正则兜底并允许空字段
