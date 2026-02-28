# -*- coding: utf-8 -*-
"""
经济日历 Provider
从 ForexFactory 拉取本周高影响宏观事件
"""

import re
import sys

import requests

FOREXFACTORY_URL = "https://r.jina.ai/https://www.forexfactory.com/calendar"
JINA_HEADERS     = {"Accept": "text/markdown", "X-No-Cache": "true"}
TIMEOUT          = 25

# 关注的货币
TARGET_CURRENCIES = {"USD", "EUR", "GBP", "CNY", "JPY"}


def _parse_events(text: str) -> list[dict]:
    """解析 ForexFactory 高影响事件（橙色 ora）"""
    events   = []
    cur_date = ""

    date_pat  = re.compile(r'\|\s*((?:Sun|Mon|Tue|Wed|Thu|Fri|Sat)\s+\w+\s+\d+)\s*\|')
    event_pat = re.compile(
        r'\|\s*([\d:apm]+|All Day)\s*\|'
        r'\s*(USD|EUR|GBP|CNY|JPY|AUD|CAD|CHF|NZD)\s*\|'
        r'[^|]*ora[^|]*\|'
        r'\s*([^|]+?)\s*\|'
        r'[^|]*\|[^|]*\|'
        r'\s*([^|]*?)\s*\|'
        r'\s*([^|]*?)\s*\|'
        r'\s*([^|]*?)\s*\|'
    )

    for line in text.split('\n'):
        dm = date_pat.search(line)
        if dm:
            cur_date = dm.group(1).strip()

        em = event_pat.search(line)
        if em:
            time_, cur, event, actual, forecast, prev = em.groups()
            if cur in TARGET_CURRENCIES:
                # 超预期/不及预期信号
                signal = _event_signal(actual.strip(), forecast.strip())
                events.append({
                    "date":     cur_date,
                    "time":     time_.strip(),
                    "currency": cur.strip(),
                    "event":    event.strip(),
                    "actual":   actual.strip(),
                    "forecast": forecast.strip(),
                    "previous": prev.strip(),
                    "signal":   signal,
                })
    return events


def _event_signal(actual: str, forecast: str) -> str:
    """判断数据超预期/不及预期"""
    try:
        a = float(re.sub(r'[^\d.\-]', '', actual))
        f = float(re.sub(r'[^\d.\-]', '', forecast))
        if a > f:   return "✅ 超预期"
        elif a < f: return "❌ 不及预期"
        return "符合预期"
    except:
        return ""


class CalendarProvider:
    """经济日历数据拉取器"""

    def __init__(self, url: str = FOREXFACTORY_URL):
        self.url = url

    def fetch(self) -> list[dict]:
        """
        拉取本周高影响经济事件

        Returns:
            list[dict]: [{date, time, currency, event, actual, forecast, previous, signal}, ...]
        """
        try:
            r = requests.get(self.url, headers=JINA_HEADERS, timeout=TIMEOUT)
            events = _parse_events(r.text)
            print(f"  [CalendarProvider] 获取 {len(events)} 个高影响事件", file=sys.stderr)
            return events[:15]
        except Exception as e:
            print(f"  [CalendarProvider] 拉取失败: {e}", file=sys.stderr)
            return []
