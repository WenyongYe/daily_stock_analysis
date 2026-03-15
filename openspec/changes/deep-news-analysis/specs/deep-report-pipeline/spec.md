## ADDED Requirements

### Requirement: Deep report pipeline orchestration
`core_deep.py` SHALL 并发调用现有 PriceProvider、MacroProvider、NewsDigestPipeline、CalendarProvider，然后将数据传递给 DeepAnalysisGenerator 生成深度解读报告。

#### Scenario: Full pipeline execution
- **WHEN** 执行 `python market_deep.py`
- **THEN** 依次完成：并发数据拉取 → 主题分析 → 深度解读生成 → 报告组装 → 输出/推送

#### Scenario: Feishu delivery
- **WHEN** 运行时指定 `--feishu` 参数
- **THEN** 通过现有 FeishuDelivery 将深度解读报告推送到飞书

### Requirement: Deep report format
深度解读报告 SHALL 采用叙事驱动结构，与现有数据驱动日报形成互补。

#### Scenario: Report structure
- **WHEN** 报告生成完成
- **THEN** 报告 MUST 按以下顺序组织：标题 → 执行摘要(3-5句) → 深度主题解读(3-5个) → 行情速览(精简表格) → 后续关注事项 → 页脚

#### Scenario: Report saved to file
- **WHEN** 运行时指定 `--output report`
- **THEN** 报告保存至 `reports/market_deep_YYYYMMDD.md`

### Requirement: Independent entry point
`market_deep.py` SHALL 作为独立入口，支持与 `market_daily.py` 相同的命令行参数风格。

#### Scenario: CLI arguments
- **WHEN** 用户运行 `python market_deep.py --feishu`
- **THEN** 执行深度解读流水线并推送飞书

#### Scenario: Default execution
- **WHEN** 用户运行 `python market_deep.py` 不带参数
- **THEN** 执行深度解读流水线并将报告打印到控制台
