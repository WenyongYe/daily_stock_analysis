## ADDED Requirements

### Requirement: Deep analysis prompt generates structured multi-theme output
`deep_analysis.py` 中的 `DeepAnalysisGenerator` SHALL 接收 prices、news_summary、macro、calendar 数据，通过单次 LLM 调用生成 3-5 个主题的结构化深度解读。每个主题 MUST 包含四个层次：事件描述、驱动因素、市场影响、前瞻推演。

#### Scenario: Normal market day with mixed signals
- **WHEN** 提供完整的 prices（含涨跌幅）、news_summary（LLM 精选摘要）、macro（VIX + 收益率曲线）、calendar（经济数据）
- **THEN** 返回包含 3-5 个主题的中文深度解读字符串，每个主题按"事件→驱动→影响→推演"结构组织

#### Scenario: Cross-validation between news and price data
- **WHEN** 新闻叙事与行情数据存在矛盾（如新闻报道利好但对应资产下跌）
- **THEN** 解读中 MUST 明确指出矛盾并分析可能原因（如"利好已提前定价"或"市场关注点在其他因素"）

#### Scenario: Cross-event correlation detection
- **WHEN** 多个独立事件/信号指向同一市场方向（如美元走弱 + 黄金上涨 + 美债收益率下行）
- **THEN** 解读中 MUST 包含一段跨事件关联分析，归纳共同指向的宏观叙事

### Requirement: Executive summary generation
`DeepAnalysisGenerator` SHALL 生成 3-5 句的执行摘要，概括今日市场核心主线、最重要驱动事件、资产联动逻辑和后续关注点。

#### Scenario: Generate executive summary from deep analysis
- **WHEN** 深度分析内容已生成
- **THEN** 执行摘要 MUST 覆盖：核心主线定性（1句）、关键驱动（1句）、资产联动（1句）、后续关注（1句）

### Requirement: Graceful degradation when data is incomplete
当部分数据源缺失时，`DeepAnalysisGenerator` SHALL 仍能生成有意义的解读，而非返回空结果。

#### Scenario: News data unavailable
- **WHEN** news_summary 为空字符串或空列表
- **THEN** 仍基于 prices + macro + calendar 生成解读，主题数量可减少至 2-3 个

#### Scenario: LLM API call fails
- **WHEN** LLM API 调用超时或返回错误
- **THEN** 返回 None，由调用方决定是否回退到现有简短叙事
