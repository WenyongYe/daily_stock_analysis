## Context

openclaw skill 体系通过 `SKILL.md` + `references/` 目录为 agent 提供领域知识和工作流指令。现有 `market-news-analyst` skill 已建立了完善的金融分析知识库（地缘商品关联、可信源分级、市场事件模式等）。本次将推特快讯分析模块化为独立 skill，并复用现有知识库。

## Goals / Non-Goals

**Goals**
- Phase 1：Prompt 外置，`analyzer.py` 从 references 文件加载分析指令
- Phase 2：创建完整 `twitter-news-briefing` skill，含知识库和模板
- Phase 3：新增 @financialjuice 数据源，优化去重逻辑
- 使用 skill-creator 工具创建和验证每个子模块

**Non-Goals**
- 不重构 client.py 和推送逻辑
- 不做实时推送
- 不修改现有 market-news-analyst skill

## Decisions

### 1. Skill 目录结构

```
skills/twitter-news-briefing/
├── SKILL.md                          # 主入口：触发条件 + 工作流
└── references/
    ├── analysis_framework.md         # 分级标准 + 去重规则 + 影响评估
    ├── account_profiles.md           # 监控账号画像和权重
    └── prompt_templates.md           # 简报模板 + few-shot 示例
```

### 2. Prompt 加载机制

`analyzer.py` 改为运行时读取 references 文件拼接 prompt：

```python
def _load_prompt():
    refs_dir = Path(SKILLS_DIR) / "twitter-news-briefing" / "references"
    framework = (refs_dir / "analysis_framework.md").read_text()
    templates = (refs_dir / "prompt_templates.md").read_text()
    return f"{framework}\n\n{templates}"
```

若 skill 文件不存在则 fallback 到内置默认 prompt，保证系统健壮性。

### 3. 知识库设计

**analysis_framework.md**：
- 三级分类标准（🔴🟡🔵）及量化阈值
- 去重合并规则（同一事件多源报道的判定标准）
- 影响评估框架（复用 market-news-analyst 的 impact score 方法论）
- 多源确认机制（单源标注⚠️，双源+标注✅）

**account_profiles.md**：
- 每个账号的类型（突发快讯/宏观分析/综合聚合）
- 权重等级（突发源可触发🔴、分析源限🟡🔵）
- 账号特征描述，帮助 LLM 理解来源可信度

**prompt_templates.md**：
- 简报输出模板（固定格式）
- 3 个 few-shot 示例（覆盖：有重大事件、仅有日常动态、无重要新闻三种场景）

### 4. @financialjuice 接入

直接在 config.py 默认列表中新增，无需额外适配。该账号发布格式与 FirstSquawk 类似（短文本快讯），现有分析流程完全兼容。

## Risks / Trade-offs

- Skill 文件被误删 → fallback 机制保证不中断
- References 文件过大影响 LLM token 使用 → 控制总量 <3000 字
- Few-shot 示例可能引导 LLM 过度模式化 → 示例选取多样化场景
