# -*- coding: utf-8 -*-
"""
市场主题分析器
根据行情数据自动判断 Risk-Off/On 状态和关键主题
"""

from dataclasses import dataclass, field


@dataclass
class ThemeResult:
    regime: str           # "risk_off" | "risk_on" | "neutral"
    label:  str           # 显示文本
    themes: list[str]     # 关键主题列表
    watch:  list[str]     # 后续关注点


def analyze_theme(prices: dict, macro: dict, calendar: list[dict] | None = None) -> ThemeResult:
    """
    分析市场主题

    Args:
        prices: PriceProvider.fetch() 的结果
        macro:  MacroProvider.fetch() 的结果

    Returns:
        ThemeResult
    """
    themes = []
    watch  = []

    def get_chg(key: str) -> float:
        d = prices.get(key, {})
        return d.get("chg", 0.0) if "error" not in d else 0.0

    def get_price(key: str) -> float:
        d = prices.get(key, {})
        return d.get("price", 0.0) if "error" not in d else 0.0

    sp_chg    = get_chg("sp500")
    nd_chg    = get_chg("nasdaq")
    gold_chg  = get_chg("gold")
    brent_chg = get_chg("brent")
    dxy_chg   = get_chg("dxy")
    stoxx_chg = get_chg("stoxx")
    us10y_chg = get_chg("us10y")

    vix_price = macro.get("vix") or get_price("vix")
    vix_chg   = get_chg("vix")
    yc        = macro.get("yield_curve", {})
    spread_bp = yc.get("spread_2y10y_bp")

    # ── 美股走势 ──
    if sp_chg < -1.0:
        themes.append(f"美股大跌 S&P {sp_chg:+.2f}%")
    elif sp_chg < -0.3:
        themes.append(f"美股下跌 S&P {sp_chg:+.2f}%")
        watch.append(f"🔍 美股支撑位：S&P 500 关键均线是否破位")
    elif sp_chg > 1.0:
        themes.append(f"美股大涨 S&P {sp_chg:+.2f}%")
    elif sp_chg > 0.3:
        themes.append(f"美股上涨 S&P {sp_chg:+.2f}%")

    # ── NASDAQ vs S&P 分化 ──
    if nd_chg < sp_chg - 0.5:
        themes.append("科技股跑输大盘（成长股承压）")
    elif nd_chg > sp_chg + 0.5:
        themes.append("科技股领涨（成长风格占优）")

    # ── VIX ──
    if vix_price:
        if vix_price >= 30:
            themes.append(f"市场极度恐慌 VIX={vix_price:.1f} 🚨")
        elif vix_price >= 25:
            themes.append(f"恐慌指数高位 VIX={vix_price:.1f} ⚠️")
        elif vix_chg > 5:
            themes.append(f"恐慌指数急升 +{vix_chg:.1f}%")
        if vix_price >= 20:
            watch.append(f"🔍 VIX={vix_price:.1f} 关注是否触顶回落")

    # ── 黄金 ──
    if gold_chg > 2.0:
        themes.append(f"黄金暴涨 {gold_chg:+.1f}%（强烈避险信号）⚠️")
        watch.append("🔍 黄金：确认避险趋势还是技术性获利了结")
    elif gold_chg > 1.0:
        themes.append(f"黄金上涨 {gold_chg:+.1f}%（避险需求）")
    elif gold_chg < -1.5:
        themes.append(f"黄金下跌 {gold_chg:+.1f}%（风险偏好回暖）")

    # ── 油价 ──
    if brent_chg > 2.0:
        themes.append(f"油价大涨 {brent_chg:+.1f}%（OPEC/地缘风险）⚠️")
        watch.append("🔍 油价驱动因素：OPEC决策 / 地缘局势 / 库存数据")
    elif brent_chg > 1.0:
        themes.append(f"油价上涨 {brent_chg:+.1f}%")
    elif brent_chg < -2.0:
        themes.append(f"油价大跌 {brent_chg:+.1f}%（需求担忧/供给压力）")

    # ── 美元 ──
    if dxy_chg < -0.5:
        themes.append(f"美元走弱 DXY {dxy_chg:+.1f}%（美元空头占优）")
        watch.append("🔍 美元弱势：影响新兴市场资金流入")
    elif dxy_chg > 0.5:
        themes.append(f"美元走强 DXY {dxy_chg:+.1f}%（避险/政策预期）")

    # ── 债券 ──
    if us10y_chg < -0.8:
        themes.append("美债收益率大幅下行（避险买盘汹涌）")
    elif us10y_chg > 0.8:
        themes.append("美债收益率上升（通胀/紧缩预期升温）")

    # ── 收益率曲线 ──
    if spread_bp is not None:
        if spread_bp < 0:
            themes.append(f"收益率曲线倒挂（2Y-10Y={float(spread_bp):+.1f}bp）🚨 历史衰退信号")
            watch.append(f"🔍 倒挂深化？当前 2Y-10Y={float(spread_bp):+.1f}bp")

    # ── 美欧分化 ──
    if sp_chg < -0.3 and stoxx_chg > 0.1:
        themes.append("美股跌欧亚涨（资金轮动出美入欧）")
    elif sp_chg > 0.3 and stoxx_chg < -0.1:
        themes.append("美股独涨（强美元逻辑）")

    # ── Risk-Off / Risk-On 判断 ──
    risk_off = sum([
        gold_chg > 0.5,
        us10y_chg < -0.3,
        vix_price >= 20 or vix_chg > 3 if vix_price else False,
        sp_chg < -0.3,
        dxy_chg < -0.3,
        brent_chg > 1.5,
    ])
    if risk_off >= 4:
        regime = "risk_off"
        label  = "⚠️ Risk-Off（避险情绪主导）"
    elif risk_off <= 1:
        regime = "risk_on"
        label  = "✅ Risk-On（风险偏好回暖）"
    else:
        regime = "neutral"
        label  = "➡️ 中性混合（多空交织）"

    # 动态后续关注：从 calendar 提取待公布事件
    if calendar:
        pending_events = [
            e for e in calendar
            if not e.get("actual", "").strip() or e["actual"].strip() == "****"
        ]
        for e in pending_events[:3]:
            event_name = e.get("event", "")
            cur = e.get("currency", "")
            date = e.get("date", "")
            forecast = e.get("forecast", "")
            hint = f"（预期 {forecast}）" if forecast else ""
            watch.append(f"🔍 {date} [{cur}] {event_name}{hint}")

    # 兜底：calendar 为空或无待公布事件时保留通用关注
    if not any("🔍" in w and "[" in w for w in watch):
        watch.append("🔍 关注本周剩余宏观数据公布及央行官员发言")

    return ThemeResult(regime=regime, label=label, themes=themes, watch=list(dict.fromkeys(watch)))
