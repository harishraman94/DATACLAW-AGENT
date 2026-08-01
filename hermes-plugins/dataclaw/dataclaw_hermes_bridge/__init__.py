"""Hermes-side Dataclaw dispatcher registration."""

from __future__ import annotations

from .catalog import SEARCH_SCHEMA, search_catalog
from .tools import (
    DISPATCH_SCHEMA,
    capture_tool_call_id,
    dispatch_tool,
)


def register(ctx) -> None:
    ctx.register_hook("pre_tool_call", capture_tool_call_id)
    ctx.register_tool(
        name="dataclaw_tool",
        toolset="dataclaw",
        schema=DISPATCH_SCHEMA,
        handler=dispatch_tool,
        description="Execute an enabled Dataclaw tool.",
    )
    ctx.register_tool(
        name="dataclaw_tool_search",
        toolset="dataclaw",
        schema=SEARCH_SCHEMA,
        handler=search_catalog,
        description="Search enabled Dataclaw tools.",
    )


__all__ = ["register"]
