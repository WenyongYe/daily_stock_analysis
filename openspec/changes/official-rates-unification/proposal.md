## Why

当前利率链路存在口径风险：
- 历史上出现过 `2Y -> ^IRX` 映射痕迹（`^IRX` 实际是短端 T-Bill，不是 2Y）；
- 报告段落中 10Y 与 2Y/利差来自不同源、不同时间戳，导致文本不闭合；
- 缺少每日利率快照留痕，难以追溯和回放。

为避免再次出现“2Y 异常”类口径错配，本变更将利率段升级为“官方同源+可追溯+强校验”。

## What Changes

- 新增官方利率抓取模块：FRED 主源 + Treasury 校验，失败时 fallback。
- 收益率曲线统一由 `macro_monitor` 输出，不再把 `^IRX` 作为 2Y。
- `market_daily` 报告利率段改为同源同日期展示，并增加闭合校验与口径标注。
- 新增历史快照入库：`data/macro_rates.db` / `yield_curve_daily`。
- 深度分析宏观摘要增加 `source/observation_date/stale_days` 与对账信息。
- 提供验证脚本 `scripts/verify_official_rates.py` 做功能验收。

## Capabilities

### New Capabilities
- `official-rates-source`: 统一的官方利率数据源抽象（FRED/Treasury/fallback）
- `rate-history-persistence`: 每日收益率曲线快照持久化与回溯
- `report-rate-consistency`: 报告层口径闭合校验与对账可视化

### Modified Capabilities
- `macro provider`: 从“混源拼接”升级为“同源快照输出”
- `market daily report`: 利率段改为官方口径并显式标注 source/date

## Impact

- 代码影响：
  - `src/official_rates.py`（新增）
  - `src/macro_monitor.py`
  - `market_daily/providers/macro.py`
  - `market_daily/report/builder.py`
  - `market_daily/report/theme.py`
  - `market_daily/report/deep_analysis.py`
  - `scripts/verify_official_rates.py`（新增）
- 数据影响：新增 `data/macro_rates.db` 与 `yield_curve_daily` 表。
- 报告影响：2Y/10Y/spread 强制同源同日期 + bp 单位 + 一致性校验。
