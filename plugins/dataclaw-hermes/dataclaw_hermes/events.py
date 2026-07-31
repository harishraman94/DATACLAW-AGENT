"""Fixture-backed Hermes event normalization."""

from __future__ import annotations

from typing import Any


def event_name(event: dict[str, Any]) -> str:
    return str(event.get("event") or event.get("type") or "").strip()


def text_delta(event: dict[str, Any]) -> str:
    if event_name(event) in {
        "message.delta",
        "assistant.delta",
        "response.output_text.delta",
    }:
        return str(event.get("delta") or event.get("text") or "")
    return ""


def is_terminal(event: dict[str, Any]) -> bool:
    return event_name(event) in {
        "run.completed",
        "run.failed",
        "run.cancelled",
    }
