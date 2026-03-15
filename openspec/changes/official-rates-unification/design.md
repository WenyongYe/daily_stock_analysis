## Context

`market_daily` 当前由 `core.py -> providers -> report builder` 组成。利率相关逻辑分散在：
- `src/macro_monitor.py`（曲线拉取）
- `market_daily/providers/macro.py`（封装/降级）
- `market_daily/report/builder.py`（展示）

历史实现中存在“10Y 实时 + 2Y 曲线值”的混口径拼接风险，导致文本展示与利差计算不闭合。

## Goals / Non-Goals

**Goals**
- 利率段统一同源同日期（尤其 2Y/10Y/spread）
- 保留官方双源（FRED 主源 + Treasury 对账）
- 提供 fallback 兜底并显式标注质量
- 每日快照落库，支持历史追溯
- 报告层增加闭合校验与可读提示

**Non-Goals**
- 不改动价格行情 provider（股票/商品/FX）
- 不引入付费数据源
- 不改动新闻聚合/筛选策略

## Decisions

1. **新增统一利率模块 `src/official_rates.py`**
   - 负责抓取 FRED（DGS3MO/DGS2/DGS5/DGS10/DGS30）
   - 同时拉 Treasury CSV 做同日对账
   - 若官方源失败，fallback 到 yfinance（仅兜底）

2. **收益率快照采用结构化对象输出**
   - 字段包含 `source_primary/source_secondary/observation_date/asof_utc/quality/stale_days/validation`
   - 下游只消费该结构，避免拼接口径失控

3. **报告层强制闭合校验**
   - 使用 `calc=(10Y-2Y)*100` 与 `spread_2y10y_bp` 对比
   - 超过 1bp 输出校验失败提示

4. **历史持久化内置在 MacroProvider**
   - SQLite 表 `yield_curve_daily`，按 `observation_date` upsert
   - 保存 rates、spreads、validation、raw_json

## Risks / Trade-offs

- **FRED/Treasury 可用性波动**：通过 fallback + quality 标记缓解。
- **日期不对齐**（FRED vs Treasury）: 输出 `matched_date=false` 和 Treasury 日期，不强制误报。
- **性能开销**：首次拉取 FRED 多序列有额外时延；通过并发 + 小重试控制。

## Validation Plan

- 语法验证：`python3 -m py_compile ...`
- 功能验证：`python3 scripts/verify_official_rates.py`
- 集成验证：`python3 market_daily_run.py --output report` 与 `python3 market_deep.py --output report`
- OpenSpec 校验：`openspec validate official-rates-unification --strict`
