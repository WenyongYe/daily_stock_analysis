## ADDED Requirements

### Requirement: LLM generates 2-3 sentence market narrative
系统 SHALL 在生成日报时调用 LLM，基于当日行情数据和新闻摘要，生成 2-3 句中文综合叙事，将行情异动与新闻事件关联解读。

#### Scenario: Normal narrative generation
- **WHEN** 行情数据和新闻摘要均可用
- **THEN** LLM SHALL 返回 2-3 句综合叙事，例如"受美以空袭伊朗影响，油价大涨 2.2%，避险情绪推动黄金上涨、美债收益率走低，道指收跌逾500点。"

#### Scenario: LLM unavailable fallback
- **WHEN** LLM API 调用失败
- **THEN** 跳过综合叙事段，日报其余部分正常生成

### Requirement: Narrative placed after theme section
综合叙事 SHALL 作为独立段落插入在"今日主题"（第一节）之后、"美股指数"（第二节）之前。

#### Scenario: Report structure with narrative
- **WHEN** 综合叙事生成成功
- **THEN** 报告结构为：主题判断 → **综合叙事** → 美股 → 欧亚 → ...
