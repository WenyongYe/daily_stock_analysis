## 1. 宏观事件板块修复

- [x] 1.1 修改 `builder.py` 的 `_calendar()` 方法：标题改为"本周宏观事件"，过滤掉 actual 为空且日期已过的事件，仅保留有数据的已公布事件和未来待公布事件
- [x] 1.2 飞书推送时将表格转为纯文本格式：`事件名: 实际值 vs 预期值 (解读)`

## 2. 飞书推送格式优化

- [x] 2.1 优化 `_strip_markdown()` 或飞书 delivery 模块，将 Markdown 表格转为可读的纯文本列表
- [x] 2.2 添加长度控制：总字符超过 15000 时截断，末尾附"完整版已保存到文件"提示

## 3. 后续关注动态化

- [x] 3.1 修改 `theme.py` 删除写死的通用话术（"NFP就业报告、CPI通胀数据"）
- [x] 3.2 改为从 calendar 事件中提取未来 3 天高影响事件作为动态关注点
- [x] 3.3 保留 1 条兜底通用关注（当 calendar 数据为空时）

## 4. LLM 综合叙事

- [x] 4.1 新建 `market_daily/report/narrative.py`，实现 `generate_narrative()` 函数：接收 prices 摘要、news 摘要、theme 结果，调 LLM 生成 2-3 句综合叙事
- [x] 4.2 修改 `core.py`，在 report build 前调用 `generate_narrative()`，将结果传入 builder
- [x] 4.3 修改 `builder.py`，在主题段后插入综合叙事段

## 5. 加密货币行情

- [x] 5.1 在 `market_daily/providers/prices.py` 的 SYMBOLS 中加入 `BTC-USD` 和 `ETH-USD`
- [x] 5.2 在 `builder.py` 新增 `_crypto()` 方法，放在外汇和债券之间

## 6. 验证

- [x] 6.1 运行 `market_daily_run.py` 验证完整日报格式正确
- [x] 6.2 验证飞书推送格式可读（无乱码表格）
