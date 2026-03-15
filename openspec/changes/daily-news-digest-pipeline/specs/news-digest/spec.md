## ADDED Requirements

### Requirement: Two-stage news filtering pipeline
系统 SHALL 实现两阶段新闻筛选 pipeline：
- **阶段一（本地粗筛）**：基于关键词评分 `_score_item()` 从 50-100 条原始新闻中筛选出 ~25 条高分候选
- **阶段二（LLM 精选）**：将 ~25 条候选新闻发送给 LLM，由 LLM 智能筛选并生成 ~10 条中文分类摘要

#### Scenario: Normal two-stage filtering
- **WHEN** 输入 80 条原始新闻
- **THEN** 阶段一输出 20-30 条评分最高的候选新闻，阶段二输出 8-12 条中文分类摘要

#### Scenario: Insufficient input news
- **WHEN** 输入不足 20 条新闻
- **THEN** 跳过阶段一粗筛，直接将所有新闻发送给 LLM 进行阶段二精选

### Requirement: LLM-powered intelligent selection and summarization
阶段二 LLM 精选 SHALL 执行以下任务：
1. **重要性判断**：基于市场影响力、时效性、信息密度筛选最重要的新闻
2. **语义去重**：合并报道同一事件的不同来源新闻
3. **分类标注**：按主题分类并标注 emoji（🌍 地缘风险、🏦 央行政策、📈 市场走势、⛽ 大宗商品、💻 科技行业、🏢 企业动态 等）
4. **中文总结**：每条新闻用一句简洁中文概括核心信息

#### Scenario: LLM generates categorized Chinese summary
- **WHEN** 向 LLM 提交 25 条英文候选新闻
- **THEN** LLM SHALL 返回 8-12 条按类别分组的中文摘要，格式为带 emoji 的分类列表

#### Scenario: LLM merges duplicate news
- **WHEN** 候选新闻中有 3 条关于同一事件（如 "Fed rate decision"）的不同来源报道
- **THEN** LLM SHALL 合并为 1 条综合摘要，不重复展示

### Requirement: LLM API fallback chain
系统 SHALL 按以下优先级使用 LLM API：
1. `AIHUBMIX_KEY`（优先，中国网络友好）
2. `OPENAI_API_KEY` + `OPENAI_BASE_URL`
3. 无 API 时回退到纯本地评分筛选（不做 LLM 总结，返回英文标题列表）

#### Scenario: Primary API available
- **WHEN** `AIHUBMIX_KEY` 已配置
- **THEN** 使用该 key 调用 OpenAI 兼容 API 进行 LLM 精选

#### Scenario: No API available fallback
- **WHEN** 没有配置任何 LLM API key
- **THEN** 跳过阶段二 LLM 筛选，直接返回阶段一评分最高的 10 条新闻英文标题列表

#### Scenario: LLM API call failure
- **WHEN** LLM API 调用失败（超时、rate limit 等）
- **THEN** 回退到阶段一评分结果，返回前 10 条新闻英文标题列表，并在 stderr 输出错误日志

### Requirement: Seamless integration with market_daily.py
`NewsDigestPipeline` 的输出 SHALL 与现有 `summarize_news_zh()` 的返回格式兼容：
- LLM 成功时返回 `str`（中文分类摘要文本）
- 回退时返回 `list[str]`（英文标题列表）

#### Scenario: Replace summarize_news_zh in market_daily.py
- **WHEN** `market_daily.py` 调用 `NewsDigestPipeline.run()`
- **THEN** 返回值可直接传给 `build_report()` 的 `news_summary` 参数，无需额外转换

### Requirement: Standalone CLI execution
系统 SHALL 支持作为独立脚本运行，用于调试和测试。

#### Scenario: CLI debug run
- **WHEN** 用户执行 `python -m market_daily.providers.news_digest` 或通过入口脚本运行
- **THEN** 打印完整的抓取统计（总数、各源数量、粗筛数、最终精选数）和最终输出到 stdout

### Requirement: LLM prompt optimization for financial news
LLM prompt SHALL 包含以下约束以确保输出质量：
- 优先选择对全球金融市场有直接影响的新闻
- 忽略软新闻、评论文章和市场噪音
- 合并报道同一事件的多条新闻
- 输出严格为中文，不保留英文原文
- 每条摘要控制在 30 字以内

#### Scenario: Prompt produces high-quality output
- **WHEN** 候选新闻包含 3 条关于 Fed 利率决策的新闻和 2 条软新闻
- **THEN** LLM 输出 SHALL 包含 1 条 Fed 相关综合摘要，不包含软新闻
