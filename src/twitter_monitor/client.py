# -*- coding: utf-8 -*-
"""twitterapi.io API 客户端"""

import logging
from typing import Any

import requests
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from src.twitter_monitor.config import get_api_key, TWITTER_API_BASE

logger = logging.getLogger(__name__)


class TwitterAPIClient:
    """twitterapi.io REST API 客户端"""

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or get_api_key()
        if not self.api_key:
            raise ValueError("TWITTER_API_KEY 未配置")
        self.session = requests.Session()
        self.session.headers.update({"X-API-Key": self.api_key})

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=3, max=15),
        retry=retry_if_exception_type((requests.ConnectionError, requests.Timeout, requests.HTTPError)),
    )
    def _request(self, params: dict) -> dict:
        resp = self.session.get(
            f"{TWITTER_API_BASE}/tweet/advanced_search",
            params=params,
            timeout=30,
        )
        if resp.status_code == 429:
            raise requests.HTTPError("429 Rate Limited", response=resp)
        resp.raise_for_status()
        return resp.json()

    def fetch_tweets(self, account: str, since: str, until: str) -> list[dict[str, Any]]:
        """拉取指定账号在时间窗口内的所有推文，自动分页。"""
        query = f"from:{account} since:{since} until:{until}"
        all_tweets: list[dict] = []
        cursor = None

        while True:
            params = {"query": query, "queryType": "Latest"}
            if cursor:
                params["cursor"] = cursor

            try:
                data = self._request(params)
            except Exception as e:
                logger.error(f"拉取 @{account} 推文失败: {e}")
                break

            tweets = data.get("tweets") or []
            for t in tweets:
                all_tweets.append({
                    "text": t.get("text", ""),
                    "createdAt": t.get("createdAt", ""),
                    "author": t.get("author", {}).get("userName", account),
                    "url": t.get("url", ""),
                })

            if not data.get("has_next_page"):
                break
            cursor = data.get("next_cursor")
            if not cursor:
                break

        logger.info(f"@{account}: 获取 {len(all_tweets)} 条推文 ({since} ~ {until})")
        return all_tweets

    def fetch_all_tweets(
        self, accounts: list[str], since: str, until: str
    ) -> list[dict[str, Any]]:
        """批量拉取多个账号推文，按时间倒序合并。"""
        all_tweets: list[dict] = []
        for account in accounts:
            tweets = self.fetch_tweets(account, since, until)
            all_tweets.extend(tweets)

        # 按 createdAt 倒序
        all_tweets.sort(key=lambda t: t.get("createdAt", ""), reverse=True)
        logger.info(f"共获取 {len(all_tweets)} 条推文（{len(accounts)} 个账号）")
        return all_tweets
