## Why

用户需要基于 @FL0WG0D 推文生成“上一交易日”的美股期权异动简报，并在北京时间 10:00 推送。该账号大量异动信息存在于图片截图中，必须接入 Vision OCR 才能提取 Volume、OI、到期日等关键字段。同时需要联网搜索，为每个标的提供可能的异动驱动摘要。

## What Changes

- 新增 `options_flow` 模块：拉取推文、解析文本+图片、结构化期权异动数据
- 新增 Vision OCR：优先 Gemini Flash，失败回退 Gemini Pro
- 新增联网搜索摘要：基于 SearchService 聚合新闻并调用 LLM 生成异动原因摘要
- 新增 CLI 入口 `options_flow_run.py`，支持 report 输出与飞书推送
- 新增 cron 脚本：北京时间 10:00 推送上一交易日数据
- 新增配置项：账号、Vision 模型、阈值、搜索时效

## Capabilities

### New Capabilities
- `options-flow-twitter-client`: 从 twitterapi.io 拉取指定账号上一交易日推文（含图片）
- `options-flow-vision-ocr`: 解析推文图片，抽取 Volume / OI / Expiry / Strike / CallPut
- `options-flow-briefing`: 期权异动聚合、排序、联网搜索摘要与报告生成

### Modified Capabilities
（无现有 spec 变更）

## Impact

- 新增文件：`src/options_flow/`、`options_flow_run.py`、`scripts/options_flow_cron.sh`
- 新增配置：`OPTIONS_FLOW_*` 相关环境变量
- 依赖：复用现有 requests、tenacity、SearchService、LLM SDK
- 输出：`reports/options_flow_YYYYMMDD.md`
