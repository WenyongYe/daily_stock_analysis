## Phase 1: 知识库 References 文件

- [x] 1.1 创建 `skills/twitter-news-briefing/references/analysis_framework.md`（分级标准 + 去重规则 + 影响评估 + 多源确认机制）
- [x] 1.2 创建 `skills/twitter-news-briefing/references/account_profiles.md`（4个账号画像 + 权重 + 类型）
- [x] 1.3 创建 `skills/twitter-news-briefing/references/prompt_templates.md`（简报模板 + 3 个 few-shot 示例）

## Phase 2: Skill 主文件

- [x] 2.1 创建 `skills/twitter-news-briefing/SKILL.md`（触发条件 + 工作流 + references 引用）
- [x] 2.2 skill 描述包含推荐触发词（推特快讯/推特简报/twitter briefing 等）

## Phase 3: Prompt 外置改造

- [x] 3.1 修改 `src/twitter_monitor/analyzer.py`：从 references 文件加载 prompt，保留 fallback
- [x] 3.2 新增 @financialjuice 到 `src/twitter_monitor/config.py` 默认账号列表

## Phase 4: 验证

- [x] 4.1 执行 `python3 twitter_news_run.py --dry-run` 确认 4 账号（含 financialjuice）拉取正常（159条）
- [x] 4.2 执行 `python3 twitter_news_run.py --output report` 确认 skill references prompt 加载成功（3460字符）
- [x] 4.3 执行 `python3 twitter_news_run.py --output report --feishu` 飞书推送成功
- [x] 4.4 确认简报新增功能生效：多源确认标注✅、账号权重分级、影响评估框架
