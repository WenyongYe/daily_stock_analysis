## 1. OpenSpec artifacts

- [x] 1.1 创建 change：`official-rates-unification`
- [x] 1.2 完成 proposal / design / specs / tasks 文档

## 2. Phase 1 — 口径统一改造

- [x] 2.1 新增 `src/official_rates.py`（FRED 主源 + Treasury 对账 + fallback）
- [x] 2.2 重构 `src/macro_monitor.py`，移除 `2Y -> ^IRX` 风险路径
- [x] 2.3 重构 `market_daily/providers/macro.py` 输出统一收益率快照
- [x] 2.4 更新 `market_daily/report/builder.py`：同源同日期展示 + 闭合校验
- [x] 2.5 更新 `market_daily/report/theme.py` 使用 `spread_2y10y_bp`
- [x] 2.6 更新 `market_daily/report/deep_analysis.py` 增加 source/date/stale 注释

## 3. Phase 2 — 历史追踪

- [x] 3.1 新增 SQLite 表 `yield_curve_daily`
- [x] 3.2 在 MacroProvider 中实现按 `observation_date` upsert
- [x] 3.3 持久化 validation_json/raw_json 以支持追溯

## 4. Phase 3 — 功能验证

- [x] 4.1 语法验证：`python3 -m py_compile ...`
- [x] 4.2 功能验证：`python3 scripts/verify_official_rates.py`
- [x] 4.3 集成验证：`python3 market_daily_run.py --output report`
- [x] 4.4 集成验证：`python3 market_deep.py --output report`
- [x] 4.5 OpenSpec 校验：`openspec validate official-rates-unification --strict`
