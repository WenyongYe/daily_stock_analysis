## 1. OpenSpec 流程与规范

- [x] 1.1 初始化 OpenSpec 项目结构（openspec init）
- [x] 1.2 创建 change：`optimize-breaking-macro-geopolitical-news`
- [x] 1.3 完成 proposal/specs/design/tasks 四个制品

## 2. 新闻聚合优化实现

- [x] 2.1 在 `news.py` 增加重要性评分模型（分类/来源/域名/关键词/时效）
- [x] 2.2 新增去重增强（标题指纹 + URL 归一化）
- [x] 2.3 新增限额策略（总数、每来源、每分类）
- [x] 2.4 将输出控制在默认 15 条，并保留阈值不足时回填机制

## 3. 债券利差修正

- [x] 3.1 停止将 `^IRX` 误读为 2Y 直接参与 2Y-10Y 计算
- [x] 3.2 `macro.py` 明确输出 `spread_2y10y_bp` 单位
- [x] 3.3 `builder.py` 改为 bp 展示并增加缺失数据兜底文案

## 4. 验证与交付

- [x] 4.1 运行 `python3 market_daily_run.py --output report` 验证输出
- [x] 4.2 检查新闻条数、分类分布、来源分布是否符合预期
- [ ] 4.3 生成一版飞书推送摘要并确认可读性
