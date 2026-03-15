## 1. 扩展新闻聚合能力（NewsAggregator）

- [x] 1.1 在 `market_daily/providers/news.py` 中扩展 `SEARCH_QUERIES` 从 5 组到 8-10 组，新增欧亚市场、企业财报/并购、加密货币等查询词
- [x] 1.2 新增 Jina Reader 抓取 Reuters Markets 页面标题（复用现有 `_fetch_ft_headlines` 模式，新增 `_fetch_reuters_headlines`）
- [x] 1.3 新增 `NewsAggregator` 类，封装多源并发抓取逻辑（`ThreadPoolExecutor`），支持配置 `max_per_query`（默认 8-10）和目标抓取量（50-100 条）
- [x] 1.4 实现 24h JSON 缓存模块：`_load_cache()` / `_save_cache()` / `_cleanup_expired()`，缓存文件 `data/news_digest_cache.json`，最多 500 条，自动清理 >24h 条目

## 2. LLM 两阶段筛选（NewsDigestPipeline）

- [x] 2.1 新建 `market_daily/providers/news_digest.py`，实现 `NewsDigestPipeline` 类，编排两阶段筛选流程
- [x] 2.2 实现阶段一（本地粗筛）：复用 `_score_item()` + `_select_focus_items()`，放宽 `limit` 到 25 条作为 LLM 候选
- [x] 2.3 实现阶段二（LLM 精选）：构造 prompt 将 ~25 条候选新闻发给 LLM，要求输出 8-12 条中文分类摘要
- [x] 2.4 编写 LLM prompt：包含筛选标准（市场影响力优先）、去重合并、emoji 分类、中文输出、30 字以内等约束
- [x] 2.5 实现 LLM API 调用逻辑：优先 `AIHUBMIX_KEY`，次选 `OPENAI_API_KEY`，失败回退到本地评分前 10 条英文标题

## 3. 集成与替换

- [x] 3.1 修改 `market_daily.py` 的 `main()` 函数，将 `summarize_news_zh()` 调用替换为 `NewsDigestPipeline.run()`
- [x] 3.2 确保 `NewsDigestPipeline.run()` 返回值与 `build_report()` 的 `news_summary` 参数格式兼容（`str` 或 `list[str]`）
- [x] 3.3 更新 `market_daily.py` 的数据拉取并发逻辑，将新闻聚合纳入 `ThreadPoolExecutor` 并发任务

## 4. CLI 与调试支持

- [x] 4.1 在 `news_digest.py` 底部添加 `if __name__ == "__main__"` 入口，支持独立运行并打印抓取统计和最终输出
- [x] 4.2 添加详细的 stderr 日志输出：各源抓取数量、粗筛数量、LLM 调用状态、最终精选数量

## 5. 测试与验证

- [x] 5.1 手动运行 `news_digest.py` 验证完整 pipeline：抓取量 ≥50、粗筛 ~25、LLM 精选 ~10
- [x] 5.2 运行 `market_daily.py` 验证日报新闻板块输出正常，格式无异常
- [x] 5.3 验证缓存文件正确写入和加载，重复运行不产生重复新闻
