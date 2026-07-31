"""Config resolution: env var > config file > default.

Usage:
    from dataclaw.config.resolver import resolve
    api_key = resolve("llm.anthropic.api_key", "ANTHROPIC_API_KEY", "")
"""

from __future__ import annotations

import json
import os
from typing import Any

from dataclaw.config.paths import config_path

_config_cache: dict[str, Any] | None = None
UTILITY_BACKENDS = frozenset({"anthropic", "openai", "gemini", "codex"})
AGENT_RUNTIMES = frozenset({"dataclaw", "openclaw", "hermes", "mock"})


def _read_config_file() -> dict[str, Any]:
    """Read and cache the config file. Returns empty dict if missing."""
    global _config_cache
    if _config_cache is not None:
        return _config_cache

    path = config_path()
    if path.exists():
        _config_cache = json.loads(path.read_text())
    else:
        _config_cache = {}
    return _config_cache


def invalidate_cache() -> None:
    """Clear the config file cache (useful after writes)."""
    global _config_cache
    _config_cache = None


def resolve(dot_path: str, env_var: str, default: Any = None) -> Any:
    """Resolve a config value: env var takes precedence, then config file, then default."""
    val = os.environ.get(env_var)
    if val is not None:
        return val

    raw: Any = _read_config_file()
    for part in dot_path.split("."):
        if not isinstance(raw, dict):
            return default
        raw = raw.get(part)
        if raw is None:
            return default
    return raw if raw is not None else default


def resolve_bool(dot_path: str, env_var: str, default: bool = False) -> bool:
    """Resolve a boolean config value with env var coercion."""
    val = resolve(dot_path, env_var, None)
    if val is None:
        return default
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.lower() in ("true", "1", "yes")
    return bool(val)


def resolve_agent_runtime() -> str:
    """Resolve the primary agent runtime with legacy config compatibility."""

    configured = str(
        resolve("agent.runtime", "DATACLAW_AGENT_RUNTIME", "") or ""
    ).strip()
    if configured:
        if configured not in AGENT_RUNTIMES:
            raise ValueError(f"Unknown agent runtime: {configured!r}")
        return configured

    legacy = str(
        resolve("llm.backend", "DATACLAW_LLM_BACKEND", "openclaw")
    ).strip()
    if legacy in {"openclaw", "hermes", "mock"}:
        return legacy
    if legacy in UTILITY_BACKENDS:
        return "dataclaw"
    raise ValueError(f"Unknown legacy runtime/backend: {legacy!r}")


def resolve_utility_backend() -> str:
    """Resolve DataClaw's utility model provider.

    ``DATACLAW_UTILITY_BACKEND`` is the canonical environment override. The
    legacy ``DATACLAW_LLM_BACKEND`` remains accepted when it names a model
    provider rather than an external runtime.
    """

    explicit_env = str(os.environ.get("DATACLAW_UTILITY_BACKEND") or "").strip()
    if explicit_env:
        if explicit_env not in UTILITY_BACKENDS:
            raise ValueError(f"Unknown utility backend: {explicit_env!r}")
        return explicit_env

    legacy_env = str(os.environ.get("DATACLAW_LLM_BACKEND") or "").strip()
    if legacy_env in UTILITY_BACKENDS:
        return legacy_env

    configured = str(resolve("llm.backend", "", "") or "").strip()
    if configured in UTILITY_BACKENDS:
        return configured

    # Read the Hermes aliases only for installations that have not yet run the
    # persisted-config migration.
    legacy_hermes = str(
        resolve(
            "plugins.hermes.utility_backend",
            "DATACLAW_HERMES_UTILITY_BACKEND",
            "",
        )
        or ""
    ).strip()
    if legacy_hermes in UTILITY_BACKENDS:
        return legacy_hermes
    raise ValueError(
        "Configure llm.backend with a DataClaw utility provider "
        "(anthropic, openai, gemini, or codex)"
    )


def resolve_utility_model(backend: str | None = None) -> str:
    """Resolve the selected utility provider's model ID."""

    selected = backend or resolve_utility_backend()
    env_var = {
        "anthropic": "ANTHROPIC_MODEL",
        "openai": "OPENAI_MODEL",
        "gemini": "GEMINI_MODEL",
        "codex": "CODEX_MODEL",
    }.get(selected, "")
    model = str(resolve(f"llm.{selected}.model", env_var, "") or "").strip()
    if model:
        return model
    return str(
        resolve(
            "plugins.hermes.utility_model",
            "DATACLAW_HERMES_UTILITY_MODEL",
            "",
        )
        or ""
    ).strip()
