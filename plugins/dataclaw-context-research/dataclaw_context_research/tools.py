"""Agent tools for open-world context research."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from dataclaw_context_research.query import generate_queries
from dataclaw_context_research.reddit import search_reddit
from dataclaw_context_research.registry import (
    filter_findings,
    mark_saved_to_okf,
    save_findings,
)
from dataclaw_context_research.summary import external_context_markdown, summarize_findings
from dataclaw_okf.registry import find_bundle, upsert_bundle


_plugin_cfg: dict[str, Any] = {}


def set_plugin_cfg(cfg: dict[str, Any]) -> None:
    global _plugin_cfg
    _plugin_cfg = cfg or {}


async def context_research_generate_queries(
    *,
    dataset_id: str = "",
    problem_statement: str = "",
    limit: int = 8,
    **kwargs: Any,
) -> dict[str, Any]:
    return generate_queries(dataset_id=dataset_id, problem_statement=problem_statement, limit=limit)


async def context_research_search_reddit(
    *,
    query: str,
    dataset_id: str = "",
    problem_statement: str = "",
    limit: int = 10,
    subreddit: str = "",
    **kwargs: Any,
) -> dict[str, Any]:
    max_results = int(_plugin_cfg.get("max_results", 15) or 15)
    effective_limit = min(max(1, int(limit)), max_results)
    try:
        findings = await search_reddit(
            query=query,
            limit=effective_limit,
            subreddit=subreddit,
            user_agent=str(_plugin_cfg.get("reddit_user_agent") or "DataclawContextResearch/0.1"),
            timeout=int(_plugin_cfg.get("request_timeout", 12) or 12),
        )
    except Exception as exc:
        return {
            "status": "error",
            "error": str(exc),
            "query": query,
            "source": "reddit",
            "saved_count": 0,
        }

    enriched = []
    for finding in findings:
        enriched.append({
            **finding,
            "dataset_id": dataset_id,
            "problem_statement": problem_statement,
        })
    saved = save_findings(enriched)
    return {
        "status": "saved",
        "query": query,
        "source": "reddit",
        "evidence_level": "weak",
        "saved_count": len(saved),
        "findings": [_summarize_finding(f) for f in saved],
        "note": "Reddit findings are weak community signals. Verify before using them as analysis assumptions.",
    }


async def context_research_list_findings(
    *,
    dataset_id: str = "",
    limit: int = 20,
    **kwargs: Any,
) -> dict[str, Any]:
    findings = filter_findings(dataset_id=dataset_id, limit=int(limit))
    return {"findings": [_summarize_finding(f) for f in findings], "count": len(findings)}


async def context_research_summarize_findings(
    *,
    dataset_id: str = "",
    finding_ids: list[str] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    findings = filter_findings(dataset_id=dataset_id, finding_ids=finding_ids)
    return summarize_findings(findings)


async def context_research_save_to_okf(
    *,
    bundle_id: str,
    dataset_id: str = "",
    finding_ids: list[str] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    bundle = find_bundle(bundle_id)
    findings = filter_findings(dataset_id=dataset_id or str(bundle.get("dataset_id", "")), finding_ids=finding_ids)
    root = Path(str(bundle.get("path", "")))
    if not root.exists():
        raise ValueError(f"OKF bundle path is missing: {root}")
    target = root / "notes" / "external_context.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(external_context_markdown(findings), encoding="utf-8")

    files = set(bundle.get("files", []))
    files.add("notes/external_context.md")
    updated = {
        **bundle,
        "files": sorted(files),
        "file_count": len(files),
    }
    upsert_bundle(updated)
    mark_saved_to_okf([str(f.get("id")) for f in findings], bundle_id)
    return {
        "bundle_id": bundle_id,
        "path": "notes/external_context.md",
        "saved_findings": len(findings),
        "evidence_note": "External context is cited and evidence-labeled; weak/community findings require verification.",
    }


def _summarize_finding(finding: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": finding.get("id"),
        "dataset_id": finding.get("dataset_id", ""),
        "source": finding.get("source"),
        "source_type": finding.get("source_type"),
        "evidence_level": finding.get("evidence_level"),
        "title": finding.get("title"),
        "url": finding.get("url"),
        "snippet": finding.get("snippet", ""),
        "subreddit": finding.get("subreddit", ""),
        "score": finding.get("score", 0),
        "comment_count": finding.get("comment_count", 0),
        "retrieved_at": finding.get("retrieved_at", ""),
        "accepted_for_okf": finding.get("accepted_for_okf", False),
    }
