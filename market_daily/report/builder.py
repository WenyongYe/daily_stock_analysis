# -*- coding: utf-8 -*-
"""
报告构建器
聚合所有 Provider 数据，按标准模板生成完整 Markdown 日报
"""

from datetime import datetime, timezone

from .theme import analyze_theme, ThemeResult


def _sign(chg: float) -> str:
    return "🟢" if chg >= 0 else "🔴"


def _fmt(d: dict, decimals: int = 2, prefix: str = "") -> str:
    """格式化一行价格+涨跌幅"""
    if not d or "error" in d:
        return "N/A"
    p   = d["price"]
    chg = d["chg"]
    return f"{prefix}{p:,.{decimals}f}  {_sign(chg)} {chg:+.2f}%"


def _price_row(label: str, key: str, prices: dict, decimals: int = 2,
               prefix: str = "", annotations: dict | None = None) -> str:
    d = prices.get(key, {})
    ann = ""
    if annotations and key in annotations:
        ann = f"  💬 {annotations[key]}"
    return f"- **{label}**: {_fmt(d, decimals, prefix)}{ann}"


class ReportBuilder:
    """金融市场日报构建器"""

    def build(
        self,
        prices:   dict,
        macro:    dict,
        news,
        calendar: list[dict],
        narrative: str | None = None,
        annotations: dict | None = None,
    ) -> str:
        """
        生成完整 Markdown 日报

        Args:
            prices:      PriceProvider.fetch() 结果
            macro:       MacroProvider.fetch() 结果
            news:        NewsDigestPipeline.run() 结果
            calendar:    CalendarProvider.fetch() 结果
            narrative:   LLM 综合叙事（可选）
            annotations: LLM 数据点注释 {key: "解读"}（可选）

        Returns:
            str: 完整 Markdown 文本
        """
        self._ann = annotations or {}

        now      = datetime.now(timezone.utc)
        date_str = now.strftime("%Y-%m-%d")
        time_str = now.strftime("%H:%M UTC")

        theme = analyze_theme(prices, macro, calendar)

        sections = [
            self._header(date_str, time_str),
            self._theme_section(theme),
            self._narrative_section(narrative),
            self._us_equity(prices, macro),
            self._intl_equity(prices),
            self._commodities(prices),
            self._fx(prices),
            self._crypto(prices),
            self._bonds(prices, macro),
            self._calendar(calendar),
            self._news(news),
            self._watchlist(theme),
            self._footer(date_str, time_str),
        ]

        return "\n\n".join(s for s in sections if s)

    # ── 各节构建 ──────────────────────────────────────────────

    def _header(self, date_str: str, time_str: str) -> str:
        return (
            f"# 📊 金融市场日报 · {date_str}\n"
            f"**{time_str}** | 数据源: FRED/Treasury(利率) · yfinance(行情) · ForexFactory · FT / Tavily\n\n"
            "---"
        )

    def _theme_section(self, theme: ThemeResult) -> str:
        lines = [f"## 🎯 今日主题：{theme.label}"]
        if theme.themes:
            for t in theme.themes:
                lines.append(f"- {t}")
        else:
            lines.append("- 市场整体平稳，无显著异动信号")
        return "\n".join(lines)

    def _narrative_section(self, narrative: str | None) -> str:
        if not narrative:
            return ""
        return f"> 💡 {narrative}"

    def _us_equity(self, prices: dict, macro: dict) -> str:
        lines = ["---", "", "## 一、美股指数"]
        for key, label in [("sp500","S&P 500"),("nasdaq","NASDAQ"),("dji","Dow Jones"),("russell","Russell 2000")]:
            lines.append(_price_row(label, key, prices, annotations=self._ann))

        # VIX（优先用 macro provider 的值）
        vix_val = macro.get("vix")
        vix_label = macro.get("vix_label", "")
        vix_d = prices.get("vix", {})
        if vix_val:
            # 日变化：优先 macro 的计算，其次 yfinance fast_info 变化
            day_chg = macro.get("vix_day_change_pct")
            if day_chg is None and vix_d and "error" not in vix_d:
                day_chg = vix_d.get("chg", 0)

            week_chg = macro.get("vix_week_change_pct")
            last_week_close = macro.get("vix_last_week_close")

            # VIX 上涨是风险上升，图标与普通资产相反
            if day_chg is None:
                day_part = "N/A"
            else:
                day_icon = "🔴" if day_chg > 0 else "🟢"
                day_part = f"{day_icon} {day_chg:+.2f}%"

            week_part = ""
            if week_chg is not None:
                week_icon = "🔴" if week_chg > 0 else "🟢"
                if last_week_close is not None:
                    week_part = f" | 周比 {week_icon} {week_chg:+.2f}%（上周收盘 {last_week_close:.2f}）"
                else:
                    week_part = f" | 周比 {week_icon} {week_chg:+.2f}%"

            vix_ann = ""
            if "vix" in self._ann:
                vix_ann = f"  💬 {self._ann['vix']}"
            lines.append(f"- **VIX 恐慌指数**: {vix_val:.2f}  {day_part}{week_part}  {vix_label}{vix_ann}")
        return "\n".join(lines)

    def _intl_equity(self, prices: dict) -> str:
        lines = ["## 二、欧亚股市"]
        for key, label in [("stoxx","Euro STOXX 600"),("dax","DAX"),("ftse","FTSE 100"),("nikkei","Nikkei 225"),("hsi","恒生指数")]:
            d = prices.get(key, {})
            if d and "error" not in d:
                lines.append(_price_row(label, key, prices, annotations=self._ann))
        return "\n".join(lines)

    def _commodities(self, prices: dict) -> str:
        lines = ["## 三、大宗商品"]
        specs = [
            ("gold",   "黄金 Gold",  2,  ""),
            ("silver", "白银 Silver",2,  ""),
            ("brent",  "布伦特原油", 2,  "$"),
            ("crude",  "WTI 原油",   2,  "$"),
            ("copper", "铜 Copper",  4,  ""),
            ("natgas", "天然气",     3,  ""),
        ]
        for key, label, dec, pre in specs:
            d = prices.get(key, {})
            if d and "error" not in d:
                lines.append(_price_row(label, key, prices, dec, pre, self._ann))
        return "\n".join(lines)

    def _fx(self, prices: dict) -> str:
        lines = ["## 四、外汇"]
        specs = [
            ("eurusd", "EUR/USD",     4),
            ("gbpusd", "GBP/USD",     4),
            ("usdjpy", "USD/JPY",     2),
            ("dxy",    "美元指数 DXY", 2),
        ]
        for key, label, dec in specs:
            d = prices.get(key, {})
            if d and "error" not in d:
                lines.append(_price_row(label, key, prices, dec, annotations=self._ann))
        return "\n".join(lines)

    def _crypto(self, prices: dict) -> str:
        btc = prices.get("btc", {})
        eth = prices.get("eth", {})
        if (not btc or "error" in btc) and (not eth or "error" in eth):
            return ""
        lines = ["## 加密货币"]
        if btc and "error" not in btc:
            lines.append(_price_row("BTC", "btc", prices, 0, "$", self._ann))
        if eth and "error" not in eth:
            lines.append(_price_row("ETH", "eth", prices, 2, "$", self._ann))
        return "\n".join(lines)

    def _bonds(self, prices: dict, macro: dict) -> str:
        lines = ["## 五、美债收益率"]

        yc = macro.get("yield_curve", {}) or {}
        rates = yc.get("rates", {}) or {}
        source = yc.get("source") or "unknown"
        observation_date = yc.get("observation_date") or "N/A"
        stale_days = yc.get("stale_days")

        if "10Y" in rates:
            lines.append(f"- **10年期国债**: {float(rates['10Y']):.3f}%")
        else:
            lines.append("- **10年期国债**: N/A")

        if "2Y" in rates:
            lines.append(f"- **2年期国债**: {float(rates['2Y']):.3f}%")
        else:
            lines.append("- **2年期国债**: N/A")

        if "3M" in rates:
            lines.append(f"- **3个月国债**: {float(rates['3M']):.3f}%")

        spread_2y10y_bp = yc.get("spread_2y10y_bp")
        if spread_2y10y_bp is not None:
            invert = "  🚨 倒挂（历史衰退前兆）" if spread_2y10y_bp < 0 else ""
            lines.append(f"- **2Y-10Y 利差**: {float(spread_2y10y_bp):+.1f}bp{invert}")
        else:
            lines.append("- **2Y-10Y 利差**: N/A（缺少同源2Y/10Y）")

        # 同口径闭合校验：spread 应等于 (10Y - 2Y) * 100
        if "10Y" in rates and "2Y" in rates and spread_2y10y_bp is not None:
            calc_bp = round((float(rates["10Y"]) - float(rates["2Y"])) * 100, 1)
            diff_bp = round(calc_bp - float(spread_2y10y_bp), 2)
            if abs(diff_bp) <= 1.0:
                lines.append(f"- ✅ 口径校验: 10Y-2Y={calc_bp:+.1f}bp，与展示一致（Δ={diff_bp:+.2f}bp）")
            else:
                lines.append(f"- ⚠️ 口径校验失败: 10Y-2Y={calc_bp:+.1f}bp，展示={float(spread_2y10y_bp):+.1f}bp（Δ={diff_bp:+.2f}bp）")

        consistency = yc.get("consistency") or {}
        if consistency and consistency.get("diff_bp") is not None:
            passed = consistency.get("passed", False)
            icon = "✅" if passed else "⚠️"
            lines.append(f"- {icon} 内部一致性: diff={float(consistency['diff_bp']):+.2f}bp")

        validation = yc.get("validation") or {}
        if validation.get("matched_date"):
            max_abs_diff_bp = validation.get("max_abs_diff_bp")
            if max_abs_diff_bp is None:
                lines.append("- ✅ Treasury 对账: 同日可比，差值 N/A")
            else:
                lines.append(f"- ✅ Treasury 对账: 同日最大偏差 {float(max_abs_diff_bp):.1f}bp")
        elif validation:
            treasury_date = validation.get("treasury_observation_date")
            if treasury_date:
                lines.append(f"- ℹ️ Treasury 对账: 日期未对齐（Treasury={treasury_date}）")

        stale_text = f" | stale={stale_days}d" if stale_days is not None else ""
        lines.append(f"- **口径标注**: source={source} | observation_date={observation_date}{stale_text}")

        curve_shape = yc.get("curve_shape", "")
        if "倒挂" in str(curve_shape).lower() or "inverted" in str(curve_shape).lower():
            lines.append("- ⚠️ 收益率曲线倒挂状态持续")

        return "\n".join(lines)

    def _calendar(self, events: list[dict]) -> str:
        lines = ["---", "", "## 六、本周宏观事件"]
        if not events:
            lines.append("*本周暂无高影响事件数据*")
            return "\n".join(lines)

        # 过滤：只保留有实际数据的事件（actual 非空且非 ****）
        valuable = [
            e for e in events
            if e.get("actual", "").strip() and e["actual"].strip() != "****"
        ]
        # 以及未来待公布的（actual 为空的也保留，标记"待公布"）
        pending = [
            e for e in events
            if not e.get("actual", "").strip() or e["actual"].strip() == "****"
        ]

        if not valuable and not pending:
            lines.append("*本周暂无高影响事件数据*")
            return "\n".join(lines)

        if valuable:
            lines += [
                "",
                "**已公布数据：**",
                "",
                "| 日期 | 货币 | 事件 | 实际 | 预期 | 前值 | AI解读 |",
                "|------|------|------|------|------|------|--------|",
            ]
            for e in valuable:
                # 优先用 AI 注释，回退到规则信号
                ann_key = f"{e['currency']}_{e['event']}"
                sig = self._ann.get(ann_key, "") or e.get("signal", "")
                lines.append(
                    f"| {e['date']} | {e['currency']} "
                    f"| {e['event']} | **{e['actual']}** | {e['forecast']} | {e['previous']} | {sig} |"
                )

        if pending:
            lines += ["", "**待公布事件：**"]
            for e in pending[:6]:
                lines.append(f"- {e['date']} {e['time']} [{e['currency']}] {e['event']}（预期: {e.get('forecast', 'N/A')}）")

        return "\n".join(lines)

    def _news(self, news_data) -> str:
        lines = ["---", "", "## 七、重要市场新闻"]
        if not news_data:
            lines.append("*新闻源暂时无法访问*")
            return "\n".join(lines)

        # NewsDigestPipeline 返回 str（LLM 中文摘要）或 list（回退）
        if isinstance(news_data, str):
            # LLM 精选的中文分类摘要，直接嵌入
            lines.append(news_data)
            return "\n".join(lines)

        if isinstance(news_data, list) and news_data and isinstance(news_data[0], str):
            # 回退模式：英文标题列表
            for i, title in enumerate(news_data, 1):
                lines.append(f"{i}. {title}")
            return "\n".join(lines)

        # 兼容旧格式：list[dict]（NewsProvider 直接返回）
        from ..providers.news import CATEGORY_ORDER
        items = news_data
        groups: dict[str, list[dict]] = {}
        for item in items:
            cat = item.get("category", "其他")
            groups.setdefault(cat, []).append(item)

        idx = 1
        for cat, emoji in CATEGORY_ORDER:
            cat_items = groups.get(cat)
            if not cat_items:
                continue
            lines.append(f"\n### {emoji} {cat}")
            for item in cat_items:
                url   = item.get("url", "")
                title = item["title"]
                src   = item.get("source", "")
                src_tag = f"  — {src}" if src else ""
                if url:
                    lines.append(f"{idx}. [{title}]({url}){src_tag}")
                else:
                    lines.append(f"{idx}. {title}{src_tag}")
                idx += 1

        return "\n".join(lines)

    def _watchlist(self, theme: ThemeResult) -> str:
        lines = ["---", "", "## 八、后续关注"]
        for w in theme.watch:
            lines.append(f"- {w}")
        return "\n".join(lines)

    def _footer(self, date_str: str, time_str: str) -> str:
        return (
            "---\n"
            f"*📅 {date_str} {time_str} · market_daily · "
            "数据: yfinance / ForexFactory / FT / Tavily*\n"
            "*⚠️ 仅供参考，不构成投资建议*"
        )
