## 1. 基础设施

- [ ] 1.1 创建 `src/options_flow/` 模块目录和 `__init__.py`
- [ ] 1.2 在 `.env.example` 添加 `OPTIONS_FLOW_*` 配置项
- [ ] 1.3 新增 OpenSpec 文档与 specs

## 2. Twitter 客户端

- [ ] 2.1 实现 `client.py` 拉取推文（含 `entities.media`）
- [ ] 2.2 支持多账号与时间窗

## 3. Vision OCR

- [ ] 3.1 实现 `vision.py`（Flash + Pro 回退）
- [ ] 3.2 输出 JSON 解析与字段校验

## 4. 结构化解析

- [ ] 4.1 文本解析 ticker/call-put/premium
- [ ] 4.2 图片解析 Volume/OI/Expiry/Strike
- [ ] 4.3 聚合与异动排序

## 5. 联网搜索与摘要

- [ ] 5.1 接入 SearchService
- [ ] 5.2 LLM 总结可能驱动

## 6. 报告与推送

- [ ] 6.1 `formatter.py` 生成报告
- [ ] 6.2 `options_flow_run.py` CLI 串联流程
- [ ] 6.3 `scripts/options_flow_cron.sh` 定时脚本

## 7. 验证

- [ ] 7.1 使用 @FL0WG0D 跑一次 report
