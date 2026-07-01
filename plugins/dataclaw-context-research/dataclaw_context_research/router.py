"""API routes for context research findings."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from dataclaw_context_research.tools import (
    context_research_generate_queries,
    context_research_list_findings,
    context_research_save_to_okf,
    context_research_search_reddit,
    context_research_summarize_findings,
)

router = APIRouter()


class QueryRequest(BaseModel):
    dataset_id: str = ""
    problem_statement: str = ""
    limit: int = 8


class RedditSearchRequest(BaseModel):
    query: str
    dataset_id: str = ""
    problem_statement: str = ""
    limit: int = 10
    subreddit: str = ""


class SaveToOKFRequest(BaseModel):
    bundle_id: str
    dataset_id: str = ""
    finding_ids: list[str] | None = None


@router.post("/queries")
async def generate_queries_route(req: QueryRequest) -> dict[str, Any]:
    try:
        return await context_research_generate_queries(
            dataset_id=req.dataset_id,
            problem_statement=req.problem_statement,
            limit=req.limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/reddit/search")
async def search_reddit_route(req: RedditSearchRequest) -> dict[str, Any]:
    return await context_research_search_reddit(
        query=req.query,
        dataset_id=req.dataset_id,
        problem_statement=req.problem_statement,
        limit=req.limit,
        subreddit=req.subreddit,
    )


@router.get("/findings")
async def list_findings_route(dataset_id: str = "", limit: int = 20) -> dict[str, Any]:
    return await context_research_list_findings(dataset_id=dataset_id, limit=limit)


@router.get("/findings/summary")
async def summarize_findings_route(dataset_id: str = "") -> dict[str, Any]:
    return await context_research_summarize_findings(dataset_id=dataset_id)


@router.post("/okf")
async def save_to_okf_route(req: SaveToOKFRequest) -> dict[str, Any]:
    try:
        return await context_research_save_to_okf(
            bundle_id=req.bundle_id,
            dataset_id=req.dataset_id,
            finding_ids=req.finding_ids,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
