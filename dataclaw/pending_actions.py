"""Durable user-action requests shared by agent runtimes and the chat API."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from dataclaw.storage import sessions


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def register_guardrail_action(
    run: Any,
    *,
    approval_id: str,
    guardrail_id: str | None,
    tool_call_id: str,
    message: str,
    severity: str = "warning",
    timeout_seconds: int = 300,
    tool_name: str | None = None,
    tool_input: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Register an approval request in memory and on the owning session."""
    created_at = _now()
    action: dict[str, Any] = {
        "id": approval_id,
        "kind": "guardrail_approval",
        "state": "pending",
        "requiresUserAction": True,
        "runId": run.run_id,
        "guardrailId": guardrail_id or "guardrail",
        "toolCallId": tool_call_id,
        "message": message,
        "severity": severity,
        "createdAt": created_at.isoformat(),
        "expiresAt": (
            created_at + timedelta(seconds=max(1, timeout_seconds))
        ).isoformat(),
        "decision": None,
        "feedback": None,
    }
    if tool_name:
        action["tool"] = {
            "name": tool_name,
            "arguments": tool_input or {},
        }
    run.guardrail_requests[approval_id] = action
    await sessions.upsert_pending_action(run.thread_id, action)
    return action


async def resolve_guardrail_action(
    run: Any,
    approval_id: str,
    *,
    state: str,
    approved: bool | None = None,
    feedback: str | None = None,
) -> dict[str, Any] | None:
    """Resolve an approval request while retaining it for replay/idempotency."""
    action = run.guardrail_requests.get(approval_id)
    if action is None:
        return None
    resolved = {
        **action,
        "state": state,
        "requiresUserAction": False,
        "decision": approved,
        "feedback": feedback,
        "resolvedAt": _now().isoformat(),
    }
    run.guardrail_requests[approval_id] = resolved
    await sessions.upsert_pending_action(run.thread_id, resolved)
    return resolved


def public_pending_actions(run: Any) -> list[dict[str, Any]]:
    """Return a stable, JSON-ready action list for run status responses."""
    return sorted(
        (dict(action) for action in run.guardrail_requests.values()),
        key=lambda action: str(action.get("createdAt") or ""),
    )
