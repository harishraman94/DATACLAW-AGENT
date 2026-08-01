"""Decode Dataclaw correlation carried in the Hermes task id."""

from __future__ import annotations

import base64
import json
from typing import Any

PREFIX = "dc1_"


def decode_correlation(task_id: str) -> dict[str, Any]:
    if not isinstance(task_id, str) or not task_id.startswith(PREFIX):
        raise ValueError("Hermes task is not correlated to a Dataclaw run")
    encoded = task_id[len(PREFIX) :]
    payload = json.loads(
        base64.urlsafe_b64decode(
            encoded + "=" * (-len(encoded) % 4)
        ).decode("utf-8")
    )
    if not isinstance(payload, dict):
        raise ValueError("Invalid Dataclaw correlation")
    if not payload.get("runId") or not payload.get("sessionId"):
        raise ValueError("Incomplete Dataclaw correlation")
    if payload.get("projectId") is not None and not isinstance(
        payload["projectId"], str
    ):
        raise ValueError("Invalid Dataclaw project correlation")
    return payload
