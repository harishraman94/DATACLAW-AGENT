"""Session-owned data cleanup registry.

Core and plugins register small, idempotent cleanup handlers at application
startup.  Deleting a chat runs every handler before removing the session
record, so a failed cascade is retryable and never silently leaves a live
session pointing at partially deleted state.
"""

from __future__ import annotations

import inspect
import shutil
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from dataclaw.config.paths import workspaces_dir

CleanupResult = dict[str, Any] | None
CleanupHandler = Callable[
    [dict[str, Any]],
    CleanupResult | Awaitable[CleanupResult],
]


def _direct_child(root: Path, child_id: str) -> Path:
    """Resolve a single child without permitting traversal or aliases."""
    if not child_id or child_id in {".", ".."} or "/" in child_id or "\\" in child_id:
        raise ValueError("Invalid session id for cleanup")
    resolved_root = root.resolve()
    candidate = resolved_root / child_id
    if candidate.parent != resolved_root:
        raise ValueError("Session cleanup target is outside its owner root")
    return candidate


def _remove_tree_or_link(path: Path) -> bool:
    if path.is_symlink():
        path.unlink()
        return True
    if path.exists():
        shutil.rmtree(path)
        return True
    return False


def cleanup_core_session_files(session: dict[str, Any]) -> CleanupResult:
    """Delete the DataClaw workspace (and independent-chat virtualenv)."""
    session_id = str(session.get("id") or "")
    removed: list[str] = []

    workspace = _direct_child(workspaces_dir(), session_id)
    if _remove_tree_or_link(workspace):
        removed.append("workspace")

    # Project chats use a project-owned virtualenv keyed by project id.  Only
    # independent chats own a venv keyed by their session id.
    if not session.get("projectId"):
        venv = _direct_child(workspaces_dir().parent / "venvs", session_id)
        if _remove_tree_or_link(venv):
            removed.append("venv")

    return {"removed": removed}


class SessionCleanupRegistry:
    """Ordered registry of idempotent session cleanup handlers."""

    def __init__(self) -> None:
        self._handlers: dict[str, CleanupHandler] = {}

    def register(self, name: str, handler: CleanupHandler) -> None:
        if not name or not callable(handler):
            raise ValueError("Session cleanup handlers need a name and callable")
        self._handlers[name] = handler

    async def cleanup(self, session: dict[str, Any]) -> dict[str, Any]:
        results: dict[str, Any] = {}
        handlers = [
            (name, handler)
            for name, handler in self._handlers.items()
            if name != "core"
        ]
        if "core" in self._handlers:
            handlers.append(("core", self._handlers["core"]))
        for name, handler in handlers:
            try:
                result = handler(session)
                if inspect.isawaitable(result):
                    result = await result
            except Exception as exc:
                raise RuntimeError(f"Session cleanup handler '{name}' failed: {exc}") from exc
            results[name] = result or {}
        return results
