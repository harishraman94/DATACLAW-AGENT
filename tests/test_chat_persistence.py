"""Tests for chat.py session-message ↔ LLM-message conversion on reload."""

from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

from dataclaw.api.routers.chat import IncomingMessage, _extract_visual_artifacts, _stored_messages_to_llm, receive_message
from dataclaw.capability_receipts import build_capability_receipt, record_tool_execution


def _tool_call_msg(call_id: str, result: str, result_for_llm: str | None = None) -> dict:
    msg: dict = {
        "role": "tool_call",
        "messageId": f"tc-{call_id}",
        "toolCallId": call_id,
        "toolName": "execute_cell",
        "args": "{}",
        "result": result,
        "status": "complete",
    }
    if result_for_llm is not None:
        msg["result_for_llm"] = result_for_llm
    return msg


def test_reviewer_internal_skill_use_is_recorded_in_capability_receipt():
    receipt = build_capability_receipt(
        run_id="review-run",
        skills=[{
            "id": "analysis_review",
            "name": "Analysis review",
            "body": "rubric",
            "source": "local",
        }],
        tools=[{"name": "request_analysis_review", "source": "plugin:analysis-review"}],
    )

    record_tool_execution(
        receipt,
        tool_name="request_analysis_review",
        call_id="review-call",
        result={
            "success": True,
            "reviewer_skill": {
                "id": "analysis_review",
                "name": "Analysis review",
                "source": "installed",
                "origin": "local",
                "sha256": "abc123",
            },
        },
        status="complete",
    )

    assert receipt["skills"]["used"] == [{
        "id": "analysis_review",
        "serialId": "analysis_review",
        "name": "Analysis review",
        "source": "installed",
        "origin": "local",
        "sha256": "abc123",
        "callId": "review-call",
        "usedBy": "analysis-reviewer",
    }]


def test_stored_messages_prefer_result_for_llm():
    """When both fields are persisted, the LLM converter uses the slim one."""
    full = '{"outputs": [{"type": "image", "data": "AAA", "mimetype": "image/png"}]}'
    slim = '{"outputs": [{"type": "image", "elided": true, "note": "<image elided>"}]}'
    msgs = _stored_messages_to_llm([
        {"role": "user", "content": "go"},
        {"role": "assistant", "content": "ok"},
        _tool_call_msg("c1", result=full, result_for_llm=slim),
    ])
    # The tool_result message in the produced LLM messages must contain the
    # slim payload, not the full one with the base64.
    serialized = "\n".join(str(m) for m in msgs)
    assert "AAA" not in serialized
    assert "elided" in serialized


def test_stored_messages_fallback_to_result():
    """Legacy persisted messages without result_for_llm still feed the LLM."""
    full = '{"outputs": [{"type": "text", "text": "hello"}]}'
    msgs = _stored_messages_to_llm([
        {"role": "user", "content": "go"},
        {"role": "assistant", "content": "ok"},
        _tool_call_msg("c1", result=full),
    ])
    serialized = "\n".join(str(m) for m in msgs)
    assert "hello" in serialized


def test_empty_result_for_llm_falls_back_to_result():
    """Defensive: an empty-string result_for_llm shouldn't black-hole the LLM view."""
    full = '{"x": 1}'
    msgs = _stored_messages_to_llm([
        {"role": "user", "content": "go"},
        _tool_call_msg("c1", result=full, result_for_llm=""),
    ])
    serialized = "\n".join(str(m) for m in msgs)
    assert "{\"x\": 1}" in serialized or '"x": 1' in serialized


# ── App compatibility layout persistence ───────────────────────────────────


def test_update_session_request_accepts_app_layout():
    """appLayout must survive the PATCH model for the legacy /app route."""
    from dataclaw.api.routers.chat import UpdateSessionRequest

    layout = {"hidden": ["chart-1", "metric-0"], "order": ["chart-2", "chart-0"]}
    req = UpdateSessionRequest(appLayout=layout)
    updates = req.model_dump(exclude_unset=True)
    assert updates == {"appLayout": layout}


async def test_app_layout_roundtrips_through_session_storage():
    from dataclaw.storage import sessions

    created = await sessions.create_session(title="Layout test")
    layout = {"hidden": ["chart-1"], "order": ["chart-2", "chart-0", "chart-1"]}
    await sessions.update_session(created["id"], {"appLayout": layout})

    loaded = await sessions.get_session(created["id"])
    assert loaded is not None
    assert loaded["appLayout"] == layout


async def test_queue_state_roundtrips_through_session_storage():
    """Queued input is session state, not browser-only state."""
    from dataclaw.storage import sessions

    created = await sessions.create_session(title="Queued work")
    queued = [{"id": "q-1", "text": "Run the sensitivity check", "ts": 123}]
    await sessions.update_session(created["id"], {"queuedMessages": queued, "queuePaused": True})

    loaded = await sessions.get_session(created["id"])
    assert loaded is not None
    assert loaded["queuedMessages"] == queued
    assert loaded["queuePaused"] is True


async def test_pending_action_roundtrips_and_decisions_are_idempotent(monkeypatch):
    """Approval state survives reconnects and duplicate button submissions."""
    import dataclaw.api.run_tracker as run_tracker
    from dataclaw.api.routers.chat import (
        GuardrailDecisionRequest,
        agent_status,
        guardrail_decision,
    )
    from dataclaw.pending_actions import register_guardrail_action
    from dataclaw.storage import sessions

    tracker = run_tracker.RunTracker()
    monkeypatch.setattr(run_tracker, "_tracker", tracker)
    created = await sessions.create_session(title="Durable approval")
    run = tracker.start_run(created["id"], "run-approval")
    event = asyncio.Event()
    approval_id = "guardrail-durable"
    run.guardrail_approvals[approval_id] = event
    await register_guardrail_action(
        run,
        approval_id=approval_id,
        guardrail_id="confirm_delete",
        tool_call_id="call-delete",
        message="Delete the generated files?",
        tool_name="delete_files",
        tool_input={"paths": ["reports/draft.html"]},
    )
    tracker.transition_run(created["id"], "waiting_approval")

    status = await agent_status(created["id"])
    assert status["status"] == "waiting_approval"
    assert status["requires_user_action"] is True
    assert status["pending_actions"][0]["tool"]["name"] == "delete_files"

    first = await guardrail_decision(
        created["id"],
        approval_id,
        GuardrailDecisionRequest(approved=False, feedback="Keep the draft."),
    )
    assert first == {
        "ok": True,
        "approved": False,
        "state": "denied",
        "idempotent": False,
    }
    assert event.is_set()
    assert run.guardrail_decisions[approval_id]["feedback"] == "Keep the draft."

    duplicate = await guardrail_decision(
        created["id"],
        approval_id,
        GuardrailDecisionRequest(approved=False, feedback="Keep the draft."),
    )
    assert duplicate["idempotent"] is True

    with pytest.raises(HTTPException) as conflict:
        await guardrail_decision(
            created["id"],
            approval_id,
            GuardrailDecisionRequest(approved=True),
        )
    assert conflict.value.status_code == 409

    stored = await sessions.get_session(created["id"])
    action = stored["pendingActions"][0]
    assert action["state"] == "denied"
    assert action["feedback"] == "Keep the draft."


# ── Loose visual normalization for compatibility App view ──────────────────


def test_extract_visual_artifacts_for_metric_and_plotly_chart():
    metric_artifacts = _extract_visual_artifacts(
        tool_name="display_metric",
        tool_call_id="m1",
        tool_input={},
        result={
            "type": "metric",
            "label": "Revenue",
            "value": "$1.2M",
            "delta": "+8%",
            "unit": "",
            "trend": "up",
        },
    )
    assert len(metric_artifacts) == 1
    assert metric_artifacts[0]["kind"] == "metric"
    assert metric_artifacts[0]["metric"]["label"] == "Revenue"
    assert metric_artifacts[0]["source_tool_call_id"] == "m1"

    figure = {"data": [{"x": ["A", "B"], "y": [1, 2], "type": "bar"}], "layout": {"title": "A vs B"}}
    chart_artifacts = _extract_visual_artifacts(
        tool_name="display_cell_output",
        tool_call_id="c1",
        tool_input={"cell_index": 4},
        result={
            "cell_index": 4,
            "caption": "B is twice A in this sample.",
            "outputs": [{"type": "plotly", "figure": figure}],
        },
    )
    assert len(chart_artifacts) == 1
    assert chart_artifacts[0]["kind"] == "chart"
    assert chart_artifacts[0]["figure"] == figure
    assert chart_artifacts[0]["caption"] == "B is twice A in this sample."
    assert chart_artifacts[0]["source_cell_index"] == 4


def test_extract_visual_artifacts_for_live_report():
    artifacts = _extract_visual_artifacts(
        tool_name="report_add_section",
        tool_call_id="r1",
        tool_input={"section_type": "header"},
        result={
            "type": "report",
            "html_path": "/tmp/workspace/reports/live.html",
            "title": "Live Report",
            "updated": True,
        },
    )
    assert len(artifacts) == 1
    assert artifacts[0]["kind"] == "report"
    assert artifacts[0]["html_path"] == "/tmp/workspace/reports/live.html"
    assert artifacts[0]["title"] == "Live Report"


def test_extract_visual_artifacts_keeps_successful_report_publish_on_reload():
    published = _extract_visual_artifacts(
        tool_name="report_publish",
        tool_call_id="r2",
        tool_input={},
        result={
            "published": True,
            "publication_status": "published",
            "html_path": "reports/quality.html",
            "title": "Quality report",
        },
    )
    blocked = _extract_visual_artifacts(
        tool_name="report_publish",
        tool_call_id="r3",
        tool_input={},
        result={
            "published": False,
            "publication_status": "blocked",
            "html_path": "reports/blocked.html",
        },
    )

    assert [artifact["html_path"] for artifact in published] == ["reports/quality.html"]
    assert blocked == []


async def test_openclaw_tool_call_message_persists_as_dataclaw_tool_call():
    from dataclaw.storage import sessions

    created = await sessions.create_session(title="OpenClaw tool call")
    receipt = build_capability_receipt(
        run_id="external-run",
        skills=[],
        tools=[{"name": "report_add_section", "source": "plugin:artifacts"}],
    )
    await sessions.upsert_capability_receipt(created["id"], receipt)
    await receive_message(
        created["id"],
        IncomingMessage(
            role="tool_call",
            messageId="tc-oc-1",
            toolCallId="oc-1",
            toolName="dataclaw_report_add_section",
            args={"section_type": "header"},
            result={
                "type": "report",
                "html_path": "/tmp/workspace/reports/live.html",
                "title": "Live Report",
            },
            startedAt="2026-07-14T09:00:00+00:00",
            finishedAt="2026-07-14T09:00:04+00:00",
        ),
    )

    loaded = await sessions.get_session(created["id"])
    assert loaded is not None
    msg = loaded["messages"][-1]
    assert msg["role"] == "tool_call"
    assert msg["toolName"] == "report_add_section"
    assert msg["args"] == '{"section_type": "header"}'
    assert '"html_path": "/tmp/workspace/reports/live.html"' in msg["result"]
    assert msg["startedAt"] == "2026-07-14T09:00:00+00:00"
    assert msg["finishedAt"] == "2026-07-14T09:00:04+00:00"
    assert loaded["visualArtifacts"][0]["kind"] == "report"
    receipt = loaded["capabilityReceipts"][0]
    assert receipt["tools"]["used"][0] == {
        "name": "report_add_section",
        "source": "plugin:artifacts",
        "callId": "oc-1",
        "status": "complete",
    }
    assert receipt["outputs"][0]["visualArtifacts"][0]["kind"] == "report"


async def test_openclaw_tool_call_message_redacts_llm_result():
    from dataclaw.storage import sessions

    created = await sessions.create_session(title="OpenClaw redaction")
    await receive_message(
        created["id"],
        IncomingMessage(
            role="tool_call",
            messageId="tc-img-1",
            toolCallId="img-1",
            toolName="dataclaw_display_cell_output",
            args={"cell_index": 2},
            result={
                "outputs": [
                    {
                        "type": "image",
                        "mimetype": "image/png",
                        "data": "A" * 100,
                        "summary": "chart",
                    }
                ]
            },
        ),
    )

    loaded = await sessions.get_session(created["id"])
    assert loaded is not None
    msg = loaded["messages"][-1]
    assert "A" * 20 in msg["result"]
    assert "A" * 20 not in msg["result_for_llm"]
    assert "image elided" in msg["result_for_llm"]
