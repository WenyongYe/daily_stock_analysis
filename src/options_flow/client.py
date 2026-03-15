# -*- coding: utf-8 -*-
"""Twitter client for options flow (with media URLs)."""

from __future__ import annotations

import logging
from typing import Any

import requests
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from src.twitter_monitor.config import get_api_key, TWITTER_API_BASE

logger = logging.getLogger(__name__)


class OptionsFlowTwitterClient:
    """twitterapi.io REST client for options flow tweets."""

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
    def _request(self, params: dict[str, Any]) -> dict:
        resp = self.session.get(
            f"{TWITTER_API_BASE}/tweet/advanced_search",
            params=params,
            timeout=30,
        )
        if resp.status_code == 429:
            raise requests.HTTPError("429 Rate Limited", response=resp)
        resp.raise_for_status()
        return resp.json()

    @staticmethod
    def _extract_media_urls(tweet: dict[str, Any]) -> list[str]:
        urls: list[str] = []
        entities = tweet.get("entities") or {}
        media_list = []
        if isinstance(entities, dict):
            media_list = entities.get("media") or []
        if not media_list:
            ext = tweet.get("extendedEntities") or {}
            if isinstance(ext, dict):
                media_list = ext.get("media") or []
        for media in media_list:
            if not isinstance(media, dict):
                continue
            url = media.get("media_url_https") or media.get("media_url")
            if url and url not in urls:
                urls.append(url)
        return urls

    def fetch_tweets(self, account: str, since: str, until: str) -> list[dict[str, Any]]:
        query = f"from:{account} since:{since} until:{until}"
        all_tweets: list[dict[str, Any]] = []
        cursor = None

        while True:
            params: dict[str, Any] = {"query": query, "queryType": "Latest"}
            if cursor:
                params["cursor"] = cursor
            try:
                data = self._request(params)
            except Exception as exc:
                logger.error("拉取 @%s 推文失败: %s", account, exc)
                break

            tweets = data.get("tweets") or []
            for t in tweets:
                all_tweets.append({
                    "text": t.get("text", ""),
                    "createdAt": t.get("createdAt", ""),
                    "author": (t.get("author") or {}).get("userName", account),
                    "url": t.get("url") or t.get("twitterUrl", ""),
                    "media_urls": self._extract_media_urls(t),
                })

            if not data.get("has_next_page"):
                break
            cursor = data.get("next_cursor")
            if not cursor:
                break

        logger.info("@%s: 获取 %d 条推文 (%s ~ %s)", account, len(all_tweets), since, until)
        return all_tweets

    def fetch_all_tweets(self, accounts: list[str], since: str, until: str) -> list[dict[str, Any]]:
        all_tweets: list[dict[str, Any]] = []
        for account in accounts:
            all_tweets.extend(self.fetch_tweets(account, since, until))
        all_tweets.sort(key=lambda t: t.get("createdAt", ""), reverse=True)
        logger.info("共获取 %d 条推文（%d 个账号）", len(all_tweets), len(accounts))
        return all_tweets
