## Why

当前新闻聚合会一次性塞入大量条目（可达 100+），噪声高、重复多、来源质量不稳定，导致真正重要的突发财经/宏观/地缘新闻不够突出。需要将新闻流从“全量抓取”升级为“高优先级情报流”。

## What Changes

- 增加新闻重要性评分（分类权重 + 来源权重 + 域名权重 + 突发关键词 + 时效）
- 增加聚合后筛选策略：总数上限、按来源上限、按分类上限、最低分阈值
- 优化分类与去重：标题指纹 + URL 归一化双重去重
- 调整债券利差展示：避免 `^IRX` 被误读为 2Y，改为 macro 曲线优先并用 bp 展示
- 保持多源容灾：RSS 主源 + Tavily 搜索补充 + FT 回退

## Capabilities

### New Capabilities
- `news-priority-fusion`: 多源新闻融合后按重要性排序并筛选
- `breaking-signal-detection`: 对突发/宏观/地缘信号进行关键词与时效加权
- `focus-report-output`: 报告仅输出高价值新闻集（控制在 12~18 条）

### Modified Capabilities
- （无）

## Impact

- 代码影响：
  - `market_daily/providers/news.py`
  - `market_daily/report/builder.py`
  - `market_daily/providers/macro.py`
  - `market_daily/providers/prices.py`
- 输出影响：日报新闻段从“全量堆叠”改为“精选情报流”
- 风险：阈值过严可能漏报，需保留回填机制与日志观测
