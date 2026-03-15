## 1. 深度解读生成器

- [x] 1.1 创建 `market_daily/report/deep_analysis.py`，实现 `DeepAnalysisGenerator` 类，包含分层 prompt（事实→因果→推演→关联）和 `generate()` 方法
- [x] 1.2 实现数据预处理：将 prices/news/macro/calendar 压缩为结构化 prompt 输入文本
- [x] 1.3 实现执行摘要生成：从深度分析结果中提炼 3-5 句 executive summary
- [x] 1.4 实现降级逻辑：数据不完整时减少主题数量，LLM 失败时返回 None

## 2. 深度解读报告模板

- [x] 2.1 在 `deep_analysis.py` 中实现 `build_deep_report()` 方法，按"标题→执行摘要→主题解读→行情速览→后续关注→页脚"组装 Markdown 报告
- [x] 2.2 实现精简行情速览板块（复用 prices 数据，仅展示关键资产一行式摘要）

## 3. 流水线编排

- [x] 3.1 创建 `market_daily/core_deep.py`，实现 `run()` 函数：并发拉取四路数据 → 调用 DeepAnalysisGenerator → 组装报告 → 输出/推送
- [x] 3.2 创建 `market_deep.py` 入口文件，支持 `--feishu` 和 `--output report` 命令行参数

## 4. 验证

- [x] 4.1 运行 `python market_deep.py` 验证完整流水线输出
- [x] 4.2 检查报告结构完整性和中文输出质量
