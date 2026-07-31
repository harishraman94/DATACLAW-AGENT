from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import dataclaw.api.run_tracker as run_tracker
from dataclaw.hooks.registry import HookRegistry
from dataclaw.plugins.registry import ProviderRegistry
from dataclaw.providers.agent.factory import (
    RuntimeBundle,
    RuntimeDiagnostics,
    RuntimeIdentity,
    RuntimeManager,
)
from dataclaw.storage import sessions
from dataclaw.storage.runtime_runs import RuntimeRunStore
from dataclaw_hermes.tool_executor import execute_tool_call


class _Availability:
    def __init__(self, fn) -> None:
        self.fn = fn

    async def resolve_tools(self, state):
        del state
        return (
            [
                {
                    "name": "echo",
                    "description": "Echo",
                    "parameters": {"type": "object", "properties": {}},
                }
            ],
            {"echo": self.fn},
        )

    def has_tool(self, name: str) -> bool:
        return name == "echo"


def _bundle(availability, hooks: HookRegistry) -> RuntimeBundle:
    component = object()
    return RuntimeBundle(
        agent=component,
        utility_llm=component,
        compaction=component,
        tool_availability=availability,
        sub_agent_registry=component,
        sub_agent_hooks=component,
        memory=component,
        system_prompt=component,
        skill=component,
        hooks=hooks,
        runtime_control=None,
        identity=RuntimeIdentity(runtime="hermes"),
        diagnostics=RuntimeDiagnostics(),
    )


async def _environment(
    *,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    tool,
    hooks: HookRegistry | None = None,
):
    import dataclaw.config.paths as paths

    dataclaw_home = tmp_path / ".dataclaw"
    dataclaw_home.mkdir()
    monkeypatch.setenv("DATACLAW_HOME", str(dataclaw_home))
    monkeypatch.setattr(paths, "DATACLAW_HOME", dataclaw_home)
    tracker = run_tracker.RunTracker()
    monkeypatch.setattr(run_tracker, "_tracker", tracker)
    registry = ProviderRegistry()
    hook_registry = hooks or HookRegistry()
    manager = RuntimeManager(
        registry,
        hook_registry,
        _bundle(_Availability(tool), hook_registry),
    )
    manager.acquire_run("dc-run")
    run = tracker.start_run("session", "dc-run")
    store = RuntimeRunStore(tmp_path / "runtime")
    await store.create_run(
        run_id="dc-run",
        session_id="session",
        project_id="project",
    )
    await store.update_run(
        "dc-run", status="running", runtimeRunId="hrun"
    )
    await sessions.create_session(session_id="session", title="Tools")
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                runtime_run_store=store,
                runtime_manager=manager,
            )
        )
    )
    return request, manager, tracker, run, store


@pytest.mark.asyncio
async def test_duplicate_callback_executes_once_and_conflicts_fail(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executions = 0
    release = asyncio.Event()

    async def echo(**params):
        nonlocal executions
        executions += 1
        await release.wait()
        return params

    request, _manager, tracker, _run, store = await _environment(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        tool=echo,
    )
    kwargs = {
        "runtime_run_id": "hrun",
        "tool_call_id": "call-1",
        "run_id": "dc-run",
        "session_id": "session",
        "project_id": "project",
        "tool_name": "echo",
        "params": {"value": 1},
    }
    first = asyncio.create_task(execute_tool_call(request, **kwargs))
    second = asyncio.create_task(execute_tool_call(request, **kwargs))
    await asyncio.sleep(0)
    release.set()
    assert await asyncio.gather(first, second) == [
        {
            "state": "completed",
            "isError": False,
            "content": {"value": 1},
            "guardrailId": None,
        }
    ] * 2
    assert executions == 1
    stored = await sessions.get_session("session")
    assert len(
        [
            message
            for message in stored["messages"]
            if message.get("toolCallId") == "call-1"
        ]
    ) == 1

    with pytest.raises(HTTPException) as conflict:
        await execute_tool_call(
            request,
            **{**kwargs, "params": {"value": 2}},
        )
    assert conflict.value.status_code == 409

    tracker.finish_run("session")
    with pytest.raises(HTTPException) as late:
        await execute_tool_call(
            request,
            **{**kwargs, "tool_call_id": "call-late"},
        )
    assert late.value.status_code == 409
    assert await store.get_tool_call("hrun", "call-late") is None


@pytest.mark.asyncio
async def test_approval_can_remain_pending_then_resume_exact_call(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executions = 0
    hooks = HookRegistry()

    async def require_approval(state):
        state["pending_tool_calls"] = []
        state["guardrail_verdicts"] = [
            {
                "phase": "pre",
                "mode": "user_approval",
                "tool_call_id": "call-approved",
                "guardrail_id": "confirm",
                "message": "Confirm",
            }
        ]
        return state

    hooks.register("preToolCallHook", require_approval)

    async def echo(**params):
        nonlocal executions
        executions += 1
        return params

    request, _manager, _tracker, run, store = await _environment(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        tool=echo,
        hooks=hooks,
    )
    task = asyncio.create_task(
        execute_tool_call(
            request,
            runtime_run_id="hrun",
            tool_call_id="call-approved",
            run_id="dc-run",
            session_id="session",
            project_id="project",
            tool_name="echo",
            params={"approved": True},
        )
    )
    for _ in range(20):
        if run.guardrail_approvals:
            break
        await asyncio.sleep(0)
    assert run.status == "waiting_approval"
    approval_id, event = next(iter(run.guardrail_approvals.items()))
    pending = await sessions.get_session("session")
    assert pending["pendingActions"][0]["state"] == "pending"
    assert pending["pendingActions"][0]["tool"] == {
        "name": "echo",
        "arguments": {"approved": True},
    }
    run.guardrail_decisions[approval_id] = {"approved": True}
    event.set()

    result = await task
    assert result["state"] == "completed"
    assert executions == 1
    assert run.status == "running"
    record = await store.get_tool_call("hrun", "call-approved")
    assert record["state"] == "completed"
    persisted = await sessions.get_session("session")
    assert persisted["pendingActions"][0]["state"] == "approved"
