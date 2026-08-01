"""In-place migrations for persisted DataClaw configuration."""

from __future__ import annotations

from typing import Any

UTILITY_BACKENDS = frozenset({"anthropic", "openai", "gemini", "codex"})
EXTERNAL_RUNTIMES = frozenset({"openclaw", "hermes"})


def migrate_runtime_utility_config(raw: dict[str, Any]) -> bool:
    """Separate the legacy combined LLM/runtime selector.

    Older configs stored direct model providers and external agent runtimes in
    ``llm.backend``. New configs keep the runtime in ``agent.runtime`` while
    ``llm.backend`` always names DataClaw's utility provider.
    """

    changed = False
    llm = raw.setdefault("llm", {})
    if not isinstance(llm, dict):
        return False

    legacy_backend = str(llm.get("backend") or "openclaw")
    agent = raw.setdefault("agent", {})
    if not isinstance(agent, dict):
        agent = {}
        raw["agent"] = agent
        changed = True

    if not agent.get("runtime"):
        if legacy_backend in EXTERNAL_RUNTIMES or legacy_backend == "mock":
            agent["runtime"] = legacy_backend
        else:
            agent["runtime"] = "dataclaw"
        changed = True

    hermes = raw.get("plugins", {}).get("hermes", {})
    if not isinstance(hermes, dict):
        hermes = {}

    if legacy_backend not in UTILITY_BACKENDS:
        migrated_backend = str(hermes.get("utility_backend") or "")
        if migrated_backend not in UTILITY_BACKENDS:
            migrated_backend = _configured_provider(llm) or "codex"
        llm["backend"] = migrated_backend
        changed = True

        migrated_model = str(hermes.get("utility_model") or "")
        if migrated_model:
            provider_config = llm.setdefault(migrated_backend, {})
            if isinstance(provider_config, dict):
                provider_config["model"] = migrated_model
                changed = True

    # These legacy aliases may remain readable in older releases, but the
    # current config has one canonical source for utility selection.
    if hermes:
        if "utility_backend" in hermes:
            del hermes["utility_backend"]
            changed = True
        if "utility_model" in hermes:
            del hermes["utility_model"]
            changed = True

    return changed


def _configured_provider(llm: dict[str, Any]) -> str | None:
    """Prefer a provider with an explicitly saved API key."""

    for backend in ("codex", "openai", "anthropic", "gemini"):
        provider = llm.get(backend)
        if isinstance(provider, dict) and str(provider.get("api_key") or ""):
            return backend
    return None
