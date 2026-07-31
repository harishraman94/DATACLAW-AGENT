"""Config router — read/update configuration with hot-reload of agent backend."""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, Request

from dataclaw.config.paths import config_path
from dataclaw.config.resolver import (
    invalidate_cache,
    resolve_agent_runtime,
)
from dataclaw.config.schema import DataclawConfig

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("")
async def get_config(request: Request) -> dict[str, Any]:
    """Get the current configuration (secrets masked)."""
    path = config_path()
    if path.exists():
        raw = json.loads(path.read_text())
    else:
        raw = DataclawConfig().model_dump()

    # Mask secrets at any nesting depth
    _mask_secrets_recursive(raw)

    # Include current active agent backend
    raw["_active_agent"] = _detect_active_agent(request)
    manager = getattr(request.app.state, "runtime_manager", None)
    if manager is not None:
        raw["_runtime_status"] = manager.diagnostics

    return raw


@router.patch("")
async def update_config(updates: dict[str, Any], request: Request) -> dict[str, Any]:
    """Merge updates into the config file and hot-reload agent if backend changed."""
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.exists():
        raw = json.loads(path.read_text())
    else:
        raw = {}

    _strip_masked_secrets(updates)
    _deep_merge(raw, updates)
    path.write_text(json.dumps(raw, indent=2))
    invalidate_cache()

    # Refresh the in-memory DataclawConfig snapshot so /api/providers reflects
    # the new backend selections (the providers router reads app.state.config).
    try:
        request.app.state.config = DataclawConfig(**raw)
    except Exception:
        logger.exception("Failed to refresh app.state.config after PATCH")

    await reload_runtime(request)

    return {"status": "updated"}


async def reload_runtime(request: Request) -> Any:
    """Route every runtime reload through the centralized async selector."""
    invalidate_cache()
    manager = getattr(request.app.state, "runtime_manager", None)
    if manager is None:
        # Compatibility for lightweight tests and embedding code that has not
        # run the application lifespan.
        _hot_reload_agent(request)
        return None
    bundle = await manager.select()
    request.app.state.hooks = bundle.hooks
    return bundle


def _hot_reload_agent(request: Request) -> None:
    """Legacy synchronous reload for callers without a RuntimeManager."""
    try:
        providers = request.app.state.providers
        invalidate_cache()
        backend = resolve_agent_runtime()
        if backend in {"openclaw", "hermes"}:
            logger.warning(
                "Cannot synchronously select external runtime %s without "
                "the application RuntimeManager",
                backend,
            )
            return
        _reload_llm_agent(providers, backend)
    except Exception:
        logger.exception("Failed to hot-reload agent provider")


def _reload_llm_agent(providers: Any, backend: str) -> None:
    """Reload the LLM-based agent provider."""
    from dataclaw.providers.llm.implementations.factory import llm_from_config
    from dataclaw.providers.agent.implementations.langchain_agent import LangChainAgentProvider
    from dataclaw.providers.compaction.implementations.llm_summarizer import LLMSummarizingCompactor

    llm = llm_from_config(backend=backend)
    providers.llm = llm
    providers.agent = LangChainAgentProvider(llm)
    providers.compaction = LLMSummarizingCompactor(llm)
    logger.info("Hot-reloaded agent: %s LLM", backend)


def _hot_reload_memory(request: Request) -> None:
    """Rebuild the memory provider from current config."""
    try:
        from dataclaw.providers.memory.implementations.factory import memory_from_config

        providers = request.app.state.providers
        providers.memory = memory_from_config()
        logger.info("Hot-reloaded memory provider: %s", type(providers.memory).__name__)
    except Exception:
        logger.exception("Failed to hot-reload memory provider")


def _hot_reload_compaction(request: Request) -> None:
    """Rebuild the compaction provider from current config."""
    try:
        from dataclaw.providers.compaction.implementations.factory import compaction_from_config

        providers = request.app.state.providers
        providers.compaction = compaction_from_config(providers.llm)
        logger.info("Hot-reloaded compaction provider: %s", type(providers.compaction).__name__)
    except Exception:
        logger.exception("Failed to hot-reload compaction provider")


def _detect_active_agent(request: Request) -> str:
    """Return the name of the currently active agent provider."""
    try:
        manager = getattr(request.app.state, "runtime_manager", None)
        if manager is not None:
            return manager.active_runtime
        backend = resolve_agent_runtime()
        agent = request.app.state.providers.agent
        name = type(agent).__name__
        if "OpenClaw" in name:
            return "openclaw"
        return backend
    except Exception:
        return "unknown"


def _mask_secrets_recursive(d: dict) -> None:
    """Recursively mask secret values for safe display."""
    for key in d:
        val = d[key]
        if isinstance(val, dict):
            _mask_secrets_recursive(val)
        elif isinstance(val, str) and _is_secret_key(key) and val:
            d[key] = val[:8] + "..." + val[-4:] if len(val) > 12 else "***"


_SECRET_KEY_PATTERNS = {"api_key", "token", "secret", "password"}


def _strip_masked_secrets(updates: dict) -> None:
    """Recursively remove masked secret values so they don't overwrite real keys.

    Any key whose name contains 'api_key', 'token', 'secret', or 'password'
    is checked. If the value looks masked (contains '...' or is '***'),
    it's removed so the real value in the config file is preserved.
    """
    _strip_masked_recursive(updates)


def _strip_masked_recursive(d: dict) -> None:
    for key in list(d.keys()):
        val = d[key]
        if isinstance(val, dict):
            _strip_masked_recursive(val)
        elif isinstance(val, str) and _is_secret_key(key) and _is_masked(val):
            del d[key]


def _is_secret_key(key: str) -> bool:
    key_lower = key.lower()
    return any(p in key_lower for p in _SECRET_KEY_PATTERNS)


def _is_masked(val: str) -> bool:
    return "..." in val or val == "***"


def _deep_merge(base: dict, updates: dict) -> None:
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
