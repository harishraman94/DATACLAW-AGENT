"""Compact, durable audit receipts for one agent run."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _skill_source(skill: dict[str, Any]) -> str:
    return str(skill.get("active_body_source") or "installed")


def _body_sha256(skill: dict[str, Any]) -> str:
    return hashlib.sha256(str(skill.get("body") or "").encode("utf-8")).hexdigest()


def build_capability_receipt(
    *,
    run_id: str,
    skills: list[dict[str, Any]],
    tools: list[dict[str, Any]],
) -> dict[str, Any]:
    """Capture the exact capabilities offered to an agent run."""
    now = _now_iso()
    return {
        "schemaVersion": 1,
        "runId": run_id,
        "startedAt": now,
        "updatedAt": now,
        "status": "running",
        "skills": {
            "offered": [
                {
                    "id": str(skill.get("id") or ""),
                    "serialId": str(skill.get("serial_id") or skill.get("id") or ""),
                    "name": str(skill.get("name") or skill.get("id") or ""),
                    "source": _skill_source(skill),
                    "origin": str(skill.get("source") or "local"),
                    "sha256": _body_sha256(skill),
                    "installedStale": bool(skill.get("installed_stale")),
                }
                for skill in skills
            ],
            "used": [],
        },
        "tools": {
            "offered": [
                {
                    "name": str(tool.get("name") or ""),
                    "source": str(tool.get("source") or "builtin"),
                }
                for tool in tools
            ],
            "used": [],
        },
        "outputs": [],
    }


def _result_references(result: Any) -> dict[str, Any]:
    """Select stable output references without duplicating full tool results."""
    if not isinstance(result, dict):
        return {}
    keys = (
        "artifact_id",
        "version",
        "url",
        "path",
        "html_path",
        "source_path",
        "notebook_path",
        "report_path",
        "dataset_id",
    )
    return {
        key: result[key]
        for key in keys
        if isinstance(result.get(key), (str, int, float, bool))
    }


def record_tool_execution(
    receipt: dict[str, Any],
    *,
    tool_name: str,
    call_id: str,
    result: Any,
    status: str,
    visual_artifacts: list[dict[str, Any]] | None = None,
) -> None:
    """Add one executed tool and its durable result/message references."""
    offered = receipt.get("tools", {}).get("offered", [])
    source = next(
        (
            str(tool.get("source") or "builtin")
            for tool in offered
            if tool.get("name") == tool_name
        ),
        "unknown",
    )
    receipt["tools"]["used"].append({
        "name": tool_name,
        "source": source,
        "callId": call_id,
        "status": status,
    })

    output: dict[str, Any] = {
        "toolCallId": call_id,
        "toolName": tool_name,
        "messageId": f"tc-{call_id}",
        "status": status,
    }
    references = _result_references(result)
    if references:
        output["references"] = references
    if visual_artifacts:
        output["visualArtifacts"] = [
            {
                key: artifact[key]
                for key in ("id", "kind", "html_path")
                if artifact.get(key) not in (None, "")
            }
            for artifact in visual_artifacts
        ]
    receipt["outputs"].append(output)

    if (
        tool_name == "fetch_skill"
        and status == "complete"
        and isinstance(result, dict)
        and not result.get("is_error")
    ):
        receipt["skills"]["used"].append({
            "id": str(result.get("skill_id") or result.get("id") or ""),
            "serialId": str(result.get("id") or ""),
            "name": str(result.get("name") or result.get("skill_id") or ""),
            "source": str(result.get("source") or "installed"),
            "origin": str(result.get("origin") or "local"),
            "sha256": str(result.get("sha256") or ""),
            "callId": call_id,
        })
    elif isinstance(result, dict) and isinstance(result.get("reviewer_skill"), dict):
        # The analysis-review tool may invoke a scoped reviewer subagent with
        # an installed rubric skill. Record that internal use explicitly so
        # it is never a hidden capability.
        reviewer_skill = result["reviewer_skill"]
        receipt["skills"]["used"].append({
            "id": str(reviewer_skill.get("id") or ""),
            "serialId": str(reviewer_skill.get("id") or ""),
            "name": str(reviewer_skill.get("name") or reviewer_skill.get("id") or ""),
            "source": str(reviewer_skill.get("source") or "installed"),
            "origin": str(reviewer_skill.get("origin") or "local"),
            "sha256": str(reviewer_skill.get("sha256") or ""),
            "callId": call_id,
            "usedBy": "analysis-reviewer",
        })

    receipt["updatedAt"] = _now_iso()


def finish_capability_receipt(
    receipt: dict[str, Any],
    status: str,
    *,
    reason: str | None = None,
) -> None:
    """Mark a receipt terminal without discarding its partial audit trail."""
    now = _now_iso()
    receipt["status"] = status
    receipt["updatedAt"] = now
    receipt["finishedAt"] = now
    if reason:
        receipt["reason"] = reason
