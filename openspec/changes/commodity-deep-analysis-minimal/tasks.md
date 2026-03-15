## 1. OpenSpec 定义

- [x] 1.1 新建 change：`commodity-deep-analysis-minimal`
- [x] 1.2 完成 proposal / design / tasks

## 2. 最小化开发

- [x] 2.1 deep_analysis prompt 增加商品三段硬性输出结构
- [x] 2.2 deep_analysis prompt 增加“定价状态 + 可信度 + 跨资产验证”约束
- [x] 2.3 core_deep 增加商品关键词新闻提取并注入深度分析上下文

## 3. 验证与交付

- [x] 3.1 运行 `python3 market_deep.py --output report --feishu`
- [x] 3.2 确认报告包含黄金/白银/原油三段并保存到 `reports/`
- [x] 3.3 回传本次报告路径供用户查阅
