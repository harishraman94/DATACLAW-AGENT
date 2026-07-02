"""Academic source providers for context research."""

from __future__ import annotations

import html
import xml.etree.ElementTree as ET
from typing import Any
from urllib.parse import urlencode

import httpx


SEMANTIC_SCHOLAR_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
ARXIV_URL = "https://export.arxiv.org/api/query"


async def search_semantic_scholar(
    *,
    query: str,
    limit: int = 10,
    timeout: int = 12,
    api_key: str = "",
) -> list[dict[str, Any]]:
    safe_limit = max(1, min(int(limit), 25))
    headers = {"User-Agent": "DataclawContextResearch/0.1"}
    if api_key:
        headers["x-api-key"] = api_key
    params = {
        "query": query,
        "limit": safe_limit,
        "fields": "title,abstract,authors,year,venue,url,citationCount,externalIds,isOpenAccess",
    }
    async with httpx.AsyncClient(headers=headers, timeout=timeout, follow_redirects=True) as client:
        response = await client.get(SEMANTIC_SCHOLAR_URL, params=params)
        response.raise_for_status()
        payload = response.json()
    return parse_semantic_scholar(payload, query=query)


def parse_semantic_scholar(payload: dict[str, Any], *, query: str) -> list[dict[str, Any]]:
    findings = []
    for item in payload.get("data", []) or []:
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        authors = [a.get("name", "") for a in item.get("authors", []) if a.get("name")]
        url = item.get("url") or _semantic_scholar_fallback_url(item)
        findings.append({
            "query": query,
            "source": "semantic_scholar",
            "source_type": "paper",
            "evidence_level": "strong",
            "title": title,
            "url": url,
            "snippet": str(item.get("abstract") or "")[:1000],
            "authors": authors,
            "venue": item.get("venue") or "",
            "year": item.get("year"),
            "citation_count": item.get("citationCount", 0),
            "is_open_access": bool(item.get("isOpenAccess", False)),
            "external_ids": item.get("externalIds") or {},
            "tags": ["academic", "paper"],
            "accepted_for_okf": False,
        })
    return findings


async def search_arxiv(
    *,
    query: str,
    limit: int = 10,
    timeout: int = 12,
) -> list[dict[str, Any]]:
    safe_limit = max(1, min(int(limit), 25))
    params = {
        "search_query": f"all:{query}",
        "start": 0,
        "max_results": safe_limit,
        "sortBy": "relevance",
        "sortOrder": "descending",
    }
    url = f"{ARXIV_URL}?{urlencode(params)}"
    async with httpx.AsyncClient(headers={"User-Agent": "DataclawContextResearch/0.1"}, timeout=timeout) as client:
        response = await client.get(url)
        response.raise_for_status()
        text = response.text
    return parse_arxiv(text, query=query)


def parse_arxiv(feed_xml: str, *, query: str) -> list[dict[str, Any]]:
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    try:
        root = ET.fromstring(feed_xml)
    except ET.ParseError:
        return []
    findings = []
    for entry in root.findall("atom:entry", ns):
        title = _text(entry.find("atom:title", ns))
        url = _text(entry.find("atom:id", ns))
        if not title or not url:
            continue
        authors = [_text(a.find("atom:name", ns)) for a in entry.findall("atom:author", ns)]
        findings.append({
            "query": query,
            "source": "arxiv",
            "source_type": "paper",
            "evidence_level": "medium",
            "title": " ".join(title.split()),
            "url": url,
            "snippet": " ".join(_text(entry.find("atom:summary", ns)).split())[:1000],
            "authors": [a for a in authors if a],
            "published_at": _text(entry.find("atom:published", ns)),
            "updated_at_source": _text(entry.find("atom:updated", ns)),
            "tags": ["academic", "preprint"],
            "accepted_for_okf": False,
        })
    return findings


def _semantic_scholar_fallback_url(item: dict[str, Any]) -> str:
    paper_id = item.get("paperId")
    return f"https://www.semanticscholar.org/paper/{paper_id}" if paper_id else ""


def _text(node: ET.Element | None) -> str:
    return html.unescape(node.text.strip()) if node is not None and node.text else ""
