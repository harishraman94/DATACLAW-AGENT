"""Public Reddit JSON search client and parser."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx


REDDIT_BASE = "https://www.reddit.com"


async def search_reddit(
    *,
    query: str,
    limit: int = 10,
    subreddit: str = "",
    user_agent: str = "DataclawContextResearch/0.1",
    timeout: int = 12,
) -> list[dict[str, Any]]:
    safe_limit = max(1, min(int(limit), 50))
    if subreddit:
        url = f"{REDDIT_BASE}/r/{subreddit.strip('/')}/search.json"
        params = {"q": query, "restrict_sr": "1", "sort": "relevance", "limit": safe_limit}
    else:
        url = f"{REDDIT_BASE}/search.json"
        params = {"q": query, "sort": "relevance", "limit": safe_limit}

    async with httpx.AsyncClient(
        headers={"User-Agent": user_agent},
        timeout=timeout,
        follow_redirects=True,
    ) as client:
        response = await client.get(url, params=params)
        response.raise_for_status()
        payload = response.json()
    return parse_reddit_search(payload, query=query)


def parse_reddit_search(payload: dict[str, Any], *, query: str) -> list[dict[str, Any]]:
    children = payload.get("data", {}).get("children", [])
    findings = []
    for child in children:
        data = child.get("data", {})
        title = str(data.get("title") or "").strip()
        permalink = str(data.get("permalink") or "")
        if not title or not permalink:
            continue
        url = permalink if permalink.startswith("http") else f"{REDDIT_BASE}{permalink}"
        snippet = str(data.get("selftext") or data.get("url") or "")[:500]
        created = data.get("created_utc")
        created_at = ""
        if isinstance(created, (int, float)):
            created_at = datetime.fromtimestamp(created, tz=timezone.utc).isoformat()
        findings.append({
            "query": query,
            "source": "reddit",
            "source_type": "community_discussion",
            "evidence_level": "weak",
            "title": title,
            "url": url,
            "snippet": snippet,
            "subreddit": data.get("subreddit", ""),
            "author": data.get("author", ""),
            "score": data.get("score", 0),
            "comment_count": data.get("num_comments", 0),
            "source_created_at": created_at,
            "tags": ["community_signal", "unverified"],
            "accepted_for_okf": False,
        })
    return findings
