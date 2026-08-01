from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

import dataclaw.providers.agent.factory as runtime_factory
from dataclaw.hooks.registry import HookRegistry
from dataclaw.plugins.registry import ProviderRegistry
from dataclaw.providers.agent.factory import (
    RuntimeBundle,
    RuntimeDiagnostics,
    RuntimeIdentity,
    RuntimeManager,
)


class _Closeable:
    def __init__(self) -> None:
        self.close_count = 0

    async def aclose(self) -> None:
        self.close_count += 1


def _bundle(name: str, closeable: _Closeable) -> RuntimeBundle:
    component = object()
    return RuntimeBundle(
        agent=closeable,
        utility_llm=component,
        compaction=component,
        tool_availability=component,
        sub_agent_registry=component,
        sub_agent_hooks=component,
        memory=component,
        system_prompt=component,
        skill=component,
        hooks=HookRegistry(),
        runtime_control=None,
        identity=RuntimeIdentity(runtime=name),
        diagnostics=RuntimeDiagnostics(),
    )


@pytest.mark.asyncio
async def test_runtime_bundle_retires_after_last_run_lease() -> None:
    registry = ProviderRegistry()
    first_closeable = _Closeable()
    first = _bundle("mock", first_closeable)
    second = _bundle("hermes", _Closeable())
    manager = RuntimeManager(registry, HookRegistry(), first)

    manager.acquire_run("run-1")
    await manager._swap(second)
    assert first_closeable.close_count == 0

    await manager.release_run("run-1")
    assert first_closeable.close_count == 1
    await manager.release_run("run-1")
    assert first_closeable.close_count == 1


def test_runtime_bundle_is_frozen() -> None:
    bundle = _bundle("mock", _Closeable())
    with pytest.raises(FrozenInstanceError):
        bundle.availability = False  # type: ignore[misc]


@pytest.mark.asyncio
async def test_reload_failure_retains_active_bundle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = ProviderRegistry()
    initial = _bundle("mock", _Closeable())
    manager = RuntimeManager(registry, HookRegistry(), initial)

    async def fail_selection(*args, **kwargs):
        del args, kwargs
        raise RuntimeError("Hermes is down")

    monkeypatch.setattr(
        runtime_factory, "build_runtime_bundle", fail_selection
    )
    selected = await manager.select(backend="hermes")
    assert selected is initial
    assert manager.configured_runtime == "hermes"
    assert manager.active_runtime == "mock"
    assert manager.last_selection_error == "Hermes is down"


@pytest.mark.asyncio
async def test_startup_failure_publishes_unavailable_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = ProviderRegistry()
    manager = RuntimeManager(
        registry, HookRegistry(), _bundle("mock", _Closeable())
    )

    async def fail_selection(*args, **kwargs):
        del args, kwargs
        raise RuntimeError("incompatible Hermes")

    monkeypatch.setattr(
        runtime_factory, "build_runtime_bundle", fail_selection
    )
    selected = await manager.select(backend="hermes", startup=True)
    assert selected.identity.runtime == "hermes"
    assert selected.availability is False
    assert manager.active_runtime == "hermes"
    assert manager.diagnostics["runtime_diagnostics"]["health"] == "unavailable"
