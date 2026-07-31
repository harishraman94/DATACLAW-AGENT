from __future__ import annotations

import pytest

import dataclaw.api.run_tracker as run_tracker
from dataclaw.api.routers.chat import _terminalize_run
from dataclaw.events.emitter import AgentEventEmitter
from dataclaw.storage import sessions


@pytest.mark.asyncio
async def test_terminalization_persists_success_exactly_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tracker = run_tracker.RunTracker()
    monkeypatch.setattr(run_tracker, "_tracker", tracker)
    await sessions.create_session(session_id="session", title="Terminal")
    run = tracker.start_run("session", "run-1")
    emitter = AgentEventEmitter("session", "run-1")

    assert await _terminalize_run(
        "session",
        outcome="success",
        emitter=emitter,
        assistant_text="done",
        message_id="answer-1",
    )
    assert not await _terminalize_run(
        "session",
        outcome="failure",
        emitter=emitter,
        error="late failure",
    )

    stored = await sessions.get_session("session")
    assistant = [
        message
        for message in stored["messages"]
        if message.get("role") == "assistant"
    ]
    assert [message["content"] for message in assistant] == ["done"]
    encoded = "\n".join(value for _, value in run.events)
    assert encoded.count("RUN_FINISHED") == 1
    assert "RUN_ERROR" not in encoded


@pytest.mark.asyncio
async def test_terminal_failure_is_event_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tracker = run_tracker.RunTracker()
    monkeypatch.setattr(run_tracker, "_tracker", tracker)
    await sessions.create_session(session_id="failed", title="Failure")
    tracker.start_run("failed", "run-2")

    assert await _terminalize_run(
        "failed",
        outcome="failure",
        emitter=AgentEventEmitter("failed", "run-2"),
        error="boom",
    )
    stored = await sessions.get_session("failed")
    assert stored["messages"] == []
    assert tracker.get_run("failed").status == "error"
