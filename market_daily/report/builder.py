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


def _alert(key: str, d: dict) -> str:
    """特殊预警标注"""
    if not d or "error" in d:
        return ""
    chg = d.get("chg", 0)
    p   = d.get("price", 0)
    alerts = {
        "gold":   (abs(chg) >= 1.5, f"  ⚠️ 大幅波动 {chg:+.1f}%"),
        "brent":  (chg > 2,         f"  ⚠️ 油价大涨（地缘/OPEC）"),
        "vix":    (p >= 25,         f"  🚨 恐慌区间"),
    }
    if key in alerts:
        cond, msg = alerts[key]
        return msg if cond else ""
    return ""


def _price_row(label: str, key: str, prices: dict, decimals: int = 2, prefix: str = "") -> str:
    d = prices.get(key, {})
    return f"- **{label}**: {_fmt(d, decimals, prefix)}{_alert(key, d)}"


class ReportBuilder:
    """金融市场日报构建器"""

    def build(
        self,
        prices:   dict,
        macro:    dict,
        news:     list[dict],
        calendar: list[dict],
    ) -> str:
        """
        生成完整 Markdown 日报

        Args:
            prices:   PriceProvider.fetch() 结果
            macro:    MacroProvider.fetch() 结果
            news:     NewsProvider.fetch() 结果
            calendar: CalendarProvider.fetch() 结果

        Returns:
            str: 完整 Markdown 文本
        """
        now      = datetime.now(timezone.utc)
        date_str = now.strftime("%Y-%m-%d")
        time_str = now.strftime("%H:%M UTC")

        theme = analyze_theme(prices, macro)

        sections = [
            self._header(date_str, time_str),
            self._theme_section(theme),
            self._us_equity(prices, macro),
            self._intl_equity(prices),
            self._commodities(prices),
            self._fx(prices),
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
            f"**{time_str}** | 数据源: yfinance · ForexFactory · FT / Tavily\n\n"
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

    def _us_equity(self, prices: dict, macro: dict) -> str:
        lines = ["---", "", "## 一、美股指数"]
        for key, label in [("sp500","S&P 500"),("nasdaq","NASDAQ"),("dji","Dow Jones"),("russell","Russell 2000")]:
            lines.append(_price_row(label, key, prices))

        # VIX（优先用 macro provider 的值）
        vix_val   = macro.get("vix")
        vix_label = macro.get("vix_label", "")
        vix_d     = prices.get("vix", {})
        if vix_val and "error" not in vix_d:
            chg = vix_d.get("chg", 0)
            lines.append(f"- **VIX 恐慌指数**: {vix_val:.2f}  {_sign(chg)} {chg:+.2f}%  {vix_label}")
        return "\n".join(lines)

    def _intl_equity(self, prices: dict) -> str:
        lines = ["## 二、欧亚股市"]
        for key, label in [("stoxx","Euro STOXX 600"),("dax","DAX"),("ftse","FTSE 100"),("nikkei","Nikkei 225"),("hsi","恒生指数")]:
            d = prices.get(key, {})
            if d and "error" not in d:
                lines.append(_price_row(label, key, prices))
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
                lines.append(_price_row(label, key, prices, dec, pre))
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
                lines.append(_price_row(label, key, prices, dec))
        return "\n".join(lines)

    def _bonds(self, prices: dict, macro: dict) -> str:
        lines = ["## 五、美债收益率"]
        # 10Y 使用 yfinance 实时涨跌，2Y 优先用 macro_monitor 的可靠值
        d10 = prices.get("us10y", {})
        if d10 and "error" not in d10:
            p, chg = d10["price"], d10["chg"]
            note = "↓ 避险买盘" if chg < -0.5 else ("↑ 通胀预期" if chg > 0.5 else "")
            lines.append(f"- **10年期国债**: {p:.3f}%  {_sign(chg)} {chg:+.2f}%  {note}")

        rates = (macro.get("yield_curve", {}) or {}).get("rates", {}) or {}
        if "2Y" in rates:
            lines.append(f"- **2年期国债**: {float(rates['2Y']):.3f}%  （来自 Treasury 曲线）")
        else:
            d3m = prices.get("us2y", {})
            if d3m and "error" not in d3m:
                lines.append(f"- **3个月国债(替代)**: {d3m['price']:.3f}%  {_sign(d3m['chg'])} {d3m['chg']:+.2f}%")

        # 收益率曲线形态（优先用 macro provider；单位使用 bp）
        yc = macro.get("yield_curve", {})
        spread_2y10y_bp = yc.get("spread_2y10y_bp")
        spread_5y10y_bp = yc.get("spread_5y10y_bp")

        if spread_2y10y_bp is not None:
            invert = "  🚨 倒挂（历史衰退前兆）" if spread_2y10y_bp < 0 else ""
            lines.append(f"- **2Y-10Y 利差**: {spread_2y10y_bp:+.1f}bp{invert}")
        elif spread_5y10y_bp is not None:
            lines.append(f"- **5Y-10Y 利差(替代)**: {spread_5y10y_bp:+.1f}bp")
        else:
            lines.append("- **2Y-10Y 利差**: N/A（缺少2Y可靠数据）")

        curve_shape = yc.get("curve_shape", "")
        if "倒挂" in str(curve_shape).lower() or "inverted" in str(curve_shape).lower():
            lines.append("- ⚠️ 收益率曲线倒挂状态持续")

        return "\n".join(lines)

    def _calendar(self, events: list[dict]) -> str:
        lines = ["---", "", "## 六、本周重要宏观事件（高影响）"]
        if not events:
            lines.append("*本周暂无高影响事件数据*")
            return "\n".join(lines)

        lines += [
            "",
            "| 日期 | 时间 | 货币 | 事件 | 实际 | 预期 | 前值 | 解读 |",
            "|------|------|------|------|------|------|------|------|",
        ]
        for e in events:
            sig = e.get("signal", "")
            lines.append(
                f"| {e['date']} | {e['time']} | {e['currency']} "
                f"| {e['event']} | **{e['actual']}** | {e['forecast']} | {e['previous']} | {sig} |"
            )
        return "\n".join(lines)

    def _news(self, items: list[dict]) -> str:
        from ..providers.news import CATEGORY_ORDER
        lines = ["---", "", "## 七、重要市场新闻"]
        if not items:
            lines.append("*新闻源暂时无法访问*")
            return "\n".join(lines)

        # 按 category 分组
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
