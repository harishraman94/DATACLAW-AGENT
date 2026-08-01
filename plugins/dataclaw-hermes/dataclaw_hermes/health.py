"""Hermes compatibility health checks."""

from __future__ import annotations

from typing import Any

from dataclaw_hermes.client import HermesClient
from dataclaw_hermes.config import HERMES_COMPAT_VERSION

REQUIRED_TOOLS = frozenset({"dataclaw_tool", "dataclaw_tool_search"})


async def verify_compatibility(client: HermesClient) -> dict[str, Any]:
    health = await client.health()
    version = str(health.get("version") or "")
    if version != HERMES_COMPAT_VERSION:
        raise RuntimeError(
            "Incompatible Hermes Agent version: "
            f"expected {HERMES_COMPAT_VERSION}, got {version or 'unknown'}"
        )
    capabilities = await client.capabilities()
    features = capabilities.get("features") or {}
    required = {
        "run_submission",
        "run_status",
        "run_events_sse",
        "run_stop",
    }
    missing = sorted(name for name in required if not features.get(name))
    if missing:
        raise RuntimeError(
            "Hermes API is missing required capabilities: "
            + ", ".join(missing)
        )
    toolsets = await client.toolsets()
    rows = [
        row
        for row in toolsets.get("data") or []
        if isinstance(row, dict)
    ]
    enabled = [row for row in rows if row.get("enabled") is True]
    if [str(row.get("name")) for row in enabled] != ["dataclaw"]:
        raise RuntimeError(
            "Hermes API profile must enable only the dataclaw toolset"
        )
    exposed = {
        str(tool)
        for tool in enabled[0].get("tools") or []
    }
    if exposed != REQUIRED_TOOLS:
        raise RuntimeError(
            "Hermes dataclaw toolset must expose exactly "
            "dataclaw_tool and dataclaw_tool_search"
        )
    return {
        "compat_version": HERMES_COMPAT_VERSION,
        "hermes_version": version,
        "capabilities": sorted(required),
        "toolset": "dataclaw",
        "tools": sorted(exposed),
    }
