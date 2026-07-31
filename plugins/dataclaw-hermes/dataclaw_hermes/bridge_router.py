"""In-process Hermes callback, search, health, and diagnostics routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from dataclaw_hermes.config import HERMES_COMPAT_VERSION, HermesConfig
from dataclaw_hermes.installer import (
    check_installation,
    install_dataclaw_extension,
    remove_dataclaw_extension,
    restart_hermes_gateway,
)
from dataclaw_hermes.tool_executor import execute_tool_call, search_tools

router = APIRouter()


class ToolSearchBody(BaseModel):
    runId: str
    sessionId: str
    projectId: str | None = None
    query: str = Field(default="", max_length=2_000)
    limit: int = Field(default=8, ge=1, le=100)


class ToolCallBody(BaseModel):
    runtimeRunId: str = ""
    toolCallId: str = Field(min_length=1, max_length=512)
    runId: str = Field(min_length=1, max_length=512)
    sessionId: str = Field(min_length=1, max_length=512)
    projectId: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)


@router.post("/tools/search")
async def tool_search(body: ToolSearchBody, request: Request) -> dict[str, Any]:
    tools = await search_tools(
        request,
        run_id=body.runId,
        session_id=body.sessionId,
        project_id=body.projectId,
        query=body.query,
        limit=body.limit,
    )
    return {"tools": tools}


@router.get("/runs/{run_id}/context")
async def run_context(run_id: str, request: Request) -> dict[str, Any]:
    store = request.app.state.runtime_run_store
    mapping = await store.get_run(run_id)
    if mapping is None or mapping.get("runtime") != "hermes":
        raise HTTPException(404, "Unknown Hermes run")
    manager = request.app.state.runtime_manager
    if manager.get_run(run_id) is None:
        raise HTTPException(404, "Hermes run lease is not active")
    return {
        "runId": mapping["runId"],
        "sessionId": mapping["sessionId"],
        "projectId": mapping.get("projectId"),
        "runtimeRunId": mapping.get("runtimeRunId"),
    }


@router.post("/tools/{tool_name}/call")
async def tool_call(
    tool_name: str, body: ToolCallBody, request: Request
) -> dict[str, Any]:
    return await execute_tool_call(
        request,
        runtime_run_id=body.runtimeRunId,
        tool_call_id=body.toolCallId,
        run_id=body.runId,
        session_id=body.sessionId,
        project_id=body.projectId,
        tool_name=tool_name,
        params=body.params,
    )


@router.get("/diagnostics")
async def diagnostics(request: Request) -> dict[str, Any]:
    config = HermesConfig.resolve()
    manager = request.app.state.runtime_manager
    unresolved = sum(
        1
        for ctx in getattr(manager, "_runs", {}).values()
        if ctx.bundle.identity.runtime == "hermes"
    )
    return {
        **manager.diagnostics,
        "adapter_version": "0.1.0",
        "hermes_compat_version": HERMES_COMPAT_VERSION,
        "effective_tool_callback_timeout_seconds": (
            config.tool_callback_timeout_seconds
        ),
        "unresolved_run_count": unresolved,
        "local_private_warning": (
            "Dataclaw has no API authentication. Keep Dataclaw and Hermes "
            "on loopback or a trusted private network."
        ),
    }


@router.get("/health")
async def health(request: Request) -> dict[str, Any]:
    manager = request.app.state.runtime_manager
    bundle = manager.active_bundle
    return {
        "status": (
            "healthy"
            if bundle.identity.runtime == "hermes" and bundle.availability
            else "configured_inactive"
            if manager.configured_runtime != "hermes"
            else "unhealthy"
        ),
        **manager.diagnostics,
    }


@router.get("/install/status")
async def install_status() -> dict[str, Any]:
    return check_installation(HermesConfig.resolve())


@router.post("/install/extension")
async def install_extension_route() -> dict[str, Any]:
    import asyncio

    return await asyncio.to_thread(
        install_dataclaw_extension, HermesConfig.resolve()
    )


@router.post("/gateway/restart")
async def restart_gateway_route() -> dict[str, Any]:
    import asyncio

    try:
        return await asyncio.to_thread(
            restart_hermes_gateway, HermesConfig.resolve()
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.delete("/install/extension")
async def remove_extension_route() -> dict[str, Any]:
    import asyncio

    return await asyncio.to_thread(
        remove_dataclaw_extension, HermesConfig.resolve()
    )
