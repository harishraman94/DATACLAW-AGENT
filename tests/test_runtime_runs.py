from __future__ import annotations

import pytest

from dataclaw.storage.runtime_runs import (
    InvalidTransition,
    RuntimeRunStore,
    canonical_arguments_digest,
)


@pytest.mark.asyncio
async def test_runtime_run_and_tool_transitions_are_durable(tmp_path) -> None:
    store = RuntimeRunStore(tmp_path / "runtime")
    run = await store.create_run(
        run_id="dc-run",
        session_id="session",
        project_id="project",
    )
    assert run["status"] == "queued"
    await store.update_run("dc-run", status="running")
    await store.update_run("dc-run", status="completed")
    with pytest.raises(InvalidTransition):
        await store.update_run("dc-run", status="running")

    digest = canonical_arguments_digest({"b": 2, "a": 1})
    assert digest == canonical_arguments_digest({"a": 1, "b": 2})
    await store.create_tool_call(
        runtime_run_id="hrun",
        tool_call_id="call-1",
        dataclaw_run_id="dc-run",
        session_id="session",
        project_id="project",
        tool_name="echo",
        arguments_digest=digest,
    )
    await store.update_tool_call("hrun", "call-1", state="executing")
    await store.update_tool_call(
        "hrun", "call-1", state="completed", result={"ok": True}
    )
    with pytest.raises(InvalidTransition):
        await store.update_tool_call("hrun", "call-1", state="executing")


@pytest.mark.asyncio
async def test_restart_fails_runs_and_marks_tools_unknown(tmp_path) -> None:
    store = RuntimeRunStore(tmp_path / "runtime")
    await store.create_run(
        run_id="dc-run",
        session_id="session",
        project_id=None,
    )
    await store.update_run("dc-run", status="running")
    await store.create_tool_call(
        runtime_run_id="hrun",
        tool_call_id="call-1",
        dataclaw_run_id="dc-run",
        session_id="session",
        project_id=None,
        tool_name="side_effect",
        arguments_digest=canonical_arguments_digest({}),
    )
    await store.update_tool_call("hrun", "call-1", state="executing")

    assert await store.fail_nonterminal_records() == {
        "runs": 1,
        "tool_calls": 1,
    }
    assert (await store.get_run("dc-run"))["status"] == "failed"
    tool = await store.get_tool_call("hrun", "call-1")
    assert tool["state"] == "unknown"
    assert tool["result"]["isError"] is True
