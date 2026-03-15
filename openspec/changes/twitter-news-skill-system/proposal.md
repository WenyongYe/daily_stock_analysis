## Why

当前 twitter_monitor 模块的分析 prompt 硬编码在 Python 中，缺乏知识库支撑和灵活调整能力。将分析逻辑抽取为 openclaw skill 体系后，可实现：prompt 迭代无需改代码、agent 可通过对话触发分析、复用现有 market-news-analyst 的专家知识库。同时新增 @financialjuice 数据源扩展覆盖面。

## What Changes

- 新增 `twitter-news-briefing` skill，包含主 SKILL.md 和 references 知识库
- 将 `analyzer.py` 的 SYSTEM_PROMPT 外置为可编辑的 Markdown 文件
- 新增 `references/analysis_framework.md`：分级标准、去重规则、影响评估框架
- 新增 `references/account_profiles.md`：监控账号特征和权重定义
- 新增 `references/prompt_templates.md`：简报模板和 few-shot 示例
- 新增 @financialjuice 到默认监控账号列表
- `analyzer.py` 改为从 references 文件加载 prompt

## Capabilities

### New Capabilities
- `twitter-news-briefing-skill`: openclaw skill，定义推特金融快讯的分析工作流、触发条件、输出格式
- `twitter-analysis-knowledge-base`: 可编辑的知识库，包含分级框架、账号画像、简报模板

### Modified Capabilities
（无现有 spec 变更）

## Impact

- 新增文件：`skills/twitter-news-briefing/` 目录及子文件
- 修改文件：`src/twitter_monitor/analyzer.py`（prompt 外置）、`src/twitter_monitor/config.py`（新增 financialjuice）
- 无新增依赖
