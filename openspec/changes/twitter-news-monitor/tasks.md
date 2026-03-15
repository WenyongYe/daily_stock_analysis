## 1. 基础设施

- [x] 1.1 创建 `src/twitter_monitor/` 模块目录和 `__init__.py`
- [x] 1.2 在 `.env.example` 中添加 `TWITTER_API_KEY` 和 `TWITTER_MONITOR_ACCOUNTS` 配置项

## 2. API 客户端 (`src/twitter_monitor/client.py`)

- [x] 2.1 实现 `TwitterAPIClient` 类，封装 twitterapi.io `advanced_search` 端点
- [x] 2.2 实现 `fetch_tweets(account, since, until)` 方法，支持游标分页
- [x] 2.3 实现 `fetch_all_tweets(accounts, since, until)` 批量拉取，按时间倒序合并
- [x] 2.4 添加 tenacity 重试装饰器（指数退避，最多 3 次，含 429 限流处理）
- [x] 2.5 添加请求日志和错误处理（失败返回空列表不中断）

## 3. 配置模块 (`src/twitter_monitor/config.py`)

- [x] 3.1 定义默认监控账号列表：FirstSquawk, DeItaone, KobeissiLetter
- [x] 3.2 支持环境变量 `TWITTER_MONITOR_ACCOUNTS` 覆盖（逗号分隔）
- [x] 3.3 定义 `get_fetch_interval_hours()` 和时间窗口计算工具函数

## 4. AI 分析模块 (`src/twitter_monitor/analyzer.py`)

- [x] 4.1 实现 `analyze_tweets(tweets)` 方法，调用 LLM adapter 进行分析
- [x] 4.2 编写 system prompt：去重合并、三级分类（🔴🟡🔵）、中文翻译与影响分析
- [x] 4.3 处理空推文场景，返回"无重大事件"简报
- [x] 4.4 添加 token 上限保护，超出时按时间倒序截断推文列表

## 5. 简报生成与推送

- [x] 5.1 实现简报格式化函数，输出飞书 Markdown 格式
- [x] 5.2 复用飞书 Webhook 通道进行推送（交互卡片格式）
- [x] 5.3 消息过长时飞书自动处理

## 6. CLI 入口 (`twitter_news_run.py`)

- [x] 6.1 实现 argparse CLI：`--output`、`--feishu`、`--dry-run`、`--hours` 参数
- [x] 6.2 串联完整流程：配置加载 → 推文拉取 → AI 分析 → 格式化 → 推送
- [x] 6.3 `--dry-run` 模式仅拉取推文打印到终端

## 7. 定时调度

- [x] 7.1 在 `cron/jobs.json` 新增 `twitter_news` 任务，cron: `0 0,8,16 * * *`

## 8. 验证与交付

- [x] 8.1 配置 `TWITTER_API_KEY` 环境变量
- [x] 8.2 执行 `python3 twitter_news_run.py --dry-run` 验证推文拉取正常（160条）
- [x] 8.3 执行 `python3 twitter_news_run.py --output report` 验证 AI 分析输出
- [x] 8.4 执行 `python3 twitter_news_run.py --output report --feishu` 验证飞书推送
- [x] 8.5 确认 cron job 注册成功
