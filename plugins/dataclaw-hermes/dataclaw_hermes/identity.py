"""Opaque correlation envelope carried through Hermes' session/task id."""

from __future__ import annotations

import base64
import json
from typing import Any

PREFIX = "dc1_"


def encode_correlation(
    *, run_id: str, session_id: str, project_id: str | None
) -> str:
    payload = json.dumps(
        {"runId": run_id, "sessionId": session_id, "projectId": project_id},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    encoded = base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")
    return PREFIX + encoded


def decode_correlation(value: str) -> dict[str, Any]:
    if not value.startswith(PREFIX):
        raise ValueError("Not a Dataclaw Hermes correlation id")
    encoded = value[len(PREFIX) :]
    padded = encoded + "=" * (-len(encoded) % 4)
    payload = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Invalid correlation payload")
    for key in ("runId", "sessionId"):
        if not isinstance(payload.get(key), str) or not payload[key]:
            raise ValueError(f"Missing correlation field: {key}")
    project_id = payload.get("projectId")
    if project_id is not None and not isinstance(project_id, str):
        raise ValueError("Invalid projectId")
    return payload
